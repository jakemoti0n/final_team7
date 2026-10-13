#!/usr/bin/env bash
# 원인 실험 1 다시: 목표를 복도 안에 둔 people2 경로. 한 명(zz_single) 기본 설정 1회 + 30초 대기 1회, 두 명 기본 1회. 제한 60/90초
T=/home/kim/limbo/tools/sim_trials; R=/home/kim/limbo; W=$R/limbo/install/limbo_simulation/share/limbo_simulation/worlds
NAV=$R/limbo/src/limbo_navigation/config/nav2_params.yaml
python3 - <<'PY'
import re
W = '/home/kim/limbo/limbo/install/limbo_simulation/share/limbo_simulation/worlds/'
w = open(W + 'aischool_2f_scenarios.sdf').read()
w2, n = re.subn(r'\s*<actor name="pair_left">.*?</actor>', '', w, count=1, flags=re.S); assert n == 1
open(W + 'zz_single.sdf', 'w').write(w2.replace('<world name="aischool_2f_scenarios">', '<world name="zz_single">'))
PY
git -C $R checkout -- $NAV
echo "=== 한명 기본 $(date +%H:%M)"; GOAL_TIMEOUT=60 WORLD=zz_single MAP=aischool_2f_map $T/trial.sh c_single people2 | tail -1
sed -i 's|      movement_time_allowance: 10.0|      movement_time_allowance: 30.0|' $NAV
echo "=== 한명 wait30 $(date +%H:%M)"; GOAL_TIMEOUT=90 WORLD=zz_single MAP=aischool_2f_map $T/trial.sh c_single_wait30 people2 | tail -1
git -C $R checkout -- $NAV
echo "=== 두명 기본 $(date +%H:%M)"; GOAL_TIMEOUT=60 $T/trial.sh c_pair people2 | tail -1
rm -f $W/zz_single.sdf; echo "=== 끝 $(date +%H:%M)"
