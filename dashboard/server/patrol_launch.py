"""Start one patrol_node against the waypoint file shown in the dashboard."""
import os
import signal
from pathlib import Path
import subprocess
import tempfile


class LaunchError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class PatrolLauncher:
    def __init__(self, waypoints, domain_id, workspace, ros_setup=Path('/opt/ros/jazzy/setup.bash'), popen=subprocess.Popen):
        self.waypoints = waypoints
        self.domain_id = domain_id
        self.workspace = Path(workspace)
        self.ros_setup = Path(ros_setup)
        self.popen = popen
        self.process = None
        self.log_path = None

    def _other_patrol_running(self):
        """Block duplicate patrol nodes, including ones started in a terminal."""
        for cmdline in Path('/proc').glob('[0-9]*/cmdline'):
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

    def start(self, use_sim_time=True):
        if self.process is not None and self.process.poll() is None or self._other_patrol_running():
            raise LaunchError('patrol_already_running', 'A patrol_node is already running')
        if self.domain_id is None:
            raise LaunchError('ros_domain_not_configured', 'Configure patrol_ros_domain_id before starting patrol')
        workspace_setup = self.workspace / 'install/setup.bash'
        executable = self.workspace / 'install/limbo_patrol/lib/limbo_patrol/patrol_node'
        for path in (self.ros_setup, workspace_setup, executable, self.waypoints.path):
            if not path.is_file():
                raise LaunchError('patrol_not_installed', f'Required file is missing: {path}')
        data, _ = self.waypoints.read()
        self.waypoints._validate(data['waypoints'])
        env = os.environ.copy()
        env['ROS_DOMAIN_ID'] = str(self.domain_id)
        env.pop('VIRTUAL_ENV', None)
        # Run the node directly: ros2 run leaves a child behind when its wrapper exits.
        script = 'source "$1" && source "$2" && exec "$3" --ros-args -p "use_sim_time:=$5" -p "waypoints:=$4"'
        with tempfile.NamedTemporaryFile(prefix='limbo-patrol-', suffix='.log', delete=False) as output:
            try:
                self.process = self.popen(
                    ['bash', '-c', script, 'patrol-launch', str(self.ros_setup), str(workspace_setup),
                     str(executable), str(self.waypoints.path), 'true' if use_sim_time else 'false'],
                    cwd=self.workspace, env=env, stdout=output, stderr=subprocess.STDOUT,
                    start_new_session=True)
            except OSError as exc:
                Path(output.name).unlink(missing_ok=True)
                raise LaunchError('patrol_launch_failed', str(exc)) from exc
        self.log_path = output.name
        return {'status': 'starting', 'pid': self.process.pid, 'log': output.name,
                'waypoints_file': str(self.waypoints.path)}

    def status(self):
        if self.process is None:
            return {'status': 'idle'}
        code = self.process.poll()
        return {'status': 'running' if code is None else 'exited', 'pid': self.process.pid,
                'exit_code': code, 'log': self.log_path}

    def stop(self):
        if self.process is None or self.process.poll() is not None:
            raise LaunchError('patrol_not_running', 'No Dashboard-started patrol_node is running')
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            raise LaunchError('patrol_not_running', 'The patrol_node has already exited')
        except OSError as exc:
            raise LaunchError('patrol_stop_failed', str(exc)) from exc
        return {'status': 'stopping', 'pid': self.process.pid, 'log': self.log_path}
