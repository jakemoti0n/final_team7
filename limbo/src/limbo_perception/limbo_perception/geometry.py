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


def person_depth(depth_image, x1, y1, x2, y2, config):
    """박스 중앙 영역의 유효 depth 중앙값(m), 없으면 None."""
    if depth_image is None:
        return None

    height, width = depth_image.shape[:2]

    # 가장자리에는 배경이 들어갈 가능성이 높기 때문에 중앙만 사용
    box_width = x2 - x1
    box_height = y2 - y1

    rx1 = int(x1 + box_width * config.roi_margin)
    rx2 = int(x2 - box_width * config.roi_margin)
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

    # 평균보다는 median이 outlier에 강함
    return float(np.median(valid_depth))


def pixel_to_optical_point(u, v, depth, intrinsics):
    """
    픽셀 (u, v)와 depth를 optical frame 3D 점으로 바꾼다.

    ROS optical frame: X = right, Y = down, Z = forward
    """
    z = depth
    x = (u - intrinsics.cx) * z / intrinsics.fx
    y = (v - intrinsics.cy) * z / intrinsics.fy
    return x, y, z
