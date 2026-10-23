#!/usr/bin/env bash
# 따라가기 3단계(관제): 2단계 장면(zz_follow2)을 그대로 쓰되, 등록·시작·정지를 ROS 서비스가 아니라 관제 화면의 길
# (대시보드 서버 → Bridge → 서비스)로 보내고, 각 명령이 confirmed로 끝나는지와 따라가기 알림을 본다. 사용법: run3.sh <라벨> [초(기본 150)]
set +u
L=$1; DUR=${2:-150}; R=~/limbo; E=$R/experiments/2026-10-22_follow_operator; T=$R/tools/sim_trials; LOGS=~/limbo_bags/sim_trials/logs
OUT=~/limbo_bags/follow_rec; mkdir -p $OUT $LOGS
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
# 관제 서버(uvicorn)와 Bridge. 서버는 ROS 없이 돌고, Bridge는 ROS 도메인 97에서 /follow/state 등을 구독한다
# setsid로 자기 프로세스 그룹에 띄우고 끝낼 때 그룹째 끝낸다. ros2 run 래퍼만 죽이면 Bridge 자식이 살아남아 다음 회차에 Bridge가 둘이 된다(fw10 무효)
setsid bash -c "cd $R/dashboard && exec env -u PYTHONPATH .venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8000 --workers 1" > $LOGS/dash_server_$L.log 2>&1 &
SRV=$!
setsid bash -c "cd $R/relay_prog && source install/setup.bash && exec ros2 run limbo_telemetry_bridge bridge --config src/limbo_telemetry_bridge/config/bridge.yaml" > $LOGS/bridge_$L.log 2>&1 &
BRG=$!
stop_side() { for g in $BRG $SRV; do kill -INT -- -$g 2>/dev/null; done; sleep 2; for g in $BRG $SRV; do kill -9 -- -$g 2>/dev/null; done; }
( cd /tmp; exec python3 $E/rec2.py $OUT/$L.json ) > $LOGS/follow_rec_$L.log 2>&1 &
REC=$!
python3 $E/api3.py wait_bridge 90 || { echo "Bridge 연결 실패 → 중단"; kill -INT $REC; stop_side; $T/sim_ctl.sh stop >/dev/null 2>&1; exit 1; }
for i in $(seq 1 20); do
  r=$(python3 $E/api3.py cmd follow_enroll 20); echo "$(date +%H:%M:%S) $r"; echo "$r" | grep -q confirmed && break; sleep 3
done
for i in $(seq 1 10); do
  r=$(python3 $E/api3.py cmd follow_start 20); echo "$(date +%H:%M:%S) $r"; echo "$r" | grep -q confirmed && break; sleep 3
done
echo "$r" | grep -q confirmed || { echo "따라가기 시작 실패 → 중단"; python3 $E/api3.py alerts; kill -INT $REC; stop_side; $T/sim_ctl.sh stop >/dev/null 2>&1; exit 1; }
sleep 2; python3 $E/svc.py pub /follow/go >/dev/null 2>&1; echo "$(date +%H:%M:%S) 운용자 출발 신호"
for i in $(seq 1 $((DUR/10))); do sleep 10; echo "$(date +%H:%M:%S) $(python3 $E/api3.py follow)"; done
r=$(python3 $E/api3.py cmd follow_stop 20); echo "$(date +%H:%M:%S) $r"
echo "----- 알림(최근)"; python3 $E/api3.py alerts 12
kill -INT $REC; wait $REC 2>/dev/null
stop_side
$T/sim_ctl.sh stop >/dev/null 2>&1
rm -f $W/zz_follow2.sdf $W/zz_follow2_movers.json
echo "##### $L 끝 $(date +%H:%M:%S)"
python3 $E/ana2.py $OUT/$L.json
