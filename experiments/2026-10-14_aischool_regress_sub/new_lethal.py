"""실패 전후 ±4 s 전역 costmap 업데이트마다: 로봇 주변·B→C 복도에서 새로 치명(≥99)이 된 칸 수와 위치"""
import sys, numpy as np, rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
T=int(sys.argv[2])
r = rosbag2_py.SequentialReader(); r.open(rosbag2_py.StorageOptions(uri=sys.argv[1], storage_id='mcap'), rosbag2_py.ConverterOptions('', ''))
types = {t.name: get_message(t.type) for t in r.get_all_topics_and_types()}
g=None; base=None; data=None; plans=[]
while r.has_next():
    tp, raw, t = r.read_next()
    if tp=='/global_costmap/costmap':
        g=deserialize_message(raw, types[tp]); w,h,res=g.info.width,g.info.height,g.info.resolution; ox,oy=g.info.origin.position.x,g.info.origin.position.y
        data=np.array(g.data,dtype=np.int16).reshape(h,w); base=data.copy()
    elif tp=='/global_costmap/costmap_updates' and data is not None:
        u=deserialize_message(raw, types[tp])
        data[u.y:u.y+u.height,u.x:u.x+u.width]=np.array(u.data,dtype=np.int16).reshape(u.height,u.width)
        if abs(t-T)<4e9:
            new=(data>=99)&(base<99)
            ys,xs=np.nonzero(new)
            wx=ox+xs*res; wy=oy+ys*res
            sel=(wx>-14.5)&(wx<-6)&(wy>6.5)&(wy<9.5)
            from scipy.ndimage import distance_transform_edt
            wall = base >= 99
            dist = distance_transform_edt(~wall) * res      # 처음 costmap의 치명(벽+inflation)까지 거리
            d = dist[ys[sel], xs[sel]]
            hist = np.histogram(d, bins=[0, 0.1, 0.2, 0.3, 0.5, 1.0, 9])[0]
            print(f'{(t-T)/1e9:+5.2f} s  B→C 일대 새 치명 {sel.sum():4d}칸, 기존 치명까지 거리 [0,.1,.2,.3,.5,1,∞) {hist.tolist()}')
            if (d > 0.3).any():
                far = np.nonzero(d > 0.3)[0][:6]
                print('     떨어진 칸 예:', [(round(float(wx[sel][k]),2), round(float(wy[sel][k]),2)) for k in far])
    elif tp=='/plan' and abs(t-T)<4e9:
        m=deserialize_message(raw, types[tp]); plans.append(((t-T)/1e9, len(m.poses)))
print('경로 메시지(시각, 점 수):', [(round(a,1),b) for a,b in plans])
