# Limbo

사람을 인식하고 피하면서 실내를 순찰하는 쓰레기통 로봇. ROS 2 Jazzy + Gazebo Harmonic + Nav2.

- 센서: Livox MID-360 (3D LiDAR + 내장 IMU), RGB-D 카메라
- 사람 인식: YOLO(yolo11n) + depth로 사람 위치 추정, 칼만 필터로 추적, 2초 앞 경로 예측
- 주행: Nav2 (AMCL 위치 추정, MPPI 컨트롤러, 사람 예측 경로에 cost를 주는 `human_layer`)

| 문서 | 언제 보나 |
|---|---|
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | pull 받은 뒤. 맨 위 "할 일"부터 |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | 에러가 났을 때. 증상 → 원인 → 해결 |
| [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) | 아직 못 고친 문제인지 확인할 때 |
| [docs/PROJECT.md](docs/PROJECT.md) | 프로젝트 개요와 할 일 |

---

## 처음부터 돌려 보기

Ubuntu 24.04 + ROS 2 Jazzy Desktop이 깔려 있다고 가정한다 ([ROS 설치](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html)). 처음 한 번은 인터넷이 필요하다 (YOLO 모델, 걷는 사람 모델 내려받음).

### 1. 설치 (처음 한 번, 10분)

```bash
sudo apt install ros-jazzy-navigation2 ros-jazzy-nav2-bringup ros-jazzy-ros-gz \
  ros-jazzy-cv-bridge ros-jazzy-pcl-ros ros-jazzy-pointcloud-to-laserscan \
  ros-jazzy-spatio-temporal-voxel-layer ros-jazzy-slam-toolbox \
  ros-jazzy-robot-localization ros-dev-tools python3-venv              # ROS 패키지
git clone --recurse-submodules https://github.com/jakemoti0n/final_team7.git ~/limbo   # 저장소 (서브모듈 포함)
python3 -m venv --system-site-packages ~/limbo/venvs/limbo_yolo && \
  ~/limbo/venvs/limbo_yolo/bin/pip install -r ~/limbo/requirements.txt   # YOLO용 Python 환경 (CPU torch)
```

`~/.bashrc` 맨 아래에 붙여 넣고 `source ~/.bashrc`:

```bash
# ===== limbo =====
alias ros_domain="export ROS_DOMAIN_ID=97; echo \"ROS_DOMAIN_ID=97\""
alias jazzy="source /opt/ros/jazzy/setup.bash && ros_domain"
alias goyolo="source ~/limbo/venvs/limbo_yolo/bin/activate"
alias limbo="jazzy && goyolo && source ~/limbo/limbo/install/setup.bash && echo \"limbo is activated\""
alias build_limbo="jazzy && goyolo && cd ~/limbo/limbo && python -m colcon build --symlink-install"
```

→ 터미널에서 `limbo`를 치면 "limbo is activated"가 나온다. NVIDIA GPU가 있으면 아래 "자세히 › GPU torch".

### 2. 빌드

```bash
build_limbo
```

→ 1~2분 뒤 `~/limbo/limbo/install/`이 생긴다. 빌드는 **반드시 `build_limbo`**로 (venv의 python이라야 YOLO를 찾는다).

### 3. 시뮬레이션 띄우기

```bash
limbo
ros2 launch limbo_bringup start_simulation.launch.py
```

→ 15초 뒤 Gazebo(15 m 정사각형 방, 걷는 사람 10명)와 RViz가 열리고 로봇이 원점에 선다. RViz에서 **Nav2 Goal**을 찍으면 바로 간다 (2D Pose Estimate 불필요).

- NVIDIA 노트북이면 launch 전에 `export __NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia` (Gazebo·RViz를 GPU로)
- Gazebo 창이 필요 없으면 `gui:=false` (CPU 절반, RViz로만 본다)

### 4. 순찰

다른 터미널에서:

```bash
limbo
ros2 run limbo_patrol patrol_node --ros-args -p use_sim_time:=true
```

→ 로봇이 waypoint를 차례로 돌고 마지막에 "Patrol mission completed"가 찍힌다. 순찰 중 상태는 `/patrol/state`로 나온다.

### 5. 관제 화면 (일시정지·재개 버튼, 지도 위 로봇 위치)

터미널 셋. 처음 한 번은 설치가 필요하다 ([dashboard/README.md](dashboard/README.md), [relay_prog/README.md](relay_prog/README.md) "설치").

```bash
cd ~/limbo/dashboard && .venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8000 --workers 1   # ① 서버 + 화면
cd ~/limbo/relay_prog && source /opt/ros/jazzy/setup.bash && source install/setup.bash && \
  ros2 run limbo_telemetry_bridge bridge --config src/limbo_telemetry_bridge/config/bridge.yaml           # ② Bridge (로봇 → 서버)
```

→ 브라우저에서 <http://127.0.0.1:8000/> 을 열면 지도 위 로봇 위치, 순찰 상태, **일시정지 / 재개** 버튼이 보인다. 버튼을 누르면 로봇이 멈추고, 재개하면 하던 순찰을 이어 간다. 설계는 [docs/CONTROL_SCREEN.md](docs/CONTROL_SCREEN.md).

---

## 자주 쓰는 변형

```bash
# 학원 2층 (실제 시연 환경, 문 0.9 m, 걷는 사람 3명)
ros2 launch limbo_bringup start_simulation.launch.py world:=aischool_2f map:=aischool_2f_map
ros2 run limbo_patrol patrol_node --ros-args -p use_sim_time:=true -p waypoints:=aischool_waypoints.yaml

# 시연 한 줄: 시뮬레이션을 띄우고 준비되면 순찰까지 자동 시작. Ctrl+C 한 번으로 전부 종료
~/limbo/tools/demo_patrol.sh                                                          # 학원 2층
~/limbo/tools/demo_patrol.sh aischool_2f_furnished aischool_2f_furnished_map aischool_furnished_waypoints.yaml   # 가구 있는 학원 2층
GUI=false ~/limbo/tools/demo_patrol.sh                                                # 화면 없이

# 이전 로봇 모델(0.45 m 정사각형)로 (Nav2 외곽·팽창 값도 예전 값으로)
ros2 launch limbo_bringup start_simulation.launch.py robot:=legacy

# 사람 인식 모델 바꿔 시험 (yaml은 그대로)
ros2 launch limbo_bringup start_simulation.launch.py person_model:=$HOME/limbo/human-leg/runs/person_leg_stage1/weights/best.pt

# 주행 평가 기록: Goal이 끝날 때마다 ~/limbo_results/nav_<월드>_<시각>.csv에 한 줄
ros2 launch limbo_bringup start_simulation.launch.py record:=true
```

| 월드 (`world:=` / `map:=`) | 내용 | 순찰 waypoint (`waypoints:=`) |
|---|---|---|
| `human_test_world` (기본) | 15 m 정사각형 방, 걷는 사람 10명 | `test_waypoints.yaml` (기본) |
| `aischool_2f` / `aischool_2f_map` | 학원 2층, 걷는 사람 3명 | `aischool_waypoints.yaml` |
| `aischool_2f_scenarios` / `aischool_2f_map` | 학원 2층 + 시험용 사람 6명 + 지도에 없는 상자 2개 | `aischool_waypoints.yaml` |
| `aischool_2f_furnished` / `aischool_2f_furnished_map` | 학원 2층 + 실제 가구 (좁은 통로 시험) | `aischool_furnished_waypoints.yaml` |
| `bookstore_world` / `bookstore_map` | 서점, 걷는 사람 2명 (초기 위치 미확인) | `waypoints.yaml` |

---

## 막히면

1. [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)에서 증상으로 찾는다 (Goal을 찍어도 안 움직임, RViz 흰 덩어리, 빌드 실패 등).
2. [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md)에 있으면 아직 못 고친 문제다.
3. pull 받은 직후라면 [docs/CHANGELOG.md](docs/CHANGELOG.md) 맨 위 "할 일"을 했는지 확인한다 (빌드 필요 여부 등).

---

## 자세히

### GPU torch (NVIDIA)

설치 3번째 줄 대신. CUDA 버전 torch(2~3 GB). `requirements.txt`는 고치지 않는다.

```bash
source ~/limbo/venvs/limbo_yolo/bin/activate
grep -v -- '--extra-index-url' ~/limbo/requirements.txt > /tmp/limbo_req_gpu.txt && pip install -r /tmp/limbo_req_gpu.txt
source /opt/ros/jazzy/setup.bash && python -c "import torch, ultralytics, cv_bridge; print(torch.cuda.is_available())"   # True면 성공
```

### 설치·빌드 참고

- `rosdep install --from-paths ~/limbo/limbo/src --ignore-src -r -y --rosdistro jazzy`: 빠진 ROS 의존성 설치 (처음이면 `sudo rosdep init && rosdep update`)
- push까지 하려면 SSH 키를 등록하고 `git@github.com:jakemoti0n/final_team7.git` 주소를 쓴다. 서브모듈 없이 받았다면 `git submodule update --init --recursive`
- `ROS_DOMAIN_ID=97`: 같은 번호끼리만 ROS 통신이 된다. 팀원과 맞출 것
- RAM 8 GB 이하면 `MAKEFLAGS="-j2" python -m colcon build --symlink-install --executor sequential`

### 시뮬레이션 참고

- launch 하나로 Gazebo, EKF, self filter, LiDAR→`/scan`, AMCL, Nav2, RViz, 사람 인식, 바퀴 헛돎 감시가 순서대로 뜬다
- AMCL은 스폰 위치(0, 0, 0°)에서 시작한다. 위치가 틀어지면 RViz의 2D Pose Estimate로 다시 맞춘다
- 로봇 모델은 실제 로봇 v14가 기본. 자세한 내용은 `limbo_description/README.md`
- 학원 2층 월드·지도는 문 폭 0.9 m(실제 기준)로 만들었다. 월드 물리 스텝은 2 ms (1 ms면 실시간 비율이 0.6에 머묾)
- `aischool_2f_scenarios`의 사람은 정해진 시간표대로 움직이고 로봇에 반응하지 않는다. 장소마다 상황 하나씩: 시작 위치 1.6 m 앞에 와서 4초 멈춤, 홀→오른쪽 복도로 꺾음, 왼쪽 복도에 서 있음, 위쪽 복도에 둘이 나란히, 왼쪽 아래 복도에 빨리 걸음. 경로는 `tools/aischool_2f/gen_world.py`의 `SCENARIO_PATHS`. 가구 배치는 `tools/aischool_2f/furniture.py`

### 순찰 참고

- 새 월드용 waypoint는 `limbo_patrol/config/`에 yaml을 추가하고 `build_limbo` 후 `-p waypoints:=새파일.yaml`
- 마지막 waypoint는 `type: stop`이어야 한다. 파일 이름이 틀리면 Nav2를 기다리기 전에 바로 오류가 난다
- 순찰 노드는 위치 추정을 30초만 기다린다. 시뮬레이션 launch와 순찰 노드를 손으로 이어 치면 시간 초과로 끝날 수 있어 `demo_patrol.sh`가 준비될 때까지 기다렸다가 시작한다
- 일시정지·재개 서비스: `/patrol/pause`, `/patrol/resume`, 상태 `/patrol/state`
- 반복 순찰: `-p loop:=true`(시연 스크립트는 `LOOP=1 tools/demo_patrol.sh`, 학원 2층은 A를 `stop`으로 둔 `aischool_loop_waypoints.yaml`을 씀 — `pass`면 2바퀴째 G → A → B 되돌아가는 경로에서 A 앞에 막힘). 마지막 waypoint 뒤에 첫 번째부터 다시 돌고, 일시정지로만 멈춘다. 상태 사유에 `lap N started`가 남는다
- 이동 실패: `retry_delay_sec`(3초) 뒤 남은 지점으로 `retries`(2)번 다시 보내고, 그래도 안 되면 순찰을 끝내지 않고 `paused`(사유 `navigation failed`)로 멈춘다. 확인 후 재개하면 남은 지점부터 간다

### 주행 평가 기록 (`record:=true`) CSV 열

| 열 | 내용 |
|---|---|
| `status` | SUCCEEDED / ABORTED / CANCELED / PREEMPTED(끝나기 전에 새 Goal) |
| `duration_s`, `path_length_m`, `mean_speed_mps` | 걸린 시간, 실제 주행 거리, 평균 속도 (Gazebo 정답 위치 기준) |
| `min_person_distance_m`, `nearest_person` | 사람 중심까지 가장 가까웠던 거리와 그 사람 (월드 SDF의 시간표 기준). 0.3 m 미만이면 사람 모델과 겹친 것(충돌) |
| `personal_space_time_s` | 사람 0.5 m 안에 있던 시간 (`nav_recorder.yaml`의 `personal_space`) |
| `action` | Goal이 온 액션. `navigate_to_pose`(RViz·`nav_route.py`) 또는 `navigate_through_poses`(순찰 노드, 정지 waypoint 사이 묶음 하나가 한 줄) |
| `person_approach_speed_mps`, `robot_speed_at_min_mps` | 사람 최소 거리 순간에 사람이 로봇 쪽으로 다가온 속도(양수 = 다가옴)와 그때 로봇 속도. 0.5 s 전 위치와 비교(`speed_window`). 사람이 멈춘 로봇에 걸어 들어온 충돌(사람 탓)과 로봇이 사람에게 간 충돌(로봇 탓)을 가른다 |
| `person_collision`, `person_collision_time_s` | 사람 중심과 0.3 m 미만으로 겹친 적이 있으면 1, 겹쳐 있던 시간. 시뮬레이션 사람은 충돌이 없어 뚫고 지나가도 `status`는 SUCCEEDED가 되므로 이 열로 거른다 (`collision_distance`) |
| `stopped_time_s`, `stopped_near_person_s`, `stopped_other_s` | 0.05 m/s 미만으로 멈춰 있던 시간. 그중 사람이 1.5 m 안에 있던 시간(사람 때문에 멈춤)과 그 밖(막혀서 멈춤) (`stop_speed`, `near_person_distance`) |
| `plan_updates`, `plan_changes` | 전역 경로를 받은 횟수와 그중 직전 경로에서 0.3 m 넘게 벗어난 횟수. 사람 꼬리로 경로가 흔들리는 정도 (`plan_change_distance`) |
| `min_obstacle_distance_m`, `nearest_obstacle`, `obstacle_contact_time_s` | 지도에 없는 장애물(SDF 이름이 `obstacle_`로 시작)까지 가장 가까웠던 거리, 그 장애물, 닿아 있던 시간 |
| `localization_error_mean_m`, `_max_m` | 위치 추정 오차 (TF `map → base_footprint`와 정답 비교) |
| `recoveries`, `controller_rate_warnings`, `wheel_slip_events` | 복구 동작 횟수, 컨트롤러 주기 경고 수, 헛돎 감지 수 |

시뮬레이션 전용. 정답 위치는 `/ground_truth/odom`(주행 노드는 안 씀). 지도 원점과 월드 원점이 같다고 가정한다. 사람은 시간표대로 움직이므로 같은 시각에 같은 Goal을 보내면 같은 상황이 재현된다.

### 새 지도 만들기 (SLAM)

시뮬레이션을 띄운 상태에서 다른 터미널로:

```bash
limbo
ros2 launch slam_toolbox online_async_launch.py use_sim_time:=true \
  slam_params_file:=$HOME/limbo/limbo/install/limbo_navigation/share/limbo_navigation/config/slam.yaml
```

로봇을 돌아다니게 한 뒤 `ros2 run nav2_map_server map_saver_cli -f <이름>`으로 저장하고, `.pgm`·`.yaml`을 `limbo_navigation/maps/`에 넣는다.

### 충장로 맛보기 (생성해서 쓰는 야외 월드)

광주 충장로 보행자 거리 200 m 구간을 OpenStreetMap 자료로 만든 월드다. 건물 메시가 커서 산출물(월드·지도)은 저장소에 없고, 처음 한 번 생성해서 쓴다 (`cv2`·`numpy` 필요).

```bash
cd ~/limbo/limbo/src/limbo_simulation/tools/chungjang && python3 gen_street.py   # 월드 chungjang·지도 chungjang_map 생성
build_limbo                                                                         # 생성한 월드를 설치 폴더로
ros2 launch limbo_bringup start_simulation.launch.py world:=chungjang map:=chungjang_map
```

### 자주 쓰는 명령

```bash
ros2 topic echo /clicked_point                                                        # RViz Publish Point로 찍은 좌표 (waypoint 만들 때)
ros2 service call /collision_monitor/toggle nav2_msgs/srv/Toggle "{enable: false}"   # Collision Monitor 끄기 (켤 때는 true)
```

### 패키지 구성

| 패키지 | 내용 |
|---|---|
| `limbo_bringup` | 통합 실행 `start_simulation.launch.py` |
| `limbo_description` | 로봇 모델 (URDF): 실제 로봇 v14(기본), 이전 모델 `urdf/legacy/`. Gazebo 센서(MID-360 LiDAR·IMU, RGB-D 카메라) |
| `limbo_simulation` | Gazebo 월드, ros_gz 브리지 설정, `tools/aischool_2f/`(도면 사진 → 월드·지도 생성) |
| `limbo_navigation` | Nav2 설정(`nav2_params.yaml`), AMCL, EKF, 지도, 사람 cost 플러그인 `human_layer` |
| `limbo_perception` | `person_detector`: YOLO 사람 인식·추적·경로 예측 |
| `limbo_interfaces` | 사람 예측 메시지 `PersonPrediction(Array)`, 순찰 상태 `PatrolState` |
| `limbo_patrol` | waypoint 순찰. 일시정지·재개 서비스 |
| `limbo_monitor` | `wheel_slip_monitor`: 바퀴 헛돎 감지 |
| `limbo_evaluation` | `nav_recorder`: Goal마다 주행 평가 지표를 CSV로 기록 (시뮬레이션 전용) |
| `robot_self_filter` | (서브모듈) LiDAR에서 로봇 몸체 점을 걸러 냄 |
| `dashboard/` | 관제 서버(FastAPI)와 화면(React) |
| `relay_prog/` | Bridge: 로봇 상태를 서버로 보내고 서버 명령을 순찰 노드에 전달 |

### 주요 토픽

| 토픽 | 내용 |
|---|---|
| `/mid360/points` → `/mid360/points_filtered` → `/scan` | 3D LiDAR → 몸체 제거 → 2D 스캔 |
| `/imu` | MID-360 내장 IMU (200 Hz) |
| `/odom` | 바퀴 odom. `odom → base_footprint` TF는 EKF가 냄 (`/odometry/filtered`) |
| `/person_detector/predictions` | 사람별 현재 위치·속도·2초 앞 예측 (→ `human_layer`) |
| `/person_detector/annotated_image` | YOLO 결과 이미지 (RViz Image로 보기) |
| `/person_detector/approach_intent` | 로봇에게 다가오는 사람이 있는지 |
| `/patrol/state` | 순찰 상태 (`PatrolState`) |
| `/wheel_slip` | 바퀴 헛돎 여부 |

### 튜닝 값 위치

빌드 없이 노드만 다시 띄우면 적용된다.

| 파일 | 내용 |
|---|---|
| `limbo_perception/config/person_detector.yaml` | YOLO confidence, 추적, 예측 시간, 접근 의도 판단 |
| `limbo_navigation/config/nav2_params.yaml` | Nav2 전체 (MPPI, costmap, collision monitor 등) |
| `limbo_navigation/config/amcl.yaml` | AMCL, 초기 위치 |
| `limbo_navigation/config/ekf.yaml` | 바퀴 odom + IMU 융합 |
| `limbo_monitor/config/wheel_slip_monitor.yaml` | 헛돎 판단 기준 |
| `limbo_evaluation/config/nav_recorder.yaml` | 평가 결과 폴더, 개인 공간 거리 |

### 하드웨어 조립 후 조정할 값

원작자 메모 (2026-09).

- `nav2_params.yaml`의 collision monitor `source_timeout`: 노트북 과열로 2.0으로 설정. 0.5까지 점차 줄여 볼 것 (과열 원인이었던 person_detector CPU 문제는 2026-10-02에 해결됨)
- `person_detector.yaml`의 `tracking.reassociate_max_age`: 추적한 사람 정보를 유지하는 시간(3초). 사람이 많이 교차하는 실제 환경에서 지켜볼 것
- SLAM으로 처음 지도를 만들 때 포인트클라우드에서 잘라 오는 높이: 지금은 LiDAR 기준 +20 cm까지 장애물로 봐서, 지나갈 수 있는 높이의 장애물을 못 지나가거나 돌아가는 경우가 있음
- 구동부: 모터 IG-32GM(1:71, 정격 83 RPM) × 2, 바퀴 지름 15 cm → 정격 0.65 m/s, 실주행 최고 약 0.8 m/s. Nav2 속도 상한은 이 안에서 둔다

### 작업 방식

- 작업은 개인 브랜치에서 하고 `dev`에 합친다. 리팩터링 전 원본은 `kkh` 브랜치에 있다
- 커밋 메시지는 바꾼 이유 한 줄. "수정본", "최종" 같은 메시지는 쓰지 않는다
- `dev`에 올릴 때 `docs/CHANGELOG.md` 맨 위에 항목을 추가한다 (할 일 / 변경 / 참고)
- 문제를 해결하면 `docs/TROUBLESHOOTING.md`에 남기고, `KNOWN_ISSUES.md`에 있던 항목이면 거기서 지운다
