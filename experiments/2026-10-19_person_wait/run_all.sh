#!/usr/bin/env bash
# 사용법: run_all.sh <guest|corridor|stand|box> [회차 목록, 기본 "1 2 3"]
# 라벨 pw_<시나리오>_<n>. 손님·앞에 서는 사람은 close_diag.py로 코앞 트랙 소실을 같이 기록한다(~/limbo_bags/person_wait_rec/close_frames/<라벨>)
E=$(cd "$(dirname "$0")" && pwd); R=~/limbo; T=$R/tools/sim_trials; LOGS=~/limbo_bags/sim_trials/logs
W=$R/limbo/install/limbo_simulation/share/limbo_simulation/worlds; S=$R/experiments/2026-10-14_social_people/worlds
REC=~/limbo_bags/person_wait_rec/close_frames
export GOAL_TIMEOUT=120 ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-97}
for i in ${2:-1 2 3}; do
  L=pw_$1_$i; echo "=== $L $(date +%H:%M) 커밋 $(git -C $R rev-parse --short HEAD)"
  case $1 in
    guest) cp $S/zz_social_approach.sdf $S/zz_social_approach_movers.json $W/
           WORLD=zz_social_approach MAP=aischool_2f_map $E/run_one.sh $L hall $REC/$L | tail -1
           rm -f $W/zz_social_approach.sdf $W/zz_social_approach_movers.json ;;
    corridor) WORLD=aischool_2f_social MAP=aischool_2f_map $E/run_one.sh $L people2 | tail -1 ;;
    stand) cp $R/experiments/2026-10-16_standing_person/worlds/zz_stand.sdf $W/
           MOVER="python3 $R/experiments/2026-10-16_standing_person/stand_mover.py $R/experiments/2026-10-16_standing_person/worlds/zz_stand_people.json" \
             WORLD=zz_stand MAP=aischool_2f_map $E/run_one.sh $L people2 $REC/$L | tail -1
           rm -f $W/zz_stand.sdf ;;
    box) WORLD=aischool_2f_scenarios MAP=aischool_2f_map $E/run_one.sh $L box | tail -1 ;;
  esac
  cat $LOGS/trial_$L.nav.log
done
