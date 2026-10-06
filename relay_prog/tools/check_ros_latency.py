#!/usr/bin/env python3
"""Measure real ROS publish -> HTTP acceptance, including Reliable publisher QoS."""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Image, PointCloud2
import yaml
from receiver import Receiver
from validate_ros import ROOT, stop


def wait_for(predicate, timeout=5):
    deadline = time.monotonic()+timeout
    while time.monotonic()<deadline:
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError('condition did not become true within deadline')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--domain',type=int,default=89)
    parser.add_argument('--output',type=Path,default=ROOT/'docs/ros_latency.json')
    args=parser.parse_args()
    env=dict(os.environ,ROS_DOMAIN_ID=str(args.domain),ROS_LOG_DIR=str(ROOT/'log/latency_ros'),
             PYTHONPATH=str(ROOT/'src/limbo_telemetry_bridge')+os.pathsep+os.environ.get('PYTHONPATH',''))
    os.environ['ROS_LOG_DIR']=env['ROS_LOG_DIR']
    server=Receiver(('127.0.0.1',0))
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    bridge=node=None
    report=dict(domain=args.domain,publisher_qos='reliable/volatile/keep_last/1',rounds=[])
    try:
        with tempfile.TemporaryDirectory(prefix='limbo-latency-') as tmp:
            config=yaml.safe_load((ROOT/'src/limbo_telemetry_bridge/config/bridge.yaml').read_text())
            config['server_url']=f'http://127.0.0.1:{server.server_port}'
            path=Path(tmp)/'config.yaml'
            path.write_text(yaml.safe_dump(config))
            bridge=subprocess.Popen([sys.executable,'-m','limbo_telemetry_bridge.node','--config',str(path)],env=env)
            wait_for(lambda:server.latest is not None)
            report['initial_empty']=all(t['received_count']==0 for t in server.latest['topics'].values())
            rclpy.init(domain_id=args.domain)
            node=Node('telemetry_latency_publisher')
            qos=QoSProfile(depth=1,reliability=ReliabilityPolicy.RELIABLE,durability=DurabilityPolicy.VOLATILE)
            specs=[('odom','/odom',Odometry),('lidar_raw','/mid360/points',PointCloud2),
                   ('lidar_filtered','/mid360/points_filtered',PointCloud2),('camera_raw','/rgbd_camera/image',Image)]
            pubs={key:node.create_publisher(kind,topic,qos) for key,topic,kind in specs}
            wait_for(lambda:all(p.get_subscription_count()==1 for p in pubs.values()))
            for index,(linear,angular) in enumerate([(0.,0.),(0.,.75),(math.nan,0.),(3.,-.5)],1):
                started=time.monotonic()
                for key,_,kind in specs:
                    msg=kind()
                    # Zero and backward ROS headers are independent of this test's monotonic timer.
                    msg.header.stamp.sec=0 if index<3 else -1
                    msg.header.stamp.nanosec=index
                    if key=='odom':
                        msg.twist.twist.linear.x=linear
                        msg.twist.twist.angular.z=angular
                    pubs[key].publish(msg)
                wait_for(lambda:all(t['header_stamp'] is not None and t['header_stamp']['nanosec']==index
                                    for t in server.latest['topics'].values()),timeout=2)
                latency=server.received_mono-started
                motion=server.latest['motion']
                assert motion['linear_speed_mps']==(None if math.isnan(linear) else abs(linear))
                assert motion['angular_velocity_radps']==(None if math.isnan(linear) else angular)
                assert 0<=latency<2
                report['rounds'].append(dict(index=index,publish_to_accept_s=latency,motion=motion))
            report['all_passed']=report['initial_empty'] and len(report['rounds'])==4
    finally:
        stop(bridge)
        if node:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        server.shutdown()
        server.server_close()
        thread.join(2)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
