"""
월드 SDF의 고정 상자 장애물(이름이 obstacle_로 시작)과 로봇 외곽 사이의 거리를 잰다.

지도에 없는 낮은 장애물을 센서가 놓쳐 부딪히는지 보려는 용도다.
상자는 회전 없이 놓였다고 본다 (gen_world.py가 그렇게 만든다).
"""

from dataclasses import dataclass
import math
import re

MODEL_PATTERN = re.compile(r'<model name="(obstacle_[^"]*)">(.*?)</model>', re.S)
POSE_PATTERN = re.compile(r'<pose>([^<]+)</pose>')
SIZE_PATTERN = re.compile(r'<box>\s*<size>([^<]+)</size>')
# 로봇 외곽 한 변을 몇 점으로 나눠 잴지. 0.45m 변이면 약 6cm 간격
POINTS_PER_SIDE = 8


@dataclass(frozen=True)
class Box:
    name: str
    x: float
    y: float
    half_x: float
    half_y: float


def parse_boxes(sdf_text):
    boxes = []
    for name, body in MODEL_PATTERN.findall(sdf_text):
        pose, size = POSE_PATTERN.search(body), SIZE_PATTERN.search(body)
        if pose is None or size is None:
            continue
        x, y = map(float, pose.group(1).split()[:2])
        size_x, size_y = map(float, size.group(1).split()[:2])
        boxes.append(Box(name, x, y, size_x / 2, size_y / 2))
    return boxes


def footprint_points(x, y, yaw, half_size):
    """정사각형 로봇 외곽 위의 점들 (map 좌표)."""
    c, s = math.cos(yaw), math.sin(yaw)
    corners = [(half_size, half_size), (-half_size, half_size),
               (-half_size, -half_size), (half_size, -half_size)]
    points = []
    for (ax, ay), (bx, by) in zip(corners, corners[1:] + corners[:1]):
        for k in range(POINTS_PER_SIDE):
            a = k / POINTS_PER_SIDE
            px, py = ax + a * (bx - ax), ay + a * (by - ay)
            points.append((x + c * px - s * py, y + s * px + c * py))
    return points


def _point_to_box(px, py, box):
    """상자 밖이면 가장 가까운 면까지 거리, 안이면 0."""
    dx = max(abs(px - box.x) - box.half_x, 0.0)
    dy = max(abs(py - box.y) - box.half_y, 0.0)
    return math.hypot(dx, dy)


def nearest_box(boxes, x, y, yaw, half_size):
    """로봇 외곽에서 가장 가까운 상자의 (이름, 거리). 닿거나 겹치면 0. 상자가 없으면 ('', inf)."""
    best_name, best_distance = '', math.inf
    points = footprint_points(x, y, yaw, half_size)
    for box in boxes:
        # 상자 모서리가 로봇 안쪽으로 들어온 경우도 닿은 것으로 본다
        if _box_corner_inside(box, x, y, yaw, half_size):
            distance = 0.0
        else:
            distance = min(_point_to_box(px, py, box) for px, py in points)
        if distance < best_distance:
            best_name, best_distance = box.name, distance
    return best_name, best_distance


def _box_corner_inside(box, x, y, yaw, half_size):
    c, s = math.cos(yaw), math.sin(yaw)
    for sx in (-1, 1):
        for sy in (-1, 1):
            dx, dy = box.x + sx * box.half_x - x, box.y + sy * box.half_y - y
            # 로봇 좌표계로 돌려서 정사각형 안인지 본다
            local_x, local_y = c * dx + s * dy, -s * dx + c * dy
            if abs(local_x) <= half_size and abs(local_y) <= half_size:
                return True
    return False
