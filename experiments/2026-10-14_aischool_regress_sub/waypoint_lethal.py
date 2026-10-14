"""전역 costmap 시간 흐름에서 웨이포인트 칸(A·B·C·D) 비용이 치명(≥99)이 된 시간"""
import sys, numpy as np, rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from scipy.ndimage import distance_transform_edt
W={'A':(-6.837,-0.240),'B':(-6.827,7.997),'C':(-13.742,7.998),'D':(-13.970,0.641)}
for bag in sys.argv[1:]:
    r = rosbag2_py.SequentialReader(); r.open(rosbag2_py.StorageOptions(uri=bag, storage_id='mcap'), rosbag2_py.ConverterOptions('', ''))
    types = {t.name: get_message(t.type) for t in r.get_all_topics_and_types()}
    data=None; hits={k:0 for k in W}; n=0; first=True
    while r.has_next():
        tp, raw, t = r.read_next()
        if tp=='/global_costmap/costmap':
            g=deserialize_message(raw, types[tp]); w,h,res=g.info.width,g.info.height,g.info.resolution; ox,oy=g.info.origin.position.x,g.info.origin.position.y
            data=np.array(g.data,dtype=np.int16).reshape(h,w)
            if first:
                free=data<99; dist=distance_transform_edt(free)*res
                print(bag.split('/')[-1], '처음 costmap에서 치명까지 여유:', {k:round(float(dist[int((y-oy)/res),int((x-ox)/res)]),2) for k,(x,y) in W.items()}); first=False
        elif tp=='/global_costmap/costmap_updates' and data is not None:
            u=deserialize_message(raw, types[tp]); data[u.y:u.y+u.height,u.x:u.x+u.width]=np.array(u.data,dtype=np.int16).reshape(u.height,u.width); n+=1
            for k,(x,y) in W.items():
                if data[int((y-oy)/res),int((x-ox)/res)]>=99:
                    hits[k]+=1; print('   ', k, '치명 at 벽시계', t)
    print('   업데이트', n, '중 웨이포인트 칸이 치명이던 횟수', hits)
