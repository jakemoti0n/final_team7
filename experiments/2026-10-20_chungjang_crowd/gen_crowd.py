"""충장로 200 m 거리에 소셜 포스 사람 N명을 놓는 월드(chungjang_crowd.sdf)와 movers json을 만든다.

사용법: python3 gen_crowd.py [N=50] [seed=1]
- 바탕: 설치된 chungjang.sdf(생성기 산출물). 시간표대로 걷는 기존 walker_1~6은 뺀다(소셜 포스 사람만 쓰려고).
- 사람: 거리(x 5~195, y -1.5~3.5, 지도에서 빈 띠) 위 두 점을 왕복. 유형은 yield 70 %, no_yield 25 %, approach 5 %.
- 산출물은 설치 폴더에만 쓴다(저장소에 넣지 않음, 피팅 방지용 기록은 README).
"""
import json, os, random, re, sys
N = int(sys.argv[1]) if len(sys.argv) > 1 else 50
random.seed(int(sys.argv[2]) if len(sys.argv) > 2 else 1)
W = os.path.expanduser('~/limbo/limbo/install/limbo_simulation/share/limbo_simulation/worlds')
base = open(os.path.join(W, 'chungjang.sdf')).read()
base = re.sub(r'\s*<actor name="walker_\d+">.*?</actor>', '', base, flags=re.S)
# gz 토픽(/world/<이름>/clock 등)은 sdf의 world 이름을 쓰므로 json의 world와 같아야 moving_obstacles가 시계를 받는다
base = base.replace('<world name="chungjang">', '<world name="chungjang_crowd">', 1)
assert '<world name="chungjang_crowd">' in base, 'world 이름 치환 실패'
actor = '''    <actor name="{name}">
      <skin><filename>https://fuel.gazebosim.org/1.0/Mingfei/models/actor/tip/files/meshes/walk.dae</filename><scale>1.0</scale></skin>
      <animation name="walk"><filename>https://fuel.gazebosim.org/1.0/Mingfei/models/actor/tip/files/meshes/walk.dae</filename><interpolate_x>false</interpolate_x></animation>
      <script><loop>true</loop><auto_start>true</auto_start></script>
    </actor>
'''
people = []
for i in range(1, N + 1):
    r = random.random()
    kind = 'yield' if r < 0.70 else 'no_yield' if r < 0.95 else 'approach'
    xa = random.uniform(5.0, 195.0); xb = min(195.0, max(5.0, xa + random.choice([-1, 1]) * random.uniform(25.0, 90.0)))
    ya, yb = random.uniform(-1.5, 3.5), random.uniform(-1.5, 3.5)
    p = {'name': f'crowd_{i:02d}', 'type': kind, 'speed': round(random.uniform(0.6, 1.2), 2),
         'waypoints': [[round(xa, 1), round(ya, 1)], [round(xb, 1), round(yb, 1)]], 'loop': True}
    if kind == 'approach':
        p['wait'] = 8.0
    people.append(p)
# 소셜 포스 사람은 시간표 없이 moving_obstacles.py가 /limbo/actor_poses로 옮기므로 actor_pose_control 플러그인이 있어야 한다
social = open(os.path.join(W, 'aischool_2f_social.sdf')).read()
plugin = re.search(r'\n\s*<!-- 소셜 포스 사람.*?</plugin>\n', social, re.S).group(0)
sdf = base.replace('  </world>', plugin + ''.join(actor.format(name=p['name']) for p in people) + '  </world>')
open(os.path.join(W, 'chungjang_crowd.sdf'), 'w').write(sdf)
json.dump({'world': 'chungjang_crowd', 'map': 'chungjang_map', 'robot': 'limbo', 'people': people},
          open(os.path.join(W, 'chungjang_crowd_movers.json'), 'w'), indent=1, ensure_ascii=False)
kinds = {k: sum(1 for p in people if p['type'] == k) for k in ('yield', 'no_yield', 'approach')}
print(f'사람 {len(people)}명 {kinds}, actor {sdf.count("<actor ")}개, 파일 {W}/chungjang_crowd.sdf·_movers.json')
