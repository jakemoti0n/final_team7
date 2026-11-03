#!/usr/bin/env bash
# 실물 주행 명령 노드 띄우기: /cmd_vel 브리지 + 바퀴 odom(TF). 키보드는 다른 터미널에서 teleop_keyboard.sh
# 사용법: run_teleop.sh [max_duty_raw:=8191] [record_dir:=~/limbo_bags/drive_xxx] (ros2 launch 인자 그대로)
# 환경: ROS_DOMAIN_ID 기본 97(프로젝트 기본), 탐색 범위 SUBNET(노트북 rviz가 같은 Wi-Fi에서 보게)
set -eo pipefail
_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
source /opt/ros/jazzy/setup.bash
source "$_repo/limbo/install/setup.bash"
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-97}
export ROS_AUTOMATIC_DISCOVERY_RANGE=${ROS_AUTOMATIC_DISCOVERY_RANGE:-SUBNET}
export RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}
exec ros2 launch limbo_hardware teleop_drive.launch.py "$@"
