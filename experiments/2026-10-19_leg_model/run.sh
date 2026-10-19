#!/usr/bin/env bash
# 사용법: [PREFIX=leg2] run.sh <base|cand> <approach|corr> <회차>  (yaml은 시작 때 내용으로 되돌림)
set +u
H=$(cd "$(dirname "$0")" && pwd); T=~/limbo/tools/sim_trials; R=~/limbo; LOGS=~/limbo_bags/sim_trials/logs
Y=$R/limbo/src/limbo_perception/config/person_detector.yaml; M=$R/limbo/src/limbo_perception/models/leg_512.pt
export ROS_DOMAIN_ID=97 GOAL_TIMEOUT=90
L=${PREFIX:-leg}_${1}_${2}_$3; B=$(mktemp); cp $Y $B
if [ $2 = approach ]; then export WORLD=zz_social_approach MAP=aischool_2f_map; ROUTE=hall; else export WORLD=aischool_2f_social MAP=aischool_2f_map; ROUTE=people2; fi
if [ $1 = cand ]; then
  sed -i 's/^      classes: \[0\] /      classes: [0, 1] /; s/^      imgsz: 640 /      imgsz: 512 /' $Y
  grep -q 'classes: \[0, 1\]' $Y && grep -q 'imgsz: 512' $Y || { echo yaml 바꾸기 실패; exit 1; }
  export EXTRA_ARGS="person_model:=$M"
else unset EXTRA_ARGS; fi
BEFORE=$(ls ~/limbo_results/*.csv 2>/dev/null | wc -l)
echo "=== $L $(date +%H:%M:%S) 커밋 $(git -C $R rev-parse --short HEAD)"
$T/sim_ctl.sh start $L || { $T/sim_ctl.sh stop; cp $B $Y; exit 1; }
source /opt/ros/jazzy/setup.bash; source $R/limbo/install/setup.bash; cd /tmp
python3 $H/rec.py $H/$L.json > $H/$L.rec.log 2>&1 & RP=$!
sleep 2
timeout 900 python3 $T/nav_route.py $ROUTE > $LOGS/trial_$L.nav.log 2>&1
sleep 2; kill -INT $RP; wait $RP
$T/sim_ctl.sh stop
cp $B $Y; rm -f $B
if [ "$(ls ~/limbo_results/*.csv | wc -l)" -gt "$BEFORE" ]; then cp $(ls -t ~/limbo_results/*.csv | head -1) $LOGS/trial_$L.csv; else echo "CSV 없음"; fi
cat $H/$L.rec.log; tail -3 $LOGS/trial_$L.nav.log; grep -m1 "모델 " $LOGS/sim_$L.log
