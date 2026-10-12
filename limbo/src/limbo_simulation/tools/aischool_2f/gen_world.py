"""walls.png(벽 마스크)로 Nav2 지도(pgm/yaml)와 Gazebo 월드(sdf)를 만든다."""
import cv2, numpy as np, re, os

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD_DIR = os.path.join(HERE, '..', '..', 'worlds')
MAP_DIR = os.path.join(HERE, '..', '..', '..', 'limbo_navigation', 'maps')

# 축척: 도면의 교실 문 여닫이 호 반지름 약 24 px = 실제 문 0.9 m (법정 유효폭).
# 예전에는 교실 깊이 6.1 m(대충 잰 값) = 190 px로 맞췄는데, 그러면 문이 0.75~0.8 m로 좁게 나왔다
METERS_PER_PX = 0.9 / 24
MAP_RESOLUTION = 0.05           # m/cell
WALL_HEIGHT = 2.5               # m
SPAWN_PX = (400, 490)           # 로봇 시작 위치 = 월드 원점 (홀 201 아래쪽)
NAME = 'aischool_2f'

walls = cv2.imread('walls.png', 0) > 0
H, W = walls.shape

def px_to_world(u, v):
    return ((u - SPAWN_PX[0]) * METERS_PER_PX, (SPAWN_PX[1] - v) * METERS_PER_PX)

# --- Nav2 지도: 0.05m 격자로 줄인다 (아래가 +y 이므로 그대로 저장하면 map_server가 맞게 읽음)
cells_w = int(round(W * METERS_PER_PX / MAP_RESOLUTION)); cells_h = int(round(H * METERS_PER_PX / MAP_RESOLUTION))
grid = cv2.resize(walls.astype(np.uint8) * 255, (cells_w, cells_h), interpolation=cv2.INTER_AREA) > 60

# 사람이 그림판으로 고친 벽 그림이 있으면 그걸 쓴다 (검정 = 벽, 1 m = 80 px, 지도 격자의 4배 크기).
# 도면 사진에서 자동으로 딴 벽보다 우선한다. 다시 고칠 때도 이 파일을 고친다
EDITED = os.path.join(HERE, 'walls_edited.png')
if os.path.exists(EDITED):
    edited = cv2.imread(EDITED, 0)
    if edited.shape != (cells_h * 4, cells_w * 4):
        raise SystemExit(f'walls_edited.png 크기가 {edited.shape[::-1]}인데 {(cells_w * 4, cells_h * 4)}여야 한다 (자르거나 늘리지 말 것)')
    grid = cv2.resize(edited, (cells_w, cells_h), interpolation=cv2.INTER_AREA) < 128
    print('walls_edited.png 사용')

# --- 문 폭을 정확히 0.9 m로 맞춘다. 사진에서 딴 벽 선과 격자 반올림 때문에 문마다 0.85~1.05 m로 달라져서,
# 최종 격자에서 문 가운데 0.9 m만 비우고 그 옆 남는 틈은 벽으로 채운다
DOOR_WIDTH = 0.9
# (이름, 월드 x, y m, 벽 방향) — 'h': 가로 벽(문 폭이 x 방향), 'v': 세로 벽(문 폭이 y 방향)
DOOR_CENTERS = [
    ('207 교실-6', -4.72, 11.14, 'h'), ('206 교실-5', 3.60, 11.14, 'h'),
    ('211 화장실(남)', -2.65, 11.14, 'h'), ('212 화장실(여)', 1.36, 11.14, 'h'),
    ('202 교실-1', -5.33, -1.99, 'h'), ('209 상담실', -0.59, -1.99, 'h'), ('203 휴게실', 4.05, -1.99, 'h'), ('204 교실-3', 12.41, -1.99, 'h'),
    ('209 안쪽 통로', -1.95, -2.55, 'v'),
    ('208 교실-7 위', -7.84, 8.17, 'v'), ('205 교실-4 위', 6.56, 8.10, 'v'),
    ('208 교실-7 아래', -7.72, 0.22, 'v'), ('205 교실-4 아래', 6.56, 0.22, 'v'),
]
DOOR_CELLS = int(round(DOOR_WIDTH / MAP_RESOLUTION))
SEARCH = int(round(1.0 / MAP_RESOLUTION))       # 문 양옆 1 m 안에서 벽 줄을 찾는다
for name, x, y, wall_dir in DOOR_CENTERS:
    col = int(round((x / METERS_PER_PX + SPAWN_PX[0]) * METERS_PER_PX / MAP_RESOLUTION))
    row = int(round((SPAWN_PX[1] - y / METERS_PER_PX) * METERS_PER_PX / MAP_RESOLUTION))
    # 가로 벽이면 그대로, 세로 벽이면 격자를 뒤집어 같은 코드로 처리한다
    g = grid if wall_dir == 'h' else grid.T
    if wall_dir == 'v':
        col, row = row, col
    left, right = col - DOOR_CELLS // 2, col - DOOR_CELLS // 2 + DOOR_CELLS
    # 벽 두께 = 문 양쪽 1 m 떨어진 곳에서 벽인 줄들
    band = [r for r in range(row - SEARCH // 2, row + SEARCH // 2)
            if g[r, left - SEARCH:left].any() and g[r, right:right + SEARCH].any()]
    if not band:
        raise SystemExit(f'{name}: 문 양옆에서 벽을 못 찾음 (좌표 확인)')
    for r in range(min(band), max(band) + 1):
        g[r, left:right] = False
        # 문 바깥으로 벽이 시작될 때까지 남는 틈을 벽으로 채운다
        c = left - 1
        while c > left - SEARCH and not g[r, c]:
            g[r, c] = True; c -= 1
        c = right
        while c < right + SEARCH and not g[r, c]:
            g[r, c] = True; c += 1
pgm = np.where(grid, 0, 254).astype(np.uint8)
cv2.imwrite(os.path.join(MAP_DIR, f'{NAME}_map.pgm'), pgm)
ox, oy = px_to_world(0, H)      # 지도 왼쪽 아래 모서리
open(os.path.join(MAP_DIR, f'{NAME}_map.yaml'), 'w').write(
    f'image: {NAME}_map.pgm\nmode: trinary\nresolution: {MAP_RESOLUTION}\n'
    f'origin: [{ox:.3f}, {oy:.3f}, 0.0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n')

# --- 벽 박스: 지도 격자의 벽 칸을 행 단위로 이은 뒤 위아래로 같은 구간끼리 합친다
boxes = []
open_runs = {}
for row in range(cells_h + 1):
    runs = set()
    if row < cells_h:
        c = 0
        while c < cells_w:
            if grid[row, c]:
                s = c
                while c < cells_w and grid[row, c]: c += 1
                runs.add((s, c))
            else:
                c += 1
    for run in list(open_runs):
        if run not in runs:
            boxes.append((run[0], open_runs.pop(run), run[1], row))
    for run in runs:
        open_runs.setdefault(run, row)

def cell_to_world(cx, cy):
    return (ox + cx * MAP_RESOLUTION, oy + (cells_h - cy) * MAP_RESOLUTION)

links = []
for i, (c0, r0, c1, r1) in enumerate(boxes):
    (x0, y1), (x1, y0) = cell_to_world(c0, r0), cell_to_world(c1, r1)
    sx, sy = x1 - x0, y1 - y0; cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    geom = f'<geometry><box><size>{sx:.3f} {sy:.3f} {WALL_HEIGHT}</size></box></geometry>'
    links.append(f'''      <collision name="w{i}_c"><pose>{cx:.3f} {cy:.3f} {WALL_HEIGHT/2} 0 0 0</pose>{geom}</collision>
      <visual name="w{i}_v"><pose>{cx:.3f} {cy:.3f} {WALL_HEIGHT/2} 0 0 0</pose>{geom}
        <material><ambient>0.85 0.85 0.82 1</ambient><diffuse>0.85 0.85 0.82 1</diffuse></material></visual>''')

walls_model = f'''    <model name="{NAME}_walls">
      <static>true</static>
      <link name="walls">
{chr(10).join(links)}
      </link>
    </model>'''

# --- 기존 월드에서 물리·플러그인·조명·바닥은 그대로 가져오고, 벽 모델과 사람 경로만 바꾼다
base = open(os.path.join(WORLD_DIR, 'human_test_world.sdf')).read()
base = re.sub(r'<world name="[^"]+">', f'<world name="{NAME}">', base)
head, rest = base.split('</world>')[0], '</world>' + base.split('</world>')[1]
# human_test_world의 기존 모델(벽 등)은 빼고, 지면/조명/플러그인만 남긴다
kept = re.sub(r'\s*<model name="(?!ground_plane)[^"]*">.*?</model>', '', head, flags=re.S)
kept = re.sub(r'\s*<actor .*?</actor>', '', kept, flags=re.S)
walls_world = kept + '\n' + walls_model + '\n  ' + rest
print(f'map {cells_w}x{cells_h} cells, origin ({ox:.2f},{oy:.2f}), wall boxes {len(boxes)}, building {W*METERS_PER_PX:.1f}x{H*METERS_PER_PX:.1f} m')

# --- 걷는 사람 (도면 px 좌표). 모서리에서는 제자리에서 방향만 바꾼다
# 경로 점은 (u, v) 또는 (u, v, 멈춤 초). 시작과 끝이 다르면 왕복한다
WALK_SPEED = 1.0   # m/s
TURN_TIME = 0.5    # sec
ACTOR_PATHS = {
    'person_1': [(40, 518), (740, 518)],                                  # 아래 복도 왕복
    'person_2': [(220, 470), (548, 470), (548, 222), (220, 222), (220, 470)],  # 코어 둘레 순환
    'person_3': [(300, 452), (500, 452)],                                 # 홀 가로지르기
}

# 시나리오 월드: 장소마다 한 가지 상황. 로봇을 그 장소로 보내 시험한다 (이름: (속도 m/s, 경로))
# Gazebo actor는 정해진 시간표대로만 움직여 로봇에 반응하지 않는다 (충돌 판정도 없음)
# 로봇은 (400, 490)에서 동쪽(+u)을 보고 시작한다
SCENARIO_PATHS = {
    # 오른쪽 아래 복도(폭 1m) 가운데로 오다가 로봇 시작 위치 1.6m 앞(접근 의도 판단 범위 0.3~2.0m)에서 4초 멈췄다 돌아간다
    'approach_stop': (1.0, [(720, 521), (560, 521), (450, 500, 4.0)]),
    # 왼쪽 복도(폭 1.6m) 서쪽 벽에 붙어 서 있다. 동쪽으로 약 1m가 남는다
    'standing': (0.0, [(207, 340)]),
    # 홀에서 동쪽으로 걷다가 오른쪽 복도로 90° 꺾어 북쪽으로 간다
    'turn_corner': (1.0, [(440, 455), (547, 455), (547, 300)]),
    # 위쪽 복도(폭 1.5m)를 0.6m 간격으로 나란히 천천히 걷는다. u=475 돌출부 앞에서 돌아선다
    'pair_left': (0.7, [(240, 210), (450, 210)]),
    'pair_right': (0.7, [(240, 229), (450, 229)]),
    # 왼쪽 아래 복도(폭 1m)를 빨리 걷는다
    'fast': (1.6, [(40, 521), (330, 521)]),
}

# 지도에 없는 낮은 장애물 (이름: (u, v, 가로 m, 세로 m, 높이 m)). 홀 ↔ 왼쪽 복도 경로 위에 둔다.
# MID-360은 아래쪽 −7°라 가까운 낮은 물체를 못 보고 카메라도 1m 안쪽 바닥은 못 봐서,
# 멀리서 본 것을 다가가는 동안 기억하는지 시험한다. 이름이 obstacle_로 시작하면 limbo_evaluation이 거리를 잰다
SCENARIO_OBSTACLES = {
    'obstacle_low_10cm': (331, 445, 0.3, 0.3, 0.10),
    'obstacle_low_30cm': (275, 440, 0.3, 0.3, 0.30),
}
OBSTACLE_COLOR = '0.85 0.35 0.1 1'

SKIN = 'https://fuel.gazebosim.org/1.0/Mingfei/models/actor/tip/files/meshes/walk.dae'
STAND_LOOP_TIME = 10.0   # sec, 서 있는 사람의 궤적 길이 (Gazebo 궤적에는 점이 두 개 이상 필요)
import math


def waypoints_of(path_px, speed):
    stops = [p[2] if len(p) > 2 else 0.0 for p in path_px]
    pts = [px_to_world(p[0], p[1]) for p in path_px]
    if len(pts) == 1:
        # 멈춰 있는 걷기 애니메이션은 걷던 자세 그대로 서 있다
        x, y = pts[0]
        return [(0.0, x, y, 0.0), (STAND_LOOP_TIME, x, y, 0.0)]
    if pts[0] != pts[-1]:
        pts = pts + pts[-2::-1]          # 왕복 경로
        stops = stops + stops[-2::-1]
    waypoints, t = [], 0.0
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        yaw = math.atan2(y1 - y0, x1 - x0)
        if i > 0:
            t += TURN_TIME
        waypoints.append((t, x0, y0, yaw))
        t += math.hypot(x1 - x0, y1 - y0) / speed
        waypoints.append((t, x1, y1, yaw))
        if stops[i + 1] > 0:
            t += stops[i + 1]
            waypoints.append((t, x1, y1, yaw))
    return waypoints


def actor_xml(name, path_px, speed=WALK_SPEED):
    wp = '\n'.join(f'          <waypoint><time>{tt:.2f}</time><pose>{x:.2f} {y:.2f} 1.0 0 0 {yw:.4f}</pose></waypoint>'
                   for tt, x, y, yw in waypoints_of(path_px, speed))
    return f'''    <actor name="{name}">
      <skin><filename>{SKIN}</filename><scale>1.0</scale></skin>
      <animation name="walk"><filename>{SKIN}</filename><interpolate_x>true</interpolate_x></animation>
      <script>
        <loop>true</loop><delay_start>0.0</delay_start><auto_start>true</auto_start>
        <trajectory id="0" type="walk">
{wp}
        </trajectory>
      </script>
    </actor>'''


def obstacle_xml(name, u, v, size_x, size_y, height):
    x, y = px_to_world(u, v)
    box = f'<geometry><box><size>{size_x} {size_y} {height}</size></box></geometry>'
    return f'''    <model name="{name}">
      <static>true</static>
      <pose>{x:.2f} {y:.2f} {height / 2:.3f} 0 0 0</pose>
      <link name="link">
        <collision name="collision">{box}</collision>
        <visual name="visual">{box}
          <material><ambient>{OBSTACLE_COLOR}</ambient><diffuse>{OBSTACLE_COLOR}</diffuse></material></visual>
      </link>
    </model>'''


def write_world(world_name, models):
    sdf = re.sub(r'<world name="[^"]+">', f'<world name="{world_name}">', walls_world)
    sdf = sdf.replace('\n  </world>', '\n' + '\n'.join(models) + '\n  </world>', 1)
    open(os.path.join(WORLD_DIR, f'{world_name}.sdf'), 'w').write(sdf)
    print(world_name, 'models', len(models))


write_world(NAME, [actor_xml(n, p) for n, p in ACTOR_PATHS.items()])
write_world(f'{NAME}_scenarios',
            [actor_xml(n, p, v) for n, (v, p) in SCENARIO_PATHS.items()]
            + [obstacle_xml(n, *spec) for n, spec in SCENARIO_OBSTACLES.items()])
