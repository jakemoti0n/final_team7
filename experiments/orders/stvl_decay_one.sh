#!/usr/bin/env bash
# 사용법: stvl_decay_one.sh <초> <라벨접두>   — 전역 costmap STVL voxel_decay를 <초>로 두고 ① 한 명 복도(people2) ② 상자 구간(box) 각 1회. 끝나면 설정 원복
# 예: stvl_decay_one.sh 3 d3  → trial_d3_single.csv, trial_d3_box.csv
set -u
T=~/limbo/tools/sim_trials; R=~/limbo; NAV=$R/limbo/src/limbo_navigation/config/nav2_params.yaml
W=$R/limbo/install/limbo_simulation/share/limbo_simulation/worlds
git -C $R checkout -- $NAV
python3 - "$1" <<'PY'
import sys, re
p = '/home/kim/limbo/limbo/src/limbo_navigation/config/nav2_params.yaml'.replace('/home/kim', __import__('os').path.expanduser('~'))
s = open(p).read(); g = s.index('\nglobal_costmap:')
head, tail = s[:g], s[g:]
tail, n = re.subn(r'(        voxel_decay: )\d+\.\d+', r'\g<1>' + str(float(sys.argv[1])), tail, count=1); assert n == 1
open(p, 'w').write(head + tail); print('전역 voxel_decay →', sys.argv[1])
PY
python3 - <<'PY'
import re, os
W = os.path.expanduser('~/limbo/limbo/install/limbo_simulation/share/limbo_simulation/worlds/')
w = open(W + 'aischool_2f_scenarios.sdf').read()
w2, n = re.subn(r'\s*<actor name="pair_left">.*?</actor>', '', w, count=1, flags=re.S); assert n == 1
open(W + 'zz_single.sdf', 'w').write(w2.replace('<world name="aischool_2f_scenarios">', '<world name="zz_single">'))
PY
echo "=== 한 명 복도 $(date +%H:%M) 커밋 $(git -C $R rev-parse --short HEAD)"
GOAL_TIMEOUT=60 WORLD=zz_single MAP=aischool_2f_map $T/trial.sh $2_single people2 | tail -1
echo "=== 상자 구간 $(date +%H:%M)"
$T/trial.sh $2_box box | tail -1
git -C $R checkout -- $NAV; rm -f $W/zz_single.sdf
echo "=== 끝 $(date +%H:%M)"
