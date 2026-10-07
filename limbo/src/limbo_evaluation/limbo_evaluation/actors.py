"""
월드 SDF에 적힌 Gazebo actor 시간표로 사람의 정답 위치를 계산한다.

actor는 정해진 시간표대로만 움직이므로 시뮬레이션 시각만 알면 위치가 정해진다.
SDF 규칙상 반복(loop)할 때마다 delay_start만큼 첫 위치에서 기다렸다가 다시 걷는다.
"""

from dataclasses import dataclass
import math
import re

ACTOR_PATTERN = re.compile(r'<actor name="([^"]+)">(.*?)</actor>', re.S)
WAYPOINT_PATTERN = re.compile(
    r'<waypoint>\s*<time>([-\d.e]+)</time>\s*<pose>([^<]+)</pose>\s*</waypoint>')
DELAY_PATTERN = re.compile(r'<delay_start>([-\d.e]+)</delay_start>')
LOOP_PATTERN = re.compile(r'<loop>\s*(true|false|1|0)\s*</loop>')


@dataclass(frozen=True)
class Trajectory:
    waypoints: tuple   # ((시각, x, y), ...)
    delay: float = 0.0
    loop: bool = True


def parse_actor_trajectories(sdf_text):
    """{actor 이름: Trajectory}. 경로 점이 두 개 미만인 actor는 뺀다."""
    trajectories = {}
    for name, body in ACTOR_PATTERN.findall(sdf_text):
        waypoints = tuple(
            (float(t), *map(float, pose.split()[:2]))
            for t, pose in WAYPOINT_PATTERN.findall(body))
        if len(waypoints) < 2:
            continue
        delay = DELAY_PATTERN.search(body)
        loop = LOOP_PATTERN.search(body)
        trajectories[name] = Trajectory(
            waypoints=waypoints,
            delay=float(delay.group(1)) if delay else 0.0,
            loop=loop.group(1) in ('true', '1') if loop else True)
    return trajectories


def position_at(trajectory, sim_time):
    """시뮬레이션 시각 sim_time(초)에 actor가 있는 (x, y)."""
    waypoints = trajectory.waypoints
    duration = waypoints[-1][0]
    t = sim_time
    if trajectory.loop:
        t %= trajectory.delay + duration
    t -= trajectory.delay
    if t <= waypoints[0][0]:
        return waypoints[0][1], waypoints[0][2]
    for (t0, x0, y0), (t1, x1, y1) in zip(waypoints, waypoints[1:]):
        if t <= t1:
            a = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return x0 + a * (x1 - x0), y0 + a * (y1 - y0)
    return waypoints[-1][1], waypoints[-1][2]


def nearest_person(trajectories, sim_time, x, y):
    """(x, y)에서 가장 가까운 사람의 (이름, 거리). 사람이 없으면 ('', inf)."""
    best_name, best_distance = '', math.inf
    for name, trajectory in trajectories.items():
        distance = math.dist(position_at(trajectory, sim_time), (x, y))
        if distance < best_distance:
            best_name, best_distance = name, distance
    return best_name, best_distance
