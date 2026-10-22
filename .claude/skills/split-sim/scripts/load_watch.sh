#!/usr/bin/env bash
# 사용법: load_watch.sh <초> <출력파일> [robot 런치 로그]
# 5초마다 load average·가용 메모리·CPU 상위 프로세스를, 20초마다 /scan·/cmd_vel 주기를 적는다. Jetson(role:=robot)과 PC(role:=sim) 양쪽에서 같은 것을 돌려 비교한다
DUR=${1:-120}; OUT=${2:-load_watch.out}; LOG=$3
NCPU=$(nproc); END=$((SECONDS+DUR)); n=0
echo "# $(hostname) cpu=$NCPU 시작 $(date +%T)" > $OUT
while [ $SECONDS -lt $END ]; do
  read l1 l5 _ < /proc/loadavg
  avail=$(awk '/MemAvailable/{printf "%.0f", $2/1024}' /proc/meminfo)
  top3=$(ps -eo pcpu,comm --sort=-pcpu | awk 'NR>1 && NR<=4 {printf "%s %.0f%% ", $2, $1}')
  echo "$(date +%T) load1 $l1 load5 $l5 memavail ${avail}MB | $top3" >> $OUT
  if [ $((n % 4)) -eq 0 ]; then
    for t in /scan /cmd_vel /tf; do
      hz=$(timeout 6 ros2 topic hz $t --window 30 2>/dev/null | grep -m1 -oE "average rate: [0-9.]+" | awk '{print $3}')
      echo "$(date +%T)   $t ${hz:-없음} Hz" >> $OUT
    done
    if [ -n "$LOG" ]; then
      echo "$(date +%T)   AMCL/TF 경고 누적: $(grep -cE "Message Filter dropping|extrapolation|TF_OLD_DATA|jump back" $LOG)" >> $OUT
    fi
  fi
  n=$((n+1)); sleep 5
done
echo "# 끝 $(date +%T)" >> $OUT
