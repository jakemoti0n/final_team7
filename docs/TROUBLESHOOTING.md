# 문제 해결 기록

겪었던 문제와 원인, 해결 방법을 남긴다. 같은 증상이 다시 나오면 여기부터 찾는다.
아직 해결하지 못한 문제는 `KNOWN_ISSUES.md`에 있고, 해결되면 이 문서로 옮긴다.

형식: **증상 → 원인 → 해결 → 확인** (커밋이 있으면 함께 적음)

목차
- [주행·위치 추정](#주행위치-추정)
- [시뮬레이션](#시뮬레이션)
- [인지(person_detector)](#인지person_detector)
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
