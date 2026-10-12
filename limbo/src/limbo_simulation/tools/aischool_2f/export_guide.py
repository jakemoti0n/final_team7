"""지금 지도를 사람이 보고 고칠 수 있는 그림 두 장으로 내보낸다.

사용법: python3 export_guide.py [출력 폴더, 기본 ~/map_edit]
  map_edit.png  : 검정 = 벽. 그림판으로 고친 뒤 이 폴더의 walls_edited.png로 덮어쓰고 gen_world.py를 다시 돌린다
  map_guide.png : 방 이름, 문(빨간 원), 순찰 waypoint(초록), 로봇 시작점(파랑)을 표시한 참고용
1 m = 80 px (지도 한 칸 5 cm = 4 px). 그림 크기를 바꾸면 gen_world.py가 거부한다.
"""
import os, re, sys
import cv2, numpy as np, yaml
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', '..', '..')
OUT = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else '~/map_edit')
SCALE = 4
FONT_PATH = '/usr/share/fonts/truetype/nanum/NanumGothic.ttf'

ROOMS = {'207 교실-6': (-9.6, 14.6), '206 교실-5': (10.3, 14.6), '211·212 화장실': (-0.4, 14.8),
         '208 교실-7': (-10.9, 4.5), '205 교실-4': (10.5, 4.5), '201 홀': (0.0, 1.1),
         '계단·엘리베이터(막음)': (-0.6, 6.0), '202 교실-1': (-9.8, -5.4), '209 상담실': (0.3, -3.5),
         '203 휴게실': (6.0, -5.8), '204 교실-3': (10.9, -5.4)}

os.makedirs(OUT, exist_ok=True)
meta = open(os.path.join(SRC, 'limbo_navigation', 'maps', 'aischool_2f_map.yaml')).read()
ox, oy = map(float, re.search(r'origin: \[([-\d.]+), ([-\d.]+)', meta).groups())
grid = cv2.imread(os.path.join(SRC, 'limbo_navigation', 'maps', 'aischool_2f_map.pgm'), 0) < 100
H, W = grid.shape
wall = cv2.resize(grid.astype(np.uint8), (W * SCALE, H * SCALE), interpolation=cv2.INTER_NEAREST) > 0
font = ImageFont.truetype(FONT_PATH, 22) if os.path.exists(FONT_PATH) else ImageFont.load_default()


def px(x, y):
    return int(round((x - ox) / 0.05 * SCALE)), int(round((H - (y - oy) / 0.05) * SCALE))


def gridded():
    """1 m 격자(옅은 회색)를 그린 흰 바탕에 벽을 얹는다."""
    im = Image.new('RGB', (W * SCALE, H * SCALE), 'white')
    d = ImageDraw.Draw(im)
    for gx in range(int(np.ceil(ox)), int(ox + W * 0.05) + 1):
        d.line([(px(gx, 0)[0], 0), (px(gx, 0)[0], H * SCALE)], fill=(225, 225, 225))
    for gy in range(int(np.ceil(oy)), int(oy + H * 0.05) + 1):
        d.line([(0, px(0, gy)[1]), (W * SCALE, px(0, gy)[1])], fill=(225, 225, 225))
    a = np.array(im)
    a[wall] = 0
    im = Image.fromarray(a)
    return im, ImageDraw.Draw(im)


def axis_labels(d, color):
    for gx in range(int(np.ceil(ox)), int(ox + W * 0.05) + 1, 2):
        d.text((px(gx, 0)[0] + 3, 6), f'x={gx}', fill=color, font=font)
    for gy in range(int(np.ceil(oy)), int(oy + H * 0.05) + 1, 2):
        d.text((6, px(0, gy)[1] - 24), f'y={gy}', fill=color, font=font)


# 수정용: 벽 + 격자 + 옅은 좌표
im, d = gridded()
axis_labels(d, (170, 170, 170))
im.save(os.path.join(OUT, 'map_edit.png'))

# 참고용
im, d = gridded()
axis_labels(d, (200, 0, 0))
for name, (x, y) in ROOMS.items():
    X, Y = px(x, y)
    w = d.textlength(name, font=font)
    d.rectangle([X - w / 2 - 4, Y - 14, X + w / 2 + 4, Y + 14], fill=(255, 255, 210))
    d.text((X - w / 2, Y - 12), name, fill=(90, 60, 0), font=font)
gen = open(os.path.join(HERE, 'gen_world.py')).read()
start = gen.index('DOOR_CENTERS = [') + len('DOOR_CENTERS = ')
doors = eval(gen[start:gen.index(']\n', start) + 1])
for name, x, y, _ in doors:
    X, Y = px(x, y)
    d.ellipse([X - 30, Y - 30, X + 30, Y + 30], outline=(230, 0, 0), width=4)
    d.text((X + 32, Y - 30), f'문 {name}', fill=(230, 0, 0), font=font)
waypoints = yaml.safe_load(open(os.path.join(SRC, 'limbo_patrol', 'config', 'aischool_waypoints.yaml')))['waypoints']
points = [px(w['x'], w['y']) for w in waypoints]
for i, w in enumerate(waypoints):
    if i:
        d.line([points[i - 1], points[i]], fill=(0, 170, 0), width=3)
    X, Y = points[i]
    d.ellipse([X - 12, Y - 12, X + 12, Y + 12], fill=(0, 170, 0))
    d.text((X + 14, Y - 30), w['name'], fill=(0, 120, 0), font=font)
X, Y = px(0, 0)
d.ellipse([X - 10, Y - 10, X + 10, Y + 10], outline=(0, 0, 200), width=4)
d.text((X + 14, Y + 8), '로봇 시작 (0,0)', fill=(0, 0, 200), font=font)
im.save(os.path.join(OUT, 'map_guide.png'))
print(f'{OUT}/map_edit.png, map_guide.png ({W * SCALE}x{H * SCALE}, 1 m = {int(SCALE / 0.05)} px)')
