# 서브 PC 지시서: BT "사람이면 기다리기" 분기 (R4, 2026-10-14)

## 무엇을 만드나
`docs/KNOWN_ISSUES.md` 맨 위 "지금 주행을 막는 것" **3번**, `docs/PROJECT.md` 8절 다음 3번.
지금은 로봇이 10초 동안 0.5 m를 못 가면(`progress_checker`) 경로를 버리고 복구(costmap 비우기 → 제자리 회전 → 5초 대기 → 후진)로 넘어간다. 사람 때문에 막힌 것도 상자에 막힌 것과 똑같이 다룬다. 전제 2-2(`PROJECT.md`): **사람 때문에 막혔으면 기다리고, 진짜 막혔을 때만 지금처럼 복구한다.** 구분은 behavior tree 조건 노드에서 `person_detector`가 내는 사람 위치로 한다.

이번 범위는 "막혔을 때 사람이 앞에 있으면 기다리기"까지다. 2-1의 "다가오는 손님을 보면 막히기 전에 멈추기"는 다음 요청(R5)이다. 같이 하지 않는다.

## 설계 (이대로 하되, 더 나은 이유가 있으면 reports.md에 적고 바꿔도 됨)

### 1. BT 조건 노드 `IsPersonAhead` (C++, `limbo_navigation`)
- 입력: `/person_detector/person_position_base` (`geometry_msgs/PointStamped`, base_link 기준 가장 가까운 사람, `person_detector.py` 36행). 이 토픽이 0.5 m 안에서도 안정적으로 나오는지 먼저 `ros2 topic hz`로 확인
- 참: 최근 `max_age`(1.0 s) 안에 받은 사람이 앞쪽(`x > 0`)이고 `x < max_distance`(2.0 m), `|y| < half_width`(0.8 m). 세 값은 BT XML 포트로 받는다(코드에 박지 않음)
- 거짓: 그 밖. 사람을 못 봤으면 거짓(= 진짜 막힘으로 보고 복구)
- 본보기: `/opt/ros/jazzy/include/nav2_behavior_tree/plugins/condition/is_battery_low_condition.hpp` (토픽 구독하는 ConditionNode, 콜백 그룹 + executor를 tick에서 돌리는 방식). 같은 구조로 `include/limbo_navigation/is_person_ahead_condition.hpp`, `src/is_person_ahead_condition.cpp`
- 등록: `BT_REGISTER_NODES` 매크로, `CMakeLists.txt`에 `find_package(nav2_behavior_tree behaviortree_cpp)`, `add_library(limbo_is_person_ahead_condition_bt_node SHARED ...)`, install. `nav2_params.yaml` `bt_navigator.plugin_lib_names: ["limbo_is_person_ahead_condition_bt_node"]`

### 2. BT XML 사본 2개 (`limbo_navigation/behavior_trees/`)
Nav2 기본 트리 `/opt/ros/jazzy/share/nav2_bt_navigator/behavior_trees/navigate_to_pose_w_replanning_and_recovery.xml`와 `navigate_through_poses_w_replanning_and_recovery.xml`을 복사해(순찰은 through_poses, 시험 도구 `nav_route.py`는 to_pose를 쓴다) 복구 쪽만 바꾼다:
```xml
<ReactiveFallback name="RecoveryFallback">
  <GoalUpdated/>
  <!-- 사람이 앞에 있으면 복구 대신 기다린다. 기다린 뒤 RecoveryNode가 다시 경로 추종을 시도한다 -->
  <Sequence name="WaitForPerson">
    <IsPersonAhead topic="/person_detector/person_position_base" max_distance="2.0" half_width="0.8" max_age="1.0"/>
    <Wait wait_duration="5.0"/>
  </Sequence>
  <RoundRobin name="RecoveryActions">
    ... 기존 그대로 (ClearingActions, Spin, Wait, BackUp) ...
  </RoundRobin>
</ReactiveFallback>
```
- 기다림 상한: `RecoveryNode number_of_retries`가 6이라 최대 6 × (10 s 진전 없음 + 5 s 대기) ≈ 90 s 뒤 Goal 실패. 전제 2-2의 "상한 수십 초, 지나면 우회"에 맞는다. 숫자를 바꾸고 싶으면 이유를 적는다. **`progress_checker.movement_time_allowance`는 건드리지 않는다**(전제 2-2 "하지 말 것")
- `nav2_params.yaml` `bt_navigator`에 `default_nav_to_pose_bt_xml`, `default_nav_through_poses_bt_xml`을 설치 경로로 넣는다(launch에서 `get_package_share_directory` 조합이 안 되면 yaml에 절대 경로 대신 launch에서 RewrittenYaml로)
- 설치: `CMakeLists.txt` `install(DIRECTORY behavior_trees ...)`

### 3. (선택, 별도 커밋) BackUp 제거
전제 2-3 "후진 금지". 같은 XML이니 `<BackUp .../>` 줄을 빼는 건 이번에 해도 된다. **별도 커밋**으로, 변경 기록에 따로 적는다. 뺀 뒤 상자 구간 성적이 유지되는지 같이 본다.

## 준비
```bash
cd ~/limbo && git pull --rebase origin lab && git rev-parse --short HEAD
build_limbo                       # C++ 플러그인
export ROS_DOMAIN_ID=98 GZ_PARTITION=desk
```
- `tools/sim_trials/sim_ctl.sh`의 Nav2 준비 검사가 10-14에 고쳐졌다(`inactive`도 통과시키던 버그). pull 뒤 쓰면 된다
- 전역 STVL 기억은 3초로 바뀌어 있다(10-14 채택). 그대로 둔다

## 시험 (바꾸기 전 1회, 바꾼 뒤 2회)
```bash
cd ~/limbo
experiments/orders/people_one.sh before     # 바꾸기 전 (지금 코드). 한 명 복도 + 상자 구간
# ... 구현 ...
experiments/orders/people_one.sh wait1
experiments/orders/people_one.sh wait2
```
- 결과 CSV: `~/limbo_bags/sim_trials/logs/trial_<라벨>_single.csv`, `trial_<라벨>_box.csv`. 10-14부터 열이 늘었다: `person_collision`(0.3 m 미만 = 충돌), `stopped_near_person_s`(사람 1.5 m 안에서 멈춘 시간), `stopped_other_s`(그 밖), `plan_changes`
- 어떤 복구가 돌았는지는 시뮬 로그로: `grep -E "behavior_server\]: (Running|Attempting)|bt_navigator" ~/limbo_bags/sim_trials/logs/sim_<라벨>_single.log`
- 기다림이 실제로 발동했는지: 로그에 `WaitForPerson`/`Wait` 뒤 `FollowPath`가 다시 시작하는지. 한 명 복도에서 한 번도 안 막히면(복구 0) 분기가 안 돌아 시험이 안 된다 → 그때는 `aischool_2f_scenarios` 원본(두 명 나란히)으로 `people2`를 1회 더 돌려 발동을 본다(통과는 못 해도 됨, 발동과 기다림 상한만 본다)

## 받아들이는 기준
| 경로 | 기대 | 깨지면 |
|---|---|---|
| 한 명 복도 (`people2`) | 사람 앞에서 회전·후진 **0번**, `person_collision` 0, 구간 시간이 전보다 크게 늘지 않음(+10 s 안) | 회전·후진이 남으면 조건 노드가 거짓을 낸 것 → 토픽 주기·`max_age`·`half_width` 확인 |
| 상자 구간 (`box`) | 전과 같은 성적(4/4, 닿음 0, 복구 횟수 비슷). **상자 앞에서 기다리면 안 됨**(`stopped_other_s`가 전보다 10 s 넘게 늘면 안 됨) | 상자 앞에서 기다리면 사람을 잘못 본 것 → 조건 노드 입력 확인 |

## 결과 남기기
- `experiments/2026-10-14_bt_wait_sub/README.md`: 왜·조건·표(라벨별 구간 시간·복구·사람 최소·충돌·멈춤 사람 앞/그 외·상자 최소·닿음)·결론·남은 것. CSV 사본 포함(작음)
- `docs/lab/reports.md`: R4 진행 → 완료, 표 요약, 질문
- 변경 기록 항목(번호 = pull 뒤 맨 위 + 1), "했음" 체. 코드 커밋은 "왜" 한 줄
- 안 되는 게 있으면 억지로 숫자(timeout)로 맞추지 말고 `막힘`으로 보고 멈춘다
- `git pull --rebase origin lab && git push origin lab`. **dev/ktj에 push 금지**
