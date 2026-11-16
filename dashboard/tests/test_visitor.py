"""방문자 안내(/visitor): 로그인 없이 읽기만. 이름·쉬운 상태·대략 위치만 내보내고, 꺼져 있으면 404."""
import uuid

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.models import Settings
from server.state import Store
from server.users import UserStore
from tests.test_robots import Clock, post, telemetry, write_map, write_route


def make(tmp_path, enabled=True, users=None, robots=None):
    clock = Clock()
    settings = Settings(map_yaml=write_map(tmp_path), waypoints_yaml=write_route(tmp_path / 'route.yaml'),
                        robots=robots or {}, visitor_enabled=enabled)
    store = Store(settings, clock, lambda: '2026-10-13T00:00:00Z')
    return clock, TestClient(create_app(settings, store, users=users))


def test_disabled_by_default_everything_is_404(tmp_path):
    assert Settings().visitor_enabled is False
    _, client = make(tmp_path, enabled=False)
    with client:
        for path in ('/visitor', '/api/v1/visitor/state', '/api/v1/visitor/map.png'):
            response = client.get(path)
            assert response.status_code == 404 and response.json()['error']['code'] == 'visitor_disabled', path


def test_only_public_fields_and_rounded_position(tmp_path):
    clock, client = make(tmp_path)
    with client:
        post(client, telemetry('LIMBO-01', str(uuid.uuid4()), patrol_state='patrolling', launch='running', at=(2.26, 3.74)))
        response = client.get('/api/v1/visitor/state')
        assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
        body = response.json()
        assert set(body) == {'server_utc', 'robots', 'operating', 'map'}
        assert body['map'] == dict(resolution=1., origin=[0., 0., 0.], width=10, height=10, image='/api/v1/visitor/map.png')
        assert body['operating'] == 1
        [robot] = body['robots']
        assert robot == dict(robot_id='LIMBO-01', status='patrolling', position=dict(x=2.5, y=3.5, stale=False, age_s=0))
        # 경고·센서·명령·waypoint는 응답 어디에도 없다
        text = response.text
        for secret in ('alerts', 'topics', 'command', 'waypoints', 'session', 'launcher', 'yaw'):
            assert secret not in text, secret
        image = client.get('/api/v1/visitor/map.png')
        assert image.status_code == 200 and image.content.startswith(b'\x89PNG')


def test_status_words(tmp_path):
    clock, client = make(tmp_path)
    with client:
        def status():
            return client.get('/api/v1/visitor/state').json()['robots'][0]['status']
        assert status() == 'checking'
        session = str(uuid.uuid4())
        post(client, telemetry('LIMBO-01', session, 1, at=(1, 1)))
        assert status() == 'idle'
        post(client, telemetry('LIMBO-01', session, 2, patrol_state='paused', launch='running', at=(1, 1)))
        assert status() == 'paused'
        clock.now += 4
        assert status() == 'checking'   # 수신 지연: 지금 상태를 모른다
        clock.now += 10
        body = client.get('/api/v1/visitor/state').json()
        assert body['robots'][0]['status'] == 'offline' and body['operating'] == 0
        assert body['robots'][0]['position']['stale'] is True   # 끊긴 로봇의 마지막 위치는 오래됨으로
        clock.now += 60
        assert client.get('/api/v1/visitor/state').json()['robots'][0]['position'] is None   # 1분 넘은 위치는 숨김


def test_robot_on_other_map_has_no_position(tmp_path):
    other = tmp_path / 'other'
    other.mkdir()
    clock, client = make(tmp_path, robots={'LIMBO-02': {'map_yaml': write_map(other)}})
    with client:
        post(client, telemetry('LIMBO-01', str(uuid.uuid4()), at=(1, 1)))
        post(client, telemetry('LIMBO-02', str(uuid.uuid4()), at=(2, 2)))
        robots = {r['robot_id']: r for r in client.get('/api/v1/visitor/state').json()['robots']}
        assert robots['LIMBO-01']['position'] is not None
        assert robots['LIMBO-02']['position'] is None and robots['LIMBO-02']['status'] == 'idle'


def test_visitor_needs_no_login_but_operator_api_still_does(tmp_path):
    users = UserStore(str(tmp_path / 'users.db'), 3600, 7200)
    try:
        _, client = make(tmp_path, users=users)
        with client:
            assert client.get('/api/v1/visitor/state').status_code == 200
            assert client.get('/api/v1/visitor/map.png').status_code == 200
            for path in ('/api/v1/state', '/api/v1/robots', '/api/v1/map', '/api/v1/map.png', '/api/v1/waypoints'):
                assert client.get(path).status_code == 401, path
            assert client.post('/api/v1/visitor/state').status_code == 405   # 명령을 받는 경로가 없다
    finally:
        users.close()
