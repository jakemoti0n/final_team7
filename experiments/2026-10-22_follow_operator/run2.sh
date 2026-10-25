#!/usr/bin/env bash
# 따라가기 2단계(주행): 운용자가 홀 → 오른쪽 복도(모퉁이) → 위쪽 복도로 약 19 m 걷고(0.5 m/s) 선다. 홀에서 사람 한 명이 가로지른다.
# 등록 → /follow/start → 운용자 출발 신호(/follow/go) → 기록 → 분석. 사용법: run2.sh <라벨> [초(기본 150)]
set +u
L=$1; DUR=${2:-150}; R=~/limbo; E=$R/experiments/2026-10-22_follow_operator; T=$R/tools/sim_trials; LOGS=~/limbo_bags/sim_trials/logs
OUT=~/limbo_bags/follow_rec; mkdir -p $OUT
W=$R/limbo/install/limbo_simulation/share/limbo_simulation/worlds
python3 - "$R/limbo/src/limbo_simulation/worlds/aischool_2f_social.sdf" "$E/band_model.sdf" "$W/zz_follow2.sdf" <<'PY'
import sys, re
src, band, dst = sys.argv[1:4]
s = open(src).read().replace('aischool_2f_social', 'zz_follow2')
actor = re.search(r'    <actor name="walker_yield">.*?</actor>\n', s, re.S).group(0)
s = re.sub(r'    <actor name="walker_yield">.*?</actor>\n    <actor name="walker_noyield">.*?</actor>\n', '', s, flags=re.S)
s = s.replace('  </world>', open(band).read() + ''.join(actor.replace('walker_yield', n) for n in ('operator', 'crosser_a')) + '  </world>')
open(dst, 'w').write(s)
PY
cp $E/zz_follow2_movers.json $W/
source /opt/ros/jazzy/setup.bash; source $R/limbo/install/setup.bash; source $R/venvs/limbo_yolo/bin/activate; export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-97}
$T/sim_ctl.sh stop >/dev/null 2>&1
rm -f ~/.limbo/follow_operator.json
echo "##### $L 시작 $(date +%H:%M:%S) 커밋 $(git -C $R rev-parse --short HEAD)"
WORLD=zz_follow2 MAP=aischool_2f_map $T/sim_ctl.sh start $L || { echo "시뮬 시작 실패"; exit 1; }
( cd /tmp; exec python3 $E/rec2.py $OUT/$L.json ) > $LOGS/follow_rec_$L.log 2>&1 &
REC=$!
BAGP=""
if [ "${BAG:-0}" = 1 ]; then   # 주행이 멈추는 원인을 볼 때: 코스트맵·속도 명령·경로를 같이 녹화 (ros2 bag, SIGINT로만 끝냄)
  rm -rf $OUT/${L}_bag
  ( cd /tmp; exec ros2 bag record -o $OUT/${L}_bag /cmd_vel /cmd_vel_nav /cmd_vel_smoothed /plan /goal_update /local_costmap/costmap \
      /follow/state /follow/target /person_wait /collision_monitor_state /tf /tf_static /sim/people ) > $LOGS/bag_$L.log 2>&1 &
  BAGP=$!
fi
for i in $(seq 1 60); do
  r=$(python3 $E/svc.py call /follow/enroll 5 2>/dev/null)
  echo "$(date +%H:%M:%S) enroll: $r"; echo "$r" | grep -q "success=True" && break; sleep 1
done
for i in $(seq 1 30); do
  r=$(python3 $E/svc.py call /follow/start 8 2>/dev/null)
  echo "$(date +%H:%M:%S) start: $r"; echo "$r" | grep -q "success=True" && break; sleep 1
done
echo "$r" | grep -q "success=True" || { echo "따라가기 시작 실패 → 중단"; kill -INT $REC; $T/sim_ctl.sh stop >/dev/null 2>&1; exit 1; }
sleep 2; python3 $E/svc.py pub /follow/go >/dev/null 2>&1; echo "$(date +%H:%M:%S) 운용자 출발 신호"
sleep $DUR
python3 $E/svc.py call /follow/stop 8 >/dev/null 2>&1
kill -INT $REC; wait $REC 2>/dev/null
[ -n "$BAGP" ] && { kill -INT $BAGP; wait $BAGP 2>/dev/null; }
$T/sim_ctl.sh stop >/dev/null 2>&1
rm -f $W/zz_follow2.sdf $W/zz_follow2_movers.json
echo "##### $L 끝 $(date +%H:%M:%S)"
python3 $E/ana2.py $OUT/$L.json
