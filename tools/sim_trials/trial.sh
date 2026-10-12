#!/usr/bin/env bash
# 사용법: trial.sh <라벨> <box|people>  — 띄우고 경로를 돌고 끈 뒤, 이번 실행의 측정 CSV를 logs/trial_<라벨>.csv로 남긴다
D=$(cd "$(dirname "$0")" && pwd); LOGS=~/limbo_bags/sim_trials/logs; mkdir -p $LOGS
BEFORE=$(ls ~/limbo_results/*.csv 2>/dev/null | wc -l)
$D/sim_ctl.sh start $1 || { $D/sim_ctl.sh stop; exit 1; }
source /opt/ros/jazzy/setup.bash; export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-97}; cd /tmp
timeout 900 python3 $D/nav_route.py $2 > $LOGS/trial_$1.nav.log 2>&1
sleep 2
$D/sim_ctl.sh stop
if [ "$(ls ~/limbo_results/*.csv | wc -l)" -gt "$BEFORE" ]; then cp $(ls -t ~/limbo_results/*.csv | head -1) $LOGS/trial_$1.csv; else echo "이번 실행의 CSV 없음"; fi
