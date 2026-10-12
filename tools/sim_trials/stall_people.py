"""멈춘 구간 동안 사람(actor)이 로봇과 목표 근처에 있었는지 본다.
사용법: stall_people.py <bag> <월드 이름> <목표x> <목표y> <구간 시작초-끝초(녹화 기준)> ..."""
import math, os, sys
import importlib.util
from limbo_evaluation import actors
here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pa', os.path.join(here, 'patrol_analyze.py'))
pa = importlib.util.module_from_spec(spec); spec.loader.exec_module(pa)
data = pa.read(sys.argv[1])
traj = actors.parse_actor_trajectories(open(os.path.expanduser(f'~/limbo/limbo/src/limbo_simulation/worlds/{sys.argv[2]}.sdf')).read())
goal = (float(sys.argv[3]), float(sys.argv[4]))
gt = [(t, m.header.stamp.sec + m.header.stamp.nanosec * 1e-9, m.pose.pose.position.x, m.pose.pose.position.y) for t, m in data['/ground_truth/odom']]
t0 = gt[0][0]
for w in sys.argv[5:]:
    s, e = (float(v) + t0 for v in w.split('-'))
    rows = [r for r in gt if s <= r[0] <= e][::10]   # 약 0.5초 간격
    near_goal = []; near_robot = []
    for _, sim_t, x, y in rows:
        dg = {n: math.dist(actors.position_at(tr, sim_t), goal) for n, tr in traj.items()}
        dr = {n: math.dist(actors.position_at(tr, sim_t), (x, y)) for n, tr in traj.items()}
        near_goal.append(min(dg.values())); near_robot.append(min(dr.items(), key=lambda kv: kv[1]))
    within = sum(d < 1.5 for d in near_goal) / len(near_goal)
    print(f'  {w}초: 목표에서 가장 가까운 사람 최소 {min(near_goal):.2f}m / 평균 {sum(near_goal)/len(near_goal):.2f}m, 목표 1.5m 안에 사람 있던 시간 {within*100:.0f}%, '
          f'로봇에서 가장 가까운 사람 최소 {min(d for _, d in near_robot):.2f}m')
