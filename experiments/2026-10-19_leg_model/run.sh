#!/usr/bin/env bash
# 사용법: [PREFIX=leg2] [DIAG=<png 폴더>] [MODEL=<.pt>] run.sh <base|cand|porto> <approach|corr> <회차>  (yaml은 시작 때 내용으로 되돌림)
set +u
H=$(cd "$(dirname "$0")" && pwd); T=~/limbo/tools/sim_trials; R=~/limbo; LOGS=~/limbo_bags/sim_trials/logs
Y=$R/limbo/src/limbo_perception/config/person_detector.yaml
export ROS_DOMAIN_ID=97 GOAL_TIMEOUT=90
L=${PREFIX:-leg}_${1}_${2}_$3; B=$(mktemp); cp $Y $B
# zz_social_* 월드는 저장소 experiments 폴더에만 있어 설치 폴더에 복사해야 Gazebo가 찾는다 (10-20: 없어서 3번 다 시작 실패)
D=$R/experiments/2026-10-14_social_people/worlds; cp $D/zz_social_*.sdf $D/zz_social_*_movers.json $R/limbo/install/limbo_simulation/share/limbo_simulation/worlds/
if [ $2 = approach ]; then export WORLD=zz_social_approach MAP=aischool_2f_map; ROUTE=hall; else export WORLD=aischool_2f_social MAP=aischool_2f_map; ROUTE=people2; fi
# 3차부터 yaml 기본이 하반신 모델(cand). base는 기존 yolo11n으로 바꿔 돌림
if [ $1 = base ]; then
  sed -i 's/^      classes: \[0, 1\] /      classes: [0] /; s/^      imgsz: 512 /      imgsz: 640 /' $Y
  grep -q 'classes: \[0\] ' $Y && grep -q 'imgsz: 640' $Y || { echo yaml 바꾸기 실패; cp $B $Y; exit 1; }
  export EXTRA_ARGS="person_model:=yolo11n.pt"
elif [ $1 = porto ]; then
  # 팀원 1단계 모델(person_leg_stage1, 입력 640, 10-08). MODEL=<.pt 절대 경로>로 준다. 클래스는 [0,1] 그대로
  sed -i 's/^      imgsz: 512 /      imgsz: 640 /' $Y
  grep -q 'imgsz: 640' $Y || { echo yaml 바꾸기 실패; cp $B $Y; exit 1; }
  export EXTRA_ARGS="person_model:=${MODEL:?MODEL=<porto_leg.pt 경로>}"
else unset EXTRA_ARGS; fi
BEFORE=$(ls ~/limbo_results/*.csv 2>/dev/null | wc -l)
echo "=== $L $(date +%H:%M:%S) 커밋 $(git -C $R rev-parse --short HEAD)"
$T/sim_ctl.sh start $L || { $T/sim_ctl.sh stop; cp $B $Y; exit 1; }
source /opt/ros/jazzy/setup.bash; source $R/limbo/install/setup.bash; cd /tmp
python3 $H/rec.py $H/$L.json > $H/$L.rec.log 2>&1 & RP=$!
# DIAG=<폴더>면 오검출 자리가 보일 때 박스 그린 RGB를 PNG로 저장 (diag.py)
if [ -n "$DIAG" ]; then python3 $H/diag.py $DIAG > $H/$L.diag.log 2>&1 & DP=$!; fi
sleep 2
timeout 900 python3 $T/nav_route.py $ROUTE > $LOGS/trial_$L.nav.log 2>&1
sleep 2; kill -INT $RP; wait $RP; [ -n "$DP" ] && { kill -INT $DP; wait $DP; cat $H/$L.diag.log; }
$T/sim_ctl.sh stop
cp $B $Y; rm -f $B
if [ "$(ls ~/limbo_results/*.csv | wc -l)" -gt "$BEFORE" ]; then cp $(ls -t ~/limbo_results/*.csv | head -1) $LOGS/trial_$L.csv; else echo "CSV 없음"; fi
cat $H/$L.rec.log; tail -3 $LOGS/trial_$L.nav.log; grep -m1 "모델 " $LOGS/sim_$L.log
