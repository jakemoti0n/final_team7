#!/usr/bin/env bash
# 사용법: run.sh [라벨접두]   — RPP(Regulated Pure Pursuit)를 오늘 벤치(비켜 주는 사람 복도 people2 / 홀 손님 hall / 상자 box)에서 각 1회, 기본 BT.
# MPPI 기준값은 같은 날 같은 설정의 pl_navfn_corridor·pl_navfn_hall·prune25_box CSV
set +u
T=~/limbo/tools/sim_trials; R=~/limbo; SW=$R/experiments/2026-10-14_social_people/worlds
W=$R/limbo/install/limbo_simulation/share/limbo_simulation/worlds; NAV=$R/limbo/src/limbo_navigation/config/nav2_params.yaml
cp $SW/zz_social_approach.sdf $SW/zz_social_approach_movers.json $W/
git -C $R checkout -- $NAV
sed -i 's|^    default_nav_to_pose_bt_xml:|    # (비교 중 끔) default_nav_to_pose_bt_xml:|; s|^    default_nav_through_poses_bt_xml:|    # (비교 중 끔) default_nav_through_poses_bt_xml:|; s|^    plugin_lib_names: \["limbo|    # (비교 중 끔) plugin_lib_names: ["limbo|' $NAV
python3 $T/apply_controller.py rpp
grep -c "RegulatedPurePursuitController" $NAV
echo "=== rpp 복도 $(date +%H:%M) 커밋 $(git -C $R rev-parse --short HEAD)"
GOAL_TIMEOUT=90 WORLD=aischool_2f_social MAP=aischool_2f_map $T/trial.sh ${1:-rpp}_corridor people2 | tail -1
echo "=== rpp 홀 $(date +%H:%M)"
GOAL_TIMEOUT=90 WORLD=zz_social_approach MAP=aischool_2f_map $T/trial.sh ${1:-rpp}_hall hall | tail -1
echo "=== rpp 상자 $(date +%H:%M)"
GOAL_TIMEOUT=90 $T/trial.sh ${1:-rpp}_box box | tail -1
git -C $R checkout -- $NAV; rm -f $W/zz_social_approach.sdf $W/zz_social_approach_movers.json
echo "=== 끝 $(date +%H:%M)"
