#!/usr/bin/env bash
# 사용법: patrol_trial.sh <라벨> [waypoint 파일, 기본 aischool_waypoints.yaml]
# 학원 2층(기본 aischool_2f, 걷는 사람 3명)을 띄우고 순찰 노드를 끝까지 돌린 뒤 끈다.
# 멈춤 원인을 가릴 수 있게 속도 명령 3단계(/cmd_vel_nav → /cmd_vel_smoothed → /cmd_vel)와
# collision monitor 상태, 위치 추정, 정답 위치를 작은 rosbag으로 남긴다. 결과는 logs/patrol_results.txt에 한 줄씩
D=$(cd "$(dirname "$0")" && pwd); LOGS=~/limbo_bags/sim_trials/logs; mkdir -p $LOGS
WAYPOINTS=${2:-aischool_waypoints.yaml}
export WORLD=${WORLD:-aischool_2f} MAP=${MAP:-aischool_2f_map}
T0=$(date +%s)
$D/sim_ctl.sh start patrol_$1 || { $D/sim_ctl.sh stop; echo "patrol_$1 START_FAIL" >> $LOGS/patrol_results.txt; exit 1; }
source /opt/ros/jazzy/setup.bash; source ~/limbo/limbo/install/setup.bash; export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-97}; cd /tmp
rm -rf $LOGS/patrol_$1_bag
# 액션 상태(/navigate_through_poses/_action/status)는 숨김 토픽이라 --include-hidden-topics가 있어야 녹화된다
ros2 bag record --include-hidden-topics -s mcap -o $LOGS/patrol_$1_bag /cmd_vel_nav /cmd_vel_smoothed /cmd_vel /collision_monitor_state \
  /amcl_pose /ground_truth/odom /odom /navigate_through_poses/_action/status /wheel_slip > /dev/null 2>&1 &
BAG=$!
sleep 2
ros2 run limbo_patrol patrol_node --ros-args -p use_sim_time:=true -p waypoints:=$WAYPOINTS > $LOGS/patrol_$1.log 2>&1 &
P=$!
for i in $(seq 1 ${PATROL_TIMEOUT:-900}); do kill -0 $P 2>/dev/null || break; sleep 1; done
if kill -0 $P 2>/dev/null; then   # 시간 초과: ros2 run이 띄운 python 자식까지 끈다
  for c in $(pgrep -P $P); do kill -INT $c; done; kill -INT $P; sleep 3; kill -9 $P $(pgrep -P $P) 2>/dev/null
fi
kill -INT $BAG; for i in $(seq 1 15); do kill -0 $BAG 2>/dev/null || break; sleep 1; done; kill -9 $BAG 2>/dev/null
# 녹화가 마무리되지 못하면 metadata가 없어 읽을 수 없다. 재색인으로 복구한다
[ -f $LOGS/patrol_$1_bag/metadata.yaml ] || ros2 bag reindex $LOGS/patrol_$1_bag -s mcap > /dev/null 2>&1
$D/sim_ctl.sh stop > /dev/null
if grep -q "Patrol mission completed" $LOGS/patrol_$1.log; then R=OK
elif grep -q "Patrol mission failed" $LOGS/patrol_$1.log; then R="FAIL ($(grep -m1 -E 'Navigation (failed|canceled)|rejected' $LOGS/patrol_$1.log))"
else R=TIMEOUT; fi
LINE="patrol_$1 $R $(( $(date +%s) - T0 ))s"
echo "$LINE" | tee -a $LOGS/patrol_results.txt
