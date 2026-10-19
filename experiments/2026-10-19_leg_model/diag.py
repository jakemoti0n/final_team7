"""지정한 map 위치(기본 손님 1회차 오검출 자리 -4.0, 2.5)가 카메라 시야 5 m 안에 들 때 RGB에 YOLO 박스를 그려 PNG로 저장.
사용법: diag.py <출력 폴더> [x y]  (SIGINT로 끝냄). 박스: 초록 person, 주황 leg(신뢰도 표시), 흰 테두리 = 합친 뒤 남은 박스.
파일 이름: <카메라 시각>_<거리>m.png, 0.5 s에 한 장까지."""
import json, math, os, sys, signal, rclpy, cv2
from rclpy.node import Node
from rclpy.time import Time
from tf2_ros import Buffer, TransformListener
from sensor_msgs.msg import Image
from std_msgs.msg import String
from cv_bridge import CvBridge
from rclpy.qos import qos_profile_sensor_data
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
TX, TY = (float(sys.argv[2]), float(sys.argv[3])) if len(sys.argv) > 3 else (-4.0, 2.5)
rclpy.init(); n = Node('leg_diag'); buf = Buffer(); TransformListener(buf, n); br = CvBridge()
imgs, last = {}, [0.0]
def on_img(m): imgs[round(Time.from_msg(m.header.stamp).nanoseconds * 1e-9, 3)] = m; [imgs.pop(k) for k in sorted(imgs)[:-30]]
def on_boxes(m):
    d = json.loads(m.data); t = round(d['t'], 3)
    if t - last[0] < 0.5 or t not in imgs: return
    try: tf = buf.lookup_transform('map', 'rgbd_camera_link', Time(nanoseconds=int(t * 1e9)))
    except Exception: return
    cx, cy = tf.transform.translation.x, tf.transform.translation.y; q = tf.transform.rotation; yaw = 2 * math.atan2(q.z, q.w)
    dist = math.hypot(TX - cx, TY - cy); bear = abs((math.atan2(TY - cy, TX - cx) - yaw + math.pi) % (2 * math.pi) - math.pi)
    if dist > 5 or bear > math.radians(36): return
    last[0] = t; img = br.imgmsg_to_cv2(imgs[t], 'bgr8')
    for c, x1, y1, x2, y2, f in d['boxes']:
        col = (0, 200, 0) if c == 0 else (0, 140, 255)
        cv2.rectangle(img, (x1, y1), (x2, y2), col, 2); cv2.putText(img, f"{'P' if c == 0 else 'L'} {f:.2f}", (x1, max(12, y1 - 4)), 0, 0.45, col, 1)
    for x1, y1, x2, y2, leg in d['kept']: cv2.rectangle(img, (x1 - 3, y1 - 3), (x2 + 3, y2 + 3), (255, 255, 255), 1)
    cv2.imwrite(f"{out}/{t:.2f}_{dist:.1f}m.png", img)
n.create_subscription(Image, '/rgbd_camera/image', on_img, qos_profile_sensor_data)
n.create_subscription(String, '/person_detector/boxes', on_boxes, 10)
stop = [False]; signal.signal(signal.SIGINT, lambda *a: stop.__setitem__(0, True)); signal.signal(signal.SIGTERM, lambda *a: stop.__setitem__(0, True))
while not stop[0]: rclpy.spin_once(n, timeout_sec=0.05)
print('저장', len(os.listdir(out)), '장')
