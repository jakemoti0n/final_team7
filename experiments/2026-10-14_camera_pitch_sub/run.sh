#!/usr/bin/env bash
# R5 Q5: 카메라 0.7 m 고정, 피치 0·8·15° × 손님 장면 3회(녹화) + 비켜 주는 사람 복도 1회, 마지막에 상자 1회(15°)
source /opt/ros/jazzy/setup.bash; source ~/limbo/limbo/install/setup.bash
export ROS_DOMAIN_ID=98 GZ_PARTITION=desk
T=~/limbo/tools/sim_trials; R=~/limbo; D=$R/experiments/2026-10-14_social_people/worlds
W=$R/limbo/install/limbo_simulation/share/limbo_simulation/worlds; L=~/limbo_bags/sim_trials/logs
cp $D/zz_social_approach.sdf $D/zz_social_approach_movers.json $W/
echo "=== 시작 $(date +%H:%M) 커밋 $(git -C $R rev-parse --short HEAD)"
for p in 0 8 15; do
  for i in 1 2 3; do
    B=~/limbo_bags/sim_trials/q5_p${p}_$i; mv $B ~/limbo_bags/old_builds/q5_p${p}_$i.$(date +%s) 2>/dev/null
    setsid ros2 bag record -s mcap -o $B /ground_truth/odom /sim/people /person_detector/predictions /person_approaching > /dev/null 2>&1 < /dev/null &
    REC=$!
    echo "=== p$p guest$i $(date +%H:%M)"
    EXTRA_ARGS="camera_z:=0.70 camera_pitch_deg:=$p" GOAL_TIMEOUT=90 WORLD=zz_social_approach MAP=aischool_2f_map $T/trial.sh q5_p${p}_guest$i hall | tail -1
    kill -TERM -- -$REC; wait $REC 2>/dev/null
  done
  echo "=== p$p social $(date +%H:%M)"
  EXTRA_ARGS="camera_z:=0.70 camera_pitch_deg:=$p" GOAL_TIMEOUT=90 WORLD=aischool_2f_social MAP=aischool_2f_map $T/trial.sh q5_p${p}_social people2 | tail -1
done
echo "=== box p15 $(date +%H:%M)"; EXTRA_ARGS="camera_z:=0.70 camera_pitch_deg:=15" $T/trial.sh q5_p15_box box | tail -1
rm -f $W/zz_social_approach.sdf $W/zz_social_approach_movers.json
echo "=== 끝 $(date +%H:%M)"
