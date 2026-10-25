---
name: split-sim
description: LIMBO 시뮬레이션을 두 대로 나눠 돌리는 설정·확인·측정 안내. PC는 Gazebo(role:=sim), Jetson Orin Nano는 실물에서 돌릴 로봇 스택(role:=robot). Jetson에서 시뮬이 느리다, 메모리 부족, load average가 높다, AMCL이 TF 시각이 안 맞는다고 한다, /scan이 느리다, 젯슨에 올려 보자, 두 대로 나눠 돌리자, 보드 부하를 재자, role:=robot, OAK 카메라를 젯슨에 꽂고 재자, camera:=oak 같은 말이 나오면 반드시 이 스킬을 따른다. 사람이 읽어도 그대로 따라 할 수 있게 썼다.
---

# 시뮬레이션 두 대로 나눠 돌리기 (PC = Gazebo, Jetson = 로봇 스택)

## 왜 나누나

Jetson Orin Nano(ARM 6코어, 메모리 8 GB를 GPU와 공유)에서 시뮬 전체를 돌리면 Gazebo 센서 렌더링(라이다 43,200 광선 10 Hz, 카메라 15 Hz)만으로 코어가 밀려
real-time factor 0.56, /scan 1~2 Hz, load average 20, 메모리 부족이 난다(2026-10-22 측정). 그러면 TF가 늦어 AMCL이 스캔을 버린다.
Jetson은 실물에서 **로봇 스택만** 돌리는 컴퓨터다. 그래서 Gazebo와 센서 가공은 PC에 두고, Jetson에는 실물에서 돌릴 것만 올린다.
이렇게 해야 "Jetson이 실물 스택을 감당하는가"를 Gazebo 부하와 섞이지 않게 잴 수 있다.

| role | 띄우는 것 | 어디서 |
|---|---|---|
| `sim` | Gazebo, robot_state_publisher, 브리지, self_filter, pointcloud_to_laserscan, rviz | PC |
| `robot` | EKF, wheel_slip_monitor, AMCL(map_server), Nav2, person_detector(YOLO, camera:=oak면 YOLO 없이 추적만), oak_camera(camera:=oak만), tof_node, person_wait | Jetson |
| `all` (기본) | 전부 | 한 대 (지금까지와 같음) |

네트워크로 오가는 것: PC→Jetson /clock, /scan, /odom, /imu, /joint_states, TF, 카메라 컬러·깊이(약 65 Mbit/s), /tof/points,
그리고 Nav2 코스트맵·collision_monitor가 받는 /rgbd_camera/points(약 213 Mbit/s)·/mid360/points_filtered(약 50 Mbit/s). Jetson→PC /cmd_vel.
role:=robot에서는 Nav2를 한 프로세스(nav2_container)로 모아 포인트클라우드를 한 벌만 받는다. 합계 약 350 Mbit/s, 모으지 않으면 약 910 Mbit/s
(2026-10-22, PC 한 대에서 robot 쪽을 UDP로만 붙여 루프백으로 잼). **유선(1 GbE)이 사실상 필수**이고 Wi-Fi로는 못 따라온다.

## 이 스킬을 따르는 에이전트에게

- 아래 순서대로 하고, 각 단계의 "→" 결과가 나오는지 확인한 뒤 다음으로 간다. 건너뛰지 않는다.
- 결정은 두 단계다. **자잘한 것은 작업자(지금 함께 있는 팀원)가 정하고, 중대한 것은 작업자를 거쳐 PM(ktj 담당)이 정한다.**
  에이전트는 어느 쪽이든 혼자 정하지 않는다. 조용히 우회하면 PM이 결정할 기회를 잃고 팀원마다 다른 구성이 생긴다.
- 자잘한 결정(작업자에게 물어 바로 답을 받는다): 로그 파일 위치·이름, 측정 시간(2분 이상이면 됨), 로봇을 순찰로 움직일지 RViz Goal로 움직일지,
  안내에 있는 월드·지도 중 무엇을 쓸지, 같은 것을 한 번 더 띄워 볼지, 무선에서 유선으로 바꿀지(안내가 권하는 쪽), 어느 컴퓨터에서 확인 스크립트를 돌릴지.
- 중대한 결정(작업자가 PM에게 물어 답을 받아 온다): 런치·yaml·코드의 값을 바꾸는 것, 이 안내에 없는 패키지를 설치하거나 다른 버전(예: Jetson용 torch)으로 바꾸는 것,
  노드를 다른 컴퓨터로 옮기거나 센서 주기·해상도를 줄이는 것, "막히면"에 적힌 조치를 다 했는데도 안 될 때 다음 수를 고르는 것,
  무엇이든 2번 다시 해도 같은 결과가 나올 때. 이 안내에 적힌 명령을 그대로 치는 것과 "막히면"에 적힌 조치는 묻지 않고 한다.
- 중대한 결정을 물을 때는 아래 형식으로 짧게. 추천은 적되 답을 기다린다("진행할까요?" 뒤에 다른 작업을 이어 가지 않는다).
  자잘한 결정은 형식 없이 한 줄로 묻는다.

  ```
  [PM 확인 필요]
  상황: (어느 단계에서, 무엇이 안 되는지. 로그 줄·숫자 그대로)
  해 본 것: (막히면 몇 번까지)
  선택지: A) … B) … (추천: A, 이유 한 줄)
  진행할까요?
  ```

- 프로세스는 Ctrl+C 또는 PID로만 끝낸다. `pkill -f <패턴>`은 자기 셸까지 죽인다.
- 결과 보고는 맨 아래 "보고 형식"대로 숫자 표로 작업자에게 낸다. 작업자가 그대로 PM에게 전달한다.

## 0. 준비물

- PC: 이 저장소가 빌드돼 있고 Gazebo가 뜨는 컴퓨터(README "처음부터 돌려 보기"). NVIDIA면 `export __NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia`.
- Jetson: Ubuntu 24.04 + ROS 2 Jazzy, 이 저장소를 README 1·2절대로 설치·빌드. Gazebo 패키지(`ros-jazzy-ros-gz`)는 없어도 된다(로봇 쪽 노드·빌드가 참조하지 않음). 이미 깔려 있어도 상관없다.
  YOLO용 venv에서 `requirements.txt`의 torch가 ARM에 안 깔리면 멈추고 작업자에게 [PM 확인 필요]로 묻는다(Jetson용 torch 휠을 쓸지는 PM이 정함).
- 두 대가 **같은 공유기**에 있고 서로 ping이 된다. 가능하면 유선. `~/.bashrc`의 `limbo` 별칭이 `ROS_DOMAIN_ID=97`을 잡는다(README 1절). 두 대 모두 97.
- `ROS_LOCALHOST_ONLY`가 설정돼 있으면 안 된다: `echo $ROS_LOCALHOST_ONLY` → 비어 있어야 한다.

두 대가 서로 보이는지 먼저 확인한다(각각 다른 터미널에서):

```bash
limbo && ros2 multicast receive    # 한쪽
limbo && ros2 multicast send       # 다른 쪽
```

→ receive 쪽에 "Received from …"가 찍힌다. 안 찍히면 "막히면 1".

## 1. PC에서 Gazebo 띄우기 (role:=sim)

```bash
limbo
ros2 launch limbo_bringup start_simulation.launch.py role:=sim world:=aischool_2f map:=aischool_2f_map
```

→ 15초 안에 Gazebo와 RViz가 열리고, 다른 터미널에서 `limbo && ros2 topic hz /scan`이 약 10 Hz(노트북에서 7~10)로 나온다. Nav2는 아직 없다(정상).

## 2. Jetson에서 로봇 스택 띄우기 (role:=robot)

PC가 뜬 뒤에 한다(Jetson 노드는 PC의 /clock·TF를 받아야 시작된다).

```bash
limbo
ros2 launch limbo_bringup start_simulation.launch.py role:=robot world:=aischool_2f map:=aischool_2f_map gui:=false
```

→ 30~60초 뒤 로그에 Nav2 lifecycle "Managed nodes are active"가 찍히고, PC의 RViz에 지도 위 로봇과 코스트맵이 보인다.

## 3. 붙었는지 확인

어느 쪽에서든(이 스킬 폴더의 스크립트):

```bash
limbo && bash .claude/skills/split-sim/scripts/check_split.sh
```

→ 다음이 나와야 한다. 하나라도 아니면 "막히면"을 보고, 거기 없으면 출력 그대로 붙여 작업자에게 [PM 확인 필요]로 묻는다.

| 항목 | 기대 |
|---|---|
| 노드 수 | 20개 이상 (양쪽 노드가 다 보임) |
| /scan | 7~10 Hz |
| /clock | 수백 Hz |
| bt_navigator | active |
| TF map→base_footprint | Translation 줄이 나옴 (AMCL 동작) |

## 4. 부하 재기 (양쪽에서 같은 것을 2분)

Jetson에서(런치 로그를 파일로 남겼다면 세 번째 인자로 주면 AMCL 경고 수도 센다):

```bash
bash .claude/skills/split-sim/scripts/load_watch.sh 120 ~/split_jetson.out
```

PC에서도 `~/split_pc.out`으로 같이 돌린다. 5초마다 load average·가용 메모리·CPU 상위 3개, 20초마다 /scan·/cmd_vel·/tf 주기가 쌓인다.

재는 동안 로봇을 움직인다(가만히 서 있을 때와 주행 중 부하가 다르다). Jetson에서:

```bash
limbo && ros2 run limbo_patrol patrol_node --ros-args -p use_sim_time:=true -p waypoints:=aischool_waypoints.yaml
```

→ 로봇이 waypoint를 돌고 "Patrol mission completed". RViz에서 Nav2 Goal을 찍어도 된다.

비교 기준(Jetson 한 대에 전부 올렸을 때, 2026-10-22): load average 20, real-time factor 0.56, /scan 1~2 Hz, 메모리 부족, AMCL TF 시각 불일치 경고.
Jetson의 load1이 코어 수(6) 아래이고 /scan이 PC와 같은 주기로 들어오며 AMCL 경고가 0이면 분리가 성공한 것이다.

## 4-2. 실물 OAK 카메라까지 붙여 재기 (camera:=oak)

실물에서 Jetson이 하는 일에는 OAK-D Lite에서 영상·깊이를 받고 카메라 안 모델 결과로 사람을 추적하는 것도 있다(Jetson은 YOLO를 돌리지 않는다).
`camera:=oak`를 **두 대 모두에** 주면 PC는 Gazebo 카메라 영상 브리지를 끄고, Jetson은 `oak_camera` 노드가 USB로 꽂힌 OAK를 열어 같은 토픽(/rgbd_camera/image·depth_image·camera_info)과
/oak/detections를 낸다. person_detector는 YOLO를 올리지 않고 그 결과에 BoT-SORT만 돌린다. PC→Jetson 카메라 영상(약 65 Mbit/s)이 없어진다.
Nav2가 받는 /rgbd_camera/points는 시뮬 월드와 맞도록 Gazebo 것을 그대로 쓴다.

먼저 Jetson에서 카메라 단독 점검(변경 기록 45의 할 일: udev 규칙, `tools/oak/check_camera.py`, `run_leg_model.py`)이 통과해야 한다.
venv에 depthai가 없으면 `pip install -r requirements.txt`를 다시 한다(`depthai<3` 포함). USB 3 케이블이면 `limbo_perception/config/oak_camera.yaml`의 `usb_speed`를 `super`로(2.0 케이블은 `high` 그대로).

```bash
# PC
ros2 launch limbo_bringup start_simulation.launch.py role:=sim camera:=oak world:=aischool_2f map:=aischool_2f_map
# Jetson (PC가 뜬 뒤)
ros2 launch limbo_bringup start_simulation.launch.py role:=robot camera:=oak world:=aischool_2f map:=aischool_2f_map gui:=false
```

→ Jetson 로그에 `oak_camera: OAK-D-LITE 연결 | USB HIGH`(또는 SUPER), person_detector `started (source oak)`, 그 뒤 10초마다 `발행 14~15 Hz … 지연 중앙값 ~230 ms`.
`ros2 topic info /rgbd_camera/image`의 Publisher count가 1(oak_camera)이어야 한다. 2면 한쪽에 camera:=oak를 빠뜨린 것이다.

- 카메라는 시뮬 로봇과 같이 움직이지 않는다. **로봇을 세워 두고** 카메라 앞에 사람이 서거나 걸으며 잰다. 순찰을 돌리면 사람 위치·속도가 틀어진다(odom 좌표가 로봇과 같이 돌기 때문). 주행 평가에는 쓰지 않는다.
- oak_camera는 stamp를 시뮬 TF에 맞추려고 /clock을 받는다. 실물에는 없는 부하이므로 보고에 "oak_camera CPU에 /clock 포함"이라고 적는다.
- `OAK 장치 오류: … → N초 뒤 다시 연결`이 계속 찍히면 oak_camera가 장치를 못 여는 것이다(노드는 살아서 1→2→4…10초 간격으로 다시 시도한다).
  `Cannot find any device`면 `lsusb | grep 03e7`부터, `X_LINK_DEVICE_ALREADY_IN_USE`면 `tools/oak` 점검 도구나 다른 oak_camera가 떠 있는지 본다.
  연결됐다 끊기기를 반복하고 `journalctl -k | grep "usb 1-"`에 `error -71`·`-110`이 있으면 케이블·포트·전원 문제다(변경 기록 46). 케이블부터 바꾼다.

## 5. 끝내기

양쪽 런치 터미널에서 Ctrl+C. 그 뒤 남은 것이 없는지:

```bash
ps -eo pid,args | grep -E 'ekf_node|parameter_bridge|gz sim|nav2|person_detector|oak_camera' | grep -v grep
```

→ 아무것도 안 나와야 한다. 남아 있으면 그 PID만 `kill <PID>`. ROS 프로세스가 하나도 없을 때 `rm -f /dev/shm/fastrtps_*`로 DDS 공유 메모리를 지운다
(강제 종료된 노드가 남긴 파일이 다음 시작을 막는다, docs/TROUBLESHOOTING.md 2026-10-14).

## 막히면

1. **`ros2 node list`에 상대 노드가 없다 / multicast가 안 온다**
   - 양쪽 `echo $ROS_DOMAIN_ID`가 97인지, `ROS_LOCALHOST_ONLY`가 비었는지.
   - `ros2 daemon stop && ros2 daemon start` 뒤 다시 본다(먼저 떠 있던 데몬이 새 노드를 못 보는 일이 있다).
   - 방화벽: `sudo ufw status`가 active면 `sudo ufw allow from 192.168.0.0/16`(자기 대역으로).
   - 그래도 안 되면 공유기가 멀티캐스트를 막는 것이다(학원·회사 Wi-Fi의 클라이언트 격리). `assets/fastdds_peers.xml`의 주소를 상대 IP로 바꿔 양쪽 모두
     `export FASTRTPS_DEFAULT_PROFILES_FILE=<그 파일 경로>`를 한 터미널에서 런치한다(유니캐스트로 서로 찾음). 여기까지 했는데도 안 되면 [PM 확인 필요].
2. **Jetson에서 AMCL "Message Filter dropping message" / TF 시각 경고가 계속 난다**
   - 먼저 Jetson의 `ros2 topic hz /scan`과 PC의 값을 비교한다. Jetson이 눈에 띄게 낮으면 네트워크가 못 따라오는 것(카메라 영상이 Wi-Fi를 채움) → 유선으로 바꾸고 다시 잰다.
   - 같은 주기인데도 경고가 나면 Jetson 자체가 밀리는 것이다. load_watch 결과(load1, CPU 상위 프로세스)를 붙여 [PM 확인 필요]. 값을 바꿔 맞추지 않는다.
3. **person_detector의 "extrapolation into the future … 10~20 ms" 경고가 10초에 한두 건**: 한 대에서 돌릴 때도 나는 정상 범위다. 매 프레임 나면 2번.
4. **Jetson에서 `package 'limbo_simulation' not found`**: 런치 파일이 시뮬 패키지 경로를 읽는다. 빌드에 포함돼야 한다(`build_limbo`가 전체를 빌드하면 들어 있다).
5. **Nav2가 configure에서 멈춘다(lifecycle timeout)**: 시작 부하 문제로 한 대에서도 가끔 난다. Ctrl+C 뒤 5절대로 정리하고 한 번 다시 띄운다. 두 번째도 실패하면 [PM 확인 필요].

## 보고 형식

```
구성: PC <호스트명>(role:=sim) + Jetson(role:=robot), camera sim/oak, 연결 유선/무선, 월드 aischool_2f
확인: 노드 N개, /scan Jetson X Hz / PC Y Hz, bt_navigator active, TF map→base_footprint 있음
Jetson 2분: load1 평균 a / 최대 b, 가용 메모리 최소 c MB, CPU 상위 (프로세스 %), AMCL 경고 n건
PC 2분:     load1 평균 / 최대, /scan Hz
주행: 순찰 waypoint k/k, 멈춤·이상 (있으면 시각과 로그 줄)
OAK(camera:=oak만): oak_camera 발행 Hz·지연 중앙값·칩 온도, oak_camera·person_detector CPU %
문제: (없음 / 증상 그대로)
```
