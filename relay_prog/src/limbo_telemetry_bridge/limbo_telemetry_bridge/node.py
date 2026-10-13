import argparse
import logging
import math
from pathlib import Path
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from geometry_msgs.msg import PoseWithCovarianceStamped
from limbo_interfaces.msg import PatrolState
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Image, PointCloud2
from std_srvs.srv import Trigger
from .config import load_config
from .state import State
from .transport import Sender


class BridgeNode(Node):
    def __init__(self, config):
        super().__init__('limbo_telemetry_bridge', parameter_overrides=[
            Parameter('use_sim_time', value=config['source_clock'] == 'ros_sim')])
        self.state = State(config['robot_id'], config['source_clock'])
        self.sender = Sender(self.state, config, controller=self)
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
        control = config['control']
        # 순찰 노드가 reliable + transient_local로 내므로 맞춘다 (늦게 붙어도 마지막 상태를 받음)
        patrol_qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=1,
                                reliability=ReliabilityPolicy.RELIABLE,
                                durability=DurabilityPolicy.TRANSIENT_LOCAL)
        # volatile 구독은 volatile·transient_local 발행자 모두와 연결된다
        pose_qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=1,
                              reliability=ReliabilityPolicy.RELIABLE,
                              durability=DurabilityPolicy.VOLATILE)
        self.topic_subscriptions.append(self.create_subscription(
            PatrolState, control['patrol_state_topic'], self._patrol_callback, patrol_qos))
        self.topic_subscriptions.append(self.create_subscription(
            PoseWithCovarianceStamped, control['pose_topic'], self._pose_callback, pose_qos))
        self.patrol_clients = {'pause': self.create_client(Trigger, control['pause_service']),
                         'resume': self.create_client(Trigger, control['resume_service'])}
        self.sender.start()

    def call(self, command):
        """명령 작업(HTTP 스레드)에서 부른다. 서비스가 없으면 기다리지 않고 None."""
        client = self.patrol_clients[command]
        if not client.service_is_ready():
            return None
        return client.call_async(Trigger.Request())

    def _patrol_callback(self, message):
        self.state.receive_patrol(message.state, message.waypoint_index, message.waypoint_count,
                                  message.waypoint_name, message.has_resumable_task, message.reason)

    def _pose_callback(self, message):
        pose = message.pose.pose
        q = pose.orientation
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        covariance = message.pose.covariance
        variance = max(covariance[0], covariance[7])
        std = math.sqrt(variance) if math.isfinite(variance) and variance >= 0 else math.nan
        self.state.receive_pose(message.header.frame_id, pose.position.x, pose.position.y, yaw, std)

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
