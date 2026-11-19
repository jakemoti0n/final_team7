"""SLAM 지도(PGM 픽셀)로 관제 화면용 자동 약도(SVG)를 만든다. 서버가 지도를 처음 읽을 때 한 번.

약도는 원본 지도와 영역·크기가 같다(viewBox = 원본 픽셀). 그래서 화면은 바탕 그림 주소만 바꾸면
waypoint·로봇 위치·지도 클릭 좌표가 그대로 맞는다.

1) 빈 칸(free)만 남긴다. 벽·미탐색은 버린다
2) 빈 칸에 둘러싸인 작은 검은 점(의자·사람·잡음, MIN_HOLE_M2 미만)은 빈 칸으로 메운다.
   다음 단계 전에 메워야 좁은 복도의 점 하나가 복도를 끊지 않는다
3) 열기(opening): MIN_WIDTH_M보다 좁은 레이저 줄무늬·틈을 지운다
4) CELL_M 칸으로 나눠 다수결 → 직각 외곽선
5) 가장 큰 덩어리와 waypoint가 있는 덩어리만 남기고, 칸으로 나누며 생긴 작은 구멍도 메운다
6) 바닥은 흰색, 바깥은 옅은 회색, 경계선은 진한 선, 1 m 격자
"""
import numpy as np

CELL_M = 0.25        # 외곽선 격자 (m)
MIN_WIDTH_M = 0.6    # 이보다 좁은 통로·줄무늬는 지운다 (m)
MIN_HOLE_M2 = 0.5    # 이보다 작은 안쪽 구멍(의자·사람·잡음)은 바닥으로 메운다 (m²)

BACKGROUND = "#ECEEE8"
FLOOR = "#FFFFFF"
GRID = "#DDE1D8"
WALL = "#2E3A33"


def _box_count(mask, k):
    """k×k 창(가운데 정렬) 안의 True 개수. 적분 영상으로 O(N)"""
    r = k // 2
    padded = np.pad(mask.astype(np.int32), ((r + 1, r), (r + 1, r)))
    s = padded.cumsum(0).cumsum(1)
    return s[k:, k:] - s[:-k, k:] - s[k:, :-k] + s[:-k, :-k]


def _components(grid):
    """4-연결 덩어리 번호(0 = 배경)와 덩어리별 칸 수(0번은 0).
    한 줄의 연속 구간(run) 단위로 이어 붙이므로 파이썬 반복은 구간 수만큼만 돈다"""
    rows = grid.shape[0]
    runs = []                     # (행, 시작, 끝)
    row_start = []                # 행마다 runs 안의 첫 번호
    for r in range(rows):
        row_start.append(len(runs))
        line = np.concatenate([[False], grid[r], [False]])
        change = np.flatnonzero(line[1:] != line[:-1])
        runs.extend((r, a, b) for a, b in zip(change[::2].tolist(), change[1::2].tolist()))
    row_start.append(len(runs))
    parent = list(range(len(runs)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for r in range(1, rows):
        i, j = row_start[r - 1], row_start[r]
        while i < row_start[r] and j < row_start[r + 1]:
            (_, a1, b1), (_, a2, b2) = runs[i], runs[j]
            if a1 < b2 and a2 < b1:          # 위아래 구간이 겹치면 같은 덩어리
                x, y = root(i), root(j)
                if x != y:
                    parent[max(x, y)] = min(x, y)
            if b1 < b2:
                i += 1
            else:
                j += 1
    labels = np.zeros(grid.shape, np.int32)
    number, sizes = {}, [0]
    for k, (r, a, b) in enumerate(runs):
        top = root(k)
        if top not in number:
            number[top] = len(sizes)
            sizes.append(0)
        labels[r, a:b] = number[top]
        sizes[number[top]] += b - a
    return labels, sizes


def _fill_small_holes(mask, max_cells, occupied=None):
    """mask가 아닌 덩어리 중 가장자리에 닿지 않고 max_cells보다 작은 것을 mask로 메운다.
    occupied를 주면 절반 넘게 점유(검정)인 구멍만 메운다: 의자·사람은 검정으로 찍히고,
    레이저 줄무늬 사이 틈은 미탐색(회색)이라 메우지 않는다 (메우면 줄무늬 다발이 바닥이 됨)"""
    holes, sizes = _components(~mask)
    edge = set(np.unique(np.concatenate([holes[0], holes[-1], holes[:, 0], holes[:, -1]])).tolist())
    small = [i for i in range(1, len(sizes)) if i not in edge and sizes[i] < max_cells]
    if small and occupied is not None:
        dark = np.bincount(holes[occupied], minlength=len(sizes))
        small = [i for i in small if dark[i] * 2 > sizes[i]]
    return mask | np.isin(holes, small) if small else mask


def floor_cells(width, height, pixels, resolution, free_thresh=0.196, negate=False, keep_px=()):
    """(바닥 칸 bool 배열, 칸 크기 px). keep_px: 남길 덩어리를 고르는 원본 픽셀 좌표 (열, 행)"""
    image = np.frombuffer(pixels, np.uint8).reshape(height, width)
    if negate:
        image = 255 - image
    free = image > 255 * (1 - free_thresh)   # map_server와 같은 기준 (점유 확률 < free_thresh)
    occupied = image < 255 * (1 - 0.65)      # 점유 확률 > 0.65 (map_server 기본 occupied_thresh)
    free = _fill_small_holes(free, MIN_HOLE_M2 / resolution ** 2, occupied)
    k = max(3, int(round(MIN_WIDTH_M / resolution)) | 1)
    free = _box_count(_box_count(free, k) == k * k, k) > 0   # 열기 = 침식 후 팽창

    s = max(1, int(round(CELL_M / resolution)))
    rows, cols = -(-height // s), -(-width // s)
    padded = np.zeros((rows * s, cols * s), np.float32)
    padded[:height, :width] = free
    cells = padded.reshape(rows, s, cols, s).mean(axis=(1, 3)) >= 0.5

    labels, sizes = _components(cells)
    if len(sizes) > 1:
        keep = {int(np.argmax(sizes[1:])) + 1}
        for col, row in keep_px:
            r, c = int(row) // s, int(col) // s
            if 0 <= r < rows and 0 <= c < cols and labels[r, c]:
                keep.add(int(labels[r, c]))
        cells = np.isin(labels, list(keep))

    return _fill_small_holes(cells, MIN_HOLE_M2 / (s * resolution) ** 2), s


def _floor_path(cells, s):
    """바닥 칸을 직사각형들로: 한 줄의 연속 구간을 위아래로 같은 구간끼리 합친다"""
    parts, open_runs = [], {}
    for r in range(cells.shape[0] + 1):
        runs = set()
        if r < cells.shape[0]:
            row = np.concatenate([[False], cells[r], [False]])
            change = np.flatnonzero(row[1:] != row[:-1])
            runs = set(zip(change[::2].tolist(), change[1::2].tolist()))
        for run in list(open_runs):
            if run not in runs:
                top = open_runs.pop(run)
                parts.append(f"M{run[0] * s} {top * s}h{(run[1] - run[0]) * s}v{(r - top) * s}h{-(run[1] - run[0]) * s}z")
        for run in runs:
            open_runs.setdefault(run, r)
    return "".join(parts)


def _edge_path(cells, s):
    """바닥과 바닥 아닌 칸 사이의 경계를 가로·세로 선분으로 (같은 줄의 이어진 선분은 하나로)"""
    padded = np.pad(cells, 1)
    parts = []
    horizontal = padded[1:, 1:-1] != padded[:-1, 1:-1]   # 칸 행 경계 r (0..rows), 열 c
    for r in range(horizontal.shape[0]):
        row = np.concatenate([[False], horizontal[r], [False]])
        change = np.flatnonzero(row[1:] != row[:-1])
        for a, b in zip(change[::2].tolist(), change[1::2].tolist()):
            parts.append(f"M{a * s} {r * s}H{b * s}")
    vertical = padded[1:-1, 1:] != padded[1:-1, :-1]       # 행 r, 칸 열 경계 c (0..cols)
    for c in range(vertical.shape[1]):
        col = np.concatenate([[False], vertical[:, c], [False]])
        change = np.flatnonzero(col[1:] != col[:-1])
        for a, b in zip(change[::2].tolist(), change[1::2].tolist()):
            parts.append(f"M{c * s} {a * s}V{b * s}")
    return "".join(parts)


def svg(width, height, pixels, resolution, origin, free_thresh=0.196, negate=False, keep_points=()):
    """자동 약도 SVG 바이트. keep_points: 지도 좌표(m) (x, y) — 그 점이 든 덩어리는 크기와 상관없이 남긴다"""
    ox, oy = origin[0], origin[1]
    keep_px = [((x - ox) / resolution, height - (y - oy) / resolution) for x, y in keep_points]
    cells, s = floor_cells(width, height, pixels, resolution, free_thresh, negate, keep_px)
    step = 1 / resolution
    grid = "".join(f"M{(gx - ox) * step:.2f} 0V{height}" for gx in range(int(np.ceil(ox)), int(ox + width * resolution) + 1))
    grid += "".join(f"M0 {height - (gy - oy) * step:.2f}H{width}" for gy in range(int(np.ceil(oy)), int(oy + height * resolution) + 1))
    line = max(1.0, 0.1 / resolution)   # 벽 선 두께 약 10 cm
    body = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
            f'<rect width="{width}" height="{height}" fill="{BACKGROUND}"/>'
            f'<path d="{_floor_path(cells, s)}" fill="{FLOOR}"/>'
            f'<path d="{grid}" stroke="{GRID}" stroke-width="{max(0.5, line / 3):.2f}" fill="none"/>'
            f'<path d="{_edge_path(cells, s)}" stroke="{WALL}" stroke-width="{line:.2f}" stroke-linecap="square" fill="none"/>'
            "</svg>")
    return body.encode("utf-8")
