"""R6 검출 조사: 정답 사람이 카메라 앞 1~5 m·시야 안일 때 같은 프레임에 YOLO(문턱 0.05)를 돌려
신뢰도·박스 크기와, 그 순간 /person_detector/predictions에 그 사람이 있었는지를 CSV로 남긴다.
사용: python det_probe.py <out.csv> [model]"""
import csv, math, sys, time
import numpy as np, rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from geometry_msgs.msg import PoseArray
from nav_msgs.msg import Odometry
from limbo_interfaces.msg import PersonPredictionArray
from ultralytics import YOLO

CAM_X, CAM_Y, HFOV = 0.235, 0.1575, 1.204

class Probe(Node):
    def __init__(self, out, model):
        super().__init__('det_probe')
        self.model = YOLO(model)
        self.w = csv.writer(open(out, 'w', newline=''))
        self.w.writerow(['t', 'dist', 'bearing_deg', 'yolo_max_conf', 'box_h_px', 'box_w_px', 'n_boxes_ge_0.3', 'pred_match'])
        self.people = self.odom = None
        self.preds = (0.0, [])
        self.last = 0.0
        self.saved = 0
        self.create_subscription(PoseArray, '/sim/people', lambda m: setattr(self, 'people', m), 10)
        self.create_subscription(Odometry, '/ground_truth/odom', lambda m: setattr(self, 'odom', m), 10)
        self.create_subscription(PersonPredictionArray, '/person_detector/predictions', self.on_pred, 10)
        self.create_subscription(Image, '/rgbd_camera/image', self.on_image, qos_profile_sensor_data)

    def on_pred(self, m):
        self.preds = (time.time(), [(p.current_position.x, p.current_position.y) for p in m.predictions])

    def on_image(self, msg):
        now = time.time()
        if now - self.last < 0.3 or self.people is None or self.odom is None:
            return
        p = self.odom.pose.pose; q = p.orientation
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        cx = p.position.x + math.cos(yaw) * CAM_X - math.sin(yaw) * CAM_Y
        cy = p.position.y + math.sin(yaw) * CAM_X + math.cos(yaw) * CAM_Y
        targets = []
        for pp in self.people.poses:
            dx, dy = pp.position.x - cx, pp.position.y - cy
            d = math.hypot(dx, dy); b = (math.atan2(dy, dx) - yaw + math.pi) % (2 * math.pi) - math.pi
            if 1.0 <= d <= 5.0 and abs(b) <= HFOV / 2 - 0.05:
                targets.append((d, math.degrees(b), pp.position.x, pp.position.y))
        if not targets:
            return
        self.last = now
        img = np.frombuffer(msg.data, np.uint8).reshape(msg.height, msg.width, -1)[:, :, :3]
        if msg.encoding.lower().startswith('rgb'):
            img = img[:, :, ::-1]
        r = self.model.predict(img, conf=0.05, classes=[0], verbose=False)[0]
        confs = r.boxes.conf.cpu().numpy() if len(r.boxes) else np.array([])
        xyxy = r.boxes.xyxy.cpu().numpy() if len(r.boxes) else np.zeros((0, 4))
        best = int(np.argmax(confs)) if len(confs) else -1
        if self.saved < 8 and any(3.0 <= t[0] <= 4.0 for t in targets):
            import cv2
            vis = r.plot() if len(r.boxes) else img.copy()
            cv2.imwrite(f'{sys.argv[1]}_{self.saved}_{targets[0][0]:.1f}m.jpg', vis); self.saved += 1
        # 예측(odom 기준)은 시작점이 같아 정답(world)과 거의 같은 축이라 0.7 m 안이면 같은 사람으로 본다
        recent = now - self.preds[0] < 0.5
        for d, b, x, y in targets:
            match = recent and any(math.hypot(px - x, py - y) < 0.7 for px, py in self.preds[1])
            self.w.writerow([f'{now:.2f}', f'{d:.2f}', f'{b:.0f}',
                             f'{confs[best]:.2f}' if best >= 0 else '0',
                             f'{xyxy[best][3] - xyxy[best][1]:.0f}' if best >= 0 else '0',
                             f'{xyxy[best][2] - xyxy[best][0]:.0f}' if best >= 0 else '0',
                             int((confs >= 0.3).sum()), int(match)])

rclpy.init()
n = Probe(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else '/home/automaton/limbo/yolo11n.pt')
try:
    rclpy.spin(n)
except Exception:
    pass
