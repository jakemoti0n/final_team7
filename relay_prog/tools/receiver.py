#!/usr/bin/env python3
"""Independent stdlib-only v1 test receiver. No ROS or bridge imports."""
import argparse
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import threading
import time
import uuid

KEYS = {'odom', 'lidar_raw', 'lidar_filtered', 'camera_raw'}


def utc():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def fields(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected.split()):
        raise ValueError('missing or unknown fields')


def number(value, minimum=None, integer=False):
    if type(value) not in ((int,) if integer else (int, float)):
        raise ValueError('invalid number type')
    if not math.isfinite(value) or (minimum is not None and value < minimum):
        raise ValueError('invalid number range')


def timestamp(value):
    if not isinstance(value, str) or 'T' not in value:
        raise ValueError('invalid UTC timestamp')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError('timestamp is not UTC')


def validate(payload):
    fields(payload, 'schema_version robot_id bridge_session_id sequence sent_at source_clock topics motion')
    if type(payload['schema_version']) is not int or payload['schema_version'] != 1:
        raise ValueError('unsupported schema_version')
    if not isinstance(payload['robot_id'], str) or not payload['robot_id']:
        raise ValueError('invalid robot_id')
    if not isinstance(payload['bridge_session_id'], str):
        raise ValueError('invalid session')
    uuid.UUID(payload['bridge_session_id'])
    number(payload['sequence'], 1, True)
    timestamp(payload['sent_at'])
    if payload['source_clock'] not in ('ros_sim', 'ros_system'):
        raise ValueError('invalid source_clock')
    if not isinstance(payload['topics'], dict) or set(payload['topics']) != KEYS:
        raise ValueError('invalid topics')
    for topic in payload['topics'].values():
        fields(topic, 'header_stamp last_received_at age_ms received_count receive_hz')
        number(topic['received_count'], 0, True)
        if topic['received_count'] == 0:
            if any(topic[k] is not None for k in topic if k != 'received_count'):
                raise ValueError('unreceived topic must be null')
            continue
        fields(topic['header_stamp'], 'sec nanosec')
        number(topic['header_stamp']['sec'], integer=True)
        number(topic['header_stamp']['nanosec'], 0, True)
        if topic['header_stamp']['nanosec'] >= 1_000_000_000:
            raise ValueError('nanosec out of range')
        timestamp(topic['last_received_at'])
        number(topic['age_ms'], 0)
        if topic['receive_hz'] is not None:
            number(topic['receive_hz'], 0)
    motion = payload['motion']
    fields(motion, 'linear_speed_mps angular_velocity_radps last_received_at age_ms')
    if all(v is None for v in motion.values()):
        return
    number(motion['linear_speed_mps'], 0)
    number(motion['angular_velocity_radps'])
    timestamp(motion['last_received_at'])
    number(motion['age_ms'], 0)
    odom = payload['topics']['odom']
    if (not odom['received_count'] or motion['last_received_at'] != odom['last_received_at']
            or motion['age_ms'] != odom['age_ms']):
        raise ValueError('motion must refer to latest odom')


class Receiver(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address=('127.0.0.1', 8000), robot_id='LIMBO-01', mode='ok', delay=1.5):
        super().__init__(address, Handler)
        self.robot_id, self.mode, self.delay = robot_id, mode, delay
        self.lock = threading.Lock()
        self.session, self.sequence, self.latest = None, 0, None
        self.retired = deque(maxlen=100)
        self.received_at = self.received_mono = None
        self.requests = self.accepted = self.bytes_received = self.max_body = 0
        self.history = deque(maxlen=100)

    def accept(self, payload, size):
        with self.lock:
            self.requests += 1
            self.bytes_received += size
            self.max_body = max(self.max_body, size)
            reply = dict(accepted=False, bridge_session_id=payload['bridge_session_id'], sequence=payload['sequence'])
            session = payload['bridge_session_id']
            if session in self.retired:
                return {**reply, 'reason': 'retired_session'}
            if session == self.session and payload['sequence'] <= self.sequence:
                return {**reply, 'reason': 'duplicate_or_out_of_order'}
            if session != self.session and self.session is not None:
                self.retired.append(self.session)
            self.session, self.sequence, self.latest = session, payload['sequence'], payload
            self.received_at, self.received_mono = utc(), time.monotonic()
            self.accepted += 1
            self.history.append({'at': self.received_mono, 'sequence': self.sequence,
                                 'counts': {k: v['received_count'] for k, v in payload['topics'].items()}})
            return {**reply, 'accepted': True, 'server_received_at': self.received_at}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, status, body):
        encoded = json.dumps(body, allow_nan=False).encode()
        try:
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def error(self, status, code, message):
        self.reply(status, {'error': {'code': code, 'message': message}})

    def do_GET(self):
        if self.path != '/status':
            return self.error(404, 'not_found', 'unknown path')
        with self.server.lock:
            self.reply(200, dict(latest=self.server.latest, accepted=self.server.accepted,
                                 bytes_received=self.server.bytes_received, max_body=self.server.max_body,
                                 received_at=self.server.received_at, history=list(self.server.history)))

    def do_POST(self):
        self.connection.settimeout(2)
        if self.path != '/api/v1/telemetry':
            return self.error(404, 'not_found', 'unknown path')
        if self.headers.get_content_type() != 'application/json':
            return self.error(415, 'unsupported_media_type', 'application/json required')
        try:
            size = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            size = -1
        if size > 8192:
            return self.error(413, 'payload_too_large', 'limit is 8192 bytes')
        if size < 0:
            return self.error(400, 'invalid_json', 'Content-Length required')
        try:
            raw = self.rfile.read(size)
            payload = json.loads(raw)
        except (ValueError, UnicodeError, OSError):
            return self.error(400, 'invalid_json', 'invalid JSON')
        try:
            validate(payload)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
            return self.error(422, 'invalid_payload', str(exc))
        if payload['robot_id'] != self.server.robot_id:
            return self.error(409, 'robot_id_mismatch', 'robot_id does not match')
        mode = self.server.mode
        if mode in ('error', 'client_error'):
            return self.error(503 if mode == 'error' else 422,
                              'server_error' if mode == 'error' else 'invalid_payload', 'injected error')
        if mode == 'malformed':
            return self.reply(200, {'unexpected': True})
        if mode == 'oversized':
            return self.reply(200, {'padding': 'x' * 9000})
        if mode == 'retired':
            return self.reply(200, dict(accepted=False, bridge_session_id=payload['bridge_session_id'],
                                       sequence=payload['sequence'], reason='retired_session'))
        reply = self.server.accept(payload, size)
        if mode == 'disconnect':
            self.close_connection = True  # Applied request, lost response.
            return
        if mode == 'delay':
            time.sleep(self.server.delay)
        if mode == 'drip':
            body = json.dumps(reply).encode()
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                for byte in body:
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                    time.sleep(0.05)
            except OSError:
                pass
            return
        self.reply(200, reply)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--robot-id', default='LIMBO-01')
    parser.add_argument('--mode', choices=['ok', 'delay', 'disconnect', 'error', 'client_error',
                                         'malformed', 'oversized', 'retired', 'drip'], default='ok')
    parser.add_argument('--delay', type=float, default=1.5)
    args = parser.parse_args()
    server = Receiver((args.host, args.port), args.robot_id, args.mode, args.delay)
    print(f'test receiver http://{args.host}:{server.server_port} mode={args.mode}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
