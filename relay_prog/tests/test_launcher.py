"""순찰 시작·종료(start·stop) 시험: 검증 규칙, 원자적 저장, 중복 거절, 가짜 프로세스로 시작·종료, 명령 흐름.

실제 ROS 노드는 띄우지 않는다 (popen·/proc·killpg를 바꿔 끼움). 계약: docs/CONTROL_API_DRAFT.md §2.5
"""
import json
import signal
import threading
from pathlib import Path

import pytest
import yaml
from limbo_telemetry_bridge.config import load_config, resolve_patrol_launch
from limbo_telemetry_bridge.launcher import LaunchError, PatrolLauncher, ROUTE_FILE, other_patrol_running, validate_route
from limbo_telemetry_bridge.state import State
from limbo_telemetry_bridge.transport import Sender, command_from
from receiver import Receiver, validate

DEFAULT = Path(__file__).resolve().parents[1]/'src/limbo_telemetry_bridge/config/bridge.yaml'
CASES = json.loads((Path(__file__).parent/'data/route_cases.json').read_text())
REV = 'b' * 64


def route(**change):
    return {'revision': REV, 'bounds': CASES['bounds'], 'waypoints': CASES['cases'][0]['waypoints'], **change}


@pytest.mark.parametrize('case', CASES['cases'], ids=lambda c: c['name'])
def test_route_rules_match_server_cases(case):
    if case['error'] is None:
        validate_route(case['waypoints'], CASES['bounds'])
    else:
        with pytest.raises(LaunchError) as raised:
            validate_route(case['waypoints'], CASES['bounds'])
        assert raised.value.code == 'invalid_route' and raised.value.args[0] == case['error']


def test_bridge_extra_route_checks():
    with pytest.raises(LaunchError, match='bounds'):
        validate_route(route()['waypoints'], {'x_min': 0})
    with pytest.raises(LaunchError, match='fields'):
        validate_route([{**route()['waypoints'][1], 'cmd': 'rm -rf'}], CASES['bounds'])
    with pytest.raises(LaunchError, match='At most'):
        validate_route([{**route()['waypoints'][1], 'name': f'P{i}'} for i in range(201)], CASES['bounds'])


class Process:
    def __init__(self, pid=4321):
        self.pid, self.code = pid, None
    def poll(self):
        return self.code


def workspace(tmp_path):
    ws = tmp_path / 'ws'
    for name in ('install/setup.bash', 'install/limbo_patrol/lib/limbo_patrol/patrol_node'):
        (ws / name).parent.mkdir(parents=True, exist_ok=True)
        (ws / name).write_text('')
    ros = tmp_path / 'ros_setup.bash'
    ros.write_text('')
    proc = tmp_path / 'proc'
    proc.mkdir()
    return dict(ros_setup=str(ros), workspace=str(ws), waypoint_dir=str(tmp_path / 'routes'), use_sim_time=True), proc


def fake_proc(proc, pid, *args):
    (proc / str(pid)).mkdir()
    (proc / str(pid) / 'cmdline').write_bytes(b'\0'.join(a.encode() for a in args) + b'\0')


def launcher(tmp_path):
    settings, proc = workspace(tmp_path)
    calls, killed = [], []
    def popen(args, **kwargs):
        calls.append((args, kwargs))
        return Process(4321 + len(calls))
    return PatrolLauncher(settings, popen=popen, proc_root=proc, killpg=lambda *a: killed.append(a)), calls, killed, proc


def test_start_saves_route_atomically_and_passes_absolute_path(tmp_path, monkeypatch):
    monkeypatch.setenv('ROS_DOMAIN_ID', '91')
    monkeypatch.setenv('VIRTUAL_ENV', '/somewhere')
    patrol, calls, _, _ = launcher(tmp_path)
    message = patrol.start(route())
    saved = (tmp_path / 'routes' / ROUTE_FILE).resolve()
    assert yaml.safe_load(saved.read_text()) == {'waypoints': route()['waypoints']}
    assert not list(saved.parent.glob('.waypoints-*'))            # 임시 파일이 남지 않음
    args, options = calls[0]
    assert args[:2] == ['bash', '-c'] and 'exec "$3"' in args[2]
    assert args[-2:] == [str(saved), 'true'] and Path(args[-2]).is_absolute()
    assert options['env']['ROS_DOMAIN_ID'] == '91' and 'VIRTUAL_ENV' not in options['env']
    assert options['start_new_session'] is True
    assert str(saved) in message
    status = patrol.status()
    assert status['state'] == 'running' and status['pid'] == 4322 and status['waypoints_revision'] == REV
    assert status['commands'] == ['pause', 'resume', 'start', 'stop']
    with pytest.raises(LaunchError) as raised:
        patrol.start(route())
    assert raised.value.code == 'patrol_already_running'


def test_invalid_route_is_not_saved_and_not_started(tmp_path):
    patrol, calls, _, _ = launcher(tmp_path)
    previous = tmp_path / 'routes' / ROUTE_FILE
    previous.parent.mkdir()
    previous.write_text('waypoints: [old]\n')
    with pytest.raises(LaunchError) as raised:
        patrol.start(route(waypoints=CASES['cases'][2]['waypoints']))
    assert str(raised.value) == 'invalid_route: The final waypoint must be a stop'
    assert previous.read_text() == 'waypoints: [old]\n' and calls == []


def test_other_patrol_node_blocks_start(tmp_path):
    patrol, calls, _, proc = launcher(tmp_path)
    fake_proc(proc, 50, '/usr/bin/python3', '/x/install/limbo_patrol/lib/limbo_patrol/patrol_node', '--ros-args')
    assert patrol.refresh() is True and patrol.status()['other_patrol_running'] is True
    with pytest.raises(LaunchError, match='patrol_already_running'):
        patrol.start(route())
    assert calls == []
    assert other_patrol_running(proc, exclude=('50',)) is False
    fake_proc(proc, 51, '/opt/ros/jazzy/bin/ros2', 'run', 'limbo_patrol', 'patrol_node')
    assert other_patrol_running(proc, exclude=('50',)) is True


def test_own_process_is_not_counted_as_other(tmp_path):
    patrol, _, _, proc = launcher(tmp_path)
    patrol.start(route())
    fake_proc(proc, 4322, '/x/patrol_node', '--ros-args')
    assert patrol.refresh() is False


def test_missing_install_is_reported(tmp_path):
    patrol, calls, _, _ = launcher(tmp_path)
    patrol.executable.unlink()
    with pytest.raises(LaunchError, match='patrol_not_installed'):
        patrol.start(route())


def test_stop_only_signals_own_process_and_reports_exit(tmp_path):
    patrol, _, killed, _ = launcher(tmp_path)
    with pytest.raises(LaunchError, match='patrol_not_running'):
        patrol.stop()
    patrol.start(route())
    assert 'SIGTERM' in patrol.stop()
    assert killed == [(4322, signal.SIGTERM)]
    patrol.process.code = 0
    status = patrol.status()
    assert status['state'] == 'exited' and status['exit_code'] == 0
    with pytest.raises(LaunchError, match='patrol_not_running'):
        patrol.stop()
    patrol.start(route())                               # 끝난 뒤 다시 시작 가능
    assert patrol.status()['pid'] == 4323


def test_shutdown_terminates_then_kills_after_timeout(tmp_path):
    patrol, _, killed, _ = launcher(tmp_path)
    patrol.shutdown()                                    # 띄운 게 없으면 아무것도 안 함
    assert killed == []
    patrol.start(route())
    clock = [0.0]
    patrol.shutdown(timeout=1, sleep=lambda s: clock.__setitem__(0, clock[0] + s), monotonic=lambda: clock[0])
    assert killed == [(4322, signal.SIGTERM), (4322, signal.SIGKILL)]


def test_status_is_valid_v3_launcher(tmp_path):
    patrol, _, _, _ = launcher(tmp_path)
    state = State(launcher_status=patrol.status)
    validate(state.snapshot())
    patrol.start(route())
    validate(state.snapshot())
    patrol.process.code = 3
    snapshot = state.snapshot()
    validate(snapshot)
    assert snapshot['launcher']['exit_code'] == 3


# ---- 설정 ----

def test_patrol_launch_configuration(tmp_path):
    config = load_config(DEFAULT)
    assert config['patrol_launch']['use_sim_time'] is True
    for change in ({'use_sim_time': 'yes'}, {'workspace': ''}, {'extra': 1}):
        raw = yaml.safe_load(DEFAULT.read_text())
        raw['patrol_launch'].update(change)
        path = tmp_path / 'bad.yaml'
        path.write_text(yaml.safe_dump(raw))
        with pytest.raises(ValueError, match='patrol_launch'):
            load_config(path)
    raw = yaml.safe_load(DEFAULT.read_text())
    del raw['patrol_launch']
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match='patrol_launch'):
        load_config(path)


def test_resolve_patrol_launch_paths(tmp_path):
    settings, _ = workspace(tmp_path)
    config = {'patrol_launch': {**settings, 'workspace': 'ws', 'waypoint_dir': 'state/routes'}}
    resolved = resolve_patrol_launch(config, base=tmp_path)
    assert resolved['workspace'] == str(tmp_path / 'ws') and (tmp_path / 'state/routes').is_dir()
    with pytest.raises(ValueError, match='workspace has no install/setup.bash'):
        resolve_patrol_launch({'patrol_launch': {**settings, 'workspace': 'nowhere'}}, base=tmp_path)
    with pytest.raises(ValueError, match='ros_setup not found'):
        resolve_patrol_launch({'patrol_launch': {**settings, 'ros_setup': 'missing.bash'}}, base=tmp_path)
    (tmp_path / 'file').write_text('')
    with pytest.raises(ValueError, match='waypoint_dir is not writable'):
        resolve_patrol_launch({'patrol_launch': {**settings, 'waypoint_dir': str(tmp_path / 'file/x')}}, base=tmp_path)


# ---- 명령 흐름 (commands/next → claim → launch → result) ----

def test_command_from_accepts_route_only_for_start():
    base = {'request_id': '6f1c5a0e-0000-4000-8000-000000000000', 'ttl_ms': 1000}
    assert command_from(json.dumps({**base, 'command': 'start', 'route': route()}))['route']['revision'] == REV
    assert command_from(json.dumps({**base, 'command': 'stop'}))['command'] == 'stop'
    for bad in ({**base, 'command': 'start'}, {**base, 'command': 'stop', 'route': route()},
                {**base, 'command': 'start', 'route': {'waypoints': []}}):
        with pytest.raises(ValueError):
            command_from(json.dumps(bad))


class Controller:
    def __init__(self, outcome=(True, 'started pid 1')):
        self.outcome, self.launched = outcome, []
    def call(self, command):
        raise AssertionError('start·stop must not call a ROS service')
    def launch(self, command):
        self.launched.append(command)
        return self.outcome


@pytest.fixture
def server():
    receiver = Receiver(('127.0.0.1', 0))
    thread = threading.Thread(target=receiver.serve_forever, daemon=True)
    thread.start()
    yield receiver
    receiver.shutdown()
    receiver.server_close()
    thread.join(2)


def config(server):
    return dict(server_url=f'http://127.0.0.1:{server.server_port}', request_timeout_s=0.5, send_interval_s=0.1,
                control=dict(command_wait_s=0.3, service_timeout_s=0.2))


def run(server, controller, command, **kwargs):
    import time
    sender = Sender(State(), config(server), controller=controller)
    sender.start()
    try:
        request_id = server.enqueue(command, **kwargs)
        end = time.monotonic() + 3
        while request_id not in server.results and time.monotonic() < end:
            time.sleep(0.01)
        return server.results[request_id]
    finally:
        sender.stop()


def test_start_command_reaches_launcher_with_route(server):
    big = [{'name': f'P{i}', 'type': 'pass', 'x': 1, 'y': 1, 'yaw': 0, 'wait_sec': 0} for i in range(199)]
    big.append({'name': 'End', 'type': 'stop', 'x': 2, 'y': 2, 'yaw': 0, 'wait_sec': 0})
    controller = Controller()
    result = run(server, controller, 'start', route=route(waypoints=big))   # 8 KiB보다 큰 명령
    assert result['outcome'] == 'accepted' and result['message'] == 'started pid 1'
    assert result['service_latency_ms'] is not None
    assert len(controller.launched[0]['route']['waypoints']) == 200


def test_stop_rejection_reason_goes_to_result(server):
    controller = Controller((False, 'patrol_not_running: No Bridge-started patrol_node is running'))
    result = run(server, controller, 'stop')
    assert result['outcome'] == 'rejected' and result['message'].startswith('patrol_not_running')


# ---- 로봇 토큰 (2단계) ----

def test_token_from_environment_or_file(tmp_path):
    from limbo_telemetry_bridge.config import resolve_token
    token = 'robot-token-0123456789abcdef'
    assert resolve_token({'token_file': None}, {}) is None
    assert resolve_token({'token_file': None}, {'LIMBO_ROBOT_TOKEN': f' {token}\n'}) == token
    (tmp_path / 'robot_token').write_text(token + '\n')
    assert resolve_token({'token_file': 'robot_token'}, {}, base=tmp_path) == token
    assert resolve_token({'token_file': 'robot_token'}, {'LIMBO_ROBOT_TOKEN': 'environment-wins-000001'}, base=tmp_path) == 'environment-wins-000001'
    with pytest.raises(ValueError, match='cannot be read'):
        resolve_token({'token_file': 'missing'}, {}, base=tmp_path)
    (tmp_path / 'empty').write_text('\n')
    with pytest.raises(ValueError, match='empty'):
        resolve_token({'token_file': 'empty'}, {}, base=tmp_path)
    with pytest.raises(ValueError, match='at least 16'):
        resolve_token({'token_file': None}, {'LIMBO_ROBOT_TOKEN': 'short'})
    raw = yaml.safe_load(DEFAULT.read_text())
    assert raw['token_file'] is None
    for bad in ('', 3):
        raw['token_file'] = bad
        path = tmp_path / 'bad.yaml'
        path.write_text(yaml.safe_dump(raw))
        with pytest.raises(ValueError, match='token_file'):
            load_config(path)


def test_every_robot_request_carries_the_token():
    import time
    token = 'robot-token-0123456789abcdef'
    receiver = Receiver(('127.0.0.1', 0), token=token)
    thread = threading.Thread(target=receiver.serve_forever, daemon=True)
    thread.start()
    sender = Sender(State(), config(receiver), controller=Controller(), token=token)
    sender.start()
    try:
        request_id = receiver.enqueue('stop')
        end = time.monotonic() + 3
        while request_id not in receiver.results and time.monotonic() < end:
            time.sleep(0.01)
        assert receiver.results[request_id]['outcome'] == 'accepted'      # next·claim·result 통과
        assert receiver.accepted > 0 and receiver.unauthorized == 0       # 텔레메트리 통과
    finally:
        sender.stop()
    wrong = Sender(State(), config(receiver), controller=Controller(), token='wrong-token-0123456789')
    wrong.start()
    try:
        end = time.monotonic() + 3
        while wrong.status != 'http_401' and time.monotonic() < end:
            time.sleep(0.01)
        assert wrong.status == 'http_401' and receiver.unauthorized > 0
    finally:
        wrong.stop()
        receiver.shutdown()
        receiver.server_close()
        thread.join(2)
