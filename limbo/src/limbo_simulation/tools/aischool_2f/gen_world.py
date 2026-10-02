"""walls.png(벽 마스크)로 Nav2 지도(pgm/yaml)와 Gazebo 월드(sdf)를 만든다."""
import cv2, numpy as np, re, os

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD_DIR = os.path.join(HERE, '..', '..', 'worlds')
MAP_DIR = os.path.join(HERE, '..', '..', '..', 'limbo_navigation', 'maps')

METERS_PER_PX = 6.1 / 190      # 교실 깊이 실측 6.1m = 도면 190px
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
open(os.path.join(WORLD_DIR, f'{NAME}.sdf'), 'w').write(kept + '\n' + walls_model + '\n  ' + rest)
print(f'map {cells_w}x{cells_h} cells, origin ({ox:.2f},{oy:.2f}), wall boxes {len(boxes)}, building {W*METERS_PER_PX:.1f}x{H*METERS_PER_PX:.1f} m')

# --- 걷는 사람: 홀과 복도를 오가는 경로 (도면 px 좌표). 모서리에서는 제자리에서 방향만 바꾼다
WALK_SPEED = 1.0   # m/s
TURN_TIME = 0.5    # sec
ACTOR_PATHS = {
    'person_1': [(40, 518), (740, 518)],                                  # 아래 복도 왕복
    'person_2': [(220, 470), (548, 470), (548, 222), (220, 222), (220, 470)],  # 코어 둘레 순환
    'person_3': [(300, 452), (500, 452)],                                 # 홀 가로지르기
}
SKIN = 'https://fuel.gazebosim.org/1.0/Mingfei/models/actor/tip/files/meshes/walk.dae'
import math
def actor_xml(name, path_px):
    pts = [px_to_world(u, v) for u, v in path_px]
    if pts[0] != pts[-1]:
        pts = pts + pts[-2::-1]          # 왕복 경로
    waypoints, t = [], 0.0
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        yaw = math.atan2(y1 - y0, x1 - x0)
        if i > 0:
            t += TURN_TIME
        waypoints.append((t, x0, y0, yaw))
        t += math.hypot(x1 - x0, y1 - y0) / WALK_SPEED
        waypoints.append((t, x1, y1, yaw))
    wp = '\n'.join(f'          <waypoint><time>{tt:.2f}</time><pose>{x:.2f} {y:.2f} 1.0 0 0 {yw:.4f}</pose></waypoint>'
                   for tt, x, y, yw in waypoints)
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

sdf = open(os.path.join(WORLD_DIR, f'{NAME}.sdf')).read()
actors = '\n'.join(actor_xml(n, p) for n, p in ACTOR_PATHS.items())
sdf = sdf.replace('\n  </world>', '\n' + actors + '\n  </world>', 1)
open(os.path.join(WORLD_DIR, f'{NAME}.sdf'), 'w').write(sdf)
print('actors', list(ACTOR_PATHS))
