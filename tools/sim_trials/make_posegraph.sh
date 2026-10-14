#!/usr/bin/env bash
# 사용법: make_posegraph.sh <월드> <지도이름>   — slam_toolbox 지도 작성 모드로 띄워 건물을 한 바퀴 돈 뒤
# 포즈그래프를 limbo_navigation/maps/<지도이름>_posegraph(.posegraph/.data)로 저장한다. localization:=slam이 이 파일을 쓴다
# 예: make_posegraph.sh aischool_2f aischool_2f_map
set +u
T=~/limbo/tools/sim_trials; R=~/limbo; OUT=$R/limbo/src/limbo_navigation/maps/$2_posegraph
source /opt/ros/jazzy/setup.bash; source $R/limbo/install/setup.bash; export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-97}
EXTRA_ARGS="localization:=mapping" WORLD=$1 MAP=$2 $T/sim_ctl.sh start posegraph_$2 || { $T/sim_ctl.sh stop; exit 1; }
cd /tmp
GOAL_TIMEOUT=120 timeout 900 python3 $T/nav_route.py box
GOAL_TIMEOUT=120 timeout 900 python3 $T/nav_route.py people
ros2 service call /slam_toolbox/serialize_map slam_toolbox/srv/SerializePoseGraph "{filename: '$OUT'}" | tail -1
sleep 2; ls -la $OUT.* 2>/dev/null
$T/sim_ctl.sh stop
