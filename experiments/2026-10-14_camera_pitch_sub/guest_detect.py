"""R5 Q5: 손님(정답 /sim/people)이 로봇 앞 3 m·카메라 시야(±36°) 안에 있던 시간 중 예측에 사람이 있던 비율. 사용: q5count.py <bag>..."""
import math, sys, bisect
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
for bag in sys.argv[1:]:
    r = rosbag2_py.SequentialReader(); r.open(rosbag2_py.StorageOptions(uri=bag, storage_id='mcap'), rosbag2_py.ConverterOptions('', ''))
    types = {t.name: get_message(t.type) for t in r.get_all_topics_and_types()}
    odom, people, preds = [], [], []
    while r.has_next():
        tp, raw, t = r.read_next(); m = deserialize_message(raw, types[tp])
        if tp == '/ground_truth/odom':
            q = m.pose.pose.orientation; yaw = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
            odom.append((t, m.pose.pose.position.x, m.pose.pose.position.y, yaw))
        elif tp == '/sim/people':
            people.append((t, [(p.position.x, p.position.y) for p in m.poses]))
        elif tp == '/person_detector/predictions':
            preds.append((t, len(m.predictions)))
    ot = [o[0] for o in odom]; qt = [p[0] for p in preds]
    inview = seen = 0
    for t, ps in people[::4]:          # 약 12 Hz
        i = bisect.bisect_right(ot, t) - 1
        if i < 0: continue
        _, rx, ry, yaw = odom[i]
        vis = False
        for gx, gy in ps:
            d = math.hypot(gx-rx, gy-ry); b = (math.degrees(math.atan2(gy-ry, gx-rx) - yaw) + 180) % 360 - 180
            if 0.8 <= d <= 3.0 and abs(b) <= 36: vis = True
        if not vis: continue
        inview += 1
        j = bisect.bisect_right(qt, t) - 1
        if j >= 0 and t - preds[j][0] < 0.3e9 and preds[j][1] > 0: seen += 1
    print(f"{bag.split('/')[-1]}: 손님 시야·0.8~3 m 안 {inview}표본, 그중 예측에 사람 {seen} ({100*seen/max(1,inview):.0f}%), 사람 든 예측 메시지 {sum(1 for p in preds if p[1])}")
