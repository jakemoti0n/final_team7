"""Raw encoder odometry for Limbo; deliberately no device, motor or EKF API.

TF odom→base_footprint는 publish_tf=true일 때만 낸다(SLAM·AMCL이 요구). EKF를 쓰게 되면 EKF가 TF를 내야 하므로 끈다.
"""
import math
import signal
import time

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from rcl_interfaces.msg import ParameterDescriptor, SetParametersResult
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from limbo_interfaces.msg import WheelEncoderCounts

from .odometry_core import CountSample, WheelOdometry


class OdometryNode(Node):
    def __init__(self, *, parameter_overrides=None, monotonic=time.monotonic,
                 clock_ns=None):
        super().__init__('wheel_odometry', parameter_overrides=parameter_overrides)
        self._mono = monotonic
        self._clock_ns = clock_ns or (lambda: self.get_clock().now().nanoseconds)
        defaults = {
            'left_wheel_radius': 0.0, 'right_wheel_radius': 0.0,
            'wheel_separation': 0.0,
            'left_counts_per_revolution': 0.0, 'right_counts_per_revolution': 0.0,
            'max_input_age_seconds': 0.5, 'max_sample_interval_seconds': 0.5,
            'max_future_stamp_seconds': 0.05,
            'initial_position_variance': 0.0025, 'initial_yaw_variance': 0.01,
            'position_variance_per_meter': 0.01, 'yaw_variance_per_meter': 0.02,
            'gap_position_variance': 0.25, 'gap_yaw_variance': 0.25,
            'linear_velocity_variance': 0.01, 'lateral_velocity_variance': 0.01,
            'angular_velocity_variance': 0.04, 'unobserved_variance': 1e6,
            'odom_frame': 'odom', 'base_frame': 'base_footprint',
            'input_topic': '/wheel/encoder_counts', 'output_topic': '/odom',
            'publish_tf': False,
        }
        descriptor = ParameterDescriptor(read_only=True)
        self.settings = {key: self.declare_parameter(key, value, descriptor).value
                         for key, value in defaults.items()}
        if self.get_parameter('use_sim_time').value:
            raise ValueError('Physical odometry requires use_sim_time=false')
        self.add_on_set_parameters_callback(self._parameter_change)
        for name in ('odom_frame', 'base_frame', 'input_topic', 'output_topic'):
            if not isinstance(self.settings[name], str) or not self.settings[name].strip():
                raise ValueError(f'{name} must be a nonempty string')
        if (self.settings['odom_frame'] == self.settings['base_frame'] or
                any(self.settings[name].startswith('/') for name in ('odom_frame', 'base_frame'))):
            raise ValueError('Odom/base frames must be distinct and have no leading slash')
        for name in ('linear_velocity_variance', 'lateral_velocity_variance',
                     'angular_velocity_variance', 'unobserved_variance'):
            value = self.settings[name]
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive')
        s = self.settings
        self.core = WheelOdometry(
            left_radius=s['left_wheel_radius'], right_radius=s['right_wheel_radius'],
            separation=s['wheel_separation'], left_cpr=s['left_counts_per_revolution'],
            right_cpr=s['right_counts_per_revolution'],
            max_dt=s['max_sample_interval_seconds'], max_age=s['max_input_age_seconds'],
            future_tolerance=s['max_future_stamp_seconds'],
            initial_position_variance=s['initial_position_variance'],
            initial_yaw_variance=s['initial_yaw_variance'],
            position_variance_per_meter=s['position_variance_per_meter'],
            yaw_variance_per_meter=s['yaw_variance_per_meter'],
            gap_position_variance=s['gap_position_variance'],
            gap_yaw_variance=s['gap_yaw_variance'])
        qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=5,
                         reliability=ReliabilityPolicy.RELIABLE)
        self.odom_pub = self.create_publisher(Odometry, s['output_topic'], qos)
        self.diag_pub = self.create_publisher(DiagnosticArray, '/diagnostics', 5)
        self.tf_broadcaster = None
        if s['publish_tf'] is True:
            from tf2_ros import TransformBroadcaster
            self.tf_broadcaster = TransformBroadcaster(self)
        self.count_sub = self.create_subscription(
            WheelEncoderCounts, s['input_topic'], self._on_counts, qos)
        self.diag_timer = self.create_timer(1.0, self._diagnostics)
        self.last_input_mono = None
        self.last_output_mono = None
        self.output_count = 0
        self.get_logger().info(
            'Raw /odom from verified wheel counts: radii=%s/%s m, separation=%s m, '
            'CPR right=%s left=%s provisional; no TF or motor commands' %
            (s['left_wheel_radius'], s['right_wheel_radius'], s['wheel_separation'],
             s['right_counts_per_revolution'], s['left_counts_per_revolution']))

    @staticmethod
    def _parameter_change(parameters):
        if any(p.name == 'use_sim_time' and p.value for p in parameters):
            return SetParametersResult(successful=False, reason='Physical input requires wall time')
        return SetParametersResult(successful=True)

    def _on_counts(self, msg):
        sample = CountSample(
            msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec,
            msg.session_id, msg.sequence, msg.baseline,
            msg.right_delta, msg.left_delta, msg.right_total, msg.left_total)
        estimate = self.core.update(sample, self._clock_ns())
        now = self._mono()
        if self.core.accepted:
            self.last_input_mono = now
        if estimate is None:
            self._diagnostics()
            return
        odom = Odometry()
        odom.header.stamp = msg.header.stamp
        odom.header.frame_id = self.settings['odom_frame']
        odom.child_frame_id = self.settings['base_frame']
        odom.pose.pose.position.x = estimate.x
        odom.pose.pose.position.y = estimate.y
        odom.pose.pose.orientation.z = math.sin(estimate.yaw / 2.0)
        odom.pose.pose.orientation.w = math.cos(estimate.yaw / 2.0)
        odom.twist.twist.linear.x = estimate.vx
        odom.twist.twist.angular.z = estimate.wz
        pose_covariance = [0.0] * 36
        twist_covariance = [0.0] * 36
        for index in (0, 7):
            pose_covariance[index] = estimate.position_variance
        pose_covariance[35] = estimate.yaw_variance
        twist_covariance[0] = self.settings['linear_velocity_variance']
        twist_covariance[7] = self.settings['lateral_velocity_variance']
        twist_covariance[35] = self.settings['angular_velocity_variance']
        for index in (14, 21, 28):
            pose_covariance[index] = twist_covariance[index] = self.settings['unobserved_variance']
        odom.pose.covariance = pose_covariance
        odom.twist.covariance = twist_covariance
        self.odom_pub.publish(odom)
        if self.tf_broadcaster is not None:
            tf = TransformStamped()
            tf.header = odom.header
            tf.child_frame_id = odom.child_frame_id
            tf.transform.translation.x = estimate.x
            tf.transform.translation.y = estimate.y
            tf.transform.rotation = odom.pose.pose.orientation
            self.tf_broadcaster.sendTransform(tf)
        self.last_output_mono = now
        self.output_count += 1

    def _diagnostics(self):
        if not self.context.ok():
            return
        now = self._mono()
        input_age = None if self.last_input_mono is None else now - self.last_input_mono
        output_age = None if self.last_output_mono is None else now - self.last_output_mono
        if input_age is not None and input_age > self.settings['max_input_age_seconds']:
            self.core.invalidate('stale_input')
        status = DiagnosticStatus()
        status.name = 'limbo/wheel_odometry'
        status.hardware_id = 'wheel_encoder_counts'
        if input_age is None or input_age > self.settings['max_input_age_seconds']:
            status.level = DiagnosticStatus.ERROR
        elif self.core.status != 'integrated':
            status.level = DiagnosticStatus.WARN
        else:
            status.level = DiagnosticStatus.OK
        status.message = self.core.status
        values = {
            'source_topic': self.settings['input_topic'],
            'output_topic': self.settings['output_topic'],
            'session_id': self.core.reference.session_id if self.core.reference else '',
            'last_input_age_seconds': input_age, 'last_output_age_seconds': output_age,
            'integrated_intervals': self.core.integrated_intervals,
            'output_count': self.output_count, 'rebases': self.core.rebases,
            'rejected_samples': self.core.rejected,
            'left_wheel_radius': self.settings['left_wheel_radius'],
            'right_wheel_radius': self.settings['right_wheel_radius'],
            'wheel_separation': self.settings['wheel_separation'],
            'left_counts_per_revolution': self.settings['left_counts_per_revolution'],
            'right_counts_per_revolution': self.settings['right_counts_per_revolution'],
            'calibration': 'provisional', 'covariance': 'provisional_diagonal_budget',
            'stamp_source': 'encoder_host_ros_receive_time',
            'twist_interval_source': 'successive_encoder_header_stamps',
            'tf_published': self.tf_broadcaster is not None, 'motor_commands_enabled': False,
            'discontinuity_policy': 'preserve_pose_skip_unobserved_motion',
        }
        status.values = [KeyValue(key=str(key), value=str(value)) for key, value in values.items()]
        message = DiagnosticArray()
        message.header.stamp = self.get_clock().now().to_msg()
        message.status = [status]
        self.diag_pub.publish(message)


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = OdometryNode()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
