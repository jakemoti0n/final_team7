#!/usr/bin/env bash
# Run from any directory. Source the existing OAK environment first if combining inputs.
set -eo pipefail
_encoder_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
_encoder_domain=${ROS_DOMAIN_ID:-97}
_encoder_discovery=${ROS_AUTOMATIC_DISCOVERY_RANGE:-LOCALHOST}
source /opt/ros/jazzy/setup.bash
source "$_encoder_repo/limbo/install/local_setup.bash"
export ROS_DOMAIN_ID=$_encoder_domain
export ROS_AUTOMATIC_DISCOVERY_RANGE=$_encoder_discovery
export RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}
exec ros2 launch limbo_hardware encoders_readonly.launch.py "$@"
