"""학원 2층 가구 배치. 사용자가 그린 대략적인 배치(real2)에서 위치·개수를 읽고, 통로는 실제 기준으로 맞춘다.

- 가구와 벽 사이 WALL_GAP(0.9 m, 한 사람 + 로봇), 같은 방 가구끼리 AISLE(1.2 m, 사람 두 명이 엇갈림)
- 책상 줄(같은 방향으로 나란한 긴 가구 여러 개)은 방 폭에 맞춰 고르게 다시 놓는다 (줄 수·방향·길이는 그대로)
- 나머지는 기준보다 가까운 면만 안쪽으로 줄인다 (위치·개수는 그대로)
- 가구는 Nav2 지도에 넣지 않는다 (센서로 보고 피함). 고정된 정수기만 지도에도 넣는다

좌표는 월드 미터 (x0, y0, x1, y1). 그림에서 읽은 값이라 몇 cm씩 어긋날 수 있다.
"""
import math
import os
import re

import cv2
import numpy as np

WALL_GAP = 0.9
AISLE = 1.2
STEP = 0.05

# (이름, 높이 m, [(x0, y0, x1, y1), ...]) — 한 줄이 한 방(같은 방 가구끼리 AISLE을 지킨다)
ROOMS = [
    ('207 교실-6 책상', 0.72, [(-13.38, 14.92, -10.75, 17.30), (-8.45, 14.90, -6.05, 17.42), (-13.60, 10.72, -11.12, 13.35)]),
    ('206 교실-5 책상', 0.72, [(5.00, 15.85, 11.95, 17.22), (5.08, 13.85, 12.05, 15.48), (5.12, 11.85, 12.15, 13.48)]),
    ('208 교실-7 책상', 0.72, [(-14.18, 1.43, -12.43, 7.55), (-11.82, 1.40, -9.85, 7.55), (-9.50, 1.65, -8.18, 7.45)]),
    ('205 교실-4 책상', 0.72, [(7.58, 1.55, 9.15, 7.40), (9.55, 1.68, 11.12, 7.42), (11.45, 1.78, 12.95, 7.42)]),
    ('202 교실-1 책상', 0.72, [(-13.62, -4.60, -6.68, -2.85), (-13.62, -6.82, -6.72, -5.02), (-13.68, -8.72, -6.68, -7.20)]),
    ('209 위쪽 작은 방 책상', 0.72, [(-4.05, -4.95, -2.45, -2.95)]),
    ('209 아래쪽 작은 방 책상', 0.72, [(-3.90, -7.90, -2.30, -6.40)]),
    ('209 상담실 책상', 0.72, [(-0.40, -5.35, 0.82, -3.90), (-0.48, -7.60, 0.82, -6.03)]),
    ('203 휴게실 테이블', 0.72, [(5.25, -4.78, 7.82, -2.72), (5.38, -8.28, 7.92, -5.90)]),
    ('204 교실-3 책상', 0.72, [(9.40, -8.18, 13.08, -2.98)]),
]
# 소파처럼 높이가 다른 것: (방 이름, 몇 번째) → 높이
HEIGHT_OVERRIDE = {}
# 벽에 붙는 가구 (규칙 적용 안 함). (모델, x, y, 방향 rad, 지도에 넣을 상자 또는 None)
# 정수기는 안 움직여서 지도에도 넣는다(받침 0.35 m + 여유). 소파는 옮길 수 있어 센서로 피한다
AGAINST_WALL = [
    ('water_dispenser', -4.34, 9.45, 1.5708, (-4.55, 9.25, -4.13, 9.67)),     # 위쪽 복도, 계단실 벽에 붙어 북쪽을 봄
    ('water_dispenser', 2.20, 2.17, -1.5708, (1.99, 1.95, 2.41, 2.37)),       # 홀, 계단실 벽에 붙어 남쪽을 봄
    ('Sofa', 2.71, -4.40, 3.1416, None), ('Sofa', 2.71, -6.80, 3.1416, None),  # 209 상담실 동쪽 벽
]

# 방마다 가구 종류. rows: 그려 준 긴 띠마다 1인용 책상을 세로로 줄지어 놓고 앞(교탁)을 보게 한다, group: 책상을 붙인 모둠 + 둘레 의자,
# tables: 나무 테이블 + 양쪽 의자, single: 나무 테이블 하나 + 의자 하나 (작은 방이라 벽 간격 규칙을 느슨하게)
KIND = {'207 교실-6 책상': 'group', '206 교실-5 책상': 'rows', '208 교실-7 책상': 'rows', '205 교실-4 책상': 'rows',
        '202 교실-1 책상': 'rows', '209 위쪽 작은 방 책상': 'single', '209 아래쪽 작은 방 책상': 'single',
        '209 상담실 책상': 'tables', '203 휴게실 테이블': 'tables', '204 교실-3 책상': 'group'}
# 모델 크기와 기본 방향 (Gazebo에 띄워 확인함)
FOLD_TABLE = (1.82, 0.74)   # foldable_table: 긴 쪽이 x
WOOD_TABLE = (1.5, 0.8)     # Table: 긴 쪽이 x, 높이 1.0 m
CHAIR = 0.5                 # foldable_chair: 앉은 사람이 -y를 봄
CHAIR_OUT = 0.05            # 의자 가운데가 책상 끝에서 바깥으로 나온 거리 (반쯤 밀어 넣은 상태 → 통로로 0.3 m 나옴)
STUDENT_DESK = (0.65, 0.5)  # student_desk: 긴 쪽(0.65)이 x
SEAT_PITCH = 1.0            # 띠를 따라 책상 + 의자 한 자리 간격
# rows 교실의 앞(교탁 쪽) 방향. 띠의 긴 방향을 따라 문이 있는 끝이 앞이다.
# 208·205는 양쪽 끝에 문이 있어 북쪽을 앞으로 골랐다
FRONT = {'206 교실-5 책상': (-1, 0), '202 교실-1 책상': (1, 0), '208 교실-7 책상': (0, 1), '205 교실-4 책상': (0, 1)}


def load_map():
    here = os.path.dirname(os.path.abspath(__file__))
    maps = os.path.join(here, '..', '..', '..', 'limbo_navigation', 'maps')
    meta = open(os.path.join(maps, 'aischool_2f_map.yaml')).read()
    ox, oy = map(float, re.search(r'origin: \[([-\d.]+), ([-\d.]+)', meta).groups())
    wall = cv2.imread(os.path.join(maps, 'aischool_2f_map.pgm'), 0) < 100
    return wall, ox, oy


def fit(rooms=ROOMS):
    """규칙에 맞게 줄인 가구 목록 [(방, 번호, 높이, (x0, y0, x1, y1)), ...]"""
    wall, ox, oy = load_map()
    h = wall.shape[0]
    dist = cv2.distanceTransform((~wall).astype(np.uint8), cv2.DIST_L2, 5) * STEP

    def wall_dist(x, y):
        c, r = int((x - ox) / STEP), int(h - (y - oy) / STEP)
        return dist[r, c]

    def side_too_close(b, side):
        x0, y0, x1, y1 = b
        n = 20
        if side in ('left', 'right'):
            x = x0 if side == 'left' else x1
            return any(wall_dist(x, y0 + (y1 - y0) * i / n) < WALL_GAP for i in range(n + 1))
        y = y0 if side == 'bottom' else y1
        return any(wall_dist(x0 + (x1 - x0) * i / n, y) < WALL_GAP for i in range(n + 1))

    def free_extent(x, y, dx, dy):
        """(x, y)에서 (dx, dy) 방향으로 벽까지 거리"""
        d = 0.0
        while wall_dist(x + dx * d, y + dy * d) > STEP:
            d += STEP
        return d

    def spread_rows(boxes):
        """나란한 책상 줄을 방 폭에 고르게 놓는다. 줄이 아니면 그대로 둔다"""
        if len(boxes) < 2:
            return boxes
        # 줄 = 길이가 폭의 2.5배 넘는 긴 가구가 같은 방향으로 나란히 (긴 쪽이 서로 겹침)
        horizontal = all(b[2] - b[0] > 2.5 * (b[3] - b[1]) for b in boxes)
        vertical = all(b[3] - b[1] > 2.5 * (b[2] - b[0]) for b in boxes)
        if not (horizontal or vertical):
            return boxes
        a = 1 if horizontal else 0          # 줄이 쌓이는 축 (가로 줄이면 y)
        L = 1 - a                           # 줄의 긴 축
        if max(b[L] for b in boxes) > min(b[L + 2] for b in boxes):
            return boxes                    # 긴 쪽이 안 겹치면 나란한 줄이 아님
        cx = sum(b[0] + b[2] for b in boxes) / (2 * len(boxes))
        cy = sum(b[1] + b[3] for b in boxes) / (2 * len(boxes))
        if a == 1:
            lo, hi = cy - free_extent(cx, cy, 0, -1), cy + free_extent(cx, cy, 0, 1)
        else:
            lo, hi = cx - free_extent(cx, cy, -1, 0), cx + free_extent(cx, cy, 1, 0)
        n = len(boxes)
        drawn = max(b[a + 2] - b[a] for b in boxes)
        thick = min(drawn, (hi - lo - 2 * WALL_GAP - (n - 1) * AISLE) / n)
        used = n * thick + (n - 1) * AISLE
        start = (lo + hi - used) / 2
        for k, b in enumerate(sorted(boxes, key=lambda b: b[a])):
            b[a] = start + k * (thick + AISLE)
            b[a + 2] = b[a] + thick
        return boxes

    out = []
    for name, height, boxes in rooms:
        boxes = spread_rows([list(b) for b in boxes])
        for b in boxes:   # 벽에서 WALL_GAP
            for _ in range(200):
                moved = False
                for side, i, d in (('left', 0, STEP), ('right', 2, -STEP), ('bottom', 1, STEP), ('top', 3, -STEP)):
                    if side_too_close(b, side):
                        b[i] += d
                        moved = True
                if not moved:
                    break
        for _ in range(200):   # 가구끼리 AISLE: 마주 보는 두 면을 같이 줄인다
            moved = False
            for i, a in enumerate(boxes):
                for b in boxes[i + 1:]:
                    gap_x = max(b[0] - a[2], a[0] - b[2])
                    gap_y = max(b[1] - a[3], a[1] - b[3])
                    if gap_x >= AISLE or gap_y >= AISLE:
                        continue
                    if gap_x >= gap_y:   # 옆으로 나란함 → x 방향으로 벌린다
                        left, right = (a, b) if a[0] < b[0] else (b, a)
                        left[2] -= STEP / 2; right[0] += STEP / 2
                    else:
                        low, high = (a, b) if a[1] < b[1] else (b, a)
                        low[3] -= STEP / 2; high[1] += STEP / 2
                    moved = True
            if not moved:
                break
        for k, b in enumerate(boxes):
            if b[2] - b[0] < 0.4 or b[3] - b[1] < 0.4:
                raise SystemExit(f'{name} {k}: 규칙을 지키면 너무 작아짐 ({b[2] - b[0]:.2f} x {b[3] - b[1]:.2f} m)')
            out.append((name, k, HEIGHT_OVERRIDE.get((name, k), height), tuple(round(v, 2) for v in b)))
    return out


def chair_yaw(face):
    """앉은 사람이 face(rad) 방향을 보게 하는 의자 방향. 의자는 기본으로 -y(-90°)를 본다"""
    return face + math.pi / 2


def table_with_chairs(model, size, cx, cy, along_x, chair_sides, seats_per_side):
    """책상 하나와 그 둘레 의자. chair_sides: 의자를 놓을 쪽 ('-y', '+y', '-x', '+x')"""
    length, depth = size
    out = [(model, cx, cy, 0.0 if along_x else math.pi / 2)]
    half_l, half_d = length / 2, depth / 2
    for side in chair_sides:
        for k in range(seats_per_side):
            t = (k + 0.5) / seats_per_side * length - half_l       # 책상 긴 쪽을 따라 고르게
            off = half_d + CHAIR_OUT
            if along_x:
                x, y = cx + t, cy + (off if side == '+y' else -off)
                face = -math.pi / 2 if side == '+y' else math.pi / 2
                if side in ('-x', '+x'):
                    continue
            else:
                x, y = cx + (off if side == '+x' else -off), cy + t
                face = math.pi if side == '+x' else 0.0
                if side in ('-y', '+y'):
                    continue
            out.append(('foldable_chair', x, y, chair_yaw(face)))
    return out


def classroom_rows(strips, front):
    """띠마다 1인용 책상을 앞에서부터 줄지어 놓고, 의자는 책상 뒤에서 앞을 본다. 맨 앞에 교탁"""
    dx, dy = front
    face = math.atan2(dy, dx)
    desk_yaw = 0.0 if dx == 0 else math.pi / 2     # 책상 긴 쪽이 앞 방향과 직각
    out = []
    fronts = []
    for x0, y0, x1, y1 in strips:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        length = (y1 - y0) if dx == 0 else (x1 - x0)
        front_end = (cx + dx * length / 2, cy + dy * length / 2)
        fronts.append(front_end)
        for k in range(int(length // SEAT_PITCH)):
            back = STUDENT_DESK[1] / 2 + k * SEAT_PITCH            # 앞 끝에서 책상 가운데까지
            dxk, dyk = front_end[0] - dx * back, front_end[1] - dy * back
            out.append(('student_desk', dxk, dyk, desk_yaw))
            chair = STUDENT_DESK[1] / 2 + CHAIR_OUT
            out.append(('foldable_chair', dxk - dx * chair, dyk - dy * chair, chair_yaw(face)))
    # 교탁: 띠 앞 끝과 앞 벽의 가운데, 방 가로 가운데
    wall, ox, oy = load_map()
    h = wall.shape[0]
    fx = sum(p[0] for p in fronts) / len(fronts)
    fy = sum(p[1] for p in fronts) / len(fronts)
    gap = 0.0
    while not wall[int(h - (fy + dy * gap - oy) / STEP), int((fx + dx * gap - ox) / STEP)]:
        gap += STEP
    out.append(('Table', fx + dx * gap / 2, fy + dy * gap / 2, 0.0 if dx == 0 else math.pi / 2))
    return out


def place():
    """Gazebo에 놓을 모델 목록 [(모델, x, y, 방향 rad), ...]"""
    models = []
    fitted = fit()
    for name in FRONT:
        models += classroom_rows([b for n, _, _, b in fitted if n == name], FRONT[name])
    for name, _, _, (x0, y0, x1, y1) in fitted:
        kind = KIND[name]
        w, h = x1 - x0, y1 - y0
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        along_x = w >= h
        if kind == 'rows':
            continue   # 위에서 방 단위로 놓았다
        elif kind == 'group':
            # 책상 긴 쪽을 상자의 긴 쪽에 맞추고, 들어가는 만큼 격자로 붙인다. 의자는 바깥쪽 긴 변에만
            long_side, short_side = max(w, h), min(w, h)
            cols = max(1, int(long_side // FOLD_TABLE[0]))
            rows = max(1, int(short_side // FOLD_TABLE[1]))
            rows = min(rows, 2)          # 가운데 책상은 의자를 못 놓으니 두 줄까지만
            for i in range(cols):
                for j in range(rows):
                    a = (i - (cols - 1) / 2) * FOLD_TABLE[0]
                    b = (j - (rows - 1) / 2) * FOLD_TABLE[1]
                    tx, ty = (cx + a, cy + b) if along_x else (cx + b, cy + a)
                    if along_x:
                        sides = (['-y'] if j == 0 else []) + (['+y'] if j == rows - 1 else [])
                    else:
                        sides = (['-x'] if j == 0 else []) + (['+x'] if j == rows - 1 else [])
                    models += table_with_chairs('foldable_table', FOLD_TABLE, tx, ty, along_x, sides, 2)
        elif kind == 'tables':
            models += table_with_chairs('Table', WOOD_TABLE, cx, cy, along_x,
                                        ['-y', '+y'] if along_x else ['-x', '+x'], 1)
        elif kind == 'single':
            models += table_with_chairs('Table', WOOD_TABLE, cx, cy, along_x, ['-y'] if along_x else ['-x'], 1)
    for model, x, y, yaw, _ in AGAINST_WALL:
        models.append((model, x, y, yaw))
    return models
