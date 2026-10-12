#!/usr/bin/env bash
# 사용법: record_drive.sh <라벨> <box|people>  — 띄우고, 경로를 돌며 헛돎 판단용 데이터를 녹화하고, 끈다
D=$(cd "$(dirname "$0")" && pwd); LOGS=~/limbo_bags/sim_trials/logs; mkdir -p $LOGS
$D/sim_ctl.sh start $1 || { $D/sim_ctl.sh stop; exit 1; }
source /opt/ros/jazzy/setup.bash; export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-97}; cd /tmp
python3 $D/slip_record.py $LOGS/slip_$1.pkl $LOGS/stop_$1 & R=$!
timeout 900 python3 $D/nav_route.py $2
touch $LOGS/stop_$1; wait $R; rm -f $LOGS/stop_$1
$D/sim_ctl.sh stop
echo "노드 로그의 판단: $(grep -cE 'SUSPECT:' $LOGS/sim_$1.log)번 의심, $(grep -c 'Wheel slip detected' $LOGS/sim_$1.log)번 확정"
