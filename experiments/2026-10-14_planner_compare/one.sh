#!/usr/bin/env bash
# 사용법: one.sh <navfn|smac2d|theta> <corridor|hall> <라벨>   — 계획기 하나·경로 하나 1회 (기본 BT)
set +u
T=~/limbo/tools/sim_trials; R=~/limbo; SW=$R/experiments/2026-10-14_social_people/worlds
W=$R/limbo/install/limbo_simulation/share/limbo_simulation/worlds; NAV=$R/limbo/src/limbo_navigation/config/nav2_params.yaml
cp $SW/zz_social_approach.sdf $SW/zz_social_approach_movers.json $W/
git -C $R checkout -- $NAV
sed -i 's|^    default_nav_to_pose_bt_xml:|    # (계획기 비교 중 끔) default_nav_to_pose_bt_xml:|; s|^    default_nav_through_poses_bt_xml:|    # (계획기 비교 중 끔) default_nav_through_poses_bt_xml:|; s|^    plugin_lib_names: \["limbo|    # (계획기 비교 중 끔) plugin_lib_names: ["limbo|' $NAV
PLANNER=$1 python3 - <<'PY'
import re, os
p = os.path.expanduser('~/limbo/limbo/src/limbo_navigation/config/nav2_params.yaml'); s = open(p).read()
blocks = {'navfn': None,
 'smac2d': '    GridBased:\n      plugin: "nav2_smac_planner::SmacPlanner2D"\n      tolerance: 0.5\n      downsample_costmap: false\n      allow_unknown: true\n      max_iterations: 1000000\n      max_on_approach_iterations: 1000\n      max_planning_time: 2.0\n      cost_travel_multiplier: 2.0\n      use_final_approach_orientation: false\n      smoother:\n        max_iterations: 1000\n        w_smooth: 0.3\n        w_data: 0.2\n        tolerance: 1.0e-10\n',
 'theta': '    GridBased:\n      plugin: "nav2_theta_star_planner::ThetaStarPlanner"\n      how_many_corners: 8\n      w_euc_cost: 1.0\n      w_traversal_cost: 2.0\n      use_final_approach_orientation: false\n'}
b = blocks[os.environ['PLANNER']]
if b:
    s2, n = re.subn(r'    GridBased:\n      plugin: "nav2_navfn_planner::NavfnPlanner"\n(?:      [^\n]*\n)+', b, s, count=1); assert n == 1; open(p, 'w').write(s2)
PY
if [ "$2" = corridor ]; then GOAL_TIMEOUT=90 WORLD=aischool_2f_social MAP=aischool_2f_map $T/trial.sh $3 people2 | tail -1
else GOAL_TIMEOUT=90 WORLD=zz_social_approach MAP=aischool_2f_map $T/trial.sh $3 hall | tail -1; fi
git -C $R checkout -- $NAV; rm -f $W/zz_social_approach.sdf $W/zz_social_approach_movers.json
echo "=== 끝 $(date +%H:%M)"
