"""기하 계산: RGB-D bounding box depth·pixel → 3D, 라이다 점 덩어리, 다가옴 최근접점 (ROS 의존 없음)."""

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
    # depth는 몸의 카메라 쪽 겉면까지라 사람 중심으로 밀 거리(m). 박스 종류마다 재는 자리가 달라 값도 다르다
    # leg 박스: 다리 앞면 → 몸 중심 / person 박스: 몸통 가운데 영역 → 몸 두께 절반
    leg_radius: float = 0.25
    person_box_radius: float = 0.12


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


def merge_leg_boxes(boxes, classes, leg_class, leg_inside_ratio, leg_iou,
                    pair_gap_ratio=1.5, pair_vertical_overlap=0.5):
    """
    같은 사람에 붙은 박스를 하나로 줄이고 (원래 번호, 박스) 목록을 반환한다.

    하반신 모델은 한 사람에 person 박스와 leg 박스를 같이 낼 때가 많다.
    추적기는 한 사람에 박스 하나만 붙이므로, 남는 박스가 새 사람이 되지 않게 한다.
    - leg 면적의 leg_inside_ratio 이상이 어떤 person 박스 안이면 leg를 버린다
    - person 없이 남은 leg는 사람으로 쓴다. leg끼리 IoU가 leg_iou 이상이면 큰 것만 남긴다
    - 다리 하나씩 따로 잡힌 leg 둘(가로로 나란함)은 둘을 감싸는 박스 하나로 합친다.
      나란함 = 박스 중심 가로 간격이 두 박스 폭 합의 pair_gap_ratio배 이내이고
      세로로 겹친 길이가 짧은 쪽 높이의 pair_vertical_overlap 이상.
      합친 박스의 번호는 큰 leg의 번호(그 leg의 추적 ID를 쓴다)
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

    # 큰 leg부터, 나란한 leg 중 가로로 가장 가까운 것과 짝짓는다
    leg_boxes = {}
    paired = set()
    for i in kept_legs:
        if i in paired:
            continue
        partners = [k for k in kept_legs
                    if k != i and k not in paired
                    and _side_by_side(boxes[i], boxes[k], pair_gap_ratio,
                                      pair_vertical_overlap)]
        if not partners:
            leg_boxes[i] = boxes[i]
            continue
        k = min(partners, key=lambda k: _center_gap(boxes[i], boxes[k]))
        paired.update((i, k))
        a, b = boxes[i], boxes[k]
        leg_boxes[i] = (min(a[0], b[0]), min(a[1], b[1]),
                        max(a[2], b[2]), max(a[3], b[3]))

    return [(i, boxes[i] if c != leg_class else leg_boxes[i])
            for i, c in enumerate(classes)
            if c != leg_class or i in leg_boxes]


def _center_gap(a, b):
    return abs((a[0] + a[2]) - (b[0] + b[2])) / 2.0


def _side_by_side(a, b, gap_ratio, vertical_overlap):
    """두 박스가 한 사람의 두 다리처럼 가로로 나란한가."""
    width_sum = (a[2] - a[0]) + (b[2] - b[0])
    if _center_gap(a, b) > gap_ratio * width_sum:
        return False
    overlap = min(a[3], b[3]) - max(a[1], b[1])
    shorter = min(a[3] - a[1], b[3] - b[1])
    return shorter > 0 and overlap >= vertical_overlap * shorter


def body_center_radius(config, leg):
    """박스 종류에 맞는 중심 보정 거리(m)."""
    return config.leg_radius if leg else config.person_box_radius


def push_to_body_center(x, y, z, radius):
    """
    광학(optical) frame 점을 카메라에서 멀어지는 수평 방향으로 radius만큼 민다.

    depth는 사람 몸의 카메라 쪽 겉면까지 거리라서, 사람 중심은 그보다 몸 반경만큼 뒤에 있다.
    optical frame에서 수평면은 x(오른쪽)·z(앞), y(아래)는 높이라 그대로 둔다
    (카메라가 수평으로 달려 있다는 전제).
    """
    horizontal = np.hypot(x, z)
    if horizontal <= 0.0 or radius == 0.0:
        return x, y, z
    scale = (horizontal + radius) / horizontal
    return x * scale, y, z * scale


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


def clipped_at_edge(box, image_width, margin_px, min_width_px):
    """
    박스가 화면 좌우 끝에 닿아 있고 폭이 좁은가 (사람이 조금만 걸쳐 보임).

    이런 박스는 depth 영역 대부분이 사람 뒤 배경이라 배경 거리를 재고,
    박스 중심도 사람보다 화면 안쪽이라 방향까지 틀어진다. 거리 계산에 쓰지 않는다.
    """
    x1, _, x2, _ = box
    at_edge = x1 <= margin_px or x2 >= image_width - margin_px
    return at_edge and (x2 - x1) < min_width_px


class DepthJumpFilter:
    """
    같은 트랙의 depth가 한 프레임에 jump_m 넘게 튀면 그 값을 버리고 직전 값을 쓴다.

    confirm_frames 프레임 연속으로 튀면(사람이 정말 그 자리에 있음) 새 값을 받아들인다.
    max_age_s 넘게 안 보였던 트랙은 처음 보는 것처럼 새 값을 받는다.
    """

    def __init__(self, jump_m=1.0, confirm_frames=3, max_age_s=1.0):
        self.jump_m = jump_m
        self.confirm_frames = confirm_frames
        self.max_age_s = max_age_s
        self._tracks = {}  # track id -> [받아들인 depth, 연속 튐 수, 마지막 시각]

    def update(self, track_id, depth, stamp):
        """(쓸 depth, 이번 값을 버렸는지)를 반환한다."""
        state = self._tracks.get(track_id)
        if (state is None or stamp - state[2] > self.max_age_s
                or abs(depth - state[0]) <= self.jump_m):
            self._tracks[track_id] = [depth, 0, stamp]
            return depth, False
        state[1] += 1
        state[2] = stamp
        if state[1] >= self.confirm_frames:
            self._tracks[track_id] = [depth, 0, stamp]
            return depth, False
        return state[0], True

    def cleanup(self, stamp):
        for track_id in [k for k, s in self._tracks.items()
                         if stamp - s[2] > self.max_age_s]:
            del self._tracks[track_id]


# 아래는 라이다 점 전처리(지도 벽 걸러내기·사람 크기 덩어리)와 다가옴 계산이다. 예전 tof_node 래치에서 썼고,
# 덩어리 판정은 라이다 다리 검출기(R9)의 입력으로, closest_approach는 사람 기다리기 상태 기계가 쓴다 (설계 2-7)


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


def tracks_ahead_of_bumper(people, robot_x, robot_y, robot_yaw, bumper_x):
    """
    고정 좌표계(odom) 사람 (x, y, vx, vy) 목록을 로봇 축 기준 (범퍼 앞 x, y, vx, vy)로 바꾼다.

    위치는 로봇 위치를 빼고 로봇 방향으로 돌린 뒤 x에서 범퍼 위치를 뺀다(기다리기 구역은 범퍼 앞부터 잰다).
    속도는 돌리기만 하고 로봇 속도를 빼지 않는다: 사람 자신의 속도라야 로봇이 서 있는 사람에게 다가가는 것을
    "사람이 다가옴"으로 잘못 보지 않는다.
    """
    c, s = np.cos(robot_yaw), np.sin(robot_yaw)
    tracks = []
    for x, y, vx, vy in people:
        dx, dy = x - robot_x, y - robot_y
        tracks.append((float(c * dx + s * dy - bumper_x), float(-s * dx + c * dy),
                       float(c * vx + s * vy), float(-s * vx + c * vy)))
    return tracks
