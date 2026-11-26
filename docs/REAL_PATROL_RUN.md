# 실물 순찰 한 바퀴 돌리기 (2026-11-10 기준)

젯슨에서 그대로 치면 로봇이 원점 테이프 자리에서 출발해 ㅁ자 복도를 한 바퀴 돌고 원점에 선다.
오늘(11-10) 기준 설정: 지도 `real_open_space_20261110`, 지나가기 순찰 `real_loop_waypoints.yaml`, 카메라는 비용 지도에서 뺀 측정용 Nav2 설정.

> **NX 보드 안내(2026-11-24 추가).** 아래 0~5절은 **Nano(원래 보드, `192.168.20.210`)** 에서 쓰던 수동 절차다. 2026-11-20부터 로봇에 달린 **NX(대여 보드, Jetson Orin NX 16 GB + Seeed J401)** 에서는 다르게 한다.
> - 접속: `ssh automaton@192.168.20.18` (비밀번호는 팀 내 구두 전달, 파일에 적지 않는다).
> - NX에서는 2절의 런치 3개(구동·센서+AMCL+지도·Nav2)가 **부팅 때 사용자 systemd 유닛으로 자동으로 떠 있다**(지도 `real_open_space_20261111`, Nav2는 저장소 `nav2_real.yaml` 그대로, YOLO 켜짐). 관제 다리(dashboard)도 같이 뜬다. 자세한 내용은 `docs/REAL_ROBOT_BRINGUP.md` "부팅 자동 기동(사용자 systemd 유닛 5개)".
> - 초기 위치는 `corridor_pose.py`(유닛 `limbo-nx-pose`)가 로봇이 멈춰 있을 때 지도 전체 탐색으로 자동으로 잡는다. 2절 ③의 `setpose.sh`는 필요 없다.
> - 아래 수동 절차를 따르려면 먼저 자동 기동을 내리고 한다(같은 노드가 두 벌 뜨지 않게):
>   ```bash
>   systemctl --user stop limbo-nx-navigation limbo-nx-sensors limbo-nx-drive limbo-nx-pose limbo-nx-dashboard
>   systemctl --user status 'limbo-nx-*'     # 모두 inactive인지 확인
>   ```
>   유닛은 enabled 상태라 재부팅하면 다시 뜬다. NX에서 수동 절차를 그대로 해 본 기록은 아직 없다(확인 필요).

### 모방 학습 런치(수동 운전 기록) — NX

사람이 패드로 운전한 바퀴를 기록한다. 패드 명령은 중재기(`drive_arbiter`) → collision_monitor → `/cmd_vel` → 바퀴로 가므로 안전 정지는 그대로 남는다. 패드는 **LB(왼쪽 어깨)를 누르는 동안만** 바퀴로 간다.

1. 빌드(처음 한 번, pull 뒤마다): `cd ~/limbo/limbo && colcon build --symlink-install --packages-select limbo_imitation limbo_bringup`. `ros-jazzy-joy`·`ros-jazzy-teleop-twist-joy`가 없으면 설치가 필요하다(sudo, PM 승인).
   - **조이스틱 연결(Acegamer T50, 블루투스)** — 처음 한 번, 그리고 패드를 껐다 켜서 안 붙을 때마다(전원을 끄면 페어링이 풀리는 경우가 있다):
     1. 패드를 **Xbox 모드** 페어링 상태(불빛 빠른 깜빡임)로 둔다. Switch 모드("Pro Controller")는 이 커널에 `hid-nintendo`가 없어 입력 장치가 안 생긴다.
     2. 젯슨에서(재부팅 뒤 한 번, 영구 적용 전까지):
        ```bash
        sudo modprobe uhid                   # 없으면 연결은 Success인데 /dev/input/js0이 안 생긴다
        groups | grep -w input               # 없으면 sudo usermod -aG input automaton 뒤 다시 로그인(joy_node가 event 장치를 열려면 필요)
        ```
     3. 페어링(`<MAC>`은 `bluetoothctl --timeout 20 scan on`으로 찾는다). 기본 `bluetoothctl pair`는 에이전트가 없어 `AuthenticationCanceled`로 실패하니 에이전트를 지정한다:
        ```bash
        bluetoothctl --agent NoInputNoOutput --timeout 30 pair <MAC>
        bluetoothctl trust <MAC>
        bluetoothctl connect <MAC>
        ```
     4. 확인: `ls /dev/input/js0` → `ros2 run joy joy_node`에서 `/joy`의 축 0(좌우)·1(상하)이 ±1.0, LB가 버튼 4(`config/joy_xbox.yaml`의 데드맨). 확인 뒤 `joy_node`는 끈다(기록 런치가 다시 띄운다).
     막히면 `docs/TROUBLESHOOTING.md` 2026-11-25(`uhid`, `bluetoothctl` 에이전트).
2. Nav2의 collision_monitor 입력을 중재기 출력으로 바꿔 다시 띄운다. 부팅 유닛의 `start navigation`이 환경 변수 `LIMBO_CMD_VEL_IN`(없으면 기본 `cmd_vel_smoothed` = 지금 동작)을 읽는다:
   ```bash
   systemctl --user set-environment LIMBO_CMD_VEL_IN=/cmd_vel_arbiter
   systemctl --user restart limbo-nx-navigation
   ```
   수동으로 띄울 때는 `bash tools/drive/run_nav2_real.sh cmd_vel_out:=/cmd_vel cmd_vel_in:=/cmd_vel_arbiter`.
3. 기록 런치 — **하루 한 번만** 띄워 두고 바퀴마다 패드 **Start(메뉴) 버튼**으로 기록을 시작·끝낸다:
   ```bash
   ros2 launch limbo_imitation imitation_real.launch.py mode:=manual driver:=<이름> note:=<메모>
   ```
   → 런치가 뜨면 패드로 운전은 되지만 **기록은 안 된다.** HOME에서 Start를 누르면 새 바퀴 폴더로 기록 시작(`run N started (button)`), 다시 누르면 끝(`run N ended (button): passed=… […]`). 누르지 않은 동안(바퀴 사이 이동·연습)은 기록하지 않는다. 바퀴 번호는 같은 런치 안에서 01, 02, …로 올라간다. 버튼을 누르고 있어도 한 번만 바뀌니 떼었다 다시 눌러야 다음 토글이다.
   - 버튼 번호는 기본 7(Xbox 배열 Start). 패드가 다르면 `ros2 topic echo /joy`에서 누를 때 1이 되는 `buttons` 자리(0부터)를 보고 런치에 `record_button:=<번호>`.
   - 순찰 노드와 같이 달리면 `/patrol/state`가 patrolling이 될 때도 시작하고 completed·failed에서 끝낸다. `manual_start:=true`는 "런치가 뜨자마자 기록" 옵션으로 남아 있다(그 바퀴도 Start나 Ctrl+C로 끝).
   - 기록 중에 Ctrl+C로 런치를 끄면 그 바퀴는 `node shutdown`으로 닫힌다.
   - 패드가 없으면 키보드: 런치에 `require_deadman:=false`를 붙이고 다른 터미널에서 `bash tools/drive/teleop_keyboard.sh /cmd_vel_teleop`. 키를 떼면 0.5 s 안에 멈춘다.
4. 기록 위치: `~/limbo_bags/imitation/<날짜_시각>_<번호>_<모드>/`(`bag/`, `meta.json`, `metrics.csv`). 바퀴 지표 표 한 장:
   ```bash
   ros2 run limbo_imitation collect_metrics ~/limbo_bags/imitation/* > ~/limbo_bags/imitation/all.csv
   ```
   열: 충돌 수, 움직이는 중 사람 최소 거리, 완주, 걸린 시간, 거리, 갇힘 시간, 비틀거림, 끼어들기, 합격 여부와 이유.
5. 학습(노트북, torch 있는 파이썬): `ros2 run limbo_imitation build_dataset ~/limbo_bags/imitation/<폴더들> -o data.npz` → `~/limbo_venvs/imitation/bin/python -m limbo_imitation.train data.npz`. 결과 `.pt`는 `~/limbo_bags/imitation/models/policy_<시각>.pt`. 저장소에 커밋할지는 PM이 정한다.
6. 정책 주행: `ros2 launch limbo_imitation imitation_real.launch.py mode:=policy_assist model_path:=<.pt> waypoints:=<patrol_node와 같은 경유점 yaml>` → `policy_node`가 `/cmd_vel_policy`를 내고, 정책이 자신 없거나 입력이 끊기면(`/policy/status` ok=false) 중재기가 MPPI로 넘긴다. LB를 누르면 사람이 끼어든다(끼어든 구간은 학습에서 가중 2).
7. 끝나면 Nav2를 원래대로: `systemctl --user unset-environment LIMBO_CMD_VEL_IN && systemctl --user restart limbo-nx-navigation`(재부팅해도 기본값으로 돌아온다).

## 0. 로봇 놓기

- 로봇을 **원점 바닥 테이프 자리**에 **+x(긴 복도 쪽)** 를 보게 놓는다.
- 로봇 2 m 안에 사람·물건이 없게 비운다. 주행 중 관찰자는 2 m 밖.
- 카메라는 비용 지도에서 빠져 있으므로 **0.75 m 아래 낮은 물건은 못 본다.** 복도에 새 물건을 두지 않는다. 계단 문 근처로는 보내지 않는다.

## 1. 젯슨 접속과 환경

(Nano 기준. NX는 위 "NX 보드 안내")

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
# ③ 위치 탐색 → 초기 위치. Nav2보다 먼저 한다(11-11): AMCL은 set_initial_pose: false라 /initialpose를 받기 전엔 map→odom을 안 내고,
#    Nav2 계획기는 활성화 때 그 TF를 60 s 기다리다 실패해 기동 전체가 중단된다(TROUBLESHOOTING 11-11). 1~2분 걸린다.
cat > /tmp/setpose.sh <<'EOF'
#!/bin/bash
# 사용: bash /tmp/setpose.sh   (창 옮길 때 CX=<x> CY=<y> R=0.3)
cd ~/limbo && export ROS_DOMAIN_ID=97 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST RMW_IMPLEMENTATION=rmw_fastrtps_cpp
source /opt/ros/jazzy/setup.bash && source limbo/install/setup.bash
sed "s/(%.1f, %.1f)/(%.3f, %.3f)/" tools/drive/pose_search.py > /tmp/pose_search3.py
OUT=$(python3 /tmp/pose_search3.py ${CX:-0.74} ${CY:--0.04} --radius ${R:-0.2} --step 0.025 --deg-step 1 --top 1 2>&1 | tail -1); echo "위치 탐색: $OUT"
FIT=$(echo "$OUT" | grep -o '[0-9]* %' | grep -o '[0-9]*'); X=$(echo "$OUT" | sed 's/.*(\([-0-9.]*\), \([-0-9.]*\)).*/\1/'); Y=$(echo "$OUT" | sed 's/.*(\([-0-9.]*\), \([-0-9.]*\)).*/\2/'); D=$(echo "$OUT" | grep -o '[-+][0-9]*°' | tr -d '°+')
if [ -z "$FIT" ] || [ "$FIT" -lt 85 ]; then echo "초기 위치 안 보냄: 일치율 $FIT % (기준 85). 2 m 안을 비우고 다시"; exit 1; fi
QZ=$(python3 -c "import math;print(math.sin(math.radians($D)/2))"); QW=$(python3 -c "import math;print(math.cos(math.radians($D)/2))")
ros2 topic pub --once -w 1 /initialpose geometry_msgs/msg/PoseWithCovarianceStamped "{header: {frame_id: map}, pose: {pose: {position: {x: $X, y: $Y}, orientation: {z: $QZ, w: $QW}}, covariance: [0.01,0,0,0,0,0, 0,0.01,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0.01]}}" >/dev/null
echo "초기 위치 보냄: ($X, $Y) ${D}°"
EOF
bash /tmp/setpose.sh
grep "Setting pose" ~/limbo_bags/logs/real.log | tail -1 | cut -c1-120
```

→ `위치 탐색: 일치 9x %`, `초기 위치 보냄: (…)`, 그리고 real.log에 `[amcl]: Setting pose … 0.8xx -0.0xx`가 찍혀야 한다. 85 % 미만이면 2 m 안을 비우고 다시(기준을 낮추지 않는다).

```bash
# ④ 측정용 Nav2 설정 만들기(저장소의 nav2_real.yaml에서: 카메라 소스 제거, 팽창 0.35)
#    되꺾임 처리(enforce_path_inversion)는 끄지 않는다: 순찰 7(11-10)에서 끄니 W3 머리핀 경로를 그대로 따라가 224 s 회전.
python3 - <<'EOF'
import yaml
src='limbo/src/limbo_navigation/config/nav2_real.yaml'; d=yaml.safe_load(open(src))
for k in ('local_costmap','global_costmap'):
    p=d[k][k]['ros__parameters']
    s=p['stvl_layer']; s['observation_sources']='mid360_mark mid360_clear'; s.pop('rgbd_mark'); s.pop('rgbd_clear')
    p['inflation_layer']['inflation_radius']=0.35
cm=d['collision_monitor']['ros__parameters']; cm['observation_sources']=['mid360_cloud']; cm['FootprintApproach']['sources_names']=['mid360_cloud']; cm.pop('rgbd_cloud')
open('/tmp/nav2_real_measure.yaml','w').write(yaml.safe_dump(d,sort_keys=False,allow_unicode=True,width=200))
print('ok')
EOF

# ⑤ Nav2
setsid -f bash tools/drive/run_nav2_real.sh cmd_vel_out:=/cmd_vel params_file:=/tmp/nav2_real_measure.yaml \
  > ~/limbo_bags/logs/nav2.log 2>&1 < /dev/null
sleep 30
grep -c "Managed nodes are active" ~/limbo_bags/logs/nav2.log
ros2 param get /collision_monitor observation_sources
```

→ `1`과 `['mid360_cloud']`가 나와야 한다. 0이면 30초 더 기다렸다 다시 센다. 그래도 0이고 nav2.log에 `Failed to activate global_costmap because transform from base_link to map`·`Aborting bringup`이 있으면 ③을 건너뛴 것이다: Nav2 런치 PID에 SIGINT → ③ → ⑤를 다시 한다(아래 "막히면").
`The inflation radius (0.35) is smaller than the circumscribed radius (0.386)` ERROR는 측정용 팽창 0.35 때문에 늘 찍히는 것으로, MPPI가 발판 기준 충돌 비용을 보수적으로 계산한다는 뜻이다(순찰 6~8 모두 이 상태로 주행).

③과 3절의 `patrol_run.sh`가 위치 탐색을 두 번 하는 셈인데, `patrol_run.sh`는 "확인 → 출발"을 한 번에 묶는 안전장치라 그대로 둔다.

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
ros2 daemon stop; rm -f /dev/shm/fastrtps_* /dev/shm/sem.fastrtps_*         # ROS 프로세스가 없을 때만(sem.* 세마포어도 같이, 11-11)
sudo shutdown -h now
```

## 막히면

- **위치 탐색이 80 % 안팎에서 안 올라감**: 로봇 2 m 안에 사람·물건이 있거나, 로봇이 테이프 자리에서 벗어나 탐색 창(±20 cm) 가장자리에 걸린 것. `CX CY R=0.3`으로 창을 옮긴다.
- **순찰 노드가 9 s 만에 "completed"**: 경유점 파일의 마지막 stop이 출발점과 같을 때 생긴다(TROUBLESHOOTING 11-10). `real_loop_waypoints.yaml`은 MID·HOME 두 stop 구조를 유지한다.
- **Nav2가 `active: 0`이고 nav2.log에 `Failed to activate global_costmap because transform from base_link to map did not become available` → `Failed to bring up all requested nodes. Aborting bringup`**: AMCL에 초기 위치를 안 줘서(`set_initial_pose: false`) `map→odom`이 없는 채로 Nav2를 띄운 것(11-11, 새로 부팅한 날). Nav2 런치 PID에 SIGINT(`ps -eo pid,args | grep "[r]os2 launch .*start_nav2_real"`) → 2절 ③ → ⑤. 생명주기 관리자는 한 번 중단하면 스스로 다시 올리지 않는다.
- **`ros2 run`으로 띄운 순찰 노드가 SIGINT로 안 끝남**: 그 PID는 `ros2 run` 껍데기라 자식을 기다리기만 한다. 자식 PID에 보낸다: `kill -INT $(pgrep -P <껍데기 PID>)`. 안 끝난 노드가 `/patrol/state` 발행자로 남으면 NX `corridor_pose.py`가 위치 재탐색을 하지 않는다(TROUBLESHOOTING 11-24).
- **위치 재탐색이 `No unique global scan match`만 반복**: 복도 중간처럼 앞뒤가 대칭인 자리다. 로봇을 HOME 테이프나 코너처럼 고유한 자리에 세우고 기다린다(11-24).
- **NX 부팅 뒤 Nav2가 안 뜸(`ready.py`에서 대기), `/scan`이 수백 Hz에 점이 몇 개뿐**: 시계가 1970년에서 출발해 NTP로 점프하기 전에 센서 유닛이 뜬 것. `timedatectl`로 동기를 확인하고 `systemctl --user restart limbo-nx-sensors` → 위치 재탐색 뒤 Nav2가 스스로 뜬다(TROUBLESHOOTING 11-25).
- **젯슨 ssh가 끊김**: 로봇이 W1 코너(복도 끝)에 있을 때 와이파이가 약하다. 돌아올 때까지 기다리면 된다. 순찰은 젯슨 안에서 계속 돈다.
- **`fastrtps_port … open_and_lock_file failed`가 찍힘**: `timeout`으로 끊은 `ros2 topic …` 명령이 남긴 공유 메모리 찌꺼기. 주행 중 CLI 확인을 줄이고, 5절처럼 ROS가 다 내려간 뒤 `/dev/shm/fastrtps_*`를 지운다.
