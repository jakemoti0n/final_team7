#!/usr/bin/env bash
# 이전 로봇(robot:=legacy)으로 오늘 월드 두 명 조건 1회 (people2, 제한 60초). 통과하면 사람을 뚫은 것
T=/home/kim/limbo/tools/sim_trials; R=/home/kim/limbo
P=$(ps -eo pid,args | awk '/[p]ass_single2.sh/{print $1; exit}'); [ -n "$P" ] && while kill -0 $P 2>/dev/null; do sleep 10; done
git -C $R checkout -- limbo/src/limbo_navigation/config/nav2_params.yaml
echo "=== 이전 로봇 두명 $(date +%H:%M)"; GOAL_TIMEOUT=60 EXTRA_ARGS="robot:=legacy" $T/trial.sh c_pair_legacy people2 | tail -1
echo "=== 끝 $(date +%H:%M)"
