"""Nav2 Goal 하나 동안 모은 값으로 평가 지표(CSV 한 줄)를 만든다."""

import bisect
from collections import deque
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class MetricsConfig:
    personal_space: float = 0.5   # m, 사람 중심에서 이 거리 안이면 개인 공간 침범으로 센다
    # m, 로봇 중심과 사람 중심이 이보다 가까우면 사람 모델과 겹친 것이라 충돌로 센다.
    # 시뮬레이션 사람은 충돌이 없어 "성공"에 뚫고 지나간 경우가 섞이기 때문에 따로 센다
    collision_distance: float = 0.3
    # m, 멈춰 있을 때 사람이 이 거리 안에 있으면 "사람 때문에 멈춤", 없으면 "막혀서 멈춤"으로 나눈다
    near_person_distance: float = 1.5
    stop_speed: float = 0.05      # m/s, 이보다 느리면 멈춘 것으로 본다
    # m, 새 전역 경로가 직전 경로에서 이보다 멀리 벗어나면 "경로가 바뀜"으로 센다
    plan_change_distance: float = 0.3
    plan_sample_spacing: float = 0.2   # m, 경로 비교는 이 간격으로 점을 골라서 한다 (계산량)
    # s, 사람 최소 거리 순간의 "사람이 다가온 속도"·"로봇 속도"를 이 시간 전 위치와 비교해 구한다.
    # 사람이 멈춘 로봇에 걸어 들어온 충돌(사람 탓)과 로봇이 사람에게 간 충돌(로봇 탓)을 가르기 위해
    speed_window: float = 0.5


class GoalMetrics:

    def __init__(self, config):
        self.config = config
        self.start_time = None
        self.end_time = None
        self.start_xy = None
        self.last_xy = None
        self.path_length = 0.0
        self.min_person_distance = math.inf
        self.nearest_person = ''
        self.person_approach_speed = math.nan   # 최소 거리 순간, 사람이 로봇 쪽으로 다가온 속도 (m/s, 양수 = 다가옴)
        self.robot_speed_at_min = math.nan       # 최소 거리 순간의 로봇 속도 (m/s)
        self.history = deque()                   # (시각, 로봇 x, y, 사람 x, y) 최근 speed_window 초
        self.personal_space_time = 0.0
        self.collision_time = 0.0
        self.stopped_time = 0.0
        self.stopped_near_person_time = 0.0
        self.last_plan = None
        self.plan_updates = 0
        self.plan_changes = 0
        self.min_obstacle_distance = math.inf
        self.nearest_obstacle = ''
        self.obstacle_contact_time = 0.0
        self.localization_errors = []
        self.recoveries = 0
        self.controller_warnings = 0
        self.slip_events = 0

    def add_truth(self, sim_time, x, y, person_name, person_distance, person_xy=None):
        """정답 위치 한 번. 사람 거리는 가장 가까운 사람까지, person_xy는 그 사람 위치(없으면 속도 열은 비움)."""
        if self.last_xy is None:
            self.start_time, self.start_xy = sim_time, (x, y)
        else:
            step = math.dist(self.last_xy, (x, y))
            dt = sim_time - self.end_time
            self.path_length += step
            self._add_time_near_person(dt, person_distance)
            if dt > 0 and step / dt < self.config.stop_speed:
                self._add_stopped_time(dt, person_distance)
        self.last_xy, self.end_time = (x, y), sim_time

        if person_distance < self.min_person_distance:
            self.min_person_distance = person_distance
            self.nearest_person = person_name
            self.person_approach_speed, self.robot_speed_at_min = \
                self._speeds_at(sim_time, x, y, person_xy)
        self._remember(sim_time, x, y, person_xy)

    def _remember(self, t, x, y, person_xy):
        self.history.append((t, x, y) + (tuple(person_xy) if person_xy else (math.nan, math.nan)))
        while self.history and t - self.history[0][0] > self.config.speed_window:
            self.history.popleft()

    def _speeds_at(self, t, x, y, person_xy):
        """speed_window 초 전 위치와 비교한 (사람이 로봇 쪽으로 다가온 속도, 로봇 속도). 기록이 짧으면 nan."""
        if not self.history or person_xy is None:
            return math.nan, math.nan
        t0, x0, y0, px0, py0 = self.history[0]
        dt = t - t0
        if dt <= 0 or math.isnan(px0):
            return math.nan, math.nan
        robot_speed = math.dist((x0, y0), (x, y)) / dt
        # 사람 속도를 "사람 → 로봇" 방향에 투영. 로봇이 움직인 몫은 빼고 사람 몫만 본다
        px, py = person_xy
        ux, uy = x - px, y - py
        norm = math.hypot(ux, uy)
        if norm < 1e-6:
            return math.nan, robot_speed
        approach = ((px - px0) * ux + (py - py0) * uy) / norm / dt
        return approach, robot_speed

    def _add_time_near_person(self, dt, person_distance):
        if person_distance < self.config.personal_space:
            self.personal_space_time += dt
        if person_distance < self.config.collision_distance:
            self.collision_time += dt

    def _add_stopped_time(self, dt, person_distance):
        self.stopped_time += dt
        if person_distance < self.config.near_person_distance:
            self.stopped_near_person_time += dt

    def add_plan(self, points):
        """전역 경로 한 번 ((x, y), ...). 직전 경로에서 많이 벗어났으면 바뀐 것으로 센다."""
        points = sample_by_spacing(points, self.config.plan_sample_spacing)
        if not points:
            return
        self.plan_updates += 1
        if self.last_plan is not None and \
                plan_deviation(points, self.last_plan) > self.config.plan_change_distance:
            self.plan_changes += 1
        self.last_plan = points

    def add_obstacle(self, dt, name, distance):
        """정답 위치 한 번마다 로봇 외곽에서 가장 가까운 장애물까지 거리 (0이면 닿음)."""
        if distance <= 0.0:
            self.obstacle_contact_time += dt
        if distance < self.min_obstacle_distance:
            self.min_obstacle_distance = distance
            self.nearest_obstacle = name

    def add_localization_error(self, error):
        self.localization_errors.append(error)

    def row(self, status):
        """CSV 한 줄 (열 이름: 값). 정답 위치를 한 번도 못 받았으면 시간·거리는 0."""
        duration = (self.end_time - self.start_time) if self.start_time is not None else 0.0
        start = self.start_xy or (math.nan, math.nan)
        end = self.last_xy or (math.nan, math.nan)
        errors = self.localization_errors
        return {
            'start_time_s': _round(self.start_time or 0.0, 1),
            'status': status,
            'duration_s': _round(duration, 1),
            'path_length_m': _round(self.path_length, 2),
            'mean_speed_mps': _round(self.path_length / duration, 2) if duration > 0 else 0.0,
            'start_x': _round(start[0], 2), 'start_y': _round(start[1], 2),
            'end_x': _round(end[0], 2), 'end_y': _round(end[1], 2),
            'recoveries': self.recoveries,
            'min_person_distance_m': _round(self.min_person_distance, 2),
            'nearest_person': self.nearest_person,
            'personal_space_time_s': _round(self.personal_space_time, 1),
            'person_collision': int(self.min_person_distance < self.config.collision_distance),
            'person_approach_speed_mps': _round(self.person_approach_speed, 2),
            'robot_speed_at_min_mps': _round(self.robot_speed_at_min, 2),
            'person_collision_time_s': _round(self.collision_time, 1),
            'stopped_time_s': _round(self.stopped_time, 1),
            'stopped_near_person_s': _round(self.stopped_near_person_time, 1),
            'stopped_other_s': _round(self.stopped_time - self.stopped_near_person_time, 1),
            'plan_updates': self.plan_updates,
            'plan_changes': self.plan_changes,
            'min_obstacle_distance_m': _round(self.min_obstacle_distance, 2),
            'nearest_obstacle': self.nearest_obstacle,
            'obstacle_contact_time_s': _round(self.obstacle_contact_time, 1),
            'localization_error_mean_m': _round(sum(errors) / len(errors), 3) if errors else '',
            'localization_error_max_m': _round(max(errors), 3) if errors else '',
            'controller_rate_warnings': self.controller_warnings,
            'wheel_slip_events': self.slip_events,
        }


def sample_by_spacing(points, spacing):
    """경로 점 중 앞 점과 spacing 이상 떨어진 것만 남긴다. 첫 점은 항상 남긴다."""
    kept = []
    for point in points:
        if not kept or math.dist(kept[-1], point) >= spacing:
            kept.append(tuple(point))
    return kept


def plan_deviation(points, reference):
    """points의 각 점에서 reference까지 가장 가까운 거리 중 최댓값. 경로가 얼마나 벗어났는지."""
    return max(min(math.dist(p, r) for r in reference) for p in points)


def nearest_in_time(times, values, t):
    """정렬된 times 중 t에 가장 가까운 시각의 값. 비어 있으면 None."""
    if not times:
        return None
    i = bisect.bisect_left(times, t)
    if i == len(times) or (i > 0 and t - times[i - 1] <= times[i] - t):
        i -= 1
    return values[i]


def _round(value, digits):
    if math.isnan(value):
        return ''
    return value if math.isinf(value) else round(value, digits)
