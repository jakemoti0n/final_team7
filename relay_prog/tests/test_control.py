"""텔레메트리 v2(순찰 상태·위치)와 관제 명령 작업 시험. 계약: docs/CONTROL_API_DRAFT.md"""
import json
import math
import threading
import time
from pathlib import Path

import pytest
import yaml
from limbo_telemetry_bridge.config import load_config
from limbo_telemetry_bridge.state import State
from limbo_telemetry_bridge.transport import Sender, command_from
from receiver import Receiver, validate

DEFAULT = Path(__file__).resolve().parents[1]/'src/limbo_telemetry_bridge/config/bridge.yaml'


class Clock:
    now = 0.0
    def mono(self):
        return self.now
    def utc(self):
        return '2026-10-13T00:00:00.000Z'


# ---- 텔레메트리 v2 ----

def test_v2_patrol_and_pose_snapshot():
    clock = Clock()
    state = State(monotonic=clock.mono, utc=clock.utc)
    first = state.snapshot()
    validate(first)
    assert first['schema_version'] == 2
    assert first['patrol']['update_count'] == 0
    assert all(v is None for k, v in first['patrol'].items() if k != 'update_count')
    assert all(v is None for v in first['pose'].values())

    state.receive_patrol('paused', 2, 10, 'C', True, 'x' * 500)
    state.receive_pose('map', 1.5, -2.0, 0.5, 0.12)
    clock.now = 2
    snapshot = state.snapshot()
    validate(snapshot)
    patrol, pose = snapshot['patrol'], snapshot['pose']
    assert patrol['state'] == 'paused' and patrol['waypoint_name'] == 'C' and patrol['update_count'] == 1
    assert len(patrol['reason']) == 200 and patrol['age_ms'] == 2000
    assert (pose['x'], pose['y'], pose['yaw'], pose['position_std_m']) == (1.5, -2.0, 0.5, 0.12)
    assert pose['age_ms'] == 2000
    assert len(json.dumps(snapshot).encode()) < 8192

    # 무효 위치는 전부 null (v1 motion과 같은 규칙)
    for bad in (math.nan, math.inf):
        state.receive_pose('map', bad, 0., 0., 0.1)
        assert all(v is None for v in state.snapshot()['pose'].values())
    state.receive_pose('map', 0., 0., 0., -1.)
    assert state.snapshot()['pose']['x'] is None

    # 모르는 상태도 수신 횟수는 센다 (명령 이후 판정은 횟수로 함)
    state.receive_patrol('dancing', 0, 0, '', False, '')
    snapshot = state.snapshot()
    validate(snapshot)
    assert snapshot['patrol']['update_count'] == 2 and snapshot['patrol']['state'] is None
    assert state.patrol_update_count() == 2


def test_v1_payload_still_valid_and_v2_rules_enforced():
    v2 = State().snapshot()
    v1 = {k: v for k, v in v2.items() if k not in ('patrol', 'pose')}
    v1['schema_version'] = 1
    validate(v1)
    for mutate in (lambda p: p.pop('patrol'),
                   lambda p: p['patrol'].update(state='paused'),          # 미수신인데 값
                   lambda p: p['pose'].update(x=1.0),                     # 일부만 채움
                   lambda p: p.update(schema_version=3)):
        payload = json.loads(json.dumps(v2))
        mutate(payload)
        with pytest.raises(ValueError):
            validate(payload)
    with pytest.raises(ValueError):
        validate(v1 | {'patrol': v2['patrol'], 'pose': v2['pose']})       # v1에 v2 필드


@pytest.mark.parametrize('key,value', [
    ('pause_service', 'patrol/pause'), ('command_wait_s', 0), ('command_wait_s', 31),
    ('service_timeout_s', math.nan), ('service_timeout_s', 11), ('extra', 1),
    ('map_frame', '/map'), ('base_frame', ''), ('base_frame', 3)])
def test_invalid_control_configuration(tmp_path, key, value):
    config = yaml.safe_load(DEFAULT.read_text())
    config['control'][key] = value
    path = tmp_path/'bad.yaml'
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError):
        load_config(path)


def test_command_response_validation():
    good = dict(request_id='4c829302-34cd-48e6-91d1-267230398eb7', command='pause', ttl_ms=4800)
    assert command_from(json.dumps(good))['command'] == 'pause'
    for bad in ({**good, 'command': 'restart'}, {**good, 'ttl_ms': -1}, {**good, 'request_id': 'x'},
                {**good, 'extra': 1}, {**good, 'ttl_ms': True}):
        with pytest.raises((ValueError, TypeError)):
            command_from(json.dumps(bad))


# ---- 관제 명령 작업 ----

class Future:
    def __init__(self, response=None):
        self.response, self.cancelled = response, False
    def done(self):
        return self.response is not None
    def result(self):
        return self.response
    def cancel(self):
        self.cancelled = True


class Reply:
    def __init__(self, success, message):
        self.success, self.message = success, message


class Controller:
    """mode: accept | reject | missing | hang"""
    def __init__(self, mode='accept'):
        self.mode, self.calls = mode, []
    def call(self, command):
        self.calls.append(command)
        if self.mode == 'missing':
            return None
        if self.mode == 'hang':
            return Future()
        return Future(Reply(self.mode == 'accept', f'{command} {"accepted" if self.mode == "accept" else "already paused"}'))


@pytest.fixture
def server():
    receiver = Receiver(('127.0.0.1', 0))
    thread = threading.Thread(target=receiver.serve_forever, daemon=True)
    thread.start()
    yield receiver
    receiver.shutdown()
    receiver.server_close()
    thread.join(2)


def config(server, wait=0.3):
    return dict(server_url=f'http://127.0.0.1:{server.server_port}', request_timeout_s=0.5,
                send_interval_s=0.1,
                control=dict(patrol_state_topic='/patrol/state', pose_topic='/amcl_pose',
                             pause_service='/patrol/pause', resume_service='/patrol/resume',
                             command_wait_s=wait, service_timeout_s=0.2))


def wait_until(cond, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def run_command(server, controller, command='pause', ttl_s=5.0, state=None):
    state = state or State()
    sender = Sender(state, config(server), controller=controller)
    sender.start()
    try:
        assert wait_until(lambda: sender.command_status == 'connected')
        request_id = server.enqueue(command, ttl_s)
        assert wait_until(lambda: request_id in server.results)
        time.sleep(0.5)  # 다시 내주거나 다시 부르지 않는지 볼 시간
        return server.results[request_id], sender
    finally:
        sender.stop()


@pytest.mark.parametrize('mode,outcome,message', [
    ('accept', 'accepted', 'pause accepted'),
    ('reject', 'rejected', 'pause already paused'),
    ('missing', 'service_unavailable', 'patrol service not available'),
    ('hang', 'no_response', 'no service response'),
])
def test_command_outcomes_reported_once(server, mode, outcome, message):
    state = State()
    for _ in range(3):
        state.receive_patrol('patrolling', 0, 10, 'A', True, 'navigating')
    controller = Controller(mode)
    result, _ = run_command(server, controller, state=state)
    assert result['outcome'] == outcome and result['message'] == message
    assert result['patrol_update_count_at_call'] == 3
    assert result['bridge_session_id'] == state.session_id
    assert (result['service_latency_ms'] is not None) == (mode in ('accept', 'reject'))
    assert controller.calls == ['pause']          # 서비스는 한 번만
    assert len(server.delivered) == 1             # 서버도 한 번만 내줌


def test_expired_command_is_not_called(server):
    controller = Controller('accept')
    result, _ = run_command(server, controller, ttl_s=0.0)
    assert result['outcome'] == 'expired' and controller.calls == []


@pytest.mark.parametrize('mode,message', [('refuse', 'claim refused'), ('slow', 'claim TimeoutError')])
def test_service_not_called_unless_server_claims_in_time(server, mode, message):
    """서버가 유효하다고 1초 안에 답하지 않으면 부르지 않는다 (늦게 읽은 명령이 '응답 없음' 뒤에 실행되지 않게)"""
    server.claim_mode = mode
    controller = Controller('accept')
    result, _ = run_command(server, controller)
    assert result['outcome'] == 'expired' and result['message'] == message
    assert controller.calls == []


def test_claim_happens_once_before_the_call(server):
    controller = Controller('accept')
    result, _ = run_command(server, controller)
    assert result['outcome'] == 'accepted' and server.claimed == {result['request_id']}


def test_patrol_unknown_while_publisher_is_gone():
    state = State()
    state.receive_patrol('patrolling', 2, 10, 'C', True, 'navigating')
    state.patrol_publisher(False)
    patrol = state.snapshot()['patrol']
    assert patrol['state'] is None and patrol['has_resumable_task'] is None
    assert patrol['update_count'] == 1 and patrol['last_received_at'] is not None   # 받은 기록은 유지
    validate(state.snapshot())                                                         # 계약 안 ("받았지만 알 수 없음")
    state.patrol_publisher(True)
    assert state.snapshot()['patrol']['state'] == 'patrolling'


def test_telemetry_keeps_flowing_while_service_hangs(server):
    controller = Controller('hang')
    state = State()
    sender = Sender(state, dict(config(server), control={**config(server)['control'], 'service_timeout_s': 1.5}),
                    controller=controller)
    sender.start()
    try:
        assert wait_until(lambda: sender.command_status == 'connected')
        server.enqueue('pause')
        assert wait_until(lambda: controller.calls)
        before = server.accepted
        time.sleep(1.0)                           # 서비스를 기다리는 동안
        assert server.accepted - before >= 5      # 텔레메트리 0.1초 주기는 계속
        assert server.latest['schema_version'] == 2
    finally:
        sender.stop()


def test_stop_during_long_poll_is_bounded(server):
    sender = Sender(State(), config(server, wait=10), controller=Controller())
    sender.start()
    assert wait_until(lambda: sender.command_status == 'connected' or server.accepted > 0)
    time.sleep(0.3)                               # long poll 대기 중
    started = time.monotonic()
    sender.stop()
    assert time.monotonic() - started < 0.5
    assert not sender.thread.is_alive() and sender.error is None


def test_fetch_failure_backs_off_and_recovers(server):
    server.command_mode = 'error'
    sender = Sender(State(), config(server), controller=Controller())
    sender.start()
    try:
        assert wait_until(lambda: sender.command_status == 'http_503')
        server.command_mode = 'ok'
        assert wait_until(lambda: sender.command_status == 'connected', timeout=4)
        request_id = server.enqueue('resume')
        assert wait_until(lambda: request_id in server.results)
        assert server.results[request_id]['outcome'] == 'accepted'
    finally:
        sender.stop()


def test_late_or_duplicate_result_is_closed(server):
    controller = Controller('accept')
    result, sender = run_command(server, controller)
    url = config(server)['server_url'] + f"/api/v1/commands/{result['request_id']}/result"
    import urllib.request
    request = urllib.request.Request(url, data=json.dumps(result).encode(),
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=1) as response:
        assert json.loads(response.read()) == {'accepted': False, 'reason': 'command_closed'}


def test_pose_from_tf_needs_amcl_uncertainty_and_fresh_transform():
    """위치는 TF로 읽어 멈춰 있어도 계속 나간다. AMCL 불확실성 전·오래된 TF·TF 없음이면 보내지 않는다"""
    from types import SimpleNamespace
    from builtin_interfaces.msg import Time as TimeMsg
    from geometry_msgs.msg import TransformStamped
    from rclpy.time import Time
    from tf2_ros import LookupException
    from limbo_telemetry_bridge.node import BridgeNode

    transform = TransformStamped()
    transform.header.stamp = TimeMsg(sec=100)
    transform.transform.translation.x, transform.transform.translation.y = 1.5, -2.0
    transform.transform.rotation.z, transform.transform.rotation.w = math.sin(0.25), math.cos(0.25)
    lookups = []

    def lookup(target, source, at):
        lookups.append((target, source))
        if fake.missing:
            raise LookupException('no transform')
        return transform
    clock = SimpleNamespace(now=lambda: Time(seconds=fake.now))
    fake = SimpleNamespace(state=State('LIMBO-01', 'ros_sim'), map_frame='map', base_frame='base_footprint',
                           position_std=None, tf_buffer=SimpleNamespace(lookup_transform=lookup),
                           get_clock=lambda: clock, now=100.5, missing=False)
    read = lambda: BridgeNode._read_pose(fake)
    read()
    assert lookups == [] and fake.state.pose is None          # AMCL이 위치를 잡기 전
    fake.position_std = 0.03
    read()
    frame, x, y, yaw, std = fake.state.pose[:5]
    assert (frame, x, y, std) == ('map', 1.5, -2.0, 0.03) and yaw == pytest.approx(0.5)
    assert lookups == [('map', 'base_footprint')]
    fake.state.pose, fake.now = None, 101.2                   # TF가 1.2초 묵음 (오도메트리 끊김)
    read()
    assert fake.state.pose is None
    fake.now, fake.missing = 100.5, True                      # TF 없음
    read()
    assert fake.state.pose is None
