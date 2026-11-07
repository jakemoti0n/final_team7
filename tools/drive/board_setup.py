#!/usr/bin/env python3
"""RoboClaw 보드 설정 도구: 보드 속도 제어(control_mode: board_speed)에 필요한 값을 젯슨에서 직접 넣고 확인한다.

모션스튜디오(윈도우) 없이 같은 일을 한다. 모든 단계는 바퀴를 띄운 상태에서, 한 단계씩 결과를 보고 다음으로 간다.
젯슨에서: source limbo/install/setup.bash 뒤 python3 tools/drive/board_setup.py <단계> [--record ~/limbo_bags/board_setup]

단계(순서대로)
  backup   지금 설정(엔코더 모드, 속도 PID·QPPS, 전압 한도, 속도 오차 한계, 명령 timeout)을 읽어 JSON으로 저장
  encoder  M2(왼쪽) 엔코더 방향 반전 비트만 켜고, 10 % 출력으로 두 바퀴를 앞으로 돌려 두 엔코더가 모두 증가하는지 확인
  qpps     모터별로 출력을 25·50·75·100 %로 올려 각각의 속도(카운트/초)를 재고 100 %일 때 값을 QPPS로 기록
  pid      속도 제어 값을 쓴다: --p --i --d (기본은 매뉴얼의 기본값 1.0 / 0.5 / 0.25), QPPS는 qpps 단계 결과 또는 --qpps
  voltage  주전원 한도: --min 10.0 --max 16.0 (납축 12 V 보호. 5.9 V 기본값으로는 배터리를 못 지킨다)
  save     보드 비휘발 메모리에 저장(보드가 재시작됨) → 다시 연결해 전부 읽어 비교
  step     보드 속도 제어로 계단 명령(기본 0.03 0.07 0.13 m/s, 앞·뒤)을 보내 도달 시간·넘침·정상 오차·멈춤을 잰다
  restore  --from <backup.json>: 백업한 설정을 그대로 되돌려 쓰고 저장

모든 단계는 record 폴더에 <단계>_<시각>.jsonl(표본)과 .json(요약)을 남긴다.
"""
import argparse
import json
import math
from pathlib import Path
import statistics
import struct
import sys
import time

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'limbo/src/limbo_hardware'))
from limbo_hardware.roboclaw_drive import (DriveTransport, DriveError, DUTY_FULL, PID_SCALE,   # noqa: E402
                                           STOP_STATUS_BITS, status_names)
from limbo_hardware.roboclaw_readonly import (CounterTracker, ENCODER_REVERSED_BIT, MOTOR_REVERSED_BIT,  # noqa: E402
                                              RoboClawError, forward_signs)

CONFIG = Path(__file__).resolve().parents[2] / 'limbo/src/limbo_hardware/config'
NVM_KEY = 0xE22EAB7A           # 명령 94의 실수 방지 키(매뉴얼)
MANUAL_DEFAULT_PID = (1.0, 0.5, 0.25)   # 매뉴얼 "명령 28"의 기본값. 출발점일 뿐, step 단계 결과로 바꾼다
SAMPLE_PERIOD_S = 0.05         # 주행 노드와 같은 20 Hz로 재서 기록을 바로 비교할 수 있게
MOTOR_NAMES = ('M1(오른쪽)', 'M2(왼쪽)')


# ---------- 패킷 (바이트 순서는 매뉴얼 rev 6.0) ----------
def pid_payload(p, i, d, qpps):
    """명령 28·29: D, P, I, QPPS 순서(매뉴얼이 이 순서다. P부터가 아니다)."""
    if any(not math.isfinite(v) or v < 0 or v * PID_SCALE > 0xffffffff for v in (p, i, d)):
        raise ValueError('P·I·D는 0 이상, 65535 이하')
    if type(qpps) is not int or not 1 <= qpps <= 0xffffffff:
        raise ValueError('QPPS는 1 이상의 정수')
    return struct.pack('>IIII', round(d * PID_SCALE), round(p * PID_SCALE), round(i * PID_SCALE), qpps)


def voltage_payload(min_v, max_v, auto_offset_v=2.0):
    """명령 57: 최소·최대(0.1 V 단위, 2바이트씩), 자동 최대 오프셋(0.1 V, 1바이트)."""
    if not 6.0 <= min_v < max_v <= 34.0:
        raise ValueError('전압 한도는 6.0 ≤ 최소 < 최대 ≤ 34.0 V (2x15A 입력 범위)')
    return struct.pack('>HHB', round(min_v * 10), round(max_v * 10), round(auto_offset_v * 10))


def encoder_mode_payload(mode):
    if type(mode) is not int or not 0 <= mode <= 255:
        raise ValueError('엔코더 모드는 0..255')
    return bytes((mode,))


def nvm_payload():
    return struct.pack('>I', NVM_KEY)


def full_duty(transport, m1, m2):
    """명령 34를 주행 상한(30 %) 없이 보낸다. qpps 단계 전용: QPPS는 정의상 "100 % 출력일 때 속도"라 100 %로 돌려야 하고,
    바퀴를 띄운 무부하 상태에서 모터 정격 전압 그대로이므로 모터에 무리가 없다. 바닥 주행에는 쓰지 않는다."""
    if any(type(v) is not int or abs(v) > DUTY_FULL for v in (m1, m2)):
        raise ValueError('duty는 ±%d 안의 정수' % DUTY_FULL)
    return transport.write_setting(34, struct.pack('>hh', m1, m2))


# ---------- 보드 읽기 ----------
def read_all(transport):
    modes = transport.read_encoder_modes()
    velocity = transport.read_velocity_settings()
    volt = transport.query(59)
    limits = struct.unpack('>II', transport.query(110))
    return {'firmware': transport.firmware,
            'encoder_modes': list(modes),
            'forward_signs_m1_m2': list(forward_signs(modes)),
            'velocity_m1_m2': velocity,
            'main_voltage_min_v': int.from_bytes(volt[0:2], 'big') / 10.0,
            'main_voltage_max_v': int.from_bytes(volt[2:4], 'big') / 10.0,
            'main_voltage_auto_offset_v': volt[4] / 10.0,
            'speed_error_limits_m1_m2': list(limits),
            'command_timeout_s': transport.read_timeout_s(),
            'battery_volts': transport.read_battery_volts()}


def load_geometry():
    odom = yaml.safe_load((CONFIG / 'wheel_odometry.yaml').read_text())['wheel_odometry']['ros__parameters']
    enc = yaml.safe_load((CONFIG / 'encoders_readonly.yaml').read_text())['roboclaw_encoder']['ros__parameters']
    # 보드 순서 [M1=오른쪽, M2=왼쪽]
    return {'radius': (odom['right_wheel_radius'], odom['left_wheel_radius']),
            'cpr': (enc['right_counts_per_revolution'], enc['left_counts_per_revolution'])}


def counts_per_s(m_per_s, geometry, index):
    return round(m_per_s / geometry['radius'][index] / math.tau * geometry['cpr'][index])


def m_per_s(counts_s, geometry, index):
    return counts_s / geometry['cpr'][index] * math.tau * geometry['radius'][index]


# ---------- 표본 수집 ----------
class Session:
    """연결 하나 + 기록 파일. 모든 모터 동작은 run()이 20 Hz로 표본을 남기고, 끝나면 반드시 duty 0."""

    def __init__(self, args, stage):
        self.args = args
        self.record = Path(args.record).expanduser()
        self.record.mkdir(parents=True, exist_ok=True)
        self.stamp = time.strftime('%m%d_%H%M%S')
        self.stage = stage
        self.samples = (self.record / f'{stage}_{self.stamp}.jsonl').open('w')
        self.transport = None
        self.tracker = None

    def connect(self):
        return DriveTransport(port=self.args.port)   # duty 상한은 주행과 같은 30 %. 100 %는 full_duty()만

    def open(self):
        self.transport = self.connect()
        self.transport.open()
        self.transport.ensure_timeout()
        try:
            self.tracker = CounterTracker(forward_signs(self.transport.read_encoder_modes()))
        except RoboClawError as error:
            raise DriveError(str(error)) from error
        return self.transport

    def reopen_after_reset(self, wait_s=15.0):
        """명령 94 뒤 보드가 재시작돼 USB가 끊긴다. 장치가 다시 보일 때까지 기다렸다가 새로 연다."""
        try:
            self.transport.serial.close()
        except Exception:
            pass
        self.transport.closed = True
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            time.sleep(0.5)
            try:
                return self.open()
            except Exception:
                continue
        raise DriveError('보드 재시작 뒤 %.0f s 안에 다시 연결되지 않음' % wait_s)

    def run(self, seconds, command, label):
        """seconds 동안 20 Hz로 command(transport)를 다시 보내며 표본을 남기고 반환(보드 명령 timeout 0.5 s 안에 계속 보내야
        출력이 유지된다 — 주행 노드와 같은 방식). 표본: 시각, 카운트, 전진 카운트/초, PWM, 전류, 상태."""
        transport, tracker = self.transport, self.tracker
        rows = []
        start = transport.clock()   # 표본 시각과 같은 시계(시험에서는 가짜 시계)
        previous = None
        while True:
            command(transport)
            sample = transport.sample()
            reading = tracker.update(tuple(sample['counts']))
            now = sample['monotonic_s']
            speed = [0.0, 0.0]
            if previous is not None and now > previous[0]:
                speed = [(b - a) / (now - previous[0]) for a, b in zip(previous[1], reading.signed_forward_total)]
            previous = (now, reading.signed_forward_total)
            row = {'label': label, 't': now - start, 'counts': sample['counts'],
                   'forward_total': list(reading.signed_forward_total), 'speed_counts_s': speed,
                   'pwm_pct': [v / 327.67 for v in sample['pwms']], 'currents_a': sample['currents_a'],
                   'status': sample['status_hex'], 'stop_reasons': sample['stop_reasons']}
            rows.append(row)
            self.samples.write(json.dumps(row) + '\n')
            if sample['stop_reasons']:
                transport.stop()
                raise DriveError('보드 상태가 출력을 막음: %s' % sample['stop_reasons'])
            if now - start >= seconds:
                break
            time.sleep(max(0.0, SAMPLE_PERIOD_S - (transport.clock() - now)))
        return rows

    def hold_zero(self, seconds):
        return self.run(seconds, lambda t: t.write_duty(0, 0), 'zero')

    def summary(self, data):
        path = self.record / f'{self.stage}_{self.stamp}.json'
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1))
        print(json.dumps(data, ensure_ascii=False, indent=1))
        print('저장:', path)
        return path

    def close(self):
        if self.transport is not None:
            acked = self.transport.close()
            print('출력 0 확인:', acked)
        self.samples.close()


# ---------- 단계 ----------
def stage_backup(session):
    data = read_all(session.open())
    return session.summary(data)


def stage_encoder(session):
    """M2 엔코더 방향 반전 비트만 켠다(다른 비트는 그대로). 그 다음 두 바퀴를 앞으로 돌려 둘 다 증가하는지 본다."""
    transport = session.open()
    before = read_all(transport)
    modes = list(before['encoder_modes'])
    if any(mode & MOTOR_REVERSED_BIT for mode in modes):
        raise DriveError('모터 방향 반전 비트가 켜져 있음 — 건드리지 않고 멈춤')
    wanted = [modes[0], modes[1] | ENCODER_REVERSED_BIT]
    if modes != wanted:
        transport.write_setting(93, encoder_mode_payload(wanted[1]))
    after_modes = list(transport.read_encoder_modes())
    if after_modes != wanted:
        raise DriveError('엔코더 모드가 반영되지 않음: %s' % after_modes)
    session.tracker = CounterTracker(forward_signs(after_modes))
    duty = round(DUTY_FULL * session.args.check_duty_pct / 100)
    session.hold_zero(0.3)
    rows = session.run(session.args.check_seconds, lambda t: t.write_duty(duty, duty), 'forward_check')
    session.hold_zero(0.5)
    moved = rows[-1]['forward_total']
    both_forward = all(v > 50 for v in moved)
    data = {'encoder_modes_before': modes, 'encoder_modes_after': after_modes,
            'forward_signs_m1_m2': list(forward_signs(after_modes)),
            'check_duty_pct': session.args.check_duty_pct, 'check_seconds': session.args.check_seconds,
            'forward_counts_m1_m2': moved, 'both_increase_forward': both_forward,
            'peak_pwm_pct': [max(abs(r['pwm_pct'][i]) for r in rows) for i in (0, 1)],
            'peak_current_a': [max(abs(r['currents_a'][i]) for r in rows) for i in (0, 1)]}
    session.summary(data)
    if not both_forward:
        raise DriveError('앞으로 돌렸는데 두 엔코더가 모두 증가하지 않음 %s — 배선 확인 필요' % moved)


def stage_qpps(session):
    """모터 하나씩, 출력 25·50·75·100 %에서 속도(카운트/초)를 잰다. QPPS = 100 %에서 뒤 절반 평균."""
    transport = session.open()
    if forward_signs(transport.read_encoder_modes()) != (1, 1):
        raise DriveError('encoder 단계를 먼저 끝내야 함(두 엔코더 모두 전진 +)')
    geometry = load_geometry()
    result = {'battery_volts_before': transport.read_battery_volts(), 'levels': {}, 'qpps_m1_m2': [0, 0]}
    for index in (0, 1):
        for pct in session.args.levels:
            duty = round(DUTY_FULL * pct / 100)
            pair = [duty if k == index else 0 for k in (0, 1)]
            rows = session.run(session.args.level_seconds, lambda t: full_duty(t, *pair), f'm{index + 1}_{pct}pct')
            settled = rows[len(rows) // 2:]
            speed = statistics.mean(r['speed_counts_s'][index] for r in settled)
            result['levels'][f'{MOTOR_NAMES[index]} {pct} %'] = {
                'counts_s': round(speed), 'm_s': round(m_per_s(speed, geometry, index), 3),
                'current_a': round(statistics.mean(abs(r['currents_a'][index]) for r in settled), 2),
                'pwm_pct': round(statistics.mean(abs(r['pwm_pct'][index]) for r in settled), 1)}
            if pct == max(session.args.levels):
                result['qpps_m1_m2'][index] = round(speed)
            session.hold_zero(1.0)
    result['battery_volts_after'] = transport.read_battery_volts()
    result['qpps_note'] = ('100 %%가 아니라 %d %%에서 쟀으면 QPPS는 그 값을 비례로 올린 것이 아니라 그대로다. 보드는 QPPS를 '
                           '"100 %%일 때 속도"로 쓰므로 반드시 100 %%에서 잰 값을 넣는다' % max(session.args.levels))
    session.summary(result)


def stage_pid(session):
    transport = session.open()
    qpps = session.args.qpps
    if qpps is None:
        latest = sorted(Path(session.record).glob('qpps_*.json'))
        if not latest:
            raise DriveError('--qpps M1 M2 를 주거나 qpps 단계를 먼저 돌려야 함')
        qpps = json.loads(latest[-1].read_text())['qpps_m1_m2']
        print('QPPS를 %s 에서 읽음: %s' % (latest[-1].name, qpps))
    if any(type(v) is not int or v < 1 for v in qpps):
        raise DriveError('QPPS 두 값은 1 이상 정수여야 함: %s' % qpps)
    p, i, d = session.args.p, session.args.i, session.args.d
    for command, value in ((28, qpps[0]), (29, qpps[1])):
        transport.write_setting(command, pid_payload(p, i, d, value))
    after = transport.read_velocity_settings()
    wanted = [{'p': p, 'i': i, 'd': d, 'qpps': q} for q in qpps]
    ok = all(abs(a[k] - w[k]) < 1e-4 for a, w in zip(after, wanted) for k in ('p', 'i', 'd')) and \
        [a['qpps'] for a in after] == qpps
    session.summary({'written_m1_m2': wanted, 'read_back_m1_m2': after, 'match': ok,
                     'note': '보드 메모리(RAM)에만 있음. save 단계 전에 전원이 꺼지면 사라진다'})
    if not ok:
        raise DriveError('읽어 보니 쓴 값과 다름')


def stage_voltage(session):
    transport = session.open()
    transport.write_setting(57, voltage_payload(session.args.min, session.args.max))
    after = read_all(transport)
    ok = abs(after['main_voltage_min_v'] - session.args.min) < 0.05 and abs(after['main_voltage_max_v'] - session.args.max) < 0.05
    session.summary({'written': {'min_v': session.args.min, 'max_v': session.args.max},
                     'read_back': {k: after[k] for k in ('main_voltage_min_v', 'main_voltage_max_v', 'main_voltage_auto_offset_v')},
                     'battery_volts_now': after['battery_volts'], 'match': ok})
    if not ok:
        raise DriveError('읽어 보니 쓴 값과 다름')


def stage_save(session):
    transport = session.open()
    before = read_all(transport)
    transport.stop()
    try:
        transport.write_setting(94, nvm_payload())
    except DriveError as error:
        print('저장 명령 응답 없음(보드가 바로 재시작하면 정상):', error)
    transport = session.reopen_after_reset()
    after = read_all(transport)
    keys = ('encoder_modes', 'velocity_m1_m2', 'main_voltage_min_v', 'main_voltage_max_v', 'speed_error_limits_m1_m2')
    same = {k: before[k] == after[k] for k in keys}
    session.summary({'before_save': before, 'after_reset': after, 'kept': same, 'all_kept': all(same.values())})
    if not all(same.values()):
        raise DriveError('재시작 뒤 값이 달라짐: %s' % [k for k, v in same.items() if not v])


def step_metrics(rows, target, geometry, index):
    """계단 응답 하나의 지표. 도달: 목표의 90 %를 처음 넘는 시각. 넘침: 최대치가 목표를 넘은 비율. 정상 오차: 뒤 1 s 평균."""
    speeds = [r['speed_counts_s'][index] for r in rows]
    sign = 1 if target > 0 else -1
    reach = next((r['t'] for r, s in zip(rows, speeds) if s * sign >= abs(target) * 0.9), None)
    peak = max(s * sign for s in speeds)
    tail = [s for r, s in zip(rows, speeds) if r['t'] >= rows[-1]['t'] - 1.0]
    steady = statistics.mean(tail) if tail else 0.0
    stalled = sum(1 for r, s in zip(rows, speeds) if r['t'] > 0.5 and s == 0.0) * SAMPLE_PERIOD_S
    return {'target_counts_s': target, 'target_m_s': round(m_per_s(target, geometry, index), 3),
            'reach_90pct_s': None if reach is None else round(reach, 2),
            'overshoot_pct': round((peak / abs(target) - 1) * 100, 1) if target else 0.0,
            'steady_m_s': round(m_per_s(steady, geometry, index), 3),
            'steady_error_pct': round((steady / target - 1) * 100, 1) if target else 0.0,
            'stalled_after_0_5s_s': round(stalled, 2),
            'peak_pwm_pct': round(max(abs(r['pwm_pct'][index]) for r in rows), 1),
            'peak_current_a': round(max(abs(r['currents_a'][index]) for r in rows), 2)}


def stage_step(session):
    transport = session.open()
    settings = transport.read_velocity_settings()
    if transport.speed_caps is None or any(s['p'] == 0 and s['i'] == 0 for s in settings):
        raise DriveError('보드에 속도 제어 값이 없음 — pid 단계 먼저')
    if forward_signs(transport.read_encoder_modes()) != (1, 1):
        raise DriveError('두 엔코더가 모두 전진 +가 아님 — encoder 단계 먼저')
    geometry = load_geometry()
    accel = [max(1, round(session.args.accel_rad_s2 / math.tau * geometry['cpr'][i])) for i in (0, 1)]
    results = {'velocity_m1_m2': settings, 'accel_counts_s2_m1_m2': accel, 'battery_volts': transport.read_battery_volts(),
               'steps': []}
    for speed in session.args.speeds:
        for direction in (1, -1):
            targets = [direction * counts_per_s(speed, geometry, i) for i in (0, 1)]
            label = '%s%.2f' % ('+' if direction > 0 else '-', speed)
            rows = session.run(session.args.step_seconds,
                               lambda t: t.write_speed(targets[0], targets[1], max(accel)), label)
            session.run(1.0, lambda t: t.write_speed(0, 0, max(accel)), label + '_to_zero')
            session.hold_zero(0.5)
            results['steps'].append({'label': label, MOTOR_NAMES[0]: step_metrics(rows, targets[0], geometry, 0),
                                     MOTOR_NAMES[1]: step_metrics(rows, targets[1], geometry, 1)})
    session.summary(results)
    print('\n계단 | 모터 | 목표 m/s | 90 % 도달 s | 넘침 % | 정상 m/s | 오차 % | 멈춤 s | 최대 PWM % | 최대 A')
    for step in results['steps']:
        for name in MOTOR_NAMES:
            m = step[name]
            print('%5s | %s | %+.3f | %5s | %6.1f | %+.3f | %6.1f | %4.2f | %5.1f | %4.2f' % (
                step['label'], name, m['target_m_s'], m['reach_90pct_s'], m['overshoot_pct'], m['steady_m_s'],
                m['steady_error_pct'], m['stalled_after_0_5s_s'], m['peak_pwm_pct'], m['peak_current_a']))


def stage_restore(session):
    saved = json.loads(Path(session.args.source).expanduser().read_text())
    transport = session.open()
    for command, mode in zip((92, 93), saved['encoder_modes']):
        transport.write_setting(command, encoder_mode_payload(mode))
    for command, v in zip((28, 29), saved['velocity_m1_m2']):
        if v['qpps'] >= 1:
            transport.write_setting(command, pid_payload(v['p'], v['i'], v['d'], v['qpps']))
        else:   # QPPS 0은 pid_payload가 거부하므로 "속도 제어 없음" 상태로 직접 되돌린다
            transport.write_setting(command, struct.pack('>IIII', round(v['d'] * PID_SCALE), round(v['p'] * PID_SCALE),
                                                         round(v['i'] * PID_SCALE), 0))
    transport.write_setting(57, struct.pack('>HHB', round(saved['main_voltage_min_v'] * 10),
                                            round(saved['main_voltage_max_v'] * 10), round(saved['main_voltage_auto_offset_v'] * 10)))
    now = read_all(transport)
    session.summary({'restored_from': session.args.source, 'now': now})
    print('되돌린 값은 RAM에만 있음. 영구히 하려면 save 단계를 이어서 실행')


STAGES = {'backup': stage_backup, 'encoder': stage_encoder, 'qpps': stage_qpps, 'pid': stage_pid,
          'voltage': stage_voltage, 'save': stage_save, 'step': stage_step, 'restore': stage_restore}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=__doc__)
    parser.add_argument('stage', choices=STAGES)
    parser.add_argument('--port', default='/dev/serial/by-id/usb-Basicmicro_Inc._USB_Roboclaw_2x15A-if00')
    parser.add_argument('--record', default='~/limbo_bags/board_setup')
    parser.add_argument('--check-duty-pct', type=float, default=10.0, help='encoder: 확인 회전 출력 %%. 띄운 바퀴는 10 %%로 돈다')
    parser.add_argument('--check-seconds', type=float, default=1.5)
    parser.add_argument('--levels', type=float, nargs='+', default=[25, 50, 75, 100], help='qpps: 출력 %% 단계')
    parser.add_argument('--level-seconds', type=float, default=2.0)
    parser.add_argument('--p', type=float, default=MANUAL_DEFAULT_PID[0])
    parser.add_argument('--i', type=float, default=MANUAL_DEFAULT_PID[1])
    parser.add_argument('--d', type=float, default=MANUAL_DEFAULT_PID[2])
    parser.add_argument('--qpps', type=int, nargs=2, metavar=('M1', 'M2'))
    parser.add_argument('--min', type=float, default=10.0, help='voltage: 최소 V. drive.yaml의 min_battery_volts와 같게')
    parser.add_argument('--max', type=float, default=16.0, help='voltage: 최대 V. 12 V 납축 충전 전압(14.4~14.8)보다 위, 충전기 무부하 29 V보다 아래')
    parser.add_argument('--speeds', type=float, nargs='+', default=[0.03, 0.07, 0.13],
                        help='step: m/s. 0.03은 11-06에 바퀴가 서던 목표, 0.13은 Nav2 상한')
    parser.add_argument('--step-seconds', type=float, default=3.0)
    parser.add_argument('--accel-rad-s2', type=float, default=2.0, help='step: drive.yaml target_slew_rad_s2와 같게')
    parser.add_argument('--from', dest='source', help='restore: 백업 JSON 경로')
    args = parser.parse_args()
    if args.stage == 'restore' and not args.source:
        parser.error('restore에는 --from <backup.json>이 필요')
    session = Session(args, args.stage)
    try:
        STAGES[args.stage](session)
    finally:
        session.close()


if __name__ == '__main__':
    main()
