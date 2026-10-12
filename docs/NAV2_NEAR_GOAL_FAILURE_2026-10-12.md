# Nav2 목표 근처 정지 원인 조사

상태: 원인 통제 재현, 해결 검증 및 waypoint 적용 완료 (2026-10-12)

## 재현 범위와 판정

- 월드: `human_test_world`, 원래 actor 3명(`person_8`, `person_9`, `person_10`).
- 순찰: `limbo_patrol/config/test_waypoints.yaml`의 C, G 등 정차 지점.
- 같은 방식의 오류: 정차 waypoint의 위치 허용 거리(0.25 m) 바깥에서 로봇의 실제 위치와 AMCL 위치가 거의 변하지 않고, `/cmd_vel_nav`의 전진 명령이 0에 가까운 상태로 `Failed to make progress`가 반복되어 해당 NavigateThroughPoses 목표가 실패한 경우. C와 G는 각각 기록한다.
- `Optimizer fail to compute path`만 발생하고 주행을 완료한 회차는 실패로 세지 않는다. 시작 실패도 세지 않는다.
- 목표: 같은 방식의 오류 5회. 매 회차의 actor, LiDAR, costmap, MPPI 명령, 실제 위치, 목표까지 거리·방향, Nav2 로그를 대조한다.

## 기존 10회 기록에서 확인한 사실

원본: `/tmp/limbo_original_actor_20261012/results.csv`, 회차별 `launch_XX_attempt1.log`, `diagnostics_XX.csv`, `bag_XX/`.

- 10회 중 6회 완주, C에서 3회(2·4·5), G에서 1회(9) 실패.
- C 실패 세 회차에서 `person_10`이 0.43~0.55 m까지 접근할 때 LiDAR 최근접 0.11~0.15 m, 로봇 위치의 local costmap 비용 74~80, MPPI 최적화 오류가 함께 발생했다. actor가 떠난 후 비용이 0이고 주변이 비어도 전진 명령이 거의 0으로 남았다.
- C 실패 종료 시 목표까지 0.31~0.43 m, 목표 방향은 로봇 진행 방향 기준 약 160~171° 뒤쪽. 로봇의 yaw는 목표 yaw(0°)와 약 1° 차이였다.
- G 실패 종료 시 목표까지 약 0.42 m, 목표 방향은 진행 방향 기준 약 100° 옆쪽. actor들은 멀리 있었고 로봇 위치 costmap 비용은 0이었다.
- 바퀴 헛돎 상태는 실패 회차에서도 `false`. AMCL/TF 위치와 Gazebo 실제 위치가 가깝다.
- MPPI 최적화 오류는 완주 회차에도 있었다. 따라서 오류 한 줄만으로 주행 실패 원인이라고 단정할 수 없다.

## 현재 설정과 검증할 가설

- `limbo/src/limbo_navigation/config/nav2_params.yaml`: MPPI `vx_min: 0.0`(후진 샘플 없음), `GoalAngleCritic`과 `PreferForwardCritic` 가중치 5, `GoalCritic` 가중치 5, `PathFollowCritic` 가중치 9.
- 같은 파일: 위치·방향 도착 허용값 각각 0.25 m/rad, `SimpleProgressChecker`는 10초 동안 0.5 m의 위치 변화를 요구한다.
- **가설 A (C)**: actor 근접으로 감속·회피한 뒤 목표를 조금 지나쳐, 목표가 로봇 뒤에 남는다. 후진이 금지되고 목표 yaw는 이미 맞아 있으므로 MPPI가 전진 또는 제자리 회전보다 정지를 낮은 비용으로 평가할 수 있다. 진행 검사기는 이 정지를 반복 실패로 처리한다.
- **가설 B (G)**: actor가 없어도 목표가 차체 옆에 남으면 비슷한 지역 최솟값이 생긴다.
- Nav2 Jazzy MPPI 소스 확인: 목표까지 0.5 m 안에서는 `PreferForwardCritic`이 꺼지고 `GoalAngleCritic`이 켜진다. 1.4 m 안에서는 `PathFollowCritic`이 꺼지고 `GoalCritic`이 켜진다. 따라서 마지막 0.3~0.4 m에서 `PreferForwardCritic` 가중치 자체가 정지의 직접 원인이라는 설명은 틀리다. `vx_min: 0.0`에 따른 후진 금지는 여전히 유효하다. 설치된 `ros-jazzy-nav2-mppi-controller`는 1.3.12.
- Jazzy `CostCritic`은 모든 후보 trajectory가 충돌한다고 판정되면 `fail_flag`를 세운다. optimizer는 현재 설정 `retry_attempt_limit: 1`에 따라 재시도 후에도 유효 후보가 없으면 `Optimizer fail to compute path`를 던진다. actor가 가까울 때의 첫 오류는 이 경로와 일치한다. 단, 각 후보의 충돌 판정 원본은 아직 계측하지 않았다.
- Jazzy `GoalCritic`은 후보 trajectory 4초(`80 × 0.05 s`) 동안의 목표까지 평균 거리 × 가중치 5를 더하고, `GoalAngleCritic`은 같은 시간의 목표 yaw 평균 절대 오차 × 가중치 5를 더한다. 후진 불가(`vx_min: 0.0`) 상태에서 목표가 뒤쪽이고 현재 yaw가 목표 yaw와 같으면, 제자리 정지 후보는 방향 비용 0인 반면 돌아서 접근하는 후보는 큰 방향 비용이 생긴다. 정지가 선택될 수 있는 구체적인 비용 구조다. 실제 후보별 점수 비교는 후속 검증이 필요하다.
- `/cmd_vel_nav` 자체가 0에 가까운지 확인해 MPPI 출력 문제와 collision monitor/velocity smoother의 후단 차단을 구분한다. 경로 끝점·방향과 매 회차 controller 파라미터도 확인한다.

## 진행 기록

| 시각 | 단계 | 결과 |
|---|---|---|
| 2026-10-12 | 기존 10회 데이터 재분석 | 목표가 뒤/옆에 남는 기하와 전진 명령 0을 확인. 가설 수립. |
| 2026-10-12 | Jazzy MPPI 소스 대조 | 근접 목표에서 GoalAngle/Goal 활성, PathFollow/PreferForward 비활성을 확인. |
| 2026-10-12 | 새 반복 실험 시작 | 원래 월드·설정으로 같은 정지 실패 5회까지 실행. `/tmp/limbo_near_goal_20261012/`에 각 회차 자료 수집. |
| 2026-10-12 | 새 실험 1~2회차 | 둘 다 순찰 완료. 목표 근처 정지 실패 0/5. 실제 controller 파라미터 dump와 plan/costmap/속도 명령 bag 확보. |
| 2026-10-12 | MPPI optimizer/CostCritic 소스 대조 | `CostCritic`의 전체 trajectory 충돌 → `fail_flag` → retry 후 `NoValidControl` 경로와 근접 목표 critic 비용식을 확인. |
| 2026-10-12 | 새 실험 1회차 `/plan` 분석 | C·G·J 글로벌 경로의 끝점 좌표와 yaw가 `test_waypoints.yaml`(모두 0°)과 일치. 내부 경로가 임의로 다른 목표 방향을 쓰는 가능성 배제. |
| 2026-10-12 | 새 실험 3회차: G 실패 (1/5) | 첫 progress 실패 때 목표 거리 0.320 m, 상대 방향 −100.1°, `/cmd_vel_nav.linear.x` 0.00012 m/s, actor 최단 6.45 m, 로봇 위치 costmap 0, 헛돎 false. 9회 progress 실패 후 Nav2 목표 실패. |
| 2026-10-12 | 새 실험 4회차 | 순찰 완료. 누적 동일 실패 1/5. |
| 2026-10-12 | 새 실험 5회차 | 순찰 완료. 새 실험 누적 동일 실패 1/5. |
| 2026-10-12 | 전체 순찰 6~7회차 | 둘 다 완주. 8회차 시작 전에 전체 순찰 반복을 안전 종료. 새 실험 7회 중 동일 실패 1회(G). 시작 실패 2건은 통계에서 제외. |
| 2026-10-12 | 통제 재현으로 전환 | 같은 목표 상대 기하(거리 약 0.33 m, 목표 오른쪽 약 100°, yaw 0°)에서 actor 없는 월드를 사용. 같은 정지 오류 5회를 재현한 뒤 목표 yaw만 바꾼 대조 실험 예정. |
| 2026-10-12 | 통제 1회차: yaw 0° 실패 (1/5) | 시작점 약 (0,0,0)에서 목표 (−0.067, −0.320, 0°). actor 0명, 근거리 장애물 없음(최소 스캔 약 7.45 m), `/cmd_vel_nav.linear.x` 거의 0. `Failed to make progress` 반복 후 `TaskResult.FAILED`(174초). |
| 2026-10-12 | 통제 2회차: yaw −102° 성공 | 같은 좌표에서 최종 yaw만 접근 방향으로 변경. 7.3초 만에 `TaskResult.SUCCEEDED`, progress/optimizer 오류 0회. 로봇이 방향을 바꾸고 약 0.105 m 전진해 목표 약 0.24 m, yaw 오차 약 0.028 rad로 도착 허용값을 만족했다. |
| 2026-10-12 | 통제 3~4회차: yaw 0° 실패 (3/5) | 모두 `TaskResult.FAILED`. 각 목표까지 약 0.33 m를 남겼고 진행 실패 14회씩 반복, optimizer 오류 0회, LiDAR 최소 거리 약 7.44 m. |
| 2026-10-12 | 통제 5~6회차: 동일 정지, 판정 보류 | 14회 이상 진행 실패가 반복됐으나 실험 스크립트의 170초 제한이 Nav2 최종 응답보다 먼저 적용되어 `TIMEOUT_CANCEL`/`UNKNOWN`. 엄격한 실패 집계에서 제외. 이후 제한을 260초로 늘려 추가 반복. |
| 2026-10-12 | 통제 7~8회차: yaw 0° 실패 (5/5) | 스크립트 제한을 260초로 늘린 뒤 두 회차 모두 Nav2 자체의 `TaskResult.FAILED`까지 확인. 실패 회차 총 1·3·4·7·8회차. 5·6회차는 동일 정지였지만 제한 시간 취소라 제외. |
| 2026-10-12 | 통제 9~10회차: yaw −102° 성공 (3/3) | 동일 좌표·환경에서 최종 yaw만 바꿔 추가 2회 모두 `TaskResult.SUCCEEDED`. 진행 실패와 optimizer 오류 없음. |
| 2026-10-12 | 원래 actor 월드 전체 순찰 검증 | 설치된 waypoint 복사본에서 정차 yaw만 C −124°, G −89°, J −179°로 임시 설정. C·G·J 모두 도착, 172.6초 완주. 진행 실패 0회, optimizer 오류 5회는 복구하며 통과. 실험 종료 후 임시 설정을 원본으로 복원하고 관련 프로세스 종료 확인. |
| 2026-10-12 | 사용자 승인 후 해결 적용 | `test_waypoints.yaml`의 정차 C/G/J yaw를 검증했던 −124°/−89°/−179°로 변경하고 현재 install 복사본에도 동기화. 통과 지점과 Nav2 MPPI 파라미터는 변경하지 않음. |
| 2026-10-12 | Jazzy 목표 판정 소스 대조 | `SimpleGoalChecker`는 0.25 m 이내 위치와 0.25 rad 이내 방향을 요구한다. `stateful`은 한 목표 안에서 위치 판정을 일단 통과하면 유지하고, 새 행동의 `reset()`은 그 상태를 초기화한다. |

## 통제 실험의 정량 결과

모든 회차는 같은 출발점 약 (0, 0, 0), 같은 목표 좌표 (−0.067, −0.320), actor 0명과 장애물 없는 복도에서 시행했다. 로그와 원본 CSV는 `/tmp/limbo_near_goal_20261012/controlled/`에 있다. 목표 yaw는 아래 표에서만 바꿨다.

| 회차 | 목표 yaw | Nav2 결과 | 종료 시 목표 거리 | 진행 실패 | optimizer 오류 | 최소 LiDAR 거리 |
|---|---:|---|---:|---:|---:|---:|
| 01 | 0° | FAILED | 0.335 m | 14 | 0 | 7.44 m |
| 02 | −102° | SUCCEEDED | 0.243 m | 0 | 0 | 7.35 m |
| 03 | 0° | FAILED | 0.329 m | 14 | 0 | 7.44 m |
| 04 | 0° | FAILED | 0.330 m | 14 | 0 | 7.44 m |
| 05 | 0° | UNKNOWN (실험 제한 취소) | 0.328 m | 14 | 0 | 7.44 m |
| 06 | 0° | UNKNOWN (실험 제한 취소) | 0.330 m | 14 | 0 | 7.44 m |
| 07 | 0° | FAILED | 0.333 m | 14 | 0 | 7.44 m |
| 08 | 0° | FAILED | 0.332 m | 16 | 0 | 7.44 m |
| 09 | −102° | SUCCEEDED | 0.245 m | 0 | 0 | 7.35 m |
| 10 | −102° | SUCCEEDED | 0.241 m | 0 | 0 | 7.38 m |

0° 실패 시 위치는 목표 판정 반경 0.25 m의 바깥에 남고 yaw는 이미 0°에 가깝다. MPPI가 대부분의 제어 주기에서 거의 0인 속도를 내며, 간헐적인 속도는 Nav2 복구 회전 등과 겹친다. 복구 동작 후 같은 정지 조건으로 돌아간다. `Failed to make progress`는 0.5 m/10초 진행 검사에서 발생하며 최종 목표 실패로 이어진다. actor, costmap 장애물, 바퀴 헛돎, optimizer 오류가 없어도 재현된다. 2회차는 목표 yaw만 바꿔 도착 허용 거리 0.25 m와 yaw 허용 오차 0.25 rad를 만족했다.

실제 순찰 파일에서 정차 C·G·J는 모두 yaw 0°다. 직전 waypoint와의 직선 진입 방향은 C 약 −123.6°, G 약 −88.8°, J 약 −178.9°다. 각 지점에서 0°를 유지해야 하는 운용 이유가 있는지에 따라 해결 설정을 결정해야 한다. 이 각도는 직선 방향일 뿐 실제 Nav2 경로의 최종 진입 각과 항상 같지는 않다.

## 원인과 해결 방향

**확인된 직접 원인**: 목표까지 약 0.33 m가 남고 목표가 로봇의 옆/뒤에 있을 때, 정차 목표 yaw 0°는 현재 로봇 yaw와 이미 일치한다. 이 지점에서 현재 MPPI 설정은 후진 샘플을 만들지 않는다(`vx_min: 0`); 0.5 m 안에서는 GoalAngleCritic이 목표 yaw 오차를 벌점으로 계산하고, PathAlign/PathAngle/PreferForward는 비활성, 1.4 m 안에서는 PathFollow가 비활성이다. 목표 쪽으로 회전해 전진하는 궤적은 방향 비용을 늘리며, 현재 상태를 유지하면 방향 비용이 거의 0이다. 기록된 실제 출력은 대부분 0에 가까웠다. 이는 **목표 방향과 현재 controller 설정의 조합이 만든 근접 목표 정지**라는 결론을 지지한다. 개별 trajectory의 critic별 점수는 계측하지 않았으므로 어느 한 critic의 단독 책임이나 정확한 비용 기여도까지 확정한 것은 아니다.

`SimpleGoalChecker`는 XY 0.25 m와 yaw 0.25 rad를 모두 요구하므로 0.33 m에서 도착 처리되지 않는다. `SimpleProgressChecker`의 0.5 m/10초 검사는 이미 발생한 정지를 감지하고 재시도·복구로 넘긴다. 회전/대기 복구 후 동일한 목표 기하가 다시 나타나 최종 실패한다. actor 접근은 C에서 MPPI optimizer 오류를 유발하거나 목표를 지나치는 계기가 될 수 있지만, G와 actor 없는 통제 환경에서도 같은 최종 정지가 발생했다. 바퀴 헛돎과 localization 오차는 이번 재현의 필수 원인이 아니다.

**우선 적용할 해결**: 정차 waypoint의 yaw를 실제 진입 방향 또는 정차 직전 계획 경로의 끝 방향에 맞춘다. 이 경로의 값 C −124°, G −89°, J −179°는 전체 순찰 1회 성공했고 사용자 요청에 따라 소스와 현재 설치본에 적용했다. `patrol_node.py`는 YAML yaw를 **도 단위**로 읽어 radian으로 변환하므로 YAML에 이 각도를 그대로 쓴다. 다른 waypoint 파일을 사용할 때는 그 경로의 진입 방향을 다시 계산해야 한다. 정차 시 0°를 반드시 유지해야 한다면 먼저 접근 방향으로 위치 목표를 완료하고 그 다음 별도 제자리 회전으로 0°를 맞추는 순서를 시험할 수 있다. `GoalAngleCritic` 가중치 축소나 후진 허용은 현재 미검증이고 다른 주행 구간에 영향을 줄 수 있어 운영 설정에 바로 적용하지 않는다. XY 허용 반경을 0.33 m 이상으로 늘리는 방법은 실제로 목표에 못 간 상태를 도착으로 오인하므로 권장하지 않는다.

**검증 범위**: 동일 좌표의 actor 없는 통제 환경에서 yaw 0°는 Nav2 최종 실패 5/5, yaw −102°는 성공 3/3. 원래 actor 월드에서는 정차 yaw만 임시 변경한 전체 순찰 1/1 완주. 원래 순찰의 모든 경로·actor 위치에서 장기 완주율이 보장된다는 뜻은 아니다. 원래 actor 월드의 optimizer 오류는 yaw 변경 후에도 5회 나왔으나 이번 회차에서는 모두 회복했고 진행 실패는 없었다. 따라서 optimizer 경고의 발생과 이 근접 목표 정지의 최종 실패를 구분해야 한다.

참고 소스: [Nav2 Jazzy GoalAngleCritic](https://github.com/ros-navigation/navigation2/blob/jazzy/nav2_mppi_controller/src/critics/goal_angle_critic.cpp), [GoalCritic](https://github.com/ros-navigation/navigation2/blob/jazzy/nav2_mppi_controller/src/critics/goal_critic.cpp), [PreferForwardCritic](https://github.com/ros-navigation/navigation2/blob/jazzy/nav2_mppi_controller/src/critics/prefer_forward_critic.cpp), [PathFollowCritic](https://github.com/ros-navigation/navigation2/blob/jazzy/nav2_mppi_controller/src/critics/path_follow_critic.cpp), [CostCritic](https://github.com/ros-navigation/navigation2/blob/jazzy/nav2_mppi_controller/src/critics/cost_critic.cpp), [Optimizer](https://github.com/ros-navigation/navigation2/blob/jazzy/nav2_mppi_controller/src/optimizer.cpp), [SimpleGoalChecker](https://github.com/ros-navigation/navigation2/blob/jazzy/nav2_controller/plugins/simple_goal_checker.cpp).

실험은 종료했고 시뮬레이션 프로세스를 정리했다. 임시 실험 설정은 당시 원본으로 복원했으며, 이후 사용자 요청으로 동일한 yaw 값을 소스와 현재 설치본에 적용했다.

적용 후 원본 actor 월드에서 10회 전체 순찰을 검증했다. 10/10회 완주하고 목표 근처 진행 실패 0회였다. 상세 결과와 남은 optimizer·시작 단계 이상은 [정차 yaw 수정 후 10회 순찰 검증](NAV2_YAW_10_RUN_VALIDATION_2026-10-12.md)을 참조한다.
