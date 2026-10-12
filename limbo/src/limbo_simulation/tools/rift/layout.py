"""협곡 느낌 맵의 배치. 게임 파일은 쓰지 않고 구조(3 라인, 강, 정글, 기지)만 따라 새로 만든다.

좌표는 맵 한 변을 0~1로 둔 값이다 (u: 오른쪽, v: 위). SIZE를 곱해 미터로 바꾼다.
파랑 팀은 왼쪽 아래, 빨강 팀은 오른쪽 위. 빨강 쪽은 파랑 쪽을 가운데 기준으로 180° 돌려 만든다.
걸을 수 있는 곳만 적고, 나머지는 모두 벽이다.
"""
import cv2
import numpy as np

SIZE = 40.0            # 맵 한 변 (m)
RESOLUTION = 0.05      # 지도 격자 (m)
SPAWN = (0.13, 0.13)   # 로봇 시작 = 월드 원점 (파랑 기지)

LANE_WIDTH = 3.5
RIVER_WIDTH = 3.0
JUNGLE_PATH_WIDTH = 1.6
CAMP_RADIUS = 1.8
PIT_RADIUS = 2.2
TOWER_RADIUS = 0.6
NEXUS_RADIUS = 1.0

# 라인 (꺾은선). 파랑 기지에서 빨강 기지로
LANES = {
    'top': [(0.07, 0.20), (0.07, 0.93), (0.80, 0.93)],
    'mid': [(0.20, 0.20), (0.80, 0.80)],
    'bot': [(0.20, 0.07), (0.93, 0.07), (0.93, 0.80)],
}
RIVER = [(0.07, 0.93), (0.30, 0.70), (0.50, 0.50), (0.70, 0.30), (0.93, 0.07)]
PITS = {'바론': (0.31, 0.69), '용': (0.69, 0.31)}

# 파랑 쪽 정글 캠프와 샛길 (빨강 쪽은 돌려서 만든다)
CAMPS = {'블루': (0.25, 0.53), '두꺼비': (0.15, 0.57), '늑대': (0.26, 0.42),
         '레드': (0.52, 0.25), '칼날부리': (0.45, 0.34), '돌거북': (0.57, 0.14)}
JUNGLE_PATHS = [
    [(0.07, 0.47), (0.15, 0.57), (0.25, 0.53), (0.34, 0.62)],      # 탑 라인 → 두꺼비 → 블루 → 강
    [(0.25, 0.53), (0.26, 0.42), (0.36, 0.36)],                      # 블루 → 늑대 → 미드
    [(0.26, 0.42), (0.17, 0.30)],                                     # 늑대 → 기지 쪽
    [(0.47, 0.07), (0.57, 0.14), (0.52, 0.25), (0.62, 0.34)],      # 바텀 라인 → 돌거북 → 레드 → 강
    [(0.52, 0.25), (0.45, 0.34), (0.40, 0.40)],                      # 레드 → 칼날부리 → 미드
    [(0.52, 0.25), (0.30, 0.17)],                                     # 레드 → 기지 쪽
]
BASE = (0.0, 0.0, 0.24, 0.24)  # 파랑 기지 (u0, v0, u1, v1)

# 파랑 포탑 (라인별 바깥 → 안쪽 → 억제기 앞) + 넥서스
TOWERS = [(0.07, 0.62), (0.07, 0.42), (0.07, 0.27),
          (0.39, 0.39), (0.32, 0.32), (0.25, 0.25),
          (0.62, 0.07), (0.42, 0.07), (0.27, 0.07)]
NEXUS = (0.10, 0.10)


def mirror(p):
    return (1.0 - p[0], 1.0 - p[1])


def build_grid():
    """True = 벽. (행, 열) = (위에서 아래, 왼쪽에서 오른쪽)"""
    n = int(round(SIZE / RESOLUTION))
    free = np.zeros((n, n), np.uint8)

    def px(p):
        return int(round(p[0] * n)), int(round((1.0 - p[1]) * n))

    def width_px(meters):
        return max(1, int(round(meters / RESOLUTION)))

    def polyline(points, meters):
        for a, b in zip(points, points[1:]):
            cv2.line(free, px(a), px(b), 1, width_px(meters))
        for p in points:  # 꺾이는 곳을 둥글게
            cv2.circle(free, px(p), width_px(meters) // 2, 1, -1)

    for side in (lambda p: p, mirror):
        u0, v0, u1, v1 = BASE
        a, b = side((u0, v0)), side((u1, v1))
        cv2.rectangle(free, px(a), px(b), 1, -1)
        for path in JUNGLE_PATHS:
            polyline([side(p) for p in path], JUNGLE_PATH_WIDTH)
        for p in CAMPS.values():
            cv2.circle(free, px(side(p)), width_px(CAMP_RADIUS), 1, -1)
    for lane in LANES.values():
        polyline(lane, LANE_WIDTH)
    polyline(RIVER, RIVER_WIDTH)
    for p in PITS.values():
        cv2.circle(free, px(p), width_px(PIT_RADIUS), 1, -1)

    grid = free == 0
    for side in (lambda p: p, mirror):
        for t in TOWERS:
            cv2.circle(grid.view(np.uint8), px(side(t)), width_px(TOWER_RADIUS), 1, -1)
        cv2.circle(grid.view(np.uint8), px(side(NEXUS)), width_px(NEXUS_RADIUS), 1, -1)
    edge = width_px(0.3)  # 바깥 테두리 벽
    grid[:edge, :] = grid[-edge:, :] = True
    grid[:, :edge] = grid[:, -edge:] = True
    return grid


def to_world(p):
    """0~1 좌표 → 월드 미터 (로봇 시작이 원점)"""
    return ((p[0] - SPAWN[0]) * SIZE, (p[1] - SPAWN[1]) * SIZE)
