"""ROS adapter tests with synthetic commands/feedback and no hardware access."""
import math
import unittest
from unittest.mock import Mock

import rclpy
from diagnostic_msgs.msg import DiagnosticStatus
from geometry_msgs.msg import Twist
from rclpy.parameter import Parameter
from sensor_msgs.msg import JointState

from limbo_hardware.drive_preview_node import DrivePreviewNode


class DrivePreviewNodeTests(unittest.TestCase):
    def setUp(self):
        rclpy.init()
        self.now, self.now_ns = 10.0, 10_000_000_000
        self.parameters = {
            'left_wheel_radius': .075, 'right_wheel_radius': .075,
            'wheel_separation': .54, 'left_counts_per_revolution': 3688.0,
            'right_counts_per_revolution': 3607.0,
        }
        self.node = DrivePreviewNode(
            parameter_overrides=[Parameter(k, value=v) for k, v in self.parameters.items()],
            monotonic=lambda: self.now, clock_ns=lambda: self.now_ns)
        self.original_target_topic = self.node.target_pub.topic_name
        self.original_status_topic = self.node.diag_pub.topic_name
        self.node.target_pub, self.node.diag_pub = Mock(), Mock()

    def tearDown(self):
        self.node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

    @staticmethod
    def command(linear=.15, angular=0.0):
        msg = Twist()
        msg.linear.x, msg.angular.z = linear, angular
        return msg

    def feedback(self, left=1.0, right=2.0, stamp_ns=None):
        msg = JointState()
        # Reverse order deliberately, as used by the existing encoder publisher.
        msg.name, msg.velocity = ['right_wheel_joint', 'left_wheel_joint'], [right, left]
        stamp_ns = self.now_ns if stamp_ns is None else stamp_ns
        msg.header.stamp.sec, msg.header.stamp.nanosec = divmod(stamp_ns, 1_000_000_000)
        return msg

    def diagnostic(self):
        self.node._diagnostics()
        status = self.node.diag_pub.publish.call_args.args[0].status[0]
        return status, {item.key: item.value for item in status.values}

    def test_one_target_per_valid_command_receipt_stamp_and_no_replay(self):
        self.node._on_command(self.command(.15, .2))
        target = self.node.target_pub.publish.call_args.args[0]
        self.assertEqual(target.name, ['left_wheel_joint', 'right_wheel_joint'])
        self.assertEqual(target.header.frame_id, 'base_footprint')
        self.assertEqual(target.header.stamp.sec, 10)
        self.assertEqual(target.header.stamp.nanosec, 0)
        self.assertEqual(list(target.position), [])
        self.assertEqual(list(target.effort), [])
        self.assertAlmostEqual(target.velocity[0], (.15 - .2*.54/2)/.075)
        self.assertAlmostEqual(target.velocity[1], (.15 + .2*.54/2)/.075)
        self.node._diagnostics()
        self.now += 2.0
        self.now_ns += 2_000_000_000
        self.node._diagnostics()
        self.assertEqual(self.node.target_pub.publish.call_count, 1)
        self.node._on_command(self.command(0.0, 0.0))
        self.assertEqual(self.node.target_pub.publish.call_count, 2)
        self.assertEqual(list(self.node.target_pub.publish.call_args.args[0].velocity), [0.0, 0.0])
        self.assertEqual(self.node.target_sequence, 2)

    def test_nonfinite_components_and_unsupported_axes_never_publish(self):
        for component in ('linear', 'angular'):
            for axis in ('x', 'y', 'z'):
                for value in (math.nan, math.inf, -math.inf):
                    with self.subTest(component=component, axis=axis, value=value):
                        msg = self.command()
                        setattr(getattr(msg, component), axis, value)
                        self.node._on_command(msg)
                        self.assertEqual(self.node.command_result, 'nonfinite_twist')
        for component, axis in (('linear', 'y'), ('linear', 'z'),
                                ('angular', 'x'), ('angular', 'y')):
            msg = self.command()
            setattr(getattr(msg, component), axis, .001)
            self.node._on_command(msg)
            self.assertEqual(self.node.command_result, 'unsupported_twist_axes')
        self.node._on_command(self.command(1e308, 1e308))
        self.assertEqual(self.node.command_result, 'nonfinite_target')
        self.node.target_pub.publish.assert_not_called()
        self.assertEqual(self.node.rejected_commands, 23)
        self.assertEqual(self.node.target_sequence, 0)

    def test_named_feedback_mapping_counts_and_observational_error(self):
        self.node._on_command(self.command(.15, 0.0))
        msg = self.feedback(left=1.0, right=3.0)
        msg.name.append('extra_joint')
        msg.velocity.append(0.0)
        self.node._on_feedback(msg)
        status, values = self.diagnostic()
        self.assertEqual(status.level, DiagnosticStatus.OK)
        self.assertEqual(values['comparison_available'], 'true')
        self.assertEqual(values['error_convention'], 'actual_minus_target')
        self.assertEqual(values['target_sequence'], '1')
        self.assertEqual(values['requested_linear_m_s'], '0.15')
        self.assertAlmostEqual(float(values['target_left_counts_per_s']), 2*3688/(2*math.pi))
        self.assertAlmostEqual(float(values['target_right_counts_per_s']), 2*3607/(2*math.pi))
        self.assertAlmostEqual(float(values['actual_left_counts_per_s']), 3688/(2*math.pi))
        self.assertAlmostEqual(float(values['actual_right_counts_per_s']), 3*3607/(2*math.pi))
        self.assertAlmostEqual(float(values['error_left_angular_rad_s']), -1.0)
        self.assertAlmostEqual(float(values['error_right_angular_rad_s']), 1.0)
        self.assertAlmostEqual(float(values['error_left_counts_per_s']), -3688/(2*math.pi))
        self.assertAlmostEqual(float(values['error_right_counts_per_s']), 3607/(2*math.pi))
        self.assertEqual(values['comparison_meaning'], 'node_does_not_actuate')
        self.assertEqual(values['tracking_performance'], 'not_measured')
        self.assertEqual(values['count_sign_convention'], 'normalized_forward_positive')

    def test_rejected_command_invalidates_comparison_without_publishing(self):
        self.node._on_command(self.command(.15, 0.0))
        self.node._on_feedback(self.feedback())
        _, values = self.diagnostic()
        self.assertEqual(values['comparison_available'], 'true')
        rejected = self.command(.3, .2)
        rejected.linear.y = .01
        self.node._on_command(rejected)
        _, values = self.diagnostic()
        self.assertEqual(values['target_state'], 'invalidated')
        self.assertEqual(values['command_result'], 'unsupported_twist_axes')
        self.assertEqual(values['comparison_available'], 'false')
        self.assertEqual(values['error_left_counts_per_s'], 'unavailable')
        self.assertEqual(values['requested_data_meaning'], 'latest_command_attempt')
        self.assertEqual(values['requested_linear_m_s'], '0.3')
        self.assertAlmostEqual(float(values['target_left_angular_rad_s']), 2.0)
        self.assertEqual(values['target_data_meaning'], 'last_valid_command_historical_when_not_fresh')
        self.assertEqual(values['target_sequence'], '1')
        self.assertEqual(self.node.target_pub.publish.call_count, 1)
        self.node._on_command(self.command(.3, 0.0))
        _, values = self.diagnostic()
        self.assertEqual(values['target_state'], 'fresh')
        self.assertEqual(values['comparison_available'], 'true')
        self.assertEqual(values['target_sequence'], '2')
        self.assertEqual(self.node.target_pub.publish.call_count, 2)

    def test_invalid_feedback_clears_previous_actual_and_comparison(self):
        self.node._on_command(self.command())
        cases = [
            ('name', ['left_wheel_joint', 'left_wheel_joint'], 'duplicate_joint_names'),
            ('name', ['right_wheel_joint', 'other_joint'], 'missing_wheel_joints'),
            ('velocity', [1.0], 'invalid_joint_array_lengths'),
            ('position', [1.0], 'invalid_joint_array_lengths'),
            ('effort', [1.0], 'invalid_joint_array_lengths'),
            ('velocity', [math.nan, 1.0], 'nonfinite_joint_values'),
            ('position', [1.0, math.inf], 'nonfinite_joint_values'),
            ('effort', [-math.inf, 1.0], 'nonfinite_joint_values'),
            ('velocity', [1e308, 1.0], 'nonfinite_feedback_counts'),
        ]
        for field, bad_value, reason in cases:
            with self.subTest(field=field, reason=reason):
                self.node._on_feedback(self.feedback())
                msg = self.feedback()
                setattr(msg, field, bad_value)
                self.node._on_feedback(msg)
                _, values = self.diagnostic()
                self.assertEqual(values['actual_state'], 'invalid')
                self.assertEqual(values['feedback_result'], reason)
                self.assertEqual(values['comparison_available'], 'false')
                self.assertEqual(values['actual_left_angular_rad_s'], 'unavailable')
                self.assertEqual(values['error_right_counts_per_s'], 'unavailable')
        self.assertEqual(self.node.rejected_feedback, len(cases))
        self.assertEqual(self.node.target_pub.publish.call_count, 1)

    def test_source_stamp_validation_and_freshness_boundaries(self):
        self.node._on_command(self.command())
        for offset in (-500_000_000, 50_000_000):
            self.node._on_feedback(self.feedback(stamp_ns=self.now_ns + offset))
            _, values = self.diagnostic()
            self.assertEqual(values['actual_state'], 'fresh')
        for stamp, state, reason in (
                (0, 'invalid', 'invalid_feedback_stamp'),
                (-1, 'invalid', 'invalid_feedback_stamp'),
                (self.now_ns + 50_000_001, 'invalid', 'future_feedback_stamp'),
                (self.now_ns - 500_000_001, 'stale', 'stale_feedback')):
            with self.subTest(stamp=stamp):
                self.node._on_feedback(self.feedback(stamp_ns=stamp))
                _, values = self.diagnostic()
                self.assertEqual(values['actual_state'], state)
                self.assertEqual(values['feedback_result'], reason)
                self.assertEqual(values['actual_right_counts_per_s'], 'unavailable')
                self.assertEqual(values['error_left_angular_rad_s'], 'unavailable')

    def test_freshness_is_reporting_only_and_checks_both_clocks(self):
        self.node._on_command(self.command())
        self.node._on_feedback(self.feedback())
        self.now_ns += 500_000_001  # Old source stamp, even with a recent receipt.
        _, values = self.diagnostic()
        self.assertEqual(values['actual_state'], 'stale')
        self.assertEqual(values['error_left_counts_per_s'], 'unavailable')
        self.node._on_feedback(self.feedback())
        self.now += .501  # Receipt and target age; ROS clock intentionally unchanged.
        _, values = self.diagnostic()
        self.assertEqual(values['target_state'], 'stale')
        self.assertEqual(values['actual_state'], 'stale')
        self.node._on_feedback(self.feedback())
        _, values = self.diagnostic()
        self.assertEqual(values['actual_state'], 'fresh')
        self.assertEqual(values['comparison_available'], 'false')
        self.assertEqual(values['error_right_angular_rad_s'], 'unavailable')
        self.assertEqual(self.node.target_pub.publish.call_count, 1)

    def test_absent_feedback_is_unavailable_and_topics_are_isolated(self):
        status, values = self.diagnostic()
        self.assertEqual(status.level, DiagnosticStatus.WARN)
        self.assertEqual(values['actual_state'], 'absent')
        self.assertEqual(values['target_state'], 'absent')
        self.assertEqual(values['actual_left_counts_per_s'], 'unavailable')
        self.assertEqual(values['error_right_counts_per_s'], 'unavailable')
        self.assertEqual(values['mode'], 'preview_only')
        self.assertEqual(values['motor_output_enabled'], 'false')
        self.assertEqual(self.node.command_sub.topic_name, '/limbo/drive_preview/cmd_vel')
        self.assertEqual(self.node.feedback_sub.topic_name, '/wheel/joint_states')
        self.assertEqual(self.original_target_topic, '/limbo/drive_preview/target_joint_states')
        self.assertEqual(self.original_status_topic, '/limbo/drive_preview/status')
        self.assertNotIn('/cmd_vel', [publisher.topic_name for publisher in self.node.publishers])

    def test_parameters_are_immutable(self):
        for key, value in (('wheel_separation', .5), ('command_topic', '/cmd_vel'),
                           ('max_target_age_seconds', 2.0), ('use_sim_time', True)):
            result = self.node.set_parameters([Parameter(key, value=value)])
            self.assertFalse(result[0].successful)

    def test_missing_invalid_geometry_and_sim_time_prevent_startup(self):
        for changes, reason in (
                ({'left_wheel_radius': 0.0}, 'left_wheel_radius'),
                ({'right_counts_per_revolution': math.nan}, 'right_counts_per_revolution'),
                ({'wheel_separation': -.5}, 'wheel_separation'),
                ({'use_sim_time': True}, 'use_sim_time=false'),
                ({'target_topic': '/cmd_vel'}, 'must not use /cmd_vel'),
                ({'target_topic': '/wheel/joint_states'}, 'must differ from feedback_topic')):
            candidate = DrivePreviewNode.__new__(DrivePreviewNode)
            try:
                with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, reason):
                    candidate.__init__(parameter_overrides=[
                        Parameter(k, value=v) for k, v in {**self.parameters, **changes}.items()])
            finally:
                candidate.destroy_node()
        candidate = DrivePreviewNode.__new__(DrivePreviewNode)
        try:
            with self.assertRaisesRegex(ValueError, 'left_wheel_radius'):
                candidate.__init__()
        finally:
            candidate.destroy_node()


if __name__ == '__main__':
    unittest.main()
