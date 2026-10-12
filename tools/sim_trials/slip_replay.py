"""녹화한 주행 데이터로 헛돎 판단을 재현하고 정답 위치와 비교한다.

사용법: slip_replay.py <slip_*.pkl> [<pkl> ...]
wheel_slip_monitor와 같은 모듈(scan_motion, slip)과 같은 설정값을 쓴다.
0.5초 구간마다 정답 이동 거리가 바퀴 이동의 30% 미만이면 '진짜 헛돎'으로 본다.
"""
import bisect
import math
import os
import pickle
import sys

from limbo_monitor import scan_motion, slip

CHECK_PERIOD = 0.5
RANGE_MIN, RANGE_MAX = 0.1, 10.0
ICP = scan_motion.IcpConfig()
SLIP_CFG = slip.SlipConfig()


def yaw(z, w):
    return 2 * math.atan2(z, w)


def nearest(series, t):
    times = [s[0] for s in series]
    i = min(max(bisect.bisect_left(times, t), 1), len(times) - 1)
    return series[i] if abs(series[i][0] - t) < abs(series[i - 1][0] - t) else series[i - 1]


LATENCY = float(os.environ.get('LATENCY', '0'))


def windows(data):
    """노드와 같은 방식으로 0.5초마다 (바퀴 이동, 회전, 스캔 추정, 정답 이동)을 만든다.
    LATENCY: 노드는 스캔이 도착한 순간의 최신 odom을 쓰므로, 스캔 지연만큼 늦은 odom을 고른다"""
    ref = None
    for t, amin, ainc, ranges in data['scan']:
        points = scan_motion.scan_to_points(ranges, amin, ainc, RANGE_MIN, RANGE_MAX)
        odom, truth = nearest(data['odom'], t + LATENCY), nearest(data['truth'], t)
        if ref is None:
            ref = (t, points, odom, truth)
            continue
        if t - ref[0] < CHECK_PERIOD:
            continue
        r_t, r_points, r_odom, r_truth = ref
        wheel = math.hypot(odom[1] - r_odom[1], odom[2] - r_odom[2])
        rotation = math.remainder(yaw(*odom[3:]) - yaw(*r_odom[3:]), 2 * math.pi)
        motion = scan_motion.estimate_motion(r_points, points, ICP)
        true_move = math.hypot(truth[1] - r_truth[1], truth[2] - r_truth[2])
        yield t, wheel, rotation, motion, true_move, (truth[1], truth[2])
        ref = (t, points, odom, truth)


def run(rows, min_inlier):
    """판단 규칙 하나로 전체 구간을 돌려 (확정 시각 목록, 구간별 상태) 반환."""
    det = slip.SlipDetector(SLIP_CFG)
    confirmed, states = [], []
    for t, wheel, rotation, motion, true_move, xy in rows:
        if motion is not None and motion.inlier_ratio < min_inlier and wheel >= SLIP_CFG.min_wheel_distance:
            state = slip.UNKNOWN   # 스캔이 잘 안 맞으면 판단 보류
        else:
            state = det.update(wheel, rotation, motion)
        states.append(state)
        if state == slip.SLIP:
            confirmed.append((t, wheel, true_move, xy))
    return confirmed, states


def main():
    rows = []
    for path in sys.argv[1:]:
        rows += list(windows(pickle.load(open(path, 'rb'))))
    judged = [r for r in rows if r[1] >= SLIP_CFG.min_wheel_distance]
    true_slip = [r for r in judged if r[4] < SLIP_CFG.max_scan_ratio * r[1]]
    print(f'0.5초 구간 {len(rows)}개, 바퀴가 0.15m 이상 간 구간 {len(judged)}개, 그중 진짜 헛돎 {len(true_slip)}개')

    def ratios(sel):
        v = sorted(r[3].inlier_ratio for r in sel if r[3] is not None)
        return f'중앙값 {v[len(v)//2]:.2f}, 하위 10% {v[len(v)//10]:.2f}' if v else '-'
    normal = [r for r in judged if r not in true_slip]
    fooled = [r for r in normal if r[3] is not None
              and math.hypot(r[3].dx, r[3].dy) < SLIP_CFG.max_scan_ratio * r[1]]
    print(f'ICP 일치 비율: 정상 주행 {ratios(normal)} / 진짜 헛돎 {ratios(true_slip)} / 스캔이 속은 정상 구간({len(fooled)}개) {ratios(fooled)}')

    for min_inlier in (0.0, 0.5, 0.6, 0.7, 0.8):
        confirmed, _ = run(rows, min_inlier)
        false = [c for c in confirmed if c[2] >= SLIP_CFG.max_scan_ratio * c[1]]
        caught = len(confirmed) - len(false)
        label = '지금 규칙' if min_inlier == 0.0 else f'일치 비율 {min_inlier:.1f} 미만이면 보류'
        print(f'  [{label:22s}] 헛돎 확정 {len(confirmed):3d}번: 오탐 {len(false):3d}, 진짜 {caught:3d}')
        for t, wheel, true_move, xy in false[:5]:
            print(f'      오탐 t={t:7.1f} 위치 ({xy[0]:5.2f},{xy[1]:5.2f}) 바퀴 {wheel:.2f}m 실제 {true_move:.2f}m')


if __name__ == '__main__':
    main()
