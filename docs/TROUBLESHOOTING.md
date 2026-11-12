# 문제 해결 기록

겪었던 문제와 원인, 해결 방법을 남긴다. 같은 증상이 다시 나오면 여기부터 찾는다.
아직 해결하지 못한 문제는 `KNOWN_ISSUES.md`에 있고, 해결되면 이 문서로 옮긴다.

형식: **증상 → 원인 → 해결 → 확인** (커밋이 있으면 함께 적음)

목차
- [주행·위치 추정](#주행위치-추정)
- [시뮬레이션](#시뮬레이션)
- [인지(person_detector)](#인지person_detector)
- [실물(Jetson·RoboClaw·센서)](#실물jetsonroboclaw센서)
- [관제 서버(dashboard)](#관제-서버dashboard)
- [빌드·git](#빌드git)
- [개발 환경(노트북)](#개발-환경노트북)
- [리팩터링 이전 (README에 있던 내용)](#리팩터링-이전-readme에-있던-내용)

---

## 주행·위치 추정

### Goal을 찍어도 로봇이 안 움직임 (Nav2 시간 초과) — 2026-10-02
- **증상**: 시뮬레이션을 띄우고 Goal을 찍어도 반응이 없음. `planner_server`, `bt_navigator`가 `inactive`
  ```
  [planner_server] Failed to activate global_costmap because transform from base_link to map did not become available before timeout
  [lifecycle_manager_navigation] Failed to bring up all requested nodes. Aborting bringup.
  ```
- **원인**: `amcl.yaml`이 `set_initial_pose: false`라 2D Pose Estimate를 찍기 전까지 `map → odom` TF가 없음. 약 90초 안에 안 찍으면 planner가 활성화에 실패하고 lifecycle manager가 나머지 노드까지 멈춤. Gazebo가 일시정지로 시작해 시간이 안 흐른 것도 겹쳤음
- **해결**: `amcl.yaml`에 초기 위치를 스폰 위치 (0, 0, 0°)로 넣었음 (`fb8b69d`). Gazebo 일시정지 문제는 [아래](#gazebo가-일시정지로-시작함--2026-10-02) 참고
- **이미 멈췄을 때 임시 복구**:
  ```bash
  ros2 service call /lifecycle_manager_navigation/manage_nodes nav2_msgs/srv/ManageLifecycleNodes "{command: 3}"
  ros2 service call /lifecycle_manager_navigation/manage_nodes nav2_msgs/srv/ManageLifecycleNodes "{command: 0}"
  ```
- **확인**: Pose Estimate 없이 Nav2 전부 `active`, Goal 주행 성공

### RViz에서 로봇이 흰 덩어리로 보이고 `No transform from [...] to [map]` — 2026-10-02
- **증상**: RobotModel이 Error, 링크마다 `No transform from [base_link] ...`
- **원인**: 위와 같음. AMCL이 초기화되지 않아 `map` 프레임이 없음
- **해결**: 초기 위치 설정으로 같이 해결됨 (`fb8b69d`)

### 2D Pose Estimate를 찍어도 위치가 크게 틀림 — 2026-10-02
- **증상**: Pose Estimate 후 주행은 되지만 위치가 어긋남
- **원인**: `human_test_world`는 정사각형 방이라 화면에서 방향을 손으로 맞추기 어렵고, 스캔만으로도 0°/90°/180°/−90°를 구분할 수 없음. 실제로 두 번 찍은 위치 모두 스캔-지도 일치가 9%, 4%였음 (정답 위치는 95%)
- **해결**: 초기 위치를 yaml로 고정했음 (`fb8b69d`). 확인 방법: 스캔 점이 지도 벽과 10cm 이내로 겹치는 비율을 후보 위치마다 계산하고, 로봇을 움직인 뒤 Gazebo 정답 위치(`gz topic -e -t /world/<월드>/pose/info`)와 비교

### 회전할수록 방향이 틀어짐 (바퀴 odom 회전 오차) — 2026-10-02
- **증상**: 제자리 360° 회전에 바퀴 odom은 31° 더 돈 것으로 계산 (약 10%). 73° 회전에 5.5° 오차
- **원인**: 바퀴가 회전할 때 미끄러짐. 바퀴 마찰 계수(`mu1`, `mu2` = 0.5)가 낮은 것도 원인으로 추정
- **해결**: MID-360 내장 IMU를 시뮬레이션에 추가하고 (`c0c5c69`), `robot_localization` EKF로 전진 속도는 바퀴, 회전 속도는 IMU에서 받아 `odom → base_footprint`를 냄 (`c02aff9`)
- **주의**: Gazebo diff-drive odom은 covariance가 전부 0이라, 같은 값(회전 속도)을 바퀴와 IMU 둘 다에서 받으면 EKF가 바퀴만 믿어 버림. 그래서 입력을 나눴음
- **확인**: 360° 회전 오차 31° → 0.4°, 73° 회전 오차 5.6° → 0.3°

### 주행 중 AMCL이 위치를 놓쳐 Goal 전에 멈춤 — 2026-10-02
- **증상**: `aischool_2f`에서 Goal 도중 멈춤
  ```
  [controller_server] Optimizer fail to compute path / Controller patience exceeded
  [behavior_server] Collision Ahead - Exiting Spin / backup failed
  [planner_server] GridBased plugin failed to plan from (-2.41, 4.78) ...
  ```
  AMCL 위치가 실제와 3.6m, 60° 어긋나 계단 코어(막힌 구역) 안에 있다고 판단하고 있었음
- **원인**: 로봇이 실제로는 30초간 멈춰 있는데 바퀴는 계속 돌아 odom이 0.40m/s로 전진했다고 보고함 (바퀴 헛돎). AMCL이 odom을 따라가다 위치를 놓침. 벽에 밀어붙이는 재현 시험에서도 6.5초 헛돌자 AMCL이 3m 어긋나 "로봇이 방 밖"으로 판단했음. IMU로는 잡을 수 없음 (등속 전진과 정지 모두 가속도 0)
- **임시 복구**: 실제 위치로 AMCL을 다시 맞춤 (RViz 2D Pose Estimate 또는 `/initialpose` 발행)
- **해결**: 0.5초마다 바퀴 이동량과 LiDAR 스캔(점-직선 ICP) 이동량을 비교해, 바퀴는 15cm 이상 갔는데 스캔상 이동이 그 30% 미만인 구간이 2번 연속이면 `/wheel_slip`을 내고 Nav2 Goal을 취소하는 `limbo_monitor/wheel_slip_monitor` 추가 (`2bb9298`). 긴 복도처럼 앞뒤 방향 단서가 부족한 스캔에서는 판단을 보류함
- **확인**: 벽 밀기 시험에서 접촉 후 1.0초 만에 감지, 감지 후 0.017초 만에 Goal 취소. `aischool_2f` 복도 4분 주행(22m 왕복 포함) 오경보 0건

### 좁은 복도에서 사람과 마주친 뒤 AMCL 위치가 크게 튐 — 2026-10-06
- **증상**: `aischool_2f` 왼쪽 복도(폭 1.54m)를 지난 뒤 복도 끝에서 AMCL 위치가 갑자기 2.6~4.4m, 방향 51~68° 어긋남. 그 뒤 Nav2가 "앞에 장애물"로 복구에 실패하고 멈춤. 매번 재현되지는 않아 원인을 찾기 어려웠음
- **원인**: 걷는 사람이 좁은 복도에서 로봇과 정면으로 마주치면, 사람에 맞은 빔이 지도와 어긋나고 앞뒤 방향의 유일한 단서인 복도 끝 벽이 가려짐 → AMCL 파티클이 복도 방향으로 퍼짐(σ 0.2 → 1.2~1.9). 사람이 지나간 뒤에도 긴 복도에서는 다시 모이지 못하다가, 복도 끝 교차로에서 엉뚱한 무리가 이기며 위치가 튐
- **찾은 방법**: 사람 없이 같은 직진을 하면 재현 안 됨(σ 0.3 이하) → 사람 경로 시각에 맞춰 일부러 정면으로 마주치게 하자 2/2 재현. odom·EKF(직진 중 실제 0.0°, EKF −0.7°), 지도·월드(코어 벽 위치 동일), AMCL 측정 모델, 스캔 시각 지연, CPU 부하, 파티클 리샘플링 간격, 빔 수는 차례로 배제함
- **해결**: `amcl.yaml`에 `laser_model_type: likelihood_field_prob`, `do_beamskip: true`. 대부분의 파티클에서 지도와 안 맞는 빔(사람 등)을 위치 계산에서만 뺌. 장애물 회피는 모든 빔을 그대로 씀
- **확인**: 같은 마주침 시험에서 최대 방향 오차 51.8°/68.1° → 1.5°/1.5°, σ 1.2~1.9 → 0.06~0.07
- **비교한 다른 방법**: `alpha1~4`를 0.05로 낮춰 odom을 더 믿게 해도 해결됐지만(방향 오차 1.3~1.5°), 실제 로봇은 odom이 시뮬레이션보다 부정확해 다른 상황에서 오히려 틀어질 수 있어 채택하지 않음
- **참고**: Gazebo의 걷는 사람 모델은 충돌이 없어 로봇을 그대로 통과함 (로봇이 밀리지 않음)

---

### 순찰 정지 waypoint 0.3m 앞에서 멈춘 뒤 주행 실패 — 2026-10-12
- **증상**: `human_test_world` 순찰에서 정지 waypoint C·G 0.31~0.43 m 앞(도착 판정 0.25 m 밖)에서 로봇이 멈추고, `Failed to make progress`가 반복된 뒤 목표 실패
- **원인**: 목표가 로봇의 옆·뒤에 남았는데 waypoint 방향(yaw 0°)은 로봇이 이미 향한 방향과 같았다. MPPI는 후진이 꺼져 있고(`vx_min: 0`) 목표 0.5 m 안에서 방향 오차에 벌점을 준다(`GoalAngleCritic`). 돌아서 다가가면 벌점, 가만히 있으면 벌점 0이라 그 자리에 멈춘다
  - 사람이 없는 빈 복도에서도 재현됨 (yaw 0° 5/5 실패). 사람은 로봇이 목표를 살짝 지나치게 만드는 계기일 뿐
- **해결**: 정지 waypoint의 yaw를 들어가는 방향에 맞춤 (`test_waypoints.yaml` C −124°, G −89°, J −179°). waypoint yaml의 yaw는 **도 단위**
- **확인**: 같은 자리에서 yaw만 바꾸면 3/3 성공. 원래 월드 순찰 10/10 완주, 목표 근처 정지 0회
- **다른 waypoint 파일을 만들 때**: 정지 지점의 yaw를 직전 지점에서 들어오는 방향으로 둔다. 도착 판정 범위를 넓히는 방법은 못 간 상태를 도착으로 착각하게 해서 쓰지 않는다
- **자세한 기록**: [원인 조사(통제 실험)](NAV2_NEAR_GOAL_FAILURE_2026-10-12.md), [수정 후 10회 검증](NAV2_YAW_10_RUN_VALIDATION_2026-10-12.md) (원작자 작성)

### 순찰이 막다른 통로 끝 0.8 m 앞에서 "Failed to make progress"를 반복함 — 2026-10-13
- **증상**: 가구 월드 순찰에서 왼쪽 책상 통로 끝(G) 직전에 멈춰 회전·후진 복구를 반복. 같은 좌표를 단독 목표로 주면 성공
- **원인**: 통로 끝 waypoint가 `pass`라 올라가는 경로와 내려오는 경로가 NavigateThroughPoses 경로 하나에 겹침. MPPI가 겹친 두 경로 사이에서 갈피를 못 잡음 (닫힌 고리 경로를 한 번에 줄 때와 같은 원인)
- **해결**: 되돌아오는 지점을 `stop`(wait_sec 0)으로 두어 구간을 나눔 (`aischool_furnished_waypoints.yaml`, 2026-10-13)
- **확인**: `tools/demo_patrol.sh aischool_2f_furnished aischool_2f_furnished_map aischool_furnished_waypoints.yaml` → 진전 없음 0번, 복구 0번으로 완주

### 장애물 없는 직선에서도 0.42 m/s밖에 안 남 (상한은 0.6) — 2026-10-13
- **증상**: 충장로 200 m 직선 왕복에서 평균 0.42 m/s. 속도 평활기·collision monitor·Gazebo 구동 상한은 모두 0.6 이상인데 MPPI가 그 이상을 안 냄
- **원인**: MPPI `prune_distance` 1.7 m. MPPI는 예측 시간(4초) 동안 갈 수 있는 경로만 보고 궤적을 고르는데, 1.7 m는 4초 × 0.425 m/s라 그보다 빠른 궤적은 경로 끝을 넘어가 점수가 낮아짐. 즉 `prune_distance`가 사실상 속도 상한이 됨
- **해결(후보)**: `prune_distance` 2.5(= 상한 0.6 × 4초 이상)면 평균 0.58 m/s, 왕복 500 → 351 s. 계산량은 거의 안 늚(batch 2000 × 80이 지배). 두 컴퓨터에서 1~6초 차이로 재현. **아직 어느 브랜치 설정에도 반영 안 함**(사람 있는 조건 재비교 뒤 결정, `PROJECT.md` 다음 5번)
- **확인**: . 상한 0.75 + 3.0이면 0.72 m/s까지 나오지만 실물은 평지에서만 0.8 m/s라 0.6~0.7이 안전

### launch 뒤에 순찰 노드를 이어서 치면 위치 추정 시간 초과로 끝남 — 2026-10-13
- **증상**: `ros2 launch ... && ros2 run limbo_patrol patrol_node`처럼 이어 치면 순찰 노드가 "위치 추정 없음"으로 바로 끝남
- **원인**: 순찰 노드는 `map → base_footprint` TF를 30초만 기다리는데, 시뮬레이션은 뜨는 데 1~2분 걸림(Gazebo + Nav2 lifecycle + AMCL)
- **해결**: `tools/demo_patrol.sh`가 `bt_navigator`가 active가 되고 TF가 나올 때까지 기다렸다가 순찰 노드를 띄움. 30초를 늘리는 대신 이렇게 한 이유: 실제 로봇에서는 30초면 충분하고, 기다림은 시뮬레이션 쪽 사정이라 스크립트가 맡는 게 맞음
- **확인**: `aischool_2f`·`aischool_2f_furnished`·`human_test_world` 순찰 완주. 참고: 이 스크립트를 백그라운드로 띄우면 launch가 SIGINT를 무시해 Ctrl+C 방식이 안 먹음 → `kill -TERM $(cat /tmp/demo_sim.pid)`

## 시뮬레이션

### Gazebo가 일시정지로 시작함 — 2026-10-02
- **증상**: 시뮬레이션을 띄웠는데 카메라 토픽(`/rgbd_camera/image`)에 데이터가 안 나옴. `/clock`은 나오지만 시간이 안 흐름 (`gz topic -e -t /stats`에 `paused: true`)
- **원인**: `gazebo.launch.py`의 `gz_args`에 `-r`(바로 재생)이 없었음
- **해결**: `gz_args`에 `-r` 추가 (`ee8fa17`)
- **이미 떠 있을 때 임시 복구**: Gazebo 창 왼쪽 아래 ▶ 버튼, 또는
  ```bash
  gz service -s /world/<월드>/control --reqtype gz.msgs.WorldControl --reptype gz.msgs.Boolean --timeout 3000 --req 'pause: false'
  ```

### Gazebo·RViz가 느리고 NVIDIA GPU를 안 씀 — 2026-10-02
- **증상**: `nvidia-smi`에 YOLO(python)만 보이고 `gz sim`, `rviz2`가 없음
- **원인**: GPU 모드가 `on-demand`라 화면 렌더링(OpenGL)은 기본적으로 Intel 내장 그래픽이 함. CUDA(YOLO)만 자동으로 NVIDIA를 씀
- **해결**: 시뮬레이션을 띄우는 터미널에서
  ```bash
  export __NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia
  ```
  (시스템 전체를 NVIDIA로 바꾸려면 `sudo prime-select nvidia` 후 재부팅. 배터리·발열 증가)

### 다른 건물 지도·월드로 바꾸기 어려움 — 2026-10-02
- **증상**: 월드와 지도가 launch 파일에 고정돼 있어 바꾸려면 코드를 고쳐야 했음
- **해결**: launch에 `world`, `map` 인자 추가 (`c4fb638`). 예: `world:=aischool_2f map:=aischool_2f_map`

---

### 시뮬레이션이 실시간의 0.6배로 돌아 로봇이 느려 보임 — 2026-10-13
- **증상**: 시연 화면에서 로봇이 너무 느려 보임. MPPI 실속 0.4 m/s가 화면에서는 0.24 m/s. Gazebo 실시간 비율(RTF) 0.60
- **원인**: gz 서버의 물리 스레드(1 ms 스텝 = 시뮬 1초에 1,000번 계산)가 한 코어를 포화함(서버 CPU 150%, 그중 메인 스레드 88%). 코어가 16개라도 물리는 한 스레드라 더 못 씀. gz gui가 210%를 더 씀
- **해결**: 월드 7개의 `max_step_size` 0.001 → 0.002 (`815bab9`). 계산이 반으로 줄어 RTF 0.60 → 0.95(화면 켬), 0.96(화면 끔). `build_limbo` 필요(월드 sdf는 install에 복사됨)
- **확인**: 정확도는 같음 — 직진 6 m에서 8 mm 차이, 제자리 5바퀴 회전 오차는 1 ms·2 ms 모두 +150°, 최고 속도 0.44 m/s 동일. . 따로 알게 된 것: 바퀴 odom이 제자리 회전 때 9% 더 돈 것으로 세는 건 스텝과 무관(실린더 바퀴 옆미끄러짐으로 추정, EKF·AMCL이 보정)

### 시뮬레이션이 3번 모두 시작 실패: 모든 노드가 `Failed init_port fastrtps_port...: open_and_lock_file failed` — 2026-10-14
- **증상**: `sim_ctl.sh start`가 3번 다 실패. 로그에 parameter_bridge·person_detector·nav_recorder 등 모든 노드가 `[RTPS_TRANSPORT_SHM Error] Failed init_port fastrtps_port7003: open_and_lock_file failed`
- **원인**: Fast DDS 공유 메모리 전송의 포트 파일(`/dev/shm/fastrtps_port*`)을 **SIGKILL로 죽은 노드가 잠근 채 남김**. 같은 날 잔존 프로세스(런치를 내려도 남은 `parameter_bridge`·파이썬 노드)를 SIGKILL로 정리한 뒤 생김. 잔존 자체는 gz transport 파이썬 노드가 SIGINT·SIGTERM을 삼켜서 생겼음
- **해결**: ROS·gz 프로세스가 하나도 없을 때 `ros2 daemon stop` 후 `rm -f /dev/shm/fastrtps_*`. 잔존 프로세스는 `ps -eo pid,lstart,args`로 런치 시각별로 보고 **PID로** 끈다(패턴으로 모아 죽이면 자기 셸까지 죽음)
- **확인**: 정리 뒤 같은 시뮬레이션이 1번에 시작해 완주. 

### 카메라 0°에서 30 cm 상자에 붙어 정체 → ToF 점군을 local costmap에 — 2026-10-14
- **증상**: 카메라 0.7 m·0° 채택 뒤 상자 벤치 12구간 중 1회, 홀로 돌아오는 구간에서 30 cm 상자에 붙은 채 `Failed to make progress` 6번·복구 7, 90 s 중단. 다른 구간도 0.11 m까지 접근
- **원인**: 0° 카메라(세로 시야 ±27°)는 30 cm 상자 윗면이 0.78 m 안에서 시야를 벗어난다(15°는 0.44 m). local STVL이 지우면 MPPI가 그 자리로 간다. 라이다는 높이 띠라 30 cm를 못 본다
- **해결**: `/tof/points`(범퍼 높이 0.10 m, 8×8 63°)를 local costmap STVL `tof_mark` 관측원으로(마킹만, obstacle_range 2.0, min_obstacle_height 0.03으로 바닥 거름)
- **확인**: 상자 3회 12/12, 접촉 0, 진전 없음 경고 0 (전 11/12). 단 옆으로 스치는 코너는 ToF 시야 밖이라 13회 중 1회 정체가 남음(KNOWN_ISSUES)

### 순찰 통과 지점 A 앞 1.2 m에서 "진전 없음"만 반복 (prune_distance 2.5 뒤) — 2026-10-14
- **증상**: 사람 10명 네모 화면 순찰 첫 묶음(A→C)이 (4.1, 5.3)에서 멈춰 `Failed to make progress` 39번, 3번 다 ABORTED. 사람을 뺀 회차도 같은 자리 → 사람·ToF 탓 아님. 위치 오차 0.033 m로 정상. 학원 2층 순찰의 "A 지점 맴돎"도 같은 증상
- **원인**: A 다음 지점이 정반대라 경로가 A에서 180° 되돌아온다. `prune_distance` 2.5로 MPPI가 잘라 쓰는 경로에 A까지 1.2 m + 되돌아오는 구간이 같이 들어와 경로 추종 critic의 기준점이 로봇 뒤를 가리켜 속도 명령 ~0(Optimizer fail은 0). 1.7일 때는 되돌이 구간이 덜 들어와 지나갔음
- **해결**: MPPI `enforce_path_inversion: true`(되돌이 점까지만 경로 사용, `inversion_xy_tolerance` 0.2·yaw 0.4)
- **확인**: 네모 순찰 AMCL·slam_toolbox 모두 3묶음 완주(145.7·137.4 s), 진전 없음 0

### 순찰 노드가 AMCL 없는 구성에서 "localization not ready (30 s)"로 실패 — 2026-10-14
- **증상**: slam_toolbox 위치 추정·지도 작성 구성(`localization:=slam|mapping`)에서 `patrol_node`가 30 s 뒤 실패
- **원인**: `wait_for_localization`이 `/amcl_pose` 수신(`initial_pose_received`)을 요구. slam_toolbox는 그 토픽이 없다
- **해결**: `map → base_footprint` TF만 본다. AMCL도 위치를 잡아야 TF를 내므로 판정은 같다
- **확인**: slam_toolbox 순찰 출발·완주

### 진단용 `ros2 bag record`가 20시간 살아남아 시작 부하를 키움 — 2026-10-15
- **증상**: 손님 장면 시뮬레이션에서 `bt_navigator`가 계획 서버 응답을 20 ms(`default_server_timeout`) 안에 못 받아 목표 4개를 0~2 s에 전부 포기(`Timed out while waiting for action server to acknowledge goal request for compute_path_to_pose`). RViz "Publisher already registered" 경고
- **원인**: 전날 진단용으로 띄운 `ros2 bag record`(local costmap·TF 등 구독)가 `kill -INT` 뒤에도 안 죽고 74,990 s 동안 남아 DDS 참여자·구독을 유지 → 기동 부하 증가. 시작 부하에서 20 ms 응답 제한은 원래 아슬아슬했음
- **해결**: 남은 녹화 프로세스를 찾아(`ps -eo pid,etime,args | grep "[b]ag record"`) PID로 종료. `nav2_params.yaml`의 `default_server_timeout` 20 → 100 ms(주행 동작 변화 없음, 서버 응답 대기만 여유)
- **확인**: 정리·100 ms 뒤 손님 장면 4/4 성공(17~28 s), 사람 충돌 0, 사람 최소 0.56 m. 같은 날 복도·상자·순찰 회귀도 시작 실패 0

### 몸체를 낮추자 로봇이 출발 자리에서 못 움직임 (Gazebo 라이다가 자기 몸체 메시를 봄) — 2026-10-15
- **증상**: `body_top` 0.835 → 0.709(라이다 0.80 m)로 줄인 뒤 복도 장면 첫 목표가 90 s 시간 초과, `Failed to make progress` 10번, 회전 복구도 실패. 로봇 둘레 costmap에 치명 칸, `/scan` 360점 중 292점이 1 m 안(최소 0.20 m)
- **원인**: 몸체 **시각 메시**(`meshes/v14/body.stl`, z 0.059~0.835 m 고정)는 그대로이고 충돌 상자만 낮아짐. Gazebo gpu_lidar는 시각 메시에 부딪히므로 0.80 m 라이다가 자기 몸체 윗부분(0.709~0.835)을 전 방향 0.2~0.3 m에서 봄(근접 점 9,444개, 방위 고르게 분포). self_filter는 충돌 상자 기준이라 못 거름
- **해결**: 메시 z 배율을 `body_top / 0.835`로(`limbo.urdf.xacro`). 실물에는 없는 시뮬레이션 모델 정합 문제. 최종 치수(`body_top` 0.609, 라이다 0.70 m)도 같은 식으로 따라감
- **확인**: 같은 진단에서 `/scan` 최소 1.80 m, 1 m 안 점 0개, 근접 점 0, 로봇 둘레 costmap 0. 복도 3/3·상자 4/4 성공. 0.70 m에서도 출발 자리 scan 1.0 m 안 점 0개(변경 기록 (33))

### 사람 앞 정지가 60 s까지 안 풀림 — 래치 구현에서 얻은 교훈 — 2026-10-14~19
- **증상**: "사람이면 멈춰 기다리기"를 켠 뒤 사람 앞 정지가 상한 60 s를 꽉 채우고서야 풀리는 일이 간헐적으로 남(복도 시험 0/3 → 2/2 → 1/3). 고칠 때마다 다른 자리에서 같은 모양으로 재발
- **원인(네 가지, 모양은 하나)**: 정지를 만들거나 유지하는 근거가 **사람인지 구분 못 하는 신호**였음. ① 정지 뒤 "손님이 아직 앞에 있나"를 라이다 앞 띠에 점 2개로 판정 → 복도 벽 모서리 점이 걸림 ② ToF 한 점 막힘 + "직전 5 s에 다가오던 사람"으로 코앞 막힘 판정 → 실제로는 벽을 봄 ③ "다가옴"을 로봇 기준 거리 감소로 판정 → 로봇이 서 있는 사람에게 다가가도 참 ④ 시작 직후 TF 준비 전 자기 몸 점. 그리고 정상 출구가 없어 **타이머 상한이 출구**였음. 조건을 하나씩 덧붙여 막았지만(지도 벽 걸러내기, 몸통 폭 덩어리, 5 s·15 s 소상한) 다음 자리에서 또 남
- **해결**: 설계를 바꿈(PROJECT 2-7). 사람 근거는 사람 트랙(카메라, 라이다 다리 검출)에서만, ToF·라이다 점은 안전 정지와 거리 보정만. 출구는 서비스 논리(사람이 구역을 벗어남 / 15 s 뒤 비켜서기)로, 타이머 상한은 출구가 아니라 경보. 래치 둘·토픽 둘·BT 조건 둘 → 상태 기계 하나·`/person_wait`·`IsWaitingForPerson`(변경 기록 39). 하반신 모델로 1.5 m 안 검출이 0~49 % → 71~95 %가 되어 "카메라가 코앞을 못 보니 ToF로 잡는다"는 전제 자체가 사라짐
- **확인**: 상태 기계 연기 시험에서 대기 진입·경보·출발이 전이 로그 한 줄씩으로 설명됨. 3단계 시뮬 결과는 변경 기록 39
- **교훈**: 같은 모양의 오류가 자리만 바꿔 재발하면 코드가 아니라 설계를 본다. "증거(센서)"와 "판단(정책)"을 분리하고, 판단의 출구를 타이머가 아닌 서비스 논리로 정의한다. 숫자 상한은 안전망이지 동작이 아니다. 래치 실험은 헛수고가 아니라 이 원칙을 만든 근거이고, 벽 걸러내기·덩어리 판정·BT 조건 자리는 그대로 다음 구현에 쓰임

## 인지(person_detector)

### person_detector가 CPU를 8코어(775%)나 씀 — 2026-10-02
- **증상**: 사람 1명, 로봇 정지 상태인데 `top`에서 person_detector가 775%. 시스템 커널 CPU(`%sys`)가 42%로 비정상적으로 높음
- **원인**: PyTorch(OpenMP)와 numpy(OpenBLAS)가 각자 코어 수(16)만큼 스레드를 띄워 서로 기다리며 헛돎. 실제 YOLO 연산은 GPU에서 프레임당 약 10ms로 끝남. 둘 중 하나만 제한해도 프레임당 CPU 시간이 99.9ms → 24ms
- **해결**: `limbo_perception/__init__.py`에서 import 전에 `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`를 2로 설정 (`200ca60`)
- **확인**: bag 재생 기준 프레임당 CPU −44%, 처리 속도 8.7 → 13.6Hz. 시뮬레이션 중 775% → 116%, 시스템 idle 17% → 48%
- **참고**: README에 "노트북 과열로 collision_monitor `source_timeout`을 2.0으로 설정"이라는 메모가 있었는데, 이 문제가 과열의 원인이었을 가능성이 큼

### 다리만 보이는 사람의 거리가 1.4m 멀게 나옴 — 2026-10-12
- **증상**: 팀원이 학습한 하반신 모델(`human-leg/runs/person_leg_stage1/weights/best.pt`)로 바꿔 보니, 1.4m 앞에 멈춘 사람(카메라에 다리·허리만 보임)의 위치가 실제보다 약 1.4m 멀게 나옴
- **원인**: 사람 거리는 YOLO 박스 가운데 영역(가장자리 30%씩 뺀 부분)의 depth 값 중 하나로 잰다. 전에는 **중앙값**을 썼는데, 다리만 있는 박스는 가운데의 절반 넘게가 **다리 사이로 보이는 뒤쪽 벽**이라 중앙값이 벽까지 거리가 됨
- **해결**: 중앙값 대신 **가까운 순으로 줄 세웠을 때 25% 위치의 값**을 씀 (`person_detector.yaml`의 `depth.percentile`, 50이면 예전 중앙값)
  - 예: 다리 1.5m ×8개, 벽 4.0m ×12개 → 중앙값 4.0m, 25% 위치 1.5m
  - 사람 몸이 가운데 영역의 25% 이상만 차지하면 사람 거리가 나옴 (중앙값은 50% 이상 필요)
  - 가장 가까운 값(0%)을 안 쓰는 이유: depth 잡음 한두 개에 흔들림
- **문제는 두 단계**: ① 검출: 기본 yolo11n(COCO)은 다리만 보이면 잘 못 잡음 → 하반신 모델 ② 거리: 잡아도 배경을 잼 → 25% 위치
- **확인**: 같은 카메라 입력으로 세 노드를 나란히 녹화 (`aischool_2f_scenarios`, 1.4m 앞에 4초 멈추는 사람, 3회)

  | | 기존 모델 + 중앙값 | 기존 모델 + 25% | 하반신 모델 + 25% |
  |---|---|---|---|
  | 멈춤 중 예측 (4초) | 24~42개 | 25~43개 | 60~61개 |
  | 가장 긴 끊김 | 0.7~1.7초 | 0.5~0.9초 | 0.1초 |
  | 위치 오차 중앙값 | 0.46m | 0.55m | 0.35m |

  - 하반신 모델 + 중앙값은 위치 오차 1.49m (거리 +1.36m)
  - YOLO만 비교: 다리만 보일 때 기존 65% → 하반신 100% 검출, 사람 없는 곳 오검출은 6 → 5개로 늘지 않음
- **기본 모델은 아직 기존 yolo11n**: 하반신 모델 근거가 시뮬레이션 사람과 팀원 학습 검증(mAP50 0.962)뿐이라 실제 사람으로 확인 후 바꾸기로 함
- **평가 도구**: `~/limbo_bags/sim_tools/compare_models.py`(YOLO만), `pred_record.py` + `stop_pos_err.py` + `pred_compare.py`(사람 인식 전체)

### 지도에 없는 낮은 장애물에 부딪힘 — 2026-10-12
- **증상**: `aischool_2f_scenarios` 홀 서쪽의 0.1m 상자에 로봇이 정면으로 부딪힘 (2/2). 바퀴가 헛돌아 헛돎 감시가 Goal을 취소함
- **원인**:
  - 사각지대: MID-360은 아래쪽 −7°라 0.1m 상자를 5.1m 안쪽에서 못 보고, 카메라는 가로 72°라 옆으로 빠지면 못 봄. 상자는 가까이 가면 어느 센서에도 안 보임
  - 장애물 층(STVL)이 로컬 costmap에만 있어서 **전역 경로가 상자를 관통**함. MPPI가 상자 앞에서 10초 넘게 머뭇거리다 상자가 기억(`voxel_decay`)에서 지워지는 순간 부딪힘
  - 로컬 기억 시간만 늘리는 건 효과 없음: 5초 1/2, 10초 2/2 부딪힘 (머뭇거리는 시간이 더 김)
- **해결**: 전역 costmap에도 STVL 층 추가 (기억 15초, 2026-10-14부터 3초, `nav2_params.yaml`). 경로 계획기가 상자를 알고 처음부터 돌아감
- **확인**: 기억 5초·15초 각 3회 (상자 통과 + 위쪽 복도 사람 왕복). 상자 6/6 회피 (최소 0.16~0.23m), 위쪽 복도 24/24 성공
- **대가**: 좁은 복도를 사람이 막으면 경로 계획이 실패하고 재시도함 → `KNOWN_ISSUES.md`. **2026-10-13 추가**: 5초와 15초가 같은 성적이었는데 15초를 택한 근거가 없었고, 이 대가를 할 일에 올리지 않아 v14(더 크고 inflation 0.45)에서 복도 통과 실패로 악화된 뒤에야 다시 찾음. 재검토는 `PROJECT.md` 다음 0번

### 멈춘 사람에게 예측 경로가 계속 뻗고, 다시 잡히면 다른 사람이 됨 — 2026-10-07
- **증상**: `aischool_2f_scenarios`에서 걷다가 4초 멈추는 사람의 추정 속도가 멈춘 뒤 2초가 지나도 약 0.4m/s (정지 판단 기준 0.05m/s 미만은 80개 중 1개). 예측 경로가 사람 앞으로 약 0.8m 더 뻗음. 검출이 잠깐 끊긴 뒤 같은 YOLO 추적 ID인데 새 person ID가 붙음
- **원인**:
  - 칼만 필터(등속 모델)가 갑작스러운 정지를 늦게 따라감. 측정 위치는 프레임마다 0.004~0.02m만 변하는데 속도 방향은 걷던 방향 그대로였음 (잡음이 아니라 느린 반응)
  - 다시 잡을 때 "안 보이는 동안 남은 속도로 계속 걸었다"고만 가정하고 위치를 외삽해서, 그 자리에 멈춘 사람이 재연결 기준(0.5m)을 넘음
- **해결**:
  - 최근 0.6초 동안 측정 위치가 0.15m 미만으로 움직였으면 멈춘 것으로 보고, 속도를 0으로 하고 위치를 최근 측정 평균으로 맞춤 (`tracking.stop_window`, `tracking.stop_max_displacement`)
  - 재연결 거리를 "계속 걸었을 경우"와 "그 자리에 멈췄을 경우" 중 가까운 쪽으로 잼
  - 칼만 필터 설정값은 바꾸지 않음. 시뮬레이션 측정 잡음은 실제 RGB-D보다 훨씬 작아서 여기에 맞춰 튜닝하면 실물에서 예측이 떨릴 수 있음
- **확인**: 같은 카메라 입력으로 수정 전후 노드를 나란히 녹화
  - 멈춘 뒤 1~2초 추정 속도 0.37 → 0.03m/s, 정지 판단 80개 중 1개 → 91개 중 22개
  - 걷는 사람은 수정 전후 출력이 같음
  - 남은 오차는 대부분 1.6m 앞 사람이 카메라에 다리만 보여 검출이 끊기는 것 때문 → `KNOWN_ISSUES.md` 센서 배치
- **분석 방법**: 사람 예측을 map 좌표로 녹화해 월드 SDF 시간표(정답)와 비교하고, "정답 위치·속도를 아는 이상적인 등속 예측"의 오차를 빼서 인식 탓인 오차만 봄

### MPPI 컨트롤러가 목표 주기(20Hz)를 못 내고 주행이 실패함 — 2026-10-07
- **증상**: `Control loop missed its desired rate of 20.0000 Hz. Current loop rate is 6.4935 Hz`. 부하 평균 14~16/16코어일 때 경로 추종이 나빠지고 `Failed to make progress`
- **원인**: 시뮬레이션 전체 CPU 부족. 컨트롤러 자체 문제가 아니라 같은 컴퓨터의 다른 노드들이 CPU를 쓰고 있었음
- **해결**: 아래 CPU 절감의 결과로 해결됨. 컨트롤러 설정은 바꾸지 않았음
  - `wheel_slip_monitor` sim time 해제 (50% → 5%)
  - `person_detector` sim time 해제 (약 −30%p)
  - 더 필요하면 `gui:=false`로 Gazebo 창 끄기 (Gazebo 285% → 110%)
- **확인**: `aischool_2f_scenarios`에서 홀 ↔ 왼쪽 복도 위쪽 끝 왕복 2번(이동 4번)
  - Gazebo 창 켬(기본): 4/4 성공, 주기 경고 1번(12.5Hz), 부하 평균 11.3
  - Gazebo 창 끔: 4/4 성공, 주기 경고 0번, 부하 평균 9.9
- **확인 방법**: `~/.ros/log/controller_server_*.log`에서 `Control loop missed` 줄 수 세기

### Python 노드가 하는 일 없이 CPU를 많이 씀 (`/clock` 처리) — 2026-10-06
- **증상**: `wheel_slip_monitor`가 0.5초마다 한 번 계산하는데 CPU 약 50%. 스레드는 30개지만 메인 스레드 하나만 바쁨
- **원인**: `use_sim_time: True`면 노드가 `/clock`을 구독하는데, Gazebo는 물리 스텝(1ms)마다 시계를 내서 약 740Hz로 들어옴. Python(rclpy)이 이걸 전부 처리하느라 CPU를 씀
- **해결**: 메시지에 찍힌 시각만 쓰면 sim time이 필요 없음. launch에서 `use_sim_time: False`로 실행
  - `wheel_slip_monitor`: 스캔 메시지끼리의 시각만 비교하고 있었음 (`14d11dc`)
  - `person_detector`: 예측 메시지 시각에만 노드 시계를 쓰고 있어서, 그 사진을 찍은 카메라 이미지 시각으로 바꿈 (`5616520`). human_layer가 예측의 나이를 잴 때도 이쪽이 더 정확함
- **확인**: 같은 노드를 나란히 띄워 비교
  - `wheel_slip_monitor`: sim time 켬 50.3%, 끔 5.0%. 판단 결과는 같음
  - `person_detector`: 139% → 109% (끈 쪽이 프레임을 더 많이 처리하면서도 낮음). 녹화 bag 재생 비교에서 출력 870프레임 동일
- **측정할 때 주의**: Gazebo가 일시정지 상태면 센서가 렌더링을 안 해 CPU가 낮게 나옴. 측정 전에 `gz topic -e -t /stats -n 1`에 `paused: true`가 없는지, `/scan`이 나오는지 확인할 것

### 리팩터링 전후로 동작이 같은지 확인하기 — 2026-10-02
- **방법**: 카메라 입력(RGB, depth, camera_info, TF, clock)만 rosbag으로 녹화하고, 전후 노드에 같은 bag을 0.5배속 + `use_sim_time:=true`로 재생해 출력 토픽을 비교. 도구는 `~/limbo_bags/` (`capture.sh`, `compare.py`)
- **주의**: 녹화기를 강제 종료하면 `metadata.yaml`이 안 생김 → `ros2 bag reindex <bag> -s mcap`으로 복구. 재색인한 bag은 파일 순서와 받은 순서가 달라서, 메시지를 받은 시각 기준으로 프레임을 묶어야 함
- **허용 차이**: TF를 이미지 시각으로 조회할 때 이미지가 TF보다 몇 ms 먼저 오면 `extrapolation into the future`로 실패해 상태가 `WARMUP`으로 남는 프레임이 생김. 재생 타이밍에 따른 비결정성이라 리팩터링 실패가 아님

---

### 벽·검은 면을 사람으로 인식해 코스트맵에 사람 장애물이 찍힘 — 2026-10-22
- **증상**: RViz 사람 인식 영상에서 화면 왼쪽 70 %를 덮는 검은 면에 박스가 쳐지고 `ID:P:70 … 1.47m STATIONARY`로 사람 판정. 그 자리에 HumanLayer 사람 장애물이 생겨 로봇이 피하거나 기다림. 기본 모델을 leg_640으로 바꾼 뒤(변경 기록 41) 보고됨
- **원인**: 하반신 모델이 **크고 어두운 균일한 사각형**을 person으로 봄. 그 장면을 모델에 직접 넣으면 leg_640 0.34(문턱 0.3 넘음), leg_512 0.25, 좌우 뒤집으면 둘 다 넘음(0.31/0.37), 밝기를 올리면 떨어짐(0.07/0.17) → 두 모델 공통 약점이고 leg_640이 조금 더 민감. 박스가 뜨면 깊이는 그 면까지 거리(1.47 m)로 잡혀 벽 자리에 사람이 생김. 검은 면은 그늘이 아니라 순수 검정(0,0,0)이라 재질 없는 물체·가구로 추정(자리는 미확인)
- **해결**(변경 기록 44): 모델·문턱은 그대로 두고 인식 노드에 기하학적 판정 둘 추가
  1. `geometry.surface_check`: 화면 15 % 이상인 박스의 가운데(각 변 30 % 안쪽) 깊이에 역깊이 평면을 맞춰 3 cm 안 비율이 0.95 이상이고, 명암 라플라시안 편차가 6 미만이면 "면"으로 버림. 사람은 몸통이 둥글고 다리 사이 틈이 있어 평면이 아니고 옷에 무늬가 있다. 처음엔 "박스 안 깊이 단차(실루엣) 유무"로 했는데, 세워 둔 검은 판을 노드가 사람으로 본 박스(신뢰도 0.85)에는 판 가장자리 단차가 들어 있어 못 걸렀다 → 가장자리는 보지 않고 가운데 평면성으로 바꿈
  2. `geometry.too_narrow_for_person`: person 박스의 실제 폭(픽셀 폭+2 × 거리 ÷ 초점 거리)이 0.15 m 미만이면 버림(판 가장자리 세로 띠 17 px·1.5 m = 0.11 m를 person 0.69로 보고 추적까지 됐음). leg 박스는 제외
- **확인**: 시뮬 녹화 같은 프레임에 적용 — 노드가 사람으로 봤던 검은 판 박스 평면 1.00·무늬 0.0 → 버림, 사람 장면 person 박스 151개(큰 것) 평면 중앙값 0.09·최대 0.84, 무늬 최소 3.0·중앙값 39 → 전부 유지, 469개 중 잘못 버린 것 0. 폭 하한에 걸리는 사람 박스는 4.6~4.9 m의 7 px짜리뿐이라 ±2 px 여유로 살림. 회귀: 손님 4/4×3(복구 0), 상자 4/4×2(최소 0.29~0.32 m), 순찰 3/3(180~186 s). 단위 시험 8개
- **진단**: 버린 박스는 `/person_detector/boxes` JSON의 `surface`에 [x1,y1,x2,y2,평면 비율,무늬]로 남고, 주석 영상에 회색 `surface plane:.. tex:..`로 그려짐. 실물에서 사람을 잘못 버리면 이 값으로 `person_detector.yaml`의 `surface.*`를 조정

## 실물(Jetson·RoboClaw·센서)

### 새로 부팅한 젯슨에서 실물 Nav2가 활성화되지 않음(`Managed nodes are active` 안 찍힘) — AMCL 초기 위치 전에 Nav2를 띄움 — 2026-11-11
- **증상**: `run_nav2_real.sh`를 띄우고 35 s 뒤 `Managed nodes are active` 0건. nav2.log: `Activating planner_server` 60 s 뒤 `[global_costmap]: Failed to activate global_costmap because transform from base_link to map did not become available` → `lifecycle_manager_navigation: Failed to change state for node: planner_server` → `Failed to bring up all requested nodes. Aborting bringup`. 그 사이 real.log에는 `[amcl]: AMCL cannot publish a pose or update the transform. Please set the initial pose...`가 2 s마다
- **원인**: 실물 AMCL(`amcl_real.yaml`)은 `set_initial_pose: false`라 `/initialpose`를 받기 전엔 `map→odom`을 내지 않는다. Nav2 비용 지도는 활성화 때 `base_link→map` TF를 60 s 기다리고(`initial_transform_timeout`), 못 받으면 활성화 실패 → 생명주기 관리자가 기동을 중단하고 스스로 다시 올리지 않는다. 11-10 절차 문서는 런치 3개를 다 띄운 뒤 위치 탐색·초기 위치를 보내는 순서였는데, 11-10에는 Nav2를 다시 띄울 때마다 AMCL이 이미 그날의 자세를 갖고 있어 드러나지 않았다
- **해결**: 순서를 센서+AMCL → **위치 탐색·`/initialpose`** → Nav2로 바꿈(`docs/REAL_PATROL_RUN.md` 2절 ③, `/tmp/setpose.sh`). 이미 중단된 Nav2는 런치 PID에 SIGINT로 내리고(노드 전부 `finished cleanly`) 초기 위치 뒤 다시 띄운다
- **확인**: 초기 위치 (0.840, −0.015) 0° 발행 → real.log `[amcl]: Setting pose` → Nav2 재기동 35 s 뒤 `Managed nodes are active` 1건, `use_astar`·`enforce_path_inversion`·충돌 감시 소스가 설정대로 읽힘

### 실물 비용 지도·충돌 감시가 라이다 높이 0.84~1.0 m 띠만 봄(0.84 m 아래 물체가 안 찍힘) — pcl_ros 복셀 노드의 기본 z 자르기 — 2026-11-10
- **증상**: 루프 13·14 bag의 `/mid360/points_costmap`(5 cm 복셀, 변경 기록 65)에서 가장 낮은 점이 거리와 상관없이 높이 0.84 m. 0.5 m 상자·쓰레기통·사람 다리가 라이다 쪽 비용 지도에 전혀 안 들어가고, 라이다 몸체 점(중심 8~38 cm)은 0.84~0.91 m라 통과
- **원인**: `pcl_ros filter_voxel_grid_node`는 `leaf_size`만 줘도 기본값 `filter_field_name: z`, `filter_limit_min/max 0~1`로 **센서 좌표 z 0~1 m만 남긴다**(노드를 따로 띄워 `ros2 param get`으로 확인). 라이다 원점이 0.837 m라 그 아래가 전부 버려짐. 11-09에 복셀을 넣으면서 이 기본값을 끄지 않았다
- **해결**: `start_mid360.launch.py`의 `mid360_costmap_voxel`에 `'filter_field_name': ''` 추가(높이 거르기는 비용 지도의 `min/max_obstacle_height`가 맡음). 테스트 `test_costmap_lidar_voxel_keeps_every_height`
- **확인**: 젯슨에서 한 장 집계 → 높이 0.60~0.84 m 점 0 → 410개. 한 바퀴(순찰 1)에서 새로 들어온 0.84 m 아래 점이 지도상 빈 바닥에 찍힌 비율 0.1~0.8 %(왼쪽·위·아래 복도), 오른쪽 복도 3 %는 정수기·쓰레기통·탁자 다리(실물). 카메라 복셀(`real_rgbd_voxel`)도 같은 기본값이지만 카메라 표시 거리가 1 m라 결과가 같아 그대로 둠

### 빈 복도·코너에서 로봇이 앞이 비었는데 1~3분 서서 좌우로 돎(W1 코너 87~182 s) — NavFn(A*) 전역 경로 떨림 + MPPI `enforce_path_inversion` — 2026-11-10
- **증상**: 순찰 4~6에서 W1 코너 통로(13.5, 0.0) 근처에 서서 방향만 10°↔114° 왕복, `Failed to make progress` 10 s마다, 복구 Spin 반복. 그 순간 로봇 발판 비용 0, 앞 1 m 비용 0, 라이다 최근접 점 1.6 m 뒤(장애물 없음), 제어기 출력 `cmd_vel_nav` 자체가 0. 사용자 사진(route1·2)도 빈 공간에서 멈춘 장면
- **원인**: `/plan`을 뽑으면 로봇 앞 3~7 cm에서 시작하는 **되꺾임이 수백 개**(순찰 5 46 s: 299개, 길이 24.6 m로 부풀어 보임; 순찰 6 150 s: (13.62, 0.21)↔(13.62, 0.23) 2 cm 왕복 374개). NavFn `use_astar: true`가 팽창 띠가 겹쳐 비용이 평평한 자리에서 내리막 따라가기가 흔들린 것. 여기에 MPPI `enforce_path_inversion: true`(10-14 시뮬 되돌이용)가 첫 되꺾임에서 경로를 자르고 `inversion_xy_tolerance 0.2`·`inversion_yaw_tolerance 0.4` 안에 들어올 때까지 정지. 경로 점 yaw는 전부 0이라 로봇이 +36°로 서 있으면 영영 못 채움. 재계획(3 s)에서 깨끗한 경로가 오면 출발 → 바퀴마다 29/110/87/182 s로 들쭉날쭉
- **확인한 반례**: W1 통과 판정(0.7 m) 실패 가설 — 네 바퀴 모두 W1을 0.07~0.14 m로 지났고 되돌아가는 경로 0개. 탁자 깜빡임 가설 — 탁자를 지도에 넣은 순찰 6이 더 나빠짐(182 s)
- **해결(진행 중)**: 순찰 7에서 `enforce_path_inversion: false`만 끄자 W1 코너 11 s(정지 0)로 풀림 → 원인 확정. 그러나 W3 코너에서 224 s 제자리 회전(3766°): 로봇이 W3(0.4, 9.8)를 1.2 m 남기고 먼저 꺾어 통과 반경 0.7 m 밖 → 경로가 W3까지 갔다 되돌아오는 진짜 머리핀(되꺾임 1개, 1.1~1.3 m 앞)이고, 처리를 끄니 MPPI가 머리핀을 따라가려다 돎. **되꺾임 처리는 머리핀용으로 필요**하므로 다시 켜고, 떨림은 계획기에서 줄인다(`use_astar: false` 또는 Smac), 머리핀은 통과 반경·W3 위치로 없앤다. 판단 지표는 경로 되꺾임 수(`plancusp.py` 방식)
- **교훈**: 10-15에 시뮬 계산 시간(A* 1~2 ms vs 다익스트라 2~6 ms)만 보고 A*로 바꿨고 경로 품질은 안 쟀다. 실물 설정은 그걸 그대로 가져왔다

### 지나가기 순찰(`navigate_through_poses`)이 출발 직후 "도착"으로 끝남(9 s, 로봇 안 움직임) — 경로 끝점이 출발점과 같음 — 2026-11-10
- **증상**: 경유점 W1·W2·W3·W4(pass) → HOME(stop)을 `patrol_node`로 보내면 `bt_navigator: Begin navigating … through 5 poses to (0.74, -0.04)` 0.04 s 뒤 `controller_server: Reached the goal!` → `Goal succeeded` → `Patrol mission completed`. 두 번 반복해도 같음
- **원인**: Nav2 지나가기 주행의 도착 판정(`general_goal_checker`, xy 0.25 m·yaw 0.25 rad)은 **전역 경로의 끝점**만 본다. 중간 경유점을 지났는지는 보지 않는다(`RemovePassedGoals`는 지난 점을 목록에서 빼는 일만 함). 로봇이 HOME에서 출발하는데 경로 끝도 HOME이라 즉시 도착. 시뮬 경유점 파일(`aischool_loop_waypoints.yaml`)이 A만 stop으로 둔 것도 같은 이유였다
- **해결**: 한 바퀴를 출발점≠끝점인 두 구간으로 나눔 — W1·W2 pass → **MID stop**(위 복도 한가운데 (6.5, 9.5), 진행 방향 180°라 회전 없이 감속만) / W3·W4 pass → HOME stop. `limbo_patrol/config/real_loop_waypoints.yaml`(변경 기록 67). `patrol_node`는 마지막 경유점이 stop이어야 하므로 HOME은 파일 맨 뒤
- **확인**: 순찰 1 한 바퀴 264 s 완주(`Begin navigating … through 3 poses to (6.50, 9.50)` → 성공 → `… to (0.74, -0.04)` → 성공)

### 스크립트 안에서 `&`로 띄운 `ros2 bag record`가 Ctrl+C(SIGINT)를 무시해 기록이 안 닫힘(열린 mcap은 읽기 실패) — 2026-11-10
- **증상**: `bash 스크립트.sh` 안에서 `ros2 bag record … &`로 띄운 기록에 PID로 `kill -INT`를 보내도 계속 돈다(`/proc/<pid>/status`의 `SigIgn`에 SIGINT). 그동안 `rosbag2_py`로 열면 `Could not open … with 'mcap'. Error: read failed`
- **원인**: 비대화형 셸이 뒤에 띄운 작업은 POSIX 규칙대로 SIGINT·SIGQUIT를 무시(SIG_IGN)한 채 시작되고, 자식은 그 상태를 물려받는다. 같은 기록을 `setsid -f`로 띄우면(루프 15) SIGINT가 먹었다
- **해결**: 스크립트 안의 기록은 `setsid -f ros2 bag record …`로 띄우고 PID를 `ps`로 찾아 `kill -INT`. 이미 무시 상태로 돈 기록은 PID에 **SIGTERM**(rosbag2가 잡아서 정상 종료, `SigCgt`에 있음) — PM 승인 뒤 1회 사용
- **확인**: SIGTERM 1 s 뒤 종료, `metadata.yaml` 생성, 290 s 기록이 정상으로 읽힘. 이후 3왕복·2왕복·순찰 기록 11개 모두 SIGINT로 닫힘

### 오른쪽 위 코너(W2→W3)에서 AMCL이 로봇을 벽 너머로 1~1.5 m 끌어올려 목표 중단(4바퀴 중 3번) — 손으로 밀어 만든 지도의 복도 길이 오차 + 열린 문 — 2026-11-09
- **증상**: W2(코너) 도착 뒤 W3로 꺾는 순간 스캔 일치율이 46 → 31 → 29 %로 떨어지고 AMCL 위치가 (11.0~11.4, 9.3~9.85), 지도상 위 복도 윗벽 너머로 올라간다. 로봇은 실제로 복도 코너에 서 있음(사용자 확인). `GridBased plugin failed to plan from (11.05, 9.07) … Failed to create plan with tolerance of: 0.500000` → 복구(후진·회전)도 `Collision Ahead` → 40~58 s 뒤 ABORTED. 17:40쯤(루프 8)은 같은 지도로 통과(코너 일치 77~89 %), 18:25 이후 루프 9·10·12 실패, 11만 통과
- **원인**: 둘이 겹침
  1. **지도 길이**: 11-05 지도(손으로 밀며 slam_toolbox)의 오른쪽 복도가 바퀴 odom보다 12~14 %(지도 5.00 m 대 odom 5.59~5.68 m, 3바퀴 모두), 위 복도가 약 16 %(6.00 대 7.00 m) 짧다. 바퀴 odom은 줄자와 1~1.5 % 일치. 벽이 진행 방향과 나란한 복도에서 AMCL은 앞뒤 위치를 odom에 기대므로, 실제 코너에 닿을 때 지도상으로는 이미 코너를 약 1 m 지나 벽 너머에 있다. 코너 벽 모양을 보고 0.6~1 m를 되돌려야 하는데 성공할 때(루프 8·11)와 못 할 때(9·10·12)가 갈린다
  2. **열린 문(악화 요인)**: W2→W3와 W3→W4(유리) 문이 18시 이후 복도 쪽으로 직각으로 열려 있었다(사용자 확인). 루프 8과 10의 같은 자리 스캔을 겹치면 10에서는 위 복도 윗벽 대신 문틀 너머 약 1 m 뒤 교실 벽이 잡힘 → 코너 모양이 지도와 더 달라 되돌림이 실패
  - AMCL 설정 탓이 아닌 근거: 수동 한 바퀴 bag을 AMCL과 독립으로 재추적(odom 예측 + 스캔-지도 ±0.25 m·±6° 국소 맞춤)해도 기존 지도에서는 같은 코너에서 일치 37~43 %로 떨어지고 위로 끌려간다
- **해결**: 원점 출발·복귀 수동 한 바퀴 bag(`~/limbo_bags/manual_loop2_1109`)으로 오프라인 SLAM(아래 항목) → 원점 주변(x −1.6~6, y −1.2~3) 벽을 ICP로 기존 지도에 맞춰 같은 좌표로 회전·저장 → `maps/real_open_space_20261109`. 경유점은 로봇이 지나간 복도 중심으로 다시 잡음(오른쪽 복도 +1.1 m, 위 복도 +1.8 m 바깥, 변경 기록 66). 떠 있는 런치에는 `ros2 service call /map_server/load_map nav2_msgs/srv/LoadMap "{map_url: <yaml>}"`로 바로 바꿀 수 있다(AMCL `Received a 680 X 560 map`, 전역 비용 지도 `StaticLayer: Resizing costmap to 680 X 560` 확인)
- **확인**: 지도 만들 때 안 쓴 bag(루프 11·12)을 새 지도로 재추적 → 일치 평균 95 %·최저 82~86 %·코너 96 %(기존 지도 72 %·21 %·41 %). 새 지도로 자율주행 2바퀴 완주(문 열림 324 s, 문 닫힘 313 s), 코너 일치 86~93 %
- **남은 것**: 새 지도는 문이 열린 상태로 만들어 W2→W3 문짝이 벽 선으로 들어가 있다 → 문틀·문짝 범위를 "모름"으로 비울 것. 오른쪽 복도는 새 지도도 odom보다 5.5 % 짧게 추적됨(줄자로 확인). **주의**: 일자 복도 구간의 "AMCL 이동량 대 odom" 비교는 AMCL이 odom을 따라가므로 지도 정확도의 근거가 못 된다(아래 복도가 1~2 %로 나온 것은 의미 없음). 코너·문·기둥처럼 앞뒤를 잡는 특징이 있는 구간에서만 길이 오차가 드러난다

### bag으로 오프라인 SLAM을 돌렸는데 지도가 안 만들어짐(`map_saver: Failed to spin map subscription`) — Jazzy slam_toolbox 수명 주기 활성화 + 재생 `/tf_static` QoS — 2026-11-09
- **증상**: 노트북에서 `ros2 run slam_toolbox sync_slam_toolbox_node --params-file slam_real.yaml -p use_sim_time:=true` + `ros2 bag play <bag> --clock 100`을 끝까지 돌려도 노드 로그는 `Node using stack size …` 한 줄뿐, `/map` 없음. 런치로 바꾼 뒤에는 `New publisher discovered on topic '/tf_static', offering incompatible QoS … DURABILITY_QOS_POLICY`가 찍히고 여전히 지도 없음
- **원인**: ① Jazzy의 slam_toolbox 노드는 수명 주기 노드라 `ros2 run`으로만 띄우면 비활성 상태로 스캔을 안 받는다. ② `ros2 bag play`는 `/tf_static`을 휘발성(volatile)으로 다시 내보내는데 tf 리스너는 transient_local을 요구해 정적 TF(`base_footprint → mid360_link`)를 못 받음 → 스캔을 로봇 좌표로 못 옮겨 전부 버림. ③ 주행 bag의 `/tf`에는 AMCL의 `map → odom`이 들어 있어 SLAM의 `map`과 충돌한다
- **해결**: (1) bag에서 `/scan /tf /tf_static /odom`만 새 bag으로 옮기며 `/tf`의 `frame_id == 'map'` 변환을 뺀다(rosbag2_py Reader→Writer). (2) `ros2 launch slam_toolbox online_sync_launch.py slam_params_file:=…/slam_real.yaml use_sim_time:=true autostart:=true`. (3) `ros2 bag play <새 bag> --clock 100 --qos-profile-overrides-path <yaml>`, yaml은 `/tf_static: {depth: 1, durability: transient_local, reliability: reliable, history: keep_last}`. (4) 재생이 끝나면 `ros2 run nav2_map_server map_saver_cli -f <이름> --ros-args -p use_sim_time:=true -p map_subscribe_transient_local:=true`. 젯슨과 섞이지 않게 `ROS_DOMAIN_ID`를 다른 번호로, `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`
- **확인**: 노드 로그에 `Registering sensor: [Custom Described Lidar]`, 재생 219 s 뒤 `Map saved successfully`, 고리가 닫힌 ㅁ자 지도. 런치가 활성화를 두 번 요청해 `Unable to start transition 3 from current state active`가 한 번 찍히는 것은 무해

### 주행 중 load 5~7(코어 6), 제어 주기 20 → 11 Hz, 계획기 응답 timeout으로 목표 중단 — 전밀도 라이다 점군을 비용 지도 2개가 각각 처리 — 2026-11-09
- **증상**: 복도 주행 중 load1 4.5~6.5, `Control loop missed its desired rate … 11.6 Hz`, MPPI `Optimizer fail to compute path` 반복(중간 멈춤·후진), 도착 방향 회전 중 `Timed out while waiting for action server to acknowledge goal request for compute_path_to_pose` → 목표 ABORTED, collision_monitor TF 외삽 실패로 정지. YOLO는 꺼진 상태
- **원인**: `/mid360/points_filtered`가 18.5k점·10 Hz·5.6 MB/s로 거의 전밀도(몸체 상자만 제거)인데 로컬·글로벌 비용 지도(mark·clear 각각)와 충돌 감시, 스캔 변환 6곳이 각자 DDS로 받아 풀고, 비용 지도 2개가 5 cm 격자에 18.5k점을 매초 10번 넣고 광선으로 지움. 주행 중 controller_server 평균 41 %·최대 59 %
- **해결**: `start_mid360.launch.py`(mounted)에 `pcl_ros filter_voxel_grid_node`(leaf 0.05) → `/mid360/points_costmap`(1,014점·270 KB/s). `build_real_configs.py`가 실물 프로필의 비용 지도·충돌 감시 소스를 그 토픽으로. 원본·`/scan`·AMCL은 그대로
- **확인**: 같은 조건 주행에서 load1 최대 6.5 → 3.9, 최적화 실패 0, 한 바퀴 구간 시간 단축. **안 줄어든 것**: 정지 상태 Nav2 노드 합계 90 → 85 %(lifecycle_manager 16 %, bt_navigator 10 % 등 할 일 없이) — 점군과 무관한 노드 자체 소모, 별도 조사. 컴포지션(`composition:=true`)은 정지 80 %로 10 %만 절감
- **주의**: 컴포지션 컨테이너에는 params 파일을 따로 줘야 한다. 안 주면 `local_costmap`이 설정 없이 기본 레이어(static·obstacle·inflation)로 떠 STVL이 빠지고, MPPI 비용 심판이 "Inconsistent configuration in collision checking" 뒤 세그폴트(exit −11)로 컨테이너가 죽는다

### 유리문 앞에서 카메라가 정면 1.0~1.22 m에 0.5 s짜리 가짜 벽을 찍음 — 스테레오가 유리에 비친 로봇 자신을 봄 (미해결 포함) — 2026-11-09
- **증상**: 한 바퀴마다 같은 자리(오른쪽 복도 y≈5.5~6.5, 왼쪽 복도 y≈4, W1 진입)에서 MPPI `Optimizer fail to compute path`가 1초에 6~7회 뭉치고 로봇이 좌우 60°씩 비틀거나 후진. 사용자 확인: 그 자리에 **유리문**이 있음
- **원인(확인된 부분)**: bag(`~/limbo_bags/glass_1109`)에서 비튼 순간을 꺼내면 카메라 점군에 정면 0.95~1.22 m·폭 0.6~0.9 m·높이 0.3~1.05 m 덩어리가 139~250점 나타났다 0.5 s 만에 0이 되고, 같은 순간 라이다 점군에는 그 자리에 아무것도 없다. 거리(유리 거리 0.5~0.6 m의 2배)·폭·높이가 로봇 몸통과 맞아 유리에 비친 로봇 거울상으로 판단. 팀원 `near_depth_filter.py`는 깊이 ≤1.0 m만 지우고 "큰 면은 통과"시키므로 1.0~1.22 m 덩어리는 그대로 비용 지도(STVL `rgbd_mark`, 표시 거리 4.5 m)에 들어가 팽창 0.45까지 더해 좁은 복도를 막는다
- **한 것**: 실물 프로필 `rgbd_mark.obstacle_range` 4.5 → 1.0 m(카메라 역할 = 라이다 사각의 가까운 낮은 장애물). 적용 후 W1→W2 1회: W2 49 s로 빨라졌지만 최적화 실패 9/11회 그대로 → **카메라만이 원인이 아니거나 0.95~1.0 m 경계가 남음**
- **확인(남은 일)**: 모든 주행에 bag을 켜고(`ros2 bag record /mid360/points_costmap /rgbd_camera/points /tf /tf_static /amcl_pose /local_costmap/costmap /plan /cmd_vel_nav /scan`) 실패 한 건마다 그 시각의 비용 지도·점군·경로를 그려 센서/경로 교체 중 어느 쪽인지 특정. 근본 처리 후보: OAK 장치 내 스테레오 신뢰도·LR 체크, 시간 일관성(두세 프레임 연속) 필터, 지도에 유리 구간 표시. 딥러닝 문제가 아니라 센서 물리·기하 문제다

### 좁은 복도(폭 1.5 m)에서 멈칫·후진 반복, `Optimizer fail to compute path` 뭉치 — 로컬 비용 지도의 정적 지도 층이 어긋난 벽을 들여옴 — 2026-11-09
- **증상**: 위 복도 11.6 m에 95 → 136 → 185 s. 멈춘 구간에 `Optimizer fail to compute path` 6~13회, 제어 주기 7.6 Hz까지, TF 외삽 오류·충돌 감시 정지 1회. 아래 복도(폭 3 m)에서는 같은 설정으로 문제 없음
- **원인**: 멈춘 구간에서 controller_server CPU가 13~30 %(순항 55~60 %)로 **낮았다** → 계산이 밀린 게 아니라 MPPI 후보가 전부 충돌로 판정돼 즉시 실패. 로컬 비용 지도 플러그인에 `static_layer`가 있어 지도 벽이 로컬 회피에 들어오는데, 손으로 밀며 만든 지도는 벽이 실제보다 20~30 cm 안쪽인 곳이 있다(원점 뒤 벽: 라이다 0.95 m, 비용 지도 0.62 m). 폭 1.5 m 복도에서 로봇 반폭 0.3 + 팽창 0.45 = 0.75를 빼면 여유가 0이라 지도 벽이 20 cm만 틀어져도 로봇이 "벽 안"
- **해결**: `build_real_configs.py`가 실물 로컬 비용 지도에서 `static_layer`를 뺀다(센서 STVL·사람 층·팽창만). 지도 벽은 글로벌 계획에만. 이동창 로컬 비용 지도에 정적 층을 안 두는 것이 Nav2 표준 구성이기도 하다
- **확인**: 한 바퀴 4차(0.4 m/s)에서 구간 시간·최적화 실패 횟수 비교(변경 기록 65). 재지도로 지도 오차 자체도 줄일 것

### 목표 주행 뒤 줄자 거리가 로봇 odom과 2 m 차이 — 복도에서는 AMCL 일치율이 앞뒤 위치를 보증하지 않는다 — 2026-11-09
- **증상**: 6 m 목표 주행 뒤 줄자 7.39 m, odom·AMCL 5.3 m(스캔 일치 99 %). 바로 뒤 같은 속도(0.25 m/s) 6 m 직진 시험은 줄자와 1.5 % 일치, 0.1 m/s 2 m도 1.1 %
- **원인(판단)**: 로봇 거리 측정은 정상(바퀴 카운트 L 5.35/R 5.39 m, 속도 상한 0.25 m/s × 움직인 25 s ≤ 6.2 m라 7.39 m는 물리적으로 불가). 기준점(출발선 또는 6 m 표시)이 달랐다고 보고 종결. 단, 이 과정에서 드러난 사실: 벽이 진행 방향과 나란한 복도에서 AMCL 스캔 일치율은 **옆 위치·방향만** 구속하고 **앞뒤 위치는 odom을 따라간다**. 일치율 99 %가 x 위치의 정답을 뜻하지 않는다
- **해결**: 거리 검증은 `straight_run.py`(odom) + 줄자로 같은 속도에서 직접. 위치 추정의 앞뒤 오차는 복도 끝·문·기둥 같은 x 방향 특징이 보일 때만 잡힌다 — 재지도 때 그런 특징이 지도에 남도록 할 것
- **확인**: 같은 날 두 번째 바퀴 끝에 AMCL이 180° 뒤집힌 가설(일치 66 %)에 눌러앉은 것도 같은 성질(앞뒤 대칭 복도). `tools/drive/pose_search.py X Y`(위치 ±0.6 m·방향 5° 간격 전수 비교)로 실제 자세를 찾아 다시 초기화

### 목표가 등 뒤에 있으면 제자리 회전에 30 s, 10 s마다 "Failed to make progress" — MPPI 좌우 대칭 + 이동만 세는 진행 감시기 — 2026-11-08
- **증상**: 6 m 직진 뒤 복귀 목표(180° 반대)를 주면 로봇이 0.05~0.1 rad/s로 찔끔찔끔 돌고, 10 s마다 "Failed to make progress"→복구 동작(비용 지도 지우기·회전·후진)이 끼어들어 180° 도는 데 29~30 s. 제자리 회전 목표만 주면(위치 같고 방향만 180°) 7 s에 0.57 rad/s로 멀쩡히 돎
- **원인**: 둘이 겹침. ① MPPI는 샘플 2,000개의 비용 가중 평균으로 명령을 내는데 경로가 정반대면 좌·우 회전 비용이 거의 같아 평균이 0 근처에서 상쇄된다(1 s 단위 기록: 0°→80° 22 s 동안 명령 0.04~0.10, 80° 아래부터 0.37로 가속, 145°부터 전진). 바퀴·평활기는 명령=실측으로 따라옴. ② 진행 감시기 `SimpleProgressChecker`는 10 s에 0.5 m **이동**만 보고 회전은 진행으로 안 쳐서 느린 회전이 매번 실패 처리
- **해결**: `nav2_params.yaml` → `FollowPath`를 `RotationShimController`(Nav2 표준, MPPI와 같은 패키지 버전 1.3.13)로 감싸고 `primary_controller`에 MPPI. 45° 이상 어긋나면 제자리에서 주행 노드 상한 0.8 rad/s로 돌고 MPPI에 넘김. 진행 감시기는 `PoseProgressChecker`(이동 0.5 m 또는 회전 0.5 rad). 값은 `build_real_configs.py`가 drive.yaml 한계에서 채움. MPPI 심판 가중치(PathAngleCritic 2)는 안 건드림 — 근거 없는 숫자 맞추기가 되기 때문
- **확인**: 11-08 주행 6: 180° 회전 6 s(명령·실측 0.8 rad/s), 45° 남았을 때 MPPI 인계, 5 m 주행 ±7°, 진행 없음 0회, 29 s 도달. `tools/drive/nav_preflight.py --goal X Y`가 목표 쪽 비용을 보므로 등 뒤 목표도 점검 가능

### 주행 중 발밑에 장애물이 켜졌다 꺼졌다 하며 제자리에서 ±90° 흔듦 — 라이다가 로봇 윗부분(뚜껑 추정)을 봄 — 2026-11-08
- **증상**: 복귀 주행 15 s 뒤 전진 0.03 m/s로 떨어지고 좌우 ±90° 흔들며 "Failed to make progress". 로컬 비용 지도 로봇 반경 0.45 m 안 최대 비용이 1 s마다 0↔99~100으로 깜빡임(이전 주행에서도 간헐적으로 켜졌다 꺼짐)
- **원인**: `/mid360/points_filtered`에 로봇 중심 0.23~0.7 m, 높이 0.80~1.37 m 점 1,330개(가장 가까운 점 (−0.20, +0.11, 0.84)). 몸체 필터(`MID360s_mount.json`)는 45×45 cm·높이 0.79 m(+1 cm)까지만 지우고, 비용 지도는 라이다 점을 높이 1.0 m까지 장애물로 찍으므로 0.80~1.0 m 점이 로봇 발밑 막힌 칸이 된다. 윗판(0.79 m)보다 위에 있는 것 = 11-04 팀원 메모 "lid must remain closed"의 뚜껑으로 추정(열림·주행 진동으로 들썩이면 깜빡임이 설명됨). 사람은 아니었음(확인)
- **해결(예정)**: 바퀴 수리 후 뚜껑 닫힘을 확인하고 0.7 m 안 라이다 점이 0인지 본 뒤 결정 — 뚜껑 고정 또는 몸체 필터 높이 상향(설계 결정, PM)
- **확인**: `python3 tools/drive/near_obstacles.py` — `/scan`·카메라·`/mid360/points_filtered`의 2 m 안 점과 로컬 비용 지도 막힌 칸을 base_footprint 기준으로 나열해 어느 센서인지 가른다. 뚜껑 닫고 0.7 m 안 라이다 점 0이어야 함. 점검 도구에 "로봇 반경 0.5 m 안 라이다 점 0개" 항목 추가 검토

### Nav2 목표를 주면 좌우로 머리를 흔들다 "Failed to make progress" — 카메라 가짜 근거리 점이 1 m 앞 가상 벽 — 2026-11-07
- **증상**: 바퀴·odom·위치 추정이 다 맞는데(스캔 일치 90 %) 목표를 주면 MPPI가 전진 0.03 m/s에 회전 ±0.4 rad/s로 좌우 40°씩 흔들고 10 s 안에 0.5 m를 못 가 중단. 11-06 팀원 로그에도 "첫 0.75 m 경로 중심선 최대 비용 92"
- **원인**: 로컬 비용 지도에 로봇 정면 1 m, 복도 폭 전체의 비용 99 띠. 점군을 base_footprint로 바꿔 보니 카메라(OAK) 점 150개가 정면 0.5~1.25 m·높이 0.3~1.0 m에 뭉쳐 있고 앞을 비워도 그대로 — 스테레오 깊이의 가짜 근거리 점(짝 오인). 팀원이 그걸 지우는 `near_depth_filter.py`를 만들었지만 런치 기본값 `filter_near_depth=false`로 꺼 둔 채였다
- **해결**: `start_real.launch.py`·`start_rgbd_points.launch.py` 기본값 `true`. 켜면 깊이 영상 1 m 안 0 %, 점군 비어 있음(비용 지도는 카메라 점을 1 m 안쪽만 쓰므로 정상)
- **확인**: `tools/drive/nav_preflight.py`가 "정면 2 m·높이 0.3 m 아래 카메라 점 0개"와 "목표 쪽 0.3~1.5 m 최대 비용 < 50"을 검사한다. 11-08 필터 켠 상태로 6 m 목표 주행 4회 도달(±4~7°, 진행 없음 0회)로 확인

### AMCL이 초기 위치와 다른 자리에 눌러앉음 (ㅁ자 복도·유리벽) — 2026-11-07
- **증상**: `/initialpose` (0, 0.3, 0°)를 줘도 AMCL이 (−0.9, −0.35, 22°) 등으로 수렴. 로봇을 1 m 옮겨도 같은 곳. 그 상태로 Nav2를 띄우면 경로가 벽을 지나 계획 실패·복구 회전만 반복
- **원인**: 지도가 ㅁ자 복도라 비슷한 단면이 많고 유리벽으로 새어 나간 빗살이 많아, 스캔이 그럴듯하게 맞는 자리가 여럿. 로봇이 지도 −x 방향을 보고 있었는데 0°로 초기화한 경우(두 번) AMCL이 가까운 가짜 해에 수렴
- **해결**: 초기화 뒤 반드시 스캔 일치율을 본다. 맞으면 80~90 %, 틀리면 29~41 %. 틀리면 로봇 방향·자리를 다시 보고 초기화. 지도 원점에서 +x(초록)를 보게 놓는 것이 11-06 팀원 시험과 같은 조건
- **확인**: `nav_preflight.py` 2번 항목(기준 70 %). 원점에서 지도 −x 쪽은 0.3 m 앞이 벽으로 그려져 있어 목표를 그쪽에 주면 계획 자체가 안 된다


### 자율주행에서 한쪽 바퀴가 서고 출발에 1.5~2 s 걸리며 방향이 ±15° 틀어짐 — 2026-11-07
- **증상**: 11-06 Nav2 목표점 주행 2회 모두 4.2~4.4 m에서 좌우 이동량 불균형으로 중단. 출발 지연 1.5~2.0 s, 0.25 m/s 명령에 실측 0.16 m/s, 0.03~0.07 m/s 목표에서 오른쪽 바퀴가 수 초씩 섬. 키보드(0.1 m/s 고정)로는 잘 감. "오도메트리가 틀어진다"고 보고됐지만 odom 방향은 AMCL과 0.4~3.8° 안에서 일치했음
- **원인**: 젯슨 쪽 PI(50 ms 주기 + 시리얼 지연 100~150 ms)는 지연 때문에 약하게(kp 0.02, ki 0.10) 둘 수밖에 없고 출력 변화율을 15 %/s로 묶어 두어, 구르기 시작에 20 % 이상이 필요한 이 로봇에서 저속·출발을 못 따라감. 같은 출력에서 오른쪽이 왼쪽의 65 %밖에 안 도는 것(50 %: 0.24 vs 0.39 m/s, 바퀴 띄우고 실측)을 호스트 PI가 못 메움. 보드의 속도 제어기(0.3 ms 주기)는 값이 전부 0(공장 상태)이라 꺼져 있었음
- **해결**: `tools/drive/board_setup.py`로 보드에 왼쪽 엔코더 방향 반전(모드 0x40), QPPS(100 % 출력 속도 M1 6264·M2 6351), 속도 PID 1.0/0.5/0.25, 전압 한도 저장. 주행 노드 `control_mode: board_speed`(기본)로 바퀴 목표 속도만 보냄. 변경 기록 55·57~60
- **확인**: 바닥 자동 직진 6 m 3회(`tools/drive/straight_run.py`): 좌우 차 4~7 mm, 방향 0.5~1.2°, 출발 0.35~0.45 s, 실측 0.100 m/s, 보드 출력 평균 18~20 %로 바퀴마다 알아서 다름. 기록 `~/limbo_bags/straight_1107_1`·`_2`

### 충전 직후·충전기 꽂은 채 보드가 "전압 높음"으로 안 움직임, 보드 최대 전압 한도가 켤 때마다 다름 — 2026-11-07
- **증상**: 11-03 아침 충전 뒤 출력을 줘도 모터가 안 돌고 상태 비트 Main Battery High. 11-06 읽은 최대 한도 31.1 V, 11-07 재시작 뒤 13.9 V로 제멋대로. 충전기를 꽂은 채 읽으면 주전원 29.2 V
- **원인**: 보드의 "최대 전압 자동 감지"(명령 57의 오프셋 바이트 ≠ 0)가 켜져 있어 켤 때마다 최대 = 그때 전압 + 2 V(11.9 → 13.9, 충전기 29.1 → 31.1). 낮은 전압에서 켠 뒤 충전하면 한도를 넘어 보드가 출력을 막음. 충전기 출력은 무부하 29 V라 꽂은 채로는 보드가 그 값을 읽음
- **해결**: `board_setup.py voltage --min 10 --max 16 --auto-offset 0` 뒤 `save`. 오프셋 0이 자동 감지 끔(재시작 뒤 16.0 유지 확인). 최소는 10.0을 쓰면 9.9로 읽힘(보드 특성)
- **확인**: 충전기 꽂으면 29 V > 16 V라 출력이 막히고(의도), 뽑으면 12 V대로 돌아와 주행. 주행 전 충전기부터 뽑을 것

### board_speed 주행 노드가 Nav2 복구 회전 중 "바퀴가 반대 방향으로 빨라짐"으로 스스로 꺼짐 — 2026-11-07
- **증상**: 자율주행 도중 주행 노드가 `구동 중단: 왼쪽 바퀴가 목표와 반대 방향으로 빨라짐(목표 −40 카운트/초, 실측 0.27 rad/s)`로 종료(두 번). 그 뒤 odom TF가 끊겨 AMCL이 스캔을 버리고 Nav2가 멈춤
- **원인**: 엔코더 방향 설정이 실제와 다를 때 보드가 출력을 계속 올리는 것을 막는 보호 장치가, 목표가 뒤집히는 순간(Nav2가 100 ms 안에 회전 방향을 바꿈)을 오판. 속도 추정이 0.1 s 창이라 목표가 바뀐 뒤 2~3틱은 옛 방향으로 빨라지는 것처럼 보이는데 판정이 3틱이었음
- **해결**: 반대 방향 + 빨라짐에 "목표 크기보다 빠름" 조건, 해상도(창 안 한 카운트) 이상 늘어난 것만 빨라짐으로, 연속 틱 요구를 추정 지연 틱(2) + 3으로. 변경 기록 58·59
- **확인**: 직진 6 m 3회·키보드 회전에서 오판 없음. 노드가 꺼졌는지는 `ros2 topic hz /odom`(19 Hz 나와야)과 런치 로그 `process has died`로 바로 알 수 있음


### Jetson에서 YOLO가 `torch.cuda.is_available(): False`, GPU를 못 봄 — 2026-11-03
- **증상**: 어제까지 GPU로 돌던 검출기가 `cuda False`로 CPU로 떨어짐. `nvpmodel -q`가 `Error opening /sys/devices/platform/17000000.gpu/devfreq_dev/min_freq`.
  커널 로그(`journalctl -b 0 -k`)에 `nvgpu ... ACR bootstrap failed`, `RISCV ucode patch wpr info failed`, `libnvrm_gpu.so: NvRmGpuLibOpen failed, error=4`
- **원인**: 그 부팅에서 GPU 펌웨어 부트스트랩이 실패한 것. 이전 부팅들엔 같은 메시지가 없고 패키지 변경도 없었다. 로봇 전원을 만진 직후 올라온 부팅이었다
- **해결**: `sudo reboot` 한 번. 재부팅 뒤 오류 0건, `cuda True (Orin)`
- **확인**: 전원을 건드린 뒤 YOLO를 띄우기 전에 `journalctl -b 0 -k | grep -c "ACR bootstrap failed"`가 0인지 본다. 0이 아니면 바로 재부팅

### 실물 slam_toolbox가 `/scan`을 구독하지 않고 `/map`·`map→odom`이 안 나옴 — 2026-11-03
- **증상**: `ros2 run slam_toolbox async_slam_toolbox_node`로 띄우면 노드는 뜨는데 `ros2 topic info -v /scan`의 구독자에 slam_toolbox가 없고 지도가 안 생김
- **원인**: Jazzy의 slam_toolbox는 lifecycle 노드라 configure·activate 전에는 아무것도 안 한다. 시뮬 런치는 `nav2_lifecycle_manager`가 자동으로 해 줬다
- **해결**: 지도 작성 런치(`start_mapping.launch.py`)에 lifecycle_manager(autostart, bond_timeout 0) 추가. 손으로는 `ros2 lifecycle set /slam_toolbox configure` → `activate`
- **확인**: `ros2 lifecycle get /slam_toolbox`가 `active`, `/map`이 나오고 `tf2_echo map base_footprint`에 Translation이 찍힘

### RoboClaw가 PWM은 15 %로 나가는데 전류 0, 바퀴가 안 돎 (충전 직후) — 2026-11-03
- **증상**: 배터리를 충전해 12.1 V가 됐는데 벤치 주행이 무동작. 보드 상태값에 `0x00040000`(Main Battery High Warning)
- **원인**: 보드의 최대 전압이 자동 모드("켤 때 전압 + 2 V")라, 배터리가 9.8 V일 때 켜면 상한 11.8 V가 되고 충전 뒤 12.1 V는 그 위. 매뉴얼: 이 경고 동안 "모터를 제동으로 멈춤"
- **해결(권고, 미적용)**: Motion Studio General Settings에서 자동 감지 끄고 Max Main Battery 16 V(납축 충전 전압 14.7 V 위), Min 10 V. 소프트웨어 쪽은 `roboclaw_drive`가 이 비트를 보면 출력을 0으로 두고 진단에 이유를 적는다
- **확인**: `probe_settings`(명령 59)의 max가 배터리 전압보다 위이고, 상태값에 0x40000이 없음

### 전원 재투입 뒤 RoboClaw 명령 timeout이 0으로 돌아감 — 2026-11-03
- **증상**: 어제 0.5 s로 넣어 둔 명령 timeout(명령 15)이 오늘 0으로 읽힘. 벤치 도구는 이 값이 5가 아니면 시작을 거부
- **원인**: 명령 14로 넣은 값은 런타임 값이라 전원을 끄면 사라진다(NVM 저장 명령 94는 일부러 안 씀)
- **해결**: `roboclaw_drive`가 시작할 때 0이면 0.5 s를 다시 넣는다(`ensure_timeout`). 벤치 도구를 쓸 때는 `configure_timeout.py`를 먼저
- **확인**: 노드 시작 로그 `opened {... "command_timeout_s": 0.5 ...}`

## 관제 서버(dashboard)

### iPhone에서 관제 화면을 열면 로그인 창이 계속 뜸(로그인해도 몇 초마다 다시 뜸) — Safari는 WebSocket에 basic auth를 싣지 않음 — 2026-11-12
- **증상**: PC 브라우저에서는 한 번 로그인하면 되는데, iPhone(Safari·iOS Chrome)에서는 로그인해도 몇 초 간격으로 로그인 창이 다시 뜸. 화면 상태도 갱신되지 않음
- **원인**: 앞단 Caddy가 화면·브라우저 API 전체에 basic auth를 건다. 실시간 상태는 WebSocket(`/api/v1/stream`)으로 받는데, WebKit(Safari, iOS의 모든 브라우저)은 WebSocket 연결에 basic auth 자격 증명을 싣지 않는다. 그래서 이 연결만 Caddy에서 `401`(`Www-Authenticate: Basic`)을 받고, 화면이 1·2·4·8·10초 간격으로 재연결할 때마다 로그인 창이 다시 떴다. PC Chrome·Firefox는 자격 증명을 실어 보내서 드러나지 않았다
- **해결**: WebSocket을 일회용 입장표로 인증 (`be489a4`, 변경 기록 75)
  - 서버: `POST /api/v1/stream-ticket`이 30초 유효·한 번만 쓰는 입장표를 준다. 이 경로는 basic auth 뒤에 있어 로그인한 사람만 받을 수 있다. `WS /api/v1/stream?ticket=`은 입장표가 맞을 때만 받는다
  - Caddy: `/api/v1/stream`만 basic auth 없이 서버로 넘긴다
  - 화면(`ui/src/live.ts`): 연결·재연결마다 입장표를 먼저 받고 WebSocket을 연다
- **함께 겪은 함정 — 서버에서 `git pull` 뒤 `up -d --build`만 했더니 그대로**: `Caddyfile`은 bind mount라 파일이 바뀌어도 Caddy 컨테이너가 다시 만들어지지 않아 예전 설정으로 계속 돌았다. `docker compose up -d --build --force-recreate`로 해결. 업데이트 안내(`docs/AWS_DEPLOY.md` 10절, `dashboard/README.md`)도 이 명령으로 바꿈 (`96ae57c`)
- **확인**:
  - 시험: 서버 114개(입장표 없음·틀림·재사용 거절 포함), UI 단위 34개, e2e 27개 통과
  - 배포 확인(로그인 없이): 아래 명령이 Caddy의 `401`이면 예전 설정, 서버의 `403`이면 새 설정. 2026-11-12 서버에서 `--force-recreate` 전 `401`, 뒤 `403`. `/`·`/api/v1/state`·`POST /api/v1/stream-ticket`은 그대로 `401`(로그인 필요)
    ```bash
    curl -si --http1.1 -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
      -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
      https://<DOMAIN>/api/v1/stream | head -1
    ```
    `--http1.1`을 빼면 HTTP/2로 붙어 업그레이드 헤더가 빠지므로 항상 basic auth `401`이 나온다
  - iPhone 실기 확인(2026-11-12, `--force-recreate` 뒤): 로그인 한 번 뒤 로그인 창이 다시 뜨지 않고 정상 접속됨
- **이후(변경 기록 76, 2026-11-12)**: Caddy basic auth를 없애고 관제 서버의 계정 로그인(로그인 화면·세션 쿠키)으로 바꿔 이 문제의 원인 자체가 사라졌다. 입장표는 로그인 세션이 있어야 받는 방식으로 남았다. 위 `curl` 확인(Caddy `401` / 서버 `403`)은 76 이후로는 맞지 않는다(둘 다 서버가 답함). 76 적용 확인은 `CHANGELOG.md` (76) 「할 일」

## 빌드·git

### 새로 clone하면 `limbo_description` 빌드 실패 — 2026-10-02
- **증상**: `ament_cmake_symlink_install_directory() can't find '.../limbo_description/rviz'`
- **원인**: CMakeLists가 `rviz/` 폴더를 설치하는데, 폴더 이동 중 빈 폴더 표시 파일이 빠져 git에 폴더가 없었음
- **해결**: `rviz/.gitkeep` 추가 (`5bfb1b6`)
- **확인**: 저장소를 새로 받은 상태로 빌드: 수정 전 실패 → 수정 후 성공

### 브랜치를 바꾼 뒤 빌드·실행이 꼬임 — 2026-10-02
- **증상**: 폴더 구조가 다른 브랜치로 바꾼 뒤 같은 플러그인이 두 패키지에서 잡히거나, 없는 패키지를 찾음
- **원인**: `install/`에 이전 브랜치의 빌드 결과가 남아 있음
- **해결**: 빌드 결과물을 지우고 새로 빌드 (git 추적 대상 아님)
  ```bash
  cd ~/limbo/limbo && rm -rf build install log && build_limbo
  ```

### 브랜치를 바꾸면 `person_detector`가 시작하자마자 죽어 시뮬레이션 시작이 계속 실패 — 2026-10-13
- **증상**: 브랜치를 바꾸고 `build_limbo` 없이 띄우면 `person_detector`가 바로 종료되고 launch가 `process has died`로 실패를 반복
- **원인**: `limbo_interfaces`의 메시지 집합이 브랜치마다 다름(ktj에 `PatrolState` 추가). 파이썬 노드는 심볼릭 링크라 소스가 바로 바뀌지만, 메시지 패키지는 빌드 산출물이라 옛 것이 남아 import가 실패함
- **해결**: 브랜치를 바꾸면 `build_limbo`(최소한 `colcon build --packages-select limbo_interfaces`). 병합 뒤 pull 받는 쪽도 같음 — 변경 기록 "할 일"에 `build_limbo`가 있으면 건너뛰지 말 것
- **확인**: 2026-10-13 재현·해결

### `git stash` 후 `limbo_monitor` 패키지가 없다는 에러 — 2026-10-06
- **원인**: stash로 소스는 치웠는데 빌드 결과물(`install/limbo_monitor`)은 남아 서로 맞지 않았음
- **해결**: `git stash pop` 후 해당 패키지 다시 빌드. 새 패키지가 있는 작업을 stash할 때는 빌드 결과물도 같이 정리해야 함

### 빌드할 때마다 `__pycache__`가 변경으로 잡힘 — 2026-10-02
- **원인**: `.pyc` 파일이 git에 커밋돼 있었음
- **해결**: `.gitignore`에 `__pycache__/`, `*.pyc` 추가, `git rm --cached`로 추적 해제 (`70961e2`)
- **주의**: 기존 `.gitignore` 마지막 줄에 줄바꿈이 없으면 `printf >>`로 추가한 줄이 앞 줄과 붙음 (`venvs/__pycache__/`처럼)

### YOLO venv에서 colcon 빌드가 setuptools 충돌 경고 — 2026-10-02
- **증상**: `colcon-core requires setuptools<80, but you have setuptools 84.0.0`
- **원인**: 최신 pip가 venv에 setuptools 84를 설치함
- **해결**: venv에서 `pip install "setuptools<80"`

---

## 개발 환경(노트북)

### 서브 모니터(HDMI)가 안 잡힘 — 2026-10-02
- **원인**: HP 노트북의 HDMI 포트가 NVIDIA GPU(RTX 4060)에 연결돼 있는데 오픈소스 드라이버(`nouveau`)로 동작 중이었음
- **해결**: `sudo ubuntu-drivers install` (nvidia-driver-595-open) 후 재부팅. Secure Boot가 켜져 있어도 서명된 모듈이라 MOK 등록 불필요
- **확인**: `nvidia-smi`, `xrandr | grep " connected"`에 `HDMI-1-0`

### RustDesk `sudo apt install ./rustdesk-*.deb`가 `Unsupported file` — 2026-10-02
- **원인**: 홈 폴더에 deb 파일이 없어서 `*`가 실제 파일 이름으로 바뀌지 않았음
- **해결**: GitHub 릴리스에서 deb를 받은 뒤 정확한 파일 이름으로 설치

### RustDesk 접속이 `The connection is not allowed` — 2026-10-02
- **원인**: RustDesk 공개 서버가 로그인한 사용자만 접속하게 바뀌었음
- **해결**: 설정 → 계정 → Google/GitHub 로그인 (양쪽 PC 모두)
- **참고**: 학원 자체 서버(`10.10.10.100`)는 내부망 전용이라 `aischool class02` Wi-Fi나 집에서는 닿지 않음

### `mpstat`에 CPU가 90% 놀고 있다고 나옴 — 2026-10-02
- **원인**: 간격 없이 `mpstat`만 실행하면 부팅 후 평균을 보여 줌
- **해결**: `mpstat 2`(2초 간격)로 현재 값을 봄. 프로세스별로는 `top -p $(pgrep -f person_detector | head -1)`. `top`은 코어 1개 = 100%

---

## 리팩터링 이전 (README에 있던 내용)

원작자가 README에 남겨 둔 해결 방법을 옮겼음.

### limbo_perception 빌드·실행 시 YOLO 패키지를 못 찾음
- **원인**: YOLO는 별도 venv(`~/limbo/venvs/limbo_yolo`)에 설치돼 있음
- **해결**: venv를 켠 상태에서 `python -m colcon build --symlink-install`로 빌드 (`build_limbo` alias)

### cv_bridge와 numpy/OpenCV 버전 충돌
- **해결**: venv에서 `numpy==1.26.4`, `opencv-python==4.10.0.84`로 고정

### RAM 8GB 이하 PC에서 첫 빌드 중 멈춤
- **해결**: `MAKEFLAGS="-j2" python -m colcon build --symlink-install --executor sequential`

### LiDAR가 로봇 몸체를 장애물로 봄
- **해결**: `robot_self_filter` 서브모듈로 몸체 점을 걸러 냄 (clone할 때 `--recurse-submodules` 필수)

### MPPI가 낸 회전 명령이 Gazebo에서 잘림 (2026-09-23)
- **원인**: Nav2 쪽 각속도 한계는 1.8인데 Gazebo diff-drive는 0.8로 남아 있었음
- **해결**: Gazebo 한계를 Nav2 값에 맞췄음 (`1628b5a`, 이후 PR #5에서 각가속도 4.0으로 다시 조정됨)
