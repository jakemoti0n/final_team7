"""R5 진단: 사람 때문에 멈춘 순간에 ToF가 무엇을 봤나. 정답(월드 사람 경로 + /ground_truth/odom)과 /tof/nearest·obstacle_ahead 비교."""
import bisect, math, sys
from pathlib import Path
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
sys.path.insert(0, str(Path.home() / 'limbo/limbo/src/limbo_evaluation'))
from limbo_evaluation import actors

bag, sdf = sys.argv[1], sys.argv[2]
traj = actors.parse_actor_trajectories(open(sdf).read())
truth, near, ahead = [], [], []   # ahead: (수신 시각 ns, 값) — Bool은 시각이 없어 bag 시각
r = rosbag2_py.SequentialReader()
r.open(rosbag2_py.StorageOptions(uri=bag, storage_id='mcap'), rosbag2_py.ConverterOptions('', ''))
types = {t.name: get_message(t.type) for t in r.get_all_topics_and_types()}
odom_wall = []
while r.has_next():
    topic, raw, t = r.read_next()
    m = deserialize_message(raw, types[topic])
    if topic == '/ground_truth/odom':
        s = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9
        q = m.pose.pose.orientation
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        v = math.hypot(m.twist.twist.linear.x, m.twist.twist.linear.y)
        truth.append((s, t, m.pose.pose.position.x, m.pose.pose.position.y, yaw, v))
    elif topic == '/tof/nearest':
        near.append((t, m.point.x, m.point.y, m.point.z))
    elif topic == '/tof/obstacle_ahead':
        ahead.append((t, m.data))
near_t = [n[0] for n in near]; ahead_t = [a[0] for a in ahead]
print(f'정답 {len(truth)}, ToF nearest {len(near)}, obstacle_ahead {len(ahead)} (참 {sum(a[1] for a in ahead)})')
rows = []
for s, t, x, y, yaw, v in truth[::10]:
    best = None
    for name, tr in traj.items():
        px, py = actors.position_at(tr, s)
        dx, dy = px - x, py - y
        fx = math.cos(yaw) * dx + math.sin(yaw) * dy
        fy = -math.sin(yaw) * dx + math.cos(yaw) * dy
        if fx > 0 and abs(fy) < 0.6 and (best is None or fx < best[0]):
            best = (fx, fy)
    if best is None or best[0] > 1.5 or v > 0.05:
        continue
    i = bisect.bisect_right(near_t, t) - 1
    j = bisect.bisect_right(ahead_t, t) - 1
    tof_x = near[i][1] if i >= 0 and t - near[i][0] < 3e8 else None
    rows.append((best[0], best[1], tof_x, ahead[j][1] if j >= 0 else None))
print(f'멈춤(0.05 m/s 미만) + 앞 1.5 m·폭 0.6 m 안 사람: {len(rows)}순간 (정답 1 s 간격)')
for b in (0.3, 0.5, 0.8, 1.5):
    sel = [r for r in rows if r[0] <= b and r[0] > b - (0.3 if b == 0.3 else (0.2 if b == 0.5 else (0.3 if b == 0.8 else 0.7)))]
    if not sel: continue
    tof_hit = [r for r in sel if r[2] is not None and r[2] < r[0] + 0.2]
    print(f'  사람 중심 앞 ~{b} m: {len(sel)}순간, ToF가 사람 근처 점 {len(tof_hit)}, obstacle_ahead 참 {sum(1 for r in sel if r[3])}, ToF 최근접 x 예: {[round(r[2],2) if r[2] else None for r in sel[:6]]}')
