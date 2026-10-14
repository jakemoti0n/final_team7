#!/usr/bin/env bash
# R6 전체: no_yield 복도 3 + yield 복도 3 + 손님 1 + 상자 1 (트리 켬, 비켜서기 포함). 회차마다 녹화
source /opt/ros/jazzy/setup.bash; source ~/limbo/limbo/install/setup.bash
export ROS_DOMAIN_ID=98 GZ_PARTITION=desk
T=~/limbo/tools/sim_trials; R=~/limbo; D=$R/experiments/2026-10-14_social_people/worlds; W=$R/limbo/install/limbo_simulation/share/limbo_simulation/worlds
cp $D/zz_social_*.sdf $D/zz_social_*_movers.json $W/
run() {  # run <라벨> <월드> <경로>
  B=~/limbo_bags/sim_trials/$1_bag; mv $B ~/limbo_bags/old_builds/$1_bag.$(date +%s) 2>/dev/null
  setsid ros2 bag record -s mcap -o $B /ground_truth/odom /sim/people /person_approaching /person_blocking /cmd_vel > /dev/null 2>&1 < /dev/null &
  REC=$!
  echo "=== $1 $(date +%H:%M)"
  if [ "$2" = box ]; then $T/trial.sh $1 box | tail -1; else GOAL_TIMEOUT=120 WORLD=$2 MAP=aischool_2f_map $T/trial.sh $1 $3 | tail -1; fi
  kill -TERM -- -$REC; wait $REC 2>/dev/null
}
echo "=== 시작 $(date +%H:%M) 커밋 $(git -C $R rev-parse --short HEAD) (+ R6 작업 폴더)"
for i in 1 2 3; do run r6_noyield$i zz_social_noyield people2; done
for i in 1 2 3; do run r6_yield$i aischool_2f_social people2; done
run r6_guest zz_social_approach hall
run r6_box box
rm -f $W/zz_social_*.sdf $W/zz_social_*_movers.json
echo "=== 끝 $(date +%H:%M)"
