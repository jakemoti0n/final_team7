#!/usr/bin/env bash
# Read-only real sensors/odom/TF; no motor output or autonomous navigation.
set -eo pipefail
_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-97}
export ROS_AUTOMATIC_DISCOVERY_RANGE=${ROS_AUTOMATIC_DISCOVERY_RANGE:-LOCALHOST}
source /opt/ros/jazzy/setup.bash
source "$HOME/livox_ws/install/local_setup.bash"
source "$_repo/tools/oak/ros_input_env.sh"
source "$_repo/tools/stvl/stvl_env.sh"
exec ros2 launch limbo_bringup start_real.launch.py \
  yolo_python:="${LIMBO_YOLO_PYTHON:-$_repo/venvs/limbo_yolo/bin/python}" "$@"
