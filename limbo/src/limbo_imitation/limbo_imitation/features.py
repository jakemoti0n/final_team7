"""
정책(신경망) 입력 벡터를 만드는 순수 함수들. rclpy를 쓰지 않는다.

학습(bag에서 뽑은 값)과 실행(정책 노드)이 이 파일 하나를 같이 써야 같은 입력이 나온다.
한쪽만 고치면 신경망이 본 적 없는 입력을 받게 되므로, 여기를 바꾸면 모델을 다시 학습한다.

한 프레임(FRAME_SIZE = 93칸)의 순서:
- [0, 72)   스캔: 정면(각도 0)부터 반시계로 5°씩 72구간의 최소 거리 / range_max (0~1, 1 = 멀거나 모름)
- [72, 76)  목표: 거리 / max_dist, sin(방향), cos(방향), 정지 경유점이면 1
- [76, 78)  속도: v / v_max, w / w_max (현재 odom 속도)
- [78, 93)  사람: 가까운 순 3명 × [x / max_dist, y / max_dist, vx, vy, 있음 1]
정책 입력(FEATURE_SIZE = 279칸)은 최근 3프레임을 오래된 것부터 이어 붙인 것이다.
"""

import math

import numpy as np

SCAN_BINS = 72
GOAL_SIZE = 4
VELOCITY_SIZE = 2
PEOPLE_K = 3
PERSON_SIZE = 5
PEOPLE_SIZE = PEOPLE_K * PERSON_SIZE
FRAME_SIZE = SCAN_BINS + GOAL_SIZE + VELOCITY_SIZE + PEOPLE_SIZE
STACK_FRAMES = 3
FEATURE_SIZE = FRAME_SIZE * STACK_FRAMES

FULL_TURN = 2.0 * math.pi


def bin_scan(ranges, angle_min, angle_increment, n_bins=SCAN_BINS,
             range_min=0.1, range_max=6.0):
    """360°를 n_bins 구간으로 나눠 구간마다 가장 가까운 거리를 0~1로 낸다.

    구간 0은 정면(각도 0)에서 시작해 반시계로 간다. inf·nan·[range_min, range_max] 밖의 값은
    "모름"이라 가장 먼 값 1.0으로 둔다. range_min보다 가까운 값은 자기 몸·센서 잡음이라 버린다.
    점이 하나도 없는 구간도 1.0이다.
    """
    ranges = np.asarray(ranges, dtype=float)
    angles = angle_min + angle_increment * np.arange(len(ranges))
    bins = (np.mod(angles, FULL_TURN) / (FULL_TURN / n_bins)).astype(int)
    bins = np.minimum(bins, n_bins - 1)  # 부동소수점으로 2π에 딱 걸친 각도
    valid = np.isfinite(ranges) & (ranges >= range_min) & (ranges <= range_max)
    values = np.where(valid, ranges, range_max)
    result = np.full(n_bins, range_max)
    np.minimum.at(result, bins, values)
    return result / range_max


def goal_features(goal_xy_in_base, is_stop_waypoint, max_dist=5.0):
    """로봇 기준 목표 위치 → [거리 비율(최대 1), sin(방향), cos(방향), 정지 경유점 1/0].

    방향을 각도 하나가 아니라 sin·cos로 주는 이유: 각도는 ±180°에서 값이 튀어
    바로 뒤쪽 목표가 신경망에게 정반대 두 값으로 보인다.
    """
    x, y = goal_xy_in_base
    distance = math.hypot(x, y)
    heading = math.atan2(y, x)
    return np.array([
        min(distance, max_dist) / max_dist,
        math.sin(heading),
        math.cos(heading),
        1.0 if is_stop_waypoint else 0.0,
    ])


def velocity_features(v, w, v_max, w_max):
    """현재 속도를 상한으로 나눠 -1~1로 낸다(상한을 넘는 측정값은 1로 자름)."""
    return np.clip(np.array([v / v_max, w / w_max]), -1.0, 1.0)


def people_features(people, k=PEOPLE_K, max_dist=5.0):
    """로봇 기준 사람 목록 [(x, y, vx, vy)] → 가까운 k명 × [x/max, y/max, vx, vy, 1].

    max_dist 밖의 사람은 넣지 않는다(나누면 1을 넘어 가까운 사람과 섞이지 않게).
    사람이 k명보다 적으면 남는 칸은 0이고, 마지막 칸(있음)이 0이라 빈자리임을 안다.
    """
    near = [p for p in people if math.hypot(p[0], p[1]) <= max_dist]
    near.sort(key=lambda p: math.hypot(p[0], p[1]))
    result = np.zeros(k * PERSON_SIZE)
    for i, (x, y, vx, vy) in enumerate(near[:k]):
        start = i * PERSON_SIZE
        result[start:start + PERSON_SIZE] = [x / max_dist, y / max_dist, vx, vy, 1.0]
    return result


def frame_features(scan_bins, goal, velocity, people):
    """한 프레임 = 스캔 + 목표 + 속도 + 사람. 칸 수가 어긋나면 바로 알리도록 확인한다."""
    frame = np.concatenate([scan_bins, goal, velocity, people])
    if frame.shape != (FRAME_SIZE,):
        raise ValueError(f'frame size {frame.shape[0]} != {FRAME_SIZE}')
    return frame


def stack_frames(frames, n=STACK_FRAMES):
    """최근 n프레임을 오래된 것부터 이어 붙인다(frames는 오래된 → 최신 순).

    시작 직후처럼 n개가 안 되면 가장 오래된 프레임을 앞에 반복해 채운다.
    0으로 채우면 "사방이 막힘·정지"처럼 보여 첫 명령이 이상해지기 때문이다.
    """
    if len(frames) == 0:
        raise ValueError('stack_frames needs at least one frame')
    recent = list(frames)[-n:]
    padding = [recent[0]] * (n - len(recent))
    return np.concatenate(padding + recent)


def map_to_base(point_map, robot_pose_map):
    """지도(map) 좌표의 점 (x, y)를 로봇 기준 (앞 +x, 왼쪽 +y)으로 바꾼다. robot_pose_map = (x, y, yaw)."""
    px, py = point_map
    rx, ry, yaw = robot_pose_map
    dx, dy = px - rx, py - ry
    cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
    return (cos_yaw * dx + sin_yaw * dy, -sin_yaw * dx + cos_yaw * dy)
