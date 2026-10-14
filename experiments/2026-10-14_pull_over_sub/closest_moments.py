"""R6: 사람이 가장 가까웠던 순간 앞뒤 로봇·사람 위치(복도 가로 y)와 로봇 속도"""
import math, sys, bisect, rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
r = rosbag2_py.SequentialReader(); r.open(rosbag2_py.StorageOptions(uri=sys.argv[1], storage_id='mcap'), rosbag2_py.ConverterOptions('', ''))
types = {t.name: get_message(t.type) for t in r.get_all_topics_and_types()}
od, pp, ap = [], [], []
while r.has_next():
    tp, raw, t = r.read_next(); m = deserialize_message(raw, types[tp])
    if tp == '/ground_truth/odom': od.append((t, m.pose.pose.position.x, m.pose.pose.position.y, m.twist.twist.linear.x))
    elif tp == '/sim/people': pp.append((t, [(p.position.x, p.position.y) for p in m.poses]))
    elif tp == '/person_approaching': ap.append((t, m.data))
ot=[o[0] for o in od]; at=[a[0] for a in ap]
d=[]
for t, ps in pp:
    i=bisect.bisect_right(ot,t)-1
    if i<0: continue
    _,rx,ry,v=od[i]
    for k,(x,y) in enumerate(ps): d.append((math.hypot(x-rx,y-ry),t,k,x,y,rx,ry,v))
d.sort()
seen=[]
for best in d:
    if any(abs(best[1]-s)<15e9 for s in seen): continue
    seen.append(best[1])
    if len(seen)>3: break
    t0=best[1]; print(f'== 최근접 {best[0]:.2f} m (사람{best[2]})')
    for dt in (-6,-4,-2,-1,0,1):
        t=t0+int(dt*1e9); j=bisect.bisect_right([p[0] for p in pp],t)-1; i=bisect.bisect_right(ot,t)-1; a=bisect.bisect_right(at,t)-1
        x,y=pp[j][1][best[2]]; _,rx,ry,v=od[i]
        print(f'  {dt:+d} s 로봇 ({rx:.2f},{ry:.2f}) v={v:.2f}  사람 ({x:.2f},{y:.2f})  거리 {math.hypot(x-rx,y-ry):.2f}  다가옴 {ap[a][1] if a>=0 else None}')
