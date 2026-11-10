# 실물 순찰 한 바퀴 돌리기 (2026-11-10 기준)

젯슨에서 그대로 치면 로봇이 원점 테이프 자리에서 출발해 ㅁ자 복도를 한 바퀴 돌고 원점에 선다.
오늘(11-10) 기준 설정: 지도 `real_open_space_20261110`, 지나가기 순찰 `real_loop_waypoints.yaml`, 카메라는 비용 지도에서 뺀 측정용 Nav2 설정.

## 0. 로봇 놓기

- 로봇을 **원점 바닥 테이프 자리**에 **+x(긴 복도 쪽)** 를 보게 놓는다.
- 로봇 2 m 안에 사람·물건이 없게 비운다. 주행 중 관찰자는 2 m 밖.
- 카메라는 비용 지도에서 빠져 있으므로 **0.75 m 아래 낮은 물건은 못 본다.** 복도에 새 물건을 두지 않는다. 계단 문 근처로는 보내지 않는다.

## 1. 젯슨 접속과 환경

노트북에서 `ssh automaton@192.168.20.210` (비밀번호는 팀 내 구두 전달, 파일에 적지 않는다). 아래는 전부 젯슨 안에서 친다.

```bash
cd ~/limbo
export ROS_DOMAIN_ID=97 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST RMW_IMPLEMENTATION=rmw_fastrtps_cpp
source /opt/ros/jazzy/setup.bash && source limbo/install/setup.bash
mkdir -p ~/limbo_bags/logs
```

→ 프롬프트가 돌아온다. 터미널을 새로 열 때마다 이 네 줄을 다시 친다.

## 2. 런치 3개 띄우기 (순서대로)

```bash
# ① 구동(바퀴·odom). 모터 명령은 Nav2가 보내기 전까지 안 나간다
setsid -f tools/drive/run_teleop.sh record_dir:=$HOME/limbo_bags/nav_$(date +%m%d) > ~/limbo_bags/logs/teleop.log 2>&1 < /dev/null
sleep 6

# ② 센서 + AMCL + 지도
setsid -f tools/drive/run_real.sh encoder_source:=external localization:=amcl \
  map:=$HOME/limbo/limbo/src/limbo_navigation/maps/real_open_space_20261110.yaml yolo:=false \
  > ~/limbo_bags/logs/real.log 2>&1 < /dev/null
sleep 40
grep -E "Init lds lidar|Driver ready|ERROR" ~/limbo_bags/logs/real.log | cut -c1-120
```

→ `Init lds lidar success!`와 `[oak]: Driver ready!`가 보여야 한다. `Init lds lidar fail!`이면 라이다 랜선·전원(포트 `enP8p1s0` carrier)을 본다.

```bash
# ③ 측정용 Nav2 설정 만들기(저장소의 nav2_real.yaml에서: 카메라 소스 제거, 팽창 0.35, 되꺾임 멈춤 끔)
python3 - <<'EOF'
import yaml
src='limbo/src/limbo_navigation/config/nav2_real.yaml'; d=yaml.safe_load(open(src))
for k in ('local_costmap','global_costmap'):
    p=d[k][k]['ros__parameters']
    s=p['stvl_layer']; s['observation_sources']='mid360_mark mid360_clear'; s.pop('rgbd_mark'); s.pop('rgbd_clear')
    p['inflation_layer']['inflation_radius']=0.35
cm=d['collision_monitor']['ros__parameters']; cm['observation_sources']=['mid360_cloud']; cm['FootprintApproach']['sources_names']=['mid360_cloud']; cm.pop('rgbd_cloud')
d['controller_server']['ros__parameters']['FollowPath']['enforce_path_inversion']=False
open('/tmp/nav2_real_measure.yaml','w').write(yaml.safe_dump(d,sort_keys=False,allow_unicode=True,width=200))
print('ok')
EOF

# ④ Nav2
setsid -f bash tools/drive/run_nav2_real.sh cmd_vel_out:=/cmd_vel params_file:=/tmp/nav2_real_measure.yaml \
  > ~/limbo_bags/logs/nav2.log 2>&1 < /dev/null
sleep 30
grep -c "Managed nodes are active" ~/limbo_bags/logs/nav2.log
ros2 param get /collision_monitor observation_sources
```

→ `1`과 `['mid360_cloud']`가 나와야 한다. 0이면 30초 더 기다렸다 다시 센다.

## 3. 출발 (위치 확인 → 초기 위치 → 점검 → 기록 → 순찰, 한 번에)

```bash
cat > /tmp/patrol_run.sh <<'EOF'
#!/bin/bash
# 사용: NAME=순찰1 bash /tmp/patrol_run.sh   (로봇이 원점 테이프 자리에 있을 때)
N=${NAME:-patrol}; L=~/limbo_bags/logs/$N.txt; : > $L
cd ~/limbo && export ROS_DOMAIN_ID=97 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST RMW_IMPLEMENTATION=rmw_fastrtps_cpp
source /opt/ros/jazzy/setup.bash && source limbo/install/setup.bash
sed "s/(%.1f, %.1f)/(%.3f, %.3f)/" tools/drive/pose_search.py > /tmp/pose_search3.py
OUT=$(python3 /tmp/pose_search3.py ${CX:-0.74} ${CY:--0.04} --radius ${R:-0.2} --step 0.025 --deg-step 1 --top 1 2>&1 | tail -1); echo "위치 탐색: $OUT" >> $L
FIT=$(echo "$OUT" | grep -o '[0-9]* %' | grep -o '[0-9]*'); X=$(echo "$OUT" | sed 's/.*(\([-0-9.]*\), \([-0-9.]*\)).*/\1/'); Y=$(echo "$OUT" | sed 's/.*(\([-0-9.]*\), \([-0-9.]*\)).*/\2/'); D=$(echo "$OUT" | grep -o '[-+][0-9]*°' | tr -d '°+')
if [ -z "$FIT" ] || [ "$FIT" -lt 85 ]; then echo "출발 안 함: 일치율 $FIT % (기준 85). 2 m 안을 비우고 다시" >> $L; echo 끝 >> $L; exit 1; fi
QZ=$(python3 -c "import math;print(math.sin(math.radians($D)/2))"); QW=$(python3 -c "import math;print(math.cos(math.radians($D)/2))")
ros2 topic pub --once -w 1 /initialpose geometry_msgs/msg/PoseWithCovarianceStamped "{header: {frame_id: map}, pose: {pose: {position: {x: $X, y: $Y}, orientation: {z: $QZ, w: $QW}}, covariance: [0.01,0,0,0,0,0, 0,0.01,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0.01]}}" >/dev/null
sleep 3; PRE=$(python3 tools/drive/nav_preflight.py 2>&1 | grep '위치 추정'); echo "점검: $PRE" >> $L
case "$PRE" in 통과*) ;; *) echo "출발 안 함: 점검 위치 추정 실패" >> $L; echo 끝 >> $L; exit 1;; esac
B=$HOME/limbo_bags/${N}_$(date +%m%d); rm -rf $B
setsid -f ros2 bag record -o $B /rgbd_camera/depth_for_points /rgbd_camera/depth_camera_info /oak/rgb/image_raw/compressed /local_costmap/costmap /mid360/points_costmap /scan /tf /tf_static /odom /plan /cmd_vel /cmd_vel_nav /amcl_pose > ~/limbo_bags/logs/${N}_bag.log 2>&1 < /dev/null
sleep 3; BP=$(ps -eo pid,args | grep "[r]os2 bag record -o $B " | awk '{print $1}' | head -1)
T0=$(date +%s.%N); O0=$(grep -c 'Optimizer fail' ~/limbo_bags/logs/nav2.log); echo "출발 $(date +%T)" >> $L
timeout 900 ros2 run limbo_patrol patrol_node --ros-args -p use_sim_time:=false -p waypoints:=real_loop_waypoints.yaml -p loop:=false > ~/limbo_bags/logs/${N}_node.log 2>&1
RC=$?; T1=$(date +%s.%N); O1=$(grep -c 'Optimizer fail' ~/limbo_bags/logs/nav2.log)
sleep 1; [ -n "$BP" ] && kill -INT $BP; for i in $(seq 1 20); do sleep 1; kill -0 $BP 2>/dev/null || break; done
printf '한 바퀴: 종료코드 %d, %.0f s, 최적화실패 +%d, 기록 %s\n' $RC "$(echo "$T1 - $T0" | bc)" $((O1-O0)) "$(du -sh $B | cut -f1)" >> $L
grep -E "Moving to|completed|failed|rejected" ~/limbo_bags/logs/${N}_node.log | tail -6 >> $L; echo 끝 >> $L
EOF

NAME=patrol1 setsid -f bash /tmp/patrol_run.sh > /dev/null 2>&1 < /dev/null
sleep 100; cat ~/limbo_bags/logs/patrol1.txt
```

→ `위치 탐색: 일치 9x %`, `점검: 통과`, `출발 HH:MM:SS`가 찍히고 10여 초 뒤 로봇이 움직인다.
- 위치 탐색은 1~2분 걸린다(±20 cm를 2.5 cm·1° 간격으로 훑음).
- `출발 안 함: 일치율 … 85 미만`이면 로봇 2 m 안을 비우고 같은 명령을 다시 친다. 기준을 낮추지 않는다.
- 로봇이 테이프 자리에서 20 cm 넘게 벗어나 있으면 `CX=<x> CY=<y> R=0.3`을 앞에 붙인다.
- 끝나면 `cat ~/limbo_bags/logs/patrol1.txt`에 `한 바퀴: … s`와 `끝`이 찍힌다. 두 번째 바퀴는 `NAME=patrol2`.

## 4. 결과 보기

```bash
cat ~/limbo_bags/logs/patrol1.txt                                   # 한 바퀴 시간·실패 수
grep -E "Begin navigating|Goal succeeded|Failed to make progress" ~/limbo_bags/logs/nav2.log | tail -8
ls -d ~/limbo_bags/patrol1_*                                        # bag(구간 분석용)
```

오늘 기준값: 순찰 3(카메라 뺌·지도 1110·W1 (11.0, 0.3)) **170 s**, 아래 복도 12 m를 20 s. W1 코너가 30 s 넘으면 변경 기록 67 "할 일"의 경로 떨림 항목을 본다.

## 5. 끝내기

런치를 띄운 역순으로 **PID에 SIGINT**. `pkill -f`·패턴 kill은 쓰지 않는다(자기 셸까지 죽는다).

```bash
for n in start_nav2_real start_real teleop_drive; do
  P=$(ps -eo pid,args | grep "[r]os2 launch .*$n" | awk '{print $1}'); [ -n "$P" ] && kill -INT $P; sleep 8
done
ps -eo pid,args | grep -E "[r]os2 launch|[n]av2_|[a]mcl|[l]ivox" | wc -l     # 0이어야 함
ros2 daemon stop; rm -f /dev/shm/fastrtps_*                                 # ROS 프로세스가 없을 때만
sudo shutdown -h now
```

## 막히면

- **위치 탐색이 80 % 안팎에서 안 올라감**: 로봇 2 m 안에 사람·물건이 있거나, 로봇이 테이프 자리에서 벗어나 탐색 창(±20 cm) 가장자리에 걸린 것. `CX CY R=0.3`으로 창을 옮긴다.
- **순찰 노드가 9 s 만에 "completed"**: 경유점 파일의 마지막 stop이 출발점과 같을 때 생긴다(TROUBLESHOOTING 11-10). `real_loop_waypoints.yaml`은 MID·HOME 두 stop 구조를 유지한다.
- **젯슨 ssh가 끊김**: 로봇이 W1 코너(복도 끝)에 있을 때 와이파이가 약하다. 돌아올 때까지 기다리면 된다. 순찰은 젯슨 안에서 계속 돈다.
- **`fastrtps_port … open_and_lock_file failed`가 찍힘**: `timeout`으로 끊은 `ros2 topic …` 명령이 남긴 공유 메모리 찌꺼기. 주행 중 CLI 확인을 줄이고, 5절처럼 ROS가 다 내려간 뒤 `/dev/shm/fastrtps_*`를 지운다.
