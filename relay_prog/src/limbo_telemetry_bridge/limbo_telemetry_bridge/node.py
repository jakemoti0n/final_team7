import argparse
import logging
import math
from pathlib import Path
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.time import Time
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from geometry_msgs.msg import PoseWithCovarianceStamped
from limbo_interfaces.msg import FollowState, PatrolState
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Image, PointCloud2
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformException, TransformListener
from .config import load_config
from .state import State
from .transport import Sender

# 위치는 TF(map → base)로 읽는다. /amcl_pose는 로봇이 움직일 때만 나와서 멈춰 있으면 끊기기 때문
# (docs/CONTROL_SCREEN.md B). /amcl_pose는 위치 불확실성(공분산)만 쓴다
POSE_PERIOD_S = 0.5
POSE_MAX_AGE_S = 1.0   # 이보다 오래된 TF(오도메트리 끊김)면 위치를 갱신하지 않는다 → 서버가 stale로 봄


def yaw_of(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


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
        # AMCL(Nav2)은 /amcl_pose를 transient_local로 낸다. 맞춰야 Bridge를 나중에 켜도 마지막 불확실성을 받음
        # (volatile이면 로봇이 움직여 AMCL이 다시 낼 때까지 위치를 못 보냄)
        pose_qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=1,
                              reliability=ReliabilityPolicy.RELIABLE,
                              durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.topic_subscriptions.append(self.create_subscription(
            PatrolState, control['patrol_state_topic'], self._patrol_callback, patrol_qos))
        self.topic_subscriptions.append(self.create_subscription(
            PoseWithCovarianceStamped, control['pose_topic'], self._pose_callback, pose_qos))
        self.map_frame, self.base_frame = control['map_frame'], control['base_frame']
        self.position_std = None
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.pose_timer = self.create_timer(POSE_PERIOD_S, self._read_pose)
        self.patrol_topic = control['patrol_state_topic']
        self.patrol_timer = self.create_timer(POSE_PERIOD_S, self._check_patrol_publisher)
        # 따라가기 상태(5 Hz, reliable·volatile)와 서비스 (PROJECT.md 2-9 3단계)
        self.follow_topic = control['follow_state_topic']
        self.topic_subscriptions.append(self.create_subscription(
            FollowState, self.follow_topic, self._follow_callback,
            QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=1, reliability=ReliabilityPolicy.RELIABLE,
                       durability=DurabilityPolicy.VOLATILE)))
        self.follow_timer = self.create_timer(POSE_PERIOD_S, self._check_follow_publisher)
        self.service_clients = {'pause': self.create_client(Trigger, control['pause_service']),
                                'resume': self.create_client(Trigger, control['resume_service']),
                                'follow_start': self.create_client(Trigger, control['follow_start_service']),
                                'follow_stop': self.create_client(Trigger, control['follow_stop_service']),
                                'follow_enroll': self.create_client(Trigger, control['follow_enroll_service'])}
        self.sender.start()

    def call(self, command):
        """명령 작업(HTTP 스레드)에서 부른다. 서비스가 없으면 기다리지 않고 None."""
        client = self.service_clients[command]
        if not client.service_is_ready():
            return None
        return client.call_async(Trigger.Request())

    def _check_patrol_publisher(self):
        self.state.patrol_publisher(self.count_publishers(self.patrol_topic) > 0)

    def _check_follow_publisher(self):
        self.state.follow_publisher(self.count_publishers(self.follow_topic) > 0)

    def _follow_callback(self, message):
        self.state.receive_follow(message.state, message.active, message.enrolled, message.visible,
                                  message.target_id, message.distance, message.reason,
                                  message.elapsed_sec, message.lost_sec)

    def _patrol_callback(self, message):
        self.state.receive_patrol(message.state, message.waypoint_index, message.waypoint_count,
                                  message.waypoint_name, message.has_resumable_task, message.reason)

    def _pose_callback(self, message):
        covariance = message.pose.covariance
        variance = max(covariance[0], covariance[7])
        self.position_std = math.sqrt(variance) if math.isfinite(variance) and variance >= 0 else None

    def _read_pose(self):
        """불확실성을 한 번이라도 받은 뒤(AMCL이 위치를 잡은 뒤)부터, 최신 TF가 1초 안 것일 때만 보낸다."""
        if self.position_std is None:
            return
        try:
            transform = self.tf_buffer.lookup_transform(self.map_frame, self.base_frame, Time())
        except TransformException:
            return
        now = self.get_clock().now()
        age = (now - Time.from_msg(transform.header.stamp, clock_type=now.clock_type)).nanoseconds / 1e9
        if age > POSE_MAX_AGE_S:
            return
        t = transform.transform
        self.state.receive_pose(self.map_frame, t.translation.x, t.translation.y, yaw_of(t.rotation),
                                self.position_std)

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
