# Source this file in every shell using the tested Limbo OAK ROS input.
# Kept separate from the DepthAI v2/YOLO virtual environments.
# Capture requested defaults before ROS setup may supply SUBNET.
_limbo_domain=${ROS_DOMAIN_ID:-97}
_limbo_discovery=${ROS_AUTOMATIC_DISCOVERY_RANGE:-LOCALHOST}
_limbo_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
_limbo_ws=${LIMBO_ROS_WS:-"$_limbo_repo/limbo"}
_limbo_oak_ws=${LIMBO_OAK_COMPAT_WS:-"$HOME/limbo_oak_ros_compat"}
for _limbo_setup in /opt/ros/jazzy/setup.bash "$_limbo_ws/install/local_setup.bash" "$_limbo_oak_ws/install/local_setup.bash"; do
    if [[ ! -r "$_limbo_setup" ]]; then
        printf 'Missing ROS setup: %s\n' "$_limbo_setup" >&2
        return 1
    fi
done
source /opt/ros/jazzy/setup.bash || return
source "$_limbo_ws/install/local_setup.bash" || return
source "$_limbo_oak_ws/install/local_setup.bash" || return
for _limbo_package in depthai_v3 depthai_bridge_v3 depthai_ros_driver_v3; do
    _limbo_prefix=$(ros2 pkg prefix "$_limbo_package") || return
    if [[ "$_limbo_prefix" != "$_limbo_oak_ws/install/$_limbo_package" ]]; then
        printf 'Expected compatibility overlay for %s, found: %s\n' "$_limbo_package" "$_limbo_prefix" >&2
        return 1
    fi
done
export DEPTHAI_AUTOCALIBRATION=OFF
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_DOMAIN_ID=$_limbo_domain
export ROS_AUTOMATIC_DISCOVERY_RANGE=$_limbo_discovery
_limbo_share=$(ros2 pkg prefix --share limbo_bringup) || return
_limbo_profile="$_limbo_share/config/fastdds_camera.xml"
if [[ ! -r "$_limbo_profile" ]]; then
    printf 'Missing Fast DDS transport profile: %s\n' "$_limbo_profile" >&2
    return 1
fi
export FASTRTPS_DEFAULT_PROFILES_FILE="$_limbo_profile"
# This XML changes transports only; retain rmw_fastrtps publication/QoS defaults.
unset RMW_FASTRTPS_USE_QOS_FROM_XML
unset _limbo_domain _limbo_discovery _limbo_share _limbo_profile _limbo_setup _limbo_package _limbo_prefix _limbo_ws _limbo_oak_ws _limbo_repo
