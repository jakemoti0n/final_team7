#!/usr/bin/env bash
# 사용법: run.sh   — 전역 costmap STVL voxel_decay 3초·15초로 한 명 복도(people2, 시간표 사람) 각 3회. plan_changes 비교. 끝나면 설정 원복
set +u
T=~/limbo/tools/sim_trials; R=~/limbo; NAV=$R/limbo/src/limbo_navigation/config/nav2_params.yaml
W=$R/limbo/install/limbo_simulation/share/limbo_simulation/worlds
python3 - <<'PY'
import re, os
W = os.path.expanduser('~/limbo/limbo/install/limbo_simulation/share/limbo_simulation/worlds/')
w = open(W + 'aischool_2f_scenarios.sdf').read()
w2, n = re.subn(r'\s*<actor name="pair_left">.*?</actor>', '', w, count=1, flags=re.S); assert n == 1
open(W + 'zz_single.sdf', 'w').write(w2.replace('<world name="aischool_2f_scenarios">', '<world name="zz_single">'))
PY
git -C $R checkout -- $NAV
for decay in 3 15; do
  python3 - "$decay" <<'PY'
import sys, re, os
p = os.path.expanduser('~/limbo/limbo/src/limbo_navigation/config/nav2_params.yaml')
s = open(p).read(); g = s.index('\nglobal_costmap:'); head, tail = s[:g], s[g:]
tail, n = re.subn(r'(        voxel_decay: )\d+\.\d+', r'\g<1>' + str(float(sys.argv[1])), tail, count=1); assert n == 1
open(p, 'w').write(head + tail); print('전역 voxel_decay →', sys.argv[1])
PY
  for i in 1 2 3; do
    echo "=== d${decay} 회차 $i $(date +%H:%M) 커밋 $(git -C $R rev-parse --short HEAD)"
    GOAL_TIMEOUT=90 WORLD=zz_single MAP=aischool_2f_map $T/trial.sh pc_d${decay}_$i people2 | tail -1
  done
  git -C $R checkout -- $NAV
done
rm -f $W/zz_single.sdf
echo "=== 끝 $(date +%H:%M)"
