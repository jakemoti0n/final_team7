"""Real ROS2 publisher -> unchanged Bridge -> FastAPI -> browser integration.

Run using the existing Bridge Python after sourcing Jazzy. An isolated domain is
required explicitly; this tool never publishes control commands.
"""
import argparse
import json
import math
import os
from pathlib import Path
import select
import shutil
import subprocess
import tempfile
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from nav_msgs.msg import Odometry
from sensor_msgs.msg import PointCloud2, Image
import yaml

from harness import ROOT, get, server, stop, wait_for


def read_line(process, timeout=10):
    if not select.select([process.stdout], [], [], timeout)[0]:
        raise AssertionError('browser observer timed out')
    line = process.stdout.readline()
    if not line:
        raise AssertionError('browser observer exited')
    return json.loads(line)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', required=True, type=int)
    parser.add_argument('--node', default=shutil.which('node'))
    args = parser.parse_args()
    if not args.node:
        parser.error('Node.js required; add to PATH or pass --node')
    relay = ROOT.parent / 'relay_prog'
    env = dict(os.environ, ROS_DOMAIN_ID=str(args.domain), ROS_LOG_DIR=str(ROOT / 'artifacts/ros'),
               PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(relay / 'src/limbo_telemetry_bridge') + os.pathsep + os.environ.get('PYTHONPATH', ''))
    os.environ['ROS_LOG_DIR'] = env['ROS_LOG_DIR']
    bridge = browser = node = None
    report = dict(domain=args.domain, input='real ROS2 test publisher', bridge='existing unchanged implementation',
                  publisher_qos='reliable/volatile/keep_last/1', rounds=[])
    try:
        with server() as url, tempfile.TemporaryDirectory(prefix='limbo-dashboard-') as tmp:
            config = yaml.safe_load((relay / 'src/limbo_telemetry_bridge/config/bridge.yaml').read_text())
            config['server_url'] = url
            config_path = Path(tmp) / 'bridge.yaml'
            config_path.write_text(yaml.safe_dump(config))
            with (ROOT / 'artifacts/bridge.log').open('w') as log:
                bridge = subprocess.Popen([str(relay / 'venvs/bridge/bin/python'), '-m', 'limbo_telemetry_bridge.node', '--config', str(config_path)], env=env, stdout=log, stderr=log)
                state = wait_for(lambda: (s if (s := get(url + '/api/v1/state'))['bridge']['status'] == 'connected' else None))
                assert all(t['status'] == 'never_received' for t in state['topics'].values())
                report['initial_empty'] = True
                browser = subprocess.Popen([args.node, str(ROOT / 'tools/observe_ui.mjs'), url], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
                assert read_line(browser)['ready']
                rclpy.init(domain_id=args.domain)
                node = Node('dashboard_integration_publisher')
                qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE)
                specs = [('odom', '/odom', Odometry), ('lidar_raw', '/mid360/points', PointCloud2),
                         ('lidar_filtered', '/mid360/points_filtered', PointCloud2), ('camera_raw', '/rgbd_camera/image', Image)]
                publishers = {key: node.create_publisher(kind, topic, qos) for key, topic, kind in specs}
                wait_for(lambda: all(p.get_subscription_count() >= 1 for p in publishers.values()))
                for index, (linear, angular, movement, retained) in enumerate([(0., 0., '정지 상태', False), (0., -.75, '회전 중', False), (math.nan, 0., '현재 확인 불가', True), (3., -.5, '이동 중', False)], 1):
                    expected = dict(speed='0.00' if index < 4 else '3.00', movement=movement, retained=retained)
                    browser.stdin.write(json.dumps(expected) + '\n'); browser.stdin.flush()
                    started = time.monotonic()
                    for key, _, kind in specs:
                        msg = kind()
                        msg.header.stamp.sec = 0 if index < 3 else -1
                        msg.header.stamp.nanosec = index
                        if key == 'odom':
                            msg.twist.twist.linear.x = linear; msg.twist.twist.angular.z = angular
                        publishers[key].publish(msg)
                    assert read_line(browser, 3)['ok']
                    latency = time.monotonic() - started
                    assert latency < 2
                    state = get(url + '/api/v1/state')
                    assert all(t['status'] == 'receiving' for t in state['topics'].values())
                    assert state['motion']['status'] == ('unknown' if retained else 'stopped' if index == 1 else 'moving')
                    report['rounds'].append(dict(index=index, publish_to_browser_upper_bound_s=latency, motion=state['motion']['status'], retained=retained))
                browser.stdin.write('{"quit":true}\n'); browser.stdin.flush(); browser.wait(5)
                assert browser.returncode == 0
                report['all_passed'] = True
    finally:
        stop(browser); stop(bridge)
        if node: node.destroy_node()
        if rclpy.ok(): rclpy.shutdown()
    (ROOT / 'artifacts/bridge-validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
