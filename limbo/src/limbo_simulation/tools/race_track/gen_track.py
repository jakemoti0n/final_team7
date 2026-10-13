"""작고 구불구불한 레이싱 트랙의 Nav2 지도(race_track_map)와 Gazebo 월드(race_track.sdf)를 만든다.

사용법: python3 gen_track.py [--preview 그림.png]
- 트랙 모양은 CONTROL(중심선 조절점, m)로 정한다. 점들을 지나는 닫힌 곡선(Catmull-Rom)으로 잇는다
- 트랙 폭 TRACK_WIDTH, 양옆 방호벽(높이 BARRIER_HEIGHT)은 지도에도 들어간다. 안쪽 잔디는 방호벽에 막혀 못 들어간다
- 로봇은 월드 원점(출발선)에서 +x를 보고 시작한다. 그래서 CONTROL의 (-2, 0), (0, 0), (2, 0)은 바꾸지 않는다
"""
import math
import os
import re
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SIM = os.path.join(HERE, '..', '..')
WORLD_DIR = os.path.join(SIM, 'worlds')
MODEL_DIR = os.path.join(SIM, 'models', 'race_track_terrain')
MAP_DIR = os.path.join(SIM, '..', 'limbo_navigation', 'maps')
NAME = 'race_track'

RES = 0.05                 # 지도 격자 (m)
TRACK_WIDTH = 1.6          # v14(폭 0.59 m) 양옆으로 약 0.5 m
BARRIER_THICK = 0.15
BARRIER_HEIGHT = 1.0       # MID-360(0.926 m)보다 높아야 가까이서도 보인다
STRIPE = 1.0               # 방호벽 빨강·흰색 한 칸 길이 (m)
MARGIN = 1.0               # 트랙 바깥 여백 (m)
COLORS = {'asphalt': '0.25 0.25 0.27 1', 'grass': '0.35 0.55 0.3 1', 'red': '0.85 0.15 0.15 1',
          'white': '0.95 0.95 0.95 1', 'line': '1 1 1 1'}

# 중심선 조절점 (m). 출발 직선 → 오른쪽 직선 → 가운데로 파고드는 헤어핀·S자 → 왼쪽 굽이 → 출발선
CONTROL = [
    (-2.0, 0.0), (0.0, 0.0), (2.0, 0.0), (5.0, 0.0),        # 출발 직선 (+x)
    (7.6, 0.3), (9.4, 1.4), (10.0, 3.0),                    # 오른쪽 아래 코너
    (10.0, 6.0),                                            # 오른쪽 직선 (x = 10)
    (10.0, 9.0), (9.4, 10.8), (7.8, 11.6),                  # 오른쪽 위 코너
    (6.0, 11.0), (5.4, 9.4), (6.6, 7.8),                    # 가운데로 파고드는 헤어핀
    (5.8, 6.0), (4.0, 5.6), (3.0, 7.2),                     # S자
    (3.0, 9.4), (1.6, 11.2),                                # 위로 빠져나감
    (-1.0, 10.4), (-2.2, 7.6), (-1.6, 5.6), (-2.8, 3.6),    # 왼쪽 굽이
    (-4.2, 1.8), (-3.8, 0.3),                               # 출발선으로
]


def catmull_rom_closed(points, step=0.05):
    """닫힌 Catmull-Rom 곡선을 step(m) 간격 점들로"""
    out = []
    n = len(points)
    for i in range(n):
        p0, p1, p2, p3 = points[i - 1], points[i], points[(i + 1) % n], points[(i + 2) % n]
        seg = max(2, int(math.dist(p1, p2) / step))
        for k in range(seg):
            t = k / seg
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in range(2)))
    return out


center = catmull_rom_closed(CONTROL)
xs, ys = [p[0] for p in center], [p[1] for p in center]
pad = TRACK_WIDTH / 2 + BARRIER_THICK + MARGIN
ox, oy = min(xs) - pad, min(ys) - pad
W, H = int(math.ceil((max(xs) + pad - ox) / RES)), int(math.ceil((max(ys) + pad - oy) / RES))


def px(p):
    return int(round((p[0] - ox) / RES)), int(round(H - (p[1] - oy) / RES))


# --- 트랙·방호벽 칸
track = np.zeros((H, W), np.uint8)
cv2.polylines(track, [np.array([px(p) for p in center], np.int32)], True, 1, int(round(TRACK_WIDTH / RES)))
track = track > 0
k = int(round(BARRIER_THICK / RES)) * 2 + 1
barrier = (cv2.dilate(track.astype(np.uint8), np.ones((k, k), np.uint8)) > 0) & ~track

# 방호벽 칸마다 가장 가까운 중심선 위치(길이)로 빨강·흰색을 번갈아 칠한다
arc = np.cumsum([0.0] + [math.dist(a, b) for a, b in zip(center, center[1:])])
lab = np.zeros((H, W), np.int32)
for i, p in enumerate(center):
    cv2.circle(lab, px(p), int(TRACK_WIDTH / RES), i + 1, -1)          # 대략적인 가까운 점 표시 (나중 것이 덮음)
nearest = np.where(lab > 0, lab - 1, 0)
red = barrier & ((arc[nearest] // STRIPE).astype(int) % 2 == 0)
white = barrier & ~red

# 출발선: 원점을 가로지르는 흰 띠 (폭 0.2 m)
start_line = np.zeros((H, W), np.uint8)
x0, y0 = px((0.0, -TRACK_WIDTH / 2)); x1, y1 = px((0.0, TRACK_WIDTH / 2))
cv2.line(start_line, (x0, y0), (x1, y1), 1, int(round(0.2 / RES)))
start_line = (start_line > 0) & track


# --- 검사: 트랙이 자기 자신과 너무 가까운 곳 (방호벽 하나 사이도 없음), 가장 급한 코너 반지름
def check():
    pts = np.array(center)
    step = 10
    sub, sub_arc = pts[::step], arc[::step]
    d = np.linalg.norm(sub[:, None, :] - sub[None, :, :], axis=2)
    along = np.abs(sub_arc[:, None] - sub_arc[None, :])
    along = np.minimum(along, arc[-1] - along)
    close = (d < TRACK_WIDTH + 2 * BARRIER_THICK) & (along > 3 * TRACK_WIDTH)
    radii = []
    for i in range(0, len(pts) - 20, 5):
        a, b, c = pts[i], pts[i + 10], pts[i + 20]
        ab, bc, ca = np.linalg.norm(b - a), np.linalg.norm(c - b), np.linalg.norm(a - c)
        area = abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2
        if area > 1e-6:
            radii.append((ab * bc * ca / (4 * area), tuple(np.round(b, 1))))
    return close.any(), min(radii)


too_close, (r_min, r_at) = check()
print(f'트랙 길이 {arc[-1]:.1f} m, 크기 {W * RES:.1f} x {H * RES:.1f} m, 가장 급한 코너 반지름 {r_min:.2f} m ({r_at} 근처)')
if too_close:
    raise SystemExit('트랙이 자기 자신과 방호벽 하나 두께보다 가까운 곳이 있음 (CONTROL을 고칠 것)')

if '--preview' in sys.argv:
    img = np.full((H, W, 3), (70, 140, 90), np.uint8)
    img[track] = (70, 65, 65); img[red] = (40, 40, 220); img[white] = (240, 240, 240); img[start_line] = (255, 255, 255)
    for i, p in enumerate(CONTROL):
        cv2.circle(img, px(p), 4, (0, 220, 255), -1)
    for gx in range(int(math.ceil(ox)), int(ox + W * RES) + 1):
        cv2.line(img, px((gx, oy)), px((gx, oy + H * RES)), (110, 170, 120), 1)
    for gy in range(int(math.ceil(oy)), int(oy + H * RES) + 1):
        cv2.line(img, px((ox, gy)), px((ox + W * RES, gy)), (110, 170, 120), 1)
    path = sys.argv[sys.argv.index('--preview') + 1]
    cv2.imwrite(path, cv2.resize(img, (W * 2, H * 2), interpolation=cv2.INTER_NEAREST))
    print(path)
    sys.exit(0)


# --- Nav2 지도: 방호벽만 벽. 트랙 밖 잔디는 방호벽에 막혀 들어갈 수 없다
cv2.imwrite(os.path.join(MAP_DIR, f'{NAME}_map.pgm'), np.where(barrier, 0, 254).astype(np.uint8))
open(os.path.join(MAP_DIR, f'{NAME}_map.yaml'), 'w').write(
    f'image: {NAME}_map.pgm\nmode: trinary\nresolution: {RES}\n'
    f'origin: [{ox:.3f}, {oy:.3f}, 0.0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n')


# --- 메시: 칸을 상자로 합쳐 종류마다 OBJ 하나 (따로 두면 센서가 하나씩 그려 시뮬레이션이 느려진다)
def merge_boxes(mask):
    boxes, open_runs = [], {}
    for row in range(H + 1):
        runs = set()
        if row < H:
            c = 0
            while c < W:
                if mask[row, c]:
                    s = c
                    while c < W and mask[row, c]:
                        c += 1
                    runs.add((s, c))
                else:
                    c += 1
        for run in list(open_runs):
            if run not in runs:
                boxes.append((run[0], open_runs.pop(run), run[1], row))
        for run in runs:
            open_runs.setdefault(run, row)
    return boxes


def write_obj(path, mask, z0, z1):
    """z0 == z1이면 바닥 판(윗면만). 법선이 없으면 dartsim이 충돌 메시를 읽다 죽는다"""
    vertices, faces = [], []
    for c0, r0, c1, r1 in merge_boxes(mask):
        x0, x1 = ox + c0 * RES, ox + c1 * RES
        y1, y0 = oy + (H - r0) * RES, oy + (H - r1) * RES
        base = len(vertices)
        for z in (z0, z1):
            vertices += [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]
        v = [base + k + 1 for k in range(8)]
        faces += [((v[4], v[5], v[6]), 1), ((v[4], v[6], v[7]), 1)]
        if z1 > z0:
            faces += [((v[0], v[1], v[5]), 2), ((v[0], v[5], v[4]), 2), ((v[1], v[2], v[6]), 3), ((v[1], v[6], v[5]), 3),
                      ((v[2], v[3], v[7]), 4), ((v[2], v[7], v[6]), 4), ((v[3], v[0], v[4]), 5), ((v[3], v[4], v[7]), 5)]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write('# gen_track.py가 만든다\n')
        f.writelines(f'v {x:.3f} {y:.3f} {z:.3f}\n' for x, y, z in vertices)
        f.write('vn 0 0 1\nvn 0 -1 0\nvn 1 0 0\nvn 0 1 0\nvn -1 0 0\n')
        f.writelines(f'f {a}//{k} {b}//{k} {c}//{k}\n' for (a, b, c), k in faces)


meshes = os.path.join(MODEL_DIR, 'meshes')
write_obj(os.path.join(meshes, 'barrier_red.obj'), red, 0.0, BARRIER_HEIGHT)
write_obj(os.path.join(meshes, 'barrier_white.obj'), white, 0.0, BARRIER_HEIGHT)
write_obj(os.path.join(meshes, 'asphalt.obj'), track & ~start_line, 0.003, 0.003)
write_obj(os.path.join(meshes, 'start_line.obj'), start_line, 0.004, 0.004)


def mesh_link(name, color, collide):
    geom = f'<geometry><mesh><uri>model://race_track_terrain/meshes/{name}.obj</uri></mesh></geometry>'
    col = f'<collision name="{name}_c">{geom}</collision>' if collide else ''
    return f'      {col}<visual name="{name}_v">{geom}<material><ambient>{color}</ambient><diffuse>{color}</diffuse></material></visual>'


cx, cy = ox + W * RES / 2, oy + H * RES / 2
grass = (f'      <visual name="grass_v"><pose>{cx:.2f} {cy:.2f} 0.001 0 0 0</pose><geometry><box><size>{W * RES:.2f} {H * RES:.2f} 0.002</size>'
         f'</box></geometry><material><ambient>{COLORS["grass"]}</ambient><diffuse>{COLORS["grass"]}</diffuse></material></visual>')
open(os.path.join(MODEL_DIR, 'model.config'), 'w').write(
    '<?xml version="1.0"?>\n<model><name>race_track_terrain</name><version>1.0</version><sdf version="1.9">model.sdf</sdf>\n'
    '  <author><name>limbo team</name></author><description>gen_track.py가 만든 레이싱 트랙 (방호벽·아스팔트·출발선)</description></model>\n')
open(os.path.join(MODEL_DIR, 'model.sdf'), 'w').write(f'''<?xml version="1.0"?>
<sdf version="1.9">
  <!-- gen_track.py가 만든다. 직접 고치지 말 것 -->
  <model name="race_track_terrain">
    <static>true</static>
    <link name="link">
{mesh_link('barrier_red', COLORS['red'], True)}
{mesh_link('barrier_white', COLORS['white'], True)}
{mesh_link('asphalt', COLORS['asphalt'], False)}
{mesh_link('start_line', COLORS['line'], False)}
{grass}
    </link>
  </model>
</sdf>
''')

# --- 월드: 기존 월드에서 물리·플러그인·조명·바닥만 가져온다
base = open(os.path.join(WORLD_DIR, 'human_test_world.sdf')).read()
base = re.sub(r'<world name="[^"]+">', f'<world name="{NAME}">', base)
head, tail = base.split('</world>')[0], '</world>' + base.split('</world>')[1]
head = re.sub(r'\s*<model name="(?!ground_plane)[^"]*">.*?</model>', '', head, flags=re.S)
head = re.sub(r'\s*<actor .*?</actor>', '', head, flags=re.S)
terrain = f'    <include><uri>model://race_track_terrain</uri><name>{NAME}_terrain</name></include>'
open(os.path.join(WORLD_DIR, f'{NAME}.sdf'), 'w').write(head + '\n' + terrain + '\n  ' + tail)
print(f'{NAME}: 지도 {W}x{H} 칸, 원점 ({ox:.2f},{oy:.2f})')
