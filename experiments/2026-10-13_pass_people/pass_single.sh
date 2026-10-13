#!/usr/bin/env bash
# 원인 실험 1: 걷는 사람 한 명(zz_single) vs 두 명(aischool_2f_scenarios). 지금 설정, people_side2, 제한 60초
T=/home/kim/limbo/tools/sim_trials; R=/home/kim/limbo
git -C $R checkout -- limbo/src/limbo_navigation/config/nav2_params.yaml limbo/src/limbo_description/urdf/limbo.gazebo.xacro
export GOAL_TIMEOUT=60
for i in 1 2; do echo "=== 한명 $i $(date +%H:%M)"; WORLD=zz_single MAP=aischool_2f_map $T/trial.sh single$i people_side2 | tail -1; done
echo "=== 두명 1 $(date +%H:%M)"; $T/trial.sh pair1 people_side2 | tail -1
rm -f $R/limbo/install/limbo_simulation/share/limbo_simulation/worlds/zz_single.sdf
echo "=== 끝 $(date +%H:%M)"
