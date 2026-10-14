import math, sys, glob
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
A=(-6.837,-0.240)
for bag in sys.argv[1:]:
    try:
        r = rosbag2_py.SequentialReader(); r.open(rosbag2_py.StorageOptions(uri=bag, storage_id='mcap'), rosbag2_py.ConverterOptions('', ''))
    except Exception as e:
        print(bag.split('/')[-1], '못 읽음'); continue
    types = {t.name: get_message(t.type) for t in r.get_all_topics_and_types()}
    ds=[]
    while r.has_next():
        tp, raw, t = r.read_next()
        if tp=='/ground_truth/odom':
            m=deserialize_message(raw, types[tp]); p=m.pose.pose.position; v=m.twist.twist.linear
            ds.append((m.header.stamp.sec+m.header.stamp.nanosec*1e-9, math.hypot(p.x-A[0],p.y-A[1]), math.hypot(v.x,v.y)))
    if not ds: print(bag.split('/')[-1],'정답 없음'); continue
    inside=[x for x in ds if x[1]<0.7]
    dur=(inside[-1][0]-inside[0][0]) if len(inside)>1 else 0
    sp=sum(x[2] for x in inside)/max(1,len(inside))
    print(f"{bag.split('/')[-1]}: A 최소 {min(x[1] for x in ds):.2f} m, 0.7 m 안 {dur:.1f} s, 그때 속도 {sp:.2f} m/s")
