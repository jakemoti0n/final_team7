# NavFn 최종 진입 방향 자동화 5회 검증

상태: 완료 (2026-10-12)

## 설정과 방법

- 원래 `human_test_world`와 actor 3명, 기존 C/G/J 좌표·YAML yaw를 유지했다. 새로 바꾼 값은 `planner_server.GridBased.use_final_approach_orientation: true` 하나다.
- 5회 모두 `/planner_server`의 실제 값 `Boolean value is: True`를 확인했다. 회차마다 Gazebo·Nav2·순찰·진단·rosbag를 새로 시작하고 종료 후 정리했다.
- `/plan` rosbag의 각 정차 지점 마지막 pose quaternion yaw를 마지막 두 위치의 `atan2(Δy, Δx)`와 비교했다. 실제 정차 자세는 TF `map → base_link`의 도착 직후 시료에서 측정했다.
- 원본은 `/tmp/limbo_navfn_approach_5_runs_20261012/`의 `results.csv`, 회차별 launch/patrol 로그, `diagnostics_XX.csv`, `bag_XX/`, `planner_param_XX.txt`다.

## 결과

**5회 모두 C·G·J에 도착해 전체 순찰을 완료했다.** `Failed to make progress` 0회, 바퀴 헛돎 감지 0회. MPPI `Optimizer fail to compute path` 경고는 회차별 7·41·21·9·17줄, 합계 95줄이었으나 모두 회복했다. 마지막 J 위치 오차는 0.059~0.162 m로 `SimpleGoalChecker`의 0.25 m 이내였다.

| 회차 | 순찰 시간 | C 실제 정차 yaw | G 실제 정차 yaw | J 실제 정차 yaw | J 위치 오차 | optimizer 경고 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 185.2초 | −122.8° | −43.9° | 44.9° | 0.162 m | 7 |
| 2 | 228.5초 | 11.7° | −40.3° | 45.0° | 0.158 m | 41 |
| 3 | 190.9초 | 10.0° | −128.8° | 44.5° | 0.142 m | 21 |
| 4 | 187.7초 | −123.3° | −129.0° | 149.1° | 0.155 m | 9 |
| 5 | 180.1초 | −124.1° | −123.5° | −138.3° | 0.059 m | 17 |

## 자동 방향 계산이 실제로 작동했는가?

작동했다. 각 회차의 C/G/J 마지막 `/plan` yaw는 그 경로의 마지막 두 위치로 계산한 접선 방향과 기록상 0.1° 이내로 일치했다. 따라서 YAML에 남아 있는 고정 yaw가 경로 종단 yaw를 결정하지 않았다. 예를 들어 1회차 J의 마지막 경로 yaw는 **36.4°**였고 YAML의 **−179°**와 달랐다. 4회차 J는 **143.6°**였으며 5회차 J는 **−128.4°**였다.

NavFn 구현은 경로 생성 후 마지막 두 점의 위치 차이로 종단 yaw를 덮어쓴다. 현재 `NavigateThroughPoses` 기본 BT는 주행 중 경로를 반복 계산하고, `FollowPath`는 최신 경로를 받아 목표 방향과 도착 판정에 사용한다. 이에 따라 같은 좌표라도 현재 로봇 위치, costmap, actor가 만든 경로의 마지막 국소 선분에 따라 최종 yaw가 달라진다. 자세한 구현은 [NavFn Jazzy 소스](https://github.com/ros-navigation/navigation2/blob/jazzy/nav2_navfn_planner/src/navfn_planner.cpp)와 [기본 NavigateThroughPoses BT](https://github.com/ros-navigation/navigation2/blob/jazzy/nav2_bt_navigator/behavior_trees/navigate_through_poses_w_replanning_and_recovery.xml)를 참조한다.

## 운용상 의미와 해결 방향

이 옵션은 **계산된 global path의 마지막 선분과 정차 yaw를 일치**시키는 목적에는 맞는다. 그러나 마지막 선분이 로봇이 멀리서 따라오던 복도 방향과 같은 것은 아니다. 목표 근처 경로가 꺾이거나 되돌아가면 자동 yaw도 크게 변한다. 실제로 같은 C에 1회차는 약 −123°, 2·3회차는 약 10~12°로 정차했고, J는 약 45°·149°·−138°로 정차했다. 따라서 카메라 시야나 충전·대면 방향처럼 일정한 정차 방향이 필요한 지점에는 그대로 적용하기 어렵다.

이번 5회 평균 순찰 시간은 194.5초였다. 이전 수동 yaw 10회의 평균 179.1초보다 길었지만 actor 동작과 시작 상태가 회차마다 달라, 5회만으로 이 옵션 자체가 느리다고 확정할 수 없다. 특히 2회차가 228.5초였고 나머지는 180.1~190.9초였다.

- **진입 마지막 선분만 맞추면 되는 운영**: 현재 옵션을 유지하되 정차 방향이 회차마다 달라져도 괜찮은지 확인한다. `patrol_node.py`가 YAML yaw를 필수로 읽으므로 옵션을 켰다고 yaw 항목을 지울 수는 없다.
- **복도에서 들어온 큰 방향을 유지하려는 운영**: 마지막 두 점 대신 목표에서 일정 거리(예: 0.5~1 m) 앞의 경로 접선을 구해 yaw를 정하고, 목표 근처 재계획에 따라 yaw가 뒤집히지 않도록 한 번 정한 방향을 고정하는 별도 로직이 필요하다. 직전 waypoint와 stop 좌표의 각도를 쓰는 기존 수동 설정은 이 경로에서 10/10회 완주했고 정차 방향도 일정했다. [기존 검증](NAV2_YAW_10_RUN_VALIDATION_2026-10-12.md)

5회 완주는 자동 옵션이 **현재 시뮬레이션의 주행 성공을 해치지 않았음**을 보여준다. 모든 actor 배치와 실제 하드웨어에서의 성공이나 일정한 최종 방향을 보장하지는 않는다. 옵션은 사용자의 이번 요청대로 `true`로 유지했다.
