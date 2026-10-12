"""
최근 바퀴 odom 위치를 보관하고 원하는 시각의 위치를 보간해 꺼낸다 (ROS 의존 없음).

스캔은 포인트클라우드 변환을 거쳐 늦게 도착하므로, 도착 순간의 최신 odom이 아니라
스캔을 찍은 시각의 odom과 비교해야 멈췄다 출발하는 순간에 헛돎으로 잘못 보지 않는다.
"""

from collections import deque
import math

# 이만큼 지난 기록은 버린다 (스캔 지연보다 넉넉하게)
KEEP_SEC = 2.0
# 가장 최근 odom보다 이 정도까지 늦은 시각은 최근 값으로 본다 (odom 50Hz → 0.02초 간격)
MAX_LEAD_SEC = 0.05


class PoseHistory:

    def __init__(self):
        self.poses = deque()   # (시각, x, y, yaw), 시각 순

    def add(self, stamp, x, y, yaw):
        if self.poses and stamp <= self.poses[-1][0]:
            return
        self.poses.append((stamp, x, y, yaw))
        while stamp - self.poses[0][0] > KEEP_SEC:
            self.poses.popleft()

    def at(self, stamp):
        """주어진 시각의 (x, y, yaw). 기록 범위를 벗어나면 None."""
        if not self.poses or stamp < self.poses[0][0]:
            return None
        newest = self.poses[-1]
        if stamp >= newest[0]:
            return newest[1:] if stamp - newest[0] <= MAX_LEAD_SEC else None
        for (t0, x0, y0, yaw0), (t1, x1, y1, yaw1) in zip(self.poses, list(self.poses)[1:]):
            if t0 <= stamp <= t1:
                a = (stamp - t0) / (t1 - t0)
                return (x0 + a * (x1 - x0),
                        y0 + a * (y1 - y0),
                        yaw0 + a * math.remainder(yaw1 - yaw0, 2 * math.pi))
        return None
