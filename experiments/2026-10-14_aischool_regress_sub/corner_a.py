"""R7: A 모서리를 어떻게 지났나 — A까지 최소 거리, 그때 시각, 전역 경로가 A로 되돌아간(첨점) 경로 수"""
import math, sys
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
A=(-6.837,-0.240)
def read(bag, topic):
    r = rosbag2_py.SequentialReader(); r.open(rosbag2_py.StorageOptions(uri=bag, storage_id='mcap'), rosbag2_py.ConverterOptions('', ''))
    types = {t.name: get_message(t.type) for t in r.get_all_topics_and_types()}
    out=[]
    while r.has_next():
        tp, raw, t = r.read_next()
        if tp == topic: out.append((t, deserialize_message(raw, types[tp])))
    return out
for i in (1,2,3):
    L=f'/home/automaton/limbo_bags/sim_trials/logs'
    od = read(f'{L}/patrol_r7_{i}_bag', '/ground_truth/odom')
    t0 = od[0][0]
    ds=[((t-t0)/1e9, math.hypot(m.pose.pose.position.x-A[0], m.pose.pose.position.y-A[1]), m.pose.pose.position) for t,m in od]
    tmin,dmin,p=min(ds,key=lambda x:x[1])
    # A 0.7 m 안에 머문 시간
    inside=sum(1 for _,d,_ in ds if d<0.7)/max(1,len(ds))*(ds[-1][0]-ds[0][0])
    plans=read(f'{L}/r7_extra{i}','/plan')
    cusp=0
    for t,m in plans:
        ys=[q.pose.position.y for q in m.poses[:400]]
        xs=[q.pose.position.x for q in m.poses[:400]]
        # 로봇이 A 북쪽(y>0.3)에서 시작해 A 근처(y<0.1)로 내려갔다 다시 올라가는 경로
        if ys and ys[0]>0.3 and min(ys)<0.1 and abs(xs[0]+6.85)<0.6: cusp+=1
    print(f'r7_{i}: A까지 최소 {dmin:.2f} m ({tmin:.0f} s, 위치 {p.x:.2f},{p.y:.2f}), A 0.7 m 안 약 {inside:.1f} s, A로 되돌아가는 전역 경로 {cusp}/{len(plans)}')
