#!/usr/bin/env python3
"""Independent stdlib-only test receiver (텔레메트리 v1·v2, 관제 명령 API). No ROS or bridge imports."""
import argparse
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import threading
import time
from urllib.parse import parse_qs, urlsplit
import uuid

KEYS = {'odom', 'lidar_raw', 'lidar_filtered', 'camera_raw'}
PATROL_STATES = {'waiting_localization', 'patrolling', 'pausing', 'paused', 'completed', 'failed'}
FOLLOW_STATES = {'idle', 'following', 'holding', 'stopped'}
OUTCOMES = {'accepted', 'rejected', 'no_response', 'service_unavailable', 'expired'}


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
    if not isinstance(payload, dict) or type(payload.get('schema_version')) is not int:
        raise ValueError('unsupported schema_version')
    version = payload['schema_version']
    if version not in (1, 2):
        raise ValueError('unsupported schema_version')
    base = 'schema_version robot_id bridge_session_id sequence sent_at source_clock topics motion'
    if version == 2 and 'follow' in payload:          # v2 선택 필드 (따라가기 3단계)
        fields(payload, base + ' patrol pose follow')
    else:
        fields(payload, base + (' patrol pose' if version == 2 else ''))
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
    if version == 2:
        validate_patrol(payload['patrol'])
        validate_pose(payload['pose'])
        if 'follow' in payload:
            validate_follow(payload['follow'])
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


def validate_patrol(patrol):
    fields(patrol, 'state waypoint_index waypoint_count waypoint_name has_resumable_task reason '
                   'update_count last_received_at age_ms')
    number(patrol['update_count'], 0, True)
    content = ('state', 'waypoint_index', 'waypoint_count', 'waypoint_name', 'has_resumable_task', 'reason')
    if patrol['update_count'] == 0:
        if any(patrol[k] is not None for k in (*content, 'last_received_at', 'age_ms')):
            raise ValueError('unreceived patrol must be null')
        return
    timestamp(patrol['last_received_at'])
    number(patrol['age_ms'], 0)
    if all(patrol[k] is None for k in content):
        return  # 받았지만 알 수 없는 상태
    if patrol['state'] not in PATROL_STATES:
        raise ValueError('invalid patrol state')
    number(patrol['waypoint_index'], 0, True)
    number(patrol['waypoint_count'], 0, True)
    if type(patrol['has_resumable_task']) is not bool:
        raise ValueError('invalid has_resumable_task')
    for key in ('waypoint_name', 'reason'):
        if not isinstance(patrol[key], str) or len(patrol[key]) > 200:
            raise ValueError('invalid ' + key)


def validate_follow(follow):
    fields(follow, 'state active enrolled visible target_id distance_m reason elapsed_s lost_s '
                   'update_count last_received_at age_ms')
    number(follow['update_count'], 0, True)
    content = ('state', 'active', 'enrolled', 'visible', 'target_id', 'distance_m', 'reason', 'elapsed_s', 'lost_s')
    if follow['update_count'] == 0:
        if any(follow[k] is not None for k in (*content, 'last_received_at', 'age_ms')):
            raise ValueError('unreceived follow must be null')
        return
    timestamp(follow['last_received_at'])
    number(follow['age_ms'], 0)
    if all(follow[k] is None for k in content):
        return  # 받았지만 알 수 없는 상태
    if follow['state'] not in FOLLOW_STATES:
        raise ValueError('invalid follow state')
    for key in ('active', 'enrolled', 'visible'):
        if type(follow[key]) is not bool:
            raise ValueError('invalid ' + key)
    number(follow['target_id'], None, True)
    for key in ('distance_m', 'elapsed_s', 'lost_s'):
        number(follow[key], 0)
    if not isinstance(follow['reason'], str) or len(follow['reason']) > 200:
        raise ValueError('invalid reason')


def validate_pose(pose):
    fields(pose, 'frame_id x y yaw position_std_m last_received_at age_ms')
    if all(v is None for v in pose.values()):
        return
    if not isinstance(pose['frame_id'], str) or not pose['frame_id']:
        raise ValueError('invalid frame_id')
    for key in ('x', 'y', 'yaw'):
        number(pose[key])
    if abs(pose['yaw']) > math.pi + 1e-9:
        raise ValueError('yaw out of range')
    number(pose['position_std_m'], 0)
    timestamp(pose['last_received_at'])
    number(pose['age_ms'], 0)


def validate_result(result, request_id):
    fields(result, 'robot_id bridge_session_id request_id outcome message service_latency_ms '
                   'patrol_update_count_at_call follow_update_count_at_call')
    if result['request_id'] != request_id or result['outcome'] not in OUTCOMES:
        raise ValueError('invalid result')
    if not isinstance(result['message'], str) or len(result['message']) > 200:
        raise ValueError('invalid message')
    number(result['patrol_update_count_at_call'], 0, True)
    number(result['follow_update_count_at_call'], 0, True)
    if result['outcome'] in ('accepted', 'rejected'):
        number(result['service_latency_ms'], 0)
    elif result['service_latency_ms'] is not None:
        raise ValueError('latency only for answered calls')


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
        # 관제 명령 흉내: 대기열 길이 1, 한 번만 내줌, 결과는 한 번만 받음
        self.command_ready = threading.Condition(self.lock)
        self.pending = None          # (request_id, command, 발급 단조 시각, ttl 초)
        self.delivered = {}          # request_id -> 명령
        self.results = {}            # request_id -> 결과
        self.command_mode = 'ok'     # ok | error (commands/next가 503)
        self.claim_mode = 'ok'       # ok | refuse (409) | slow (1.5초 뒤 허락)
        self.claimed = set()

    def enqueue(self, command, ttl_s=5.0):
        with self.lock:
            request_id = str(uuid.uuid4())
            self.pending = (request_id, command, time.monotonic(), ttl_s)
            self.command_ready.notify_all()
            return request_id

    def next_command(self, wait_s):
        deadline = time.monotonic() + wait_s
        with self.lock:
            while self.pending is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self.command_ready.wait(remaining)
            request_id, command, issued, ttl = self.pending
            self.pending = None
            self.delivered[request_id] = command
            ttl_ms = max(0.0, (issued + ttl - time.monotonic()) * 1000)
            return dict(request_id=request_id, command=command, ttl_ms=ttl_ms)

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
        if self.path.startswith('/api/v1/commands/next'):
            return self.commands_next()
        if self.path != '/status':
            return self.error(404, 'not_found', 'unknown path')
        with self.server.lock:
            self.reply(200, dict(latest=self.server.latest, accepted=self.server.accepted,
                                 bytes_received=self.server.bytes_received, max_body=self.server.max_body,
                                 received_at=self.server.received_at, history=list(self.server.history),
                                 results=self.server.results))

    def commands_next(self):
        query = parse_qs(urlsplit(self.path).query)
        if query.get('robot_id', [''])[0] != self.server.robot_id:
            return self.error(409, 'robot_id_mismatch', 'robot_id does not match')
        if self.server.command_mode == 'error':
            return self.error(503, 'server_error', 'injected error')
        try:
            wait_s = min(10.0, max(0.0, float(query.get('wait_s', ['0'])[0])))
        except ValueError:
            return self.error(422, 'invalid_payload', 'wait_s')
        command = self.server.next_command(wait_s)
        if command is None:
            try:
                self.send_response(204)
                self.end_headers()
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        self.reply(200, command)

    def read_json(self):
        size = int(self.headers.get('Content-Length', '-1'))
        if not 0 <= size <= 8192:
            raise ValueError('invalid size')
        return json.loads(self.rfile.read(size))

    def commands_claim(self):
        request_id = self.path[len('/api/v1/commands/'):-len('/claim')]
        body = self.read_json()
        if not isinstance(body, dict) or set(body) != {'robot_id', 'bridge_session_id'}:
            return self.error(422, 'invalid_payload', 'robot_id and bridge_session_id')
        if self.server.claim_mode == 'slow':
            time.sleep(1.5)
        with self.server.lock:
            ok = (self.server.claim_mode != 'refuse' and request_id in self.server.delivered
                  and request_id not in self.server.claimed and request_id not in self.server.results)
            if ok:
                self.server.claimed.add(request_id)
        if not ok:
            return self.error(409, 'command_closed', 'command is no longer valid')
        return self.reply(200, {'claimed': True})

    def commands_post(self):
        if self.path.endswith('/claim'):
            return self.commands_claim()
        if self.path == '/api/v1/commands':
            body = self.read_json()
            if not isinstance(body, dict) or set(body) != {'command'} or body['command'] not in ('pause', 'resume'):
                return self.error(422, 'invalid_command', 'pause or resume')
            return self.reply(202, dict(request_id=self.server.enqueue(body['command']),
                                        command=body['command'], stage='queued'))
        request_id = self.path[len('/api/v1/commands/'):-len('/result')]
        result = self.read_json()
        with self.server.lock:
            if request_id not in self.server.delivered or request_id in self.server.results:
                return self.reply(200, {'accepted': False, 'reason': 'command_closed'})
            validate_result(result, request_id)
            self.server.results[request_id] = result
        return self.reply(200, {'accepted': True})

    def do_POST(self):
        self.connection.settimeout(2)
        if self.path == '/api/v1/commands' or (self.path.startswith('/api/v1/commands/')
                                              and self.path.endswith(('/result', '/claim'))):
            try:
                return self.commands_post()
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                return self.error(422, 'invalid_payload', str(exc))
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
