"""지도(OccupancyGrid)로 벽까지 거리를 잰다. 경로 계획기 비교에서 "경로가 벽에 얼마나 붙는가"를 보기 위해."""

import math

import numpy as np


class WallDistance:
    """점유 격자의 거리 변환. occupied 임계(기본 50) 이상인 칸이 벽."""

    def __init__(self, width, height, resolution, origin_x, origin_y, data, occupied=50):
        grid = np.array(data, dtype=np.int16).reshape(height, width)
        free = (grid >= 0) & (grid < occupied)
        self.resolution = resolution
        self.origin_x, self.origin_y = origin_x, origin_y
        self.distance = _distance_transform(free) * resolution

    def at(self, x, y):
        i = int((x - self.origin_x) / self.resolution)
        j = int((y - self.origin_y) / self.resolution)
        if 0 <= j < self.distance.shape[0] and 0 <= i < self.distance.shape[1]:
            return float(self.distance[j, i])
        return math.nan


def _distance_transform(free):
    """빈 칸마다 가장 가까운 막힌 칸까지 칸 수. OpenCV가 있으면 그걸, 없으면 두 번 훑는 근사(Danielsson)."""
    try:
        import cv2
        return cv2.distanceTransform(free.astype(np.uint8), cv2.DIST_L2, 5)
    except ImportError:
        h, w = free.shape
        d = np.where(free, np.inf, 0.0)
        for j in range(h):
            for i in range(w):
                if d[j, i] == 0:
                    continue
                best = d[j, i]
                if j > 0:
                    best = min(best, d[j - 1, i] + 1)
                if i > 0:
                    best = min(best, d[j, i - 1] + 1)
                d[j, i] = best
        for j in range(h - 1, -1, -1):
            for i in range(w - 1, -1, -1):
                best = d[j, i]
                if j < h - 1:
                    best = min(best, d[j + 1, i] + 1)
                if i < w - 1:
                    best = min(best, d[j, i + 1] + 1)
                d[j, i] = best
        return d
