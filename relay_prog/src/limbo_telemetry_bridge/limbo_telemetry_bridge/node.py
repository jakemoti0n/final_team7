import argparse
import logging
from pathlib import Path
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Image, PointCloud2
from .config import load_config
from .state import State
from .transport import Sender


class BridgeNode(Node):
    def __init__(self, config):
        super().__init__('limbo_telemetry_bridge', parameter_overrides=[
            Parameter('use_sim_time', value=config['source_clock'] == 'ros_sim')])
        self.state = State(config['robot_id'], config['source_clock'])
        self.sender = Sender(self.state, config)
        types = {'odom': Odometry, 'lidar_raw': PointCloud2,
                 'lidar_filtered': PointCloud2, 'camera_raw': Image}
        self.topic_subscriptions = []
        for key, topic in config['topics'].items():
            qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST, depth=topic['depth'],
                reliability=ReliabilityPolicy.BEST_EFFORT if topic['reliability'] == 'best_effort'
                else ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.VOLATILE if topic['durability'] == 'volatile'
                else DurabilityPolicy.TRANSIENT_LOCAL)
            self.topic_subscriptions.append(self.create_subscription(
                types[key], topic['name'], self._callback(key), qos))
        self.sender.start()

    def _callback(self, key):
        def callback(message):
            stamp = message.header.stamp
            velocity = None
            if key == 'odom':
                twist = message.twist.twist
                velocity = (twist.linear.x, twist.linear.y, twist.angular.z)
            self.state.receive(key, stamp.sec, stamp.nanosec, velocity)
        return callback

    def destroy_node(self):
        self.sender.stop()
        return super().destroy_node()


def main(args=None):
    parser = argparse.ArgumentParser(description='LIMBO metadata telemetry bridge')
    parser.add_argument('--config', type=Path, required=True)
    parsed, ros_args = parser.parse_known_args(args)
    config = load_config(parsed.config)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    rclpy.init(args=ros_args)
    node = None
    try:
        node = BridgeNode(config)
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
