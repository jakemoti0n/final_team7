#!/usr/bin/env bash
# 사용법: run.sh [라벨접두]   — 위치 추정 AMCL(지금) vs slam_toolbox 위치 추정 모드(maps/aischool_2f_map_posegraph)를
# 비켜 주는 사람 복도(people2)·홀 손님(hall)에서 각 1회. 기본 BT. 이미 CSV가 있는 회차는 건너뜀
set +u
T=~/limbo/tools/sim_trials; R=~/limbo; SW=$R/experiments/2026-10-14_social_people/worlds
W=$R/limbo/install/limbo_simulation/share/limbo_simulation/worlds; NAV=$R/limbo/src/limbo_navigation/config/nav2_params.yaml
L=~/limbo_bags/sim_trials/logs
cp $SW/zz_social_approach.sdf $SW/zz_social_approach_movers.json $W/
# 포즈그래프는 설치 폴더(복사 설치)에서 읽으므로 src에서 만든 것을 복사해 둔다
cp $R/limbo/src/limbo_navigation/maps/*_posegraph.* $R/limbo/install/limbo_navigation/share/limbo_navigation/maps/ 2>/dev/null
git -C $R checkout -- $NAV
sed -i 's|^    default_nav_to_pose_bt_xml:|    # (비교 중 끔) default_nav_to_pose_bt_xml:|; s|^    default_nav_through_poses_bt_xml:|    # (비교 중 끔) default_nav_through_poses_bt_xml:|; s|^    plugin_lib_names: \["limbo|    # (비교 중 끔) plugin_lib_names: ["limbo|' $NAV
for loc in amcl slam; do
  export EXTRA_ARGS="localization:=$loc"
  if [ ! -f $L/trial_${1:-lc}_${loc}_corridor.csv ]; then
    echo "=== $loc 복도 $(date +%H:%M) 커밋 $(git -C $R rev-parse --short HEAD)"
    GOAL_TIMEOUT=90 WORLD=aischool_2f_social MAP=aischool_2f_map $T/trial.sh ${1:-lc}_${loc}_corridor people2 | tail -1
  fi
  if [ ! -f $L/trial_${1:-lc}_${loc}_hall.csv ]; then
    echo "=== $loc 홀 $(date +%H:%M)"
    GOAL_TIMEOUT=90 WORLD=zz_social_approach MAP=aischool_2f_map $T/trial.sh ${1:-lc}_${loc}_hall hall | tail -1
  fi
done
git -C $R checkout -- $NAV; rm -f $W/zz_social_approach.sdf $W/zz_social_approach_movers.json
echo "=== 끝 $(date +%H:%M)"
