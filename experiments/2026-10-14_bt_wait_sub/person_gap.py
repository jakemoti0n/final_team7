"""R4 진단 (사용: python3 person_gap.py <bag> <월드 sdf>): 사람이 로봇 앞 가까이 있을 때 person_position_base가 얼마나 끊기는지.
정답 사람 위치(월드 SDF 경로) + 정답 로봇 위치(/ground_truth/odom)로 '앞 2 m·폭 0.8 m 안 사람'인 순간마다
마지막 인식 위치의 나이(영상 시각 기준)를 잰다."""
import math, sys, collections
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from pathlib import Path
sys.path.insert(0, str(Path.home() / 'limbo/limbo/src/limbo_evaluation'))
from limbo_evaluation import actors

bag, sdf = sys.argv[1], sys.argv[2]
traj = actors.parse_actor_trajectories(open(sdf).read())
truth, dets = [], []
reader = rosbag2_py.SequentialReader()
reader.open(rosbag2_py.StorageOptions(uri=bag, storage_id='mcap'), rosbag2_py.ConverterOptions('', ''))
types = {t.name: get_message(t.type) for t in reader.get_all_topics_and_types()}
while reader.has_next():
    topic, raw, _ = reader.read_next()
    m = deserialize_message(raw, types[topic])
    s = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9
    if topic == '/ground_truth/odom':
        q = m.pose.pose.orientation
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        truth.append((s, m.pose.pose.position.x, m.pose.pose.position.y, yaw))
    else:
        dets.append(s)
dets.sort()
print(f'정답 {len(truth)}개, 인식 {len(dets)}개')
bins = collections.defaultdict(lambda: [0, 0, []])  # 거리 구간 → [순간 수, 1초 안 인식 있음, 나이]
import bisect
for s, x, y, yaw in truth[::5]:
    for name, tr in traj.items():
        px, py = actors.position_at(tr, s)
        dx, dy = px - x, py - y
        fx = math.cos(yaw) * dx + math.sin(yaw) * dy
        fy = -math.sin(yaw) * dx + math.cos(yaw) * dy
        if 0 < fx < 2.0 and abs(fy) < 0.8:
            i = bisect.bisect_right(dets, s)
            age = s - dets[i - 1] if i else math.inf
            b = min(int(math.hypot(fx, fy) / 0.5), 3)
            bins[b][0] += 1
            bins[b][1] += age <= 1.0
            bins[b][2].append(age)
for b in sorted(bins):
    n, ok, ages = bins[b]
    ages.sort()
    print(f'{b*0.5:.1f}~{(b+1)*0.5 if b < 3 else 2.0:.1f} m: {n}순간, 1초 안 인식 {ok} ({100*ok/n:.0f}%), 나이 중앙값 {ages[len(ages)//2]:.1f} s')
