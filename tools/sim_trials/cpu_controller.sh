#!/usr/bin/env bash
# 사용법: cpu_controller.sh <라벨>  — 띄운 뒤 controller_server CPU를 서 있을 때 15초, 주행(홀 → 왼쪽 복도 끝) 동안 재고 끈다
# controller_server에는 로컬 costmap(STVL)도 같이 돌아서, 서 있을 때(장애물 지도만)와 주행 중(컨트롤러 계산 추가)을 나눠 잰다
D=$(cd "$(dirname "$0")" && pwd); LOGS=~/limbo_bags/sim_trials/logs; mkdir -p $LOGS
$D/sim_ctl.sh start cpu_$1 > /dev/null || { $D/sim_ctl.sh stop; exit 1; }
source /opt/ros/jazzy/setup.bash; export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-97}; cd /tmp
P=$(pgrep -f "^/opt/ros/jazzy/lib/nav2_controller/controller_server" | head -1)  # 맨 앞이 실행 파일인 것만 (셸 명령 줄에 같은 글자가 있어도 안 잡히게)
echo "  controller_server pid $P"
sample() {  # $1초 동안 1초 간격: 프로세스 전체 CPU와 스레드별 CPU 상위
  top -H -b -n $(( $1 + 1 )) -d 1 -p $P | awk -v skip=1 '/^top -/{n++; next} n>skip && $1 ~ /^[0-9]+$/ {tot[n]+=$9; th[$12]+=$9} END {
    s=0; c=0; for (k in tot) {s+=tot[k]; c++}; printf "  프로세스 합계 평균 %.1f%%\n", s/c;
    for (t in th) printf "    %-16s %.1f%%\n", t, th[t]/c }' | sort -t'%' -k1 | head -8
}
echo "[$1] 서 있을 때 (15초)"; sample 15
timeout 90 python3 $D/one_goal.py -5.8 8.6 60 > /dev/null 2>&1 &
G=$!; sleep 3
echo "[$1] 주행 중 (25초)"; sample 25
wait $G
echo "  주기 경고: $(grep -c 'Control loop missed' $LOGS/sim_cpu_$1.log)줄"
$D/sim_ctl.sh stop > /dev/null
