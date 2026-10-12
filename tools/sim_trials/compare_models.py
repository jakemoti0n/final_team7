"""녹화한 카메라 이미지에서 approach_stop 사람을 두 모델이 얼마나 잡는지 거리 구간별로 비교한다.

사용법: compare_models.py <frames.npz> <모델1.pt> <모델2.pt>
로봇은 시작 위치(0, 0)에서 동쪽을 본다고 가정한다 (녹화 동안 움직이지 않음).
"""
import os
import collections
import math
import sys

import numpy as np
from limbo_evaluation import actors
from ultralytics import YOLO

SDF = os.path.expanduser('~/limbo/limbo/src/limbo_simulation/worlds/aischool_2f_scenarios.sdf')
CAMERA_X = 0.22                         # base_link 기준 앞쪽 (m)
FX = 160 / math.tan(1.25 / 2)           # 320px, 가로 시야 1.25rad
MATCH_PX = 45                           # 예상 위치와 박스 가운데 차이 허용 (px)
CONF = 0.3                              # person_detector의 yolo.confidence

traj = actors.parse_actor_trajectories(open(SDF).read())['approach_stop']
stop = next((a[0], b[0]) for a, b in zip(traj.waypoints, traj.waypoints[1:])
            if a[1:] == b[1:] and b[0] - a[0] >= 1.0)
period = traj.waypoints[-1][0]


def phase(t):
    x, y = actors.position_at(traj, t)
    dist = math.hypot(x - CAMERA_X, y)
    if not stop[0] <= t % period <= stop[1] and dist > 5.0:
        return None, None
    bearing = math.atan2(y, x - CAMERA_X)
    if abs(bearing) > 0.6:
        return None, None
    stopped = stop[0] <= t % period <= stop[1]
    if stopped:
        name = '멈춤 (다리·허리만, 1.4m)'
    elif dist > 3.0:
        name = '걸어옴 3~5m (전신)'
    else:
        name = '걸어옴 1.4~3m (위가 잘림)'
    return name, 160 - FX * math.tan(bearing)


def detect(model, frame, u):
    """예상 위치 근처 박스들 [(클래스 이름, 신뢰도)]."""
    r = model.predict(frame, conf=0.05, verbose=False)[0]
    found = []
    for cls, conf, (x1, _, x2, _) in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist(),
                                         r.boxes.xyxy.tolist()):
        name = r.names[int(cls)]
        if name in ('person', 'leg') and abs((x1 + x2) / 2 - u) < MATCH_PX:
            found.append((name, conf))
    return found


def main():
    data = np.load(sys.argv[1])
    models = {p.split('/')[-4] if 'runs' in p else p.split('/')[-1]: YOLO(p) for p in sys.argv[2:]}
    stats = collections.defaultdict(lambda: collections.defaultdict(list))
    for frame, t in zip(data['frames'], data['stamps']):
        name, u = phase(float(t))
        if name is None:
            continue
        bgr = frame[:, :, ::-1].copy()
        for label, model in models.items():
            stats[name][label].append(detect(model, bgr, u))

    for name in sorted(stats):
        print(f'\n[{name}] {len(next(iter(stats[name].values())))}장')
        for label, rows in stats[name].items():
            best = [max((c for _, c in f), default=0.0) for f in rows]
            hit = sum(b >= CONF for b in best) / len(best)
            kinds = collections.Counter(k for f in rows for k, c in f if c >= CONF)
            many = sum(sum(c >= CONF for _, c in f) >= 2 for f in rows) / len(rows)
            print(f'  {label:22s} 잡힘(≥{CONF}) {hit * 100:5.1f}%  신뢰도 중앙값 {sorted(best)[len(best) // 2]:.2f}  '
                  f'박스 종류 {dict(kinds)}  한 사람에 박스 2개 이상 {many * 100:4.1f}%')


if __name__ == '__main__':
    main()
