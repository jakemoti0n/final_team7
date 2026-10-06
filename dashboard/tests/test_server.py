from copy import deepcopy
import json
import uuid

from fastapi.testclient import TestClient
import pytest

from server.app import create_app
from server.models import Settings, Telemetry
from server.state import Store
from tools.sender import empty, sample


class Clock:
    now = 0.
    def __call__(self):
        return self.now


@pytest.fixture
def rig():
    clock = Clock()
    store = Store(Settings(), clock, lambda: "2026-10-06T10:00:00Z")
    with TestClient(create_app(store.settings, store)) as client:
        yield clock, store, client


def test_initial_and_health(rig):
    clock, store, client = rig
    state = client.get('/api/v1/state').json()
    assert state['bridge']['status'] == 'checking'
    assert state['motion']['current'] is None
    assert state['motion']['status'] == 'unconfirmed'
    assert all(t['age_s'] is None and t['status'] == 'never_received' for t in state['topics'].values())
    assert client.get('/healthz').json() == {'status': 'ok'}
    clock.now = 9.999
    assert store.snapshot()['bridge']['status'] == 'checking'
    clock.now = 10
    assert store.snapshot()['bridge']['status'] == 'disconnected'
    assert client.post('/api/v1/control', json={}).status_code == 404


@pytest.mark.parametrize('age,expected', [(2.999, 'connected'), (3., 'delayed'), (3.001, 'delayed'), (9.999, 'delayed'), (10., 'disconnected'), (10.001, 'disconnected')])
def test_bridge_boundaries(rig, age, expected):
    clock, store, client = rig
    client.post('/api/v1/telemetry', json=sample())
    clock.now = age
    state = store.snapshot()
    assert state['bridge']['status'] == expected
    if age >= 3:
        assert all(t['status'] == 'unknown' for t in state['topics'].values())
        assert state['motion']['current'] is None


@pytest.mark.parametrize('age,expected', [(2999., 'receiving'), (3000., 'delayed'), (3001., 'delayed')])
def test_topic_and_motion_boundaries(rig, age, expected):
    _, store, client = rig
    payload = sample()
    payload['topics']['lidar_filtered']['age_ms'] = age
    payload['motion']['age_ms'] = age
    client.post('/api/v1/telemetry', json=payload)
    state = store.snapshot()
    assert state['bridge']['status'] == 'connected'
    assert state['topics']['lidar_filtered']['status'] == expected
    assert (state['motion']['current'] is not None) == (age < 3000)


def test_duplicate_retired_sessions_do_not_refresh_heartbeat(rig):
    clock, store, client = rig
    a = sample(sequence=5)
    assert client.post('/api/v1/telemetry', json=a).json()['accepted']
    clock.now = 4
    for n in (5, 4):
        a['sequence'] = n
        result = client.post('/api/v1/telemetry', json=a).json()
        assert result['reason'] == 'duplicate_or_out_of_order'
        assert 'server_received_at' not in result
    assert store.snapshot()['bridge']['status'] == 'delayed'
    b = empty()
    client.post('/api/v1/telemetry', json=b)
    assert store.snapshot()['motion']['last_valid'] is None
    assert all(t['status'] == 'never_received' for t in store.snapshot()['topics'].values())
    a['sequence'] = 100
    assert client.post('/api/v1/telemetry', json=a).json()['reason'] == 'retired_session'
    assert store.sequence == 1
    for _ in range(105):
        store.accept(Telemetry.model_validate(empty()))
    assert len(store.retired) == 100


@pytest.mark.parametrize('mutate', [
    lambda p: p.update(schema_version=2), lambda p: p.update(schema_version=True),
    lambda p: p.update(sequence=0), lambda p: p.update(sequence='1'),
    lambda p: p.update(extra='image'), lambda p: p.update(source_clock='utc'),
    lambda p: p.update(bridge_session_id='not-uuid'),
    lambda p: p.update(sent_at='2026-10-06T10:00:00+09:00'),
    lambda p: p['topics'].pop('odom'), lambda p: p['topics']['odom'].update(extra=0),
    lambda p: p['topics']['odom'].update(age_ms=-1),
    lambda p: p['topics']['odom'].update(age_ms=True),
    lambda p: p['topics']['odom'].update(received_count=0),
    lambda p: p['topics']['odom'].update(last_received_at=None),
    lambda p: p['topics']['odom']['header_stamp'].update(nanosec=1000000000),
    lambda p: p['motion'].update(linear_speed_mps=-1),
    lambda p: p['motion'].update(age_ms=None),
    lambda p: p['motion'].update(angular_velocity_radps=float('nan')),
    lambda p: p['motion'].update(linear_speed_mps=float('inf')),
])
def test_invalid_payload_never_changes_state(rig, mutate):
    _, store, client = rig
    payload = sample()
    mutate(payload)
    response = client.post('/api/v1/telemetry', content=json.dumps(payload), headers={'Content-Type': 'application/json'})
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'invalid_payload'
    assert store.payload is None


def test_http_errors(rig):
    _, store, client = rig
    for body, content_type, code, name in [(b'{', 'application/json', 400, 'invalid_json'),
        (b'\xff', 'application/json', 400, 'invalid_json'),
        (b' '*8193, 'application/json', 413, 'payload_too_large'),
        (b'{}', 'text/plain', 415, 'unsupported_media_type')]:
        result = client.post('/api/v1/telemetry', content=body, headers={'Content-Type': content_type})
        assert result.status_code == code
        assert result.json()['error']['code'] == name
    p = empty(); p['robot_id'] = 'other'
    assert client.post('/api/v1/telemetry', json=p).status_code == 409
    assert store.payload is None


def test_zero_rotation_invalid_and_clock_independence(rig):
    clock, store, client = rig
    p = sample(speed=0.)
    p['sent_at'] = '1990-01-01T00:00:00Z'
    client.post('/api/v1/telemetry', json=p)
    assert store.snapshot()['motion']['status'] == 'stopped'
    p['sequence'] += 1; p['motion']['angular_velocity_radps'] = -.05
    p['topics']['odom']['header_stamp']['sec'] = -10
    client.post('/api/v1/telemetry', json=p)
    assert store.snapshot()['motion']['rotating']
    p['sequence'] += 1; p['motion'] = empty()['motion']
    client.post('/api/v1/telemetry', json=p)
    state = store.snapshot()
    assert state['motion']['status'] == 'unknown'
    assert state['motion']['current'] is None
    assert state['motion']['last_valid']['linear_speed_mps'] == 0
    assert state['topics']['odom']['status'] == 'receiving'


def test_alert_lifecycle_and_session_reset(rig):
    clock, store, client = rig
    p = empty()
    client.post('/api/v1/telemetry', json=p)
    clock.now = 3
    p['sequence'] = 2
    client.post('/api/v1/telemetry', json=p)
    for _ in range(10): store.snapshot()
    assert len(store.active) == 4
    assert all(t['status'] == 'never_received' for t in store.snapshot()['topics'].values())
    clock.now = 6
    store.snapshot()
    count = len(store.alerts)
    clock.now = 13
    store.snapshot()
    assert len(store.alerts) == count  # severity update, no new incident
    assert store.active['bridge']['severity'] == 'error'
    p = sample(p['bridge_session_id'], 3)
    client.post('/api/v1/telemetry', json=p)
    assert not store.active
    assert sum(a['kind'] == 'recovery' for a in store.alerts) == 5
    p['sequence'] += 1; p['topics']['lidar_raw']['age_ms'] = 4000.
    client.post('/api/v1/telemetry', json=p)
    client.post('/api/v1/telemetry', json=empty())
    assert 'topic:lidar_raw' not in store.active
    assert sum(a['message'] == 'LiDAR 원본 수신 재개' for a in store.alerts) == 1


def test_alert_capacity_is_independent_of_active_keys(rig):
    _, store, _ = rig
    store.problem('topic:odom', 'warning', 'pending')
    for i in range(150): store.add(str(i), 'info', 'test', 'connection')
    assert len(store.alerts) == 100
    store.problem('topic:odom', 'warning', 'pending')
    assert len(store.alerts) == 100
    assert not any(a['key'] == 'topic:odom' for a in store.alerts)


def test_websocket_initial_tick_latest_and_disconnect_cleanup(rig):
    clock, store, client = rig
    with client.websocket_connect('/api/v1/stream') as ws:
        initial = ws.receive_json()
        clock.now = 10
        tick = ws.receive_json()
        assert tick['bridge']['status'] == 'disconnected'
        assert tick['revision'] > initial['revision']
        assert all(q.maxsize == 1 for q in client.app.state.subscribers)
        client.post('/api/v1/telemetry', json=sample())
        assert ws.receive_json()['bridge']['status'] == 'connected'
    assert not client.app.state.subscribers


def test_heartbeat_cannot_refresh_stopped_topics(rig):
    clock, store, client = rig
    p = sample()
    client.post('/api/v1/telemetry', json=p)
    for second in range(1, 12):
        clock.now = float(second)
        p['sequence'] += 1
        for topic in p['topics'].values():
            topic.update(age_ms=second * 1000., receive_hz=0.)
        p['motion']['age_ms'] = second * 1000.
        client.post('/api/v1/telemetry', json=p)
    s = store.snapshot()
    assert s['bridge']['status'] == 'connected'
    assert all(t['status'] == 'delayed' and t['receive_hz'] is None for t in s['topics'].values())
    assert s['motion']['current'] is None
    assert len(store.active) == 4
    assert len(s['alerts']) == 5


def test_exact_body_limit_and_empty_motion_relation(rig):
    _, _, client = rig
    p = empty()
    encoded = json.dumps(p).encode()
    response = client.post('/api/v1/telemetry', content=encoded + b' ' * (8192 - len(encoded)), headers={'Content-Type': 'application/json; charset=utf-8'})
    assert response.status_code == 200
    p['motion'] = sample()['motion']
    assert client.post('/api/v1/telemetry', json=p).status_code == 422


def test_custom_thresholds_and_restart_clear_state():
    clock = Clock()
    cfg = Settings.model_validate({'topic_delay_s': {'odom': 8., 'lidar_filtered': 1.}})
    store = Store(cfg, clock)
    p = sample()
    for t in p['topics'].values(): t['age_ms'] = 2000.
    p['motion']['age_ms'] = 4000.
    store.accept(Telemetry.model_validate(p))
    state = store.snapshot()
    assert state['topics']['lidar_filtered']['status'] == 'delayed'
    assert state['topics']['odom']['status'] == 'receiving'
    assert state['motion']['current'] is not None
    restarted = Store(cfg, clock).snapshot()
    assert restarted['server_run_id'] != state['server_run_id']
    assert restarted['alerts'] == []
    assert restarted['motion']['last_valid'] is None
