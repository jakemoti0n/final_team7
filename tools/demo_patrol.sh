#!/usr/bin/env bash
# 시연용: 시뮬레이션을 띄우고, Nav2·위치 추정이 준비되면 순찰을 시작한다. Ctrl+C 한 번이면 전부 내려간다.
# 사용법: tools/demo_patrol.sh [월드] [지도] [waypoint 파일]
#   기본: aischool_2f aischool_2f_map aischool_waypoints.yaml
#   예:   tools/demo_patrol.sh aischool_2f_furnished aischool_2f_furnished_map aischool_furnished_waypoints.yaml
# 순찰 노드는 위치 추정을 30초만 기다리는데 시뮬레이션은 뜨는 데 1~2분 걸려서, 그냥 이어서 치면 시간 초과로 끝난다
WORLD=${1:-aischool_2f} MAP=${2:-aischool_2f_map} WAYPOINTS=${3:-aischool_waypoints.yaml}
source /opt/ros/jazzy/setup.bash; source ~/limbo/limbo/install/setup.bash; source ~/limbo/venvs/limbo_yolo/bin/activate
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-97} DISPLAY=${DISPLAY:-:1}
export __NV_PRIME_RENDER_OFFLOAD=${__NV_PRIME_RENDER_OFFLOAD:-1} __GLX_VENDOR_LIBRARY_NAME=${__GLX_VENDOR_LIBRARY_NAME:-nvidia}
[ -n "$XAUTHORITY" ] || export XAUTHORITY=/run/user/$(id -u)/gdm/Xauthority
cd ~/limbo/limbo
ros2 launch limbo_bringup start_simulation.launch.py world:=$WORLD map:=$MAP gui:=${GUI:-true} > /tmp/demo_sim.log 2>&1 &
LAUNCH=$!; echo $LAUNCH > /tmp/demo_sim.pid    # 다른 터미널에서 내리려면 kill -INT $(cat /tmp/demo_sim.pid). 백그라운드로 띄웠으면 launch가 INT를 무시하니 kill -TERM
trap 'echo; echo "끝내는 중"; kill -INT $LAUNCH 2>/dev/null; wait $LAUNCH 2>/dev/null; exit' INT TERM

echo "시뮬레이션 띄우는 중 ($WORLD). 로그: /tmp/demo_sim.log"
for i in $(seq 1 120); do
  grep -qE "Failed to bring up|process has died" /tmp/demo_sim.log && { echo "시작 실패. tail /tmp/demo_sim.log 로 확인"; kill -INT $LAUNCH; wait $LAUNCH; exit 1; }
  timeout 5 ros2 lifecycle get /bt_navigator 2>/dev/null | grep -q '^active' && break   # 'active'만 쓰면 inactive에도 맞는다
  sleep 2
done
for i in $(seq 1 40); do
  timeout 4 ros2 run tf2_ros tf2_echo map base_footprint 2>&1 | grep -q Translation && break
  sleep 2
done
sleep 3
echo "준비됨. 순찰 시작 ($WAYPOINTS)"
ros2 run limbo_patrol patrol_node --ros-args -p use_sim_time:=true -p waypoints:=$WAYPOINTS
echo "순찰 끝. 시뮬레이션은 계속 떠 있음. Ctrl+C 로 내림"
wait $LAUNCH
