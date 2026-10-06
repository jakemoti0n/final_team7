# Limbo

사람을 인식하고 피하면서 실내를 순찰하는 로봇. ROS 2 Jazzy + Gazebo Harmonic + Nav2.

- 센서: Livox MID-360 (3D LiDAR + 내장 IMU), RGB-D 카메라
- 사람 인식: YOLO(yolo11n) + depth로 사람 위치 추정, 칼만 필터로 추적, 2초 앞 경로 예측
- 주행: Nav2 (AMCL 위치 추정, MPPI 컨트롤러, 사람 예측 경로에 cost를 주는 `human_layer`)

## 문서

| 문서 | 내용 |
|---|---|
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | 무엇이 바뀌었고 pull한 뒤 무엇을 해야 하는지. **pull 받으면 맨 위 "할 일"부터** |
| [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) | 아직 해결하지 못한 문제 |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | 겪었던 문제의 증상·원인·해결. 에러가 나면 여기부터 찾기 |
| [docs/PROJECT.md](docs/PROJECT.md) | 프로젝트 개요와 할 일 |

---

## 설치 (처음 한 번)

Ubuntu 24.04, ROS 2 Jazzy Desktop이 설치돼 있다고 가정한다.

### 1. ROS 패키지

```bash
sudo apt install \
  ros-jazzy-navigation2 ros-jazzy-nav2-bringup ros-jazzy-ros-gz \
  ros-jazzy-cv-bridge ros-jazzy-pcl-ros ros-jazzy-pointcloud-to-laserscan \
  ros-jazzy-spatio-temporal-voxel-layer ros-jazzy-slam-toolbox \
  ros-jazzy-robot-localization python3-venv
```

### 2. 저장소 받기

서브모듈(`robot_self_filter`)이 있어서 `--recurse-submodules`가 꼭 필요하다. 아래 경로(`~/limbo`)를 기준으로 alias와 문서가 쓰여 있다.

```bash
git clone --recurse-submodules git@github.com:jakemoti0n/final_team7.git ~/limbo
```

### 3. YOLO용 Python 환경

`limbo_perception`은 YOLO가 설치된 별도 venv에서 돈다.

```bash
python3 -m venv --system-site-packages ~/limbo/venvs/limbo_yolo
source ~/limbo/venvs/limbo_yolo/bin/activate
pip install --upgrade pip
pip install -r ~/limbo/requirements.txt
```

- **NVIDIA GPU가 있으면** `requirements.txt`의 `--extra-index-url` 줄을 빼고 설치한다 (CUDA 버전 torch, 2~3GB). 그대로 설치하면 CPU 버전
- 확인: `python -c "import torch, ultralytics, cv_bridge; print(torch.cuda.is_available())"`

### 4. alias 등록

`~/.bashrc` 맨 아래에 추가하고 `source ~/.bashrc`.

```bash
# ===== limbo =====
alias ros_domain="export ROS_DOMAIN_ID=97; echo \"ROS_DOMAIN_ID=97\""
alias jazzy="source /opt/ros/jazzy/setup.bash && ros_domain"
alias goyolo="source ~/limbo/venvs/limbo_yolo/bin/activate"
alias limbo="jazzy && goyolo && source ~/limbo/limbo/install/setup.bash && echo \"limbo is activated\""
alias build_limbo="jazzy && goyolo && cd ~/limbo/limbo && python -m colcon build --symlink-install"
```

- `ROS_DOMAIN_ID=97`: 같은 번호끼리만 ROS 통신이 된다. 팀원과 맞출 것
- **빌드는 반드시 `build_limbo`로.** venv의 python으로 colcon을 돌려야 `limbo_perception`이 YOLO를 찾는다

### 5. 빌드

```bash
build_limbo
```

RAM 8GB 이하 PC는 병렬 빌드 중 멈출 수 있다: `MAKEFLAGS="-j2" python -m colcon build --symlink-install --executor sequential`

---

## 실행

```bash
limbo
export __NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia   # NVIDIA 노트북이면 (Gazebo·RViz를 GPU로)
ros2 launch limbo_bringup start_simulation.launch.py
```

이 launch 하나로 Gazebo, EKF, self filter, LiDAR→`/scan` 변환, AMCL, Nav2, RViz, 사람 인식, 바퀴 헛돎 감시가 순서대로 뜬다 (약 15초).

- **2D Pose Estimate 없이 바로 Goal을 찍어도 된다.** AMCL이 스폰 위치(0, 0, 0°)에서 시작한다
- 다른 곳에서 시작했거나 위치가 틀어지면 RViz의 2D Pose Estimate로 다시 맞춘다

### 월드 바꾸기

월드와 지도는 같은 건물끼리 짝지어 바꾼다.

| 월드 | 명령 인자 | 내용 |
|---|---|---|
| `human_test_world` (기본) | 없음 | 15m 정사각형 방, 걷는 사람 10명 |
| `aischool_2f` | `world:=aischool_2f map:=aischool_2f_map` | 학원 2층 (피난안내도로 만든 실제 구조), 걷는 사람 3명 |
| `bookstore_world` | `world:=bookstore_world map:=bookstore_map` | 서점, 걷는 사람 2명. 초기 위치가 맞는지 아직 확인 안 함 (틀리면 2D Pose Estimate) |

### 자주 쓰는 명령

```bash
ros2 run limbo_patrol patrol_node        # waypoint 순찰 (limbo_patrol/config/waypoints.yaml)
ros2 topic echo /clicked_point           # RViz Publish Point로 찍은 좌표 (waypoint 만들 때)

# Collision Monitor 켜기/끄기 (끌 때는 false)
ros2 service call /collision_monitor/toggle nav2_msgs/srv/Toggle "{enable: true}"
```

### 새 지도 만들기 (SLAM)

시뮬레이션을 띄운 상태에서 다른 터미널로:

```bash
limbo
ros2 launch slam_toolbox online_async_launch.py use_sim_time:=true \
  slam_params_file:=$HOME/limbo/limbo/install/limbo_navigation/share/limbo_navigation/config/slam.yaml
```

로봇을 돌아다니게 한 뒤 `ros2 run nav2_map_server map_saver_cli -f <이름>`으로 저장하고, 만들어진 `.pgm`, `.yaml`을 `limbo_navigation/maps/`에 넣는다.

---

## 패키지 구성

| 패키지 | 내용 |
|---|---|
| `limbo_bringup` | 통합 실행 `start_simulation.launch.py` |
| `limbo_description` | 로봇 모델 (URDF), Gazebo 센서(MID-360 LiDAR·IMU, RGB-D 카메라) |
| `limbo_simulation` | Gazebo 월드, ros_gz 브리지 설정, `tools/aischool_2f/`(도면 사진 → 월드·지도 생성 스크립트) |
| `limbo_navigation` | Nav2 설정(`nav2_params.yaml`), AMCL, EKF, 지도, 사람 cost 플러그인 `human_layer` |
| `limbo_perception` | `person_detector`: YOLO 사람 인식·추적·경로 예측 |
| `limbo_interfaces` | 사람 예측 메시지 `PersonPrediction(Array)` |
| `limbo_patrol` | waypoint 순찰 |
| `limbo_monitor` | `wheel_slip_monitor`: 바퀴 헛돎을 감지하면 Nav2 Goal을 취소 |
| `robot_self_filter` | (서브모듈) LiDAR에서 로봇 몸체 점을 걸러 냄 |

### 주요 토픽

| 토픽 | 내용 |
|---|---|
| `/mid360/points` → `/mid360/points_filtered` → `/scan` | 3D LiDAR → 몸체 제거 → 2D 스캔 |
| `/imu` | MID-360 내장 IMU (200Hz) |
| `/odom` | 바퀴 odom (diff-drive). `odom → base_footprint` TF는 EKF가 냄 (`/odometry/filtered`) |
| `/person_detector/predictions` | 사람별 현재 위치·속도·2초 앞 예측 (→ `human_layer`) |
| `/person_detector/annotated_image` | YOLO 결과 이미지 (RViz Image로 보기) |
| `/person_detector/approach_intent` | 로봇에게 다가오는 사람이 있는지 |
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

---

## 하드웨어 조립 후 조정할 값

원작자 메모 (2026-09).

- `nav2_params.yaml` 의 collision monitor `source_timeout`: 노트북 과열로 2.0으로 설정. 0.5까지 점차 줄여 볼 것. (과열의 원인이었을 person_detector CPU 문제는 2026-10-02에 해결됨, `docs/TROUBLESHOOTING.md` 참고)
- `person_detector.yaml` 의 `tracking.reassociate_max_age`: 추적한 사람 정보를 유지하는 시간(3초). 사람이 많이 교차하는 실제 환경에서 어떻게 동작하는지 지켜볼 것
- SLAM으로 처음 지도를 만들 때 포인트클라우드에서 잘라 오는 높이: 지금은 LiDAR 기준 +20cm까지 장애물로 봐서, 지나갈 수 있는 높이의 장애물을 못 지나가거나 돌아가는 경우가 있음

---

## 작업 방식

- 작업은 개인 브랜치에서 하고 `dev`에 합친다. 리팩터링 전 원본은 `kkh` 브랜치에 있다
- 커밋 메시지는 바꾼 이유 한 줄. "수정본", "최종" 같은 메시지는 쓰지 않는다
- `dev`에 올릴 때 `docs/CHANGELOG.md` 맨 위에 항목을 추가한다 (할 일 / 변경 / 참고)
- 문제를 해결하면 `docs/TROUBLESHOOTING.md`에 남기고, `KNOWN_ISSUES.md`에 있던 항목이면 거기서 지운다
