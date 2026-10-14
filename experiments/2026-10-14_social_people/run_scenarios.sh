#!/usr/bin/env bash
# 사용법: run_scenarios.sh <라벨접두>   — HumanLayer 켬/끔 × (no_yield 복도 people2, approach 홀 hall) 각 1회
# 결과 CSV: ~/limbo_bags/sim_trials/logs/trial_<라벨>_{on,off}_{noyield,approach}.csv
set +u
T=~/limbo/tools/sim_trials; R=~/limbo; D=$R/experiments/2026-10-14_social_people/worlds
W=$R/limbo/install/limbo_simulation/share/limbo_simulation/worlds; NAV=$R/limbo/src/limbo_navigation/config/nav2_params.yaml
cp $D/zz_social_*.sdf $D/zz_social_*_movers.json $W/
git -C $R checkout -- $NAV
for cond in on off; do
  if [ $cond = off ]; then python3 - <<'PY'
import re, os
p = os.path.expanduser('~/limbo/limbo/src/limbo_navigation/config/nav2_params.yaml'); s = open(p).read()
s, n = re.subn(r'(      human_layer:\n        plugin: "limbo_navigation::HumanLayer"\n        enabled: )true', r'\g<1>false', s); assert n == 1
open(p, 'w').write(s); print('human_layer enabled: false')
PY
  fi
  echo "=== $cond noyield $(date +%H:%M) 커밋 $(git -C $R rev-parse --short HEAD)"
  GOAL_TIMEOUT=90 WORLD=zz_social_noyield MAP=aischool_2f_map $T/trial.sh ${1}_${cond}_noyield people2 | tail -1
  echo "=== $cond approach $(date +%H:%M)"
  GOAL_TIMEOUT=90 WORLD=zz_social_approach MAP=aischool_2f_map $T/trial.sh ${1}_${cond}_approach hall | tail -1
  git -C $R checkout -- $NAV
done
rm -f $W/zz_social_*.sdf $W/zz_social_*_movers.json
echo "=== 끝 $(date +%H:%M)"
