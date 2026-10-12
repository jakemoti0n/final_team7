# 넓은 네모 맵 순찰 반복 — 목표 앞 정지 재현 — 2026-10-12

팀원이 본 "waypoint 34cm 앞에서 멈춘 뒤 주행 실패"는 학원 맵이 아니라 넓은 네모 맵(`human_test_world`)에서 났다고 해서, 학원 맵에서 재현이 안 된 [R1](../2026-10-12_patrol_repro/README.md) 대신 같은 조건으로 다시 했다.

- 실행: 노트북, `lab` `eacafba`, 설정 변경 없음 (dev 기준 + 전역 STVL 15초)
- 월드 `human_test_world`(걷는 사람 10명), 지도 `human_test_map`, waypoint `test_waypoints.yaml`(A~J, 정지 지점 C·G·J, C에서 5초 대기)
- 명령: `WORLD=human_test_world MAP=human_test_map tools/sim_trials/patrol_trial.sh room<k> test_waypoints.yaml`

## 정정 (2026-10-12, 원작자 PR #9 이후)
**아래 "원인"은 틀렸다.** 멈춘 동안 사람이 근처에 있었다는 상관관계만 보고 판단했고, 사람을 뺀 대조 실험을 하지 않았다.
원작자가 사람 없는 빈 복도에서도 같은 정지를 재현했다 (yaw 0° 5/5 실패, 목표 방향만 바꾸면 3/3 성공).
진짜 원인은 **정지 waypoint의 방향(yaw 0°)이 로봇이 이미 향한 방향과 같고, 목표가 로봇 옆·뒤에 남았을 때 후진이 꺼진 MPPI가 돌아서 다가가는 대신 멈추는 것**이다. 사람은 로봇이 목표를 지나치게 만드는 계기였다.
해결: C·G·J yaw를 들어가는 방향으로 (dev `test_waypoints.yaml`). 자세히: [`docs/TROUBLESHOOTING.md`](../../docs/TROUBLESHOOTING.md), [`docs/NAV2_NEAR_GOAL_FAILURE_2026-10-12.md`](../../docs/NAV2_NEAR_GOAL_FAILURE_2026-10-12.md).
아래 대책 후보 2(도착 판정 0.45 m)는 못 간 상태를 도착으로 착각하게 해서 쓰지 않는다 (시험도 중단함).

## 결론 (정정 전 기록)
- **재현됨. 10회 중 3회 실패, 그중 2회가 팀원과 같은 현상** (C 앞 0.3~0.4 m에서 멈춘 뒤 중단)
- **원인: waypoint C가 걷는 사람의 경로 위에 있다.** 한 사람이 C에서 0.2 m 이내를 반복해서 지나가고, 멈춘 동안 목표 1.5 m 안에 사람이 있던 시간이 51~63%
  - 사람이 오면 사람 예측(human_layer)과 장애물 지도가 목표 주변에 cost를 깔고, MPPI가 0.3~0.4 m 앞에서 속도를 0으로 내고 기다린다 (MPPI 출력부터 0, collision monitor 개입 없음, 위치 추정 오차 0.01~0.04 m)
  - 사람이 비키는 틈에 들어가면 성공(room1·7), 그 전에 Nav2가 진전 없음으로 포기하면 실패(room4·10)
  - 사람이 근처에 없던 회차(room6 등)는 바로 도착
- room3 실패는 다른 지점(G로 가는 길, waypoint D 근처 (−5.2, 4.7))이지만 같은 계열: 그 자리도 사람 경로(x ≈ −5) 위라 사람이 로봇 0.26~0.35 m까지 반복해서 지나감. collision monitor 접근 감속도 섞임
- 즉 MPPI 고장이 아니라 **사람이 계속 다니는 자리에 waypoint를 둔 것 + 기다리다 포기하는 시간**의 문제

## 회차별
| 회차 | 결과 | 시간 | C 앞 정지 | 비고 |
|---|---|---|---|---|
| room1 | OK | 287s | 64초 (−1.46, 1.84) | 사람이 C 0.2 m까지, 1.5 m 안 52% |
| room2 | OK | 222s | 없음 | |
| room3 | FAIL | 337s | — | G로 가는 길 (−5.2, 4.7)에서 약 2분. 사람이 로봇 0.26 m까지 |
| room4 | FAIL | 269s | 163초 (−1.34, 1.97) → 중단 | C에서 0.38 m. 사람 1.5 m 안 55~59% |
| room5 | OK | 243s | 없음 | |
| room6 | OK | 243s | 3초 | 근처에 사람 없음 (최소 1.9 m) |
| room7 | OK | 296s | 30초 (−1.35, 1.90) | 사람 1.5 m 안 51% |
| room8 | OK | 225s | 없음 | |
| room9 | OK | 239s | 없음 | |
| room10 | FAIL | 269s | 143초 (−1.39, 1.91~2.04) → 중단 | 사람 1.5 m 안 52~63% |

- 사람 거리 계산: `tools/sim_trials/stall_people.py <bag> human_test_world -1.72 2.03 <구간>` (월드 SDF의 사람 시간표 기준)
- 원본: [`patrol_results.txt`](patrol_results.txt). bag은 노트북 `~/limbo_bags/sim_trials/logs/patrol_room*`

## 대책 후보
1. **정지 waypoint를 사람 경로에서 비켜 두기** (`test_waypoints.yaml`의 C, D): 가장 간단. 실제 순찰 지점도 통로 한가운데는 피하는 게 맞다
2. **도착 판정 범위 0.25 → 0.4 m** (`general_goal_checker.xy_goal_tolerance`): 0.3~0.4 m 앞에서 멈춰도 도착으로 인정. 정지 위치 정확도는 떨어짐
3. **포기 전에 더 기다리기**: 순찰 노드가 목표 근처(예: 0.5 m 안)에서 실패하면 잠깐 기다렸다 다시 보내기. 사람 많은 실제 환경에서 필요한 동작
