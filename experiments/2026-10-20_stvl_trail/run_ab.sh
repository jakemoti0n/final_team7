#!/usr/bin/env bash
# 지역 STVL 잔상이 멈칫거림을 늘리는지: A(지금) vs B(지역 STVL mark에 사람 점 제외) × 장면 2개 × 3회
#  장면 corr: aischool_2f_social, 경로 people2 (비켜 주는 사람 한 명이 위 복도를 왕복 → 마주 오기·같은 방향)
#  장면 cross: zz_cross(= aischool_2f_social 사본), 경로 hall (사람이 홀 x -2.5에서 y -1.0~1.5를 왕복해 로봇 진로를 가로지름)
# 회차마다 stvl_trail.py로 사람 뒤 치명 칸을 잼. 사용법: run_ab.sh <라벨접두>
set +u
T=~/limbo/tools/sim_trials; R=~/limbo; E=$R/experiments/2026-10-20_stvl_trail; LOGS=~/limbo_bags/sim_trials/logs
W=$R/limbo/install/limbo_simulation/share/limbo_simulation/worlds; NAV=$R/limbo/src/limbo_navigation/config/nav2_params.yaml
sed 's/aischool_2f_social/zz_cross/g' $R/limbo/src/limbo_simulation/worlds/aischool_2f_social.sdf > $W/zz_cross.sdf; cp $E/zz_cross_movers.json $W/
git -C $R checkout -- $NAV
run() {  # 라벨 월드 경로
  $T/sim_ctl.sh stop >/dev/null 2>&1
  ( source /opt/ros/jazzy/setup.bash; export ROS_DOMAIN_ID=97; cd /tmp; sleep 60; exec python3 $T/stvl_trail.py 600 ) > $LOGS/trail_$1.log 2>&1 &
  TP=$!
  GOAL_TIMEOUT=90 WORLD=$2 MAP=aischool_2f_map $T/trial.sh $1 $3 > $LOGS/trial_$1.out 2>&1
  kill $TP 2>/dev/null; sleep 1; kill -9 $TP 2>/dev/null
  echo "$1 $(date +%H:%M): $(grep -E '→' $LOGS/trial_$1.nav.log | tr '\n' ' ')"
}
for cond in A B; do
  git -C $R checkout -- $NAV
  if [ $cond = B ]; then
    sed -i '287s|/mid360/points_filtered$|/mid360/points_filtered_nopeople|; 356s|/rgbd_camera/points$|/rgbd_camera/points_nopeople|' $NAV
  fi
  echo "=== $cond 설정 차이: $(git -C $R diff --no-color $NAV | grep -c '^+ ')줄 커밋 $(git -C $R rev-parse --short HEAD)"
  for i in 1 2 3; do
    run ${1}_${cond}_corr$i aischool_2f_social people2
    run ${1}_${cond}_cross$i zz_cross hall
  done
done
git -C $R checkout -- $NAV; rm -f $W/zz_cross.sdf $W/zz_cross_movers.json
echo "=== 끝 $(date +%H:%M)"
