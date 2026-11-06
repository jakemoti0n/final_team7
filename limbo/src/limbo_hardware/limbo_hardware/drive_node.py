"""/cmd_vel → RoboClaw duty 브리지 (실물 주행 명령 노드).

Nav2·키보드(teleop)가 내는 /cmd_vel(Twist)을 좌우 바퀴 목표 각속도로 나누고, 엔코더 피드백으로 바퀴별 PI를 돌려
duty 명령을 20 Hz로 보낸다. 엔코더 카운트·관절 상태를 벤치 노드와 같은 토픽으로 내므로 기존 wheel_odometry가 /odom을 만든다.

출력을 0으로 두는 상황(타이머가 아니라 신호로 분기한다):
- 명령 끊김: 마지막 /cmd_vel 뒤 보드 명령 timeout(보드에서 읽은 값, 기본 0.5 s)만큼 지나면. 노드가 죽어도 보드가 같은
  시간에 끊으므로 어느 쪽이 죽든 멈추는 시점이 같다.
- 배터리 저전압: 납축 12 V는 10.5 V 아래로 쓰면 수명이 급히 준다. 부하 중 순간 처짐을 고려해 10.0 V(설정값) 아래면 멈추고
  0.3 V 올라올 때까지 유지(보드 분해능 0.1 V·부하 변동에 떨지 않게).
- 보드 상태 비트: E-stop, 드라이버 고장, 과전압·저전압 등 (roboclaw_drive.STOP_STATUS_BITS).
- 사람 기다리기: /person_wait(limbo_interfaces/PersonWait).wait가 참인 동안(2-7, 시뮬 BT의 IsWaitingForPerson과 같은 필드).
  Nav2 없이 키보드로 몰 때도 사람 앞에서 서게 한다. 마지막 값을 그대로 쓴다(person_wait 노드가 죽으면 마지막 값에 머무름).
- 잠김(stall): 출력이 상한에 붙었는데 그 바퀴 엔코더가 stall_seconds 동안 안 움직임. 11-03 축 수리 뒤 왼쪽 바퀴가 15 %
  상한에서 8 s 동안 0카운트였다. 정상 출발은 0.3 s 안에 카운트가 오르므로 1 s면 "미는 중"이 아니라 "잠김"이다.
  잠김은 양쪽 목표가 0이 될 때(키를 떼거나 Nav2가 멈추면) 풀린다.

제어 방식은 control_mode 하나로 고른다(기본 host_duty, 위에 적은 방식).
- board_speed: 속도 맞추기를 보드에 맡긴다. 이 노드는 바퀴별 목표 속도(카운트/초)와 가속도만 명령 40으로 보내고, 보드 안의
  속도 제어기가 출력을 정한다. 20 Hz·USB 왕복으로는 멈춘 바퀴를 밀어 올리는 데 1~2 s가 걸리고 저속 목표에서 바퀴가 서던 것
  (11-06 목표점 주행)을 보드의 빠른 고리로 푼다. 보드에 속도 제어 값이 저장돼 있고(모션스튜디오 자동 튜닝) 양쪽 엔코더가
  "양수 명령 = 카운트 증가"로 맞춰져 있어야 시작한다. 아니면 시작을 거부한다.
  위의 출력 0 상황은 그대로이고, 그때는 속도 0이 아니라 duty 0을 보낸다(보드 제어기를 끄고 즉시 정지).
  이 모드의 잠김: 목표 속도가 있는데 엔코더가 stall_seconds 동안 0(엔코더 선이 빠져 보드가 출력을 끝까지 올리는 경우도 여기 걸린다).
  반대로 달림: 목표와 반대 방향으로 점점 빨라지는 틱이 MAX_CONSECUTIVE_ERRORS번 이어지면 노드를 끝낸다(방향 설정이 실제와 다름).

전진 카운트 부호는 시작할 때 보드의 엔코더 모드에서 읽어 정한다(roboclaw_readonly.forward_signs). 보드 설정을 바꿔도 따라간다.

직렬 오류는 연속 MAX_CONSECUTIVE_ERRORS번까지 넘긴다(그 틱은 0 출력 시도). 11-03 19분 주행이 USB 쓰기 timeout 한 번으로 끝났는데,
한 번 삐끗한 것과 USB가 빠진 것은 다르다. 3틱 = 0.15 s는 보드 timeout 0.5 s 안이라 그 사이 모터는 마지막 명령대로 돌다 보드가 끊는다.
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
from limbo_interfaces.msg import PersonWait, WheelEncoderCounts

from .drive_preview_core import calculate_drive_targets
from .roboclaw_readonly import CounterTracker, forward_signs
from .roboclaw_drive import DriveTransport, DriveError, DUTY_CEILING
from .speed_pi import PIConfig, WheelSpeedPI
from .speed_estimator import CountWindowEstimator

# 연속 직렬 오류 허용 횟수. 3틱(0.15 s)은 보드 명령 timeout(0.5 s)보다 짧아, 넘기는 동안에도 보드 쪽 안전망이 먼저 걸린다
MAX_CONSECUTIVE_ERRORS = 3


def limit_twist(linear, angular, max_linear, max_angular):
    """두 성분 중 하나라도 상한을 넘으면 같은 비율로 줄인다(회전 반경 유지). 유한하지 않으면 0."""
    if not (math.isfinite(linear) and math.isfinite(angular)):
        return 0.0, 0.0
    scale = max(1.0, abs(linear) / max_linear, abs(angular) / max_angular)
    return linear / scale, angular / scale


class StraightStart:
    """Use signed wheel travel to limit left duty rise during departure only."""

    def __init__(self):
        self.phase = 'ready'
        self.lead_m = 0.0

    def update(self, targets, speeds, positions):
        stopped = max(map(abs, speeds)) < 0.01
        if targets == (0.0, 0.0):
            self.phase = 'ready' if stopped else 'done'
            self.lead_m = 0.0
            return 1.0
        if self.phase == 'done':
            return 1.0

        left, right = targets  # Forward wheel targets in m/s.
        near_straight = min(targets) > 0.0 and abs(left - right) <= 0.35 * max(targets)
        if not near_straight:
            # A steering request before either wheel rolls may settle to straight.
            before_roll = self.phase == 'ready' or (
                self.phase == 'tracking'
                and max(abs(p - origin) for p, origin in zip(positions, self.origin)) < 0.001
            )
            self.phase = 'ready' if before_roll and stopped else 'done'
            return 1.0
        if self.phase == 'ready':
            if not stopped:  # Command changed while coasting.
                self.phase = 'done'
                return 1.0
            self.origin = self.previous = positions
            self.lead_m = 0.0
            self.phase = 'tracking'

        dl = positions[0] - self.previous[0]
        dr = positions[1] - self.previous[1]
        self.previous = positions
        # Subtract the difference the commanded arc itself would produce.
        self.lead_m += dl - dr - (dl + dr) * (left - right) / (left + right)
        both_rolling = min(positions[i] - self.origin[i] for i in (0, 1)) >= 0.005
        if both_rolling and self.lead_m <= 0.001:
            self.phase = 'done'
        elif self.lead_m >= 0.001:
            self.phase = 'limiting'
        # Stop restraining the left wheel if it falls behind before catch-up.
        elif self.phase == 'limiting' and self.lead_m <= 0.0:
            self.phase = 'tracking'
        return 0.10 if self.phase == 'limiting' else 1.0


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
            'use_right_forward_curve': False,
            'right_forward_feedforward_curve': [0., 0., 0., 0.],  # Two (wheel m/s, duty fraction) pairs.
            'max_duty_raw': DUTY_CEILING, 'target_slew_rad_s2': 2.0, 'output_slew_per_s': 0.15,
            'velocity_window_s': 0.10, 'control_period_s': 0.05, 'balance_straight_start': False,
            'max_linear_m_s': 0.25, 'max_angular_rad_s': 0.8,
            'min_battery_volts': 10.0, 'battery_recover_volts': 0.3, 'battery_period_s': 0.5,
            'stall_seconds': 1.0, 'record_dir': '',
            'wait_topic': '/person_wait',   # 비우면 사람 기다리기 게이트를 안 쓴다
            'control_mode': 'host_duty',    # host_duty: 이 노드의 PI가 duty를 정함 / board_speed: 보드 속도 제어기에 목표만 보냄
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
        if s['control_mode'] not in ('host_duty', 'board_speed'):
            raise ValueError('control_mode는 host_duty 또는 board_speed')
        self.board_speed = s['control_mode'] == 'board_speed'
        # 바퀴 목표 각속도의 상한: 선속도·각속도 상한을 둘 다 꽉 채웠을 때 바깥 바퀴 값. PI가 이 위를 거부한다
        radius = min(s['left_wheel_radius'], s['right_wheel_radius'])
        max_wheel = (s['max_linear_m_s'] + s['max_angular_rad_s'] * s['wheel_separation'] / 2.0) / radius
        common = PIConfig(kp=s['kp'], ki=s['ki'], max_duty_raw=s['max_duty_raw'],
                          target_slew_rad_s2=s['target_slew_rad_s2'], output_slew_per_s=s['output_slew_per_s'],
                          max_target_rad_s=max_wheel * 1.001, feedforward_gain=s['feedforward_gain'])
        configs = []
        for gain in (s['left_feedforward_gain'], s['right_feedforward_gain']):
            configs.append(common if gain == -1 else replace(common, feedforward_gain=gain))
        curve = s['right_forward_feedforward_curve']
        if s['use_right_forward_curve']:
            if len(curve) != 4:
                raise ValueError('right_forward_feedforward_curve needs two speed/duty pairs')
            slow, low_duty, fast, high_duty = curve
            radius = s['right_wheel_radius']
            configs[1] = replace(configs[1], forward_curve=(slow / radius, low_duty, fast / radius, high_duty))
        self.controllers = [WheelSpeedPI(c) for c in configs]  # [왼쪽, 오른쪽]
        self.straight_start = StraightStart() if s['balance_straight_start'] else None
        self.wheel_radii = (s['left_wheel_radius'], s['right_wheel_radius'])
        self.metres_per_count = (
            math.tau * self.wheel_radii[0] / s['left_counts_per_revolution'],
            math.tau * self.wheel_radii[1] / s['right_counts_per_revolution'],
        )
        self.estimator = CountWindowEstimator(s['left_counts_per_revolution'],
                                              s['right_counts_per_revolution'], s['velocity_window_s'])
        self.tracker = None                # 전진 부호를 보드에서 읽은 뒤 _open에서 만든다 (M1=오른쪽, M2=왼쪽)
        self.forward_signs = None
        self.velocity_settings = None      # board_speed에서 보드가 가진 [M1, M2] 속도 제어 값
        # 보드에 넘길 가속도(카운트/초²): 바퀴 목표 변화율 설정을 단위만 바꾼 것. 좌우 CPR 중 큰 쪽 기준(두 바퀴가 한 값을 같이 쓴다)
        self.accel_qpps2 = max(1, round(s['target_slew_rad_s2'] * max(
            s['left_counts_per_revolution'], s['right_counts_per_revolution']) / math.tau))
        self.wrong_way = [0, 0]            # 바퀴별: 목표 반대 방향으로 빨라진 연속 틱 수
        self.wrong_way_speed = [0.0, 0.0]  # 직전 틱의 |실측 속도|
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
        self.person_wait = False           # /person_wait.wait 마지막 값
        self.person_wait_reason = ''
        self.previous = None               # 직전 sample
        self.last_control = None
        self.errors = []
        self.consecutive_errors = 0
        self.transient_errors = 0          # 넘긴 직렬 오류 누계 (진단에 표시)
        self.closed = False
        self.state = 'opening'

        self.count_pub = self.create_publisher(WheelEncoderCounts, '/wheel/encoder_counts', 5)
        self.joint_pub = self.create_publisher(JointState, '/wheel/joint_states', 5)
        self.diag_pub = self.create_publisher(DiagnosticArray, '/diagnostics', 5)
        self.command_sub = self.create_subscription(Twist, '/cmd_vel', self._on_command, 1)
        self.wait_sub = (self.create_subscription(PersonWait, s['wait_topic'], self._on_person_wait, 5)
                         if s['wait_topic'] else None)
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
        modes = self.transport.read_encoder_modes()
        self.forward_signs = forward_signs(modes)
        self.tracker = CounterTracker(signs=self.forward_signs)
        if self.board_speed:
            self.velocity_settings = self.transport.read_velocity_settings()
            if self.transport.speed_caps is None or any(v['p'] == 0 and v['i'] == 0 for v in self.velocity_settings):
                raise DriveError('보드에 속도 제어 값이 없음 (읽힌 값 %s). 모션스튜디오에서 양쪽 속도 자동 튜닝을 하고 '
                                 '보드에 저장한 뒤 다시 시작할 것' % (self.velocity_settings,))
            if self.forward_signs != (1, 1):
                raise DriveError('엔코더 방향이 보드 속도 제어와 맞지 않음 (전진 부호 M1 %+d, M2 %+d, 엔코더 모드 %s). '
                                 '양수 명령에서 카운트가 올라가도록 모션스튜디오 Encoder 2 Mode의 방향을 뒤집고 저장할 것'
                                 % (self.forward_signs + (list(modes),)))
        row = self.transport.sample()
        self.board_stop, self.board_notes = row['stop_reasons'], row['notes']
        self._publish_feedback(row, None)
        self.previous = row
        self.estimator.update(row['monotonic_s'], 0, 0)
        self.state = 'ready'
        self._event('opened', firmware=firmware, command_timeout_s=self.command_timeout_s,
                    battery_volts=self.battery_volts, status=row['status_hex'], max_duty_raw=self.s['max_duty_raw'],
                    control_mode=self.s['control_mode'], encoder_modes=list(modes),
                    forward_signs_m1_m2=list(self.forward_signs), velocity_settings=self.velocity_settings,
                    accel_qpps2=self.accel_qpps2)

    # ---- 명령 ----
    def _on_command(self, msg):
        linear, angular = limit_twist(msg.linear.x, msg.angular.z, self.s['max_linear_m_s'], self.s['max_angular_rad_s'])
        self.command = (linear, angular)
        self.command_mono = self.mono()
        if linear == 0.0 and angular == 0.0 and any(self.stalled):
            self.stalled = [False, False]
            self.stall_since = [None, None]
            self._event('stall_cleared')

    def _on_person_wait(self, msg):
        if msg.wait != self.person_wait:
            self._event('person_wait', wait=msg.wait, state=msg.state, reason=msg.reason)
        self.person_wait, self.person_wait_reason = msg.wait, msg.reason

    def _targets_now(self, now):
        """이번 틱의 좌우 바퀴 목표 각속도와, 0으로 둔 이유."""
        reasons = []
        if self.command_mono is None or now - self.command_mono > self.command_timeout_s:
            reasons.append('command_timeout')
        if self.battery_low:
            reasons.append('battery_low')
        if self.board_stop:
            reasons.extend(self.board_stop)
        if self.person_wait:
            reasons.append('person_wait')
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
            if self.board_speed:
                self._step_board_speed(row, dt, count, targets, reasons, measured, now)
                return
            left_rise = 1.0
            if self.straight_start is not None:
                left_rise = self.straight_start.update(
                    tuple(v * r for v, r in zip(targets, self.wheel_radii)),
                    tuple(v * r for v, r in zip(measured, self.wheel_radii)),
                    (count.left_total * self.metres_per_count[0], count.right_total * self.metres_per_count[1]),
                )
            outputs = []
            for index, (pi, target, actual) in enumerate(zip(self.controllers, targets, measured)):
                if target and pi.direction and (target > 0) != (pi.direction > 0):
                    pi.reset()  # 방향 전환은 0을 거쳐서 (PI 규약). 출력은 변화율 제한을 따라 다시 오른다
                outputs.append(pi.step(target, actual, dt, forward_rise_scale=left_rise if index == 0 else 1.0))
                self._watch_stall(index, outputs[-1], actual, now)
            if any(self.stalled) and not reasons:
                # 이번 틱에 막 잠김으로 판정됐다: 출력은 이미 보냈으면 안 되므로 0으로
                outputs = [pi.step(0.0, actual, dt) for pi, actual in zip(self.controllers, measured)]
                reasons = ['stall_left' if self.stalled[0] else 'stall_right']
            duties = (outputs[1].duty_raw, outputs[0].duty_raw)  # M1=오른쪽, M2=왼쪽
            self.transport.write_duty(*duties)
            self.consecutive_errors = 0
            self.state = 'driving' if any(duties) else 'idle'
            self.last_control = {
                'monotonic_s': row['monotonic_s'], 'dt': dt, 'command': list(self.command), 'reasons': reasons,
                'target_left_right_rad_s': list(targets), 'measured_left_right_rad_s': list(measured),
                'duty_m1_m2': list(duties), 'left_total': count.left_total, 'right_total': count.right_total,
                'battery_volts': self.battery_volts, 'status': row['status_hex'],
                'straight_start_phase': self.straight_start.phase if self.straight_start else 'off',
                'left_rise_scale': left_rise, 'pi_left_right': [asdict(o) for o in outputs],
                'control_mode': 'host_duty', 'board_pwm_m1_m2': row.get('pwms'),
                'currents_m1_m2_a': row.get('currents_a')}
            self._record('control', self.last_control)
        except Exception as error:
            text = type(error).__name__ + ': ' + str(error)
            if self.state != 'opening' and self.consecutive_errors + 1 < MAX_CONSECUTIVE_ERRORS:
                # 한 번 삐끗한 교환: 버퍼를 비우고 이번 틱은 0 출력을 시도한 뒤 다음 틱에 다시 간다
                self.consecutive_errors += 1
                self.transient_errors += 1
                self._event('serial_error_tolerated', error=text, consecutive=self.consecutive_errors)
                try:
                    self.transport.recover()
                    self.transport.write_duty(0, 0)
                except Exception:
                    pass
                return
            # 시작 실패이거나 연속 오류 상한: 출력 0을 시도하고 노드를 끝낸다. 재접속은 사람이 원인을 보고 다시 띄운다
            self.errors.append(text)
            self.get_logger().error('구동 중단: ' + text)
            self.shutdown('error')

    def _step_board_speed(self, row, dt, count, targets, reasons, measured, now):
        """board_speed 한 틱: 멈출 이유가 있으면 duty 0, 없으면 바퀴별 속도 목표(카운트/초)를 보드에 보낸다."""
        cpr = (self.s['left_counts_per_revolution'], self.s['right_counts_per_revolution'])
        caps = (self.transport.speed_caps[1], self.transport.speed_caps[0])   # [왼쪽=M2, 오른쪽=M1]
        speeds = [0, 0]                                                       # [왼쪽, 오른쪽] 카운트/초
        if not reasons:
            for index, target in enumerate(targets):
                wanted = round(target * cpr[index] / math.tau)
                speeds[index] = max(-caps[index], min(caps[index], wanted))   # 모터가 낼 수 있는 속도(QPPS)까지만
                if self._runs_wrong_way(index, speeds[index], measured[index]):
                    text = ('%s 바퀴가 목표와 반대 방향으로 빨라짐 (목표 %d 카운트/초, 실측 %.2f rad/s). 엔코더 방향 설정이 '
                            '실제와 다르다' % ('왼쪽' if index == 0 else '오른쪽', speeds[index], measured[index]))
                    self.errors.append(text)
                    self.get_logger().error('구동 중단: ' + text)
                    self.shutdown('error')
                    return
                self._watch_board_stall(index, speeds[index], measured[index], row, now)
            if any(self.stalled):
                reasons = ['stall_left' if self.stalled[0] else 'stall_right']
        if reasons:
            speeds = [0, 0]
            self.stall_since = [None, None]
            self.wrong_way = [0, 0]
            self.transport.write_duty(0, 0)
        else:
            self.transport.write_speed(speeds[1], speeds[0], self.accel_qpps2)   # M1=오른쪽, M2=왼쪽
        self.consecutive_errors = 0
        self.state = 'driving' if any(speeds) else 'idle'
        self.last_control = {
            'monotonic_s': row['monotonic_s'], 'dt': dt, 'command': list(self.command), 'reasons': reasons,
            'target_left_right_rad_s': list(targets), 'measured_left_right_rad_s': list(measured),
            'duty_m1_m2': list(row['pwms']),   # 이 모드에서는 보드가 정한 출력(읽은 값)
            'left_total': count.left_total, 'right_total': count.right_total,
            'battery_volts': self.battery_volts, 'status': row['status_hex'],
            'straight_start_phase': 'off', 'left_rise_scale': 1.0,
            'control_mode': 'board_speed', 'speed_m1_m2_qpps': [speeds[1], speeds[0]],
            'accel_qpps2': self.accel_qpps2, 'board_pwm_m1_m2': row.get('pwms'),
            'currents_m1_m2_a': row.get('currents_a')}
        self._record('control', self.last_control)

    def _watch_board_stall(self, index, speed_qpps, measured_rad_s, row, now):
        """board_speed의 잠김: 목표 속도가 있는데 엔코더가 stall_seconds 동안 0.

        속도 추정 창 안에 한 카운트도 안 들어올 만큼 작은 목표는 0으로 보여도 정상이므로 세지 않는다.
        """
        measurable = abs(speed_qpps) * self.s['velocity_window_s'] >= 1.0
        if measurable and measured_rad_s == 0.0:
            if self.stall_since[index] is None:
                self.stall_since[index] = now
            elif now - self.stall_since[index] >= self.s['stall_seconds'] and not self.stalled[index]:
                self.stalled[index] = True
                self._event('stall', wheel='left' if index == 0 else 'right', speed_qpps=speed_qpps,
                            board_pwm_m1_m2=row.get('pwms'), currents_m1_m2_a=row.get('currents_a'),
                            seconds=now - self.stall_since[index])
        else:
            self.stall_since[index] = None

    def _runs_wrong_way(self, index, speed_qpps, measured_rad_s):
        """목표와 반대 방향으로 '점점 빨라지는' 틱이 MAX_CONSECUTIVE_ERRORS번 이어지면 참.

        방향을 바꾸는 중에도 잠깐 반대로 돌지만 그때는 느려진다. 빨라진다면 보드가 엔코더를 거꾸로 읽어 출력을 계속 올리는 것이다.
        """
        speed = abs(measured_rad_s)
        opposite = speed_qpps != 0 and measured_rad_s != 0.0 and (measured_rad_s > 0) != (speed_qpps > 0)
        growing = speed > self.wrong_way_speed[index]
        self.wrong_way_speed[index] = speed
        self.wrong_way[index] = self.wrong_way[index] + 1 if opposite and growing else 0
        return self.wrong_way[index] >= MAX_CONSECUTIVE_ERRORS

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
        values = {'state': self.state, 'control_mode': self.s['control_mode'],
                  'encoder_forward_signs_m1_m2': self.forward_signs,
                  'board_qpps_m1_m2': [v['qpps'] for v in self.velocity_settings] if self.velocity_settings else '',
                  'battery_volts': self.battery_volts, 'battery_low': self.battery_low,
                  'command_timeout_s': self.command_timeout_s, 'max_duty_raw': self.s['max_duty_raw'],
                  'board_stop_bits': ','.join(self.board_stop), 'board_notes': ','.join(self.board_notes),
                  'stalled_left_right': self.stalled, 'transient_serial_errors': self.transient_errors,
                  'person_wait': self.person_wait, 'person_wait_reason': self.person_wait_reason,
                  'errors': ' | '.join(self.errors)}
        if self.last_control:
            for key in ('command', 'target_left_right_rad_s', 'measured_left_right_rad_s', 'duty_m1_m2',
                        'straight_start_phase', 'left_rise_scale', 'board_pwm_m1_m2', 'currents_m1_m2_a'):
                values[key] = self.last_control[key]
            if 'speed_m1_m2_qpps' in self.last_control:
                values['speed_m1_m2_qpps'] = self.last_control['speed_m1_m2_qpps']
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
