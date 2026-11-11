#!/usr/bin/env bash
# Starts only the no-actuation Twist-to-wheel-target preview node.
set -eo pipefail
_preview_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
_preview_domain=${ROS_DOMAIN_ID:-97}
_preview_discovery=${ROS_AUTOMATIC_DISCOVERY_RANGE:-LOCALHOST}
source /opt/ros/jazzy/setup.bash
source "$_preview_repo/limbo/install/local_setup.bash"
export ROS_DOMAIN_ID=$_preview_domain
export ROS_AUTOMATIC_DISCOVERY_RANGE=$_preview_discovery
export RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}
exec ros2 launch limbo_hardware drive_preview.launch.py "$@"
