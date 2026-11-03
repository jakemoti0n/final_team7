#!/usr/bin/env bash
# 실물 사람 앞 기다리기 시험: 카메라 장착 TF(임시값, limbo_bringup/config/real_robot_mount.yaml) + person_wait 노드.
# 먼저 떠 있어야 함: 카메라(tools/oak/run_ros_input.sh), 검출기(run_ros_yolo.sh), 주행 브리지(run_teleop.sh), 라이다+SLAM(run_mapping.sh 또는 수동).
# 준비되면 로그에 person_wait 상태가 NOT_READY → DRIVING으로 바뀌고, 사람이 앞 1.5 m 구역에 서면 WAITING(브리지 출력 0).
set -eo pipefail
_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
source /opt/ros/jazzy/setup.bash
source "$_repo/limbo/install/setup.bash"
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-97}
export ROS_AUTOMATIC_DISCOVERY_RANGE=${ROS_AUTOMATIC_DISCOVERY_RANGE:-SUBNET}
export RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}
exec ros2 launch limbo_bringup start_person_wait_real.launch.py "$@"
