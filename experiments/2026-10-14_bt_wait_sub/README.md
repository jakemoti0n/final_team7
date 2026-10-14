# BT "사람이면 기다리기" 분기 (R4, 2026-10-14, 서브 PC) — 막힘

## 왜 했나
막히면 사람 때문이든 상자 때문이든 10초 뒤 복구(회전·후진)로 넘어간다(`KNOWN_ISSUES` 맨 위 3번, 전제 2-2와 어긋남). 복구 분기 앞에 "앞에 사람이 있으면 기다리기"를 넣어 사람 앞에서 회전·후진이 없어지는지 본다. 요청 R4, 지시서 `experiments/orders/2026-10-14_sub_bt_wait.md`.

## 만든 것 (지시서 설계 그대로)
- C++ BT 조건 노드 `IsPersonAhead`(`limbo_navigation/src/is_person_ahead_condition.cpp`): `/person_detector/person_position_base`의 마지막 위치가 영상 시각 기준 `max_age` 1.0 s 안이고 앞 `max_distance` 2.0 m·좌우 `half_width` 0.8 m 안이면 참. 세 값은 XML 포트
- BT XML 사본 2개(`limbo_navigation/behavior_trees/`): Nav2 Jazzy 기본 트리의 `RecoveryFallback`에서 `GoalUpdated` 다음, `RoundRobin` 앞에 `Sequence(IsPersonAhead, Wait 5 s)`
- `nav2_params.yaml` `bt_navigator`: 두 XML을 `$(find-pkg-share limbo_navigation)/...`로, `plugin_lib_names`. **막힘이라 커밋에는 넣지 않았다**(아래 "켜는 법")
- 후진 제거(지시서 3)는 하지 않았다

## 조건
- 커밋 `07f240f` + 위 변경(커밋 전). **노트북의 HumanLayer 치명 비용(변경 기록 (63)) 전 코드**다, 서브 PC (RTX 3070), `ROS_DOMAIN_ID=98`, `GZ_PARTITION=desk`, v14, 전역 STVL 3초
- `experiments/orders/people_one.sh before|wait1|wait2`(한 명 복도 `people2` + 상자 구간 `box`)
- 한 명 복도에서 분기가 안 돌아서 지시서대로 두 명 복도(`aischool_2f_scenarios` 원본) `people2`를 2회(`waitpair`, 진단용 녹화를 붙인 `diagpair`, 제한 200 s)

## 결과

한 명 복도 (2·3행 = 복도 구간):

| 라벨 | 복도 동쪽 s | 복도 서쪽 s | 복구 | 사람 최소 m | 충돌 | 멈춤 사람 앞 / 그 외 s | 조건 노드 발동 |
|---|---|---|---|---|---|---|---|
| before | 32.5 | 34.6 | 0 · 0 | **0.29** · 0.52 | 1 | 3.5 / 1.3 · 0.2 / 4.1 | — |
| wait1 | 30.5 | 34.2 | 0 · 2 | 0.52 · 0.48 | 0 | 0.8 / 1.4 · 1.4 / 4.2 | 0번 |
| wait2 | 32.9 | 39.3 | 0 · 1 | 0.30 · 0.33 | 0 | 3.7 / 1.4 · 2.2 / 5.2 | 0번 |

복구 수는 내부 FollowPath·경로 계획의 costmap 비우기(`-Context`)이고, 바깥 복구 분기(회전·대기·후진)까지 간 적은 세 번 모두 없다. 그래서 wait1·wait2의 차이는 새 분기와 무관하다.

상자 구간 (4구간): before·wait1·wait2 모두 4/4 성공, 상자 최소 0.21~0.33 m, 닿음 0 s, 그 외 멈춤 0.9~3.1 s, 사람 최소 0.47 m 이상. 조건 노드 발동 0번(상자 앞에서 기다리지 않음).

두 명 복도 (분기 발동 확인용):

| 라벨 | 복도 동쪽 | 복도 서쪽 | 사람 최소 | 회전 / 대기(기다림 분기 포함) / 후진 | 조건 노드 "사람 → 기다림" |
|---|---|---|---|---|---|
| waitpair | 성공 64.9 s | 성공 163.3 s | 0.01 m (충돌) | 2 / 2 / 0 | 1번 |
| diagpair | 성공 176.1 s | 200 s 제한 초과 | 0.01 m (충돌) | 3 / 4 / 3 | 1번 |

바깥 복구까지 간 경우 조건 노드는 대부분 "아님 → 복구"였다. 그때 마지막 사람 위치는 **4~13초 전 것**이었다(예: `x=1.15 y=-0.35, 13.5 s 전`).

### 사람 인식이 가까이에서 끊긴다 (`diagpair` 녹화, `person_gap.py`)
정답 위치(월드 SDF 사람 경로 + `/ground_truth/odom`)로 사람이 로봇 앞 2 m·좌우 0.8 m 안에 있던 순간마다, 그 직전 1초 안에 `person_position_base`가 나왔는지 셌다(정답 0.1 s 간격).

| 사람까지 | 순간 수 | 1초 안 인식 | 마지막 인식 나이 중앙값 |
|---|---|---|---|
| 0.0 ~ 0.5 m | 86 | 9 (10%) | 6.5 s |
| 0.5 ~ 1.0 m | 182 | 29 (16%) | 6.2 s |
| 1.0 ~ 1.5 m | 126 | 57 (45%) | 1.9 s |
| 1.5 ~ 2.0 m | 102 | 65 (64%) | 0.2 s |

## 결론
- **막힘.** 로봇이 사람 때문에 막히는 거리(1 m 안)에서는 `person_detector`가 사람을 거의 못 낸다(10~16%). 그래서 조건 노드가 "사람 없음 = 진짜 막힘"으로 보고 회전·후진을 고른다. 조건 노드 설정값(`max_age`, `half_width`) 문제가 아니라 입력 문제다
- `max_age`를 6~13초로 늘리면 발동은 하겠지만 숫자로 맞추는 것이고, 사람이 지나간 뒤 상자에 막혀도 기다리게 된다. 하지 않았다
- 조건 노드·BT XML·플러그인 등록 자체는 동작한다: bt_navigator가 새 트리와 플러그인을 읽고(`ros2 param get`으로 확인), 신선한 사람 위치가 있을 때는 "사람 → 기다림"으로 5초 대기를 골랐다(2회). 상자 구간 성적은 그대로이고 상자 앞에서 기다리지 않았다
- 한 명 복도는 세 번 모두 바깥 복구까지 가지 않아 이 경로로는 분기를 시험할 수 없다
- ReactiveFallback이 매 tick(10 ms) 조건을 다시 물어서 로그가 1초에 100줄 나왔다. 판단이 바뀌거나 1초 지났을 때만 남기게 고쳤다(그 뒤 시뮬레이션은 다시 안 돌림, 컴파일만 확인)
- 두 명 복도에서 기다림 상한(지시서 계산 약 90 s)은 확인하지 못했다. 실제 재시도 한 번은 진전 없음 10 s × 2(내부 FollowPath 재시도) + 복구라서 더 길고, `diagpair` 복도 서쪽은 200 s 안에 실패로 끝나지 않았다

## 켜는 법 (커밋에는 꺼 둠)
`nav2_params.yaml` `bt_navigator`의 기본 트리 주석 세 줄 자리에:
```yaml
    default_nav_to_pose_bt_xml: $(find-pkg-share limbo_navigation)/behavior_trees/limbo_navigate_to_pose_w_replanning_and_recovery.xml
    default_nav_through_poses_bt_xml: $(find-pkg-share limbo_navigation)/behavior_trees/limbo_navigate_through_poses_w_replanning_and_recovery.xml
    plugin_lib_names: ["limbo_is_person_ahead_condition_bt_node"]
```
(Nav2 `navigation_launch.py`가 `allow_substs=True`로 읽어서 `$(find-pkg-share)`가 풀린다)

## 다음 (노트북이 정할 것)
- HumanLayer 치명 비용(63) 뒤에는 한 명 복도에서도 사람 앞에서 멈췄다가 "진전 없음" 복구로 넘어간다고 한다((64)). 그 위에서 다시 돌리면 한 명 복도로도 분기를 시험할 수 있다. 다만 입력 끊김은 그대로일 것이다
- 조건 노드 입력을 가까운 거리에서도 끊기지 않는 것으로: (가) `person_detector` 추적(track)이 사람을 잃은 뒤에도 들고 있는 예측 `/person_detector/predictions`(유지 `track_timeout` 3 s라 중앙값 6 s 끊김을 다 덮지 못할 수 있음), (나) LiDAR 다리 인식(`human-leg`), (다) "최근 N초 안에 앞에서 본 사람 + 그 뒤 로봇이 거의 안 움직임"처럼 기억을 조건 노드 안에 두기. (다)는 숫자로 때우기에 가까워 근거가 필요하다
- 왜 1 m 안에서 끊기는지(카메라 화각에서 잘림, depth 최소 거리, YOLO가 잘린 사람을 못 봄, 시뮬레이션 사람이 로봇을 통과)는 이번에 나누어 보지 않았다
