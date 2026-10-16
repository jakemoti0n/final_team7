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


@dataclass
class BlockingConfig:
    memory_sec: float = 5.0      # s, 막히기 직전 이 시간 안에 본 사람만
    min_distance: float = 0.8    # m, 카메라가 사람을 잘 잡는 앞쪽 거리 (1.5 m 안은 거의 못 봄, R4)
    max_distance: float = 3.0
    half_width: float = 1.0
    clear_sec: float = 1.0       # s, ToF가 이만큼 계속 비면 풂
    max_hold_sec: float = 60.0   # s, 상한. 넘으면 풀어서 보통 복구로
    max_pair_gap_sec: float = 1.0  # s, 다가옴을 잴 두 위치의 최대 간격
    blob_only_hold_sec: float = 5.0  # s, 라이다 덩어리만 근거일 때 상한 (사람인지 확인 못 한 물체 앞 예의 시간)
    camera_match_radius: float = 1.0  # m, 카메라가 본 사람이 덩어리에서 이 안이면 같은 사람으로 봄


class PersonBlocking:
    """'사람이 지금 코앞을 막고 있다'를 ToF가 막힌 동안 정해 두는 래치 (R5 Q2).

    카메라는 1.5 m 안 사람을 거의 못 보고, ToF는 사람·상자를 못 가른다. 그래서 근거를 셋 둔다.
    - approach: ToF가 비었다 → 막힘으로 바뀌는 순간, 직전 memory_sec 안에 다가오던 사람을 봤다.
    - camera: 라이다 앞 사람 덩어리가 있고, 카메라가 memory_sec 안에 그 자리(camera_match_radius 안)에서 사람을 봤다.
    - blob: 라이다 앞 사람 덩어리만 있다(옆·뒤에서 와서 선 사람, 느린 사람). 상자일 수도 있으므로
      blob_only_hold_sec만 기다리고, 그 뒤엔 ToF가 빌 때까지 다시 잡지 않는다(상자 앞 무한 대기 방지).
    ToF가 clear_sec 넘게 비거나 상한(approach·camera는 max_hold_sec)이 지나면 푼다.
    시각은 메시지 시각(초), 위치(world)는 odom처럼 로봇이 움직여도 고정된 좌표계다.
    """

    def __init__(self, config):
        self.config = config
        self.previous = None     # (t, x)
        self.last_seen = None    # 조건에 맞는 다가오는 사람을 마지막으로 본 시각
        self.sightings = []      # 카메라가 본 사람 (t, world x, world y), memory_sec 안만
        self.blocked = False
        self.last_blocked = None
        self.latched_at = None
        self.reason = None       # 'approach' | 'camera' | 'blob'
        self.gave_up = False     # 이번 막힘에서 상한으로 풀었음 → ToF가 빌 때까지 다시 안 잡음
        self.release_reason = None

    def on_person(self, t, x, y):
        c = self.config
        approaching = (self.previous is not None and
                       0.0 < t - self.previous[0] <= c.max_pair_gap_sec and
                       x < self.previous[1])
        self.previous = (t, x)
        if approaching and c.min_distance <= x <= c.max_distance and abs(y) < c.half_width:
            self.last_seen = t

    def on_camera_people(self, t, positions):
        """카메라가 본 사람들의 world 위치 [(x, y), ...] (서 있는 사람 포함)."""
        self.sightings = [s for s in self.sightings if t - s[0] <= self.config.memory_sec]
        self.sightings.extend((t, x, y) for x, y in positions)

    def camera_saw(self, t, blob_world):
        c = self.config
        bx, by = blob_world
        return any(0.0 <= t - st <= c.memory_sec and
                   (sx - bx) ** 2 + (sy - by) ** 2 <= c.camera_match_radius ** 2
                   for st, sx, sy in self.sightings)

    def on_tof(self, t, blocked, blob_world=None):
        """디바운스한 ToF 판단과 앞 사람 덩어리(world 중심, 없으면 None)를 받아 래치 상태를 돌려준다."""
        c = self.config
        self.release_reason = None
        if blocked and not self.blocked:
            seen = self.last_seen is not None and 0.0 <= t - self.last_seen <= c.memory_sec
            if seen:
                self.latched_at, self.reason = t, 'approach'
        self.blocked = blocked
        if blocked:
            self.last_blocked = t
        if blocked and blob_world is not None and not self.gave_up:
            if self.latched_at is None:
                self.latched_at, self.reason = t, 'blob'
            if self.reason == 'blob' and self.camera_saw(t, blob_world):
                self.reason = 'camera'   # 덩어리가 사람으로 확인됨 → 긴 상한
        if self.latched_at is not None:
            limit = c.blob_only_hold_sec if self.reason == 'blob' else c.max_hold_sec
            if not blocked and t - self.last_blocked >= c.clear_sec:
                self.latched_at, self.release_reason = None, 'tof clear'
            elif t - self.latched_at > limit:
                self.latched_at, self.gave_up = None, True
                self.release_reason = f'{self.reason} hold limit {limit:.0f} s'
        if not blocked and self.last_blocked is not None and t - self.last_blocked >= c.clear_sec:
            self.gave_up = False
        if self.latched_at is None:
            self.reason = None
        return self.latched_at is not None


@dataclass
class ApproachConfig:
    cpa_radius: float = 0.6      # m, 사람 속도 방향 직선이 로봇에서 이 안을 지나면 진로 위로 다가옴 (전제 2-1)
    max_range: float = 3.0       # m, 카메라가 사람을 믿을 만하게 보는 거리
    min_speed: float = 0.2       # m/s, 이보다 느리면 방향을 믿지 않음 (서 있는 사람은 다가오는 사람이 아님)
    seen_hold_sec: float = 1.0   # s, 다가오는 사람을 마지막으로 본 뒤 이만큼은 다가오는 중으로 봄 (검출 끊김)
    release_sec: float = 1.0     # s, 다가옴도 ToF도 앞 사람 덩어리도 없으면 이만큼 뒤 다시 출발
    max_hold_sec: float = 60.0   # s, 상한. 넘으면 풀어서 보통 주행·복구로
    blob_only_hold_sec: float = 15.0  # s, 유지 근거가 라이다 덩어리뿐인 채로 이만큼 지나면 풂


@dataclass
class BlobConfig:
    """라이다 앞 '사람 덩어리' 판정. 폭은 사람 몸통 치수, 띠는 로봇 치수에서 온다(로봇마다 노드가 계산)."""

    half_width: float = 0.55      # m, 로봇 중심선 좌우 = 로봇 반폭 + 사람 반경 (덩어리 중심 기준)
    max_range: float = 1.5        # m, 범퍼 앞부터. ToF(0.5 m) 밖에 선 손님까지
    neighbor_gap: float = 0.15    # m, 각도 순 이웃 점 간격이 이 안이면 같은 덩어리
    min_width: float = 0.15       # m, 사람 몸통 최소 폭 (기둥·잡음 제외)
    max_width: float = 0.60       # m, 사람 몸통 최대 폭 (벽·큰 상자 제외)


def filter_map_points(points_map_xy, grid, margin_cells=2):
    """
    지도 좌표 점(N×2) 중 지도 점유 칸에서 margin_cells칸 밖인 것만 True인 마스크.

    벽 점을 버린다(사람이 떠난 뒤 복도 벽 모서리가 앞 띠에 걸려 정지가 안 풀렸다).
    지도 밖·미지 칸의 점은 남긴다(지도에 없는 것이 사람·상자다).
    """
    points = np.asarray(points_map_xy, dtype=float).reshape(-1, 2)
    near = grid.near_occupied(margin_cells)
    col, row = grid.cells(points)
    inside = (col >= 0) & (col < grid.width) & (row >= 0) & (row < grid.height)
    keep = np.ones(len(points), dtype=bool)
    keep[inside] = ~near[row[inside], col[inside]]
    return keep


class MapGrid:
    """OccupancyGrid 값(행=y)과 원점·해상도. 점유(>= occupied) 칸을 margin칸 넓힌 마스크를 캐시한다."""

    def __init__(self, data, width, height, resolution, origin_x, origin_y, origin_yaw=0.0,
                 occupied=50):
        self.width, self.height, self.resolution = width, height, resolution
        self.origin = (origin_x, origin_y, origin_yaw)
        self.occupied = np.asarray(data, dtype=np.int16).reshape(height, width) >= occupied
        self._near = {}

    def cells(self, points_xy):
        ox, oy, yaw = self.origin
        dx, dy = points_xy[:, 0] - ox, points_xy[:, 1] - oy
        c, s = np.cos(yaw), np.sin(yaw)
        gx, gy = c * dx + s * dy, -s * dx + c * dy
        return (np.floor(gx / self.resolution).astype(int),
                np.floor(gy / self.resolution).astype(int))

    def near_occupied(self, margin_cells):
        if margin_cells not in self._near:
            m = int(margin_cells)
            near = self.occupied.copy()
            padded = np.pad(self.occupied, m)
            for di in range(-m, m + 1):
                for dj in range(-m, m + 1):
                    if di * di + dj * dj <= m * m:
                        near |= padded[m + di:m + di + self.height, m + dj:m + dj + self.width]
            self._near[margin_cells] = near
        return self._near[margin_cells]


def person_blob_ahead(points_base, origin_x, config):
    """
    base_link 평면 점(N×2 이상)에서 범퍼(origin_x) 앞 띠 안의 사람 크기 덩어리를 찾는다.

    점을 각도 순으로 놓고 이웃 간격 neighbor_gap 안이면 한 덩어리로 묶는다. 띠로 자르기 전에 묶어서
    띠 밖까지 이어진 벽·큰 상자는 전체 폭으로 재어 버린다. 덩어리 중심이 띠 안이고 폭이
    min_width~max_width면 사람 후보. 반환: (있음, 중심 x, 중심 y, 폭), 여럿이면 가장 가까운 것.
    """
    none = (False, None, None, None)
    if len(points_base) == 0:
        return none
    points = np.asarray(points_base, dtype=float).reshape(len(points_base), -1)[:, :2]
    points = points[np.isfinite(points).all(axis=1)]
    if len(points) < 2:
        return none
    points = points[np.argsort(np.arctan2(points[:, 1], points[:, 0]), kind='stable')]
    gaps = np.linalg.norm(np.diff(points, axis=0), axis=1)
    breaks = np.flatnonzero(gaps > config.neighbor_gap) + 1
    best = none
    for blob in np.split(points, breaks):
        if len(blob) < 2:
            continue
        width = float(np.linalg.norm(blob[-1] - blob[0]))
        cx, cy = blob.mean(axis=0)
        ahead = cx - origin_x
        if (config.min_width <= width <= config.max_width and 0.0 < ahead <= config.max_range and
                abs(cy) <= config.half_width and (best[0] is False or cx < best[1])):
            best = (True, float(cx), float(cy), width)
    return best


def closest_approach(px, py, vx, vy):
    """로봇(원점)에 대한 사람 위치·속도로 (최근접까지 시간 s, 최근접 거리 m). 멀어지면 시간 <= 0."""
    speed2 = vx * vx + vy * vy
    if speed2 == 0.0:
        return 0.0, (px * px + py * py) ** 0.5
    t = -(px * vx + py * vy) / speed2
    cx, cy = px + vx * t, py + vy * t
    return t, (cx * cx + cy * cy) ** 0.5


class ApproachWatch:
    """다가오는 사람(손님)이면 그 자리에 멈춰 기다린다 (전제 2-1, R5 Q4).

    사람 속도 방향 직선이 로봇에서 cpa_radius 안을 지나면 정지를 시작한다.
    카메라는 1.5 m 안 사람을 거의 못 보므로(R4), 정지한 뒤에는 ToF가 코앞을 막힘으로 보거나
    라이다 앞 띠에 사람 덩어리가 있는 동안(손님이 와서 섬) 정지를 유지한다(Q5·Q9).
    유지 근거(basis: seen·tof·blob)가 덩어리뿐인 채로 blob_only_hold_sec가 지나면 푼다(지도에 없는
    물체가 띠에 남아 사람이 떠난 뒤에도 안 풀리는 것을 막음). 카메라·ToF가 근거면 max_hold_sec까지.
    정지는 다가옴으로만 시작하므로 상자 앞에서는 서지 않는다. 근거가 release_sec 동안 없으면 다시 출발한다.
    시각은 모두 메시지 시각(초)이다.
    """

    def __init__(self, config):
        self.config = config
        self.last_approach = None
        self.stopped_at = None
        self.last_reason = None
        self.basis = None          # 지금 정지를 유지하는 근거
        self.basis_since = None
        self.release_reason = None

    def approaching(self, rel_x, rel_y, vx, vy):
        c = self.config
        too_slow = (vx * vx + vy * vy) ** 0.5 < c.min_speed
        if too_slow or (rel_x * rel_x + rel_y * rel_y) ** 0.5 > c.max_range:
            return False
        t, distance = closest_approach(rel_x, rel_y, vx, vy)
        return t > 0.0 and distance < c.cpa_radius

    def on_people(self, t, people):
        """people: 로봇 기준 (상대 x, 상대 y, 속도 x, 속도 y) 목록 (같은 좌표계 축)."""
        if any(self.approaching(*person) for person in people):
            self.last_approach = t

    def _set_basis(self, t, basis):
        if basis != self.basis:
            self.basis, self.basis_since = basis, t

    def on_tick(self, t, tof_blocked, blob_ahead=False):
        c = self.config
        self.release_reason = None
        seen = self.last_approach is not None and 0.0 <= t - self.last_approach <= c.seen_hold_sec
        if self.stopped_at is None:
            if seen:
                self.stopped_at = self.last_reason = t
                self._set_basis(t, 'seen')
            return self.stopped_at is not None
        basis = 'seen' if seen else 'tof' if tof_blocked else 'blob' if blob_ahead else None
        if basis is not None:
            self.last_reason = t
            self._set_basis(t, basis)
        if t - self.last_reason >= c.release_sec:
            self.release_reason = 'clear'
        elif t - self.stopped_at > c.max_hold_sec:
            self.release_reason = f'hold limit {c.max_hold_sec:.0f} s'
        elif self.basis == 'blob' and t - self.basis_since > c.blob_only_hold_sec:
            self.release_reason = f'blob-only hold limit {c.blob_only_hold_sec:.0f} s'
        if self.release_reason is not None:
            self.stopped_at = None
            self.last_approach = None   # 상한으로 풀었을 때 바로 다시 잡지 않게
            self._set_basis(t, None)
        return self.stopped_at is not None
