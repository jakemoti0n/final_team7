#!/usr/bin/env bash
# 사용법: run_angles.sh [라벨 접두]   — 카메라 배치 4가지(지금 0.5 m 수평, 0.7 m 12°·15°·18°)마다 사람 검출(50 s)과 상자 costmap(25 s)을 잰다
# 결과: experiments/2026-10-14_camera_angle/results_<라벨>.txt
set +u   # ROS setup.bash가 정의 안 된 변수를 써서 -u를 켤 수 없다
T=~/limbo/tools/sim_trials; R=~/limbo; D=$R/experiments/2026-10-14_camera_angle
W=$R/limbo/install/limbo_simulation/share/limbo_simulation/worlds
cp $D/worlds/zz_cam_person.sdf $D/worlds/zz_cam_box.sdf $W/
source /opt/ros/jazzy/setup.bash; source $R/limbo/install/setup.bash; export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-97}
OUT=$D/results_${1:-run}.txt; : > $OUT
echo "커밋 $(git -C $R rev-parse --short HEAD) $(date +%F_%H:%M)" | tee -a $OUT
for cfg in "0.50 0 base" "0.70 12 p12" "0.70 15 p15" "0.70 18 p18"; do
  set -- $cfg; Z=$1; P=$2; L=$3
  export EXTRA_ARGS="camera_z:=$Z camera_pitch_deg:=$P" LABEL="$L (z=$Z, pitch=$P)"
  echo "=== $L 사람 $(date +%H:%M)" | tee -a $OUT
  WORLD=zz_cam_person MAP=human_test_map $T/sim_ctl.sh start cam_${L}_person > /dev/null && \
    python3 $D/camera_probe.py person 50 $W/zz_cam_person.sdf 2>&1 | tee -a $OUT
  $T/sim_ctl.sh stop > /dev/null
  echo "=== $L 상자 $(date +%H:%M)" | tee -a $OUT
  WORLD=zz_cam_box MAP=human_test_map $T/sim_ctl.sh start cam_${L}_box > /dev/null && \
    python3 $D/camera_probe.py box 25 2>&1 | tee -a $OUT
  $T/sim_ctl.sh stop > /dev/null
done
rm -f $W/zz_cam_person.sdf $W/zz_cam_box.sdf
echo "=== 끝 $(date +%H:%M)" | tee -a $OUT
