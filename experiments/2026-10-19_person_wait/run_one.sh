#!/usr/bin/env bash
# 사용법: run_one.sh <라벨> <경로> [진단 폴더]  — WORLD·MAP 환경변수로 월드를 고른다.
# trial.sh와 같되, 주행하는 동안 close_diag.py(코앞 트랙 소실 진단)를 같이 돌릴 수 있다
T=~/limbo/tools/sim_trials; LOGS=~/limbo_bags/sim_trials/logs; E=$(cd "$(dirname "$0")" && pwd)
BEFORE=$(ls ~/limbo_results/*.csv 2>/dev/null | wc -l)
$T/sim_ctl.sh start $1 || { $T/sim_ctl.sh stop; exit 1; }
source /opt/ros/jazzy/setup.bash; source ~/limbo/limbo/install/setup.bash; export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-97}; cd /tmp
# MOVER: 월드 json 대신 따로 사람을 움직이는 명령(앞에 서는 사람 시나리오). PID로 끈다
[ -n "$MOVER" ] && { $MOVER > $LOGS/trial_$1.mover.log 2>&1 & MPID=$!; }
if [ -n "$3" ]; then ~/limbo/venvs/limbo_yolo/bin/python $E/close_diag.py $3 > $LOGS/diag_$1.log 2>&1 & DIAG=$!; fi
timeout 900 python3 $T/nav_route.py $2 > $LOGS/trial_$1.nav.log 2>&1
[ -n "$DIAG" ] && { kill -INT $DIAG; wait $DIAG; }
[ -n "$MPID" ] && { kill $MPID 2>/dev/null; wait $MPID 2>/dev/null; }
sleep 2
$T/sim_ctl.sh stop
if [ "$(ls ~/limbo_results/*.csv | wc -l)" -gt "$BEFORE" ]; then cp $(ls -t ~/limbo_results/*.csv | head -1) $LOGS/trial_$1.csv; else echo "이번 실행의 CSV 없음"; fi
