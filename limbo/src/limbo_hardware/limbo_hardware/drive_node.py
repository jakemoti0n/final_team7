"""/cmd_vel → RoboClaw duty 브리지 (실물 주행 명령 노드).

Nav2·키보드(teleop)가 내는 /cmd_vel(Twist)을 좌우 바퀴 목표 각속도로 나누고, 엔코더 피드백으로 바퀴별 PI를 돌려
duty 명령을 20 Hz로 보낸다. 엔코더 카운트·관절 상태를 벤치 노드와 같은 토픽으로 내므로 기존 wheel_odometry가 /odom을 만든다.

출력을 0으로 두는 상황(타이머가 아니라 신호로 분기한다):
- 명령 끊김: 마지막 /cmd_vel 뒤 보드 명령 timeout(보드에서 읽은 값, 기본 0.5 s)만큼 지나면. 노드가 죽어도 보드가 같은
  시간에 끊으므로 어느 쪽이 죽든 멈추는 시점이 같다.
- 배터리 저전압: 납축 12 V는 10.5 V 아래로 쓰면 수명이 급히 준다. 부하 중 순간 처짐을 고려해 10.0 V(설정값) 아래면 멈추고
  0.3 V 올라올 때까지 유지(보드 분해능 0.1 V·부하 변동에 떨지 않게).
- 보드 상태 비트: E-stop, 드라이버 고장, 과전압·저전압 등 (roboclaw_drive.STOP_STATUS_BITS).
- 잠김(stall): 출력이 상한에 붙었는데 그 바퀴 엔코더가 stall_seconds 동안 안 움직임. 11-03 축 수리 뒤 왼쪽 바퀴가 15 %
  상한에서 8 s 동안 0카운트였다. 정상 출발은 0.3 s 안에 카운트가 오르므로 1 s면 "미는 중"이 아니라 "잠김"이다.
  잠김은 양쪽 목표가 0이 될 때(키를 떼거나 Nav2가 멈추면) 풀린다.
"""
from dataclasses import asdict, replace
import json
import math
from pathlib import Path
import signal
import time
import uuid

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from rclpy.signals import SignalHandlerOptions
from rcl_interfaces.msg import ParameterDescriptor, SetParametersResult
from geometry_msgs.msg import Twist
from sensor_msgs.msg import JointState
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from limbo_interfaces.msg import WheelEncoderCounts

from .drive_preview_core import calculate_drive_targets
from .roboclaw_readonly import CounterTracker
from .roboclaw_drive import DriveTransport, DriveError, DUTY_CEILING
from .speed_pi import PIConfig, WheelSpeedPI
from .speed_estimator import CountWindowEstimator


def limit_twist(linear, angular, max_linear, max_angular):
    """두 성분 중 하나라도 상한을 넘으면 같은 비율로 줄인다(회전 반경 유지). 유한하지 않으면 0."""
    if not (math.isfinite(linear) and math.isfinite(angular)):
        return 0.0, 0.0
    scale = max(1.0, abs(linear) / max_linear, abs(angular) / max_angular)
    return linear / scale, angular / scale


class DriveNode(Node):
    def __init__(self, *, parameter_overrides=None, transport_factory=DriveTransport, monotonic=time.monotonic):
        super().__init__('roboclaw_drive', parameter_overrides=parameter_overrides)
        self.mono = monotonic
        defaults = {
            'port': '/dev/serial/by-id/usb-Basicmicro_Inc._USB_Roboclaw_2x15A-if00',
            'left_wheel_radius': 0.0, 'right_wheel_radius': 0.0, 'wheel_separation': 0.0,
            'left_counts_per_revolution': 0.0, 'right_counts_per_revolution': 0.0,
            'kp': 0.02, 'ki': 0.10, 'feedforward_gain': 0.25,
            'left_feedforward_gain': -1.0, 'right_feedforward_gain': -1.0,
            'max_duty_raw': 4915, 'target_slew_rad_s2': 2.0, 'output_slew_per_s': 0.15,
            'velocity_window_s': 0.10, 'control_period_s': 0.05,
            'max_linear_m_s': 0.25, 'max_angular_rad_s': 0.8,
            'min_battery_volts': 10.0, 'battery_recover_volts': 0.3, 'battery_period_s': 0.5,
            'stall_seconds': 1.0, 'record_dir': '',
        }
        descriptor = ParameterDescriptor(read_only=True)
        self.s = {k: self.declare_parameter(k, v, descriptor).value for k, v in defaults.items()}
        if self.get_parameter('use_sim_time').value:
            raise ValueError('실물 구동은 use_sim_time=false여야 함')
        self.add_on_set_parameters_callback(lambda ps: SetParametersResult(
            successful=not any(p.name == 'use_sim_time' for p in ps), reason='실물 시계 고정'))
        s = self.s
        for name in ('left_wheel_radius', 'right_wheel_radius', 'wheel_separation',
                     'left_counts_per_revolution', 'right_counts_per_revolution',
                     'max_linear_m_s', 'max_angular_rad_s', 'control_period_s', 'battery_period_s',
                     'stall_seconds', 'min_battery_volts', 'battery_recover_volts'):
            if not math.isfinite(s[name]) or s[name] <= 0:
                raise ValueError(f'{name}은 양수여야 함 (실물 치수는 설정 파일에서 와야 한다)')
        if type(s['max_duty_raw']) is not int or not 1 <= s['max_duty_raw'] <= DUTY_CEILING:
            raise ValueError(f'max_duty_raw는 1..{DUTY_CEILING} 정수')
        # 바퀴 목표 각속도의 상한: 선속도·각속도 상한을 둘 다 꽉 채웠을 때 바깥 바퀴 값. PI가 이 위를 거부한다
        radius = min(s['left_wheel_radius'], s['right_wheel_radius'])
        max_wheel = (s['max_linear_m_s'] + s['max_angular_rad_s'] * s['wheel_separation'] / 2.0) / radius
        common = PIConfig(kp=s['kp'], ki=s['ki'], max_duty_raw=s['max_duty_raw'],
                          target_slew_rad_s2=s['target_slew_rad_s2'], output_slew_per_s=s['output_slew_per_s'],
                          max_target_rad_s=max_wheel * 1.001, feedforward_gain=s['feedforward_gain'])
        configs = []
        for gain in (s['left_feedforward_gain'], s['right_feedforward_gain']):
            configs.append(common if gain == -1 else replace(common, feedforward_gain=gain))
        self.controllers = [WheelSpeedPI(c) for c in configs]  # [왼쪽, 오른쪽]
        self.estimator = CountWindowEstimator(s['left_counts_per_revolution'],
                                              s['right_counts_per_revolution'], s['velocity_window_s'])
        self.tracker = CounterTracker(signs=(1, -1))  # M1=오른쪽 전진 +, M2=왼쪽 전진 −(원시) → 둘 다 전진 +
        self.session = str(uuid.uuid4())
        self.sequence = 0
        self.files = {}
        if s['record_dir']:
            folder = Path(s['record_dir'])
            folder.mkdir(parents=True, exist_ok=False)
            self.files = {name: (folder / (name + '.jsonl')).open('w', buffering=1) for name in ('wire', 'control', 'events')}
        self.transport = transport_factory(port=s['port'], duty_cap=s['max_duty_raw'],
                                           wire_sink=lambda row: self._record('wire', row))

        # 명령·상태
        self.command = (0.0, 0.0)          # 제한을 거친 (선속도, 각속도)
        self.command_mono = None           # 마지막 /cmd_vel 수신 시각
        self.command_timeout_s = None      # 보드에서 읽은 명령 timeout
        self.battery_volts = None
        self.battery_low = False
        self.battery_checked_mono = None
        self.stall_since = [None, None]    # 바퀴별 포화 시작 시각
        self.stalled = [False, False]
        self.board_stop = []               # 보드 상태 비트 이름들
        self.board_notes = []
        self.previous = None               # 직전 sample
        self.last_control = None
        self.errors = []
        self.closed = False
        self.state = 'opening'

        self.count_pub = self.create_publisher(WheelEncoderCounts, '/wheel/encoder_counts', 5)
        self.joint_pub = self.create_publisher(JointState, '/wheel/joint_states', 5)
        self.diag_pub = self.create_publisher(DiagnosticArray, '/diagnostics', 5)
        self.command_sub = self.create_subscription(Twist, '/cmd_vel', self._on_command, 1)
        self.timer = self.create_timer(s['control_period_s'], self._tick)
        self.diag_timer = self.create_timer(0.25, self._diagnostics)

    # ---- 기록 ----
    def _record(self, name, row):
        stream = self.files.get(name)
        if stream is not None:
            stream.write(json.dumps(row, allow_nan=False) + '\n')

    def _event(self, kind, **data):
        self.get_logger().info(kind + ('' if not data else ' ' + json.dumps(data, ensure_ascii=False)))
        self._record('events', {'event': kind, 'monotonic_s': self.mono(), **data})

    # ---- 시작 ----
    def _open(self):
        firmware = self.transport.open()
        self.command_timeout_s = self.transport.ensure_timeout()
        self.battery_volts = self.transport.read_battery_volts()
        self.battery_checked_mono = self.mono()
        self.battery_low = self.battery_volts < self.s['min_battery_volts']
        # 이전 프로세스가 비정상 종료해 남긴 출력이 있을 수 있으니 0부터 시작
        self.transport.write_duty(0, 0)
        row = self.transport.sample()
        self.board_stop, self.board_notes = row['stop_reasons'], row['notes']
        self._publish_feedback(row, None)
        self.previous = row
        self.estimator.update(row['monotonic_s'], 0, 0)
        self.state = 'ready'
        self._event('opened', firmware=firmware, command_timeout_s=self.command_timeout_s,
                    battery_volts=self.battery_volts, status=row['status_hex'], max_duty_raw=self.s['max_duty_raw'])

    # ---- 명령 ----
    def _on_command(self, msg):
        linear, angular = limit_twist(msg.linear.x, msg.angular.z, self.s['max_linear_m_s'], self.s['max_angular_rad_s'])
        self.command = (linear, angular)
        self.command_mono = self.mono()
        if linear == 0.0 and angular == 0.0 and any(self.stalled):
            self.stalled = [False, False]
            self.stall_since = [None, None]
            self._event('stall_cleared')

    def _targets_now(self, now):
        """이번 틱의 좌우 바퀴 목표 각속도와, 0으로 둔 이유."""
        reasons = []
        if self.command_mono is None or now - self.command_mono > self.command_timeout_s:
            reasons.append('command_timeout')
        if self.battery_low:
            reasons.append('battery_low')
        if self.board_stop:
            reasons.extend(self.board_stop)
        if any(self.stalled):
            reasons.append('stall_left' if self.stalled[0] else 'stall_right')
        if reasons:
            return (0.0, 0.0), reasons
        targets = calculate_drive_targets(
            *self.command, left_radius_m=self.s['left_wheel_radius'], right_radius_m=self.s['right_wheel_radius'],
            wheel_separation_m=self.s['wheel_separation'],
            left_counts_per_revolution=self.s['left_counts_per_revolution'],
            right_counts_per_revolution=self.s['right_counts_per_revolution'])
        return (targets.left.angular_rad_s, targets.right.angular_rad_s), reasons

    # ---- 피드백 발행 ----
    def _publish_feedback(self, row, dt):
        reading = self.tracker.update(tuple(row['counts']))
        stamp = self.get_clock().now().to_msg()
        count = WheelEncoderCounts()
        count.header.stamp = stamp
        count.session_id = self.session
        count.sequence = self.sequence
        count.baseline = reading.baseline
        count.m1_raw, count.m2_raw = reading.raw
        count.right_delta, count.left_delta = reading.signed_forward_delta
        count.right_total, count.left_total = reading.signed_forward_total
        self.count_pub.publish(count)
        joint = JointState()
        joint.header.stamp = stamp
        joint.name = ['right_wheel_joint', 'left_wheel_joint']
        cpr = (self.s['right_counts_per_revolution'], self.s['left_counts_per_revolution'])
        joint.position = [n * math.tau / c for n, c in zip(reading.signed_forward_total, cpr)]
        if dt:
            joint.velocity = [n * math.tau / c / dt for n, c in zip(reading.signed_forward_delta, cpr)]
        self.joint_pub.publish(joint)
        self.sequence += 1
        return count

    # ---- 제어 틱 ----
    def _tick(self):
        if self.closed:
            return
        try:
            if self.state == 'opening':
                self._open()
                return
            now = self.mono()
            row = self.transport.sample()
            self.board_stop, self.board_notes = row['stop_reasons'], row['notes']
            dt = row['monotonic_s'] - self.previous['monotonic_s']
            count = self._publish_feedback(row, dt)
            self.previous = row
            estimate = self.estimator.update(row['monotonic_s'], count.left_total, count.right_total)
            config = self.controllers[0].config
            if dt > config.max_dt:
                # 호스트가 멈칫해 속도 창보다 긴 틈이 생겼다. 그 속도값으로 제어하지 않고 0을 보낸 뒤 다음 틱부터 다시
                for pi in self.controllers:
                    pi.reset()
                self.transport.write_duty(0, 0)
                self._event('control_gap', dt=dt)
                return
            if dt < config.min_dt or estimate is None:
                return
            if now - self.battery_checked_mono >= self.s['battery_period_s']:
                self._check_battery(now)
            targets, reasons = self._targets_now(now)
            measured = (estimate.left_rad_s, estimate.right_rad_s)
            outputs = []
            for index, (pi, target, actual) in enumerate(zip(self.controllers, targets, measured)):
                if target and pi.direction and (target > 0) != (pi.direction > 0):
                    pi.reset()  # 방향 전환은 0을 거쳐서 (PI 규약). 출력은 변화율 제한을 따라 다시 오른다
                outputs.append(pi.step(target, actual, dt))
                self._watch_stall(index, outputs[-1], actual, now)
            if any(self.stalled) and not reasons:
                # 이번 틱에 막 잠김으로 판정됐다: 출력은 이미 보냈으면 안 되므로 0으로
                outputs = [pi.step(0.0, actual, dt) for pi, actual in zip(self.controllers, measured)]
                reasons = ['stall_left' if self.stalled[0] else 'stall_right']
            duties = (outputs[1].duty_raw, outputs[0].duty_raw)  # M1=오른쪽, M2=왼쪽
            self.transport.write_duty(*duties)
            self.state = 'driving' if any(duties) else 'idle'
            self.last_control = {
                'monotonic_s': row['monotonic_s'], 'dt': dt, 'command': list(self.command), 'reasons': reasons,
                'target_left_right_rad_s': list(targets), 'measured_left_right_rad_s': list(measured),
                'duty_m1_m2': list(duties), 'left_total': count.left_total, 'right_total': count.right_total,
                'battery_volts': self.battery_volts, 'status': row['status_hex'],
                'pi_left_right': [asdict(o) for o in outputs]}
            self._record('control', self.last_control)
        except Exception as error:
            # 통신·장치 오류: 출력 0을 시도하고 노드를 끝낸다. 재접속은 사람이 원인을 보고 다시 띄운다
            self.errors.append(type(error).__name__ + ': ' + str(error))
            self.get_logger().error('구동 중단: ' + self.errors[-1])
            self.shutdown('error')

    def _check_battery(self, now):
        self.battery_volts = self.transport.read_battery_volts()
        self.battery_checked_mono = now
        low, recover = self.s['min_battery_volts'], self.s['min_battery_volts'] + self.s['battery_recover_volts']
        if not self.battery_low and self.battery_volts < low:
            self.battery_low = True
            self._event('battery_low', volts=self.battery_volts)
        elif self.battery_low and self.battery_volts >= recover:
            self.battery_low = False
            self._event('battery_recovered', volts=self.battery_volts)

    def _watch_stall(self, index, output, measured_rad_s, now):
        """상한에 붙은 채 바퀴가 안 돌면 잠김. 포화가 풀리거나 바퀴가 돌면 시계를 되돌린다."""
        moving = abs(measured_rad_s) > 0.0
        if output.saturated and not moving:
            if self.stall_since[index] is None:
                self.stall_since[index] = now
            elif now - self.stall_since[index] >= self.s['stall_seconds'] and not self.stalled[index]:
                self.stalled[index] = True
                self._event('stall', wheel='left' if index == 0 else 'right', duty_raw=output.duty_raw,
                            seconds=now - self.stall_since[index])
        else:
            self.stall_since[index] = None

    # ---- 진단 ----
    def _diagnostics(self):
        if not self.context.ok():
            return
        status = DiagnosticStatus(name='limbo/roboclaw_drive', hardware_id='roboclaw_2x15A')
        reasons = self.last_control['reasons'] if self.last_control else []
        status.level = (DiagnosticStatus.ERROR if self.errors else
                        DiagnosticStatus.WARN if reasons and reasons != ['command_timeout'] else DiagnosticStatus.OK)
        status.message = self.state if not reasons else self.state + ': ' + ','.join(reasons)
        values = {'state': self.state, 'battery_volts': self.battery_volts, 'battery_low': self.battery_low,
                  'command_timeout_s': self.command_timeout_s, 'max_duty_raw': self.s['max_duty_raw'],
                  'board_stop_bits': ','.join(self.board_stop), 'board_notes': ','.join(self.board_notes),
                  'stalled_left_right': self.stalled, 'errors': ' | '.join(self.errors)}
        if self.last_control:
            for key in ('command', 'target_left_right_rad_s', 'measured_left_right_rad_s', 'duty_m1_m2'):
                values[key] = self.last_control[key]
        status.values = [KeyValue(key=k, value=str(v)) for k, v in values.items()]
        msg = DiagnosticArray()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.status = [status]
        self.diag_pub.publish(msg)

    # ---- 종료 ----
    def shutdown(self, reason):
        if self.closed:
            return
        self.closed = True
        self.state = 'stopped'
        saved = {}
        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                saved[sig] = signal.signal(sig, signal.SIG_IGN)
            acked = self.transport.close()
        finally:
            for sig, handler in saved.items():
                signal.signal(sig, handler)
        self._event('closed', reason=reason, zero_acked=acked)
        if not acked and self.transport.firmware is not None:
            self.get_logger().error('정지 명령 ACK를 못 받음. 보드 timeout이 끊었는지 눈으로 확인할 것')
        for stream in self.files.values():
            stream.close()


def main(args=None):
    rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    node = None

    def interrupt(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, interrupt)
    signal.signal(signal.SIGTERM, interrupt)
    try:
        node = DriveNode()
        while rclpy.ok() and not node.closed:
            rclpy.spin_once(node, timeout_sec=0.05)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        if node is not None:
            node.shutdown('signal')
            ok = not node.errors
            node.destroy_node()
        else:
            ok = False
        if rclpy.ok():
            rclpy.shutdown()
    return 0 if ok else 1
