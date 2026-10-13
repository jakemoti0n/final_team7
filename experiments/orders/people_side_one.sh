#!/usr/bin/env bash
# 사용법: people_side_one.sh <A|B|C> <라벨>   — 조건 하나를 people_side 경로로 1회 돌리고 설정을 되돌린다
# A 현재 설정 / B prune_distance 2.5 / C 상한 0.75 + prune_distance 3.0 (experiments/2026-10-13_people_speed 참고)
set -u
T=~/limbo/tools/sim_trials; R=~/limbo
NAV=$R/limbo/src/limbo_navigation/config/nav2_params.yaml; XACRO=$R/limbo/src/limbo_description/urdf/limbo.gazebo.xacro
restore() { git -C $R checkout -- limbo/src/limbo_navigation/config/nav2_params.yaml limbo/src/limbo_description/urdf/limbo.gazebo.xacro; }
restore
case "$1" in
  A) ;;
  B) python3 $T/apply_mppi_tune.py prune_distance=2.5 ;;
  C) python3 $T/apply_mppi_tune.py prune_distance=3.0 vx_max=0.75
     sed -i 's|max_velocity: \[0.6, 0.0, 1.8\]|max_velocity: [0.75, 0.0, 1.8]|' $NAV
     sed -i 's|<max_linear_velocity>0.6<|<max_linear_velocity>0.8<|; s|<min_linear_velocity>-0.6<|<min_linear_velocity>-0.8<|' $XACRO ;;
  *) echo "조건은 A, B, C 중 하나"; exit 1 ;;
esac
echo "=== $1 $2 $(date +%H:%M) 커밋 $(git -C $R rev-parse --short HEAD)"
$T/trial.sh $2 people_side | tail -1
restore
