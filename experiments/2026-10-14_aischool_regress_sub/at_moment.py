"""R7: 전역 계획 실패 순간(벽시계 ns) 사람 위치(시간표)와 전역 costmap에서 B→C 복도를 막은 치명 칸"""
import math, sys, bisect, os
import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
sys.path.insert(0, os.path.expanduser('~/limbo/limbo/src/limbo_evaluation'))
from limbo_evaluation import actors
T = int(sys.argv[3])   # 실패 시각 (ns, 벽시계)
def read(bag, topics):
    r = rosbag2_py.SequentialReader(); r.open(rosbag2_py.StorageOptions(uri=bag, storage_id='mcap'), rosbag2_py.ConverterOptions('', ''))
    types = {t.name: get_message(t.type) for t in r.get_all_topics_and_types()}
    out = {k: [] for k in topics}
    while r.has_next():
        tp, raw, t = r.read_next()
        if tp in topics: out[tp].append((t, deserialize_message(raw, types[tp])))
    return out
od = read(sys.argv[1], ['/ground_truth/odom'])['/ground_truth/odom']
i = min(range(len(od)), key=lambda k: abs(od[k][0]-T)); m = od[i][1]
sim = m.header.stamp.sec + m.header.stamp.nanosec*1e-9; rp = m.pose.pose.position
print(f'실패 순간 시뮬레이션 {sim:.1f} s, 로봇 ({rp.x:.2f}, {rp.y:.2f}), 기록 시각 차 {(od[i][0]-T)/1e9:.2f} s')
tr = actors.parse_actor_trajectories(open(os.path.expanduser('~/limbo/limbo/install/limbo_simulation/share/limbo_simulation/worlds/aischool_2f.sdf')).read())
for n, t in tr.items():
    x, y = actors.position_at(t, sim); print(f'  {n}: ({x:.2f}, {y:.2f}), 로봇까지 {math.hypot(x-rp.x, y-rp.y):.2f} m')
rd = read(sys.argv[2], ['/global_costmap/costmap', '/global_costmap/costmap_updates'])
g = rd['/global_costmap/costmap'][0][1]
w, h, res = g.info.width, g.info.height, g.info.resolution; ox, oy = g.info.origin.position.x, g.info.origin.position.y
data = np.array(g.data, dtype=np.int16).reshape(h, w)
last = None
for t, u in rd['/global_costmap/costmap_updates']:
    if t > T: break
    data[u.y:u.y+u.height, u.x:u.x+u.width] = np.array(u.data, dtype=np.int16).reshape(u.height, u.width)
    last = t
print(f'전역 costmap: 업데이트 {len(rd["/global_costmap/costmap_updates"])}개, 실패 {(T-last)/1e9:.2f} s 전까지 반영')
def cell(x, y): return int((y-oy)/res), int((x-ox)/res)
blocked = []
for x in np.arange(-13.5, -6.9, 0.05):
    col = [data[cell(x, y)] for y in np.arange(7.0, 9.0, res)]
    if min(col) >= 99: blocked.append(round(float(x), 2))
print('B→C 복도(y 7~9) 완전히 막힌 x 단면:', blocked[:10], '...', blocked[-5:], f'({len(blocked)}개)')
if blocked:
    x0 = blocked[len(blocked)//2]
    print(f'x={x0} 단면 비용(y 7.0→9.0, 0.1 m 간격):', [int(data[cell(x0, y)]) for y in np.arange(7.0, 9.01, 0.1)])
    # 그 자리에 치명이 STVL 장애물(254)인지 inflation(253 이하)인지
    r, c = cell(x0, 8.0); print('  B→C 중앙선 비용', int(data[r, c]))
# 정적 지도와 비교: 같은 단면에서 원래 지도 비용
print('최초 costmap(정적+초기)에서 같은 범위 막힌 단면 수:', sum(1 for x in np.arange(-13.5, -6.9, 0.05) if min(np.array(g.data, dtype=np.int16).reshape(h, w)[cell(x, y)] for y in np.arange(7.0, 9.0, res)) >= 99))
for name, (x, y) in {'출발(로봇)': (float(sys.argv[4]), float(sys.argv[5])), '도착 C': (-13.742, 7.998)}.items():
    r, c = cell(x, y)
    win = data[r-6:r+7, c-6:c+7]   # ±0.3 m
    print(f'{name} ({x}, {y}) 칸 비용 {int(data[r, c])}, ±0.3 m 안 치명(254) {int((win == 254).sum())}칸 · 253 {int((win == 253).sum())}칸 · 최소 {int(win.min())}')
    print('   행(위→아래, 0.1 m 간격):')
    for yy in np.arange(y+0.5, y-0.51, -0.1):
        print('   ', ' '.join(f'{int(data[cell(xx, yy)]):3d}' for xx in np.arange(x-0.5, x+0.51, 0.1)))
