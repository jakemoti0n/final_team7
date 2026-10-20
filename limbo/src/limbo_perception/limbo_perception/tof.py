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
