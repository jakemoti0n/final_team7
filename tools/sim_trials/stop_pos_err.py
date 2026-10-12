"""멈춤 구간에서 approach_stop 근처(3m 이내) 예측의 위치 오차를 본다. 사용법: stop_pos_err.py <라벨=json> ..."""
import os
import json, math, statistics as st, sys
from limbo_evaluation import actors
tr = actors.parse_actor_trajectories(open(os.path.expanduser('~/limbo/limbo/src/limbo_simulation/worlds/aischool_2f_scenarios.sdf')).read())['approach_stop']
period = tr.waypoints[-1][0]
stop = next((a[0], b[0]) for a, b in zip(tr.waypoints, tr.waypoints[1:]) if a[1:] == b[1:] and b[0] - a[0] >= 1.0)
for arg in sys.argv[1:]:
    label, path = arg.split('=')
    errs = []; far = []
    for r in json.load(open(path)):
        rel = (r['t'] % period) - stop[0]
        if not 0 <= rel <= stop[1] - stop[0]: continue
        tx, ty = actors.position_at(tr, r['t']); d = math.dist(r['pos'], (tx, ty))
        if d < 3.0: errs.append(d)
        # 로봇(원점)에서 본 거리 차: +면 실제보다 멀게 추정
        if d < 3.0: far.append(math.hypot(*r['pos']) - math.hypot(tx, ty))
    print(f'[{label}] 멈춤 구간 예측 {len(errs)}개, 위치 오차 중앙값 {st.median(errs):.2f}m, 1m 넘는 것 {sum(e > 1 for e in errs)}개, '
          f'로봇에서 본 거리 차 중앙값 {st.median(far):+.2f}m (최대 {max(far):+.2f})')
