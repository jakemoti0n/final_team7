"""R5 Q4 진단: 손님(/sim/people 정답)이 카메라 시야·3 m 안에 있을 때 예측에 사람이 있었나. 사용: python3 guest_seen.py <bag>"""
import math, sys, bisect
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
r = rosbag2_py.SequentialReader()
r.open(rosbag2_py.StorageOptions(uri=sys.argv[1], storage_id='mcap'), rosbag2_py.ConverterOptions('', ''))
types = {t.name: get_message(t.type) for t in r.get_all_topics_and_types()}
odom, people, preds = [], [], []
while r.has_next():
    topic, raw, t = r.read_next(); m = deserialize_message(raw, types[topic])
    if topic == '/ground_truth/odom':
        q=m.pose.pose.orientation; yaw=math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
        odom.append((t, m.pose.pose.position.x, m.pose.pose.position.y, yaw))
    elif topic == '/sim/people':
        people.append((t, [(p.position.x, p.position.y) for p in m.poses]))
    elif topic == '/person_detector/predictions':
        preds.append((t, len(m.predictions), [(q.current_position.x,q.current_position.y) for q in m.predictions]))
print('예측 메시지', len(preds), '사람 있는 것', sum(1 for p in preds if p[1]))
ot=[o[0] for o in odom]; qt=[p[0] for p in preds]
rows=0
for t, ps in people[::12]:
    i=bisect.bisect_right(ot,t)-1
    if i<0: continue
    _, rx, ry, yaw = odom[i]
    for n,(gx,gy) in enumerate(ps):
        dx,dy=gx-rx,gy-ry; d=math.hypot(dx,dy)
        if d>3.5: continue
        bearing=math.degrees(math.atan2(dy,dx)-yaw); bearing=(bearing+180)%360-180
        j=bisect.bisect_right(qt,t)-1
        seen = j>=0 and t-preds[j][0]<0.5e9 and preds[j][1]>0
        print(f'{t/1e9%1000:6.1f} 사람{n} 거리 {d:4.2f} 방향 {bearing:5.0f}°  예측에 사람 {"있음" if seen else "없음"}')
        rows+=1
    if rows>70: break
