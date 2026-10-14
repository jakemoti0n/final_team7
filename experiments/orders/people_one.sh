#!/usr/bin/env bash
# 사용법: people_one.sh <라벨>   — 한 명 복도(people2, pair_left 뺀 월드) 1회 + 상자 구간(box) 1회. 설정은 건드리지 않는다
# 결과: ~/limbo_bags/sim_trials/logs/trial_<라벨>_single.csv, trial_<라벨>_box.csv
set -u
T=~/limbo/tools/sim_trials; R=~/limbo
W=$R/limbo/install/limbo_simulation/share/limbo_simulation/worlds
python3 - <<'PY'
import re, os
W = os.path.expanduser('~/limbo/limbo/install/limbo_simulation/share/limbo_simulation/worlds/')
w = open(W + 'aischool_2f_scenarios.sdf').read()
w2, n = re.subn(r'\s*<actor name="pair_left">.*?</actor>', '', w, count=1, flags=re.S); assert n == 1
open(W + 'zz_single.sdf', 'w').write(w2.replace('<world name="aischool_2f_scenarios">', '<world name="zz_single">'))
PY
echo "=== 한 명 복도 $(date +%H:%M) 커밋 $(git -C $R rev-parse --short HEAD)"
GOAL_TIMEOUT=90 WORLD=zz_single MAP=aischool_2f_map $T/trial.sh $1_single people2 | tail -1
echo "=== 상자 구간 $(date +%H:%M)"
$T/trial.sh $1_box box | tail -1
rm -f $W/zz_single.sdf
echo "=== 끝 $(date +%H:%M)"
