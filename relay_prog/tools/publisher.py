#!/usr/bin/env python3
"""Synthetic ROS2 data only; never publishes robot control commands."""
import argparse
from array import array
import json
from pathlib import Path
import time
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Image, PointCloud2, PointField
from rosgraph_msgs.msg import Clock


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--metrics', type=Path, required=True)
    parser.add_argument('--duration', type=float, default=640)
    parser.add_argument('--constant-large', action='store_true', help='fixed large load without fault scenarios')
    args = parser.parse_args()
    rclpy.init()
    node = Node('telemetry_test_publisher')
    qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT,
                     durability=DurabilityPolicy.VOLATILE)
    specs = [('odom', '/odom', Odometry), ('lidar_raw', '/mid360/points', PointCloud2),
             ('lidar_filtered', '/mid360/points_filtered', PointCloud2),
             ('camera_raw', '/rgbd_camera/image', Image)]
    pubs = {k: node.create_publisher(t, name, qos) for k, name, t in specs}
    clock_pub = node.create_publisher(Clock, '/clock', 1)
    messages = {k: t() for k, _, t in specs}
    counts = {k: 0 for k in pubs}
    started = time.monotonic()
    next_at = started
    size_mode = None
    try:
        while rclpy.ok() and time.monotonic()-started < args.duration:
            elapsed = time.monotonic()-started
            large = args.constant_large or elapsed >= 40
            if large != size_mode:
                for key in ('lidar_raw', 'lidar_filtered'):
                    msg = messages[key]
                    msg.height, msg.width, msg.point_step = 1, 65536 if large else 1, 16
                    msg.row_step = msg.width*msg.point_step
                    msg.fields = [PointField(name='x', offset=0, datatype=7, count=1),
                                  PointField(name='y', offset=4, datatype=7, count=1),
                                  PointField(name='z', offset=8, datatype=7, count=1)]
                    msg.data = array('B', [0])*msg.row_step
                msg = messages['camera_raw']
                msg.height, msg.width = (480, 640) if large else (1, 1)
                msg.encoding, msg.step = 'rgb8', msg.width*3
                msg.data = array('B', [0])*(msg.height*msg.step)
                size_mode = large
            # Simulated ROS clock pauses, then jumps backward; wall publication continues.
            ros_seconds = (int(elapsed) if args.constant_large else
                           100 if 45 <= elapsed < 55 else 2 if 55 <= elapsed < 65 else int(elapsed))
            clock = Clock()
            clock.clock.sec = ros_seconds
            clock_pub.publish(clock)
            for key, msg in messages.items():
                if not args.constant_large and ((75 <= elapsed < 85 and key == 'camera_raw') or 100 <= elapsed < 110):
                    continue
                msg.header.stamp.sec = ros_seconds
                if key == 'odom':
                    msg.twist.twist.linear.x = float('nan') if not args.constant_large and 65 <= elapsed < 69 else 0.0
                    msg.twist.twist.angular.z = .75
                pubs[key].publish(msg)
                counts[key] += 1
            if counts['odom'] % 20 == 0:
                args.metrics.write_text(json.dumps(dict(
                    elapsed=elapsed, counts=counts, large=large,
                    matched={k: p.get_subscription_count() for k, p in pubs.items()})))
            rclpy.spin_once(node, timeout_sec=0)
            next_at += .05
            time.sleep(max(0, next_at-time.monotonic()))
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
