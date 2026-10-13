"""텔레메트리 v2(순찰 상태·위치), 관제 명령, 지도 API 시험. 계약: docs/CONTROL_API_DRAFT.md"""
import struct
import uuid
import zlib

from fastapi.testclient import TestClient
import pytest

from server.app import create_app
from server.models import Settings
from server.state import Store
from tools.sender import sample

SESSION = str(uuid.uuid4())


class Clock:
    now = 0.
    def __call__(self):
        return self.now


class Robot:
    """같은 세션으로 순번을 올려 가며 v2 텔레메트리를 보낸다."""
    def __init__(self, client, session=SESSION):
        self.client, self.session, self.sequence = client, session, 0
        self.patrol = dict(state='patrolling', waypoint_index=0, waypoint_count=10, waypoint_name='A',
                           has_resumable_task=True, reason='navigating', update_count=3,
                           last_received_at='2026-10-13T00:00:00.000Z', age_ms=100.)
        self.speed = 0.3

    def send(self, **patrol):
        self.sequence += 1
        self.patrol.update(patrol)
        payload = sample(self.session, self.sequence, speed=self.speed)
        payload.update(schema_version=2, patrol=dict(self.patrol),
                       pose=dict(frame_id='map', x=1.0, y=2.0, yaw=0.5, position_std_m=0.05,
                                 last_received_at='2026-10-13T00:00:00.000Z', age_ms=50.))
        return self.client.post('/api/v1/telemetry', json=payload)


@pytest.fixture
def rig():
    clock = Clock()
    store = Store(Settings(), clock, lambda: "2026-10-13T00:00:00Z")
    with TestClient(create_app(store.settings, store)) as client:
        yield clock, store, client, Robot(client)


def result(request_id, outcome='accepted', message='pause accepted', count=3, session=SESSION):
    answered = outcome in ('accepted', 'rejected')
    return dict(robot_id='LIMBO-01', bridge_session_id=session, request_id=request_id, outcome=outcome,
                message=message, service_latency_ms=12.0 if answered else None,
                patrol_update_count_at_call=count)


def deliver(client, command='pause'):
    issued = client.post('/api/v1/commands', json={'command': command})
    assert issued.status_code == 202, issued.text
    got = client.get('/api/v1/commands/next', params=dict(robot_id='LIMBO-01', bridge_session_id=SESSION, wait_s=0))
    assert got.status_code == 200, got.text
    return got.json()


def stage(store):
    return store.snapshot()['command']['stage']


# ---- 텔레메트리 v2 ----

def test_v2_patrol_and_pose_in_snapshot(rig):
    clock, store, client, robot = rig
    assert robot.send().json()['accepted']
    clock.now = 1
    state = store.snapshot()
    assert state['patrol']['state'] == 'patrolling' and state['patrol']['age_s'] == pytest.approx(1.1)
    assert state['pose']['x'] == 1.0 and state['pose']['stale'] is False
    clock.now = 3
    assert store.snapshot()['pose']['stale'] is True        # 3초 넘으면 위치 확인 불가


def test_v1_still_accepted_and_v2_rules(rig):
    clock, store, client, robot = rig
    assert client.post('/api/v1/telemetry', json=sample(SESSION, 1)).json()['accepted']
    assert store.snapshot()['patrol'] is None and store.snapshot()['pose'] is None
    good = sample(SESSION, 2)
    good.update(schema_version=2, patrol=dict.fromkeys(robot.patrol, None) | {'update_count': 0},
                pose=dict.fromkeys(('frame_id', 'x', 'y', 'yaw', 'position_std_m', 'last_received_at', 'age_ms')))
    assert client.post('/api/v1/telemetry', json=good).status_code == 200
    for bad in (good | {'schema_version': 1},                              # v1에 v2 필드
                {k: v for k, v in good.items() if k != 'pose'},            # v2에 pose 없음
                good | {'pose': good['pose'] | {'x': 1.0}},                # 위치 일부만
                good | {'patrol': good['patrol'] | {'state': 'paused'}},   # 미수신인데 상태
                good | {'patrol': robot.patrol | {'state': 'dancing'}}):
        assert client.post('/api/v1/telemetry', json=bad | {'sequence': 9}).status_code == 422


# ---- 명령 접수·전달 ----

def test_issue_requires_connection_and_one_at_a_time(rig):
    clock, store, client, robot = rig
    assert client.post('/api/v1/commands', json={'command': 'pause'}).json()['error']['code'] == 'bridge_not_connected'
    robot.send()
    assert client.post('/api/v1/commands', json={'command': 'restart'}).status_code == 422
    assert client.post('/api/v1/commands', json={'command': 'pause', 'x': 1}).status_code == 422
    first = client.post('/api/v1/commands', json={'command': 'pause'})
    assert first.status_code == 202 and first.json()['stage'] == 'queued'
    second = client.post('/api/v1/commands', json={'command': 'resume'})
    assert second.status_code == 409 and second.json()['error']['code'] == 'command_in_progress'


def test_next_delivers_once_to_current_session(rig):
    clock, store, client, robot = rig
    robot.send()
    params = dict(robot_id='LIMBO-01', bridge_session_id=SESSION, wait_s=0)
    assert client.get('/api/v1/commands/next', params=params).status_code == 204
    assert client.get('/api/v1/commands/next', params=params | {'robot_id': 'X'}).status_code == 409
    assert client.get('/api/v1/commands/next', params=params | {'bridge_session_id': 'x'}).status_code == 422
    client.post('/api/v1/commands', json={'command': 'pause'})
    other = str(uuid.uuid4())
    assert client.get('/api/v1/commands/next', params=params | {'bridge_session_id': other}).status_code == 204
    clock.now = 1.5
    got = client.get('/api/v1/commands/next', params=params).json()
    assert got['command'] == 'pause' and set(got) == {'request_id', 'command', 'ttl_ms'}
    assert got['ttl_ms'] == pytest.approx(3500)             # 발급 후 5초 기준 남은 시간
    assert stage(store) == 'delivered'
    assert client.get('/api/v1/commands/next', params=params).status_code == 204   # 다시 안 줌


# ---- 판정 ----

def test_pause_confirmed_only_after_newer_paused_state_and_stop(rig):
    clock, store, client, robot = rig
    robot.send()
    command = deliver(client)
    assert client.post(f"/api/v1/commands/{command['request_id']}/result",
                       json=result(command['request_id'], count=3)).json() == {'accepted': True}
    assert stage(store) == 'accepted'
    robot.send(state='paused')                               # 횟수 3 그대로 → 명령 이전 상태
    assert stage(store) == 'accepted'
    robot.send(state='paused', update_count=4)               # 새 상태지만 아직 움직임
    assert stage(store) == 'accepted'
    robot.speed = 0.0
    robot.send(state='paused', update_count=4)
    state = store.snapshot()
    assert state['command']['stage'] == 'confirmed'
    assert state['alerts'][0]['message'] == '정지 상태 확인됨' and state['alerts'][0]['kind'] == 'control'


def test_resume_confirmed_by_state_not_speed(rig):
    clock, store, client, robot = rig
    robot.speed = 0.0
    robot.send(state='paused')
    command = deliver(client, 'resume')
    client.post(f"/api/v1/commands/{command['request_id']}/result",
                json=result(command['request_id'], message='resume accepted'))
    robot.send(state='patrolling', update_count=4)          # 아직 속도 0이어도 됨
    assert stage(store) == 'confirmed'


@pytest.mark.parametrize('outcome,expected,text', [
    ('rejected', 'rejected', '정지 요청 실패: already paused'),
    ('service_unavailable', 'service_unavailable', '정지 요청 실패: 순찰 노드가 응답할 수 없음'),
    ('no_response', 'no_response', '정지 여부 확인 불가: 로봇 응답 없음'),
    ('expired', 'expired', '정지 여부 확인 불가: 요청이 로봇에 전달되지 않음'),
])
def test_bridge_reported_failures(rig, outcome, expected, text):
    clock, store, client, robot = rig
    robot.send()
    command = deliver(client)
    client.post(f"/api/v1/commands/{command['request_id']}/result",
                json=result(command['request_id'], outcome, 'already paused' if outcome == 'rejected' else ''))
    state = store.snapshot()
    assert state['command']['stage'] == expected and state['alerts'][0]['message'] == text


def test_timeouts_and_late_result_does_not_change_outcome(rig):
    clock, store, client, robot = rig
    robot.send()
    command = deliver(client)
    clock.now = 4.999
    robot.send()
    assert stage(store) == 'delivered'
    clock.now = 5.0
    robot.send()
    assert stage(store) == 'no_response'                    # 결과 5초 안에 안 옴
    late = client.post(f"/api/v1/commands/{command['request_id']}/result", json=result(command['request_id']))
    assert late.json() == {'accepted': False, 'reason': 'command_closed'}
    assert stage(store) == 'no_response'
    # 응답 후 상태 확인이 5초 안에 없으면 unconfirmed
    command = deliver(client)
    client.post(f"/api/v1/commands/{command['request_id']}/result", json=result(command['request_id']))
    clock.now = 9.9
    robot.send()
    assert stage(store) == 'accepted'
    clock.now = 10.0
    robot.send()
    assert stage(store) == 'unconfirmed'


def test_queued_command_expires_if_not_fetched(rig):
    clock, store, client, robot = rig
    robot.send()
    client.post('/api/v1/commands', json={'command': 'pause'})
    clock.now = 2.5
    robot.send()
    clock.now = 5.0
    robot.send()
    params = dict(robot_id='LIMBO-01', bridge_session_id=SESSION, wait_s=0)
    assert client.get('/api/v1/commands/next', params=params).status_code == 204
    assert stage(store) == 'expired'


def test_connection_lost_on_new_session_or_disconnect(rig):
    clock, store, client, robot = rig
    robot.send()
    deliver(client)
    Robot(client, str(uuid.uuid4())).send()                  # Bridge 재시작
    assert stage(store) == 'connection_lost'
    clock2 = Clock()
    store2 = Store(Settings(), clock2, lambda: "2026-10-13T00:00:00Z")
    with TestClient(create_app(store2.settings, store2)) as client2:
        Robot(client2).send()
        deliver(client2)
        clock2.now = 10
        assert store2.snapshot()['command']['stage'] == 'connection_lost'


def test_result_validation(rig):
    clock, store, client, robot = rig
    robot.send()
    command = deliver(client)
    url = f"/api/v1/commands/{command['request_id']}/result"
    good = result(command['request_id'])
    assert client.post(url, json=good | {'service_latency_ms': None}).status_code == 422
    assert client.post(url, json=good | {'extra': 1}).status_code == 422
    assert client.post(f"/api/v1/commands/{uuid.uuid4()}/result", json=good).status_code == 422
    assert client.post(url, json=good | {'robot_id': 'X'}).status_code == 409
    assert client.post(url, json=good | {'bridge_session_id': str(uuid.uuid4())}).json()['reason'] == 'command_closed'
    assert client.post(url, content=b'{}', headers={'content-type': 'text/plain'}).status_code == 415


# ---- 지도 ----

def test_map_api(tmp_path):
    pgm = tmp_path / 'm.pgm'
    pgm.write_bytes(b'P5\n# test\n3 2\n255\n' + bytes([0, 128, 255, 205, 205, 0]))
    (tmp_path / 'm.yaml').write_text('image: m.pgm\nresolution: 0.05\norigin: [-1.0, -2.0, 0.0]\n')
    (tmp_path / 'w.yaml').write_text('waypoints:\n  - {name: A, type: pass, x: 1, y: 2, yaw: 0, wait_sec: 0}\n')
    store = Store(Settings(map_yaml=str(tmp_path / 'm.yaml'), waypoints_yaml=str(tmp_path / 'w.yaml')))
    with TestClient(create_app(store.settings, store)) as client:
        meta = client.get('/api/v1/map').json()
        assert (meta['width'], meta['height'], meta['resolution'], meta['origin']) == (3, 2, 0.05, [-1.0, -2.0, 0.0])
        assert meta['waypoints'] == [{'name': 'A', 'type': 'pass', 'x': 1.0, 'y': 2.0}]
        png = client.get('/api/v1/map.png')
        assert png.headers['content-type'] == 'image/png' and png.content[:8] == b'\x89PNG\r\n\x1a\n'
        width, height = struct.unpack('>II', png.content[16:24])
        idat = png.content[png.content.index(b'IDAT') + 4:png.content.index(b'IEND') - 8]
        assert (width, height) == (3, 2) and zlib.decompress(idat) == b'\x00' + bytes([0, 128, 255]) + b'\x00' + bytes([205, 205, 0])
        assert client.get('/api/v1/state').json()['map_available'] is True
    store = Store(Settings())
    with TestClient(create_app(store.settings, store)) as client:
        assert client.get('/api/v1/map').status_code == 404 and client.get('/api/v1/map.png').status_code == 404
        assert client.get('/api/v1/state').json()['map_available'] is False


def test_real_project_map_loads():
    store = Store(Settings(map_yaml='limbo/src/limbo_navigation/maps/human_test_map.yaml',
                           waypoints_yaml='limbo/src/limbo_patrol/config/test_waypoints.yaml'))
    with TestClient(create_app(store.settings, store)) as client:
        meta = client.get('/api/v1/map').json()
        assert meta['width'] > 0 and len(meta['waypoints']) == 10
