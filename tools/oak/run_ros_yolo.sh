#!/usr/bin/env bash
set -eo pipefail
_oak_tools=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
_oak_yolo_repo=$(cd -- "$_oak_tools/../.." && pwd)
source "$_oak_tools/ros_input_env.sh"
_yolo_python=${LIMBO_YOLO_PYTHON:-"$_oak_yolo_repo/venvs/limbo_yolo/bin/python"}
if [[ ! -x "$_yolo_python" ]]; then
    printf 'Missing YOLO Python: %s\n' "$_yolo_python" >&2
    exit 1
fi
_perception_share=$(ros2 pkg prefix --share limbo_perception)
# Prevent inference/tracking from silently changing NumPy or other dependencies.
export YOLO_AUTOINSTALL=false
exec "$_yolo_python" -m limbo_perception.person_detector --ros-args \
    --params-file "$_perception_share/config/person_detector.yaml" \
    --params-file "$_perception_share/config/person_detector_oak_ros.yaml" "$@"
