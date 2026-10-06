import asyncio
import json
import math
import threading
import time
import urllib.error
import urllib.request
import aiohttp
import pytest
from limbo_telemetry_bridge.state import State, TOPICS
from limbo_telemetry_bridge.transport import Sender, Retry, response_outcome
from receiver import Receiver, validate


class Clock:
    now = 0.0
    def mono(self):
        return self.now
    def utc(self):
        return '2026-10-06T00:00:00.000Z'


def test_time_frequency_motion_and_restart():
    clock = Clock()
    state = State(monotonic=clock.mono, utc=clock.utc)
    first = state.snapshot()
    validate(first)
    assert all(t['received_count'] == 0 and t['receive_hz'] is None for t in first['topics'].values())
    for i in range(1, 51):
        clock.now = i / 10
        for key in TOPICS:
            state.receive(key, 100-i, 0, (3., 4., -0.5) if key == 'odom' else None)
    snapshot = state.snapshot()
    validate(snapshot)
    assert snapshot['motion']['linear_speed_mps'] == 5
    assert snapshot['motion']['angular_velocity_radps'] == -0.5
    assert snapshot['topics']['odom']['receive_hz'] == 10
    assert snapshot['topics']['odom']['header_stamp']['sec'] == 50
    clock.now = 11
    snapshot = state.snapshot()
    assert snapshot['topics']['odom']['receive_hz'] == 0
    assert snapshot['topics']['odom']['age_ms'] == 6000
    assert snapshot['topics']['odom']['received_count'] == 50
    state.receive('odom', 0, 0, (0., 0., 1.))
    assert state.snapshot()['motion']['linear_speed_mps'] == 0
    assert state.snapshot()['motion']['angular_velocity_radps'] == 1
    for bad in (math.nan, math.inf, -math.inf):
        for index in range(3):
            values = [0., 0., 0.]
            values[index] = bad
            state.receive('odom', 0, 0, tuple(values))
            snapshot = state.snapshot()
            validate(snapshot)
            assert all(v is None for v in snapshot['motion'].values())
    restarted = State().snapshot()
    assert restarted['sequence'] == 1 and restarted['bridge_session_id'] != first['bridge_session_id']
    assert restarted['topics']['odom']['received_count'] == 0


def test_bounded_history_and_warmup():
    clock = Clock()
    state = State(monotonic=clock.mono, utc=clock.utc)
    for i in range(10000):
        clock.now = i / 100
        state.receive('camera_raw', 0, 0)
        if clock.now < 5:
            assert state.snapshot()['topics']['camera_raw']['receive_hz'] is None
    assert len(state.topics['camera_raw']['buckets']) <= 51
    assert state.snapshot()['topics']['camera_raw']['receive_hz'] == 100
    assert len(json.dumps(state.snapshot()).encode()) < 8192


def test_retry_schedule():
    retry = Retry(1)
    assert [retry.delay('failure') for _ in range(7)] == [1, 2, 4, 8, 10, 10, 10]
    assert retry.delay('success') == 1
    assert retry.delay('failure') == 1
    assert retry.delay('slow') == 10


def test_sender_schedule_with_virtual_monotonic_clock():
    clock = Clock()
    async def sleep(delay):
        clock.now += delay
        await asyncio.sleep(0)
    state = State(monotonic=clock.mono, utc=clock.utc)
    sender = Sender(state, dict(server_url='http://127.0.0.1:1',
                               request_timeout_s=1, send_interval_s=1),
                    monotonic=clock.mono, sleep=sleep)
    attempts = []
    outcomes = iter(['failure', 'failure', 'failure', 'slow', 'success', 'success'])
    async def post(client, payload):
        attempts.append((clock.now, payload['sequence']))
        clock.now += .2
        outcome = next(outcomes)
        if len(attempts) == 6:
            sender.stop_event.set()
        return outcome, outcome
    sender.post = post
    asyncio.run(sender.run())
    assert [a[0] for a in attempts] == pytest.approx([0, 1.2, 3.4, 7.6, 17.8, 18.8])
    assert [a[1] for a in attempts] == [1, 2, 3, 4, 5, 6]


@pytest.fixture
def server():
    receiver = Receiver(('127.0.0.1', 0))
    thread = threading.Thread(target=receiver.serve_forever, daemon=True)
    thread.start()
    yield receiver
    receiver.shutdown()
    receiver.server_close()
    thread.join(2)


def config(server, timeout=0.15):
    return dict(server_url=f'http://127.0.0.1:{server.server_port}',
                request_timeout_s=timeout, send_interval_s=0.1)


@pytest.mark.parametrize('mode,expected', [('ok','success'), ('delay','failure'),
    ('disconnect','failure'), ('error','failure'), ('client_error','slow'),
    ('malformed','failure'), ('oversized','failure'), ('retired','slow'), ('drip','failure')])
def test_real_http_faults_and_recovery(server, mode, expected):
    async def run():
        state = State()
        sender = Sender(state, config(server))
        server.mode = mode
        started = time.monotonic()
        async with aiohttp.ClientSession(auto_decompress=False) as client:
            result = await sender.post(client, state.snapshot())
            assert result[1] == expected
            assert time.monotonic()-started < 0.6
            state.receive('odom', 0, 0, (0., 0., 0.))
            server.mode = 'ok'
            assert (await sender.post(client, state.snapshot()))[1] == 'success'
        assert server.latest['sequence'] == 2
        assert server.latest['topics']['odom']['received_count'] == 1
    asyncio.run(run())


def test_worker_keeps_collection_and_shutdown_bounded(server):
    state = State()
    server.mode = 'delay'
    sender = Sender(state, config(server))
    sender.start()
    try:
        deadline = time.monotonic()+0.5
        count = 0
        while time.monotonic() < deadline:
            state.receive('camera_raw', 0, 0)
            count += 1
            time.sleep(.001)
        assert state.topics['camera_raw']['count'] == count > 100
        assert sender.in_flight <= 1
        server.mode = 'ok'
        deadline = time.monotonic()+2
        while sender.status != 'connected' and time.monotonic() < deadline:
            time.sleep(.01)
        assert sender.status == 'connected'
        assert server.latest['topics']['camera_raw']['received_count'] == count
    finally:
        before = time.monotonic()
        sender.stop()
        assert time.monotonic()-before < .5
    assert sender.error is None


def test_session_rules_and_heartbeat(server):
    state = State()
    first = state.snapshot()
    assert server.accept(first, 100)['accepted']
    received = server.received_mono
    assert server.accept(first, 100)['reason'] == 'duplicate_or_out_of_order'
    assert server.received_mono == received
    second = State().snapshot()
    assert server.accept(second, 100)['accepted']
    assert server.accept(state.snapshot(), 100)['reason'] == 'retired_session'
    for _ in range(105):
        server.accept(State().snapshot(), 100)
    assert len(server.retired) == 100


@pytest.mark.parametrize('mutate', [
    lambda p: p.update(extra=1), lambda p: p.update(schema_version=True),
    lambda p: p.update(sequence=0), lambda p: p.update(source_clock='utc'),
    lambda p: p['topics']['odom'].update(received_count=-1),
    lambda p: p['topics']['odom'].update(age_ms=0),
    lambda p: p['motion'].update(linear_speed_mps=0),
])
def test_independent_contract_rejects_invalid(mutate):
    payload = State().snapshot()
    mutate(payload)
    with pytest.raises(ValueError):
        validate(payload)


def test_receiver_http_errors(server):
    url = config(server)['server_url'] + '/api/v1/telemetry'
    good = State().snapshot()
    for data, content_type, status in [(b'{', 'application/json', 400),
            (b'x'*8193, 'application/json', 413), (b'{}','text/plain',415),
            (b'{}', 'application/json',422),
            (json.dumps({**good, 'robot_id':'other'}).encode(), 'application/json',409)]:
        request = urllib.request.Request(url, data=data, headers={'Content-Type':content_type})
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(request, timeout=1)
        assert exc.value.code == status


def test_response_identity_and_duplicates():
    payload = State().snapshot()
    reply = dict(accepted=False, bridge_session_id=payload['bridge_session_id'],
                 sequence=1, reason='duplicate_or_out_of_order')
    assert response_outcome(200, json.dumps(reply), payload)[1] == 'success'
    reply['sequence'] = True
    assert response_outcome(200, json.dumps(reply), payload)[1] == 'failure'
    reply['sequence'] = 9
    assert response_outcome(200, json.dumps(reply), payload)[1] == 'failure'


def test_shutdown_during_active_timeout(server):
    server.mode = 'delay'
    server.delay = 3
    sender = Sender(State(), config(server, timeout=1))
    sender.start()
    deadline = time.monotonic()+1
    while not sender.in_flight and time.monotonic() < deadline:
        time.sleep(.001)
    assert sender.in_flight == 1
    started = time.monotonic()
    sender.stop()
    assert time.monotonic()-started < 1.3
    assert not sender.thread.is_alive()


def test_wall_clock_reversal_does_not_affect_age_or_frequency():
    clock = Clock()
    state = State(monotonic=clock.mono, utc=clock.utc)
    state.receive('odom', 100, 0, (1., 0., 0.))
    state.utc = lambda: '2000-01-01T00:00:00.000Z'
    clock.now = 6
    state.receive('camera_raw', -5, 0)
    payload = state.snapshot()
    validate(payload)
    assert payload['topics']['odom']['age_ms'] == 6000
    assert payload['topics']['odom']['receive_hz'] == 0
    assert payload['topics']['camera_raw']['header_stamp']['sec'] == -5
