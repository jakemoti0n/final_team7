"""One request in flight, zero queued snapshots, monotonic scheduling.

텔레메트리와 별도로 관제 명령 작업을 돈다 (docs/CONTROL_API_DRAFT.md §2):
commands/next long poll → 순찰 서비스 호출 → 결과를 한 번만 보고. 명령은 다시 보내지 않는다.
"""
import asyncio
from datetime import datetime
import json
import logging
import threading
import time
import math
import uuid
import aiohttp

LOG = logging.getLogger(__name__)
MAX_BYTES = 8192
COMMANDS = ('pause', 'resume')
MESSAGE_LIMIT = 200
# 서비스를 부르기 직전 서버에 "아직 유효한가"를 묻는 왕복 시간 한도. 넘으면 부르지 않는다.
# ttl_ms만으로는 서버가 넘긴 뒤 Bridge가 읽기까지 걸린 시간을 알 수 없다 (2026-10-13 실패 시험 문제 1)
CLAIM_MAX_RTT_S = 1.0


def command_from(body):
    """commands/next 200 응답 검증. 정의된 세 필드만 허용한다."""
    reply = json.loads(body)
    if not isinstance(reply, dict) or set(reply) != {'request_id', 'command', 'ttl_ms'}:
        raise ValueError('unexpected command fields')
    if not isinstance(reply['request_id'], str):
        raise ValueError('invalid request_id')
    uuid.UUID(reply['request_id'])
    if reply['command'] not in COMMANDS:
        raise ValueError('unknown command')
    ttl = reply['ttl_ms']
    if type(ttl) not in (int, float) or not math.isfinite(ttl) or ttl < 0:
        raise ValueError('invalid ttl_ms')
    return reply


def response_outcome(status, body, snapshot):
    if 400 <= status < 500:
        return f'http_{status}', 'slow'
    if status != 200:
        return f'http_{status}', 'failure'
    try:
        reply = json.loads(body)
        if (reply['bridge_session_id'] != snapshot['bridge_session_id'] or
                type(reply['sequence']) is not int or reply['sequence'] != snapshot['sequence']):
            raise ValueError('response identity mismatch')
        if reply['accepted'] is True:
            if set(reply) != {'accepted', 'bridge_session_id', 'sequence', 'server_received_at'}:
                raise ValueError('unexpected response fields')
            at = datetime.fromisoformat(reply['server_received_at'].replace('Z', '+00:00'))
            if at.utcoffset() is None or at.utcoffset().total_seconds() != 0:
                raise ValueError('response timestamp must be UTC')
            return 'connected', 'success'
        if reply['accepted'] is not False or set(reply) != {'accepted', 'bridge_session_id', 'sequence', 'reason'}:
            raise ValueError('invalid rejection')
        if reply['reason'] == 'retired_session':
            return 'retired_session: check configuration or duplicate bridge', 'slow'
        if reply['reason'] == 'duplicate_or_out_of_order':
            return 'duplicate_or_out_of_order', 'success'
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    return 'invalid_response', 'failure'


class Retry:
    def __init__(self, interval):
        self.interval, self.failures = interval, 0

    def delay(self, outcome):
        if outcome == 'success':
            self.failures = 0
            return self.interval
        if outcome == 'slow':
            self.failures = 0
            return 10.0
        delay = (1, 2, 4, 8, 10)[min(self.failures, 4)]
        self.failures = min(self.failures + 1, 5)
        return float(delay)


class Sender:
    def __init__(self, state, config, monotonic=time.monotonic, sleep=asyncio.sleep, controller=None):
        # controller: call(command) -> 서비스 future 또는 None(서비스 없음). None이면 명령 작업을 안 돈다
        self.state, self.config, self.controller = state, config, controller
        self.monotonic, self.sleep = monotonic, sleep
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._thread_main, name='telemetry-http', daemon=True)
        self.status = None
        self.attempts = self.bytes_sent = self.max_payload_bytes = 0
        self.in_flight = 0
        self.error = None
        self.command_status = None
        self.command_results = []  # 보고한 결과 (진단·시험용, 최근 20개)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        # 명령 작업의 long poll도 stop_event를 0.05초마다 보고 취소되므로 같은 기한으로 충분하다
        self.thread.join(timeout=self.config['request_timeout_s'] + 2)
        if self.thread.is_alive():
            raise RuntimeError('HTTP worker failed to stop within its deadline')

    def _thread_main(self):
        try:
            asyncio.run(self.main())
        except Exception as exc:
            self.error = repr(exc)
            LOG.exception('telemetry worker stopped unexpectedly')

    async def main(self):
        jobs = [self.run()]
        if self.controller is not None:
            jobs.append(self.command_run())
        await asyncio.gather(*jobs)

    async def stoppable(self, coro):
        """stop_event가 서면 진행 중인 요청을 취소한다. 취소되면 None."""
        task = asyncio.ensure_future(coro)
        while not task.done():
            if self.stop_event.is_set():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                return None
            await asyncio.wait({task}, timeout=0.05)
        return task.result()

    async def post(self, client, snapshot):
        body = json.dumps(snapshot, allow_nan=False, separators=(',', ':')).encode('utf-8')
        if len(body) > MAX_BYTES:
            return 'payload_too_large', 'slow'
        self.attempts += 1
        self.bytes_sent += len(body)
        self.max_payload_bytes = max(self.max_payload_bytes, len(body))
        self.in_flight = 1
        try:
            # Includes DNS/connect/headers/body; redirects and decompression are disabled.
            async with asyncio.timeout(self.config['request_timeout_s']):
                async with client.post(self.config['server_url'].rstrip('/') + '/api/v1/telemetry',
                                       data=body, headers={'Content-Type': 'application/json'},
                                       allow_redirects=False) as response:
                    if response.status != 200:
                        # Status is sufficient even when proxy body is absent or malformed.
                        return response_outcome(response.status, b'', snapshot)
                    if response.content_type != 'application/json':
                        return 'invalid_response', 'failure'
                    chunks = bytearray()
                    async for chunk in response.content.iter_chunked(1024):
                        chunks.extend(chunk)
                        if len(chunks) > MAX_BYTES:
                            return 'response_too_large', 'failure'
                    return response_outcome(response.status, chunks, snapshot)
        except (aiohttp.ClientError, TimeoutError, OSError) as exc:
            return type(exc).__name__, 'failure'
        finally:
            self.in_flight = 0

    async def run(self):
        retry = Retry(self.config['send_interval_s'])
        async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config['request_timeout_s']),
                connector=aiohttp.TCPConnector(limit=1), cookie_jar=aiohttp.DummyCookieJar(),
                auto_decompress=False, read_bufsize=8192) as client:
            while not self.stop_event.is_set():
                started = self.monotonic()
                status, outcome = await self.post(client, self.state.snapshot())
                delay = retry.delay(outcome)
                if status != self.status:
                    LOG.log(logging.INFO if outcome == 'success' else logging.WARNING,
                            'transport=%s next_delay_s=%.2f', status, delay)
                    self.status = status
                # Normal cadence is start-to-start; failures wait after completion.
                deadline = (started if outcome == 'success' else self.monotonic()) + delay
                while not self.stop_event.is_set() and self.monotonic() < deadline:
                    await self.sleep(min(0.05, max(0, deadline-self.monotonic())))

    # ---- 관제 명령 ----

    async def fetch_command(self, client):
        """('command', 명령, 받은 단조 시각) / ('empty',) / (상태, 'slow'|'failure')"""
        control = self.config['control']
        params = dict(robot_id=self.state.robot_id, bridge_session_id=self.state.session_id,
                      wait_s=str(control['command_wait_s']))
        try:
            async with asyncio.timeout(control['command_wait_s'] + self.config['request_timeout_s']):
                async with client.get(self.config['server_url'].rstrip('/') + '/api/v1/commands/next',
                                      params=params, allow_redirects=False) as response:
                    if response.status == 204:
                        return ('empty',)
                    if response.status != 200:
                        return (f'http_{response.status}', 'slow' if 400 <= response.status < 500 else 'failure')
                    body = await response.content.read(MAX_BYTES + 1)
                    if len(body) > MAX_BYTES:
                        return ('response_too_large', 'failure')
                    received = self.monotonic()
                    return ('command', command_from(body), received)
        except (ValueError, KeyError, TypeError, AttributeError):
            return ('invalid_command', 'failure')
        except (aiohttp.ClientError, TimeoutError, OSError) as exc:
            return (type(exc).__name__, 'failure')

    async def claim(self, client, command):
        """('claimed'|'refused'|오류 이름, 왕복 초). 왕복은 Bridge 단조 시계로만 잰다."""
        url = self.config['server_url'].rstrip('/') + '/api/v1/commands/' + command['request_id'] + '/claim'
        body = json.dumps(dict(robot_id=self.state.robot_id, bridge_session_id=self.state.session_id)).encode()
        started = self.monotonic()
        try:
            async with asyncio.timeout(CLAIM_MAX_RTT_S):
                async with client.post(url, data=body, headers={'Content-Type': 'application/json'},
                                       allow_redirects=False) as response:
                    status = 'claimed' if response.status == 200 else 'refused'
        except (aiohttp.ClientError, TimeoutError, OSError) as exc:
            status = type(exc).__name__
        return status, self.monotonic() - started

    async def execute(self, command, received, client=None):
        """서버에 유효한지 확인한 뒤 서비스를 한 번 부르고 결과 보고 본문을 만든다. 다시 부르지 않는다."""
        result = dict(robot_id=self.state.robot_id, bridge_session_id=self.state.session_id,
                      request_id=command['request_id'], outcome=None, message='',
                      service_latency_ms=None,
                      patrol_update_count_at_call=self.state.patrol_update_count())
        if self.monotonic() - received >= command['ttl_ms'] / 1000:
            return {**result, 'outcome': 'expired', 'message': 'command expired before service call'}
        claimed, rtt = await self.claim(client, command)
        if claimed != 'claimed':
            return {**result, 'outcome': 'expired', 'message': f'claim {claimed}'}
        if rtt > CLAIM_MAX_RTT_S:
            return {**result, 'outcome': 'expired', 'message': f'claim too slow ({rtt:.2f} s)'}
        started = self.monotonic()
        future = self.controller.call(command['command'])
        if future is None:
            return {**result, 'outcome': 'service_unavailable', 'message': 'patrol service not available'}
        deadline = started + self.config['control']['service_timeout_s']
        while not future.done() and self.monotonic() < deadline and not self.stop_event.is_set():
            await self.sleep(0.01)
        latency = (self.monotonic() - started) * 1000
        if not future.done():
            future.cancel()
            return {**result, 'outcome': 'no_response', 'message': 'no service response'}
        response = future.result()
        message = str(getattr(response, 'message', ''))[:MESSAGE_LIMIT]
        outcome = 'accepted' if getattr(response, 'success', False) is True else 'rejected'
        return {**result, 'outcome': outcome, 'message': message, 'service_latency_ms': latency}

    async def report(self, client, result):
        """결과는 한 번만 보낸다. 유실되면 서버가 no_response로 처리한다."""
        url = (self.config['server_url'].rstrip('/') + '/api/v1/commands/'
               + result['request_id'] + '/result')
        body = json.dumps(result, allow_nan=False, separators=(',', ':')).encode('utf-8')
        try:
            async with asyncio.timeout(self.config['request_timeout_s'] + 1):
                async with client.post(url, data=body, headers={'Content-Type': 'application/json'},
                                       allow_redirects=False) as response:
                    return f'http_{response.status}'
        except (aiohttp.ClientError, TimeoutError, OSError) as exc:
            return type(exc).__name__

    async def command_run(self):
        retry = Retry(1.0)
        control = self.config['control']
        async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=control['command_wait_s'] + self.config['request_timeout_s']),
                connector=aiohttp.TCPConnector(limit=1), cookie_jar=aiohttp.DummyCookieJar(),
                auto_decompress=False, read_bufsize=8192) as client:
            while not self.stop_event.is_set():
                fetched = await self.stoppable(self.fetch_command(client))
                if fetched is None:
                    break
                if fetched[0] == 'command':
                    _, command, received = fetched
                    retry.delay('success')
                    LOG.info('command %s %s', command['command'], command['request_id'])
                    result = await self.execute(command, received, client)
                    reported = await self.stoppable(self.report(client, result))
                    LOG.info('command %s outcome=%s message=%s report=%s', command['request_id'],
                             result['outcome'], result['message'], reported)
                    self.command_results = (self.command_results + [{**result, 'report': reported}])[-20:]
                    self.command_status = 'connected'
                    continue
                if fetched[0] == 'empty':
                    retry.delay('success')
                    if self.command_status != 'connected':
                        LOG.info('commands=connected')
                    self.command_status = 'connected'
                    continue
                status, outcome = fetched
                delay = retry.delay(outcome)
                if status != self.command_status:
                    LOG.warning('commands=%s next_delay_s=%.2f', status, delay)
                    self.command_status = status
                deadline = self.monotonic() + delay
                while not self.stop_event.is_set() and self.monotonic() < deadline:
                    await self.sleep(min(0.05, max(0, deadline - self.monotonic())))
