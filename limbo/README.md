## Gazebo 실행 후 필요한 명령어 모음!

### **처음 clone 받을 때 주의 사항**
- 같이 다운 받아야할 submodules가 있으니 git clone --recurse-submodules <저장소_URL> 와 같은 형태로 받을것!!!!!

### colcon build 할 때 주의 사항!!!!!
limbo_perception은 yolo를 통해 사람 인식하려고 만든 패키지인데 얘는 새로 받은 yolo용 python 써야해서 이제부터 빌드할 때
python -m colcon build --symlink-install 로 사용해야함. alias 만들어서 사용할 것을 추천...ㅠ

### 몇개 잊었지만 늦게라도 적어보는 받아야할 pkg 목록
1. sudo apt install ros-jazzy-cv-bridge python3-venv : openCV 관련 pkg
1-1. sudo apt install ros-jazzy-pcl-ros ros-jazzy-pointcloud-to-laserscan ros-jazzy-spatio-temporal-voxel-layer
   : robot_self_filter 빌드(pcl_ros), LiDAR→/scan 변환, costmap STVL 플러그인. 없으면 빌드/실행 실패
1-2. 메모리 8GB 이하 PC는 병렬 빌드하면 뻗음. 첫 빌드는 아래처럼:
   MAKEFLAGS="-j2" python -m colcon build --symlink-install --executor sequential
2. python3 -m venv --system-site-packages ~/limbo/venvs/limbo_yolo
source ~/limbo/venvs/limbo_yolo/bin/activate
pip install -r ~/limbo/requirements.txt : YOLO용 Python 환경 설치
3. python -m pip install --force-reinstall \
  "numpy==1.26.4" \
  "opencv-python==4.10.0.84" : python과 yolo 충돌 안나게 버전 고정

## 주행 / 인지 투트랙 개발 가이드 (2026-09-22 구조 변경)

### 왜 바꿨나
인지(사람 인식) 개발이 `limbo_navigation` 안의 `nav2_params.yaml`을 직접 고치는 구조라, 주행 쪽에서 planner/controller를 바꿔가며 성능 비교를 하려면 매번 인지 쪽 수정과 충돌했음.
그래서 **폴더를 담당별로 나누고**, **파라미터를 축별 파일로 쪼개서 launch 인자로 조합**하도록 바꿈. 이제 두 사람이 서로 파일을 안 건드리고 동시에 개발할 수 있음.

### 폴더: 누가 어디를 만지나

| 폴더 | 담당 | 내용 |
|---|---|---|
| `src/navigation/` | **주행** | `limbo_navigation`(Nav2 설정, 맵, launch), `limbo_patrol`(waypoint 순찰) |
| `src/perception/` | **인지** | `limbo_perception`(YOLO), `limbo_interfaces`(메시지), `limbo_human_costmap`(human_layer 플러그인) |
| `src/common/` | 공용 | `limbo_description`(로봇 모델), `limbo_simulation`(Gazebo), `limbo_bringup`(통합 launch). 고칠 일 있으면 서로 말하고 고치기 |
| `src/robot_self_filter/` | 서브모듈 | 건드릴 일 없음 |

- `human_layer` 플러그인은 `limbo_navigation` → `limbo_human_costmap`으로 옮겨짐. 플러그인 이름(`limbo_navigation::HumanLayer`)은 그대로라 yaml 안 바꿔도 됨.
- 주행만 빌드하려면 venv 없이: `colcon build --packages-up-to limbo_navigation limbo_patrol limbo_bringup`

### 실행: 누가 뭘 켜나

**둘 다 똑같이** `ros2 launch limbo_bringup start_simulation.launch.py` — 기본값이 인지 on (person_detector + human_layer + 사람 회피 MPPI 값), 월드/맵은 `human_test`.
주행/인지 모두 같은 월드·같은 사람(actor 경로는 스크립트라 매번 동일)에서 테스트하는 게 원칙. 알고리즘 성능도 사람 있는 환경에서 재는 것.

`use_perception:=false` 는 대조군·디버깅용 — 사람 예측 없이 LiDAR 반응 회피만으로 돌려보고 싶을 때, 또는 YOLO venv 없는 PC에서 주행만 확인할 때.

launch 인자 (전부 생략 가능, 기본값은 괄호):
```
planner:=navfn            config/planner/<이름>.yaml
controller:=mppi          config/controller/<이름>.yaml
localization:=amcl        config/localization/<이름>.yaml
use_perception:=true      false 면 인지 파트 끔 (대조군용)
map:=human_test_map       limbo_navigation/maps/<이름>.yaml
world:=human_test_world   limbo_simulation/worlds/<이름>.sdf
```
예) 주행 벤치마크: `... controller:=rpp planner:=smac_hybrid map:=bookstore_map world:=bookstore_world`

### 파라미터 파일 구조 (`limbo_navigation/config/`)

```
common/        bt_navigator, behaviors, velocity_smoother, collision_monitor, docking, self_filter   ← 주행
costmap/       base.yaml ← 주행   |   with_human.yaml ← 인지
planner/       navfn.yaml ...                                                                       ← 주행
controller/    mppi.yaml ...                                                                        ← 주행
  overlays/    mppi_human.yaml ← 인지  (규칙: <컨트롤러이름>_human.yaml)
localization/  amcl.yaml, slam.yaml                                                                 ← 주행
robot/         sim.yaml, real.yaml  (시뮬/실물 차이만)                                               ← 주행
```

launch 가 `common/* → costmap/base → planner → controller → [인지 on 이면: costmap/with_human → controller/overlays/*_human] → robot` 순서로 겹쳐서 하나로 만든 뒤 Nav2 에 넘김.
뒤에 오는 파일이 앞 값을 덮어씀. **단, 리스트(`plugins: [...]`)는 병합이 아니라 통째로 교체**됨 → 오버레이에서 목록을 바꿀 땐 전체를 다시 적을 것.

실제로 Nav2 가 받은 최종 파일은 launch 로그의 `[limbo_navigation] 병합 파일: /tmp/...` 에 찍힘. "값이 왜 이렇지?" 싶으면 그 파일을 열어보면 됨.
조합 비교: `ros2 run limbo_navigation nav2_params_tool.py diff --controller mppi --vs-use-perception`

### 인지 개발하다 주행 값을 바꿔야 할 때

인지 결과가 주행에 반영돼야 하니 주행을 건드리는 건 당연함. 문제는 "어디를 어떻게" 임. 바꾸려는 게 뭔지 한 번만 자문:

1. **로봇한테 새 정보를 주는 건가?** (사람 위치, 예측 경로) → costmap 레이어, speed_limit 토픽 같은 정해진 입구로. 인지 담당이 발행하는 쪽을 만들고 컨트롤러 내부는 안 건드림.
2. **인지 기능 때문에만 필요한 값인가?** ("예측 경로를 멀리 보려면 컨트롤러가 더 앞을 봐야 해") → `costmap/with_human.yaml`, `controller/overlays/<컨트롤러>_human.yaml` 에만 적음. **인지 담당 자유 실험 영역, 허락 필요 없음.** 단 base 파일은 안 건드림.
3. **로봇 전체에 적용될 정책인가?** (후진 금지, 가감속 한계, inflation 반경) → 주행 담당에게 말해서 base 에 반영. 직접 안 고치는 이유는 그게 모든 비교 실험의 기준을 바꾸는 행위라서.

한 줄로: **새 정보는 입구로, 인지 전용 값은 오버레이로, 로봇 전체 정책은 요청으로.**

### 자주 나올 질문
- **주행이 base(`mppi.yaml`)를 바꾸면 인지 쪽은?** → 오버레이는 5개 값만 덮으니 나머지는 자동으로 따라감. 크게 바꿀 땐 한마디 해주기.
- **주행이 컨트롤러를 RPP 로 바꿔서 테스트하면 인지 쪽은?** → 영향 없음. 인지는 계속 `mppi` + 오버레이로 개발. 최종 컨트롤러가 정해지면 그때 주행 담당이 `overlays/<승자>_human.yaml` 을 한 번 만들어줌.
- **인지 켜고 끈 게 정말 같은 조건인가?** → 켰을 때 = 구조 변경 전 `nav2_params.yaml` 과 499개 파라미터 전부 동일 (param dump 로 검증함). 껐을 때는 인지 전용 12개 값만 다름.
- **옛날 `nav2_params.yaml` 은?** → git 이력 `8a3733f` 에 있음. `nav2_params_before_stvl.yaml` 은 `docs/old_params/` 로.

#### 통합 실행 명령어

ros2 launch limbo_bringup start_simulation.launch.py


#### PointCloud : 3D LiDAR 센서 2D로 변환

ros2 run pointcloud_to_laserscan pointcloud_to_laserscan_node \
  --ros-args \
  -r cloud_in:=/mid360/points_filtered \
  -r scan:=/scan \
  -p use_sim_time:=true \
  -p target_frame:=mid360_link \
  -p min_height:=-0.03 \
  -p max_height:=0.20 \
  -p angle_min:=-3.14159265 \
  -p angle_max:=3.14159265 \
  -p angle_increment:=0.0174533 \
  -p scan_time:=0.1 \
  -p range_min:=0.10 \
  -p range_max:=20.0


#### slam_toolbox 실행 : 주행할 지도를 만들 때만 사용

ros2 launch slam_toolbox online_async_launch.py \
  use_sim_time:=true \
  slam_params_file:=$HOME/limbo/install/limbo_navigation/share/limbo_navigation/config/localization/slam.yaml


#### AMCL과 map_server 실행 : slam을 통해 만든 map 불러오기 + 로봇 위치 파악

ros2 launch limbo_navigation localization.launch.py

#### map을 교체하고 싶다??
navigation/launch에 있는 localization.launch.py 파일에서 default_map_file 변경하기

#### Nav2 실행

ros2 launch limbo_navigation navigation.launch.py planner:=navfn controller:=mppi   (use_perception 기본 true)

(nav2_params.yaml 은 없어짐. config/ 아래 축별 yaml 을 launch 가 조합해서 Nav2 에 넘김. 아래 "Nav2 파라미터 구조" 참고)

#### self-filter 실행 : 로봇 몸체를 LiDAR가 인식하지 않도록 필터링

ros2 launch robot_self_filter self_filter.launch.py \
  robot_description:="$(xacro $HOME/limbo/src/common/limbo_description/urdf/limbo.urdf.xacro)" \
  filter_config:=$HOME/limbo/src/navigation/limbo_navigation/config/self_filter.yaml \
  in_pointcloud_topic:=/mid360/points \
  out_pointcloud_topic:=/mid360/points_filtered \
  lidar_sensor_type:=0 \
  zero_for_removed_points:=false \
  use_sim_time:=true


#### Collision Monitor on/off

ros2 service call /collision_monitor/toggle \
  nav2_msgs/srv/Toggle \
  "{enable: true}"   <-false로 고치면 끄기

#### 하드웨어 조립 후 조정해야할 파타미터 정리

- config/common/collision_monitor.yaml -> source_timeout : 센서의 반영 속도 / 노트북 메모리 과열로 현재 2.0으로 설정. 이후 0.5까지 점차적으로 감소시켜 보기

- person_detector.py -> self.reassociate_max_age : tracking된 사람 정보 유지 시간. 3초로 설정했지만 실제 사람들이 많이 교차되는 환경에서 오랜 시간 유지되는 tracking 데이터가 어떤식으로 작동할지 몰라 주시 필요함

- SLAM을 통해 초기 map을 생성할 때 pointclaud에서 잘라오는 3D 데이터의 높이 설정을 수정할 필요 있음. 현재 LiDAR 기준 +20cm 까지 감지하기 때문에 충분히 지나갈 수 있는 높이의 장애물을 못 지나가거나 돌아가는 선택지가 발생

#### YOLO를 통한 사람 구별

ros2 run limbo_perception person_detector \
  --ros-args \
  -p use_sim_time:=true

#### waypoint 설정을 통한 주행 경로 설정: limbo_patrol

#### rviz에 찍힌 좌표 값을 가져오는 명령어
ros2 topic echo /clicked_point

#### 지정된 wayPoint로 이동하는 명령어
ros2 run limbo_patrol patrol_node