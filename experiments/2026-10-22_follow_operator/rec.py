"""운용자 판정(/follow/target, map 좌표로 변환)·/sim/people 정답·카메라 자세를 녹화. 사용법: rec.py <출력.json> (SIGINT로 끝내면 저장)"""
import json, math, sys, time, signal, rclpy
from rclpy.node import Node
from rclpy.time import Time
from tf2_ros import Buffer, TransformListener
from limbo_interfaces.msg import FollowTarget
from geometry_msgs.msg import PoseArray
from std_msgs.msg import String
rclpy.init(); n = Node('follow_rec'); buf = Buffer(); TransformListener(buf, n)
pending, frames, gt, names = [], [], [], ['']
n.create_subscription(FollowTarget, '/follow/target', lambda m: pending.append((m, time.time())), 50)
n.create_subscription(PoseArray, '/sim/people', lambda m: gt.append((Time.from_msg(m.header.stamp).nanoseconds * 1e-9, [(p.position.x, p.position.y) for p in m.poses])), 50)
n.create_subscription(String, '/sim/people_names', lambda m: names.__setitem__(0, m.data), 10)
stop = [False]; signal.signal(signal.SIGINT, lambda *a: stop.__setitem__(0, True)); signal.signal(signal.SIGTERM, lambda *a: stop.__setitem__(0, True))
def yaw(q): return 2 * math.atan2(q.z, q.w)
while not stop[0]:
    rclpy.spin_once(n, timeout_sec=0.05)
    keep = []
    for m, wall in pending:
        st = Time.from_msg(m.header.stamp)
        try:
            tf = buf.lookup_transform('map', m.header.frame_id, st)
            cam = buf.lookup_transform('map', 'rgbd_camera_link', st)
        except Exception:
            if time.time() - wall < 2.0: keep.append((m, wall))
            continue
        a = yaw(tf.transform.rotation); c, s = math.cos(a), math.sin(a); tx, ty = tf.transform.translation.x, tf.transform.translation.y
        frames.append({'t': st.nanoseconds * 1e-9, 'enrolled': m.enrolled, 'found': m.found, 'reason': m.reason, 'pid': m.person_id,
                       'band': m.band_pixels, 'sim': round(m.similarity, 3), 'since_band': round(m.since_band_sec, 2), 'lost': round(m.lost_sec, 2),
                       'xy': (tx + c * m.position.x - s * m.position.y, ty + s * m.position.x + c * m.position.y) if m.found else None,
                       'cam': (cam.transform.translation.x, cam.transform.translation.y, yaw(cam.transform.rotation))})
    pending = keep
json.dump({'frames': frames, 'gt': gt, 'names': names[0]}, open(sys.argv[1], 'w')); print(f'frames {len(frames)} gt {len(gt)}')
