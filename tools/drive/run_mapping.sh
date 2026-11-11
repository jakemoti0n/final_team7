#!/usr/bin/env bash
# 실물 지도 작성: 주행 명령 노드 + MID-360S + slam_toolbox + bag 녹화. 키보드는 다른 터미널에서 teleop_keyboard.sh
# 사용법: run_mapping.sh [label:=학원2층] [max_duty_raw:=9830] [bag:=false]
# 끝나면 다른 터미널에서 save_map.sh <지도이름> 으로 저장한 뒤 Ctrl+C
# 전제: 라이다가 본체 LAN(192.168.1.50)에, 노트북은 Wi-Fi로. 노트북 rviz는 같은 도메인(97)·SUBNET으로 /map, /scan을 본다
set -eo pipefail
_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
source /opt/ros/jazzy/setup.bash
source "$HOME/livox_ws/install/local_setup.bash"
source "$_repo/limbo/install/setup.bash"
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-97}
export ROS_AUTOMATIC_DISCOVERY_RANGE=${ROS_AUTOMATIC_DISCOVERY_RANGE:-SUBNET}
export RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}
mkdir -p "$HOME/limbo_bags"
exec ros2 launch limbo_bringup start_mapping.launch.py "$@"
