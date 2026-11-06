#!/usr/bin/env python3
"""주행 기록(roboclaw_drive의 record_dir) 요약: 바퀴가 목표 속도를 얼마나 따라갔는지 한눈에 본다.

사용법: drive_report.py <record_dir 또는 control.jsonl> [--min-target 0.03] [--start-mm 5]

보는 것 (11-06 목표점 주행 시험 기록과 같은 항목이라 앞뒤를 바로 비교할 수 있다)
- 출발 지연: 서 있다가 목표가 생긴 순간부터 각 바퀴가 start-mm만큼 구를 때까지 걸린 시간
- 속도 추종: 목표가 일정한 구간별 목표·실측 속도와 오차
- 서 버린 시간: 목표가 min-target 이상인데 바퀴가 안 도는 시간 (저속 사각지대)
- 좌우 이동량, 그 차이로 본 방향 변화, 모터 전류, 보드 출력, 배터리 최저 전압, 멈춘 이유

바퀴 치수와 1회전 카운트는 설정 파일(wheel_odometry.yaml, encoders_readonly.yaml)에서 읽는다.
"""
import argparse
import collections
import json
import math
from pathlib import Path
import statistics

import yaml

CONFIG = Path(__file__).resolve().parents[2] / 'limbo/src/limbo_hardware/config'


def load_geometry():
    odom = yaml.safe_load((CONFIG / 'wheel_odometry.yaml').read_text())['wheel_odometry']['ros__parameters']
    enc = yaml.safe_load((CONFIG / 'encoders_readonly.yaml').read_text())['roboclaw_encoder']['ros__parameters']
    return {'radius': (odom['left_wheel_radius'], odom['right_wheel_radius']),   # [왼쪽, 오른쪽]
            'separation': odom['wheel_separation'],
            'cpr': (enc['left_counts_per_revolution'], enc['right_counts_per_revolution'])}


def load_rows(path):
    path = Path(path).expanduser()
    if path.is_dir():
        path = path / 'control.jsonl'
    return [json.loads(line) for line in path.open()]


def wheel_metres(row, geometry):
    """누적 카운트를 바퀴별 이동 거리 [왼쪽, 오른쪽] m로."""
    return [row[key] * math.tau * geometry['radius'][i] / geometry['cpr'][i]
            for i, key in enumerate(('left_total', 'right_total'))]


def start_delays(rows, geometry, start_m):
    """(시작 시각, [왼쪽 지연, 오른쪽 지연]) 목록. 지연이 None이면 그 출발에서 끝까지 start_m을 못 굴렀다."""
    result = []
    waiting = None    # 출발 중: (시작 시각, 시작 위치, [지연, 지연])
    stopped = True
    for row in rows:
        targets = row['target_left_right_rad_s']
        measured = row['measured_left_right_rad_s']
        if waiting is None:
            if stopped and any(targets):
                waiting = (row['monotonic_s'], wheel_metres(row, geometry), [None, None])
            stopped = not any(targets) and not any(measured)
            continue
        began, origin, delays = waiting
        position = wheel_metres(row, geometry)
        for i in (0, 1):
            wanted = targets[i]
            if delays[i] is None and wanted and (position[i] - origin[i]) * math.copysign(1, wanted) >= start_m:
                delays[i] = row['monotonic_s'] - began
        done = all(delay is not None or not targets[i] for i, delay in enumerate(delays))
        if done or not any(targets):
            result.append((began, delays))
            waiting = None
            stopped = not any(targets) and not any(measured)
    if waiting is not None:
        result.append((waiting[0], waiting[2]))
    return result


def steady_segments(rows, geometry, minimum_s=1.0):
    """목표가 그대로인 구간(1 s 이상)별 평균. 가속이 끝난 뒤를 보려고 구간 앞 절반은 뺀다."""
    segments = []
    start = 0
    for index in range(1, len(rows) + 1):
        ended = index == len(rows) or rows[index]['target_left_right_rad_s'] != rows[start]['target_left_right_rad_s']
        if not ended:
            continue
        chunk = rows[start:index]
        start = index
        targets = chunk[0]['target_left_right_rad_s']
        if not any(targets) or chunk[-1]['monotonic_s'] - chunk[0]['monotonic_s'] < minimum_s:
            continue
        settled = chunk[len(chunk) // 2:]
        measured = [statistics.mean(r['measured_left_right_rad_s'][i] for r in settled) for i in (0, 1)]
        segments.append({
            'seconds': chunk[-1]['monotonic_s'] - chunk[0]['monotonic_s'],
            'target_m_s': [targets[i] * geometry['radius'][i] for i in (0, 1)],
            'measured_m_s': [measured[i] * geometry['radius'][i] for i in (0, 1)]})
    return segments


def stopped_seconds(rows, geometry, min_target_m_s):
    """목표가 min_target 이상인데 그 바퀴 실측이 0인 시간 [왼쪽, 오른쪽] s."""
    total = [0.0, 0.0]
    for row in rows:
        for i in (0, 1):
            target = abs(row['target_left_right_rad_s'][i]) * geometry['radius'][i]
            if target >= min_target_m_s and row['measured_left_right_rad_s'][i] == 0.0:
                total[i] += row['dt']
    return total


def report(rows, geometry, min_target, start_m):
    lines = []
    seconds = rows[-1]['monotonic_s'] - rows[0]['monotonic_s']
    driving = [r for r in rows if any(r['target_left_right_rad_s'])]
    modes = collections.Counter(r.get('control_mode', 'host_duty') for r in rows)
    lines.append('기록 %.0f s, 표본 %d개, 목표가 있던 시간 %.0f s, 제어 방식 %s' % (
        seconds, len(rows), sum(r['dt'] for r in driving), dict(modes)))

    travel = [b - a for a, b in zip(wheel_metres(rows[0], geometry), wheel_metres(rows[-1], geometry))]
    heading = math.degrees((travel[1] - travel[0]) / geometry['separation'])
    lines.append('이동량 왼쪽 %.3f m, 오른쪽 %.3f m, 차이 %+.3f m → odom 방향 변화 %+.1f°' % (
        travel[0], travel[1], travel[1] - travel[0], heading))

    delays = start_delays(rows, geometry, start_m)
    lines.append('출발 %d번 (목표가 생긴 뒤 %g mm 구를 때까지, s):' % (len(delays), start_m * 1000))
    show = lambda value: ' 못 감' if value is None else '%5.2f' % value
    for began, (left, right) in delays[:12]:
        lines.append('  t=%7.1f  왼쪽 %s  오른쪽 %s' % (began - rows[0]['monotonic_s'], show(left), show(right)))
    reached = [[d[i] for _, d in delays if d[i] is not None] for i in (0, 1)]
    if any(reached):
        lines.append('  중앙값 왼쪽 %s, 오른쪽 %s / 최대 왼쪽 %s, 오른쪽 %s' % (
            *(show(statistics.median(v)) if v else '    -' for v in reached),
            *(show(max(v)) if v else '    -' for v in reached)))

    segments = steady_segments(rows, geometry)
    lines.append('목표가 일정했던 구간 %d개 (구간 뒤 절반의 평균, m/s):' % len(segments))
    lines.append('   길이 s | 목표 왼쪽  오른쪽 | 실측 왼쪽  오른쪽 | 오차 왼쪽  오른쪽')
    for seg in sorted(segments, key=lambda s: -s['seconds'])[:12]:
        error = [m - t for m, t in zip(seg['measured_m_s'], seg['target_m_s'])]
        lines.append('   %6.1f | %+.3f  %+.3f | %+.3f  %+.3f | %+.3f  %+.3f' % (
            seg['seconds'], *seg['target_m_s'], *seg['measured_m_s'], *error))

    stuck = stopped_seconds(rows, geometry, min_target)
    lines.append('목표 %.2f m/s 이상인데 안 돈 시간: 왼쪽 %.2f s, 오른쪽 %.2f s' % (min_target, *stuck))

    with_current = [r for r in driving if r.get('currents_m1_m2_a')]
    if with_current:
        for name, index in (('오른쪽(M1)', 0), ('왼쪽(M2)', 1)):
            amps = [abs(r['currents_m1_m2_a'][index]) for r in with_current]
            pwm = [abs(r['board_pwm_m1_m2'][index]) / 327.67 for r in with_current]
            lines.append('%s 전류 평균 %.2f A, 최대 %.2f A / 보드 출력 평균 %.1f %%, 최대 %.1f %%' % (
                name, statistics.mean(amps), max(amps), statistics.mean(pwm), max(pwm)))
    else:
        lines.append('전류·보드 출력 기록 없음 (변경 기록 55 이전 기록)')

    volts = [r['battery_volts'] for r in rows if r.get('battery_volts') is not None]
    if volts:
        lines.append('배터리 최저 %.1f V, 최고 %.1f V' % (min(volts), max(volts)))
    reasons = collections.Counter(reason for r in rows for reason in r['reasons'])
    lines.append('멈춘 이유(표본 수): ' + (', '.join('%s %d' % item for item in reasons.most_common()) or '없음'))
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('record')
    parser.add_argument('--min-target', type=float, default=0.03,
                        help='이 속도(m/s) 이상의 목표에서 바퀴가 서 있으면 센다. 0.03은 11-06 시험에서 바퀴가 서던 목표 크기')
    parser.add_argument('--start-mm', type=float, default=5.0,
                        help='출발했다고 보는 이동 거리(mm). 11-06 기록의 "5mm forward crossing"과 같은 기준')
    args = parser.parse_args()
    rows = load_rows(args.record)
    if len(rows) < 2:
        raise SystemExit('표본이 2개 미만이라 요약할 수 없음')
    print(report(rows, load_geometry(), args.min_target, args.start_mm / 1000.0))


if __name__ == '__main__':
    main()
