"""두 2D 스캔 사이에 센서가 실제로 얼마나 움직였는지 점-직선 ICP로 추정한다 (ROS 의존 없음)."""

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

# 법선을 구할 때 쓰는 이웃 점 수. 벽처럼 곧은 면의 방향을 안정적으로 얻을 만큼만 쓴다
NORMAL_NEIGHBORS = 5
CONVERGED_STEP = 1e-5


@dataclass
class IcpConfig:
    max_iterations: int = 20
    max_correspondence: float = 0.3   # m, 이보다 먼 점끼리는 짝짓지 않는다
    min_points: int = 30


@dataclass
class MotionEstimate:
    dx: float          # m, 이전 센서 기준 앞쪽 이동
    dy: float          # m, 이전 센서 기준 왼쪽 이동
    dyaw: float        # rad
    # 0~1. 벽 법선이 앞뒤 방향을 얼마나 가리키는지. 긴 복도처럼 양옆 벽만 보이면 0에 가깝고,
    # 그때는 앞뒤 이동을 스캔으로 알 수 없다
    forward_constraint: float
    inlier_ratio: float


def scan_to_points(ranges, angle_min, angle_increment, range_min, range_max):
    r = np.asarray(ranges, dtype=float)
    angles = angle_min + np.arange(len(r)) * angle_increment
    valid = np.isfinite(r) & (r > range_min) & (r < range_max)
    return np.column_stack((r[valid] * np.cos(angles[valid]),
                            r[valid] * np.sin(angles[valid])))


def estimate_normals(points):
    """각 점 주변 이웃의 주성분으로 면의 법선(단위벡터)을 구한다."""
    _, idx = cKDTree(points).query(points, k=NORMAL_NEIGHBORS)
    neighbors = points[idx]
    centered = neighbors - neighbors.mean(axis=1, keepdims=True)
    cov = np.einsum('nki,nkj->nij', centered, centered)
    _, vectors = np.linalg.eigh(cov)
    # 고유값이 가장 작은 방향 = 면에 수직인 방향
    return vectors[:, :, 0]


def estimate_motion(prev_points, cur_points, config):
    """현재 스캔을 이전 스캔에 맞추는 변환(= 그 사이 센서 이동)을 구한다. 점이 부족하면 None."""
    if len(prev_points) < config.min_points or len(cur_points) < config.min_points:
        return None

    tree = cKDTree(prev_points)
    normals = estimate_normals(prev_points)
    tx = ty = yaw = 0.0
    inliers = np.zeros(len(cur_points), dtype=bool)
    matched_normals = np.empty((0, 2))

    for _ in range(config.max_iterations):
        c, s = np.cos(yaw), np.sin(yaw)
        moved = cur_points @ np.array([[c, s], [-s, c]]) + (tx, ty)
        dist, idx = tree.query(moved, distance_upper_bound=config.max_correspondence)
        inliers = np.isfinite(dist)
        if inliers.sum() < config.min_points:
            return None

        p = moved[inliers]
        q = prev_points[idx[inliers]]
        n = normals[idx[inliers]]
        residual = np.sum(n * (p - q), axis=1)
        # 점-직선 거리를 (tx, ty, yaw)로 미분한 값. 회전은 현재 위치 기준 작은 각도로 근사한다
        jacobian = np.column_stack((
            n[:, 0], n[:, 1],
            -n[:, 0] * (p[:, 1] - ty) + n[:, 1] * (p[:, 0] - tx)))
        step, *_ = np.linalg.lstsq(jacobian, -residual, rcond=None)
        tx, ty, yaw = tx + step[0], ty + step[1], yaw + step[2]
        matched_normals = n
        if np.linalg.norm(step) < CONVERGED_STEP:
            break

    return MotionEstimate(
        dx=float(tx), dy=float(ty), dyaw=float(yaw),
        forward_constraint=float(np.mean(matched_normals[:, 0] ** 2)),
        inlier_ratio=float(inliers.mean()),
    )
