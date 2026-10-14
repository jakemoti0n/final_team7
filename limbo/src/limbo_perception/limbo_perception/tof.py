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


@dataclass
class ApproachConfig:
    cpa_radius: float = 0.6      # m, 사람 속도 방향 직선이 로봇에서 이 안을 지나면 진로 위로 다가옴 (전제 2-1)
    max_range: float = 3.0       # m, 카메라가 사람을 믿을 만하게 보는 거리
    min_speed: float = 0.2       # m/s, 이보다 느리면 방향을 믿지 않음 (서 있는 사람은 다가오는 사람이 아님)
    seen_hold_sec: float = 1.0   # s, 다가오는 사람을 마지막으로 본 뒤 이만큼은 다가오는 중으로 봄 (검출 끊김)
    release_sec: float = 1.0     # s, 다가옴도 ToF도 앞 섹터 점유도 없으면 이만큼 뒤 다시 출발
    max_hold_sec: float = 60.0   # s, 상한. 넘으면 풀어서 보통 주행·복구로


@dataclass
class SectorConfig:
    # 진로 폭 띠 (Q9): 부채꼴(±30°)은 복도에서 사람이 떠난 뒤 벽 모서리를 잡아 정지가 안 풀렸다
    half_width: float = 0.55      # m, 로봇 중심선 좌우. 로봇 반폭 0.3 + 사람 반경 0.25 = 진로를 막는 사람
    max_range: float = 1.5        # m, 범퍼 앞부터. ToF(0.5 m) 밖에 선 손님까지
    min_points: int = 2           # 이만큼 칸이 차야 점유 (한 칸짜리 잡음 무시)


def sector_occupied(points_base, origin_x, config):
    """base_link 기준 평면 점(N×2 이상)이 범퍼 앞(origin_x) 0~max_range, 좌우 half_width 띠에 min_points 이상인가."""
    if len(points_base) == 0:
        return False
    points = np.asarray(points_base, dtype=float).reshape(len(points_base), -1)[:, :2]
    points = points[np.isfinite(points).all(axis=1)]
    dx, dy = points[:, 0] - origin_x, points[:, 1]
    inside = (dx > 0.0) & (dx <= config.max_range) & (np.abs(dy) <= config.half_width)
    return int(inside.sum()) >= config.min_points


def closest_approach(px, py, vx, vy):
    """로봇(원점)에 대한 사람 위치·속도로 (최근접까지 시간 s, 최근접 거리 m). 멀어지면 시간 <= 0."""
    speed2 = vx * vx + vy * vy
    if speed2 == 0.0:
        return 0.0, (px * px + py * py) ** 0.5
    t = -(px * vx + py * vy) / speed2
    cx, cy = px + vx * t, py + vy * t
    return t, (cx * cx + cy * cy) ** 0.5


class ApproachWatch:
    """다가오는 사람(손님)이면 그 자리에 멈춰 기다린다 (전제 2-1, R5 Q4).

    사람 속도 방향 직선이 로봇에서 cpa_radius 안을 지나면 정지를 시작한다.
    카메라는 1.5 m 안 사람을 거의 못 보므로(R4), 정지한 뒤에는 ToF가 코앞을 막힘으로 보거나
    라이다 앞 진로 폭 띠(범퍼 앞 1.5 m, 좌우 0.55 m)가 차 있는 동안(손님이 와서 섬) 정지를 유지한다(Q5·Q9).
    정지는 다가옴으로만 시작하므로 상자 앞에서는 서지 않는다. 셋 다 release_sec 동안 없으면 다시 출발한다.
    시각은 모두 메시지 시각(초)이다.
    """

    def __init__(self, config):
        self.config = config
        self.last_approach = None
        self.stopped_at = None
        self.last_reason = None

    def approaching(self, rel_x, rel_y, vx, vy):
        c = self.config
        too_slow = (vx * vx + vy * vy) ** 0.5 < c.min_speed
        if too_slow or (rel_x * rel_x + rel_y * rel_y) ** 0.5 > c.max_range:
            return False
        t, distance = closest_approach(rel_x, rel_y, vx, vy)
        return t > 0.0 and distance < c.cpa_radius

    def on_people(self, t, people):
        """people: 로봇 기준 (상대 x, 상대 y, 속도 x, 속도 y) 목록 (같은 좌표계 축)."""
        if any(self.approaching(*person) for person in people):
            self.last_approach = t

    def on_tick(self, t, tof_blocked, front_occupied=False):
        c = self.config
        seen = self.last_approach is not None and 0.0 <= t - self.last_approach <= c.seen_hold_sec
        if self.stopped_at is None:
            if seen:
                self.stopped_at = self.last_reason = t
            return self.stopped_at is not None
        if seen or tof_blocked or front_occupied:
            self.last_reason = t
        if t - self.last_reason >= c.release_sec or t - self.stopped_at > c.max_hold_sec:
            self.stopped_at = None
            self.last_approach = None   # 상한으로 풀었을 때 바로 다시 잡지 않게
        return self.stopped_at is not None
