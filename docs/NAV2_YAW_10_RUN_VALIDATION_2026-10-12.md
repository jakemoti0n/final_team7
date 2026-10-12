# 정차 yaw 수정 후 10회 순찰 검증

상태: 10회 완료 (2026-10-12)

## 조건과 판정

- `human_test_world` 원본 actor 3명과 현재 Nav2 설정 사용. 정차 waypoint의 yaw만 C −124°, G −89°, J −179°로 수정한 상태.
- 회차마다 Gazebo·Nav2·순찰 노드·진단 노드·rosbag를 새로 실행하고 종료 후 정리. ROS 도메인과 Gazebo partition도 분리.
- 순찰 C·G·J 도착과 전체 임무 완료를 성공으로 판정. 시작 단계 오류는 실제 주행 실패와 별도 분류.
- 원본: `/tmp/limbo_yaw_10_runs_20261012/`의 회차별 `launch_XX_attemptN.log`, `patrol_XX.log`, `diagnostics_XX.csv`, `bag_XX/`, `params_XX.txt`. 보정 집계는 `corrected_results.csv`, optimizer 경고 시각별 표는 `optimizer_events.csv`.

## 결과

**10회 중 10회 완주.** 목표 근처 `Failed to make progress`는 0회, 바퀴 헛돎 감지는 0회. J 최종 AMCL/TF 위치 오차는 0.188~0.209 m로 목표 허용값 0.25 m 안이었다. Gazebo 실제 위치 오차도 0.186~0.205 m. 마지막 yaw 오차는 절댓값 0.8~4.9°로 허용값 0.25 rad(약 14.3°) 안이었다. 각 회차의 C·G·J는 순찰 노드에서 모두 도착으로 기록됐다.

아래 최종 거리 값은 자동 요약 스크립트의 끝에서 세 번째 시료가 아니라 **진단 CSV의 마지막 유효 위치 시료**로 다시 계산했다. 자동 `results.csv`의 `goal_distance_m`는 도착 직전 시료라 0.36~0.53 m처럼 크게 보일 수 있다.

| 회차 | 시작 시도 | 주행 시간(s) | 최종 J 거리(m) | 최종 yaw 오차(°) | optimizer 경고 | 진행 실패 | 결과 |
|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 1 | 184.6 | 0.202 | -0.8 | 37 | 0 | PASS |
| 2 | 1 | 180.3 | 0.188 | -1.0 | 20 | 0 | PASS |
| 3 | 1 | 178.9 | 0.191 | -3.2 | 1 | 0 | PASS |
| 4 | 1 | 177.2 | 0.195 | -4.3 | 20 | 0 | PASS |
| 5 | 2 | 173.7 | 0.207 | -3.2 | 14 | 0 | PASS |
| 6 | 1 | 176.4 | 0.191 | -4.9 | 21 | 0 | PASS |
| 7 | 1 | 182.0 | 0.202 | -4.3 | 11 | 0 | PASS |
| 8 | 1 | 172.6 | 0.193 | -4.7 | 8 | 0 | PASS |
| 9 | 1 | 180.8 | 0.205 | -3.7 | 9 | 0 | PASS |
| 10 | 1 | 184.1 | 0.209 | -1.1 | 16 | 0 | PASS |

## 이상 1: MPPI optimizer 경고가 반복됐지만 회복

- 10회 합계 `Optimizer fail to compute path` **157줄**, 시간상 별도 경고 군집 **30개**. 회차별 경고는 1~37줄로 달랐지만 모두 완주했다.
- 각 군집 시작 시각에 가장 가까운 0.5초 진단 시료를 대조했다. **30/30군집**에서 actor 최단 거리 1.0 m 이하(실측 범위 0.059~0.906 m), LiDAR 최근접 0.65 m 이하(0.100~0.598 m)였다. 28/30군집에서는 actor 0.75 m 이하이면서 LiDAR 0.5 m 이하였다. 로봇 위치 local costmap 비용 68 이상은 15/30군집이었다. 모든 주행 시료 3522개 중 actor 1.0 m 이하와 LiDAR 0.65 m 이하가 동시에 나타난 시료는 159개이므로 근접 자체가 매번 optimizer 경고를 만드는 것은 아니다.
- 예: 1회차에는 actor가 로봇 실제 위치 기준 약 0.08 m, LiDAR 약 0.10 m, 로봇 위치 costmap 80인 구간에서 15줄의 경고가 집중됐다. 이후 제어가 회복됐다. 경고는 원본 actor가 센서와 costmap에 매우 가깝게 들어온 상태와 강하게 연관된다.
- 현재 MPPI는 2000개 후보 trajectory를 80×0.05초(4초) 범위에서 평가하고 `CostCritic` 가중치 6, footprint 충돌 검사, collision cost 1,000,000을 사용한다. Nav2 Jazzy 구현에서 `CostCritic`은 모든 후보가 충돌하면 `fail_flag`를 세우고 optimizer는 설정된 재시도 한도를 넘으면 `NoValidControl`과 이 경고 문구를 낸다. 이 경로는 관찰된 actor/센서/costmap 상태와 **일치하는 설명**이다. 후보 trajectory별 충돌 판정·critic 점수를 직접 계측하지 않았으므로 이 157줄 각각의 내부 원인을 확정한 것은 아니다.
- 현재 controller의 `failure_tolerance: 0.3` 설정 아래 이번 10회에서는 Nav2가 경고 뒤 제어를 계속해 임무 실패로 이어지지 않았다. 어떤 회복 단계가 각 경고를 해소했는지는 후보별 계측 없이 단정하지 않는다. 경고를 없애려고 충돌 비용이나 안전 거리를 근거 없이 낮추는 것은 권장하지 않는다. actor가 로봇·LiDAR를 통과하거나 극근접하는 월드의 모델/충돌 및 costmap 입력을 먼저 점검하고, 실제 주행 정지가 재발할 때 경고 직전의 궤적·footprint 판정까지 계측하는 것이 해결 순서다.

## 이상 2: 5회차 첫 시작에서 localization 활성화 실패

- 5회차의 첫 시작에서는 `map_server/change_state` 응답 시간 초과가 먼저 기록됐다. Localization lifecycle manager가 AMCL을 활성화하지 못했고, 이어 global costmap이 `map → base_link` TF를 기다리다 시간 초과되어 planner 서버 활성화가 실패했다. 순찰 명령 전의 문제다.
- `start_simulation.launch.py`는 localization을 시작 후 8초, Nav2를 11초에 **고정 시간으로** 실행한다. Localization 활성 상태를 확인하지 않고 Nav2가 시작되므로, 초기화가 지연되는 회차에 이런 의존성 경합이 발생할 수 있다. 재시도한 두 번째 시작에서는 정상 활성화돼 해당 회차도 완주했다.
- 종료 시 RViz Ogre의 `Vertex Buffer: Out of memory` 오류도 보였다. 이 로그는 map 서버 시간 초과보다 뒤에 나타나므로 첫 실패의 직접 원인으로 단정하지 않는다. 현재 `gui:=false`는 Gazebo 창만 끄며 RViz는 계속 시작한다.
- 해결안: 고정된 8초/11초 지연 대신 map server·AMCL의 active 상태와 필요한 `map → odom → base_link` TF 확인 후 Nav2를 실행하도록 시작 의존성을 연결한다. 반복 시험용으로 RViz 실행을 끌 수 있는 별도 launch 인자를 두면 렌더링 부담을 줄일 수 있다. 이 두 변경은 이번 10회 조건을 유지하기 위해 적용하지 않았다.

## 결론과 범위

정차 yaw를 진입 방향으로 맞춘 현재 경로는 이 월드의 순찰에서 10/10회 완주했고, 이전에 C/G에서 관찰된 목표 근처 정지 실패는 재현되지 않았다. 경고와 시작 재시도는 남아 있으므로 **주행 목표 정지 문제의 개선**과 **actor 근접 시 optimizer 경고·시작 의존성 문제**를 별개로 관리한다. 10회 성공이 모든 actor 위치와 하드웨어 환경에서 무조건 성공함을 뜻하지는 않는다.

관련 원인 통제 실험: [Nav2 목표 근처 정지 원인 조사](NAV2_NEAR_GOAL_FAILURE_2026-10-12.md). Nav2 구현: [CostCritic](https://github.com/ros-navigation/navigation2/blob/jazzy/nav2_mppi_controller/src/critics/cost_critic.cpp), [Optimizer](https://github.com/ros-navigation/navigation2/blob/jazzy/nav2_mppi_controller/src/optimizer.cpp).
