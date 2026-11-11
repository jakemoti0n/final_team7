#!/usr/bin/env bash
# Opens one explicitly enabled, finite bench session; sends no ROS start command.
set -eo pipefail
_speed_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
_speed_domain=${ROS_DOMAIN_ID:-97}
_speed_discovery=${ROS_AUTOMATIC_DISCOVERY_RANGE:-LOCALHOST}
source /opt/ros/jazzy/setup.bash
source "$_speed_repo/limbo/install/local_setup.bash"
export ROS_DOMAIN_ID=$_speed_domain
export ROS_AUTOMATIC_DISCOVERY_RANGE=$_speed_discovery
export RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}
exec ros2 launch limbo_hardware speed_bench.launch.py "$@"
