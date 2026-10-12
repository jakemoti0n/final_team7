"""두 녹화의 approach_stop 사람 예측을 비교한다 (멈춤 구간 끊김·ID·추정 속도). 사용법: pred_compare.py <라벨=json> ..."""
import os
import json, math, statistics as st, sys
from limbo_evaluation import actors
TRAJ = actors.parse_actor_trajectories(open(os.path.expanduser('~/limbo/limbo/src/limbo_simulation/worlds/aischool_2f_scenarios.sdf')).read())
tr = TRAJ['approach_stop']; period = tr.waypoints[-1][0]
stop = next((a[0], b[0]) for a, b in zip(tr.waypoints, tr.waypoints[1:]) if a[1:] == b[1:] and b[0] - a[0] >= 1.0)
for arg in sys.argv[1:]:
    label, path = arg.split('=')
    rows = [r for r in json.load(open(path)) if actors.nearest_person(TRAJ, r['t'], *r['pos'])[0] == 'approach_stop'
            and actors.nearest_person(TRAJ, r['t'], *r['pos'])[1] < 1.0]
    cycles = {}
    for r in rows:
        rel = (r['t'] % period) - stop[0]
        if 0 <= rel <= stop[1] - stop[0]: cycles.setdefault(int(r['t'] // period), []).append((rel, r['id'], math.hypot(*r['vel'])))
    print(f'[{label}] approach_stop 예측 {len(rows)}개, 추적 ID {len(set(r["id"] for r in rows))}개')
    for c, v in sorted(cycles.items()):
        v.sort(); gaps = [b[0] - a[0] for a, b in zip(v, v[1:])] + [v[0][0], (stop[1] - stop[0]) - v[-1][0]]
        print(f'   멈춤 {c}: 예측 {len(v)}개, 가장 긴 끊김 {max(gaps):.1f}초, ID {len(set(i for _, i, _ in v))}개, '
              f'추정 속도 중앙값 {st.median(s for *_, s in v):.2f}m/s, 0.05 미만 {sum(s < 0.05 for *_, s in v)}/{len(v)}')
