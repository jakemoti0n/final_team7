"""ROS adapter tests with synthetic messages; no physical device is opened."""
import math
import unittest
from unittest.mock import Mock

import rclpy
from rclpy.parameter import Parameter
from diagnostic_msgs.msg import DiagnosticStatus
from limbo_interfaces.msg import WheelEncoderCounts
from limbo_hardware.odometry_node import OdometryNode


class OdometryNodeTests(unittest.TestCase):
    def setUp(self):
        rclpy.init()
        self.now = 1.0
        self.now_ns = 1_000_000_000
        self.parameters = {
            'left_wheel_radius': .075, 'right_wheel_radius': .075,
            'wheel_separation': .54, 'left_counts_per_revolution': 3688.0,
            'right_counts_per_revolution': 3607.0,
        }
        self.node = OdometryNode(
            parameter_overrides=[Parameter(k, value=v) for k, v in self.parameters.items()],
            monotonic=lambda: self.now, clock_ns=lambda: self.now_ns)
        self.node.odom_pub = Mock()
        self.node.diag_pub = Mock()

    def tearDown(self):
        self.node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

    def message(self, seq, right=0, left=0, dr=0, dl=0, session='one', baseline=False):
        self.now_ns = 1_000_000_000 + seq * 100_000_000
        self.now = self.now_ns / 1e9
        msg = WheelEncoderCounts()
        msg.header.stamp.sec, msg.header.stamp.nanosec = divmod(self.now_ns, 1_000_000_000)
        msg.session_id, msg.sequence, msg.baseline = session, seq, baseline
        msg.right_delta, msg.left_delta = dr, dl
        msg.right_total, msg.left_total = right, left
        return msg

    def test_message_frames_covariances_and_unequal_cpr(self):
        self.node._on_counts(self.message(0, baseline=True))
        self.node.odom_pub.publish.assert_not_called()
        counts = self.message(1, 3607, 3688, 3607, 3688)
        self.node._on_counts(counts)
        odom = self.node.odom_pub.publish.call_args.args[0]
        self.assertEqual(odom.header.stamp, counts.header.stamp)
        self.assertEqual(odom.header.frame_id, 'odom')
        self.assertEqual(odom.child_frame_id, 'base_footprint')
        self.assertAlmostEqual(odom.pose.pose.position.x, .15*math.pi)
        self.assertAlmostEqual(odom.pose.pose.position.y, 0)
        self.assertEqual(odom.pose.pose.orientation.w, 1)
        self.assertEqual(odom.twist.twist.linear.y, 0)
        self.assertAlmostEqual(odom.twist.twist.linear.x, .15*math.pi/.1)
        self.assertAlmostEqual(odom.twist.twist.angular.z, 0, delta=1e-12)
        for covariance in (odom.pose.covariance, odom.twist.covariance):
            self.assertEqual(len(covariance), 36)
            self.assertTrue(all(math.isfinite(value) for value in covariance))
            for index in (0, 7, 14, 21, 28, 35):
                self.assertGreater(covariance[index], 0)
        self.assertEqual(odom.pose.covariance[14], 1e6)

    def test_left_only_turn_has_negative_yaw_and_normalized_quaternion(self):
        self.node._on_counts(self.message(0, baseline=True))
        self.node._on_counts(self.message(1, 0, 3688, 0, 3688))
        odom = self.node.odom_pub.publish.call_args.args[0]
        q = odom.pose.pose.orientation
        self.assertLess(q.z, 0)
        self.assertAlmostEqual(q.z*q.z+q.w*q.w, 1)
        self.assertLess(odom.twist.twist.angular.z, 0)
        self.assertGreater(odom.twist.twist.linear.x, 0)

    def test_stale_timer_does_not_republish_old_pose_and_recovery_skips_gap(self):
        self.node._on_counts(self.message(0, baseline=True))
        self.node._on_counts(self.message(1, 100, 100, 100, 100))
        position = self.node.core.x
        self.now += 1
        self.node._diagnostics()
        self.assertEqual(self.node.odom_pub.publish.call_count, 1)
        self.assertEqual(self.node.diag_pub.publish.call_args.args[0].status[0].level,
                         DiagnosticStatus.ERROR)
        self.node._on_counts(self.message(2, 1000, 1000, 900, 900))
        self.assertEqual(self.node.odom_pub.publish.call_count, 1)
        self.assertEqual(self.node.core.x, position)
        self.node._on_counts(self.message(3, 1000, 1000))
        odom = self.node.odom_pub.publish.call_args.args[0]
        self.assertEqual(odom.twist.twist.linear.x, 0)
        self.assertEqual(odom.twist.twist.angular.z, 0)
        self.node._diagnostics()
        self.assertEqual(self.node.diag_pub.publish.call_args.args[0].status[0].level,
                         DiagnosticStatus.OK)

    def test_parameters_are_immutable_and_diagnostics_describe_uncertainty(self):
        result = self.node.set_parameters([Parameter('wheel_separation', value=.5)])
        self.assertFalse(result[0].successful)
        result = self.node.set_parameters([Parameter('use_sim_time', value=True)])
        self.assertFalse(result[0].successful)
        self.node._on_counts(self.message(0, baseline=True))
        self.node._on_counts(self.message(1))
        self.node._diagnostics()
        status = self.node.diag_pub.publish.call_args.args[0].status[0]
        values = {entry.key: entry.value for entry in status.values}
        self.assertEqual(status.name, 'limbo/wheel_odometry')
        self.assertEqual(values['calibration'], 'provisional')
        self.assertEqual(values['tf_published'], 'False')
        self.assertEqual(values['motor_commands_enabled'], 'False')
        self.assertEqual(values['left_counts_per_revolution'], '3688.0')

    def test_publish_tf_sends_odom_to_base_transform(self):
        self.node.destroy_node()
        self.node = OdometryNode(
            parameter_overrides=[Parameter(k, value=v) for k, v in self.parameters.items()] +
            [Parameter('publish_tf', value=True)],
            monotonic=lambda: self.now, clock_ns=lambda: self.now_ns)
        self.node.odom_pub = Mock()
        self.node.diag_pub = Mock()
        self.node.tf_broadcaster = Mock()
        self.node._on_counts(self.message(0, baseline=True))
        self.node._on_counts(self.message(1, 3607, 3688, 3607, 3688))
        tf = self.node.tf_broadcaster.sendTransform.call_args.args[0]
        self.assertEqual((tf.header.frame_id, tf.child_frame_id), ('odom', 'base_footprint'))
        self.assertAlmostEqual(tf.transform.translation.x, .15*math.pi)
        self.node._diagnostics()
        values = {e.key: e.value for e in self.node.diag_pub.publish.call_args.args[0].status[0].values}
        self.assertEqual(values['tf_published'], 'True')

    def test_missing_geometry_does_not_start_with_a_simulation_default(self):
        candidate = OdometryNode.__new__(OdometryNode)
        try:
            with self.assertRaisesRegex(ValueError, 'left_radius'):
                candidate.__init__()
        finally:
            candidate.destroy_node()


if __name__ == '__main__':
    unittest.main()
