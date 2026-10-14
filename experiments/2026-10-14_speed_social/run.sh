#!/usr/bin/env bash
# 사용법: run.sh [라벨접두]   — 속도 설정 A(지금: vx 0.6, prune 1.7) / B(prune 2.5) / C(vx 0.75 + prune 3.0)를
# 소셜 포스 사람 조건에서 비교: 비켜 주는 사람 복도(aischool_2f_social, people2) + 손님 홀(zz_social_approach, hall) 각 1회. 끝나면 원복
set +u
T=~/limbo/tools/sim_trials; R=~/limbo; D=$R/experiments/2026-10-14_social_people/worlds
W=$R/limbo/install/limbo_simulation/share/limbo_simulation/worlds
NAV=$R/limbo/src/limbo_navigation/config/nav2_params.yaml; XACRO=$R/limbo/src/limbo_description/urdf/limbo.gazebo.xacro
restore() { git -C $R checkout -- $NAV $XACRO; }
cp $D/zz_social_approach.sdf $D/zz_social_approach_movers.json $W/
restore
for cond in A B C; do
  case $cond in
    B) python3 $T/apply_mppi_tune.py prune_distance=2.5 ;;
    C) python3 $T/apply_mppi_tune.py prune_distance=3.0 vx_max=0.75
       sed -i 's|max_velocity: \[0.6, 0.0, 1.8\]|max_velocity: [0.75, 0.0, 1.8]|' $NAV
       sed -i 's|<max_linear_velocity>0.6<|<max_linear_velocity>0.8<|; s|<min_linear_velocity>-0.6<|<min_linear_velocity>-0.8<|' $XACRO ;;
  esac
  echo "=== $cond 복도 $(date +%H:%M) 커밋 $(git -C $R rev-parse --short HEAD)"
  GOAL_TIMEOUT=90 WORLD=aischool_2f_social MAP=aischool_2f_map $T/trial.sh ${1:-sp}_${cond}_corridor people2 | tail -1
  echo "=== $cond 홀 $(date +%H:%M)"
  GOAL_TIMEOUT=90 WORLD=zz_social_approach MAP=aischool_2f_map $T/trial.sh ${1:-sp}_${cond}_hall hall | tail -1
  restore
done
rm -f $W/zz_social_approach.sdf $W/zz_social_approach_movers.json
echo "=== 끝 $(date +%H:%M)"
