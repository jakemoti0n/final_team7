"""월드 안의 물체(미니언 등)를 정해진 고리 경로를 따라 일정 속도로 움직인다.

사용법: moving_obstacles.py <worlds/<월드>_movers.json>
- Gazebo의 set_pose_vector 서비스로 20 Hz마다 위치를 한꺼번에 옮긴다 (물리 힘이 아니라 위치를 직접 정함 → 속도·경로가 정확)
- 시간은 Gazebo 시뮬레이션 시간을 따른다 (시뮬레이션이 느려지면 같이 느려짐)
- json: {"world", "speed" m/s, "height" m, "groups": [{"loop": [[x, y], ...], "start": m, "members": [{"name", "side" m, "back" m}]}]}
  고리를 따라 start + speed * t 만큼 간 곳이 무리의 가운데. 각 물체는 진행 방향 오른쪽으로 side, 앞으로 back만큼 떨어진 자리
"""
import json
import math
import sys
import time

from gz.msgs10.boolean_pb2 import Boolean
from gz.msgs10.clock_pb2 import Clock
from gz.msgs10.pose_v_pb2 import Pose_V
from gz.transport13 import Node

RATE_HZ = 20.0


class Loop:
    """닫힌 꺾은선 위에서 거리로 위치·방향 찾기"""

    def __init__(self, points):
        self.points = [tuple(p) for p in points]
        self.edges = list(zip(self.points, self.points[1:] + self.points[:1]))
        self.lengths = [math.dist(a, b) for a, b in self.edges]
        self.total = sum(self.lengths)

    def at(self, distance):
        distance %= self.total
        for (a, b), length in zip(self.edges, self.lengths):
            if distance <= length:
                f = distance / length
                return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, math.atan2(b[1] - a[1], b[0] - a[0])
            distance -= length
        a, b = self.edges[-1]
        return b[0], b[1], math.atan2(b[1] - a[1], b[0] - a[0])


def main():
    config = json.load(open(sys.argv[1]))
    world = config['world']
    speed, z = config['speed'], config['height'] / 2
    groups = [(Loop(g['loop']), g['start'], g['members']) for g in config['groups']]
    node = Node()
    sim = {'t': None}

    def on_clock(msg):
        sim['t'] = msg.sim.sec + msg.sim.nsec * 1e-9

    node.subscribe(Clock, f'/world/{world}/clock', on_clock)
    service = f'/world/{world}/set_pose_vector'
    while sim['t'] is None:      # Gazebo가 뜰 때까지 기다린다
        time.sleep(0.5)
    print(f'{world}: 물체 {sum(len(m) for _, _, m in groups)}개를 {speed} m/s로 움직임', flush=True)
    while True:
        request = Pose_V()
        for loop, start, members in groups:
            for m in members:
                x, y, yaw = loop.at(start + speed * sim['t'] + m['back'])
                pose = request.pose.add()
                pose.name = m['name']
                pose.position.x = x + math.sin(yaw) * m['side']
                pose.position.y = y - math.cos(yaw) * m['side']
                pose.position.z = z
                pose.orientation.z, pose.orientation.w = math.sin(yaw / 2), math.cos(yaw / 2)
        node.request(service, request, Pose_V, Boolean, 200)
        time.sleep(1.0 / RATE_HZ)


if __name__ == '__main__':
    main()
