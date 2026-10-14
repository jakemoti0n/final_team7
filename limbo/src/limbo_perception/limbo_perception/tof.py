"""ToF 근접 센서: 점들 → "코앞에 무언가 있음" (ROS 의존 없음, R5)."""

from dataclasses import dataclass

import numpy as np


@dataclass
class TofConfig:
    stop_distance: float = 0.50        # m, 센서 앞면부터. 근거는 config/tof.yaml
    min_obstacle_height: float = 0.03  # m, base_link z. 바닥 반사를 거른다
    confirm_frames: int = 3            # 연속 프레임이 같아야 판단을 바꾼다 (실물 햇빛 튐 대비)


def nearest_point(points_base, sensor_x, config):
    """base_link 기준 점(N×3) 중 바닥이 아닌 가장 가까운 점과 센서 앞 거리. 없으면 (None, inf)."""
    points = np.asarray(points_base, dtype=float).reshape(-1, 3)
    valid = np.isfinite(points).all(axis=1) & (points[:, 2] >= config.min_obstacle_height)
    points = points[valid]
    if len(points) == 0:
        return None, float('inf')
    ahead = points[:, 0] - sensor_x
    i = int(np.argmin(ahead))
    return points[i], float(ahead[i])


class Debounce:
    """원시 판단이 confirm_frames번 연속 같아야 상태를 바꾼다."""

    def __init__(self, confirm_frames, state=False):
        self.confirm_frames = confirm_frames
        self.state = state
        self.streak = 0

    def update(self, raw):
        if raw == self.state:
            self.streak = 0
            return self.state
        self.streak += 1
        if self.streak >= self.confirm_frames:
            self.state, self.streak = raw, 0
        return self.state


@dataclass
class BlockingConfig:
    memory_sec: float = 5.0      # s, 막히기 직전 이 시간 안에 본 사람만
    min_distance: float = 0.8    # m, 카메라가 사람을 잘 잡는 앞쪽 거리 (1.5 m 안은 거의 못 봄, R4)
    max_distance: float = 3.0
    half_width: float = 1.0
    clear_sec: float = 1.0       # s, ToF가 이만큼 계속 비면 풂
    max_hold_sec: float = 60.0   # s, 상한. 넘으면 풀어서 보통 복구로
    max_pair_gap_sec: float = 1.0  # s, 다가옴을 잴 두 위치의 최대 간격


class PersonBlocking:
    """'방금 다가오던 사람이 지금 코앞을 막고 있다'를 막히기 시작한 순간에 정해 두는 래치 (R5 Q2).

    카메라는 1.5 m 안 사람을 거의 못 보고, ToF는 사람·상자를 못 가른다.
    그래서 ToF가 비었다 → 막힘으로 바뀌는 순간에 직전 memory_sec 안에 다가오던 사람을 봤는지로 정하고,
    ToF가 clear_sec 넘게 비거나 max_hold_sec가 지날 때까지 그대로 둔다.
    시각은 모두 메시지 시각(초)이다.
    """

    def __init__(self, config):
        self.config = config
        self.previous = None     # (t, x)
        self.last_seen = None    # 조건에 맞는 다가오는 사람을 마지막으로 본 시각
        self.blocked = False
        self.last_blocked = None
        self.latched_at = None

    def on_person(self, t, x, y):
        c = self.config
        approaching = (self.previous is not None and
                       0.0 < t - self.previous[0] <= c.max_pair_gap_sec and
                       x < self.previous[1])
        self.previous = (t, x)
        if approaching and c.min_distance <= x <= c.max_distance and abs(y) < c.half_width:
            self.last_seen = t

    def on_tof(self, t, blocked):
        """디바운스한 ToF 판단을 받아 래치 상태를 돌려준다."""
        c = self.config
        if blocked and not self.blocked:
            seen = self.last_seen is not None and 0.0 <= t - self.last_seen <= c.memory_sec
            self.latched_at = t if seen else None
        self.blocked = blocked
        if blocked:
            self.last_blocked = t
        if self.latched_at is not None:
            if not blocked and t - self.last_blocked >= c.clear_sec:
                self.latched_at = None
            elif t - self.latched_at > c.max_hold_sec:
                self.latched_at = None
        return self.latched_at is not None
