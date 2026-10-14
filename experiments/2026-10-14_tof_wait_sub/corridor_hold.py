"""다가옴 정지가 켜진 동안 0.5 s마다: ToF 막힘, 앞 섹터(±30°, 1.5 m) 점유 칸 수와 그 점 위치, 가장 가까운 사람(정답)"""
import math, sys, bisect
import numpy as np, rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
sys.path.insert(0, '/home/automaton/limbo/limbo/src/limbo_perception')
from limbo_perception import tof
r = rosbag2_py.SequentialReader(); r.open(rosbag2_py.StorageOptions(uri=sys.argv[1], storage_id='mcap'), rosbag2_py.ConverterOptions('', ''))
types = {t.name: get_message(t.type) for t in r.get_all_topics_and_types()}
D={k:[] for k in ['/ground_truth/odom','/sim/people','/scan','/tof/obstacle_ahead','/person_approaching']}
while r.has_next():
    tp, raw, t = r.read_next()
    if tp in D: D[tp].append((t, deserialize_message(raw, types[tp])))
def at(tp, t):
    ts=[x[0] for x in D[tp]]; i=bisect.bisect_right(ts,t)-1; return D[tp][i][1] if i>=0 else None
ap=D['/person_approaching']; on=None; spans=[]
for t,m in ap:
    if m.data and on is None: on=t
    if not m.data and on is not None: spans.append((on,t)); on=None
cfg=tof.SectorConfig()
for a,b in spans:
    print(f'== 정지 {(b-a)/1e9:.1f} s')
    for t in range(a, b, int(0.5e9))[::4]:
        sc=at('/scan',t); od=at('/ground_truth/odom',t); pp=at('/sim/people',t); tb=at('/tof/obstacle_ahead',t)
        rng=np.array(sc.ranges); ang=sc.angle_min+sc.angle_increment*np.arange(len(rng))
        ok=np.isfinite(rng)&(rng>=sc.range_min)&(rng<=sc.range_max)
        pts=np.column_stack([rng*np.cos(ang), rng*np.sin(ang)])[ok]
        dx,dy=pts[:,0]-0.25, pts[:,1]
        ins=(dx>0)&(np.hypot(dx,dy)<=1.5)&(np.abs(np.degrees(np.arctan2(dy,dx)))<=30)
        q=od.pose.pose.orientation; yaw=math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z)); rx,ry=od.pose.pose.position.x,od.pose.pose.position.y
        ppl=[]
        for p in pp.poses:
            ddx,ddy=p.position.x-rx,p.position.y-ry
            ppl.append((math.hypot(ddx,ddy), math.cos(yaw)*ddx+math.sin(yaw)*ddy, -math.sin(yaw)*ddx+math.cos(yaw)*ddy))
        nd=min(ppl)
        sect=pts[ins]
        print(f'  +{(t-a)/1e9:4.1f} s ToF {"막힘" if tb and tb.data else "빔 "} 섹터 {ins.sum():2d}칸'+(f' (x {sect[:,0].min():.2f}~{sect[:,0].max():.2f}, y {sect[:,1].min():.2f}~{sect[:,1].max():.2f})' if ins.sum() else '')+f'  사람 {nd[0]:.2f} m (앞 {nd[1]:.2f}, 옆 {nd[2]:.2f})  로봇 ({rx:.2f},{ry:.2f})')
