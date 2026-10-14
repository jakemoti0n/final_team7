#!/usr/bin/env bash
# R5 Q6·Q7 확인: 트리 켬, 카메라 기본(0.7 m 0°). 비켜 주는 사람 복도 3회(녹화) + 손님 1회 + 상자 1회
source /opt/ros/jazzy/setup.bash; source ~/limbo/limbo/install/setup.bash
export ROS_DOMAIN_ID=98 GZ_PARTITION=desk
T=~/limbo/tools/sim_trials; R=~/limbo; D=$R/experiments/2026-10-14_social_people/worlds
W=$R/limbo/install/limbo_simulation/share/limbo_simulation/worlds
echo "=== 시작 $(date +%H:%M) 커밋 $(git -C $R rev-parse --short HEAD) (+ 계획 대기, 트리 켬)"
for i in 1 2 3; do
  B=~/limbo_bags/sim_trials/q7_corr${i}_bag; mv $B ~/limbo_bags/old_builds/q7_corr${i}_bag.$(date +%s) 2>/dev/null
  setsid ros2 bag record -s mcap -o $B /ground_truth/odom /sim/people /scan /tof/obstacle_ahead /person_approaching /person_blocking > /dev/null 2>&1 < /dev/null &
  REC=$!
  echo "=== corr$i $(date +%H:%M)"; GOAL_TIMEOUT=120 WORLD=aischool_2f_social MAP=aischool_2f_map $T/trial.sh q7_corr$i people2 | tail -1
  kill -TERM -- -$REC; wait $REC 2>/dev/null
done
cp $D/zz_social_approach.sdf $D/zz_social_approach_movers.json $W/
echo "=== guest $(date +%H:%M)"; GOAL_TIMEOUT=90 WORLD=zz_social_approach MAP=aischool_2f_map $T/trial.sh q7_guest hall | tail -1
rm -f $W/zz_social_approach.sdf $W/zz_social_approach_movers.json
echo "=== box $(date +%H:%M)"; $T/trial.sh q7_box box | tail -1
echo "=== 끝 $(date +%H:%M)"
