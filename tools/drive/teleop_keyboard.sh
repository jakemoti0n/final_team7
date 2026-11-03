#!/usr/bin/env bash
# 키보드로 /cmd_vel 보내기 (이 터미널에서 i/,/j/l/k 키). run_teleop.sh 또는 run_mapping.sh가 떠 있어야 바퀴가 돈다.
# - repeat_rate 10: 기본은 키를 누를 때만 한 번 발행이라 브리지의 명령 끊김 정지(보드 timeout 0.5 s)에 걸린다. 10 Hz로 반복
# - key_timeout 0.6: 키를 뗀 뒤 이 시간 안에 새 키가 없으면 0을 보낸다. 반복 주기(0.1 s)보다 길고 끊김 정지(0.5 s)와 비슷하게
# - speed 0.1 m/s, turn 0.4 rad/s로 시작. q/z로 10 %씩 키우고 줄인다. 브리지 상한(0.25 m/s, 0.8 rad/s) 위는 잘린다
set -eo pipefail
_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
source /opt/ros/jazzy/setup.bash
source "$_repo/limbo/install/setup.bash"
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-97}
export ROS_AUTOMATIC_DISCOVERY_RANGE=${ROS_AUTOMATIC_DISCOVERY_RANGE:-SUBNET}
export RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}
exec ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args \
  -p repeat_rate:=10.0 -p key_timeout:=0.6 -p speed:=0.1 -p turn:=0.4 "$@"
