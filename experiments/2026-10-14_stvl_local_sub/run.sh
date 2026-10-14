#!/usr/bin/env bash
# R8: local costmap STVL voxel_decay 1 s(기준) vs 3 s. 상자 구간 각 3회 + 3 s로 비켜 주는 사람 복도 1회. 끝나면 설정 되돌림
source /opt/ros/jazzy/setup.bash; source ~/limbo/limbo/install/setup.bash
export ROS_DOMAIN_ID=98 GZ_PARTITION=desk
T=~/limbo/tools/sim_trials; R=~/limbo; NAV=$R/limbo/src/limbo_navigation/config/nav2_params.yaml
set_decay() { python3 - "$1" <<'PY'
import sys
p='/home/automaton/limbo/limbo/src/limbo_navigation/config/nav2_params.yaml'; s=open(p).read()
lines=s.split('\n'); n=[i for i,l in enumerate(lines) if l.strip().startswith('voxel_decay:')][0]   # 첫 번째 = local costmap
lines[n]=lines[n].split('voxel_decay:')[0]+'voxel_decay: '+sys.argv[1]
open(p,'w').write('\n'.join(lines)); print('local voxel_decay', sys.argv[1])
PY
}
echo "=== 시작 $(date +%H:%M) 커밋 $(git -C $R rev-parse --short HEAD)"
for d in 1.0 3.0; do
  set_decay $d
  for i in 1 2 3; do echo "=== decay$d box$i $(date +%H:%M)"; $T/trial.sh r8_d${d%.0}_box$i box | tail -1; done
done
echo "=== decay3 corr $(date +%H:%M)"; GOAL_TIMEOUT=120 WORLD=aischool_2f_social MAP=aischool_2f_map $T/trial.sh r8_d3_corr people2 | tail -1
git -C $R checkout -- $NAV
echo "=== 끝 $(date +%H:%M)"
