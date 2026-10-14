"""no_yield 정면 조우: 사람이 5 m → 최근접 오는 동안 0.5 s마다 정답 거리·예측 위치/속도·직선 최근접·다가옴"""
import math, sys, bisect, rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
r = rosbag2_py.SequentialReader(); r.open(rosbag2_py.StorageOptions(uri=sys.argv[1], storage_id='mcap'), rosbag2_py.ConverterOptions('', ''))
types = {t.name: get_message(t.type) for t in r.get_all_topics_and_types()}
od, pp, pr, ap = [], [], [], []
while r.has_next():
    tp, raw, t = r.read_next()
    if tp not in ('/ground_truth/odom', '/sim/people', '/person_detector/predictions', '/person_approaching'): continue
    m = deserialize_message(raw, types[tp])
    if tp == '/ground_truth/odom': od.append((t, m.pose.pose.position.x, m.pose.pose.position.y, m.twist.twist.linear.x))
    elif tp == '/sim/people': pp.append((t, [(p.position.x, p.position.y) for p in m.poses]))
    elif tp == '/person_detector/predictions': pr.append((t, [(q.current_position.x, q.current_position.y, q.velocity.x, q.velocity.y) for q in m.predictions]))
    else: ap.append((t, m.data))
ot=[o[0] for o in od]; prt=[p[0] for p in pr]; at=[a[0] for a in ap]
def at_(lst, ts, t):
    i=bisect.bisect_right(ts,t)-1; return lst[i] if i>=0 else None
# 최근접 순간들
d=[]
for t, ps in pp:
    o=at_(od,ot,t)
    if not o: continue
    for k,(x,y) in enumerate(ps): d.append((math.hypot(x-o[1],y-o[2]),t,k))
d.sort(); seen=[]
for dist,t0,k in d:
    if any(abs(t0-s)<20e9 for s in seen) or dist>0.5: continue
    seen.append(t0); print(f'== 최근접 {dist:.2f} m')
    for dt in [x*0.5 for x in range(-12,1)]:
        t=t0+int(dt*1e9); j=bisect.bisect_right([p[0] for p in pp],t)-1; x,y=pp[j][1][k]; o=at_(od,ot,t); rx,ry=o[1],o[2]
        P=at_(pr,prt,t); a=at_(ap,at,t)
        s=f'  {dt:+5.1f} s 정답 {math.hypot(x-rx,y-ry):4.2f} m'
        if P and t-P[0]<0.5e9:
            m=[q for q in P[1] if math.hypot(q[0]-x,q[1]-y)<0.8]
            if m:
                q=m[0]; px,py,vx,vy=q[0]-rx,q[1]-ry,q[2],q[3]; sp=math.hypot(vx,vy)
                tt=-(px*vx+py*vy)/(sp*sp) if sp>0 else 0; c=math.hypot(px+vx*tt,py+vy*tt)
                s+=f'  예측 {math.hypot(px,py):4.2f} m 속도 {sp:4.2f} 최근접 {c:4.2f} (t {tt:4.1f})'
            else: s+='  예측에 이 사람 없음'
        else: s+='  예측 없음'
        s+=f'  다가옴 {a[1] if a else None}'
        print(s)
