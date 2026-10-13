#!/usr/bin/env bash
# 원인 실험 3(진단용): progress checker 허용 시간 10 → 30초로 "사람이 지나갈 때까지 경로를 안 버리면 통과하는가". 두 명·한 명 각 1회, 제한 90초
T=/home/kim/limbo/tools/sim_trials; R=/home/kim/limbo; S=$(dirname "$0")
while kill -0 288889 2>/dev/null; do sleep 10; done     # pass_single.sh가 끝날 때까지
W=$R/limbo/install/limbo_simulation/share/limbo_simulation/worlds
python3 - <<'PY'
import re
W = '/home/kim/limbo/limbo/install/limbo_simulation/share/limbo_simulation/worlds/'
w = open(W + 'aischool_2f_scenarios.sdf').read()
w2, n = re.subn(r'\s*<actor name="pair_left">.*?</actor>', '', w, count=1, flags=re.S); assert n == 1
open(W + 'zz_single.sdf', 'w').write(w2.replace('<world name="aischool_2f_scenarios">', '<world name="zz_single">'))
PY
git -C $R checkout -- limbo/src/limbo_navigation/config/nav2_params.yaml
sed -i 's|      movement_time_allowance: 10.0|      movement_time_allowance: 30.0|' $R/limbo/src/limbo_navigation/config/nav2_params.yaml
grep -n "movement_time_allowance" $R/limbo/src/limbo_navigation/config/nav2_params.yaml
export GOAL_TIMEOUT=90
echo "=== 두명 wait30 $(date +%H:%M)"; $T/trial.sh pair_wait30 people_side2 | tail -1
echo "=== 한명 wait30 $(date +%H:%M)"; WORLD=zz_single MAP=aischool_2f_map $T/trial.sh single_wait30 people_side2 | tail -1
git -C $R checkout -- limbo/src/limbo_navigation/config/nav2_params.yaml
rm -f $W/zz_single.sdf
[ -f $S/trace_bag.pid ] && kill -TERM $(cat $S/trace_bag.pid) 2>/dev/null
echo "=== 끝 $(date +%H:%M)"
