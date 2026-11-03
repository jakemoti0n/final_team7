"""Observe differential-drive targets and wheel feedback without any actuation API."""
import math
import signal
import time

import rclpy
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from geometry_msgs.msg import Twist
from rcl_interfaces.msg import ParameterDescriptor, SetParametersResult
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState

from .drive_preview_core import calculate_drive_targets


class DrivePreviewNode(Node):
    JOINT_NAMES = ('left_wheel_joint', 'right_wheel_joint')

    def __init__(self, *, parameter_overrides=None, monotonic=time.monotonic,
                 clock_ns=None):
        super().__init__('drive_preview', parameter_overrides=parameter_overrides)
        self._mono = monotonic
        self._clock_ns = clock_ns or (lambda: self.get_clock().now().nanoseconds)
        defaults = {
            'left_wheel_radius': 0.0, 'right_wheel_radius': 0.0,
            'wheel_separation': 0.0, 'left_counts_per_revolution': 0.0,
            'right_counts_per_revolution': 0.0,
            'max_feedback_age_seconds': 0.5, 'max_target_age_seconds': 0.5,
            'max_future_stamp_seconds': 0.05, 'base_frame': 'base_footprint',
            'command_topic': '/limbo/drive_preview/cmd_vel',
            'feedback_topic': '/wheel/joint_states',
            'target_topic': '/limbo/drive_preview/target_joint_states',
            'status_topic': '/limbo/drive_preview/status',
        }
        descriptor = ParameterDescriptor(read_only=True)
        self.settings = {key: self.declare_parameter(key, value, descriptor).value
                         for key, value in defaults.items()}
        if self.get_parameter('use_sim_time').value:
            raise ValueError('Physical feedback requires use_sim_time=false')
        self.add_on_set_parameters_callback(self._parameter_change)
        for key, value in self.settings.items():
            if isinstance(defaults[key], float):
                if not math.isfinite(value) or value <= 0:
                    raise ValueError(f'{key} must be finite and positive')
            elif not isinstance(value, str) or not value.strip():
                raise ValueError(f'{key} must be a nonempty string')
        if self.settings['base_frame'].startswith('/'):
            raise ValueError('base_frame must have no leading slash')
        # Resolve remapping too: a preview publisher must never occupy /cmd_vel.
        for key in ('target_topic', 'status_topic'):
            if self.resolve_topic_name(self.settings[key]) == '/cmd_vel':
                raise ValueError('Preview outputs must not use /cmd_vel')
        if (self.resolve_topic_name(self.settings['target_topic']) ==
                self.resolve_topic_name(self.settings['feedback_topic'])):
            raise ValueError('target_topic must differ from feedback_topic')
        self.targets = None
        self.target_sequence = 0
        self.requested = None
        self.target_received_mono = None
        self.feedback_received_mono = None
        self.feedback_stamp_ns = None
        self.actual = None
        self.command_result = 'absent'
        self.feedback_result = 'absent'
        self.accepted_commands = self.rejected_commands = 0
        self.accepted_feedback = self.rejected_feedback = 0
        self.target_pub = self.create_publisher(JointState, self.settings['target_topic'], 5)
        self.diag_pub = self.create_publisher(DiagnosticArray, self.settings['status_topic'], 5)
        self.command_sub = self.create_subscription(
            Twist, self.settings['command_topic'], self._on_command, 5)
        self.feedback_sub = self.create_subscription(
            JointState, self.settings['feedback_topic'], self._on_feedback,
            qos_profile_sensor_data)
        self.diag_timer = self.create_timer(1.0, self._diagnostics)
        self.get_logger().info(
            'Drive preview only: one target per valid Twist; motor output disabled; '
            'wheel differences are observations, not tracking-performance measurements')

    @staticmethod
    def _parameter_change(parameters):
        if any(p.name == 'use_sim_time' for p in parameters):
            return SetParametersResult(successful=False, reason='use_sim_time is immutable')
        return SetParametersResult(successful=True)

    def _calculate(self, linear, angular):
        s = self.settings
        return calculate_drive_targets(
            linear, angular, left_radius_m=s['left_wheel_radius'],
            right_radius_m=s['right_wheel_radius'],
            wheel_separation_m=s['wheel_separation'],
            left_counts_per_revolution=s['left_counts_per_revolution'],
            right_counts_per_revolution=s['right_counts_per_revolution'])

    def _on_command(self, msg):
        received_mono, received_ns = self._mono(), self._clock_ns()
        self.requested = tuple(value if math.isfinite(value) else None
                               for value in (msg.linear.x, msg.angular.z))
        values = (msg.linear.x, msg.linear.y, msg.linear.z,
                  msg.angular.x, msg.angular.y, msg.angular.z)
        reason = None
        if not all(math.isfinite(value) for value in values):
            reason = 'nonfinite_twist'
        elif any(value != 0.0 for value in (msg.linear.y, msg.linear.z,
                                          msg.angular.x, msg.angular.y)):
            reason = 'unsupported_twist_axes'
        else:
            try:
                targets = self._calculate(msg.linear.x, msg.angular.z)
            except (ValueError, OverflowError):
                reason = 'nonfinite_target'
        if reason:
            self.rejected_commands += 1
            self.command_result = reason
            return
        target_msg = JointState()
        target_msg.header.stamp.sec, target_msg.header.stamp.nanosec = divmod(
            received_ns, 1_000_000_000)
        target_msg.header.frame_id = self.settings['base_frame']
        target_msg.name = list(self.JOINT_NAMES)
        target_msg.velocity = [targets.left.angular_rad_s, targets.right.angular_rad_s]
        # Position and effort deliberately remain empty: neither is a target here.
        self.target_pub.publish(target_msg)
        self.targets = targets
        self.target_received_mono = received_mono
        self.target_sequence += 1
        self.accepted_commands += 1
        self.command_result = 'accepted'

    def _on_feedback(self, msg):
        self.feedback_received_mono = self._mono()
        self.actual = None
        self.feedback_stamp_ns = None
        reason = None
        names = list(msg.name)
        if len(set(names)) != len(names):
            reason = 'duplicate_joint_names'
        elif any(name not in names for name in self.JOINT_NAMES):
            reason = 'missing_wheel_joints'
        elif len(msg.velocity) != len(names) or any(
                len(values) not in (0, len(names)) for values in (msg.position, msg.effort)):
            reason = 'invalid_joint_array_lengths'
        elif not all(math.isfinite(value) for values in
                     (msg.velocity, msg.position, msg.effort) for value in values):
            reason = 'nonfinite_joint_values'
        else:
            stamp_ns = msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec
            age = (self._clock_ns() - stamp_ns) / 1e9
            if (stamp_ns <= 0 or msg.header.stamp.sec < 0 or
                    msg.header.stamp.nanosec >= 1_000_000_000):
                reason = 'invalid_feedback_stamp'
            else:
                self.feedback_stamp_ns = stamp_ns
                if age < -self.settings['max_future_stamp_seconds']:
                    reason = 'future_feedback_stamp'
                elif age > self.settings['max_feedback_age_seconds']:
                    reason = 'stale_feedback'
            if reason is None:
                velocities = tuple(msg.velocity[names.index(name)] for name in self.JOINT_NAMES)
                counts = tuple(velocity * (self.settings[f'{side}_counts_per_revolution'] /
                                           (2.0 * math.pi))
                               for side, velocity in zip(('left', 'right'), velocities))
                if not all(math.isfinite(value) for value in counts):
                    reason = 'nonfinite_feedback_counts'
                else:
                    self.actual = (velocities, counts)
        if reason:
            self.rejected_feedback += 1
            self.feedback_result = reason
        else:
            self.accepted_feedback += 1
            self.feedback_result = 'accepted'

    def _diagnostics(self):
        if not self.context.ok():
            return
        now, now_ns = self._mono(), self._clock_ns()
        target_age = None if self.target_received_mono is None else now - self.target_received_mono
        feedback_age = (None if self.feedback_received_mono is None
                        else now - self.feedback_received_mono)
        source_age = (None if self.feedback_stamp_ns is None
                      else (now_ns - self.feedback_stamp_ns) / 1e9)
        target_state = ('absent' if target_age is None else 'fresh'
                        if 0 <= target_age <= self.settings['max_target_age_seconds'] else 'stale')
        if self.targets is not None and self.command_result != 'accepted':
            target_state = 'invalidated'
        actual_state = 'absent' if feedback_age is None else 'invalid'
        if self.feedback_result == 'stale_feedback':
            actual_state = 'stale'
        if self.actual is not None:
            if (0 <= feedback_age <= self.settings['max_feedback_age_seconds'] and
                    -self.settings['max_future_stamp_seconds'] <= source_age <=
                    self.settings['max_feedback_age_seconds']):
                actual_state = 'fresh'
            else:
                actual_state = 'stale'
        comparable = target_state == 'fresh' and actual_state == 'fresh'
        status = DiagnosticStatus()
        status.name, status.hardware_id = 'limbo/drive_preview', 'no_actuation'
        status.level = DiagnosticStatus.OK if comparable else DiagnosticStatus.WARN
        status.message = ('preview_only; observational comparison available' if comparable else
                          f'preview_only; comparison unavailable (target={target_state}, '
                          f'actual={actual_state})')
        values = {
            'mode': 'preview_only', 'motor_output_enabled': False,
            'comparison_available': comparable,
            'comparison_meaning': 'node_does_not_actuate',
            'tracking_performance': 'not_measured',
            'error_convention': 'actual_minus_target',
            'count_sign_convention': 'normalized_forward_positive',
            'target_stamp_source': 'host_ros_twist_receipt_time',
            'target_sequence': self.target_sequence, 'target_state': target_state,
            'target_data_meaning': 'last_valid_command_historical_when_not_fresh',
            'requested_data_meaning': 'latest_command_attempt',
            'actual_state': actual_state, 'target_age_seconds': target_age,
            'feedback_receipt_age_seconds': feedback_age, 'feedback_source_age_seconds': source_age,
            'command_result': self.command_result, 'feedback_result': self.feedback_result,
            'accepted_commands': self.accepted_commands, 'rejected_commands': self.rejected_commands,
            'accepted_feedback': self.accepted_feedback, 'rejected_feedback': self.rejected_feedback,
            'requested_linear_m_s': None if self.requested is None else self.requested[0],
            'requested_angular_rad_s': None if self.requested is None else self.requested[1],
            **self.settings,
        }
        for index, side in enumerate(('left', 'right')):
            target = None if self.targets is None else getattr(self.targets, side)
            for field in ('linear_m_s', 'angular_rad_s', 'counts_per_s'):
                values[f'target_{side}_{field}'] = None if target is None else getattr(target, field)
            for offset, field in enumerate(('angular_rad_s', 'counts_per_s')):
                actual = self.actual[offset][index] if actual_state == 'fresh' else None
                values[f'actual_{side}_{field}'] = actual
                error = actual - getattr(target, field) if comparable else None
                values[f'error_{side}_{field}'] = (
                    error if error is not None and math.isfinite(error) else None)
        def as_text(value):
            if value is None:
                return 'unavailable'
            return str(value).lower() if isinstance(value, bool) else str(value)
        status.values = [KeyValue(key=key, value=as_text(value)) for key, value in values.items()]
        message = DiagnosticArray()
        message.header.stamp.sec, message.header.stamp.nanosec = divmod(now_ns, 1_000_000_000)
        message.status = [status]
        self.diag_pub.publish(message)


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = DrivePreviewNode()
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
