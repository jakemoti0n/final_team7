"""순찰 bag(/ground_truth/odom + /navigate_through_poses 상태)과 월드 SDF 사람 시간표로 묶음별 사람 최소 거리·0.3 m 미만 시간·멈춤 시간,
최소 거리 순간의 로봇 속도와 사람 접근 속도를 센다. nav_recorder가 NavigateThroughPoses(순찰)를 안 받아서 만든 보조 도구.
사용법: bag_person.py <bag 폴더> <월드 이름>   (예: patrol_nemo_hl2_bag human_test_world)"""
import sys, os, math
sys.path.insert(0, os.path.expanduser('~/limbo/limbo/src/limbo_evaluation'))
from limbo_evaluation import actors
from rosbag2_py import SequentialReader, StorageOptions, ConverterOptions
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
bag, world = sys.argv[1], sys.argv[2]
sdf = open(os.path.expanduser(f'~/limbo/limbo/install/limbo_simulation/share/limbo_simulation/worlds/{world}.sdf')).read()
people = actors.parse_actor_trajectories(sdf)
r = SequentialReader(); r.open(StorageOptions(uri=bag, storage_id='mcap'), ConverterOptions('', ''))
types = {t.name: get_message(t.type) for t in r.get_all_topics_and_types()}
truth, starts = [], []
while r.has_next():
    topic, data, _ = r.read_next()
    if topic == '/ground_truth/odom':
        m = deserialize_message(data, types[topic]); t = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9
        truth.append((t, m.pose.pose.position.x, m.pose.pose.position.y))
    elif topic == '/navigate_through_poses/_action/status':
        m = deserialize_message(data, types[topic])
        for s in m.status_list:
            if s.status == 2: starts.append(s.goal_info.stamp.sec + s.goal_info.stamp.nanosec * 1e-9)
starts = sorted(set(starts)); bounds = starts + [truth[-1][0] + 1]
print(f'정답 {len(truth)}개, 구간 시작 {len(starts)}개')
for i in range(len(starts)):
    seg = [p for p in truth if bounds[i] <= p[0] < bounds[i + 1]]
    if len(seg) < 2: continue
    dmin, tcol, tstop, tstop_near, dist = math.inf, 0.0, 0.0, 0.0, 0.0
    for (t0, x0, y0), (t1, x1, y1) in zip(seg, seg[1:]):
        dt = t1 - t0; step = math.hypot(x1 - x0, y1 - y0); dist += step
        _, d = actors.nearest_person(people, t1, x1, y1)
        dmin = min(dmin, d)
        if d < 0.3: tcol += dt
        if dt > 0 and step / dt < 0.05:
            tstop += dt
            if d < 1.5: tstop_near += dt
    print(f'구간 {i+1}: {seg[-1][0]-seg[0][0]:5.1f} s  {dist:5.1f} m  사람 최소 {dmin:.2f} m  0.3 m 미만 {tcol:.1f} s  멈춤 {tstop:.1f} s (사람 앞 {tstop_near:.1f})')

# 추가: 사람 최소 거리 순간의 로봇 속도와 사람의 접근 속도, /cmd_vel_nav 끊김(1 s 이상)
r = SequentialReader(); r.open(StorageOptions(uri=bag, storage_id='mcap'), ConverterOptions('', ''))
cmd_t = []
while r.has_next():
    topic, data, ts = r.read_next()
    if topic == '/cmd_vel_nav': cmd_t.append(ts * 1e-9)
gaps = [(a, b - a) for a, b in zip(cmd_t, cmd_t[1:]) if b - a > 1.0]
print('cmd_vel_nav 1 s 넘는 끊김:', [(round(g[0] - cmd_t[0], 1), round(g[1], 1)) for g in gaps])
for i in range(len(starts)):
    seg = [p for p in truth if bounds[i] <= p[0] < bounds[i + 1]]
    best = min(((actors.nearest_person(people, t, x, y)[1], t, x, y, actors.nearest_person(people, t, x, y)[0]) for t, x, y in seg[1:]), default=None)
    if not best: continue
    d, t, x, y, name = best
    j = next(k for k, p in enumerate(seg) if p[0] == t)
    t0, x0, y0 = seg[max(j - 10, 0)]
    v_robot = math.hypot(x - x0, y - y0) / max(t - t0, 1e-6)
    px0, py0 = actors.position_at(people[name], t - 0.5); px1, py1 = actors.position_at(people[name], t)
    d0 = math.hypot(px0 - x0, py0 - y0); approach = (d0 - d) / 0.5
    print(f'구간 {i+1} 최소 {d:.2f} m ({name}, 구간 시작 +{t-seg[0][0]:.1f} s): 로봇 속도 {v_robot:.2f} m/s, 사람이 다가온 속도 {approach:.2f} m/s')
