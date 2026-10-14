#!/usr/bin/env bash
# 사용법: run.sh [라벨접두]   — 전역 경로 계획기 3개(NavFn 지금 / Smac 2D / Theta*)를 경로 3개에서 각 1회
# 경로: 비켜 주는 사람 복도(aischool_2f_social, people2) / 홀 손님(zz_social_approach, hall). 충장로는 선별에서 뺌(최종 단계 장소, 사용자 결정 10-14)
# 이미 CSV가 있는 회차는 건너뛴다
set +u
T=~/limbo/tools/sim_trials; R=~/limbo; SW=$R/experiments/2026-10-14_social_people/worlds
W=$R/limbo/install/limbo_simulation/share/limbo_simulation/worlds; NAV=$R/limbo/src/limbo_navigation/config/nav2_params.yaml
cp $SW/zz_social_approach.sdf $SW/zz_social_approach_movers.json $W/
git -C $R checkout -- $NAV
for planner in navfn smac2d theta; do
  git -C $R checkout -- $NAV
  # 계획기 비교는 Nav2 기본 BT로 한다. lab에 켜 둔 기다리기 BT(R5)는 비켜 주는 사람 복도에서 60번 기다리다 포기해(10-14) 비교를 망침
  sed -i 's|^    default_nav_to_pose_bt_xml:|    # (계획기 비교 중 끔) default_nav_to_pose_bt_xml:|; s|^    default_nav_through_poses_bt_xml:|    # (계획기 비교 중 끔) default_nav_through_poses_bt_xml:|; s|^    plugin_lib_names: \["limbo|    # (계획기 비교 중 끔) plugin_lib_names: ["limbo|' $NAV
  python3 - "$planner" <<'PY'
import sys, re, os
p = os.path.expanduser('~/limbo/limbo/src/limbo_navigation/config/nav2_params.yaml'); s = open(p).read()
blocks = {
 'navfn': None,
 'smac2d': '''    GridBased:
      plugin: "nav2_smac_planner::SmacPlanner2D"
      tolerance: 0.5
      downsample_costmap: false
      allow_unknown: true
      max_iterations: 1000000
      max_on_approach_iterations: 1000
      max_planning_time: 2.0
      cost_travel_multiplier: 2.0
      use_final_approach_orientation: false
      smoother:
        max_iterations: 1000
        w_smooth: 0.3
        w_data: 0.2
        tolerance: 1.0e-10
''',
 'theta': '''    GridBased:
      plugin: "nav2_theta_star_planner::ThetaStarPlanner"
      how_many_corners: 8
      w_euc_cost: 1.0
      w_traversal_cost: 2.0
      use_final_approach_orientation: false
''',
}
b = blocks[sys.argv[1]]
if b:
    s2, n = re.subn(r'    GridBased:\n      plugin: "nav2_navfn_planner::NavfnPlanner"\n(?:      [^\n]*\n)+', b, s, count=1); assert n == 1
    open(p, 'w').write(s2)
print('planner', sys.argv[1])
PY
  L=~/limbo_bags/sim_trials/logs
  if [ ! -f $L/trial_${1:-pl}_${planner}_corridor.csv ]; then
    echo "=== $planner 복도 $(date +%H:%M) 커밋 $(git -C $R rev-parse --short HEAD)"
    GOAL_TIMEOUT=90 WORLD=aischool_2f_social MAP=aischool_2f_map $T/trial.sh ${1:-pl}_${planner}_corridor people2 | tail -1
  fi
  if [ ! -f $L/trial_${1:-pl}_${planner}_hall.csv ]; then
    echo "=== $planner 홀 $(date +%H:%M)"
    GOAL_TIMEOUT=90 WORLD=zz_social_approach MAP=aischool_2f_map $T/trial.sh ${1:-pl}_${planner}_hall hall | tail -1
  fi
done
git -C $R checkout -- $NAV; rm -f $W/zz_social_approach.sdf $W/zz_social_approach_movers.json
echo "=== 끝 $(date +%H:%M)"
