"""코앞 트랙 소실 진단. ToF가 범퍼 앞 0.5 m 안에 무언가를 보는데 /person_wait 구역 트랙이 0인 순간의 RGB에
YOLO 박스를 그려 PNG로 남기고(박스 그리기는 2026-10-19_leg_model/diag.py와 같음), 그런 ToF 메시지마다 CSV 한 줄을 쓴다.
사용법: close_diag.py <출력 폴더>  (SIGINT로 끝냄)
CSV: t, ToF 범퍼 앞 거리, collision_monitor 동작, person_wait 상태·사유·구역 트랙 수, 예측 수, 박스 수,
     박스별 "클래스:폭px:위잘림:아래잘림", 합친 뒤 박스 수, PNG 저장 여부"""
import csv, json, os, signal, sys, rclpy, cv2
from rclpy.node import Node
from rclpy.time import Time
from sensor_msgs.msg import Image
from std_msgs.msg import String
from geometry_msgs.msg import PointStamped
from nav2_msgs.msg import CollisionMonitorState
from limbo_interfaces.msg import PersonPredictionArray, PersonWait
from cv_bridge import CvBridge
from rclpy.qos import qos_profile_sensor_data
BUMPER_X, TOF_NEAR, EDGE = 0.25, 0.5, 2
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
rclpy.init(); n = Node('close_diag'); br = CvBridge()
imgs, last, st = {}, [0.0], {'tof': (None, 0.0), 'cm': '', 'pw': None, 'pred': 0}
f = open(f'{out}/close_diag.csv', 'w', newline=''); w = csv.writer(f)
w.writerow(['t', 'tof_ahead_m', 'cm_action', 'pw_state', 'pw_reason', 'pw_zone_tracks', 'predictions',
            'boxes', 'box_list', 'kept', 'png'])
def on_img(m): imgs[round(Time.from_msg(m.header.stamp).nanoseconds * 1e-9, 3)] = m; [imgs.pop(k) for k in sorted(imgs)[:-30]]
def on_cm(m): st['cm'] = f'{m.action_type}:{m.polygon_name}'
def on_pw(m): st['pw'] = m
def on_pred(m): st['pred'] = len(m.predictions)
def on_boxes(m): st['boxes'] = json.loads(m.data)
def on_tof(m):
    """ToF가 코앞(TOF_NEAR 안)에 무언가를 볼 때마다 한 줄. 박스 메시지는 트랙 ID가 있을 때만 오므로 0.3 s 안 것만 '있음'."""
    tof = m.point.x - BUMPER_X; t = Time.from_msg(m.header.stamp).nanoseconds * 1e-9; pw = st['pw']
    if tof >= TOF_NEAR:
        return
    d = st.get('boxes')
    d = d if d is not None and abs(d['t'] - t) < 0.3 else {'t': t, 'boxes': [], 'kept': []}
    img_msg = imgs.get(round(d['t'], 3)) or (imgs[max(imgs)] if imgs else None); h = img_msg.height if img_msg else 0
    boxes = [f"{'P' if c == 0 else 'L'}:{x2 - x1}:{int(y1 <= EDGE)}:{int(h and y2 >= h - EDGE)}" for c, x1, y1, x2, y2, _ in d['boxes']]
    lost = pw is not None and pw.tracks_in_zone == 0
    png = ''
    if lost and img_msg is not None and t - last[0] >= 0.5:
        last[0] = t; img = br.imgmsg_to_cv2(img_msg, 'bgr8')
        for c, x1, y1, x2, y2, conf in d['boxes']:
            col = (0, 200, 0) if c == 0 else (0, 140, 255)
            cv2.rectangle(img, (x1, y1), (x2, y2), col, 2); cv2.putText(img, f"{'P' if c == 0 else 'L'} {conf:.2f}", (x1, max(12, y1 - 4)), 0, 0.45, col, 1)
        for x1, y1, x2, y2, leg in d['kept']: cv2.rectangle(img, (x1 - 3, y1 - 3), (x2 + 3, y2 + 3), (255, 255, 255), 1)
        cv2.putText(img, f"tof {tof:.2f} m  {st['cm']}  pw {pw.state} {pw.reason}", (5, 15), 0, 0.45, (0, 0, 255), 1)
        png = f'{t:.2f}_tof{tof:.2f}.png'; cv2.imwrite(f'{out}/{png}', img)
    w.writerow([round(t, 3), round(tof, 3), st['cm'], pw.state if pw else '', pw.reason if pw else '',
                pw.tracks_in_zone if pw else '', st['pred'], len(d['boxes']), ' '.join(boxes), len(d['kept']), png]); f.flush()
n.create_subscription(Image, '/rgbd_camera/image', on_img, qos_profile_sensor_data)
n.create_subscription(String, '/person_detector/boxes', on_boxes, 10)
n.create_subscription(PointStamped, '/tof/nearest', on_tof, 10)
n.create_subscription(CollisionMonitorState, '/collision_monitor_state', on_cm, 10)
n.create_subscription(PersonWait, '/person_wait', on_pw, 10)
n.create_subscription(PersonPredictionArray, '/person_detector/predictions', on_pred, 10)
stop = [False]; signal.signal(signal.SIGINT, lambda *a: stop.__setitem__(0, True)); signal.signal(signal.SIGTERM, lambda *a: stop.__setitem__(0, True))
while not stop[0]: rclpy.spin_once(n, timeout_sec=0.05)
f.close(); print('PNG', sum(x.endswith('.png') for x in os.listdir(out)), '장')
