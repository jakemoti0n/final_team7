#!/usr/bin/env bash
# slam_toolbox가 만든 지도를 저장: <이름>.pgm/.yaml(map_server용) + <이름>_posegraph(slam_toolbox 위치 추정용)
# 사용법: save_map.sh <이름> [저장 폴더(기본 limbo_navigation/maps)]
# run_mapping.sh가 떠 있는 상태에서 실행한다. 저장 뒤 지도 파일을 ktj/dev에 올릴 때는 maps/ 아래 이름을 PM과 정한다
set -eo pipefail
[ -n "$1" ] || { echo "사용법: save_map.sh <이름> [폴더]"; exit 1; }
_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
source /opt/ros/jazzy/setup.bash
source "$_repo/limbo/install/setup.bash"
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-97}
export ROS_AUTOMATIC_DISCOVERY_RANGE=${ROS_AUTOMATIC_DISCOVERY_RANGE:-SUBNET}
export RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}
_dir=${2:-$_repo/limbo/src/limbo_navigation/maps}
mkdir -p "$_dir"
ros2 service call /slam_toolbox/save_map slam_toolbox/srv/SaveMap "{name: {data: '$_dir/$1'}}"
ros2 service call /slam_toolbox/serialize_map slam_toolbox/srv/SerializePoseGraph "{filename: '$_dir/$1_posegraph'}"
ls -l "$_dir/$1"*
