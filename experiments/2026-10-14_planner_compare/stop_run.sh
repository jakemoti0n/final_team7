#!/usr/bin/env bash
# run.sh와 그 trial을 멈춘다. 명령줄 두 번째 칸이 스크립트 경로인 bash만 고른다(인자에 같은 문자열을 든 다른 셸은 안 잡힘)
pids=$(ps -eo pid,args | awk '$2 ~ /bash$/ && ($3 ~ /_compare\/run\.sh$/ || ($3 ~ /trial\.sh$/)) {print $1}')
[ -n "$pids" ] && echo "멈춤: $pids" && kill -TERM $pids 2>/dev/null
sleep 2
~/limbo/tools/sim_trials/sim_ctl.sh stop
