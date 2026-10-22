#!/usr/bin/env bash
# 따라가기 1단계: 로봇은 출발점(0,0)에 서 있고 운용자(밴드)가 앞 1.8~4 m를 돌며 다른 두 사람이 가로지른다.
# 등록 → 기록(기본 180 s) → 분석. 사용법: run.sh <라벨> [초]
set +u
L=$1; DUR=${2:-180}; R=~/limbo; E=$R/experiments/2026-10-22_follow_operator; T=$R/tools/sim_trials; LOGS=~/limbo_bags/sim_trials/logs
OUT=~/limbo_bags/follow_rec; mkdir -p $OUT
W=$R/limbo/install/limbo_simulation/share/limbo_simulation/worlds
# 월드: 소셜 월드 사본에 밴드 모델을 넣고, 소셜 사람 2명은 이 장면의 3명으로 바꾼다 (actor 이름만 다르고 메시는 같음)
python3 - "$R/limbo/src/limbo_simulation/worlds/aischool_2f_social.sdf" "$E/band_model.sdf" "$W/zz_follow.sdf" <<'PY'
import sys, re
src, band, dst = sys.argv[1:4]
s = open(src).read().replace('aischool_2f_social', 'zz_follow')
actor = re.search(r'    <actor name="walker_yield">.*?</actor>\n', s, re.S).group(0)
s = re.sub(r'    <actor name="walker_yield">.*?</actor>\n    <actor name="walker_noyield">.*?</actor>\n', '', s, flags=re.S)
actors = ''.join(actor.replace('walker_yield', n) for n in ('operator', 'crosser_a', 'crosser_b'))
s = s.replace('  </world>', open(band).read() + actors + '  </world>')
open(dst, 'w').write(s)
PY
cp $E/zz_follow_movers.json $W/
source /opt/ros/jazzy/setup.bash; source $R/limbo/install/setup.bash; source $R/venvs/limbo_yolo/bin/activate; export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-97}
$T/sim_ctl.sh stop >/dev/null 2>&1
rm -f ~/.limbo/follow_operator.json
echo "##### $L 시작 $(date +%H:%M:%S) 커밋 $(git -C $R rev-parse --short HEAD)"
WORLD=zz_follow MAP=aischool_2f_map $T/sim_ctl.sh start $L || { echo "시뮬 시작 실패"; exit 1; }
( cd /tmp; exec python3 $E/rec.py $OUT/$L.json ) > $LOGS/follow_rec_$L.log 2>&1 &
REC=$!
# 운용자가 등록 구역(앞 0.5~2.5 m)을 지날 때 등록이 된다. 될 때까지 1 s마다 다시 요청 (최대 90 s)
for i in $(seq 1 90); do
  r=$(python3 $E/svc.py call /follow/enroll 5 2>/dev/null)
  echo "$(date +%H:%M:%S) enroll: $r"
  echo "$r" | grep -q "success=True" && break
  sleep 1
done
sleep $DUR
kill -INT $REC; wait $REC 2>/dev/null
$T/sim_ctl.sh stop >/dev/null 2>&1
rm -f $W/zz_follow.sdf $W/zz_follow_movers.json
echo "##### $L 끝 $(date +%H:%M:%S)"
python3 $E/ana.py $OUT/$L.json
