#!/usr/bin/env bash
# Requires real sensors/odom and exactly one SLAM or AMCL map->odom source.
# Default output is /limbo/nav2_preview/cmd_vel. Does not start a motor driver.
set -eo pipefail
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-97}
export ROS_AUTOMATIC_DISCOVERY_RANGE=${ROS_AUTOMATIC_DISCOVERY_RANGE:-LOCALHOST}
_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
source /opt/ros/jazzy/setup.bash
source "$_repo/tools/oak/ros_input_env.sh"
source "$_repo/tools/stvl/stvl_env.sh"
exec ros2 launch limbo_bringup start_nav2_real.launch.py "$@"
