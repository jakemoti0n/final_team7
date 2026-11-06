"""순찰 시작·종료는 서버가 명령만 쌓고 로봇 쪽 Bridge가 실행한다 (docs/CONTROL_API_DRAFT.md §2.5).

서버는 ROS도 subprocess도 쓰지 않는다. 텔레메트리 v3 launcher로 Bridge가 띄운 노드 상태를 본다."""
import uuid

import pytest
import yaml
from fastapi.testclient import TestClient

from server.app import create_app
from server.models import Settings
from server.state import Store
from tools.sender import sample

SESSION = str(uuid.uuid4())
REV = 'a' * 64


class Clock:
    now = 0.
    def __call__(self):
        return self.now


def launcher(state='idle', pid=None, exit_code=None, other=False, commands=('pause', 'resume', 'start', 'stop')):
    return dict(commands=list(commands), state=state, pid=pid, exit_code=exit_code,
                waypoints_revision=None if state == 'idle' else REV,
                log=None if state == 'idle' else '/tmp/limbo-patrol-x.log', other_patrol_running=other)


class Robot:
    def __init__(self, client):
        self.client, self.sequence = client, 0
        self.patrol = dict(state=None, waypoint_index=None, waypoint_count=None, waypoint_name=None,
                           has_resumable_task=None, reason=None, update_count=0,
                           last_received_at=None, age_ms=None)
        self.launcher = launcher()
        self.version = 3

    def send(self, launcher=None, **patrol):
        self.sequence += 1
        if launcher is not None:
            self.launcher = launcher
        if patrol:
            self.patrol.update(dict(waypoint_index=0, waypoint_count=2, waypoint_name='A', has_resumable_task=False,
                                    reason='', last_received_at='2026-10-13T00:00:00.000Z', age_ms=10.), **patrol)
            if self.patrol['state'] is None:   # 발행자가 없으면 Bridge는 내용을 모두 비운다
                self.patrol.update(dict.fromkeys(('waypoint_index', 'waypoint_count', 'waypoint_name',
                                                  'has_resumable_task', 'reason')))
        payload = sample(SESSION, self.sequence)
        payload.update(schema_version=self.version, patrol=dict(self.patrol),
                       pose=dict.fromkeys(('frame_id', 'x', 'y', 'yaw', 'position_std_m', 'last_received_at', 'age_ms')))
        if self.version == 3:
            payload['launcher'] = dict(self.launcher)
        response = self.client.post('/api/v1/telemetry', json=payload)
        assert response.status_code == 200 and response.json()['accepted'], response.text
        return response


@pytest.fixture
def rig(tmp_path):
    (tmp_path / 'map.pgm').write_bytes(b'P5\n10 10\n255\n' + bytes([205]) * 100)
    (tmp_path / 'map.yaml').write_text('image: map.pgm\nresolution: 1\norigin: [0, 0, 0]\n')
    route = tmp_path / 'route.yaml'
    route.write_text(yaml.safe_dump({'waypoints': [
        {'name': 'A', 'type': 'pass', 'x': 2, 'y': 2, 'yaw': 90, 'wait_sec': 0},
        {'name': 'B', 'type': 'stop', 'x': 4, 'y': 4, 'yaw': 0, 'wait_sec': 5}]}))
    clock = Clock()
    settings = Settings(map_yaml=str(tmp_path / 'map.yaml'), waypoints_yaml=str(route))
    store = Store(settings, clock, lambda: '2026-10-13T00:00:00Z')
    with TestClient(create_app(settings, store)) as client:
        yield clock, store, client, Robot(client), route


def take(client):
    got = client.get('/api/v1/commands/next', params=dict(robot_id='LIMBO-01', bridge_session_id=SESSION, wait_s=0))
    assert got.status_code == 200, got.text
    return got.json()


def report(client, command, outcome='accepted', message='started', count=0):
    answered = outcome in ('accepted', 'rejected')
    body = dict(robot_id='LIMBO-01', bridge_session_id=SESSION, request_id=command['request_id'], outcome=outcome,
                message=message, service_latency_ms=3.0 if answered else None, patrol_update_count_at_call=count)
    claim = client.post(f"/api/v1/commands/{command['request_id']}/claim",
                        json=dict(robot_id='LIMBO-01', bridge_session_id=SESSION))
    assert claim.status_code == 200
    assert client.post(f"/api/v1/commands/{command['request_id']}/result", json=body).json() == {'accepted': True}


def stage(store):
    return store.snapshot()['command']['stage']


def code(response):
    return response.json()['error']['code']


def test_start_carries_route_frozen_at_issue_time(rig):
    clock, store, client, robot, route = rig
    robot.send()
    issued = client.post('/api/v1/commands', json={'command': 'start'})
    assert issued.status_code == 202, issued.text
    # 명령을 만든 뒤 파일이 바뀌어도 실린 경로는 그대로
    route.write_text(yaml.safe_dump({'waypoints': [{'name': 'Z', 'type': 'stop', 'x': 1, 'y': 1, 'yaw': 0, 'wait_sec': 0}]}))
    command = take(client)
    assert set(command) == {'request_id', 'command', 'ttl_ms', 'route'}
    assert command['command'] == 'start'
    assert [w['name'] for w in command['route']['waypoints']] == ['A', 'B']
    assert command['route']['waypoints'][0] == {'name': 'A', 'type': 'pass', 'x': 2, 'y': 2, 'yaw': 90, 'wait_sec': 0}
    assert command['route']['bounds'] == {'x_min': 0, 'y_min': 0, 'x_max': 10, 'y_max': 10}
    assert len(command['route']['revision']) == 64


def test_pause_resume_and_stop_have_no_route(rig):
    clock, store, client, robot, route = rig
    robot.send(launcher('running', 77), state='patrolling', update_count=1)
    assert client.post('/api/v1/commands', json={'command': 'stop'}).status_code == 202
    assert set(take(client)) == {'request_id', 'command', 'ttl_ms'}


def test_start_stop_preconditions(rig):
    clock, store, client, robot, route = rig
    assert code(client.post('/api/v1/commands', json={'command': 'start'})) == 'bridge_not_connected'
    robot.version = 2                       # 이전 Bridge: launcher 없음
    robot.send()
    assert store.snapshot()['launcher'] is None
    for name in ('start', 'stop'):
        assert code(client.post('/api/v1/commands', json={'command': name})) == 'bridge_unsupported'
    robot.version = 3
    robot.send(launcher(commands=('pause', 'resume')))
    assert code(client.post('/api/v1/commands', json={'command': 'start'})) == 'bridge_unsupported'
    robot.send(launcher())
    assert code(client.post('/api/v1/commands', json={'command': 'stop'})) == 'patrol_not_running'
    robot.send(launcher(other=True))       # 다른 터미널에서 띄운 노드
    assert code(client.post('/api/v1/commands', json={'command': 'start'})) == 'patrol_already_running'
    robot.send(launcher('running', 5), state='patrolling', update_count=1)
    assert code(client.post('/api/v1/commands', json={'command': 'start'})) == 'patrol_already_running'
    # Bridge가 띄운 노드가 끝났는데 순찰 상태가 아직 남아 있으면 시작 가능 (오래된 상태)
    robot.send(launcher('exited', 5, 0), state='patrolling', update_count=1)
    assert client.post('/api/v1/commands', json={'command': 'start'}).status_code == 202
    assert code(client.post('/api/v1/commands', json={'command': 'stop'})) == 'command_in_progress'


def test_invalid_server_route_is_not_queued(rig):
    clock, store, client, robot, route = rig
    robot.send()
    route.write_text(yaml.safe_dump({'waypoints': [{'name': 'A', 'type': 'pass', 'x': 1, 'y': 1, 'yaw': 0, 'wait_sec': 0}]}))
    response = client.post('/api/v1/commands', json={'command': 'start'})
    assert response.status_code == 409 and code(response) == 'invalid_route'
    assert store.command is None


def test_start_confirmed_by_patrol_state_after_call(rig):
    clock, store, client, robot, route = rig
    robot.send(launcher('exited', 4, 0), state='completed', update_count=3)
    client.post('/api/v1/commands', json={'command': 'start'})
    command = take(client)
    report(client, command, count=3)
    assert stage(store) == 'accepted'
    robot.send(launcher('exited', 4, 0))   # 수락 전 찍힌 이전 실행 보고: 실패로 보지 않음
    assert stage(store) == 'accepted'
    clock.now = 20                           # pause용 5초 확인 제한은 넘었지만 start는 60초
    robot.send(launcher('running', 9), state='waiting_localization', update_count=4)
    assert stage(store) == 'confirmed'


def test_start_fails_when_new_node_exits(rig):
    clock, store, client, robot, route = rig
    robot.send()
    client.post('/api/v1/commands', json={'command': 'start'})
    report(client, take(client))
    robot.send(launcher('running', 9))
    assert stage(store) == 'accepted'
    robot.send(launcher('exited', 9, 1))
    view = store.snapshot()['command']
    assert view['stage'] == 'rejected' and 'code 1' in view['message']


def test_start_bridge_rejection_and_timeouts(rig):
    clock, store, client, robot, route = rig
    robot.send()
    client.post('/api/v1/commands', json={'command': 'start'})
    report(client, take(client), outcome='rejected', message='patrol_already_running')
    view = store.snapshot()['command']
    assert view['stage'] == 'rejected' and view['message'] == 'patrol_already_running'
    client.post('/api/v1/commands', json={'command': 'start'})
    report(client, take(client))
    clock.now = 59
    robot.send()
    assert stage(store) == 'accepted'
    clock.now = 61
    robot.send()
    assert stage(store) == 'unconfirmed'


def test_stop_confirmed_by_exit_or_missing_patrol_state(rig):
    clock, store, client, robot, route = rig
    robot.send(launcher('running', 9), state='paused', update_count=5)
    client.post('/api/v1/commands', json={'command': 'stop'})
    report(client, take(client), message='SIGTERM sent', count=5)
    clock.now = 10
    robot.send()
    assert stage(store) == 'accepted'      # 아직 종료 중 (Nav2 목표 취소 대기)
    robot.send(launcher('exited', 9, 0))
    assert stage(store) == 'confirmed'

    robot.send(launcher('running', 10), state='patrolling', update_count=6)
    client.post('/api/v1/commands', json={'command': 'stop'})
    report(client, take(client), count=6)
    robot.send(state=None)                 # 발행자 사라짐 → Bridge가 상태를 비움
    assert stage(store) == 'confirmed'


def test_stop_confirm_timeout_is_separate(rig):
    clock, store, client, robot, route = rig
    robot.send(launcher('running', 9), state='patrolling', update_count=1)
    client.post('/api/v1/commands', json={'command': 'stop'})
    report(client, take(client), count=1)
    clock.now = 29
    robot.send()
    assert stage(store) == 'accepted'
    clock.now = 31
    robot.send()
    assert stage(store) == 'unconfirmed'


def test_waypoint_edit_lock_follows_bridge_report(rig):
    clock, store, client, robot, route = rig
    revision = client.get('/api/v1/waypoints').json()['revision']
    change = {'revision': revision, 'action': 'rename', 'name': 'A', 'new_name': 'A2'}
    robot.send(launcher('running', 9))
    assert code(client.put('/api/v1/waypoints', json=change)) == 'patrol_active'
    robot.send(launcher(other=True))
    assert code(client.put('/api/v1/waypoints', json=change)) == 'patrol_active'
    robot.send(launcher('exited', 9, 0), state='patrolling', update_count=2)
    assert client.put('/api/v1/waypoints', json=change).status_code == 200
    revision = client.get('/api/v1/waypoints').json()['revision']
    client.post('/api/v1/commands', json={'command': 'start'})   # 시작 처리 중에도 잠금
    response = client.put('/api/v1/waypoints', json={**change, 'revision': revision, 'name': 'A2', 'new_name': 'A3'})
    assert code(response) == 'patrol_active'


def test_v3_telemetry_contract(rig):
    clock, store, client, robot, route = rig
    payload = sample(SESSION, 1)
    payload.update(schema_version=3, patrol=dict(robot.patrol),
                   pose=dict.fromkeys(('frame_id', 'x', 'y', 'yaw', 'position_std_m', 'last_received_at', 'age_ms')))
    assert client.post('/api/v1/telemetry', json=payload).status_code == 422       # launcher 없음
    for bad in (launcher('idle', 3), launcher('running', None), {**launcher('running', 3), 'exit_code': 0},
                {**launcher(), 'commands': ['start', 'start']}, {**launcher(), 'extra': 1}):
        assert client.post('/api/v1/telemetry', json={**payload, 'launcher': bad}).status_code == 422
    v2 = {**payload, 'schema_version': 2, 'launcher': launcher()}
    assert client.post('/api/v1/telemetry', json=v2).status_code == 422             # v2에 launcher 금지
    assert client.post('/api/v1/telemetry', json={**payload, 'launcher': launcher()}).json()['accepted']
    assert store.snapshot()['launcher']['state'] == 'idle'


def test_old_patrol_endpoints_removed(rig):
    clock, store, client, robot, route = rig
    for method, path in (('post', '/api/v1/patrol/start'), ('post', '/api/v1/patrol/stop'), ('get', '/api/v1/patrol/launch')):
        assert getattr(client, method)(path).status_code in (404, 405)
