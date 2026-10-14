# 소셜 포스 사람 첫 회차: 비켜 주는 사람 한 명 복도 (2026-10-14, 노트북)

## 왜 했나
시간표(trajectory) actor는 로봇을 비켜 주지도 멈추지도 않아 "사람 있는 주행" 평가가 안 된다(네모 화면: 사람이 0.5~1.0 m/s로 멈춘 로봇에 걸어 들어옴, `../2026-10-14_human_layer_lethal/`). PROJECT 다음 4번. 소셜 포스 사람을 넣고 한 명 복도(`people2`)에서 시간표 사람 회차(`hl1`, HumanLayer 치명 후)와 비교한다.

## 만든 것 (변경 기록 69)
- gz-sim 시스템 플러그인 `limbo::ActorPoseControl`(`limbo_simulation/plugins/actor_pose_control.cpp`): 토픽 `/limbo/actor_poses`(Pose_V)대로 actor의 TrajectoryPose·AnimationTime을 바꾼다. actor는 set_pose 서비스로는 안 움직여서 필요 (해결 기록 참고)
- `scripts/moving_obstacles.py`: 사람 유형 셋 — `yield`(로봇을 사람처럼 피함), `no_yield`(로봇을 안 봄), `approach`(3 m 안이면 다가와 0.8 m에 멈춰 `wait`초 머물다 감). 힘: 목표(τ 0.5 s) + 사람끼리(2.0·exp(−gap/0.3)) + 로봇(3.0·exp(−gap/0.4), yield만) + 벽(지도 거리 변환, 5.0·exp(−gap/0.15)). 사람 위치는 `/sim/people`(PoseArray)·`/sim/people_names`로도 발행
- `nav_recorder`: `/sim/people`이 오면 SDF 시간표 대신 그 위치로 사람 거리를 잰다
- 월드 `aischool_2f_social`(시나리오 월드에서 actor를 다 빼고 플러그인 + 사람 2명) + `aischool_2f_social_movers.json`(위쪽 복도 yield 1명 0.7 m/s, 아래 복도 no_yield 1명)

## 오프라인 점검 (ROS 없이 `Person.step`만)
정지한 로봇 (4, 0) 옆을 (0,0)→(8,0)으로 지나갈 때: yield 최소 거리 0.96 m(돌아감, 18 s), no_yield 0.05 m(뚫음, 12 s). approach는 (3, 1.5) 로봇에 0.8 m까지 와서 3 s 멈춘 뒤 제 목표로.

## 결과 (`people2`, 각 1회, 전역 STVL 3초·HumanLayer 치명)

| | 구간 | 시간 s | 복구 | 사람 최소 m | 충돌 | 사람 앞 멈춤 s | 그 외 멈춤 s |
|---|---|---|---|---|---|---|---|
| 시간표 actor (`hl1`) | 복도→동 | 32.3 | 1 | 0.34 | 0 | 3.3 | 1.4 |
| | 복도→서 | 33.5 | 2 | 0.55 | 0 | 0.4 | 4.0 |
| 소셜 포스 yield (`social1`) | 복도→동 | 33.0 | 0 | 0.81 | 0 | 4.1 | 0.2 |
| | 복도→서 | 34.5 | 0 | 0.89 | 0 | 1.2 | 3.0 |

- "진전 없음" 0번(시간표 때 2번), MPPI `Optimizer fail` 1번(시간표 때 14번)
- YOLO가 플러그인으로 움직이는 actor를 잡는다(person_detector 새 추적 6건), HumanLayer도 그대로 받는다

## 결론
- 비켜 주는 사람이면 1.8 m 복도에서 로봇과 사람이 서로 0.8 m 이상 두고 지나간다. 사람 있는 평가의 기준선이 생겼다
- 소셜 포스 숫자(힘 크기·거리)는 Helbing 모델의 흔한 값에서 시작했고 근거는 "오프라인에서 돌아가는 폭 1 m"뿐이다. 실제 사람이 로봇을 얼마나 떨어져 지나가는지(실물 관찰)로 맞춰야 한다

## 남은 것
- `no_yield`·`approach` 유형을 넣은 시나리오(복도에서 no_yield와 마주침, 홀에서 approach가 다가옴)로 2·3번(HumanLayer·BT 기다리기) 성적 재기
- 사람 여러 명이 서로 피하는지, 벽 힘이 복도 모서리에서 사람을 튕기지 않는지 눈으로 확인(gui)
- 걷는 애니메이션 속도(`animation_x_vel` 2.0)는 눈으로 맞추지 않았음
