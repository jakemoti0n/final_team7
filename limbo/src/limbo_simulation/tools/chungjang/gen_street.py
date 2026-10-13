"""광주 충장로 보행자 거리 가운데 200 m를 OpenStreetMap 자료로 재현한 Nav2 지도(chungjang_map)와 Gazebo 월드(chungjang.sdf)를 만든다.

사용법: python3 gen_street.py [--preview 그림.png]
- 자료: osm_chungjang.json (© OpenStreetMap contributors, ODbL 1.0. Overpass로 받은 건물·길). 없으면 다시 받는다
- 보행자 길(highway=pedestrian, 충장로) 중심선 가운데 SEGMENT m를 잘라, 구간 시작이 월드 원점·거리 방향이 +x가 되게 돌린다
- 거리 양옆 HALF_WIDTH m 안의 건물을 세운다. OSM에 층수가 있으면 층수 x 3.2 m, 없으면 3~5층(건물 번호로 정함)
- OSM 건물 외곽선 사이에 생긴 좁은 틈(GAP_CLOSE m 미만)은 메운다. 실제로는 붙은 건물을 조금 떨어지게 그린 경우가 많다
- OSM에 길로 등록된 골목은 폭 ALLEY_WIDTH m까지 넓힌다. 외곽선이 처마·보도 끝까지 그려져 실제보다 좁게 나온다
- 구간 바깥 경계는 낮은 울타리로 막는다 (옆 골목은 경계에서 끝남). 걷는 사람이 거리를 양방향으로 다닌다
"""
import json
import math
import os
import re
import sys
import urllib.parse
import urllib.request

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SIM = os.path.join(HERE, '..', '..')
WORLD_DIR = os.path.join(SIM, 'worlds')
MODEL_DIR = os.path.join(SIM, 'models', 'chungjang_terrain')
MAP_DIR = os.path.join(SIM, '..', 'limbo_navigation', 'maps')
NAME = 'chungjang'
OSM = os.path.join(HERE, 'osm_chungjang.json')
OSM_QUERY = '[out:json][timeout:90];(way["building"](35.1460,126.9135,35.1505,126.9195);way["highway"](35.1460,126.9135,35.1505,126.9195););out geom;'

SEGMENT = 200.0        # 거리 가운데 몇 m를 쓸지
HALF_WIDTH = 40.0      # 거리 양옆으로 몇 m까지 건물을 세울지
BEFORE = 5.0           # 구간 앞뒤 여유 (m). 로봇이 구간 시작점 뒤로 조금 빠질 수 있게
RES = 0.05
GAP_CLOSE = 1.2        # 이보다 좁은 건물 사이 틈은 메운다 (m)
ALLEY_WIDTH = 3.0      # 골목 최소 폭 (m)
FENCE_HEIGHT = 1.2
FENCE_THICK = 0.2
LEVEL_HEIGHT = 3.2
COLORS = ['0.78 0.74 0.68 1', '0.70 0.72 0.76 1', '0.82 0.80 0.74 1', '0.66 0.62 0.58 1']   # 건물 벽 색 몇 가지
GROUND = '0.55 0.55 0.53 1'
FENCE = '0.35 0.38 0.40 1'
SKIN = 'https://fuel.gazebosim.org/1.0/Mingfei/models/actor/tip/files/meshes/walk.dae'

if not os.path.exists(OSM):
    data = urllib.parse.urlencode({'data': OSM_QUERY}).encode()
    req = urllib.request.Request('https://overpass-api.de/api/interpreter', data, {'User-Agent': 'limbo-sim/1.0'})
    open(OSM, 'wb').write(urllib.request.urlopen(req, timeout=180).read())
elements = json.load(open(OSM))['elements']

# --- 위경도 → 미터 (좁은 범위라 평면 근사)
lat0, lon0 = 35.148, 126.916
K = 111320.0
KX = K * math.cos(math.radians(lat0))


def to_m(p):
    return ((p['lon'] - lon0) * KX, (p['lat'] - lat0) * K)


street = next(e for e in elements if e.get('tags', {}).get('highway') == 'pedestrian' and e['tags'].get('name') == '충장로')
line = [to_m(p) for p in street['geometry']]
acc = [0.0]
for a, b in zip(line, line[1:]):
    acc.append(acc[-1] + math.dist(a, b))


def along(s):
    for (a, b), s0, s1 in zip(zip(line, line[1:]), acc, acc[1:]):
        if s <= s1:
            f = (s - s0) / (s1 - s0)
            return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
    return line[-1]


s_start = acc[-1] / 2 - SEGMENT / 2
start, end = along(s_start), along(s_start + SEGMENT)
angle = math.atan2(end[1] - start[1], end[0] - start[0])
cos_a, sin_a = math.cos(-angle), math.sin(-angle)


def to_world(p):
    """미터 좌표 → 월드 (구간 시작이 원점, 거리 방향이 +x)"""
    x, y = p[0] - start[0], p[1] - start[1]
    return (x * cos_a - y * sin_a, x * sin_a + y * cos_a)


# --- 격자: 구간 앞뒤 BEFORE, 양옆 HALF_WIDTH
ox, oy = -BEFORE, -HALF_WIDTH
W, H = int(round((SEGMENT + 2 * BEFORE) / RES)), int(round(2 * HALF_WIDTH / RES))


def px(p):
    return int(round((p[0] - ox) / RES)), int(round(H - (p[1] - oy) / RES))


buildings = []          # (높이, 색 번호, 격자 마스크)
heights = {}
for e in elements:
    tags = e.get('tags', {})
    if 'building' not in tags or len(e.get('geometry', [])) < 3:
        continue
    poly = np.array([px(to_world(to_m(p))) for p in e['geometry']], np.int32)
    if poly[:, 0].max() < 0 or poly[:, 0].min() >= W or poly[:, 1].max() < 0 or poly[:, 1].min() >= H:
        continue
    levels = tags.get('building:levels')
    floors = int(float(levels)) if levels and levels.replace('.', '').isdigit() else 3 + e['id'] % 3
    mask = np.zeros((H, W), np.uint8)
    cv2.fillPoly(mask, [poly], 1)
    if mask.any():
        buildings.append((floors * LEVEL_HEIGHT, e['id'] % len(COLORS), mask > 0))

walls = np.zeros((H, W), bool)
for _, _, m in buildings:
    walls |= m

# 좁은 틈 메우기: 닫힘 연산으로 메운 칸을 가장 가까운 건물에 붙인다 (높이·색을 따라감)
k = int(round(GAP_CLOSE / RES)) | 1
filled = cv2.morphologyEx(walls.astype(np.uint8), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))) > 0
filler = filled & ~walls
label = np.zeros((H, W), np.float32)
for i, (_, _, m) in enumerate(buildings):
    label[m] = i + 1
grown = label.copy()
for _ in range(k):
    grown = np.where(grown > 0, grown, cv2.dilate(grown, np.ones((3, 3), np.uint8)))
buildings = [(h, c, m | (filler & (grown == i + 1))) for i, (h, c, m) in enumerate(buildings)]

# 골목 넓히기: OSM 길(거리 자체 빼고) 가운데 선 양옆 ALLEY_WIDTH/2 안의 건물을 깎는다
alleys = np.zeros((H, W), np.uint8)
alley_count = 0
for e in elements:
    if 'highway' not in e.get('tags', {}) or e['id'] == street['id']:
        continue
    pts = np.array([px(to_world(to_m(p))) for p in e['geometry']], np.int32)
    if pts[:, 0].max() < 0 or pts[:, 0].min() >= W or pts[:, 1].max() < 0 or pts[:, 1].min() >= H:
        continue
    cv2.polylines(alleys, [pts], False, 1, int(round(ALLEY_WIDTH / RES)))
    alley_count += 1
alleys = alleys > 0
buildings = [(h, c, m & ~alleys) for h, c, m in buildings]
walls = np.zeros((H, W), bool)
for _, _, m in buildings:
    walls |= m
print(f'메운 틈 {int(filler.sum() * RES * RES)} m², 넓힌 골목 {alley_count}개')
fence = np.zeros((H, W), bool)
t = int(round(FENCE_THICK / RES))
fence[:t, :] = fence[-t:, :] = True
fence[:, :t] = fence[:, -t:] = True
fence &= ~walls
grid = walls | fence

# --- 검사: 거리 가운데 선의 폭 (로봇 출발점이 비어 있는지 포함)
dist = cv2.distanceTransform((~grid).astype(np.uint8), cv2.DIST_L2, 5) * RES
centre = [to_world(along(s_start + s)) for s in np.arange(0, SEGMENT + 0.1, 1.0)]
widths = [2 * dist[px(p)[1], px(p)[0]] for p in centre if 0 <= px(p)[1] < H and 0 <= px(p)[0] < W]
print(f'구간: 거리 중심선 {s_start:.0f}~{s_start + SEGMENT:.0f} m (전체 {acc[-1]:.0f} m), 방향 {math.degrees(angle):.0f}°, '
      f'건물 {len(buildings)}채, 거리 폭(벽 사이) 최소 {min(widths):.1f} m · 중간 {sorted(widths)[len(widths) // 2]:.1f} m')
if dist[px((0, 0))[1], px((0, 0))[0]] < 1.0:
    raise SystemExit('로봇 출발점(원점)이 벽에 너무 가깝다')

if '--preview' in sys.argv:
    img = np.full((H, W, 3), (200, 200, 195), np.uint8)
    img[walls] = (150, 170, 200)
    img[fence] = (60, 60, 60)
    cv2.polylines(img, [np.array([px(p) for p in centre], np.int32)], False, (0, 0, 220), 3)
    cv2.circle(img, px((0, 0)), 12, (0, 160, 0), -1)
    for gx in range(0, int(SEGMENT) + 1, 10):
        cv2.line(img, px((gx, -HALF_WIDTH)), px((gx, HALF_WIDTH)), (180, 180, 180), 1)
        cv2.putText(img, str(gx), (px((gx, 0))[0] + 3, H - 8), 0, 0.8, (0, 0, 0), 2)
    path = sys.argv[sys.argv.index('--preview') + 1]
    cv2.imwrite(path, cv2.resize(img, (W // 2, H // 2), interpolation=cv2.INTER_AREA))
    print(path)
    sys.exit(0)

# --- Nav2 지도
cv2.imwrite(os.path.join(MAP_DIR, f'{NAME}_map.png'), np.where(grid, 0, 254).astype(np.uint8))
open(os.path.join(MAP_DIR, f'{NAME}_map.yaml'), 'w').write(
    f'image: {NAME}_map.png\nmode: trinary\nresolution: {RES}\n'
    f'origin: [{ox:.3f}, {oy:.3f}, 0.0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n')


# --- 메시: 높이·색이 같은 건물끼리 칸을 상자로 합쳐 OBJ 하나로 (상자를 따로 두면 센서가 하나씩 그려 느려진다)
def merge_boxes(mask):
    boxes, open_runs = [], {}
    for row in range(H + 1):
        runs = set()
        if row < H:
            cols = np.flatnonzero(np.diff(np.concatenate(([0], mask[row].astype(np.int8), [0]))))
            runs = set(zip(cols[::2], cols[1::2]))
        for run in list(open_runs):
            if run not in runs:
                boxes.append((run[0], open_runs.pop(run), run[1], row))
        for run in runs:
            open_runs.setdefault(run, row)
    return boxes


def write_obj(path, mask, z1):
    """법선이 없으면 dartsim이 충돌 메시를 읽다 죽는다"""
    vertices, faces = [], []
    for c0, r0, c1, r1 in merge_boxes(mask):
        x0, x1 = ox + c0 * RES, ox + c1 * RES
        y1, y0 = oy + (H - r0) * RES, oy + (H - r1) * RES
        base = len(vertices)
        for z in (0.0, z1):
            vertices += [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]
        v = [base + k + 1 for k in range(8)]
        faces += [((v[4], v[5], v[6]), 1), ((v[4], v[6], v[7]), 1),
                  ((v[0], v[1], v[5]), 2), ((v[0], v[5], v[4]), 2), ((v[1], v[2], v[6]), 3), ((v[1], v[6], v[5]), 3),
                  ((v[2], v[3], v[7]), 4), ((v[2], v[7], v[6]), 4), ((v[3], v[0], v[4]), 5), ((v[3], v[4], v[7]), 5)]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write('# gen_street.py가 만든다 (© OpenStreetMap contributors, ODbL)\n')
        f.writelines(f'v {x:.3f} {y:.3f} {z:.3f}\n' for x, y, z in vertices)
        f.write('vn 0 0 1\nvn 0 -1 0\nvn 1 0 0\nvn 0 1 0\nvn -1 0 0\n')
        f.writelines(f'f {a}//{k} {b}//{k} {c}//{k}\n' for (a, b, c), k in faces)


links = []
groups = {}
for height, color, mask in buildings:
    key = (height, color)
    groups[key] = groups.get(key, np.zeros((H, W), bool)) | mask
taken = np.zeros((H, W), bool)
for (height, color), mask in sorted(groups.items(), reverse=True):    # 높은 건물부터 (겹치는 칸은 높은 쪽에)
    mask = mask & ~taken
    taken |= mask
    name = f'bldg_{int(height * 10)}_{color}'
    write_obj(os.path.join(MODEL_DIR, 'meshes', f'{name}.obj'), mask, height)
    geom = f'<geometry><mesh><uri>model://chungjang_terrain/meshes/{name}.obj</uri></mesh></geometry>'
    links.append(f'      <collision name="{name}_c">{geom}</collision><visual name="{name}_v">{geom}'
                 f'<material><ambient>{COLORS[color]}</ambient><diffuse>{COLORS[color]}</diffuse></material></visual>')
write_obj(os.path.join(MODEL_DIR, 'meshes', 'fence.obj'), fence, FENCE_HEIGHT)
geom = '<geometry><mesh><uri>model://chungjang_terrain/meshes/fence.obj</uri></mesh></geometry>'
links.append(f'      <collision name="fence_c">{geom}</collision><visual name="fence_v">{geom}'
             f'<material><ambient>{FENCE}</ambient><diffuse>{FENCE}</diffuse></material></visual>')
cx, cy = ox + W * RES / 2, oy + H * RES / 2
links.append(f'      <visual name="ground_v"><pose>{cx:.2f} {cy:.2f} 0.001 0 0 0</pose><geometry><box><size>{W * RES:.2f} {H * RES:.2f} 0.002'
             f'</size></box></geometry><material><ambient>{GROUND}</ambient><diffuse>{GROUND}</diffuse></material></visual>')
open(os.path.join(MODEL_DIR, 'model.config'), 'w').write(
    '<?xml version="1.0"?>\n<model><name>chungjang_terrain</name><version>1.0</version><sdf version="1.9">model.sdf</sdf>\n'
    '  <author><name>limbo team</name></author>\n'
    '  <description>광주 충장로 보행자 거리 가운데 200 m. 건물 자료 © OpenStreetMap contributors (ODbL 1.0)</description></model>\n')
open(os.path.join(MODEL_DIR, 'model.sdf'), 'w').write(f'''<?xml version="1.0"?>
<sdf version="1.9">
  <!-- gen_street.py가 만든다. 직접 고치지 말 것. 건물 자료 © OpenStreetMap contributors (ODbL 1.0) -->
  <model name="chungjang_terrain">
    <static>true</static>
    <link name="link">
{chr(10).join(links)}
    </link>
  </model>
</sdf>
''')


# --- 걷는 사람: 거리 중심선 양옆을 양방향으로 (왕복)
def actor_xml(name, offset, speed, phase, reverse):
    pts = [(p[0], p[1] + offset) for p in centre]
    if reverse:
        pts = pts[::-1]
    pts = pts + pts[-2::-1]
    wps, t = [], 0.0
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        yaw = math.atan2(y1 - y0, x1 - x0)
        wps.append((t, x0, y0, yaw))
        t += math.hypot(x1 - x0, y1 - y0) / speed
    wps.append((t, *pts[-1], wps[-1][3]))
    body = '\n'.join(f'          <waypoint><time>{tt:.2f}</time><pose>{x:.2f} {y:.2f} 1.0 0 0 {yw:.4f}</pose></waypoint>'
                     for tt, x, y, yw in wps)
    return f'''    <actor name="{name}">
      <skin><filename>{SKIN}</filename><scale>1.0</scale></skin>
      <animation name="walk"><filename>{SKIN}</filename><interpolate_x>true</interpolate_x></animation>
      <script><loop>true</loop><delay_start>{phase:.1f}</delay_start><auto_start>true</auto_start>
        <trajectory id="0" type="walk">
{body}
        </trajectory>
      </script>
    </actor>'''


# (이름, 중심선에서 옆으로 m, 속도 m/s, 출발 늦춤 s, 반대 방향)
PEOPLE = [('walker_1', 1.5, 1.1, 0, False), ('walker_2', -1.5, 1.0, 0, True), ('walker_3', 2.5, 0.9, 40, True),
          ('walker_4', -2.5, 1.2, 20, False), ('walker_5', 0.5, 0.8, 60, True), ('walker_6', -0.8, 1.0, 90, False)]
base = open(os.path.join(WORLD_DIR, 'human_test_world.sdf')).read()
base = re.sub(r'<world name="[^"]+">', f'<world name="{NAME}">', base)
head, tail = base.split('</world>')[0], '</world>' + base.split('</world>')[1]
head = re.sub(r'\s*<model name="(?!ground_plane)[^"]*">.*?</model>', '', head, flags=re.S)
head = re.sub(r'\s*<actor .*?</actor>', '', head, flags=re.S)
models = [f'    <include><uri>model://chungjang_terrain</uri><name>{NAME}_terrain</name></include>']
models += [actor_xml(*p) for p in PEOPLE]
open(os.path.join(WORLD_DIR, f'{NAME}.sdf'), 'w').write(
    head + '\n    <!-- 건물 자료 © OpenStreetMap contributors (ODbL 1.0) -->\n' + '\n'.join(models) + '\n  ' + tail)
print(f'{NAME}: 지도 {W}x{H} 칸, 원점 ({ox:.1f},{oy:.1f}), 건물 메시 {len(groups)}개, 걷는 사람 {len(PEOPLE)}명')
