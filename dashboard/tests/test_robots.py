"""여러 로봇: 로봇마다 상태·명령·지도·waypoint 파일이 따로다. 처음 보는 robot_id는 자동 등록된다."""
import uuid

import pytest
import yaml
from fastapi.testclient import TestClient

from server.app import create_app
from server.models import Settings
from server.state import Store
from tools.sender import sample
from tests.test_patrol_commands import launcher


class Clock:
    now = 0.
    def __call__(self):
        return self.now


def write_map(tmp_path):
    (tmp_path / 'map.pgm').write_bytes(b'P5\n10 10\n255\n' + bytes([205]) * 100)
    (tmp_path / 'map.yaml').write_text('image: map.pgm\nresolution: 1\norigin: [0, 0, 0]\n')
    return str(tmp_path / 'map.yaml')


def write_route(path, first='A'):
    path.write_text(yaml.safe_dump({'waypoints': [
        {'name': first, 'type': 'pass', 'x': 2, 'y': 2, 'yaw': 90, 'wait_sec': 0},
        {'name': 'B', 'type': 'stop', 'x': 4, 'y': 4, 'yaw': 0, 'wait_sec': 5}]}))
    return str(path)


def telemetry(robot_id, session, sequence=1, patrol_state=None, launch='idle', at=None):
    payload = sample(session, sequence)
    patrol = dict(state=None, waypoint_index=None, waypoint_count=None, waypoint_name=None,
                  has_resumable_task=None, reason=None, update_count=0, last_received_at=None, age_ms=None)
    if patrol_state:
        patrol.update(state=patrol_state, waypoint_index=0, waypoint_count=2, waypoint_name='A',
                      has_resumable_task=False, reason='', update_count=sequence,
                      last_received_at='2026-10-13T00:00:00.000Z', age_ms=10.)
    payload.update(robot_id=robot_id, schema_version=3, patrol=patrol,
                   pose=dict(frame_id='map', x=at[0], y=at[1], yaw=0.5, position_std_m=.1,
                             last_received_at='2026-10-13T00:00:00.000Z', age_ms=10.) if at else
                   dict.fromkeys(('frame_id', 'x', 'y', 'yaw', 'position_std_m', 'last_received_at', 'age_ms')),
                   launcher=launcher(launch, pid=None if launch == 'idle' else 42))
    return payload


@pytest.fixture
def rig(tmp_path):
    clock = Clock()
    settings = Settings(map_yaml=write_map(tmp_path), waypoints_yaml=write_route(tmp_path / 'shared.yaml'),
                        robots={'LIMBO-02': {'waypoints_yaml': write_route(tmp_path / 'two.yaml', 'C')}},
                        max_robots=3)
    store = Store(settings, clock, lambda: '2026-10-13T00:00:00Z')
    with TestClient(create_app(settings, store)) as client:
        yield clock, client, tmp_path


def post(client, payload):
    response = client.post('/api/v1/telemetry', json=payload)
    assert response.status_code == 200 and response.json()['accepted'], response.text
    return response


def test_configured_robots_listed_before_connecting(rig):
    _, client, _ = rig
    body = client.get('/api/v1/robots').json()
    assert body['default'] == 'LIMBO-01'
    assert [(r['robot_id'], r['status']) for r in body['robots']] == [('LIMBO-01', 'checking'), ('LIMBO-02', 'checking')]
    assert client.get('/api/v1/state').json()['robot_id'] == 'LIMBO-01'
    assert client.get('/api/v1/state', params={'robot_id': 'LIMBO-02'}).json()['robot_id'] == 'LIMBO-02'
    assert client.get('/api/v1/state', params={'robot_id': 'NOPE'}).status_code == 404


def test_each_robot_has_its_own_state_and_unknown_robot_registers(rig):
    _, client, _ = rig
    one, three = str(uuid.uuid4()), str(uuid.uuid4())
    post(client, telemetry('LIMBO-01', one, patrol_state='patrolling'))
    post(client, telemetry('LIMBO-03', three, patrol_state='paused'))   # 설정에 없는 로봇: 자동 등록
    a = client.get('/api/v1/state', params={'robot_id': 'LIMBO-01'}).json()
    c = client.get('/api/v1/state', params={'robot_id': 'LIMBO-03'}).json()
    assert (a['bridge']['session_id'], a['patrol']['state']) == (one, 'patrolling')
    assert (c['bridge']['session_id'], c['patrol']['state']) == (three, 'paused')
    assert client.get('/api/v1/state', params={'robot_id': 'LIMBO-02'}).json()['bridge']['session_id'] is None
    statuses = {r['robot_id']: r['status'] for r in a['robots']}
    assert statuses == {'LIMBO-01': 'connected', 'LIMBO-02': 'checking', 'LIMBO-03': 'connected'}
    # 같은 세션이 다른 로봇 이름으로 와도 서로 섞이지 않는다
    post(client, telemetry('LIMBO-02', one))
    assert client.get('/api/v1/state').json()['bridge']['sequence'] == 1


def test_auto_registration_limit(rig):
    _, client, _ = rig
    post(client, telemetry('LIMBO-03', str(uuid.uuid4())))
    response = client.post('/api/v1/telemetry', json=telemetry('LIMBO-04', str(uuid.uuid4())))
    assert response.status_code == 429 and response.json()['error']['code'] == 'too_many_robots'
    assert len(client.get('/api/v1/robots').json()['robots']) == 3


def test_commands_go_only_to_the_chosen_robot(rig):
    _, client, _ = rig
    one, two = str(uuid.uuid4()), str(uuid.uuid4())
    post(client, telemetry('LIMBO-01', one, patrol_state='patrolling'))
    post(client, telemetry('LIMBO-02', two, patrol_state='patrolling'))
    issued = client.post('/api/v1/commands', json={'command': 'pause', 'robot_id': 'LIMBO-02'})
    assert issued.status_code == 202
    nothing = client.get('/api/v1/commands/next', params=dict(robot_id='LIMBO-01', bridge_session_id=one, wait_s=0))
    assert nothing.status_code == 204
    # 다른 로봇 이름으로 claim하면 거절 (그 로봇에는 이 명령이 없다)
    got = client.get('/api/v1/commands/next', params=dict(robot_id='LIMBO-02', bridge_session_id=two, wait_s=0))
    assert got.status_code == 200
    request_id = got.json()['request_id']
    wrong = client.post(f'/api/v1/commands/{request_id}/claim', json=dict(robot_id='LIMBO-01', bridge_session_id=one))
    assert wrong.status_code == 409
    right = client.post(f'/api/v1/commands/{request_id}/claim', json=dict(robot_id='LIMBO-02', bridge_session_id=two))
    assert right.status_code == 200
    assert client.get('/api/v1/state').json()['command'] is None
    assert client.get('/api/v1/state', params={'robot_id': 'LIMBO-02'}).json()['command']['stage'] == 'delivered'
    # robot_id 없는 요청은 기본 로봇, 모르는 로봇은 404
    assert client.post('/api/v1/commands', json={'command': 'pause'}).status_code == 202
    assert client.post('/api/v1/commands', json={'command': 'pause', 'robot_id': 'NOPE'}).status_code == 404


def test_start_freezes_each_robots_own_route(rig):
    _, client, _ = rig
    two = str(uuid.uuid4())
    post(client, telemetry('LIMBO-02', two))
    assert client.post('/api/v1/commands', json={'command': 'start', 'robot_id': 'LIMBO-02'}).status_code == 202
    got = client.get('/api/v1/commands/next', params=dict(robot_id='LIMBO-02', bridge_session_id=two, wait_s=0)).json()
    assert [w['name'] for w in got['route']['waypoints']] == ['C', 'B']


def test_waypoints_and_map_per_robot(rig):
    _, client, tmp_path = rig
    assert [w['name'] for w in client.get('/api/v1/waypoints').json()['waypoints']] == ['A', 'B']
    assert [w['name'] for w in client.get('/api/v1/waypoints', params={'robot_id': 'LIMBO-02'}).json()['waypoints']] == ['C', 'B']
    info = client.get('/api/v1/map', params={'robot_id': 'LIMBO-02'}).json()
    assert info['image'] == '/api/v1/map.png?robot_id=LIMBO-02'
    assert [w['name'] for w in info['waypoints']] == ['C', 'B']
    assert client.get(info['image']).headers['content-type'] == 'image/png'


def test_waypoint_lock_follows_robots_sharing_the_file(rig):
    _, client, tmp_path = rig
    one, three = str(uuid.uuid4()), str(uuid.uuid4())
    post(client, telemetry('LIMBO-01', one))
    post(client, telemetry('LIMBO-03', three, patrol_state='patrolling', launch='running'))   # 공통 파일 사용
    def rename(robot_id, name, new_name):
        revision = client.get('/api/v1/waypoints', params={'robot_id': robot_id}).json()['revision']
        return client.put('/api/v1/waypoints', params={'robot_id': robot_id},
                          json={'revision': revision, 'action': 'rename', 'name': name, 'new_name': new_name})
    # LIMBO-03이 공통 경로로 순찰 중 → 같은 파일을 쓰는 LIMBO-01도 편집 불가
    blocked = rename('LIMBO-01', 'A', 'A2')
    assert blocked.status_code == 409 and blocked.json()['error']['code'] == 'patrol_active'
    # LIMBO-02는 자기 파일이므로 편집 가능
    assert rename('LIMBO-02', 'C', 'C2').status_code == 200
    assert 'C2' in (tmp_path / 'two.yaml').read_text()
    assert 'A2' not in (tmp_path / 'shared.yaml').read_text()


def test_stream_per_robot(rig):
    _, client, _ = rig
    with client.websocket_connect('/api/v1/stream?robot_id=LIMBO-02') as ws:
        assert ws.receive_json()['robot_id'] == 'LIMBO-02'
        post(client, telemetry('LIMBO-02', str(uuid.uuid4())))
        assert ws.receive_json()['bridge']['status'] == 'connected'
    assert not client.app.state.robots['LIMBO-02'].subscribers


def test_unregistered_robot_next_command_is_empty(rig):
    _, client, _ = rig
    got = client.get('/api/v1/commands/next', params=dict(robot_id='LIMBO-09', bridge_session_id=str(uuid.uuid4()), wait_s=0))
    assert got.status_code == 204
    assert 'LIMBO-09' not in client.app.state.robots


def test_other_robots_on_the_same_map_carry_their_pose(rig):
    clock, client, _ = rig
    post(client, telemetry('LIMBO-01', str(uuid.uuid4()), at=(1., 2.)))
    post(client, telemetry('LIMBO-02', str(uuid.uuid4()), at=(3., 4.)))   # 경로 파일만 다르고 지도는 같음
    robots = {r['robot_id']: r for r in client.get('/api/v1/state').json()['robots']}
    assert 'pose' not in robots['LIMBO-01']                       # 자기 위치는 스냅샷의 pose
    assert robots['LIMBO-02']['pose'] == {'x': 3., 'y': 4., 'yaw': .5, 'age_s': .01, 'stale': False}
    # 위치를 보낸 적 없는 로봇은 None, /api/v1/robots 목록에는 위치를 넣지 않는다
    post(client, telemetry('LIMBO-03', str(uuid.uuid4())))
    assert {r['robot_id']: r for r in client.get('/api/v1/state').json()['robots']}['LIMBO-03']['pose'] is None
    assert all('pose' not in r for r in client.get('/api/v1/robots').json()['robots'])
    # 연결이 늦어지면 오래된 위치로 표시
    clock.now = 4
    assert {r['robot_id']: r for r in client.get('/api/v1/state').json()['robots']}['LIMBO-02']['pose']['stale'] is True


def test_robots_on_another_map_are_not_drawn(tmp_path):
    other = tmp_path / 'other'
    other.mkdir()
    settings = Settings(map_yaml=write_map(tmp_path), waypoints_yaml=write_route(tmp_path / 'shared.yaml'),
                        robots={'LIMBO-02': {'map_yaml': write_map(other)}})
    with TestClient(create_app(settings)) as client:
        post(client, telemetry('LIMBO-01', str(uuid.uuid4()), at=(1., 2.)))
        post(client, telemetry('LIMBO-02', str(uuid.uuid4()), at=(3., 4.)))
        robots = {r['robot_id']: r for r in client.get('/api/v1/state').json()['robots']}
        assert robots['LIMBO-02']['pose'] is None
        mine = {r['robot_id']: r for r in client.get('/api/v1/state', params={'robot_id': 'LIMBO-02'}).json()['robots']}
        assert mine['LIMBO-01']['pose'] is None
