"""RGB-D 기하 계산: bounding box depth, pixel → 3D (ROS 의존 없음)."""

from dataclasses import dataclass

import numpy as np


@dataclass
class CameraIntrinsics:
    fx: float
    fy: float
    cx: float
    cy: float

    @classmethod
    def from_k(cls, k):
        """K 행렬(CameraInfo.k, [fx 0 cx; 0 fy cy; 0 0 1])로 만든다."""
        return cls(fx=k[0], fy=k[4], cx=k[2], cy=k[5])


@dataclass
class DepthConfig:
    # Bounding box 가장자리 비율 (각 변에서 잘라냄 → 중앙 40%만 사용)
    roi_margin: float = 0.30
    min_depth: float = 0.1
    max_depth: float = 5.0
    # 박스 안에서 사람은 보통 배경보다 앞에 있으므로 가까운 쪽 값을 쓴다.
    # 중앙값(50)을 쓰면 다리만 보이는 박스에서 다리 사이로 보이는 뒤쪽 벽까지 거리를 잰다
    percentile: float = 25.0
    # leg 박스(하반신 모델 클래스 1)는 두 다리를 감싸면 가운데가 다리 사이 틈(배경)이다.
    # 그래서 가로는 거의 전부(양옆 다리 포함) 쓰고, 더 가까운 쪽 값을 쓴다.
    # 다리 하나짜리 박스는 다리가 박스 대부분이라 같은 방법으로도 다리 거리가 나온다
    leg_roi_margin_x: float = 0.05
    leg_percentile: float = 10.0


def person_depth(depth_image, x1, y1, x2, y2, config, leg=False):
    """
    박스 중앙 영역의 유효 depth 중 가까운 쪽 값(m, percentile), 없으면 None.

    leg=True(다리 박스)면 가로 여백을 줄여 양옆 다리 자리까지 넣고
    더 낮은 percentile을 써서, 다리 사이로 보이는 배경을 잡지 않는다.
    """
    if depth_image is None:
        return None

    height, width = depth_image.shape[:2]

    # 가장자리에는 배경이 들어갈 가능성이 높기 때문에 중앙만 사용
    box_width = x2 - x1
    box_height = y2 - y1

    margin_x = config.leg_roi_margin_x if leg else config.roi_margin
    percentile = config.leg_percentile if leg else config.percentile
    rx1 = int(x1 + box_width * margin_x)
    rx2 = int(x2 - box_width * margin_x)
    ry1 = int(y1 + box_height * config.roi_margin)
    ry2 = int(y2 - box_height * config.roi_margin)

    rx1 = max(0, min(rx1, width - 1))
    rx2 = max(0, min(rx2, width))
    ry1 = max(0, min(ry1, height - 1))
    ry2 = max(0, min(ry2, height))

    if rx2 <= rx1 or ry2 <= ry1:
        return None

    depth_roi = depth_image[ry1:ry2, rx1:rx2]

    valid_depth = depth_roi[
        np.isfinite(depth_roi)
        & (depth_roi > config.min_depth)
        & (depth_roi < config.max_depth)
    ]

    if len(valid_depth) == 0:
        return None

    return float(np.percentile(valid_depth, percentile))


def _area(box):
    x1, y1, x2, y2 = box
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _intersection(a, b):
    return _area((max(a[0], b[0]), max(a[1], b[1]),
                  min(a[2], b[2]), min(a[3], b[3])))


def merge_leg_boxes(boxes, classes, leg_class, leg_inside_ratio, leg_iou):
    """
    같은 사람에 붙은 박스를 하나로 줄이고 남길 박스 번호(입력 순서)를 반환한다.

    하반신 모델은 한 사람에 person 박스와 leg 박스를 같이 낼 때가 많다.
    추적기는 한 사람에 박스 하나만 붙이므로, 남는 박스가 새 사람이 되지 않게 한다.
    - leg 면적의 leg_inside_ratio 이상이 어떤 person 박스 안이면 leg를 버린다
    - person 없이 남은 leg는 사람으로 쓴다. leg끼리 IoU가 leg_iou 이상이면 큰 것만 남긴다
    """
    people = [b for b, c in zip(boxes, classes) if c != leg_class]
    legs = sorted((i for i, c in enumerate(classes) if c == leg_class),
                  key=lambda i: _area(boxes[i]), reverse=True)

    kept_legs = []
    for i in legs:
        leg = boxes[i]
        leg_area = _area(leg)
        if leg_area <= 0:
            continue
        if any(_intersection(leg, p) >= leg_inside_ratio * leg_area
               for p in people):
            continue
        if any(_iou(leg, boxes[k]) >= leg_iou for k in kept_legs):
            continue
        kept_legs.append(i)

    kept = set(kept_legs)
    return [i for i, c in enumerate(classes) if c != leg_class or i in kept]


def _iou(a, b):
    inter = _intersection(a, b)
    union = _area(a) + _area(b) - inter
    return inter / union if union > 0 else 0.0


def pixel_to_optical_point(u, v, depth, intrinsics):
    """
    픽셀 (u, v)와 depth를 optical frame 3D 점으로 바꾼다.

    ROS optical frame: X = right, Y = down, Z = forward
    """
    z = depth
    x = (u - intrinsics.cx) * z / intrinsics.fx
    y = (v - intrinsics.cy) * z / intrinsics.fy
    return x, y, z
