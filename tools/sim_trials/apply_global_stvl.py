"""nav2_params.yaml의 전역 costmap에 로컬과 같은 STVL 층을 넣는다 (시험용). 사용법: apply_global_stvl.py <기억 초>
되돌리기: cd ~/limbo && git checkout limbo/src/limbo_navigation/config/nav2_params.yaml"""
import os, sys
p = os.path.expanduser('~/limbo/limbo/src/limbo_navigation/config/nav2_params.yaml'); s = open(p).read()
lc = s.index('local_costmap:'); gc = s.index('\nglobal_costmap:')
local = s[lc:gc]
block = local[local.index('      stvl_layer:\n'):local.index('      static_layer:\n')].rstrip() + '\n'
block = block.replace('        voxel_decay: 1.0\n', f'        voxel_decay: {float(sys.argv[1])}\n').replace(
    '        publish_voxel_map: true\n', '        publish_voxel_map: false\n')
g = s[gc:]
old = '      plugins: ["static_layer", "inflation_layer"]\n'
assert g.count(old) == 1, '이미 적용됐거나 형식이 다름'
g = g.replace(old, '      plugins: ["static_layer", "stvl_layer", "inflation_layer"]\n', 1)
i = g.index('      inflation_layer:\n')
open(p, 'w').write(s[:gc] + g[:i] + block + g[i:])
print('전역 STVL 기억', sys.argv[1], '초 적용')
