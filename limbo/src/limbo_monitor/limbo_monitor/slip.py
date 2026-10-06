"""바퀴 이동량과 스캔으로 본 실제 이동량을 비교해 바퀴 헛돎을 판단한다 (ROS 의존 없음)."""

from dataclasses import dataclass

OK = 'OK'
UNKNOWN = 'UNKNOWN'   # 스캔으로 판단할 수 없는 구간 (복도 직진, 큰 회전 등)
SUSPECT = 'SUSPECT'
SLIP = 'SLIP'


@dataclass
class SlipConfig:
    # 바퀴가 이만큼은 움직였다고 해야 판단한다. 그보다 작으면 스캔 오차와 구분이 안 된다
    min_wheel_distance: float = 0.15          # m
    # 스캔 이동량이 바퀴 이동량의 이 비율보다 작으면 헛돎 의심
    max_scan_ratio: float = 0.3
    # 앞뒤 방향 단서가 이보다 적으면(긴 복도) 판단을 보류한다
    min_forward_constraint: float = 0.1
    # 크게 회전하는 동안은 ICP가 불안정해서 판단을 보류한다
    max_wheel_rotation: float = 0.35          # rad
    # 의심이 이만큼 연속돼야 헛돎으로 확정한다 (사람이 스캔을 가리는 순간적 오판 방지)
    consecutive_windows: int = 2


class SlipDetector:

    def __init__(self, config):
        self.config = config
        self.suspect_count = 0

    def update(self, wheel_distance, wheel_rotation, motion):
        """한 구간의 판단 결과(OK/UNKNOWN/SUSPECT/SLIP)를 반환한다. motion이 None이면 스캔 실패."""
        cfg = self.config

        if wheel_distance < cfg.min_wheel_distance:
            self.suspect_count = 0
            return OK

        if (motion is None
                or abs(wheel_rotation) > cfg.max_wheel_rotation
                or motion.forward_constraint < cfg.min_forward_constraint):
            return UNKNOWN

        scan_distance = (motion.dx ** 2 + motion.dy ** 2) ** 0.5
        if scan_distance >= cfg.max_scan_ratio * wheel_distance:
            self.suspect_count = 0
            return OK

        self.suspect_count += 1
        return SLIP if self.suspect_count >= cfg.consecutive_windows else SUSPECT
