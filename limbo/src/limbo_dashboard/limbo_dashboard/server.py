"""ROS subscriptions and a read-only HTTP server for Limbo robots."""

import argparse
import json
import math
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ament_index_python.packages import get_package_share_directory
from diagnostic_msgs.msg import DiagnosticArray
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import OccupancyGrid
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String


DIAGNOSTIC_TIMEOUT = 30.0
ROBOT_ID_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$')


def robot_topic(namespace, name):
    return '/' + '/'.join(part for part in (namespace.strip('/'), name) if part)


def parse_robots(specs, parser):
    robots = []
    ids = set()
    for spec in specs or ['limbo-01:/']:
        if ':' not in spec:
            parser.error('--robot 형식: ID:/ROS_NAMESPACE (예: limbo-02:/limbo_02)')
        robot_id, namespace = spec.split(':', 1)
        if not ROBOT_ID_PATTERN.fullmatch(robot_id) or robot_id in ids:
            parser.error(f'잘못되었거나 중복된 로봇 ID: {robot_id}')
        if namespace not in ('', '/') and not re.fullmatch(r'(?:/[A-Za-z0-9_]+)+/?', namespace):
            parser.error(f'잘못된 ROS namespace: {namespace}')
        ids.add(robot_id)
        robots.append((robot_id, namespace.rstrip('/')))
    return robots


class DashboardNode(Node):
    def __init__(self, robot_configs):
        super().__init__('limbo_dashboard')
        self.lock = threading.Lock()
        self.robot_configs = robot_configs
        self.robots = {
            robot_id: {
                'pose': None, 'pose_seen': None,
                'patrol': None, 'diagnostics': {},
            }
            for robot_id, _ in robot_configs
        }
        self.map_data = None
        self.map_revision = 0

        pose_qos = QoSProfile(depth=1)
        pose_qos.reliability = ReliabilityPolicy.RELIABLE
        pose_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        map_qos = QoSProfile(depth=1)
        map_qos.reliability = ReliabilityPolicy.RELIABLE
        map_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        patrol_qos = QoSProfile(depth=1)
        patrol_qos.reliability = ReliabilityPolicy.RELIABLE
        patrol_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL

        self.create_subscription(OccupancyGrid, '/map', self.on_map, map_qos)
        for robot_id, namespace in robot_configs:
            self.create_subscription(
                PoseWithCovarianceStamped, robot_topic(namespace, 'amcl_pose'),
                lambda msg, rid=robot_id: self.on_pose(rid, msg), pose_qos
            )
            self.create_subscription(
                String, robot_topic(namespace, 'limbo/patrol_status'),
                lambda msg, rid=robot_id: self.on_patrol(rid, msg), patrol_qos
            )
            self.create_subscription(
                DiagnosticArray, robot_topic(namespace, 'diagnostics'),
                lambda msg, rid=robot_id: self.on_diagnostics(rid, msg), 10
            )

    def on_pose(self, robot_id, message):
        p = message.pose.pose.position
        q = message.pose.pose.orientation
        yaw = math.atan2(
            2 * (q.w * q.z + q.x * q.y),
            1 - 2 * (q.y * q.y + q.z * q.z),
        )
        with self.lock:
            self.robots[robot_id]['pose'] = {'x': p.x, 'y': p.y, 'yaw': yaw}
            self.robots[robot_id]['pose_seen'] = time.monotonic()

    def on_map(self, message):
        origin = message.info.origin
        q = origin.orientation
        yaw = math.atan2(
            2 * (q.w * q.z + q.x * q.y),
            1 - 2 * (q.y * q.y + q.z * q.z),
        )
        data = {
            'width': message.info.width,
            'height': message.info.height,
            'resolution': message.info.resolution,
            'origin': {'x': origin.position.x, 'y': origin.position.y, 'yaw': yaw},
            'cells': list(message.data),
        }
        with self.lock:
            self.map_data = data
            self.map_revision += 1

    def on_patrol(self, robot_id, message):
        try:
            value = json.loads(message.data)
            if not isinstance(value, dict) or value.get('state') not in (
                'waiting', 'moving', 'recovering', 'paused', 'completed', 'error'
            ):
                return
            value = {
                'state': value['state'],
                'target': str(value.get('target', ''))[:120],
                'detail': str(value.get('detail', ''))[:500],
            }
        except (ValueError, TypeError):
            self.get_logger().warning(f'Invalid patrol status for {robot_id}')
            return
        with self.lock:
            self.robots[robot_id]['patrol'] = value

    def on_diagnostics(self, robot_id, message):
        now = time.monotonic()
        with self.lock:
            for item in message.status:
                try:
                    level = item.level[0] if isinstance(item.level, bytes) else int(item.level)
                except (ValueError, TypeError, IndexError):
                    self.get_logger().warning('Invalid diagnostic level')
                    continue
                self.robots[robot_id]['diagnostics'][item.name] = {
                    'level': level,
                    'name': item.name,
                    'message': item.message,
                    'seen': now,
                }

    def status(self):
        now = time.monotonic()
        with self.lock:
            snapshots = []
            for robot_id, namespace in self.robot_configs:
                robot = self.robots[robot_id]
                pose_age = None if robot['pose_seen'] is None else now - robot['pose_seen']
                diagnostics = [
                    {key: value[key] for key in ('level', 'name', 'message')}
                    for value in robot['diagnostics'].values()
                    if now - value['seen'] <= DIAGNOSTIC_TIMEOUT and value['level'] >= 1
                ]
                diagnostics.sort(key=lambda item: (-item['level'], item['name']))
                patrol = robot['patrol']
                health = 'error' if (
                    (patrol and patrol['state'] == 'error') or
                    any(item['level'] >= 2 for item in diagnostics)
                ) else 'warning' if diagnostics or (patrol and patrol['state'] == 'recovering') else 'ok' if patrol else 'unknown'
                snapshots.append({
                    'id': robot_id,
                    'pose': robot['pose'],
                    'pose_age': round(pose_age, 1) if pose_age is not None else None,
                    'patrol': patrol,
                    'diagnostics': diagnostics,
                    'health': health,
                    'patrol_topic': robot_topic(namespace, 'limbo/patrol_status'),
                })
            revision = self.map_revision
        for robot in snapshots:
            robot['patrol_online'] = self.count_publishers(robot['patrol_topic']) > 0
            if (robot['health'] == 'ok' and not robot['patrol_online'] and
                    robot['patrol']['state'] not in ('completed', 'error')):
                robot['health'] = 'unknown'
            del robot['patrol_topic']
        return {'robots': snapshots, 'map_revision': revision}

    def map_snapshot(self):
        with self.lock:
            return self.map_data


def handler_for(node, web_file):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/api/status':
                self.send_json(node.status())
            elif self.path == '/api/map':
                data = node.map_snapshot()
                if data is None:
                    self.send_json({'error': 'map unavailable'}, 503)
                else:
                    self.send_json(data)
            elif self.path in ('/', '/index.html'):
                with open(web_file, 'rb') as stream:
                    body = stream.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_error(404)

        def send_json(self, value, code=200):
            body = json.dumps(value, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format_string, *args):
            node.get_logger().debug(format_string % args)

    return Handler


def spin_node(node):
    try:
        rclpy.spin(node)
    except ExternalShutdownException:
        pass


def main(args=None):
    parser = argparse.ArgumentParser(description='Limbo monitoring dashboard')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--robot', action='append', metavar='ID:/NAMESPACE',
                        help='로봇 ID와 ROS namespace. 여러 대는 반복 지정')
    options, ros_args = parser.parse_known_args(args)
    robots = parse_robots(options.robot, parser)
    rclpy.init(args=ros_args)
    node = DashboardNode(robots)
    web_file = os.path.join(
        get_package_share_directory('limbo_dashboard'), 'web', 'index.html'
    )
    worker = threading.Thread(target=spin_node, args=(node,), daemon=True)
    worker.start()
    server = None
    try:
        server = ThreadingHTTPServer(
            (options.host, options.port), handler_for(node, web_file)
        )
        node.get_logger().info(
            f'Dashboard: http://{options.host}:{options.port}'
        )
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if server is not None:
            server.server_close()
        if rclpy.ok():
            rclpy.shutdown()
        worker.join(timeout=2)
        node.destroy_node()


if __name__ == '__main__':
    main()
