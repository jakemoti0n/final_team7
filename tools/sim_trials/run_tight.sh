#!/usr/bin/env bash
# 좁은 곳 통과 시험: 설정 4가지를 차례로 (lab). 각 설정마다 시뮬레이션을 새로 띄워 tight_trial.py를 돌린다.
# 사용법: run_tight.sh [반복 수, 기본 3]. 끝나면 nav2_params.yaml을 원래대로 되돌린다
D=$(cd "$(dirname "$0")" && pwd)
LOOPS=${1:-3}
P=limbo/src/limbo_navigation/config/nav2_params.yaml
export WORLD=aischool_2f_furnished MAP=aischool_2f_furnished_map
restore() { (cd ~/limbo && git checkout -q $P); }
run() {   # run <라벨> <설정 바꾸는 명령...>
  local label=$1; shift
  restore
  for cmd in "$@"; do eval "$cmd"; done
  $D/sim_ctl.sh start tight_$label > /dev/null 2>&1 || { echo "$label START_FAIL"; $D/sim_ctl.sh stop > /dev/null; return; }
  (source /opt/ros/jazzy/setup.bash; source ~/limbo/limbo/install/setup.bash; export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-97}; cd /tmp
   python3 $D/tight_trial.py $label $LOOPS 2>&1 | grep -v WARN)
  $D/sim_ctl.sh stop > /dev/null 2>&1
}
trap restore EXIT
run base
run fp "python3 $D/apply_footprint.py 0.25 0.295 0.0"
run fp_nc "python3 $D/apply_footprint.py 0.25 0.295 0.0" "python3 $D/apply_mppi_tune.py CostCritic.near_collision_cost=254"
run fp_nc_scale "python3 $D/apply_footprint.py 0.25 0.295 0.0" "python3 $D/apply_mppi_tune.py CostCritic.near_collision_cost=254" \
    "sed -i '0,/        cost_scaling_factor: 5.0/s//        cost_scaling_factor: 10.0/' ~/limbo/$P"
