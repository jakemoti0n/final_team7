"""녹화가 조건을 넘어 이어졌으므로 mcap 파일을 직접 열고 시간 창으로 잘라 조건별 직진 속도를 낸다."""
import sys, math, statistics as st, bisect
sys.path.insert(0, '/home/kim/limbo/tools/sim_trials')
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
import rosbag2_py
from speed_stages import twist, at, STRAIGHT_WZ, MOVING
def read(path):
    r = rosbag2_py.SequentialReader(); r.open(rosbag2_py.StorageOptions(uri=path, storage_id='mcap'), rosbag2_py.ConverterOptions('', ''))
    types = {t.name: get_message(t.type) for t in r.get_all_topics_and_types()}; d = {}
    while r.has_next():
        topic, raw, t = r.read_next(); d.setdefault(topic, []).append((t*1e-9, deserialize_message(raw, types[topic])))
    return d
base = '/home/kim/limbo_bags/sim_trials/street_'
bags = {c: read(f'{base}{c}/street_{c}_0.mcap') for c in 'ABC'}
starts = {c: min(v[0][0] for v in bags[c].values()) for c in 'ABC'}
windows = {'A': (starts['A'], starts['B']), 'B': (starts['B'], starts['C']), 'C': (starts['C'], 1e18)}
for c in 'ABC':
    d = bags[c]; lo, hi = windows[c]
    nav = [x for x in d['/cmd_vel_nav'] if lo <= x[0] < hi]; smooth, final = d['/cmd_vel_smoothed'], d['/cmd_vel']
    gt = [(t, m.pose.pose.position.x, m.pose.pose.position.y) for t, m in d['/ground_truth/odom'] if lo <= t < hi]
    real = [(t1, math.hypot(x1-x0, y1-y0)/(t1-t0)) for (t0,x0,y0),(t1,x1,y1) in zip(gt, gt[1:]) if t1 > t0]
    rows = []
    for t, m in nav:
        v, w = twist(m).linear.x, twist(m).angular.z
        if abs(w) > STRAIGHT_WZ or v < MOVING: continue
        rows.append((v, twist(at(smooth, t)).linear.x, twist(at(final, t)).linear.x, at([(a, (b,)) for a, b in real], t)[0]))
    print(f'== 조건 {c}: 직진 순간 {len(rows)}개')
    for name, k in (('컨트롤러 /cmd_vel_nav', 0), ('평활 후 /cmd_vel_smoothed', 1), ('최종 /cmd_vel', 2), ('실제 속도(정답)', 3)):
        v = sorted(r[k] for r in rows); print(f'  {name:26s} 평균 {st.mean(v):.2f} 중앙값 {v[len(v)//2]:.2f} 상위10% {v[int(len(v)*0.9)]:.2f} 최대 {v[-1]:.2f}')
    cut = sum(1 for r in rows if r[2] < r[0] - 0.05); print(f'  최종이 컨트롤러보다 0.05 넘게 낮은 순간 {cut}/{len(rows)}')
    cm = [m for t, m in d.get('/collision_monitor_state', []) if lo <= t < hi]; print(f'  collision monitor 상태 {len(cm)}개, 종류 {sorted({m.action_type for m in cm})}')
