"""사람 움직임 분류와 미래 경로 예측 (ROS 의존 없음)."""

from dataclasses import dataclass, field

import numpy as np

# 사람과 로봇이 거의 겹치면 방향을 정의할 수 없다
MIN_DIRECTION_DISTANCE = 0.001


@dataclass
class MotionConfig:
    # 이 속도 이하면 정지 상태로 간주
    stationary_speed_threshold: float = 0.05
    # Limbo 방향 속도 성분이 이 이상이면 접근/이탈로 판단
    approach_speed_threshold: float = 0.03


@dataclass
class PredictionConfig:
    horizon: float = 2.0
    dt: float = 0.25


@dataclass
class PredictedPerson:
    """human_layer와 RViz marker로 내보낼 한 사람의 예측 결과 (odom 기준)."""

    track_id: int
    current_x: float
    current_y: float
    vx: float
    vy: float
    # (future_x, future_y, time_offset)
    points: list = field(default_factory=list)


def classify_person_motion(person_x, person_y, vx, vy, robot_x, robot_y, config):
    """사람 속도를 Limbo 방향으로 투영해 (상태, 접근 속도)를 반환한다."""
    speed = np.sqrt(vx * vx + vy * vy)

    if speed < config.stationary_speed_threshold:
        return 'STATIONARY', 0.0

    dx = robot_x - person_x
    dy = robot_y - person_y
    distance = np.sqrt(dx * dx + dy * dy)

    if distance < MIN_DIRECTION_DISTANCE:
        return 'STATIONARY', 0.0

    # 사람 속도를 Limbo 방향 단위벡터에 투영한다
    approach_speed = vx * (dx / distance) + vy * (dy / distance)

    if approach_speed > config.approach_speed_threshold:
        state = 'APPROACHING'
    elif approach_speed < -config.approach_speed_threshold:
        state = 'LEAVING'
    else:
        state = 'PASSING'

    return state, approach_speed


def predict_trajectory(x, y, vx, vy, config):
    """등속 모델로 dt 간격, horizon까지의 미래 위치 목록을 만든다."""
    predicted_points = []

    t = config.dt
    while t <= config.horizon:
        predicted_points.append((x + vx * t, y + vy * t, t))
        t += config.dt

    return predicted_points
