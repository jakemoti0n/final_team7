#!/usr/bin/env bash
# ToF 단독 확인 (R5): 상자 월드에서 로봇 정지, /tof/obstacle_ahead·/tof/nearest 읽기
# 사용: tof_check.sh <라벨> <상자 a 중심 x>
source /opt/ros/jazzy/setup.bash; source ~/limbo/limbo/install/setup.bash
export ROS_DOMAIN_ID=98 GZ_PARTITION=desk
W=~/limbo/limbo/install/limbo_simulation/share/limbo_simulation/worlds
sed -e "s#<pose>0.885 0.16 0.15 0 0 0</pose>#<pose>$2 0.16 0.15 0 0 0</pose>#" -e 's#<world name="[^"]*">#<world name="zz_tof_'$1'">#' \
  ~/limbo/experiments/2026-10-14_camera_angle/worlds/zz_cam_box.sdf > $W/zz_tof_$1.sdf
WORLD=zz_tof_$1 MAP=human_test_map ~/limbo/tools/sim_trials/sim_ctl.sh start tof_$1 | tail -1
sleep 5
echo "== $1 (상자 a 중심 x=$2, 앞면 $(python3 -c "print(round($2-0.15-0.25,3))") m from sensor)"
timeout 5 ros2 topic hz /tof/points 2>&1 | grep average | tail -1
for i in 1 2 3; do timeout 3 ros2 topic echo --once /tof/obstacle_ahead 2>&1 | head -1; done
timeout 3 ros2 topic echo --once /tof/nearest 2>&1 | grep -A3 "point:"
~/limbo/tools/sim_trials/sim_ctl.sh stop | tail -1
rm -f $W/zz_tof_$1.sdf
