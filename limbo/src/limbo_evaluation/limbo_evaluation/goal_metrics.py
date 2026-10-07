"""Nav2 Goal 하나 동안 모은 값으로 평가 지표(CSV 한 줄)를 만든다."""

import bisect
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class MetricsConfig:
    personal_space: float = 0.5   # m, 사람 중심에서 이 거리 안이면 개인 공간 침범으로 센다


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
        self.personal_space_time = 0.0
        self.localization_errors = []
        self.recoveries = 0
        self.controller_warnings = 0
        self.slip_events = 0

    def add_truth(self, sim_time, x, y, person_name, person_distance):
        """정답 위치 한 번. 사람 거리는 같은 시각에 계산한 가장 가까운 사람까지."""
        if self.last_xy is None:
            self.start_time, self.start_xy = sim_time, (x, y)
        else:
            self.path_length += math.dist(self.last_xy, (x, y))
            if person_distance < self.config.personal_space:
                self.personal_space_time += sim_time - self.end_time
        self.last_xy, self.end_time = (x, y), sim_time

        if person_distance < self.min_person_distance:
            self.min_person_distance = person_distance
            self.nearest_person = person_name

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
            'localization_error_mean_m': _round(sum(errors) / len(errors), 3) if errors else '',
            'localization_error_max_m': _round(max(errors), 3) if errors else '',
            'controller_rate_warnings': self.controller_warnings,
            'wheel_slip_events': self.slip_events,
        }


def nearest_in_time(times, values, t):
    """정렬된 times 중 t에 가장 가까운 시각의 값. 비어 있으면 None."""
    if not times:
        return None
    i = bisect.bisect_left(times, t)
    if i == len(times) or (i > 0 and t - times[i - 1] <= times[i] - t):
        i -= 1
    return values[i]


def _round(value, digits):
    return value if math.isinf(value) or math.isnan(value) else round(value, digits)
