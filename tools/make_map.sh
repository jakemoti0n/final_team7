#!/usr/bin/env bash
# 지도 만들기. 따라 하면 limbo_navigation/maps/<이름>.pgm/.yaml 과 <이름>_posegraph 가 생긴다.
#
#   tools/make_map.sh start <이름> [월드]   지도 작성 스택을 뒤에서 띄운다 (RViz 창이 열림). 60 s마다 자동 저장
#   tools/make_map.sh drive                 이 터미널에서 키보드로 몬다 (게임패드는 start 때부터 됨: LB 누른 채 왼쪽 스틱)
#   tools/make_map.sh save                  지금까지를 저장한다 (몇 번이든)
#   tools/make_map.sh status                돌고 있는지, 마지막 자동 저장이 언제인지
#   tools/make_map.sh stop                  내린다 (저장 안 했으면 물어본다)
#   tools/make_map.sh resume <이름> [월드]  저장된 포즈그래프를 읽어 이어서 작성한다 (중간에 죽었을 때)
#
# 어디에 무엇이 남나: ~/limbo_bags/mapping/ 에 로그·PID·자동 저장 시각. 지도는 limbo_navigation/maps/ (src).
# 포즈그래프(큰 파일)는 저장소에 넣지 않는다(.gitignore). pgm/yaml만 커밋한다.
# (set -u는 쓰지 않는다: ROS setup.bash가 미정의 변수를 써서 걸린다)
R=~/limbo; MAPS=$R/limbo/src/limbo_navigation/maps; D=~/limbo_bags/mapping; mkdir -p $D
STAMP=$D/autosave_stamp; NAMEFILE=$D/current_map; PID_LAUNCH=$D/launch.pgid; PID_AUTO=$D/autosave.pid; SAVED=$D/saved_once
AUTOSAVE_SEC=${AUTOSAVE_SEC:-60}
source /opt/ros/jazzy/setup.bash; source $R/limbo/install/setup.bash; export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-97}

running() { [ -f $PID_LAUNCH ] && kill -0 -- -"$(cat $PID_LAUNCH)" 2>/dev/null; }

serialize() {   # 포즈그래프 저장 (slam_toolbox 서비스). $1 = 확장자 없는 경로
  timeout 30 ros2 service call /slam_toolbox/serialize_map slam_toolbox/srv/SerializePoseGraph "{filename: '$1'}" > /dev/null 2>&1
}

start_stack() {   # $1 이름, $2 월드, $3 이어서 읽을 포즈그래프(없으면 빈 문자열)
  running && { echo "이미 돌고 있다: $(cat $NAMEFILE). 먼저 stop"; exit 1; }
  echo "$1" > $NAMEFILE; rm -f $STAMP $SAVED
  export DISPLAY=${DISPLAY:-:1}
  # 빈 값은 launch 인자로 못 넘기므로(ros2 launch가 거부) 이어 하기일 때만 resume_from을 붙인다
  resume_arg=""; [ -n "$3" ] && resume_arg="resume_from:=$3"
  setsid ros2 launch limbo_bringup mapping.launch.py world:=$2 map_name:=$1 $resume_arg autosave_stamp_file:=$STAMP \
    > $D/launch_$1.log 2>&1 < /dev/null &
  echo $! > $PID_LAUNCH
  # 자동 저장: slam이 뜬 뒤부터 AUTOSAVE_SEC마다 <이름>_autosave 포즈그래프를 덮어쓴다
  ( while kill -0 -- -"$(cat $PID_LAUNCH)" 2>/dev/null; do
      sleep $AUTOSAVE_SEC
      if timeout 5 ros2 service type /slam_toolbox/serialize_map > /dev/null 2>&1; then
        serialize $MAPS/$1_autosave && touch $STAMP
      fi
    done ) > $D/autosave_$1.log 2>&1 &
  echo $! > $PID_AUTO
  echo "지도 작성 시작: $1 (월드 $2)$( [ -n "$3" ] && echo ", 이어서: $3" )"
  echo "→ 잠시 뒤 RViz 창에 지도가 쌓인다. 다른 터미널에서 'tools/make_map.sh drive'로 몰고, 'save'로 저장, 'stop'으로 내린다"
}

case "${1:-}" in
  start)
    [ -n "${2:-}" ] || { echo "사용법: make_map.sh start <이름> [월드]"; exit 1; }
    start_stack "$2" "${3:-human_test_world}" "" ;;
  resume)
    [ -n "${2:-}" ] || { echo "사용법: make_map.sh resume <이름> [월드]"; exit 1; }
    f=$MAPS/$2_autosave; [ -f $f.posegraph ] || f=$MAPS/$2_posegraph
    [ -f $f.posegraph ] || { echo "이어서 읽을 포즈그래프가 없다: $MAPS/$2_autosave 또는 $MAPS/$2_posegraph"; exit 1; }
    start_stack "$2" "${3:-human_test_world}" "$f" ;;
  drive)
    running || { echo "지도 작성이 안 돌고 있다. 먼저 start"; exit 1; }
    echo "키보드 조종: i 전진, , 후진, j/l 회전, k 정지, q/z 속도 ±10 %. 손을 떼면 0.5 s 뒤 선다(데드맨). 끝내려면 Ctrl+C"
    # 키보드 노드는 속도를 /drive/cmd로 내고, drive_gate가 상한·데드맨을 걸어 /cmd_vel을 낸다
    ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r cmd_vel:=/drive/cmd -p speed:=0.2 -p turn:=0.6 ;;
  save)
    running || { echo "지도 작성이 안 돌고 있다"; exit 1; }
    name=$(cat $NAMEFILE)
    echo "저장 중: $MAPS/$name ..."
    # pgm/yaml은 slam_toolbox의 저장 서비스로(map_saver_cli는 지도 구독 대기 2 s 안에 못 받으면 실패함, 2026-10-14)
    timeout 30 ros2 service call /slam_toolbox/save_map slam_toolbox/srv/SaveMap "{name: {data: '$MAPS/$name'}}" > $D/save_$name.log 2>&1
    serialize $MAPS/${name}_posegraph && touch $SAVED
    ls -la --time-style=+%H:%M:%S $MAPS/$name.pgm $MAPS/$name.yaml $MAPS/${name}_posegraph.posegraph 2>/dev/null | awk '{print $5, $6, $NF}'
    echo "→ 이 지도로 주행: ros2 launch limbo_bringup start_simulation.launch.py world:=<월드> map:=$name" ;;
  status)
    if running; then
      name=$(cat $NAMEFILE); echo "돌고 있음: $name"
      timeout 5 ros2 service type /slam_toolbox/serialize_map > /dev/null 2>&1 && echo "slam_toolbox: 살아 있음" || echo "slam_toolbox: 응답 없음 (죽었으면 stop 뒤 resume $name)"
      [ -f $STAMP ] && echo "마지막 자동 저장: $(( $(date +%s) - $(stat -c %Y $STAMP) )) s 전 ($MAPS/${name}_autosave)" || echo "자동 저장: 아직 없음"
      timeout 5 ros2 topic echo --once /map --field info 2>/dev/null | grep -E "resolution|width|height" | tr '\n' ' '; echo
    else echo "안 돌고 있음"; fi ;;
  stop)
    running || { echo "안 돌고 있음"; rm -f $PID_LAUNCH $PID_AUTO; exit 0; }
    name=$(cat $NAMEFILE)
    if [ ! -f $SAVED ] && [ -t 0 ]; then
      read -r -p "아직 save를 안 했다. 저장하고 내릴까? [Y/n] " a; [ "${a:-Y}" != "n" ] && "$0" save
    fi
    kill $(cat $PID_AUTO) 2>/dev/null
    G=$(cat $PID_LAUNCH); kill -INT -- -$G 2>/dev/null
    for i in $(seq 1 20); do kill -0 -- -$G 2>/dev/null || break; sleep 1; done
    kill -9 -- -$G 2>/dev/null; rm -f $PID_LAUNCH $PID_AUTO
    # launch가 죽은 뒤 남는 노드(self_filter 등)는 시험 도구의 정리 루틴으로 끝낸다
    $R/tools/sim_trials/sim_ctl.sh stop > /dev/null 2>&1
    echo "내렸다: $name" ;;
  *) sed -n '2,10p' "$0" ;;
esac
