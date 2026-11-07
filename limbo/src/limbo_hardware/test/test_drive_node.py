"""/cmd_vel 브리지 노드 검사: 가짜 transport로 명령 끊김·속도 제한·방향 전환·잠김·저전압·보드 상태 비트,
보드 속도 제어 모드(board_speed)와 보드에서 읽는 엔코더 전진 부호."""
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
        self.encoder_modes = (0, 0)      # 보드 엔코더 모드 (M1, M2). 0x40 = 엔코더 방향 반전
        self.velocity = [{'p': 1.5, 'i': 0.3, 'd': 0.0, 'qpps': 5000}, {'p': 1.5, 'i': 0.3, 'd': 0.0, 'qpps': 5100}]
        self.speed_caps = None
        self.speed_writes = []           # (M1, M2, 가속도)
        self.pwms = [0, 0]
        self.currents = [0.0, 0.0]

    def read_encoder_modes(self):
        return self.encoder_modes

    def read_velocity_settings(self):
        caps = tuple(row['qpps'] for row in self.velocity)
        self.speed_caps = caps if all(cap > 0 for cap in caps) else None
        return self.velocity

    def write_speed(self, m1, m2, accel):
        assert self.speed_caps is not None and abs(m1) <= self.speed_caps[0] and abs(m2) <= self.speed_caps[1]
        self.speed_writes.append((m1, m2, accel))

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
                'status_hex': f'0x{self.status:08x}', 'pwms': list(self.pwms), 'currents_a': list(self.currents),
                'stop_reasons': status_names(self.status, STOP_STATUS_BITS),
                'notes': status_names(self.status, NOTE_STATUS_BITS)}

    def recover(self):
        pass

    def close(self):
        self.writes.append((0, 0))
        self.closed = True
        return True

    def spin_wheels(self, left_counts, right_counts):
        """전진 회전: M1(오른쪽)은 +, M2(왼쪽)는 원시 −. 보드에서 M2 엔코더 방향을 뒤집었으면 M2도 +."""
        left_sign = 1 if self.encoder_modes[1] & 0x40 else -1
        self.counts[0] = (self.counts[0] + right_counts) % 2**32
        self.counts[1] = (self.counts[1] + left_sign * left_counts) % 2**32


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

    def make(self, board=None, **overrides):
        """board: 열기 전에 가짜 보드 상태(엔코더 모드·속도 제어 값)를 바꾸는 함수."""
        values = {'left_wheel_radius': .075, 'right_wheel_radius': .075, 'wheel_separation': .54,
                  'left_counts_per_revolution': 3688., 'right_counts_per_revolution': 3607.}
        values.update(overrides)

        def factory(**kwargs):
            self.transport = FakeTransport(self, **kwargs)
            if board is not None:
                board(self.transport)
            return self.transport
        self.node = DriveNode(parameter_overrides=[Parameter(k, value=v) for k, v in values.items()],
                              transport_factory=factory, monotonic=lambda: self.now)
        self.node.count_pub, self.node.joint_pub, self.node.diag_pub = Mock(), Mock(), Mock()
        self.node._tick()  # opening → ready
        return self.node, self.transport

    def test_curve_calibrates_only_right_wheel_in_forward_units(self):
        node, _ = self.make(use_right_forward_curve=True, right_forward_feedforward_curve=[.07, .22, .13, .30])
        left, right = (controller.config for controller in node.controllers)
        self.assertEqual(left.forward_curve, ())
        self.assertEqual(right.forward_curve, (.07/.075, .22, .13/.075, .30))

    def test_saved_curve_requires_explicit_opt_in(self):
        node, _ = self.make(right_forward_feedforward_curve=[.07, .22, .13, .30])
        self.assertEqual(node.controllers[1].config.forward_curve, ())

    def command(self, linear, angular=0.0):
        msg = Twist()
        msg.linear.x, msg.angular.z = linear, angular
        self.node._on_command(msg)

    def step(self, seconds=0.05, left=0, right=0):
        self.now += seconds
        self.transport.spin_wheels(left, right)
        self.node._tick()

    def test_straight_start_limits_left_rise_then_restores_pi(self):
        node, fake = self.make(balance_straight_start=True)
        self.command(0.13)
        self.step()
        self.step()
        before = fake.writes[-1]
        self.step(left=16)
        right, left = fake.writes[-1]
        self.assertEqual(node.last_control['straight_start_phase'], 'limiting')
        self.assertLessEqual(left - before[1], 26)
        self.assertGreater(right - before[0], 200)
        self.step(left=40, right=57)
        self.assertEqual(node.last_control['straight_start_phase'], 'done')
        self.assertEqual(node.last_control['left_rise_scale'], 1.0)
        self.step(left=48)
        self.assertEqual(node.last_control['left_rise_scale'], 1.0)
        self.command(0.0)
        self.step()
        self.assertEqual(fake.writes[-1], (0, 0))

    def test_steering_jitter_before_motion_does_not_disarm_straight_start(self):
        node, _ = self.make(balance_straight_start=True)
        for angular in (0.0, 0.20, 0.0):
            self.command(0.08, angular)
            self.step()
        self.step(left=24)
        self.assertEqual(node.last_control['left_rise_scale'], 0.10)

    def test_start_limiter_yields_to_a_turn_and_to_timeout(self):
        node, fake = self.make(balance_straight_start=True)
        self.command(0.13)
        self.step()
        self.step(left=24)
        self.assertEqual(node.last_control['left_rise_scale'], 0.10)
        self.command(0.0, 0.3)
        self.step()
        self.assertEqual(node.last_control['left_rise_scale'], 1.0)
        self.assertLessEqual(fake.writes[-1][1], 0)
        for _ in range(12):
            self.step()
        self.assertEqual(fake.writes[-1], (0, 0))
        self.assertEqual(node.straight_start.phase, 'ready')
        self.command(-0.1)
        self.step()
        self.assertEqual(node.last_control['left_rise_scale'], 1.0)

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

    def test_person_wait_zeroes_output_until_cleared(self):
        from limbo_interfaces.msg import PersonWait
        node, fake = self.make()
        self.command(0.1)
        for _ in range(4):
            self.step(left=2, right=2)
            self.command(0.1)
        self.assertNotEqual(fake.writes[-1], (0, 0))
        msg = PersonWait(); msg.wait = True; msg.state = 'WAITING'; msg.reason = 'in_zone'
        node._on_person_wait(msg)
        self.command(0.1)
        self.step(left=2, right=2)
        self.assertEqual(fake.writes[-1], (0, 0))
        self.assertIn('person_wait', node.last_control['reasons'])
        msg.wait = False; msg.state = 'DRIVING'; msg.reason = 'zone_clear'
        node._on_person_wait(msg)
        for _ in range(3):
            self.command(0.1)
            self.step(left=2, right=2)
        self.assertNotEqual(fake.writes[-1], (0, 0))

    def test_board_stop_bit_zeroes_output(self):
        node, fake = self.make()
        fake.status = 0x03040000
        self.command(0.1)
        self.step()
        self.assertEqual(fake.writes[-1], (0, 0))
        self.assertIn('main_voltage_high_warning', node.last_control['reasons'])

    def test_transient_transport_errors_are_tolerated_then_fatal(self):
        node, fake = self.make()
        fake.recovers = 0
        fake.recover = lambda: setattr(fake, 'recovers', fake.recovers + 1)
        self.command(0.1)
        self.step(left=2, right=2)
        fake.sample_error = RuntimeError('synthetic CRC')
        self.step()   # 1회째: 넘김
        self.step()   # 2회째: 넘김
        self.assertFalse(node.closed)
        self.assertEqual(node.transient_errors, 2)
        self.assertEqual(fake.recovers, 2)
        self.assertEqual(fake.writes[-1], (0, 0))
        fake.sample_error = None
        self.command(0.1)
        self.step(left=2, right=2)   # 회복: 연속 카운터 초기화
        self.assertEqual(node.consecutive_errors, 0)
        fake.sample_error = RuntimeError('synthetic CRC')
        for _ in range(3):
            self.step()
        self.assertTrue(node.closed)   # 연속 3회째에 종료
        self.assertTrue(fake.closed)
        self.assertEqual(fake.writes[-1], (0, 0))
        self.assertTrue(any('synthetic CRC' in e for e in node.errors))

    def test_open_failure_is_fatal_immediately(self):
        self.node = None

        def factory(**kwargs):
            fake = FakeTransport(self, **kwargs)
            fake.open = lambda: (_ for _ in ()).throw(RuntimeError('no device'))
            self.transport = fake
            return fake
        values = {'left_wheel_radius': .075, 'right_wheel_radius': .075, 'wheel_separation': .54,
                  'left_counts_per_revolution': 3688., 'right_counts_per_revolution': 3607.}
        self.node = DriveNode(parameter_overrides=[Parameter(k, value=v) for k, v in values.items()],
                              transport_factory=factory, monotonic=lambda: self.now)
        self.node.count_pub, self.node.joint_pub, self.node.diag_pub = Mock(), Mock(), Mock()
        self.node._tick()
        self.assertTrue(self.node.closed)

    def test_control_gap_resets_and_sends_zero(self):
        node, fake = self.make()
        self.command(0.1)
        self.step(0.2)
        self.assertEqual(fake.writes[-1], (0, 0))
        self.assertFalse(node.closed)

    # ---- 보드에서 읽는 엔코더 전진 부호 ----
    @staticmethod
    def left_encoder_reversed(fake):
        fake.encoder_modes = (0, 0x40)

    def test_forward_sign_follows_board_encoder_mode(self):
        node, fake = self.make(board=self.left_encoder_reversed)
        self.assertEqual(node.forward_signs, (1, 1))
        self.command(0.1)
        for _ in range(6):
            self.step(left=2, right=2)   # 가짜 보드는 이제 왼쪽도 원시 +로 센다
            self.command(0.1)
        count = node.count_pub.publish.call_args.args[0]
        self.assertGreater(count.left_total, 0)
        self.assertGreater(count.right_total, 0)
        self.assertGreater(fake.writes[-1][1], 0)
        self.assertEqual(node.errors, [])

    def test_motor_reverse_setting_refuses_to_start(self):
        def board(fake):
            fake.encoder_modes = (0x20, 0)
        node, fake = self.make(board=board)
        self.assertTrue(node.closed)
        self.assertTrue(any('모터 방향 반전' in e for e in node.errors))
        self.assertTrue(all(w == (0, 0) for w in fake.writes))

    # ---- board_speed: 속도 맞추기를 보드에 맡기는 모드 ----
    def make_speed(self, board=None, **overrides):
        def prepared(fake):
            self.left_encoder_reversed(fake)
            if board is not None:
                board(fake)
        return self.make(board=prepared, control_mode='board_speed', **overrides)

    @staticmethod
    def qpps(linear_m_s, cpr):
        return round(linear_m_s / .075 * cpr / math.tau)

    def test_board_speed_refuses_board_without_velocity_settings(self):
        def board(fake):
            fake.velocity = [{'p': 0.0, 'i': 0.0, 'd': 0.0, 'qpps': 0}] * 2
        node, fake = self.make_speed(board=board)
        self.assertTrue(node.closed)
        self.assertTrue(any('자동 튜닝' in e for e in node.errors))
        self.assertEqual(fake.speed_writes, [])

    def test_board_speed_refuses_encoder_that_counts_down_on_forward(self):
        def board(fake):
            fake.encoder_modes = (0, 0)   # 왼쪽이 아직 전진에서 내려가는 상태
        node, fake = self.make_speed(board=board)
        self.assertTrue(node.closed)
        self.assertTrue(any('엔코더 방향' in e for e in node.errors))
        self.assertEqual(fake.speed_writes, [])

    def test_board_speed_sends_wheel_speeds_and_never_duty_while_driving(self):
        node, fake = self.make_speed()
        self.assertEqual(node.state, 'ready')
        self.command(0.1)
        self.step(left=2, right=2)
        accel = round(2.0 * 3688. / math.tau)   # 목표 변화율 2.0 rad/s²를 카운트/초²로
        self.assertEqual(fake.speed_writes[-1], (self.qpps(0.1, 3607.), self.qpps(0.1, 3688.), accel))
        self.assertTrue(all(w == (0, 0) for w in fake.writes))   # duty는 시작할 때의 0뿐
        self.assertEqual(node.last_control['control_mode'], 'board_speed')
        self.assertEqual(node.last_control['reasons'], [])
        self.command(0.0, 0.4)   # 제자리 왼쪽 회전: 오른쪽(M1) 전진, 왼쪽(M2) 후진
        self.step()
        m1, m2, _ = fake.speed_writes[-1]
        self.assertGreater(m1, 0)
        self.assertLess(m2, 0)

    def test_board_speed_stop_reasons_send_duty_zero_not_speed_zero(self):
        from limbo_interfaces.msg import PersonWait
        node, fake = self.make_speed()
        self.command(0.1)
        self.step(left=2, right=2)
        sent = len(fake.speed_writes)
        duty_writes = len(fake.writes)
        msg = PersonWait(); msg.wait = True; msg.state = 'WAITING'; msg.reason = 'in_zone'
        node._on_person_wait(msg)
        self.command(0.1)
        self.step(left=2, right=2)
        self.assertEqual(len(fake.speed_writes), sent)
        self.assertEqual(len(fake.writes), duty_writes + 1)
        self.assertEqual(fake.writes[-1], (0, 0))
        self.assertIn('person_wait', node.last_control['reasons'])
        msg.wait = False
        node._on_person_wait(msg)
        for _ in range(12):   # 명령이 0.5 s 넘게 안 오면 역시 duty 0
            self.step()
        self.assertIn('command_timeout', node.last_control['reasons'])
        self.assertEqual(fake.writes[-1], (0, 0))

    def test_board_speed_stall_when_target_set_but_encoder_silent(self):
        node, fake = self.make_speed(stall_seconds=1.0)
        for _ in range(40):
            self.command(0.1)
            self.step(left=0, right=2)   # 왼쪽만 안 돈다 (끼었거나 엔코더 선이 빠짐)
            if node.stalled[0]:
                break
        self.assertTrue(node.stalled[0])
        self.assertEqual(fake.writes[-1], (0, 0))
        self.assertIn('stall_left', node.last_control['reasons'])
        self.command(0.0)
        self.assertEqual(node.stalled, [False, False])

    def test_board_speed_target_below_one_count_per_window_is_not_a_stall(self):
        node, fake = self.make_speed(stall_seconds=1.0)
        for _ in range(40):
            self.command(0.0005)   # 약 4 카운트/초: 속도 창 0.1 s 안에 한 카운트가 안 들어온다
            self.step()
        self.assertEqual(node.stalled, [False, False])
        self.assertEqual(node.last_control['reasons'], [])

    def test_board_speed_wheel_speeding_up_the_wrong_way_is_fatal(self):
        node, fake = self.make_speed()
        for back in (10, 20, 30, 40, 50, 60, 70):   # 전진 목표인데 뒤로, 목표 크기보다 빠르게, 점점 빨라진다
            self.command(0.1)
            self.step(left=-back, right=-back)
            if node.closed:
                break
        self.assertTrue(node.closed)
        self.assertTrue(any('반대 방향' in e for e in node.errors))
        self.assertEqual(fake.writes[-1], (0, 0))

    def test_board_speed_reversal_while_still_rolling_forward_is_normal(self):
        node, fake = self.make_speed()
        for _ in range(6):
            self.command(0.1)
            self.step(left=40, right=40)
        for rolling in (30, 20, 10, 0, -10, -20):   # 후진 명령: 앞으로 구르던 바퀴가 느려졌다가 뒤로
            self.command(-0.1)
            self.step(left=rolling, right=rolling)
        self.assertFalse(node.closed)
        self.assertEqual(node.errors, [])
        self.assertLess(fake.speed_writes[-1][0], 0)

    def test_board_speed_nav2_flipping_tiny_turn_while_wheel_breaks_free_is_normal(self):
        """11-07 1차 자율주행 재현: 회전 목표가 100 ms 사이에 +0.05 → -0.03 rad/s로 뒤집히고, 왼쪽 바퀴는 막 구르기 시작해
        옛 방향으로 조금씩 빨라진다(틱당 1~2카운트). 목표 크기보다 느리므로 반대 주행이 아니다."""
        node, fake = self.make_speed()
        for _ in range(3):
            self.command(0.0, 0.05)          # 왼쪽 목표 뒤로(-0.014 m/s)
            self.step(left=-1, right=1)
        for _ in range(4):
            self.command(0.0, -0.03)         # 왼쪽 목표 앞으로(+0.008 m/s) — 바퀴는 아직 뒤로 1→2→3→4카운트/틱
            self.step(left=-(_ + 1), right=_ + 1)
        self.assertFalse(node.closed)
        self.assertEqual(node.errors, [])

    def test_board_speed_clamps_target_to_what_the_motor_can_do(self):
        def board(fake):
            fake.velocity = [{'p': 1.0, 'i': 0.2, 'd': 0.0, 'qpps': 500}, {'p': 1.0, 'i': 0.2, 'd': 0.0, 'qpps': 500}]
        node, fake = self.make_speed(board=board)
        self.command(0.25)
        self.step(left=2, right=2)
        self.assertEqual(fake.speed_writes[-1][:2], (500, 500))

    def test_unknown_control_mode_refuses(self):
        self.node = None
        with self.assertRaises(ValueError):
            self.make(control_mode='auto')

    def test_missing_geometry_refuses(self):
        self.node = None
        with self.assertRaises(ValueError):
            DriveNode(parameter_overrides=[], transport_factory=lambda **k: None, monotonic=lambda: 0.0)


if __name__ == '__main__':
    unittest.main()
