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
  for p in $(ps -eo pid,args | awk '/[s]tart_simulation.launch|[g]z sim -r|[g]z sim server/{print $1}'); do kill -9 $p 2>/dev/null; done
  sleep 1
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
  for i in $(seq 1 90); do
    grep -qE "Failed to bring up|process has died" $LOG && return 1
    timeout 5 ros2 lifecycle get /bt_navigator 2>/dev/null | grep -q '^active' && break
    sleep 2
  done
  # 3분이 지나도 active가 아니면 실패로 본다. lifecycle 서비스 응답이 끊겨(collision_monitor change_state timeout) Nav2가
  # configure 단계에서 멈춘 채 TF만 나오는 경우가 있어서, TF만 보고 "준비됨"으로 넘기면 Goal이 영영 처리되지 않는다 (2026-10-13)
  timeout 5 ros2 lifecycle get /bt_navigator 2>/dev/null | grep -q '^active' || return 1
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
  echo "남은 gz: $(ps -eo args | grep -cE '^gz sim|^ruby .*gz sim')  남은 launch: $(ps -eo args | grep -c '[s]tart_simulation.launch')" ;;
esac
