#!/usr/bin/env bash
# 사용법: sim_ctl.sh start <로그이름> | stop
# 시뮬레이션(기본은 시나리오 월드, WORLD·MAP 환경변수로 바꿈)을 자기 프로세스 그룹으로 띄우고, 끌 때는 그 그룹만 정리한다.
# 시작할 때 부하가 몰려 Nav2 lifecycle이 시간 초과로 실패하는 경우가 있어 최대 3번 다시 띄운다
D=$(cd "$(dirname "$0")" && pwd); LOGS=~/limbo_bags/sim_trials/logs; mkdir -p $LOGS; PIDFILE=$LOGS/sim.pgid

stop_sim() {
  G=$(cat $PIDFILE 2>/dev/null)
  [ -n "$G" ] && kill -INT -- -$G 2>/dev/null
  for i in $(seq 1 20); do pgrep -g "$G" >/dev/null 2>&1 || break; sleep 1; done
  [ -n "$G" ] && kill -9 -- -$G 2>/dev/null
  # 프로세스 그룹 kill로 안 죽고 남은 launch·gz가 있으면 PID로 끝낸다 (2026-10-13: 남은 launch가 쌓여 다음 회차의 map_server까지 실패함).
  # 자기 셸은 이 패턴과 일치하지 않는다 (sim_ctl.sh stop)
  # 명령줄 첫 칸이 실행 파일인 것만 (인자에 같은 문자열을 든 셸은 안 잡힘 — 2026-10-14 그걸로 호출한 셸이 세 번 죽음)
  for p in $(ps -eo pid,args | awk '($2=="/usr/bin/python3" && $4=="launch" && $6 ~ /start_simulation/) || ($2=="gz" && $3=="sim") || ($2=="ruby" && $4=="sim") {print $1}'); do kill -9 $p 2>/dev/null; done
  sleep 1
  sweep_nodes
}

# launch가 죽은 뒤에도 남는 노드들을 실행 파일 이름으로 찾아 끝낸다. gz transport를 쓰는 파이썬 노드는 SIGINT·SIGTERM을 삼키고,
# launch가 먼저 죽으면 자식이 고아가 되어 남는다 (2026-10-14: 남은 ekf_node·parameter_bridge가 TF·/clock을 또 내서 다음 시뮬의
# AMCL이 스캔을 전부 버리고 시작이 3번 다 실패함). 이 컴퓨터에서 시뮬레이션은 한 번에 하나라는 전제
sweep_nodes() {
  # 명령줄이 노드 실행 파일로 시작하는 것만(셸이 이 문자열을 인자로 들고 있어도 안 잡힘)
  local pat='^ *[0-9]+ (/usr/bin/python3 /opt/ros/jazzy/bin/ros2 bag record|/home/kim/limbo/limbo/install/(robot_self_filter|limbo_drive|limbo_perception|limbo_evaluation|limbo_monitor|limbo_patrol)/lib/|/opt/ros/jazzy/lib/(ros_gz_bridge|robot_state_publisher|robot_localization|nav2_|opennav_docking|rviz2|pointcloud_to_laserscan|slam_toolbox)|/opt/ros/jazzy/lib/ros_gz_sim/create|/home/kim/limbo/venvs/[^ ]+/bin/python /home/kim/limbo/limbo/install/(limbo_perception|limbo_evaluation|limbo_monitor)/|python3 /home/kim/limbo/limbo/install/limbo_simulation/share/limbo_simulation/scripts/|/usr/bin/python3 /opt/ros/jazzy/bin/ros2 launch limbo_bringup)'
  local pids=$(ps -eo pid,args | grep -E "$pat" | awk '{print $1}')
  [ -z "$pids" ] && return
  echo "남은 노드 정리: $pids"
  kill -TERM $pids 2>/dev/null; sleep 3; kill -KILL $pids 2>/dev/null; sleep 1
}

start_once() {   # 0: 준비됨, 1: 실패
  local LOG=$1
  source /opt/ros/jazzy/setup.bash; source ~/limbo/limbo/install/setup.bash; source ~/limbo/venvs/limbo_yolo/bin/activate
  # 화면·GPU 설정은 이미 있으면 그대로 쓴다 (컴퓨터마다 다름). 기본값은 NVIDIA 노트북(PRIME) 기준
  export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-97} DISPLAY=${DISPLAY:-:1}
  export __NV_PRIME_RENDER_OFFLOAD=${__NV_PRIME_RENDER_OFFLOAD:-1} __GLX_VENDOR_LIBRARY_NAME=${__GLX_VENDOR_LIBRARY_NAME:-nvidia}
  [ -n "$XAUTHORITY" ] || export XAUTHORITY=/run/user/$(id -u)/gdm/Xauthority
  cd ~/limbo/limbo
  setsid ros2 launch limbo_bringup start_simulation.launch.py world:=${WORLD:-aischool_2f_scenarios} map:=${MAP:-aischool_2f_map} gui:=false record:=true ${EXTRA_ARGS} \
    > $LOG 2>&1 < /dev/null &
  echo $! > $PIDFILE
  # ros2 CLI는 데몬으로 노드를 찾는데, 시뮬보다 먼저 떠 있던 데몬이 새 노드를 못 보는 일이 있다(2026-10-14: Nav2는 7초 만에
  # 전부 active인데 `ros2 lifecycle get`이 Node not found → 3번 다 시작 실패 판정). 대기 직전에 데몬을 새로 띄우고 10초를 준다
  sleep 10; ros2 daemon stop > /dev/null 2>&1; ros2 daemon start > /dev/null 2>&1; sleep 2
  for i in $(seq 1 90); do
    grep -qE "Failed to bring up|process has died" $LOG && return 1
    timeout 10 ros2 lifecycle get /bt_navigator 2>/dev/null | grep -q '^active' && break
    sleep 2
  done
  # 3분이 지나도 active가 아니면 실패로 본다. lifecycle 서비스 응답이 끊겨(collision_monitor change_state timeout) Nav2가
  # configure 단계에서 멈춘 채 TF만 나오는 경우가 있어서, TF만 보고 "준비됨"으로 넘기면 Goal이 영영 처리되지 않는다 (2026-10-13)
  timeout 10 ros2 lifecycle get /bt_navigator 2>/dev/null | grep -q '^active' || return 1
  # AMCL이 map → base_footprint를 내야 Nav2가 Goal을 받는다
  for i in $(seq 1 30); do
    timeout 4 ros2 run tf2_ros tf2_echo map base_footprint 2>&1 | grep -q Translation && { sleep 3; return 0; }
    sleep 2
  done
  return 1
}

case "$1" in
start)
  for attempt in 1 2 3; do
    start_once $LOGS/sim_$2.log && { echo ready; exit 0; }
    echo "시작 실패 ($attempt번째), 다시 띄움"; cp $LOGS/sim_$2.log $LOGS/sim_$2.fail$attempt.log; stop_sim
  done
  echo "3번 모두 실패"; exit 1 ;;
stop)
  stop_sim
  echo "남은 gz: $(ps -eo args | grep -cE '^gz sim|^ruby .*gz sim')  남은 launch: $(ps -eo args | grep -c '[s]tart_simulation.launch')"
  # SIGKILL로 끝난 노드가 남긴 Fast DDS 공유 메모리 포트 파일이 잠긴 채 남으면 다음 시작에서 모든 노드가
  # "Failed init_port fastrtps_port...: open_and_lock_file failed"로 통신을 못 해 Nav2가 3번 다 실패한다 (2026-10-14).
  # ROS·gz 프로세스가 하나도 없을 때만 daemon을 멈추고 지운다 (다른 ROS 프로세스가 있으면 건드리지 않는다)
  if [ "$(ps -eo args | grep -E '^(/opt/ros|gz sim|/home/kim/limbo/venvs|/usr/bin/python3 /opt/ros)' | grep -vc 'ros2-daemon')" = "0" ]; then
    ros2 daemon stop > /dev/null 2>&1; rm -f /dev/shm/fastrtps_* 2>/dev/null; ros2 daemon start > /dev/null 2>&1; echo "DDS 공유 메모리 정리"
  fi ;;
esac
