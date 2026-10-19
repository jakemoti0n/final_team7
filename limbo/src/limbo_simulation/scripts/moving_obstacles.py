"""월드 안의 물체와 사람을 움직인다. 두 가지를 한 프로세스에서 20 Hz로 돈다.

1. 물체(미니언 등): 정해진 고리 경로를 일정 속도로. Gazebo set_pose_vector 서비스 (위치를 직접 정함 → 속도·경로가 정확)
2. 사람(actor): 소셜 포스 모델. 목표로 가려는 힘 + 사람·로봇·벽에서 밀려나는 힘을 합쳐 속도를 정하고,
   그 위치를 gz 토픽 /limbo/actor_poses로 보낸다. 월드 SDF의 플러그인 limbo::ActorPoseControl(plugins/actor_pose_control.cpp)이
   actor를 그 자리로 옮긴다 (Gazebo actor는 set_pose로는 안 움직여서 플러그인이 필요하다, 2026-10-14).
   왜 소셜 포스인가: 시간표(trajectory) actor는 로봇을 비켜 주지도 멈추지도 않아 사람 있는 주행 평가가 안 된다 (PROJECT.md 2-5).
   HuNavSim은 Jazzy를 지원하지 않아 직접 구현.

사용법: moving_obstacles.py <worlds/<월드>_movers.json>
json:
  "world": 월드 이름
  "speed", "height", "groups": [...]           — 물체 (이전과 같음). 없어도 됨
  "map": "aischool_2f_map"                      — 벽 반발용 지도 (limbo_navigation/maps). 없으면 벽 힘 없음
  "robot": "limbo"                              — 로봇 모델 이름 (pose/info에서 위치를 읽음)
  "people": [{"name": actor 이름, "type": "yield" | "no_yield" | "approach",
              "speed": m/s, "waypoints": [[x, y], ...], "loop": true, "wait": 초(approach가 로봇 앞에 머무는 시간)}]
  유형:  yield     — 보통 사람. 로봇을 사람처럼 피해 간다
         no_yield  — 로봇을 안 보는 사람(폰 보는 사람). 로봇에서 밀려나는 힘이 없다. 로봇이 알아서 피하거나 멈춰야 한다
         approach  — 손님. 로봇이 approach_distance 안에 들어오면 로봇 쪽으로 와서 stop_distance에 멈춰 wait초 머문 뒤 제 갈 길을 간다
"""
import json
import math
import os
import signal
import sys
import time

from gz.msgs10.boolean_pb2 import Boolean
from gz.msgs10.clock_pb2 import Clock
from gz.msgs10.pose_v_pb2 import Pose_V
from gz.transport13 import Node

RATE_HZ = 20.0
ACTOR_TOPIC = '/limbo/actor_poses'
# 평가(nav_recorder)가 사람 정답 위치를 알 수 있게 ROS로도 낸다. ROS가 없으면 조용히 생략
PEOPLE_TOPIC = '/sim/people'          # geometry_msgs/PoseArray, map 기준
PEOPLE_NAMES_TOPIC = '/sim/people_names'   # std_msgs/String, 쉼표로 이은 이름 (PoseArray와 같은 순서)
ACTOR_Z = 1.0            # 사람 메시 원점(골반) 높이. 월드 시간표 actor와 같음

# 소셜 포스 (Helbing 1995 꼴). 힘은 가속도(m/s²). 거리는 몸 가장자리 사이로 잰다
PERSON_RADIUS = 0.3
ROBOT_RADIUS = 0.4       # v14 외접 반지름 0.39
RELAX_TIME = 0.5         # 원하는 속도로 돌아가는 시간 (s). 작을수록 급하게 방향을 바꿈
PERSON_FORCE = (3.0, 0.3)   # (A m/s², B m): A·exp((r−d)/B). 사람끼리. 2.0이면 복도에서 어깨 간격 0.54 m까지 스쳐 3.0으로 (10-14 눈 확인)
ROBOT_FORCE = (3.0, 0.4)    # yield가 로봇을 피하는 힘. 사람보다 조금 넓게 피한다(기계라 조심함)
WALL_FORCE = (5.0, 0.15)    # 벽. 가까울 때만 강하게
MAX_SPEED_RATIO = 1.3    # 원하는 속도의 몇 배까지 허용
GOAL_REACHED = 0.3       # m, 이 안이면 다음 waypoint
APPROACH_DISTANCE = 3.0  # m, approach형이 로봇을 알아보는 거리
STOP_DISTANCE = 0.8      # m, approach형이 로봇 앞에서 멈추는 거리 (중심 사이)
# 돌아가기: 로봇이 멈춰 길을 막으면 목표 힘(앞으로)과 로봇 반발(뒤로)이 상쇄돼 yield 사람도 로봇 앞에 서 버린다(소셜 포스 국소 최소점).
# 그러면 로봇은 "1 m 안에 1 s 넘게 선 사람 = 손님"으로 보고 기다려 서로 기다린다 (2026-10-14 서브 PC 회귀, 60 s). 실제 사람은 옆으로 돌아간다
SIDESTEP_AHEAD = 2.5     # m, 로봇이 이 거리 안. 1.5는 로봇 코앞까지 간 뒤에야 돌아가기 시작해 틈이 없는 자리에서 섰다(서브 PC Q10)
ROBOT_STOPPED_SPEED = 0.1   # m/s, 로봇이 이보다 느리면 "서 있는 로봇". 서 있는 로봇이 진로에 있으면 막히기 전에 미리 돌아간다 (실제 사람처럼)
SIDESTEP_ANGLE = math.radians(35)   # 목표 방향에서 이 각 안에 로봇이 있으면 "정면을 막음"
STUCK_SPEED = 0.2        # m/s, 목표 쪽으로 나아가는 속도가 이보다 느리면 (밀려났다 다가가기를 반복하는 경우도 잡힌다)
STUCK_TIME = 1.0         # s, 이 시간 넘게 막혀 있으면 돌아가기 시작
SIDESTEP_FORCE = 8.0     # m/s², 옆으로 미는 힘의 상한. 3.0은 1.8 m 복도에서 벽 힘·로봇 반발에 막혀 1.5 m 앞에 다시 섰다(서브 PC 10-14)
SIDESTEP_GAIN = 8.0      # 1/s², 목표 옆 자리까지 남은 거리에 비례해 민다 (일정한 힘은 로봇이 복도 가운데서 벗어나 있으면 옆 0.5 m에서 다시 멈췄다, 서브 PC Q9)
SIDESTEP_MARGIN = 0.1    # m, 로봇 옆을 지날 때 몸 가장자리 사이 여유. 목표 옆 자리 = 로봇 중심에서 (로봇 반경 + 돌아갈 때 몸 반경 + 여유)
SIDESTEP_PERSON_RADIUS = 0.2   # m, 돌아가는 동안의 몸 반경(어깨를 틀어 좁힘). 1.8 m 복도에 0.8 m 로봇이 서 있으면 한쪽 0.5 m뿐이라 이게 없으면 벽·로봇 힘에 끼어 멈춘다
SIDESTEP_ROBOT_FORCE = (3.0, 0.15)  # 돌아가는 동안의 로봇 반발. B를 줄여 "바짝 지나가기로 한" 사람은 로봇과 0.6 m까지 좁힌다


class Loop:
    """닫힌 꺾은선 위에서 거리로 위치·방향 찾기 (물체용)"""

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


class WallMap:
    """지도 이미지의 거리 변환으로 가장 가까운 벽까지 거리와 벽에서 멀어지는 방향을 준다"""

    def __init__(self, map_name):
        import cv2
        import numpy as np
        import yaml
        from ament_index_python.packages import get_package_share_directory
        folder = os.path.join(get_package_share_directory('limbo_navigation'), 'maps')
        meta = yaml.safe_load(open(os.path.join(folder, map_name + '.yaml')))
        image = cv2.imread(os.path.join(folder, meta['image']), cv2.IMREAD_GRAYSCALE)
        free = (image > 255 * (1 - meta['free_thresh'])).astype(np.uint8)   # 흰 칸 = 빈 곳
        self.distance = cv2.distanceTransform(free, cv2.DIST_L2, 5) * meta['resolution']
        self.resolution = meta['resolution']
        self.origin_x, self.origin_y = meta['origin'][0], meta['origin'][1]
        self.height = image.shape[0]

    def _cell(self, x, y):
        i = int((x - self.origin_x) / self.resolution)
        j = self.height - 1 - int((y - self.origin_y) / self.resolution)   # 이미지는 위가 북쪽
        if 0 <= i < self.distance.shape[1] and 0 <= j < self.distance.shape[0]:
            return self.distance[j, i]
        return 0.0

    def nearest(self, x, y):
        """(벽까지 거리, 벽에서 멀어지는 단위 방향). 거리 변환의 기울기가 그 방향"""
        d = self._cell(x, y)
        h = self.resolution
        gx = (self._cell(x + h, y) - self._cell(x - h, y)) / (2 * h)
        gy = (self._cell(x, y + h) - self._cell(x, y - h)) / (2 * h)
        norm = math.hypot(gx, gy)
        return d, ((gx / norm, gy / norm) if norm > 1e-6 else (0.0, 0.0))


def exp_force(params, gap):
    """가장자리 사이 거리 gap에서 밀어내는 힘의 크기"""
    a, b = params
    return a * math.exp(-gap / b)


class Person:

    def __init__(self, spec):
        self.name = spec['name']
        self.type = spec.get('type', 'yield')
        self.speed = spec.get('speed', 0.8)
        self.waypoints = [tuple(w) for w in spec['waypoints']]
        self.loop = spec.get('loop', True)
        self.wait = spec.get('wait', 5.0)
        self.x, self.y = self.waypoints[0]
        self.vx = self.vy = 0.0
        self.yaw = 0.0
        self.goal_index = 1 if len(self.waypoints) > 1 else 0
        self.waiting_until = None    # approach형이 로봇 앞에 멈춘 뒤 떠나는 시각
        self.served = False          # 한 로봇 방문에 한 번만 다가간다
        self.blocked_since = None    # yield형이 로봇 정면에 막혀 느려진 시각
        self.robot_hist = None       # (시각, x, y) 로봇 속도 추정용
        self.sidestep = None         # 돌아가는 중이면 옆 방향 단위 벡터

    def goal(self, robot, t):
        """지금 향할 점. approach형은 로봇이 가까우면 로봇이 목표"""
        if self.type == 'approach' and robot is not None and self.served:
            # 로봇이 알아보는 거리 밖으로 떠나야 다음 방문으로 본다. 집 자리에 닿을 때 풀면, 서 있는 로봇 곁으로
            # 돌아와 다시 다가가기를 끝없이 되풀이한다 (2026-10-19 손님 연기 시험: 로봇이 150 s 동안 못 떠남)
            if math.dist((self.x, self.y), robot) > APPROACH_DISTANCE:
                self.served = False
                self.waiting_until = None
        if self.type == 'approach' and robot is not None and not self.served:
            d = math.dist((self.x, self.y), robot)
            if d < APPROACH_DISTANCE:
                if d <= STOP_DISTANCE:
                    if self.waiting_until is None:
                        self.waiting_until = t + self.wait
                    if t < self.waiting_until:
                        return None            # 멈춰서 기다림
                    self.served = True
                else:
                    return robot
        return self.waypoints[self.goal_index]

    def step(self, dt, t, robot, others, walls):
        goal = self.goal(robot, t)
        if goal is None:
            self.vx = self.vy = 0.0
            return
        if math.dist((self.x, self.y), goal) < GOAL_REACHED and goal is not robot:
            self._next_goal()
            goal = self.waypoints[self.goal_index]
        ax, ay = self._goal_force(goal)
        for p in others:
            ax, ay = self._add_repulsion(ax, ay, (p.x, p.y), PERSON_RADIUS + PERSON_RADIUS, PERSON_FORCE)
        body = SIDESTEP_PERSON_RADIUS if self.sidestep else PERSON_RADIUS   # 돌아가는 동안은 어깨를 틀어 좁게
        if robot is not None and self.type == 'yield':
            ax, ay = self._add_repulsion(ax, ay, robot, body + ROBOT_RADIUS,
                                         SIDESTEP_ROBOT_FORCE if self.sidestep else ROBOT_FORCE)
            ax, ay = self._add_sidestep(ax, ay, goal, robot, walls, t)
        if walls is not None:
            d, (nx, ny) = walls.nearest(self.x, self.y)
            f = exp_force(WALL_FORCE, d - body)
            ax, ay = ax + f * nx, ay + f * ny
        self.vx += ax * dt
        self.vy += ay * dt
        speed = math.hypot(self.vx, self.vy)
        limit = self.speed * MAX_SPEED_RATIO
        if speed > limit:
            self.vx, self.vy = self.vx / speed * limit, self.vy / speed * limit
        self.x += self.vx * dt
        self.y += self.vy * dt
        if speed > 0.05:
            self.yaw = math.atan2(self.vy, self.vx)

    def _next_goal(self):
        if self.goal_index + 1 < len(self.waypoints):
            self.goal_index += 1
        elif self.loop:
            self.goal_index = 0

    def _goal_force(self, goal):
        dx, dy = goal[0] - self.x, goal[1] - self.y
        d = math.hypot(dx, dy)
        if d < 1e-6:
            return -self.vx / RELAX_TIME, -self.vy / RELAX_TIME
        return ((self.speed * dx / d - self.vx) / RELAX_TIME,
                (self.speed * dy / d - self.vy) / RELAX_TIME)

    def _add_sidestep(self, ax, ay, goal, robot, walls, t):
        """로봇이 정면을 막아 STUCK_TIME 넘게 느려지면 벽 여유가 큰 쪽으로 옆 힘을 더한다. 로봇을 지나치면 끝"""
        dx, dy = robot[0] - self.x, robot[1] - self.y
        d = math.hypot(dx, dy)
        gx, gy = goal[0] - self.x, goal[1] - self.y
        g = math.hypot(gx, gy)
        if d < 1e-6 or g < 1e-6:
            return ax, ay
        robot_speed = None
        if self.robot_hist is not None and t > self.robot_hist[0]:
            robot_speed = math.dist(robot, self.robot_hist[1:]) / (t - self.robot_hist[0])
        self.robot_hist = (t, robot[0], robot[1])
        toward = (dx * gx + dy * gy) / (d * g)        # 목표 방향과 로봇 방향의 cos
        ahead = d < SIDESTEP_AHEAD and toward > math.cos(SIDESTEP_ANGLE)
        if self.sidestep is None:
            progress = (self.vx * gx + self.vy * gy) / g       # 목표 쪽 속도 성분
            robot_stopped = robot_speed is not None and robot_speed < ROBOT_STOPPED_SPEED
            # 서 있는 로봇이 진로에 있거나(미리 돌아감), 내가 막혀 못 나아가면(뒤늦게라도 돌아감)
            if ahead and (robot_stopped or progress < STUCK_SPEED):
                if self.blocked_since is None:
                    self.blocked_since = t
                elif t - self.blocked_since > STUCK_TIME:
                    lx, ly = -dy / d, dx / d                   # 로봇 방향의 왼쪽
                    # 로봇 양옆의 지나갈 자리에서 벽까지 거리를 비교한다 (사람 위치 기준으로 재면 로봇이 한쪽에 치우쳐 있어도 못 가른다)
                    want = SIDESTEP_PERSON_RADIUS + ROBOT_RADIUS + SIDESTEP_MARGIN
                    left = walls.nearest(robot[0] + lx * want, robot[1] + ly * want)[0] if walls else 1.0
                    right = walls.nearest(robot[0] - lx * want, robot[1] - ly * want)[0] if walls else 1.0
                    self.sidestep = (lx, ly) if left >= right else (-lx, -ly)
                    self.blocked_since = None
                    print(f'{self.name}: 로봇에 막혀 {"왼쪽" if left >= right else "오른쪽"}으로 돌아감 (t={t:.1f})', flush=True)
            else:
                self.blocked_since = None
            return ax, ay
        if toward < 0.0 or d > SIDESTEP_AHEAD + 1.0:   # 로봇이 뒤로 갔거나 멀어짐
            self.sidestep = None
            return ax, ay
        # 로봇 옆 목표 자리(반경 합 + 여유)까지 남은 옆 거리에 비례해 민다. 자리에 닿으면 힘이 0이라 벽 쪽으로 더 밀지 않는다
        sx, sy = self.sidestep
        lateral = (self.x - robot[0]) * sx + (self.y - robot[1]) * sy
        want = SIDESTEP_PERSON_RADIUS + ROBOT_RADIUS + SIDESTEP_MARGIN
        f = max(-SIDESTEP_FORCE, min(SIDESTEP_FORCE, SIDESTEP_GAIN * (want - lateral)))
        return ax + f * sx, ay + f * sy

    def _add_repulsion(self, ax, ay, other, radii, params):
        dx, dy = self.x - other[0], self.y - other[1]
        d = math.hypot(dx, dy)
        if d < 1e-6:
            return ax, ay
        f = exp_force(params, d - radii)
        return ax + f * dx / d, ay + f * dy / d


def load_groups(config):
    return [(Loop(g['loop']), g['start'], g['members']) for g in config.get('groups', [])]


def object_poses(groups, speed, z, t):
    request = Pose_V()
    for loop, start, members in groups:
        for m in members:
            x, y, yaw = loop.at(start + speed * t + m['back'])
            pose = request.pose.add()
            pose.name = m['name']
            pose.position.x = x + math.sin(yaw) * m['side']
            pose.position.y = y - math.cos(yaw) * m['side']
            pose.position.z = z
            pose.orientation.z, pose.orientation.w = math.sin(yaw / 2), math.cos(yaw / 2)
    return request


def people_poses(people):
    msg = Pose_V()
    for p in people:
        pose = msg.pose.add()
        pose.name = p.name
        pose.position.x, pose.position.y, pose.position.z = p.x, p.y, ACTOR_Z
        pose.orientation.z, pose.orientation.w = math.sin(p.yaw / 2), math.cos(p.yaw / 2)
    return msg


class RosPeoplePublisher:
    """사람 위치를 ROS 토픽으로 낸다. spin 없이 publish만 하므로 gz 루프와 같이 돌 수 있다"""

    def __init__(self, people):
        import rclpy
        from geometry_msgs.msg import PoseArray
        from std_msgs.msg import String
        rclpy.init()
        self.node = rclpy.create_node('sim_people')
        self.pose_pub = self.node.create_publisher(PoseArray, PEOPLE_TOPIC, 10)
        self.name_pub = self.node.create_publisher(String, PEOPLE_NAMES_TOPIC, 10)
        self.PoseArray, self.String = PoseArray, String
        self.names = ','.join(p.name for p in people)

    def publish(self, people, t):
        msg = self.PoseArray()
        msg.header.frame_id = 'map'
        msg.header.stamp.sec, msg.header.stamp.nanosec = int(t), int((t - int(t)) * 1e9)
        from geometry_msgs.msg import Pose
        for p in people:
            pose = Pose()
            msg.poses.append(pose)
            pose.position.x, pose.position.y, pose.position.z = p.x, p.y, 0.0
            pose.orientation.z, pose.orientation.w = math.sin(p.yaw / 2), math.cos(p.yaw / 2)
        try:
            self.pose_pub.publish(msg)
            self.name_pub.publish(self.String(data=self.names))
        except Exception:      # launch가 끝날 때 ROS가 먼저 내려가면 publish가 예외를 낸다. 조용히 넘긴다
            pass


def main():
    config = json.load(open(sys.argv[1]))
    world = config['world']
    groups = load_groups(config)
    people = [Person(spec) for spec in config.get('people', [])]
    walls = WallMap(config['map']) if config.get('map') and people else None
    robot_name = config.get('robot', 'limbo')

    node = Node()
    # gz transport가 SIGINT·SIGTERM 핸들러를 걸어 신호를 삼키므로, launch가 끝낼 때 이 스크립트가 남지 않게 우리 핸들러로 덮는다
    # (2026-10-14: 잔존 스크립트 둘이 같은 actor에 다른 위치를 보내 사람이 두 자리를 번갈아 그려짐)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: sys.exit(0))
    sim = {'t': None, 'robot': None}

    def on_clock(msg):
        sim['t'] = msg.sim.sec + msg.sim.nsec * 1e-9

    def on_pose(msg):
        for pose in msg.pose:
            if pose.name == robot_name:
                sim['robot'] = (pose.position.x, pose.position.y)

    node.subscribe(Clock, f'/world/{world}/clock', on_clock)
    if people:
        node.subscribe(Pose_V, f'/world/{world}/dynamic_pose/info', on_pose)
    actor_pub = node.advertise(ACTOR_TOPIC, Pose_V)
    ros_pub = None
    if people:
        try:
            ros_pub = RosPeoplePublisher(people)
        except Exception as e:       # ROS 없이 gz만 띄운 경우
            print(f'ROS 사람 위치 발행 안 함: {e}', flush=True)
    service = f'/world/{world}/set_pose_vector'
    while sim['t'] is None:      # Gazebo가 뜰 때까지 기다린다
        time.sleep(0.5)
    print(f'{world}: 물체 {sum(len(m) for _, _, m in groups)}개, 사람 {len(people)}명 '
          f'({", ".join(p.type for p in people)})', flush=True)

    last_t = sim['t']
    while True:
        t = sim['t']
        dt = min(max(t - last_t, 0.0), 0.2)    # 시뮬레이션이 멈췄다 가도 한 번에 크게 뛰지 않게
        last_t = t
        if groups:
            node.request(service, object_poses(groups, config['speed'], config['height'] / 2, t), Pose_V, Boolean, 200)
        if people:
            for p in people:
                p.step(dt, t, sim['robot'], [q for q in people if q is not p], walls)
            actor_pub.publish(people_poses(people))
            if ros_pub is not None:
                ros_pub.publish(people, t)
        time.sleep(1.0 / RATE_HZ)


if __name__ == '__main__':
    main()
