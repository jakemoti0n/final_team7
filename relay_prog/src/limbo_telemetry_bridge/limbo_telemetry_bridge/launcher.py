"""로봇 컴퓨터에서 patrol_node를 띄우고 끈다 (관제 명령 start·stop, docs/CONTROL_API_DRAFT.md §2.5).

서버(인터넷 너머일 수 있음)는 명령과 waypoint 목록만 보낸다. 이 모듈이
1. 받은 목록을 서버와 같은 규칙으로 검사하고
2. waypoint_dir에 YAML을 원자적으로 저장한 뒤(임시 파일 → os.replace)
3. 그 절대 경로를 waypoints 파라미터로 넘겨 patrol_node를 띄운다.
끌 때는 자기가 띄운 프로세스에만 SIGTERM을 보낸다. 순찰 노드는 SIGTERM을 받으면 진행 중인
Nav2 목표를 취소하고 끝난다(limbo_patrol patrol_node.main).
"""
import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time

import yaml

ROUTE_FILE = 'dashboard_waypoints.yaml'
MAX_WAYPOINTS = 200
COMMANDS = ('pause', 'resume', 'start', 'stop')


class LaunchError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code

    def __str__(self):
        return f'{self.code}: {self.args[0]}'


def validate_route(points, bounds):
    """서버 dashboard/server/waypoints.py WaypointFile._validate와 같은 규칙·같은 문구. 바꾸면 같이 바꾼다."""
    def bad(message):
        raise LaunchError('invalid_route', message)
    if not isinstance(points, list) or not points or not isinstance(points[-1], dict) or points[-1].get('type') != 'stop':
        bad('The final waypoint must be a stop')
    if len(points) > MAX_WAYPOINTS:
        bad(f'At most {MAX_WAYPOINTS} waypoints are allowed')
    if not isinstance(bounds, dict) or set(bounds) != {'x_min', 'y_min', 'x_max', 'y_max'} or not all(
            type(v) in (int, float) and math.isfinite(v) for v in bounds.values()):
        bad('Map bounds are invalid')
    seen = set()
    for p in points:
        if not isinstance(p, dict) or not isinstance(p.get('name'), str) or not 1 <= len(p['name'].strip()) <= 32:
            bad('Each waypoint needs a name of 1–32 characters')
        key = p['name'].strip().casefold()
        if key in seen:
            bad('Waypoint names must be unique')
        seen.add(key)
        if p.get('type') not in ('pass', 'stop'):
            bad('Waypoint type must be pass or stop')
        for field in ('x', 'y', 'yaw', 'wait_sec'):
            value = p.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                bad(f'Waypoint {field} must be finite')
        if not bounds['x_min'] <= p['x'] <= bounds['x_max'] or not bounds['y_min'] <= p['y'] <= bounds['y_max']:
            bad('Waypoint position must be inside the map')
        if p['wait_sec'] < 0:
            bad('wait_sec cannot be negative')
        if set(p) != {'name', 'type', 'x', 'y', 'yaw', 'wait_sec'}:   # Bridge만: 모르는 필드를 YAML에 쓰지 않음
            bad('Waypoint fields must be name, type, x, y, yaw and wait_sec')


def other_patrol_running(proc_root=Path('/proc'), exclude=()):
    """이 컴퓨터에 patrol_node가 있는가. 다른 터미널에서 띄운 노드도 포함 (예전 서버 PatrolLauncher에서 옮김)."""
    for cmdline in Path(proc_root).glob('[0-9]*/cmdline'):
        if cmdline.parent.name in exclude:
            continue
        try:
            args = [part.decode(errors='replace') for part in cmdline.read_bytes().split(b'\0') if part]
        except (OSError, PermissionError):
            continue
        if not args:
            continue
        if Path(args[0]).name == 'patrol_node' or (len(args) > 1 and Path(args[1]).name == 'patrol_node'):
            return True
        if ((Path(args[0]).name == 'ros2' and args[1:4] == ['run', 'limbo_patrol', 'patrol_node'])
                or (len(args) > 1 and Path(args[1]).name == 'ros2' and args[2:5] == ['run', 'limbo_patrol', 'patrol_node'])):
            return True
    return False


class PatrolLauncher:
    """명령 작업 스레드(start·stop)와 ROS 타이머(poll)가 함께 쓰므로 잠금으로 보호한다."""

    def __init__(self, settings, popen=subprocess.Popen, proc_root=Path('/proc'), killpg=os.killpg):
        self.ros_setup = Path(settings['ros_setup'])
        self.workspace = Path(settings['workspace'])
        self.waypoint_dir = Path(settings['waypoint_dir'])
        self.use_sim_time = settings['use_sim_time']
        self.popen, self.proc_root, self.killpg = popen, proc_root, killpg
        self.lock = threading.Lock()
        self.process = None
        self.revision = self.log_path = None
        self.other = False

    @property
    def workspace_setup(self):
        return self.workspace / 'install/setup.bash'

    @property
    def executable(self):
        return self.workspace / 'install/limbo_patrol/lib/limbo_patrol/patrol_node'

    def _mine(self):
        return () if self.process is None else (str(self.process.pid),)

    def refresh(self):
        """2초마다(ROS 타이머) 다른 곳에서 띄운 patrol_node가 있는지 다시 본다."""
        found = other_patrol_running(self.proc_root, self._mine())
        with self.lock:
            self.other = found
        return found

    def save_route(self, route):
        """검사한 목록을 waypoint_dir/dashboard_waypoints.yaml로 원자적으로 저장하고 절대 경로를 돌려준다."""
        validate_route(route.get('waypoints') if isinstance(route, dict) else None,
                       route.get('bounds') if isinstance(route, dict) else None)
        path = (self.waypoint_dir / ROUTE_FILE).resolve()
        rendered = yaml.safe_dump({'waypoints': route['waypoints']}, allow_unicode=True, sort_keys=False).encode()
        temp = None
        try:
            self.waypoint_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.waypoints-', suffix='.yaml', delete=False) as out:
                temp = Path(out.name)
                out.write(rendered)
                out.flush()
                os.fsync(out.fileno())
            os.chmod(temp, 0o644)
            os.replace(temp, path)
        except OSError as exc:
            raise LaunchError('waypoint_save_failed', str(exc)) from exc
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)
        return path

    def start(self, route):
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                raise LaunchError('patrol_already_running', 'A Bridge-started patrol_node is already running')
        if other_patrol_running(self.proc_root, self._mine()):
            raise LaunchError('patrol_already_running', 'Another patrol_node is already running on this robot')
        for path in (self.ros_setup, self.workspace_setup, self.executable):
            if not path.is_file():
                raise LaunchError('patrol_not_installed', f'Required file is missing: {path}')
        waypoints = self.save_route(route)
        env = os.environ.copy()        # ROS_DOMAIN_ID 등은 Bridge 프로세스 환경 그대로
        env.pop('VIRTUAL_ENV', None)
        # ros2 run을 거치지 않고 노드를 직접 exec한다: ros2 run 래퍼는 SIGTERM 때 자식을 남긴다
        script = 'source "$1" && source "$2" && exec "$3" --ros-args -p "use_sim_time:=$5" -p "waypoints:=$4"'
        with tempfile.NamedTemporaryFile(prefix='limbo-patrol-', suffix='.log', delete=False) as output:
            try:
                process = self.popen(
                    ['bash', '-c', script, 'patrol-launch', str(self.ros_setup), str(self.workspace_setup),
                     str(self.executable), str(waypoints), 'true' if self.use_sim_time else 'false'],
                    cwd=self.workspace, env=env, stdout=output, stderr=subprocess.STDOUT,
                    start_new_session=True)
            except OSError as exc:
                Path(output.name).unlink(missing_ok=True)
                raise LaunchError('patrol_launch_failed', str(exc)) from exc
        with self.lock:
            self.process, self.revision, self.log_path = process, route.get('revision'), output.name
        return f'started pid {process.pid} with {waypoints}'

    def stop(self):
        with self.lock:
            process = self.process
            if process is None or process.poll() is not None:
                raise LaunchError('patrol_not_running', 'No Bridge-started patrol_node is running')
        try:
            self.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            raise LaunchError('patrol_not_running', 'The patrol_node has already exited')
        except OSError as exc:
            raise LaunchError('patrol_stop_failed', str(exc)) from exc
        return f'SIGTERM sent to pid {process.pid}'

    def status(self):
        """텔레메트리 v3 launcher 객체"""
        with self.lock:
            process = self.process
            code = None if process is None else process.poll()
            return dict(commands=list(COMMANDS),
                        state='idle' if process is None else 'running' if code is None else 'exited',
                        pid=None if process is None else process.pid, exit_code=code,
                        waypoints_revision=self.revision, log=self.log_path,
                        other_patrol_running=self.other)

    def shutdown(self, timeout=15.0, sleep=time.sleep, monotonic=time.monotonic):
        """Bridge가 끝날 때: 자기가 띄운 노드를 SIGTERM으로 끈다 (원격 제어 없이 로봇이 계속 돌지 않게).
        제한 시간 안에 안 끝나면 그때만 SIGKILL."""
        try:
            self.stop()
        except LaunchError:
            return
        deadline = monotonic() + timeout
        while self.process.poll() is None and monotonic() < deadline:
            sleep(0.1)
        if self.process.poll() is None:
            try:
                self.killpg(self.process.pid, signal.SIGKILL)
            except OSError:
                pass
