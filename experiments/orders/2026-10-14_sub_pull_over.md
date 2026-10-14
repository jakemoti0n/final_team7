# 서브 PC 지시서: 안 비켜 주는 사람이 정면으로 오면 복도 한쪽으로 비켜선 뒤 기다리기 (R6, 2026-10-14) — R5 뒤에

## 배경
소셜 포스 시나리오(`experiments/2026-10-14_social_people/README.md` 2회차): 복도 가운데로 폰 보는 사람(`no_yield`)이 정면으로 오면 로봇은 사람 앞에서 멈추지만 **복도 가운데**에 멈춰 그대로 뚫린다. HumanLayer를 켜도 꺼도 같다(0.02·0.09 m). 치명 비용은 로봇이 사람에게 들어가는 것만 막고, 미리 옆으로 비켜서는 행동은 못 만든다.
전제 2-2(막히면 기다리기)를 복도에서 지키려면 **먼저 한쪽으로 비켜선 뒤** 기다려야 한다. 실제 사람은 멈춘 로봇을 보면 돌아가겠지만, 복도 가운데를 막고 서는 로봇은 어차피 민폐다.

R5(ToF + 카메라 기억 기다리기)가 끝난 뒤에 한다. R5의 `IsPersonAhead`·ToF 노드를 그대로 쓴다.

## 설계 (이대로 하되, 더 나은 이유가 있으면 reports.md에 적고 바꿔도 됨)

### 1. 조건 노드 `IsPersonOncoming` (C++, `limbo_navigation`)
- 입력: `/person_detector/predictions`(base_link로 변환하거나 odom에서 로봇 pose로 계산). 사람이 앞 `min_distance` 1.5 ~ `max_distance` 4.0 m, 옆 `half_width` 0.6 m 안(로봇 진로 위), 그리고 **다가오는 중**(로봇 기준 상대 속도의 x 성분 < −`closing_speed` 0.3 m/s, 또는 `/person_detector/approach_intent`)이면 참. 1.5 m 밖을 쓰는 이유: 카메라가 1.5 m 안은 못 잡고 2.5~4 m에서 잘 잡는다(`experiments/2026-10-14_camera_angle/`)
- 이미 옆으로 치우친 사람(|y| > half_width)은 거짓 — 그냥 지나가면 된다(HumanLayer 몫)
- 포트: 위 숫자 전부. 한 번 참이면 `hold_sec`(2 s) 유지(깜빡임 방지)

### 2. 동작 노드 `ComputePullOverPose` (C++ BT 액션)
- local costmap을 읽어 로봇 좌·우 `side_offset`(0.5 m) 지점 중 비용이 낮은 쪽을 고르고, 그 지점(map 기준, 현재 yaw 유지)을 블랙보드 `{pull_over_pose}`로 낸다. 둘 다 치명이면 실패(→ 그냥 멈춰 기다리기로)
- 복도 폭 1.8 m, 로봇 폭 0.59 m: 가운데서 0.5 m 옆이면 몸 가장자리가 벽에서 약 0.3 m. inflation 0.45 안이라 비용은 있지만 치명은 아님. 사람이 가운데로 지나가면 로봇 중심과 0.5 m… 사람 몸 반경 0.25 + 로봇 반폭 0.295 = 0.545라 **빠듯하다**. `side_offset`을 0.55~0.6으로 올려 보고 벽 쪽 치명에 안 걸리는 값을 reports.md에 적는다

### 3. BT 분기 (R4의 트리 사본 2개에 추가)
NavigateWithReplanning 앞에 `ReactiveFallback`으로:
```xml
<ReactiveFallback name="PullOverIfOncoming">
  <Inverter><IsPersonOncoming .../></Inverter>
  <Sequence name="PullOverAndWait">
    <ComputePullOverPose side_offset="0.55" pose="{pull_over_pose}"/>
    <ComputePathToPose goal="{pull_over_pose}" path="{pull_over_path}" planner_id="GridBased"/>
    <FollowPath path="{pull_over_path}" controller_id="FollowPath"/>
    <!-- 사람이 지나갈 때까지. 상한은 수십 초: 지나면 원래 경로로 (전제 2-2) -->
    <RetryUntilSuccessful num_attempts="20">
      <Sequence><Inverter><IsPersonAhead .../></Inverter><Wait wait_duration="1.0"/></Sequence>
    </RetryUntilSuccessful>
  </Sequence>
</ReactiveFallback>
```
- 비켜선 뒤 "지나갔다"는 R5의 조건(카메라 기억 + ToF)이 거짓이 되는 것으로 본다. 사람이 안 지나가고 계속 서 있으면 상한(약 20 s) 뒤 원래 경로를 다시 간다
- **하지 말 것**: 후진(2-3), timeout 숫자로 때우기, 사람 속도 추정을 믿을 수 없을 때 억지로 참으로 만들기(그럴 땐 거짓 = 기존 동작)

## 준비
```bash
cd ~/limbo && git pull --rebase origin lab && git rev-parse --short HEAD
build_limbo
export ROS_DOMAIN_ID=98 GZ_PARTITION=desk
```

## 시험
```bash
experiments/2026-10-14_social_people/run_scenarios.sh r6     # 켬/끔 × no_yield·approach (켬이 본 시험, 끔은 대조)
experiments/orders/people_one.sh r6                           # 시간표 한 명 복도 + 상자 (성적 유지 확인)
```
- 바꾸기 전 기준: `experiments/2026-10-14_social_people/trial_hl_on_*.csv` (no_yield 0.02 m 충돌, approach 0.56~0.72 m)
- 어떤 분기가 돌았는지: `grep -E "PullOver|IsPersonOncoming|WaitForPerson" ~/limbo_bags/sim_trials/logs/sim_r6_*_single.log`

## 받아들이는 기준
| 시나리오 | 기대 | 깨지면 |
|---|---|---|
| no_yield 복도 (`people2`) | `person_collision` 0, 사람 최소 **0.5 m 이상**, 로봇이 비켜선 뒤 기다렸다 재출발(시간 +20 s 안), 회전·후진 0 | 비켜서다 벽 치명에 걸리면 `side_offset` 조정. 조건이 안 켜지면 2.5~4 m에서 사람 속도 추정 확인 |
| approach 홀 (`hall`) | 전과 같음(충돌 0). 손님은 정면으로 와도 비켜서지 말고 멈춰 기다려야 함(R5) — `IsPersonOncoming`이 손님에도 참이 되면 안 됨 → 구분: 손님은 `approach_intent`가 참이고 1.5 m 안에서 멈춤. 손님이면 비켜서기 대신 R5 기다리기 | 손님 앞에서 비켜서면 조건 분리 |
| 시간표 한 명 복도·상자 | 전과 같음(복구·충돌·상자 닿음) | 상자 앞에서 비켜서면 사람 판정 입력 확인 |

## 결과 남기기
- `experiments/<날짜>_pull_over_sub/README.md` + CSV, `docs/lab/reports.md` R6, 변경 기록. 코드 커밋은 "왜" 한 줄. `git pull --rebase origin lab && git push origin lab`, **dev/ktj 금지**
