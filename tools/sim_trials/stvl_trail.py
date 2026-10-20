"""지역 STVL 층이 걷는 사람 뒤에 남기는 치명 꼬리를 잰다. 사용법: 시뮬이 떠 있을 때 python3 stvl_trail.py [초, 기본 60]

`/local_costmap/stvl_layer`의 치명 칸 가운데 정적 지도 벽(0.12 m 안)이 아닌 것을, 시뮬레이션 사람 실제 위치(`/sim/people`)까지의
거리로 나눠 4초마다 한 줄씩 찍는다. 사람 반경(0.5 m)보다 먼 칸이 꾸준히 나오면 그것이 꼬리(voxel_decay 기억)다.
왜 지도 벽을 빼나: 거리 양쪽 건물 벽이 치명 칸의 대부분이라 사람 자취가 묻힌다. 왜 실제 위치인가: 검출 트랙은 시야 밖 사람을 못 보니
"검출 못 한 사람"과 "꼬리"를 가르려면 정답이 필요하다(시뮬 전용).
벽 판정은 지도를 2칸 팽창시켜 두고 조회한다. 벽 칸 전체와 거리 행렬을 만들면 충장로 지도(벽 수백만 칸)에서 수십 GB가 되어
OOM으로 시뮬 전체의 heartbeat가 끊겼다(10-20, 회차 3개 무효).
"""
import sys, time, numpy as np, rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from nav_msgs.msg import OccupancyGrid
from geometry_msgs.msg import PoseArray
from tf2_ros import Buffer, TransformListener

BINS = [0, 0.5, 1.0, 1.5, 2.5, 100]   # 사람까지 거리 구간(m). 0.5 = person_filter 반경
WALL_CELLS = 2                         # 지도 벽에서 이 칸 수(0.05 m 격자 → 0.1 m) 안이면 벽으로 본다


def grid(g):
    return np.array(g.data, dtype=np.int16).reshape(g.info.height, g.info.width), g.info


def cells(g, cond):
    a, i = grid(g); ys, xs = np.where(cond(a))
    return np.c_[i.origin.position.x + (xs + 0.5) * i.resolution, i.origin.position.y + (ys + 0.5) * i.resolution]


def nearest(pts, ref):
    """칸마다 기준점(사람 수십 명)까지 최단 거리. 기준점이 수천 개를 넘는 용도로 쓰지 말 것(행렬 메모리)"""
    if len(pts) == 0 or len(ref) == 0:
        return np.full(len(pts), np.inf)
    return np.min(np.hypot(pts[:, 0, None] - ref[None, :, 0], pts[:, 1, None] - ref[None, :, 1]), axis=1)


def dilate(mask, cells):
    out = mask.copy()
    for dy in range(-cells, cells + 1):
        for dx in range(-cells, cells + 1):
            out |= np.roll(np.roll(mask, dy, 0), dx, 1)
    return out


def is_wall(pts, wall_mask, info):
    c = ((pts[:, 0] - info.origin.position.x) / info.resolution).astype(int)
    r = ((pts[:, 1] - info.origin.position.y) / info.resolution).astype(int)
    ok = (c >= 0) & (r >= 0) & (c < info.width) & (r < info.height)
    out = np.ones(len(pts), bool)          # 지도 밖은 벽으로 쳐서 뺀다
    out[ok] = wall_mask[r[ok], c[ok]]
    return out


def spin_for(n, secs):
    t = time.time()
    while time.time() - t < secs:
        rclpy.spin_once(n, timeout_sec=0.1)


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 60
    rclpy.init(); n = Node('stvl_trail'); m = {}
    latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE)
    n.create_subscription(OccupancyGrid, '/local_costmap/stvl_layer', lambda g: m.__setitem__('stvl', g), latched)
    n.create_subscription(OccupancyGrid, '/map', lambda g: m.__setitem__('map', g), latched)
    n.create_subscription(PoseArray, '/sim/people', lambda g: m.__setitem__('people', g), 10)
    buf = Buffer(); TransformListener(buf, n)
    wall_mask = None; t0 = time.time()
    print('t(s)  로봇 위치      4.5 m 안 사람  비벽 치명 칸 | 사람까지 ' + ' '.join(f'{a}-{b}' for a, b in zip(BINS[:-1], BINS[1:])))
    while time.time() - t0 < secs:
        t = time.time()
        while time.time() - t < 10 and not all(k in m for k in ('stvl', 'map', 'people')):
            rclpy.spin_once(n, timeout_sec=0.2)
        if not all(k in m for k in ('stvl', 'map', 'people')):
            print('토픽 없음:', [k for k in ('stvl', 'map', 'people') if k not in m]); continue
        if wall_mask is None:
            a, info = grid(m['map']); wall_mask = dilate(a >= 50, WALL_CELLS)
        try:
            tb = buf.lookup_transform('map', 'base_footprint', rclpy.time.Time())
            rx, ry = tb.transform.translation.x, tb.transform.translation.y
        except Exception:
            rx = ry = float('nan')
        ppl = np.array([[p.position.x, p.position.y] for p in m['people'].poses]).reshape(-1, 2)
        pts = cells(m['stvl'], lambda a: a >= 99)
        pts = pts[~is_wall(pts, wall_mask, info)]
        hist = np.histogram(nearest(pts, ppl), bins=BINS)[0]
        near_people = int(np.sum(np.hypot(ppl[:, 0] - rx, ppl[:, 1] - ry) < 4.5)) if len(ppl) else 0
        print(f'{time.time() - t0:4.0f}  ({rx:6.1f},{ry:5.1f})  {near_people:2d}명  {len(pts):5d} | ' + ' '.join(f'{h:4d}' for h in hist), flush=True)
        for k in ('stvl', 'people'):
            m.pop(k, None)
        spin_for(n, 4)                     # 자는 동안도 spin해야 TF·토픽이 갱신된다
    rclpy.shutdown()


if __name__ == '__main__':
    main()
