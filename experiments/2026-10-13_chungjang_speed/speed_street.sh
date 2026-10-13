#!/usr/bin/env bash
# 충장로 거리 속도 실험: 조건 A/B/C 차례로. 결과 CSV → ~/limbo_bags/sim_trials/logs/street_<조건>.csv, bag → ~/limbo_bags/sim_trials/street_<조건>
T=/home/kim/limbo/tools/sim_trials; LOGS=~/limbo_bags/sim_trials/logs; R=/home/kim/limbo
NAV=$R/limbo/src/limbo_navigation/config/nav2_params.yaml; XACRO=$R/limbo/src/limbo_description/urdf/limbo.gazebo.xacro
restore() { git -C $R checkout -- limbo/src/limbo_navigation/config/nav2_params.yaml limbo/src/limbo_description/urdf/limbo.gazebo.xacro; }
run_one() {   # 조건이름
  echo "=== 조건 $1 $(date +%H:%M)"
  BEFORE=$(ls ~/limbo_results/*.csv 2>/dev/null | wc -l)
  cd $T && WORLD=chungjang MAP=chungjang_map ./sim_ctl.sh start street_$1 | tail -1 || { ./sim_ctl.sh stop; return; }
  source /opt/ros/jazzy/setup.bash; source $R/limbo/install/setup.bash; export ROS_DOMAIN_ID=97; cd /tmp
  rm -rf ~/limbo_bags/sim_trials/street_$1
  ros2 bag record -s mcap -o ~/limbo_bags/sim_trials/street_$1 /cmd_vel_nav /cmd_vel_smoothed /cmd_vel /ground_truth/odom /collision_monitor_state > $LOGS/street_$1.bag.log 2>&1 & BAG=$!
  sleep 3
  GOAL_TIMEOUT=450 timeout 1000 python3 $T/nav_route.py street 2>&1 | tee $LOGS/street_$1.nav.log
  kill -INT $BAG; sleep 3
  $T/sim_ctl.sh stop
  [ "$(ls ~/limbo_results/*.csv | wc -l)" -gt "$BEFORE" ] && cp $(ls -t ~/limbo_results/*.csv | head -1) $LOGS/street_$1.csv
}
restore
run_one A
python3 $T/apply_mppi_tune.py prune_distance=2.5
run_one B
restore
python3 $T/apply_mppi_tune.py prune_distance=3.0 vx_max=0.75
sed -i 's|max_velocity: \[0.6, 0.0, 1.8\]|max_velocity: [0.75, 0.0, 1.8]|' $NAV
sed -i 's|<max_linear_velocity>0.6<|<max_linear_velocity>0.8<|; s|<min_linear_velocity>-0.6<|<min_linear_velocity>-0.8<|' $XACRO
grep -n "max_velocity:" $NAV; grep -n "linear_velocity" $XACRO
run_one C
restore
echo "=== 끝 $(date +%H:%M)"; git -C $R status --short
