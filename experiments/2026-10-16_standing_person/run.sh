#!/usr/bin/env bash
# 사용법: run.sh <라벨>  — zz_stand 월드에서 people2 경로(위쪽 복도 왕복)를 돈다. 옆 문틈 사람은 stand_mover.py가 움직인다
# (월드에 movers json을 두지 않아 launch는 사람을 안 움직이고, 이 스크립트가 띄우고 PID로 끈다)
E=$(cd "$(dirname "$0")" && pwd); T=~/limbo/tools/sim_trials; LOGS=~/limbo_bags/sim_trials/logs
W=~/limbo/limbo/install/limbo_simulation/share/limbo_simulation/worlds
cp $E/worlds/zz_stand.sdf $W/
BEFORE=$(ls ~/limbo_results/*.csv 2>/dev/null | wc -l)
WORLD=zz_stand MAP=aischool_2f_map $T/sim_ctl.sh start $1 || { $T/sim_ctl.sh stop; rm -f $W/zz_stand.sdf; exit 1; }
source /opt/ros/jazzy/setup.bash; source ~/limbo/limbo/install/setup.bash; export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-97}; cd /tmp
python3 $E/stand_mover.py $E/worlds/zz_stand_people.json > $LOGS/trial_$1.mover.log 2>&1 &
MOVER=$!
timeout 900 python3 $T/nav_route.py people2 > $LOGS/trial_$1.nav.log 2>&1
kill $MOVER 2>/dev/null; wait $MOVER 2>/dev/null
sleep 2
$T/sim_ctl.sh stop
rm -f $W/zz_stand.sdf
if [ "$(ls ~/limbo_results/*.csv | wc -l)" -gt "$BEFORE" ]; then cp $(ls -t ~/limbo_results/*.csv | head -1) $LOGS/trial_$1.csv; else echo "이번 실행의 CSV 없음"; fi
