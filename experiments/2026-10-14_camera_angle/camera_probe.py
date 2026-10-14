"""카메라 배치(높이·피치) 비교 측정 노드. 로봇은 원점에 서 있고 Goal을 보내지 않는다.

  person 모드: /person_detector/predictions를 받아 사람 정답 위치(월드 SDF 시간표)까지의 거리 0.5 m 구간마다
               프레임 수·검출 비율·위치 오차(예측 현재 위치 vs 정답)를 센다
  box 모드:    /local_costmap/costmap에서 상자 발자국 안의 최대 비용을 읽는다 (100 = 치명, 99 = 로봇 반경 안)

사용법: camera_probe.py person <초> <월드 sdf 경로>
        camera_probe.py box <초>
"""
import math
import os
import sys
import time

sys.path.insert(0, os.path.expanduser('~/limbo/limbo/src/limbo_evaluation'))
from limbo_evaluation import actors  # noqa: E402

import rclpy  # noqa: E402
from rclpy.node import Node  # noqa: E402
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy  # noqa: E402
from limbo_interfaces.msg import PersonPredictionArray  # noqa: E402
from nav_msgs.msg import OccupancyGrid  # noqa: E402

CAMERA_X, CAMERA_Y = 0.235, 0.1575   # base_link 기준 카메라 위치 (limbo.urdf.xacro)
BIN = 0.5
BOXES = [  # (이름, 중심 x, 중심 y, 반 변) zz_cam_box.sdf와 같게
    ('a 30cm @0.5m', 0.885, 0.16, 0.15),
    ('b 30cm @0.8m', 1.185, 0.61, 0.15),
    ('c 10cm @1.0m', 1.285, -0.34, 0.05),
]


class PersonProbe(Node):
    def __init__(self, world_sdf):
        super().__init__('camera_probe')
        self.people = actors.parse_actor_trajectories(open(world_sdf).read())
        self.bins = {}   # 구간 시작 거리 → [프레임, 검출, 오차 합]
        self.create_subscription(PersonPredictionArray, '/person_detector/predictions', self.cb, 10)

    def cb(self, msg):
        t = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        name, truth_d = actors.nearest_person(self.people, t, CAMERA_X, CAMERA_Y)
        if name == '':
            return
        b = math.floor(truth_d / BIN) * BIN
        row = self.bins.setdefault(b, [0, 0, 0.0])
        row[0] += 1
        if msg.predictions:
            row[1] += 1
            tx, ty = actors.position_at(self.people[name], t)
            p = msg.predictions[0].current_position
            row[2] += math.hypot(p.x - tx, p.y - ty)

    def report(self, label):
        print(f'== person {label}: 거리 구간(m) | 프레임 | 검출 % | 위치 오차 평균 m')
        for b in sorted(self.bins):
            n, d, e = self.bins[b]
            print(f'{b:3.1f}~{b+BIN:3.1f} | {n:4d} | {100*d/n:5.1f} | {e/d if d else float("nan"):.2f}')


class BoxProbe(Node):
    def __init__(self):
        super().__init__('camera_probe')
        self.grid = None
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(OccupancyGrid, '/local_costmap/costmap', self.cb, qos)

    def cb(self, msg):
        self.grid = msg

    def report(self, label):
        print(f'== box {label}: 상자 | 최대 비용 (100 치명, 99 로봇 반경 안, 0 없음)')
        if self.grid is None:
            print('costmap을 못 받음')
            return
        g = self.grid
        for name, cx, cy, h in BOXES:
            best = -1
            for x in (cx - h, cx, cx + h):
                for y in (cy - h, cy, cy + h):
                    i = int((x - g.info.origin.position.x) / g.info.resolution)
                    j = int((y - g.info.origin.position.y) / g.info.resolution)
                    if 0 <= i < g.info.width and 0 <= j < g.info.height:
                        best = max(best, g.data[j * g.info.width + i])
            print(f'{name} | {best}')


def main():
    mode, seconds = sys.argv[1], float(sys.argv[2])
    label = os.environ.get('LABEL', '')
    rclpy.init()
    node = PersonProbe(sys.argv[3]) if mode == 'person' else BoxProbe()
    t0 = time.time()
    while time.time() - t0 < seconds:
        rclpy.spin_once(node, timeout_sec=0.1)
    node.report(label)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
