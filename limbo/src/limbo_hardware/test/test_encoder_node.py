"""ROS message/fault behavior with a fake reader; never opens a physical port."""
import math
import unittest
from unittest.mock import Mock

import rclpy
from rclpy.parameter import Parameter
from diagnostic_msgs.msg import DiagnosticStatus
from limbo_hardware.encoder_node import EncoderNode


class FakeReader:
    def __init__(self, **kwargs):
        self.raw = (100, 1000)
        self.fail = False
        self.closed = False
        self.open_calls = 0

    def open(self):
        self.open_calls += 1
        self.closed = False
        return 'USB Roboclaw 2x15A fake transport'

    def read_counts(self):
        if self.fail:
            raise OSError('simulated USB loss')
        return self.raw

    def close(self):
        self.closed = True


class NodeTests(unittest.TestCase):
    def setUp(self):
        rclpy.init()
        self.now = 100.0
        self.node = EncoderNode(reader_factory=FakeReader, monotonic=lambda: self.now)
        self.node.count_pub = Mock()
        self.node.joint_pub = Mock()
        self.node.diag_pub = Mock()

    def tearDown(self):
        self.node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

    def test_baseline_then_3607_counts_is_one_right_revolution(self):
        self.node._poll()
        first = self.node.count_pub.publish.call_args.args[0]
        joint = self.node.joint_pub.publish.call_args.args[0]
        self.assertTrue(first.baseline)
        self.assertEqual(first.sequence, 0)
        self.assertEqual(list(joint.velocity), [])
        self.assertEqual(list(joint.name), ['right_wheel_joint'])
        self.now += 2
        self.node.reader.raw = (3707, 990)
        self.node._poll()
        counts = self.node.count_pub.publish.call_args.args[0]
        joint = self.node.joint_pub.publish.call_args.args[0]
        self.assertEqual(counts.right_total, 3607)
        self.assertEqual(counts.left_total, 10)
        self.assertAlmostEqual(joint.position[0], 2 * math.pi)
        self.assertAlmostEqual(joint.velocity[0], math.pi)
        self.assertEqual(counts.header.stamp, joint.header.stamp)

    def test_loss_stops_samples_and_reconnect_rebaselines(self):
        self.node._poll()
        old_epoch = self.node.session_id
        self.node.reader.fail = True
        self.now += .05
        self.node._poll()
        self.assertEqual(self.node.count_pub.publish.call_count, 1)
        self.assertEqual(self.node.joint_pub.publish.call_count, 1)
        self.assertEqual(self.node.diag_pub.publish.call_args.args[0].status[0].level,
                         DiagnosticStatus.ERROR)
        self.assertTrue(self.node.reader.closed)
        self.now += 1
        self.node._poll()
        self.assertEqual(self.node.reader.open_calls, 1)
        self.node.reader.fail = False
        self.node.reader.raw = (99999, 22222)
        self.now += 2
        self.node._poll()
        reading = self.node.count_pub.publish.call_args.args[0]
        self.assertNotEqual(reading.session_id, old_epoch)
        self.assertTrue(reading.baseline)
        self.assertEqual(reading.right_total, 0)
        self.assertEqual(reading.left_total, 0)
        self.assertEqual(list(self.node.joint_pub.publish.call_args.args[0].velocity), [])

    def test_large_jump_is_not_published(self):
        self.node._poll()
        self.node.reader.raw = (20000, 1000)
        self.now += .05
        self.node._poll()
        self.assertEqual(self.node.count_pub.publish.call_count, 1)
        self.assertFalse(self.node.connected)

    def test_readonly_parameters_and_wall_clock(self):
        result = self.node.set_parameters([Parameter('right_counts_per_revolution', value=1.0)])
        self.assertFalse(result[0].successful)
        result = self.node.set_parameters([Parameter('left_counts_per_revolution', value=4000.0)])
        self.assertFalse(result[0].successful)
        result = self.node.set_parameters([Parameter('use_sim_time', value=True)])
        self.assertFalse(result[0].successful)

    def test_diagnostics_mark_provisional_and_missing_left_cpr(self):
        self.node._poll()
        self.node._diagnostics()
        status = self.node.diag_pub.publish.call_args.args[0].status[0]
        values = {v.key: v.value for v in status.values}
        self.assertEqual(status.level, DiagnosticStatus.OK)
        self.assertEqual(values['right_calibration'], 'provisional')
        self.assertEqual(values['left_counts_per_revolution'], 'unconfirmed')
        self.assertEqual(values['left_calibration'], 'unconfirmed')
        self.assertEqual(values['left_angle_enabled'], 'False')
        self.assertEqual(values['motor_commands_enabled'], 'False')

    def enable_left_angle(self, cpr=4000.0):
        self.node.destroy_node()
        self.node = EncoderNode(
            reader_factory=FakeReader, monotonic=lambda: self.now,
            parameter_overrides=[Parameter('left_counts_per_revolution', value=cpr)])
        self.node.count_pub = Mock()
        self.node.joint_pub = Mock()
        self.node.diag_pub = Mock()

    def test_left_calibration_publishes_forward_reverse_and_stop(self):
        # Deliberately unlike 3607: sharing the right conversion must fail this test.
        self.enable_left_angle(4000.0)
        self.node._poll()
        baseline = self.node.joint_pub.publish.call_args.args[0]
        self.assertEqual(list(baseline.name), ['right_wheel_joint', 'left_wheel_joint'])
        self.assertEqual(list(baseline.position), [0.0, 0.0])
        self.assertEqual(list(baseline.velocity), [])
        self.assertEqual(list(baseline.effort), [])

        self.now += 2.0
        self.node.reader.raw = (3707, (1000 - 4000) % 2**32)
        self.node._poll()
        counts = self.node.count_pub.publish.call_args.args[0]
        joints = self.node.joint_pub.publish.call_args.args[0]
        self.assertEqual(counts.m2_raw, (1000 - 4000) % 2**32)
        self.assertEqual(counts.left_total, 4000)
        self.assertEqual(counts.header.stamp, joints.header.stamp)
        for position in joints.position:
            self.assertAlmostEqual(position, 2 * math.pi)
        for velocity in joints.velocity:
            self.assertAlmostEqual(velocity, math.pi)

        self.now += 0.5
        self.node.reader.raw = (3707, 1000)
        self.node._poll()
        counts = self.node.count_pub.publish.call_args.args[0]
        joints = self.node.joint_pub.publish.call_args.args[0]
        self.assertEqual(counts.left_delta, -4000)
        self.assertEqual(counts.left_total, 0)
        self.assertAlmostEqual(joints.position[0], 2 * math.pi)
        self.assertEqual(joints.position[1], 0.0)
        self.assertEqual(joints.velocity[0], 0.0)
        self.assertAlmostEqual(joints.velocity[1], -4 * math.pi)

        self.now += 0.13
        self.node._poll()
        joints = self.node.joint_pub.publish.call_args.args[0]
        self.assertEqual(list(joints.velocity), [0.0, 0.0])
        self.assertAlmostEqual(joints.position[0], 2 * math.pi)
        self.assertEqual(joints.position[1], 0.0)

    def test_left_angle_reconnect_clears_both_positions_and_velocity(self):
        self.enable_left_angle()
        self.node._poll()
        self.now += 0.5
        self.node.reader.raw = (200, 900)
        self.node._poll()
        old_epoch = self.node.session_id
        self.node.reader.fail = True
        self.now += 0.05
        self.node._poll()
        self.assertEqual(self.node.joint_pub.publish.call_count, 2)
        self.assertEqual(self.node.count_pub.publish.call_count, 2)
        self.assertFalse(self.node.connected)
        self.now += 2.1
        self.node.reader.fail = False
        self.node.reader.raw = (99999, 22222)
        self.node._poll()
        counts = self.node.count_pub.publish.call_args.args[0]
        joints = self.node.joint_pub.publish.call_args.args[0]
        self.assertNotEqual(counts.session_id, old_epoch)
        self.assertTrue(counts.baseline)
        self.assertEqual(list(joints.position), [0.0, 0.0])
        self.assertEqual(list(joints.velocity), [])

    def test_left_diagnostics_expose_provisional_value(self):
        self.enable_left_angle(4000.0)
        self.node._poll()
        self.node._diagnostics()
        status = self.node.diag_pub.publish.call_args.args[0].status[0]
        values = {v.key: v.value for v in status.values}
        self.assertEqual(status.level, DiagnosticStatus.OK)
        self.assertEqual(values['left_counts_per_revolution'], '4000.0')
        self.assertEqual(values['left_calibration'], 'provisional')
        self.assertEqual(values['left_angle_enabled'], 'True')
        self.assertEqual(values['right_counts_per_revolution'], '3607.0')
        self.assertEqual(values['motor_commands_enabled'], 'False')

    def test_invalid_left_cpr_is_rejected_before_reader_creation(self):
        for value in (-1.0, float('inf'), float('nan')):
            with self.subTest(left_cpr=value):
                reader = Mock()
                candidate = EncoderNode.__new__(EncoderNode)
                try:
                    with self.assertRaisesRegex(ValueError, 'left_counts_per_revolution'):
                        candidate.__init__(reader_factory=reader,
                            parameter_overrides=[Parameter('left_counts_per_revolution', value=value)])
                    reader.assert_not_called()
                finally:
                    candidate.destroy_node()


if __name__ == '__main__':
    unittest.main()
