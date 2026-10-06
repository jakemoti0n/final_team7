"""One request in flight, zero queued snapshots, monotonic scheduling."""
import asyncio
from datetime import datetime
import json
import logging
import threading
import time
import aiohttp

LOG = logging.getLogger(__name__)
MAX_BYTES = 8192


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
    def __init__(self, state, config, monotonic=time.monotonic, sleep=asyncio.sleep):
        self.state, self.config = state, config
        self.monotonic, self.sleep = monotonic, sleep
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._thread_main, name='telemetry-http', daemon=True)
        self.status = None
        self.attempts = self.bytes_sent = self.max_payload_bytes = 0
        self.in_flight = 0
        self.error = None

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=self.config['request_timeout_s'] + 2)
        if self.thread.is_alive():
            raise RuntimeError('HTTP worker failed to stop within its deadline')

    def _thread_main(self):
        try:
            asyncio.run(self.run())
        except Exception as exc:
            self.error = repr(exc)
            LOG.exception('telemetry worker stopped unexpectedly')

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
