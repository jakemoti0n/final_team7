#!/usr/bin/env bash
set -eo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/ros_input_env.sh"
exec ros2 launch limbo_bringup start_oak_camera.launch.py "$@"
