"""2단계 기록: /follow/state, /follow/target(found), /person_wait, 로봇 map 자세(10 Hz), /sim/people 정답. 사용법: rec2.py <출력.json>"""
import json, math, sys, time, signal, rclpy
from rclpy.node import Node
from rclpy.time import Time
from tf2_ros import Buffer, TransformListener
from limbo_interfaces.msg import FollowState, FollowTarget, PersonWait
from geometry_msgs.msg import PoseArray
from std_msgs.msg import String
rclpy.init(); n = Node('follow_rec2'); buf = Buffer(); TransformListener(buf, n)
states, targets, waits, robot, gt, names = [], [], [], [], [], ['']
sec = lambda st: Time.from_msg(st).nanoseconds * 1e-9
n.create_subscription(FollowState, '/follow/state', lambda m: states.append((sec(m.header.stamp), m.state, m.reason, m.target_id, round(m.distance, 2), round(m.lost_sec, 1))), 50)
n.create_subscription(FollowTarget, '/follow/target', lambda m: targets.append((sec(m.header.stamp), m.found, m.reason, m.band_pixels, m.person_id)), 50)
boxes = []   # 프레임마다 (t, YOLO 박스 수, 합친 뒤 박스 수, 박스 목록) — 근거리에서 검출 자체가 끊기는지 보려고
n.create_subscription(String, '/person_detector/boxes', lambda m: boxes.append((lambda j: (j['t'], len(j['boxes']), len(j['kept']), j['kept']))(json.loads(m.data))), 50)
n.create_subscription(PersonWait, '/person_wait', lambda m: waits.append((sec(m.header.stamp), m.wait, m.reason, m.tracks_in_zone)), 50)
n.create_subscription(PoseArray, '/sim/people', lambda m: gt.append((sec(m.header.stamp), [(p.position.x, p.position.y) for p in m.poses])), 50)
n.create_subscription(String, '/sim/people_names', lambda m: names.__setitem__(0, m.data), 10)
stop = [False]; signal.signal(signal.SIGINT, lambda *a: stop.__setitem__(0, True)); signal.signal(signal.SIGTERM, lambda *a: stop.__setitem__(0, True))
last = 0.0
while not stop[0]:
    rclpy.spin_once(n, timeout_sec=0.05)
    if time.time() - last >= 0.1:
        last = time.time()
        try:
            tf = buf.lookup_transform('map', 'base_link', Time()); q = tf.transform.rotation
            robot.append((sec(tf.header.stamp), tf.transform.translation.x, tf.transform.translation.y, 2 * math.atan2(q.z, q.w)))
        except Exception:
            pass
json.dump({'states': states, 'targets': targets, 'waits': waits, 'robot': robot, 'gt': gt, 'names': names[0], 'boxes': boxes}, open(sys.argv[1], 'w'))
print(f'states {len(states)} robot {len(robot)} gt {len(gt)}')
