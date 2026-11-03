"""/cmd_vel 브리지 노드 검사: 가짜 transport로 명령 끊김·속도 제한·방향 전환·잠김·저전압·보드 상태 비트."""
import math
import unittest
from unittest.mock import Mock

import rclpy
from geometry_msgs.msg import Twist
from rclpy.parameter import Parameter

from limbo_hardware.drive_node import DriveNode, limit_twist


class FakeTransport:
    def __init__(self, owner, **kwargs):
        self.owner = owner
        self.duty_cap = kwargs['duty_cap']
        self.firmware = None
        self.timeout_raw = 0
        self.volts = 11.9
        self.status = 0x03000000
        self.counts = [1000, 4000000]
        self.writes = []
        self.closed = False
        self.sample_error = None

    def open(self):
        self.firmware = 'USB Roboclaw 2x15A v4.4.9'
        return self.firmware

    def ensure_timeout(self, raw=5):
        if self.timeout_raw == 0:
            self.timeout_raw = raw
        return self.timeout_raw * 0.1

    def read_battery_volts(self):
        return self.volts

    def write_duty(self, m1, m2):
        assert abs(m1) <= self.duty_cap and abs(m2) <= self.duty_cap
        self.writes.append((m1, m2))

    def sample(self):
        if self.sample_error:
            raise self.sample_error
        from limbo_hardware.roboclaw_drive import status_names, STOP_STATUS_BITS, NOTE_STATUS_BITS
        return {'monotonic_s': self.owner.now, 'counts': list(self.counts), 'status': self.status,
                'status_hex': f'0x{self.status:08x}', 'pwms': [0, 0],
                'stop_reasons': status_names(self.status, STOP_STATUS_BITS),
                'notes': status_names(self.status, NOTE_STATUS_BITS)}

    def close(self):
        self.writes.append((0, 0))
        self.closed = True
        return True

    def spin_wheels(self, left_counts, right_counts):
        """전진 회전: M1(오른쪽)은 +, M2(왼쪽)는 원시 −."""
        self.counts[0] = (self.counts[0] + right_counts) % 2**32
        self.counts[1] = (self.counts[1] - left_counts) % 2**32


class LimitTwistTests(unittest.TestCase):
    def test_scales_both_components_together(self):
        self.assertEqual(limit_twist(0.1, 0.2, 0.25, 0.8), (0.1, 0.2))
        linear, angular = limit_twist(0.5, 0.8, 0.25, 0.8)
        self.assertAlmostEqual(linear, 0.25)
        self.assertAlmostEqual(angular, 0.4)  # 같은 비율로 줄어 회전 반경 유지
        self.assertEqual(limit_twist(math.nan, 0.1, 0.25, 0.8), (0.0, 0.0))


class DriveNodeTests(unittest.TestCase):
    def setUp(self):
        rclpy.init()
        self.now = 100.0
        self.transport = None

    def tearDown(self):
        if self.node is not None:
            self.node.shutdown('test')
            self.node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

    def make(self, **overrides):
        values = {'left_wheel_radius': .075, 'right_wheel_radius': .075, 'wheel_separation': .54,
                  'left_counts_per_revolution': 3688., 'right_counts_per_revolution': 3607.}
        values.update(overrides)

        def factory(**kwargs):
            self.transport = FakeTransport(self, **kwargs)
            return self.transport
        self.node = DriveNode(parameter_overrides=[Parameter(k, value=v) for k, v in values.items()],
                              transport_factory=factory, monotonic=lambda: self.now)
        self.node.count_pub, self.node.joint_pub, self.node.diag_pub = Mock(), Mock(), Mock()
        self.node._tick()  # opening → ready
        return self.node, self.transport

    def command(self, linear, angular=0.0):
        msg = Twist()
        msg.linear.x, msg.angular.z = linear, angular
        self.node._on_command(msg)

    def step(self, seconds=0.05, left=0, right=0):
        self.now += seconds
        self.transport.spin_wheels(left, right)
        self.node._tick()

    def test_open_sets_board_timeout_and_starts_from_zero(self):
        node, fake = self.make()
        self.assertEqual(node.state, 'ready')
        self.assertEqual(fake.timeout_raw, 5)
        self.assertEqual(node.command_timeout_s, 0.5)
        self.assertEqual(fake.writes, [(0, 0)])

    def test_no_command_means_zero_output(self):
        node, fake = self.make()
        for _ in range(5):
            self.step()
        self.assertTrue(all(w == (0, 0) for w in fake.writes))
        self.assertIn('command_timeout', node.last_control['reasons'])

    def test_forward_command_drives_both_wheels_positive_then_times_out(self):
        node, fake = self.make()
        self.command(0.1)
        for _ in range(6):
            self.step(left=2, right=2)
        m1, m2 = fake.writes[-1]
        self.assertGreater(m1, 0)
        self.assertGreater(m2, 0)
        self.assertEqual(node.last_control['reasons'], [])
        # 명령이 0.5 s 넘게 안 오면 0
        for _ in range(11):
            self.step(left=2, right=2)
        self.assertEqual(fake.writes[-1], (0, 0))
        self.assertIn('command_timeout', node.last_control['reasons'])

    def test_turn_left_in_place_drives_wheels_opposite(self):
        node, fake = self.make()
        self.command(0.0, 0.4)
        for _ in range(6):
            self.step()
            self.command(0.0, 0.4)
        m1, m2 = fake.writes[-1]
        self.assertGreater(m1, 0)   # 오른쪽 전진
        self.assertLess(m2, 0)      # 왼쪽 후진

    def test_reversal_passes_through_zero_without_error(self):
        node, fake = self.make()
        self.command(0.1)
        for _ in range(4):
            self.step(left=2, right=2)
            self.command(0.1)
        self.command(-0.1)
        self.step()
        self.assertLessEqual(fake.writes[-1][0], 0)
        self.assertEqual(node.errors, [])

    def test_speed_limit_clamps_target(self):
        node, fake = self.make()
        self.command(5.0)
        self.assertAlmostEqual(node.command[0], 0.25)

    def test_stall_latches_after_stall_seconds_and_clears_on_zero_command(self):
        node, fake = self.make(stall_seconds=1.0)
        # 오른쪽만 돌고 왼쪽은 잠김: 왼쪽 출력이 상한까지 올라간 뒤 1 s 안 움직이면 잠김
        for _ in range(60):
            self.command(0.1)
            self.step(left=0, right=2)
            if node.stalled[0]:
                break
        self.assertTrue(node.stalled[0])
        self.assertEqual(fake.writes[-1], (0, 0))
        self.assertIn('stall_left', node.last_control['reasons'])
        self.command(0.0)
        self.assertEqual(node.stalled, [False, False])

    def run_half_second(self):
        for _ in range(11):  # 0.55 s: 전압 확인 주기(0.5 s)를 한 번 넘긴다
            self.command(0.1)
            self.step()

    def test_battery_low_stops_and_recovers_with_hysteresis(self):
        node, fake = self.make()
        fake.volts = 9.9
        self.run_half_second()
        self.assertTrue(node.battery_low)
        self.command(0.1)
        self.step()
        self.assertEqual(fake.writes[-1], (0, 0))
        self.assertIn('battery_low', node.last_control['reasons'])
        fake.volts = 10.2
        self.run_half_second()
        self.assertTrue(node.battery_low)  # 10.3 전에는 유지
        fake.volts = 10.3
        self.run_half_second()
        self.assertFalse(node.battery_low)

    def test_board_stop_bit_zeroes_output(self):
        node, fake = self.make()
        fake.status = 0x03040000
        self.command(0.1)
        self.step()
        self.assertEqual(fake.writes[-1], (0, 0))
        self.assertIn('main_voltage_high_warning', node.last_control['reasons'])

    def test_transport_error_shuts_down_with_zero(self):
        node, fake = self.make()
        fake.sample_error = RuntimeError('synthetic CRC')
        self.step()
        self.assertTrue(node.closed)
        self.assertTrue(fake.closed)
        self.assertEqual(fake.writes[-1], (0, 0))
        self.assertTrue(any('synthetic CRC' in e for e in node.errors))

    def test_control_gap_resets_and_sends_zero(self):
        node, fake = self.make()
        self.command(0.1)
        self.step(0.2)
        self.assertEqual(fake.writes[-1], (0, 0))
        self.assertFalse(node.closed)

    def test_missing_geometry_refuses(self):
        self.node = None
        with self.assertRaises(ValueError):
            DriveNode(parameter_overrides=[], transport_factory=lambda **k: None, monotonic=lambda: 0.0)


if __name__ == '__main__':
    unittest.main()
