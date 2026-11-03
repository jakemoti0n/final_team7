#!/usr/bin/env bash
# Starts the single read-only encoder owner and its odometry consumer together.
set -eo pipefail
_odom_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
_odom_domain=${ROS_DOMAIN_ID:-97}
_odom_discovery=${ROS_AUTOMATIC_DISCOVERY_RANGE:-LOCALHOST}
source /opt/ros/jazzy/setup.bash
source "$_odom_repo/limbo/install/local_setup.bash"
export ROS_DOMAIN_ID=$_odom_domain
export ROS_AUTOMATIC_DISCOVERY_RANGE=$_odom_discovery
export RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}
exec ros2 launch limbo_hardware encoders_odometry.launch.py "$@"
