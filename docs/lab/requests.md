# lab 요청 (노트북 → 서브 PC)

**이 파일은 노트북만 쓴다.** 서브 PC는 읽기만 하고, 진행 상황·결과·질문은 [`reports.md`](reports.md)에 쓴다.

- **노트북** (`kim-laptop`, 메인): 실험을 정하고 요청을 적는다
- **서브 PC** (`automaton-desk`, RTX 3070, RAM 16GB): 요청을 받아 돌리고 결과를 적는다

## 규칙 (두 파일 공통)

- **파일 주인**: `requests.md`는 노트북만, `reports.md`는 서브 PC만 쓴다. 상대 파일은 읽기만 한다 (같은 파일을 두 PC가 고치면 커밋이 충돌한다)
- 실험 결과 폴더 `experiments/<날짜>_<주제>/`는 그 실험을 한 PC만 쓴다
- push 전에 항상 `git pull --rebase origin lab`. **`git push --force` 금지** (상대 커밋이 사라진다)
- 실험 묶음(예: 10회 반복) 도중에는 pull하지 않는다. 시작할 때 `git rev-parse --short HEAD`를 결과에 적고, 끝난 뒤 pull한다
- 요청은 `R번호`, 질문은 `Q번호`. 진행 상태(`대기` → `진행` → `완료`/`막힘`)는 서브 PC가 `reports.md`에 적는다
- 결과 원본(CSV·bag)은 저장소 밖 `~/limbo_bags/sim_trials/`, 여기에는 요약과 결론만

---

## 요청

### R6. 안 비켜 주는 사람이 정면으로 오면 복도 한쪽으로 비켜선 뒤 기다리기 (2026-10-14 13:00, 대기 — **R5 끝난 뒤**)

소셜 포스 시나리오에서 폰 보는 사람 정면 조우가 HumanLayer 켬/끔 모두 뚫림(로봇이 복도 가운데서 멈춤). 조건 노드 `IsPersonOncoming`(1.5~4 m 앞, 진로 위, 다가옴) + 액션 `ComputePullOverPose`(costmap으로 비울 쪽 고름) + BT 분기(비켜선 뒤 R5 조건이 거짓이 될 때까지 기다림, 상한 약 20 s). 손님(approach_intent)에는 비켜서지 말고 R5 기다리기.

자세한 지시: [`experiments/orders/2026-10-14_sub_pull_over.md`](../experiments/orders/2026-10-14_sub_pull_over.md). 시험 벤치 `experiments/2026-10-14_social_people/run_scenarios.sh`
- 기준: no_yield 복도 충돌 0·최소 0.5 m 이상, approach·시간표 복도·상자는 전과 같음
- 하지 말 것: 후진, timeout으로 때우기

### R5. ToF 근접 센서(시뮬레이션+노드) + `IsPersonAhead` 입력을 "카메라 기억 + ToF"로 (2026-10-14 11:50 → 노트북 답 13:30, **이어서 진행**)

> **Q2 답 (13:30).** 둘 다 서브 PC 생각대로.
> - **(A) 판단은 "막히기 시작한 순간"에.** 상시 도는 작은 노드(`tof_node`에 붙여도 되고 따로 `person_blocking` 노드여도 됨)가 ToF가 비었다→막힘으로 바뀌는 순간에 "직전 `memory_sec`(5 s) 안에 앞 0.8~3 m에서 다가오던 사람을 봤는가"를 보고 `/person_blocking`(Bool) 참을 내고, ToF가 1 s 이상 비면 거짓. 상한 60 s. 조건 노드는 이 토픽만 본다. 기억 시간은 안 늘림. 판단 로직은 `rclpy` 없는 파일에 두고 pytest(막힘 시작 전 사람 봄 → 참, 사람 없이 막힘(상자) → 거짓, ToF 빔 → 거짓).
> - **(B) `stop_distance`는 물리에서 정한다, 튜닝이 아니라.** 로봇이 서는 자리는 HumanLayer 치명 반경 0.25 m + inflation(로봇 내접 반경 0.25 m까지 253)이라 로봇 앞면이 사람 몸 표면에서 약 0.3~0.4 m(관측 ToF 0.32~0.40 m). 그래서 `stop_distance` = **0.5 m**(관측 최대 0.40 + 여유 0.1). yaml 주석에 이 근거를 적는다. 치명 반경을 바꾸면 같이 바꿔야 하니 두 yaml 주석이 서로를 가리키게. 30 cm 상자 0.485 m가 참이 되지만 카메라 기억이 없으면 `person_blocking`은 거짓이라 괜찮다.
> - 한 명 복도에서 바깥 복구까지 안 가면 분기가 tick 0인 건 정상(멈췄다가 사람이 지나가면 그냥 간다). 시험은 두 명 복도(`aischool_2f_scenarios` 원본 `people2`)와 **소셜 포스 approach 손님**(`experiments/2026-10-14_social_people/run_scenarios.sh`의 `zz_social_approach`, 경로 `hall`: 손님이 0.8 m 앞에 와서 6 s 서 있음)으로. 손님 앞에서 "기다림"이 돌고 회전·후진 0이면 통과.
> - R6은 R5가 풀린 뒤.

R4 Q1의 답: **(다) + ToF**. 실물에 VL53L5CX(8×8, 63°, 4 m) 하나를 범퍼 높이 10 cm 전면 수평으로 달아 젯슨 오린 나노 I2C에 직결하기로 함. 시뮬레이션 센서·노드(`/tof/obstacle_ahead` Bool, `/tof/nearest`)를 만들고, 조건 노드를 "최근 5 s 안 카메라가 0.8~3 m에서 다가오는 사람을 봤음 AND 지금 ToF 0.3 m 안 물체"로 바꿔 한 명 복도·상자 구간으로 시험. 통과하면 켠 채로 커밋.

자세한 지시: [`experiments/orders/2026-10-14_sub_tof_wait.md`](../experiments/orders/2026-10-14_sub_tof_wait.md)
- 준비: pull 후 `build_limbo` 필수. lab에는 HumanLayer 치명 비용(63)이 들어가 R4 때와 달리 한 명 복도에서도 분기가 발동함
- 하지 말 것: 추적 유지 시간·`max_age`·timeout으로 때우기, LiDAR 다리 인식
- 실물 I2C 드라이버는 안 함(하드웨어 오면 노트북)

### R4. BT "사람이면 기다리기" 분기 구현 + 한 명 복도·상자 구간 시험 (2026-10-14 09:50 → 노트북: 결과 받음, 11:50)

> 결과 확인함(막힘). 조건 노드·트리는 잘 만들었고, 입력이 문제라는 판단에 동의. 노트북 측정에서도 1.5 m 안 검출 0 %(카메라 각도 무관). Q1 답은 R5.

`docs/KNOWN_ISSUES.md` 맨 위 3번(막히면 기다리지 않고 복구로 넘어감). 복구 분기 앞에 "사람이 앞에 있으면 Wait" 조건을 넣는 C++ BT 조건 노드 하나와 BT XML 사본 2개. 구현 + 시험 약 반나절.

자세한 지시: [`experiments/orders/2026-10-14_sub_bt_wait.md`](../experiments/orders/2026-10-14_sub_bt_wait.md), 시험 스크립트 `experiments/orders/people_one.sh <라벨>`
- 준비: pull 후 `build_limbo` 필수 (C++)
- 범위: "막혔을 때 사람이면 기다리기"까지. 2-1의 "다가오는 손님 보면 미리 멈추기"는 R5로 따로
- 하지 말 것: `progress_checker` timeout 숫자로 때우기, 후진 복구를 이번 커밋에 섞기(별도 커밋이면 됨)
- 결과는 `experiments/2026-10-14_bt_wait_sub/`와 `reports.md`에

### R3. 전역 costmap STVL 기억 시간 15 → 3초 시험 (2026-10-13 19:10 → 노트북: 결과 받음, 2026-10-14)

> 결과 확인함 (`experiments/2026-10-13_stvl_decay_sub/`). 상자 회피 유지·복도 복구 같음(1회씩) → 같은 성적이면 작은 값 규칙대로 **전역 `voxel_decay` 3초 채택** (10-14). 효과는 전역 경로가 바뀐 횟수를 재는 열을 도구에 넣은 뒤 반복 시험으로 확인한다. **서브 PC는 이 작업에서 해제**, 다음 요청 전까지 대기.

`docs/KNOWN_ISSUES.md` 맨 위 0번(사람 꼬리로 전역 경로 흔들림·복도 복구 반복)의 첫 시험. 3초와 15초로 각각 한 명 복도 + 상자 구간 1회씩, 약 30분.

자세한 지시: [`experiments/orders/2026-10-13_sub_stvl_decay.md`](../experiments/orders/2026-10-13_sub_stvl_decay.md), 실행 스크립트 `experiments/orders/stvl_decay_one.sh`
- 준비: pull 후 **`build_limbo` 필수** (ktj 병합으로 순찰 노드·메시지가 바뀜)
- 결과는 `experiments/2026-10-13_stvl_decay_sub/`와 `reports.md`에. 설정 파일은 바꾼 채로 커밋하지 않음

### R2. 사람 있는 복도 속도 설정 A·B·C 각 1회 (2026-10-13 16:40 → **16:55 범위 축소**)

> **16:55 변경: 복도(`people_side`) 회차는 그만두고 R2-b(충장로 거리 2회차)만 해 주세요.** 노트북에서 목표를 벽 쪽으로 옮겨도 지금 설정부터 복도 4구간 중 2구간밖에 못 지나가서(두 사람 사이를 못 지나감) 속도 설정 비교가 의미 없다고 판단함. 이미 돌린 복도 회차가 있으면 CSV만 `experiments/2026-10-13_people_speed_sub/`에 넣고 요약 한 줄이면 충분. 지시서의 "실행" 절은 건너뛰고 "여유가 있으면 (R2-b)" 절을 본 작업으로.


노트북이 `people_side` 경로로 A·B·C를 2회씩 돌리는 중. 서브 PC가 3회차(조건당 1회)를 맡는다. 여유가 있으면 충장로 거리 200 m 왕복도 조건당 1회 (R2-b).

자세한 지시: [`experiments/orders/2026-10-13_sub_people_side.md`](../experiments/orders/2026-10-13_sub_people_side.md)
(준비 `build_limbo` 필수 — 월드 물리 스텝이 바뀜, 실행 스크립트 `experiments/orders/people_side_one.sh`, 결과는 `experiments/2026-10-13_people_speed_sub/`)

- 조건: A 현재 설정, B `prune_distance` 2.5, C 상한 0.75 + `prune_distance` 3.0. 스크립트가 적용·원복을 다 한다
- 시작 전에 실시간 비율(RTF)을 한 번 재서 보고에 적는다 (두 PC 결과를 같이 볼 때 필요)
- 경로 스크립트가 첫 줄만 찍고 멈추면 그 회차는 버리고 라벨 뒤에 `r`을 붙여 다시 (노트북에서 1번 있었음)
- **추가 (16:35)**: 노트북에서 시뮬레이션이 "ready"를 냈는데 `nav.log`가 비어 있고 10분 넘게 로봇이 출발점에 있는 회차가 있었음. Nav2가 configure 단계에서 멈춘 것(`collision_monitor change_state timeout`). `sim_ctl.sh`를 고쳐 `135851e`에 올렸으니 **회차 사이에 pull 받아도 됨** (도구만 바뀜, 결과엔 영향 없음). pull 안 했으면 그런 회차는 `kill <nav_route PID>`로 끊고 라벨 뒤에 `r`을 붙여 다시

### R1. 학원 2층 순찰 반복 — 목표 앞 정지 재현 (노트북: 결과 받음, 2026-10-12 15:00)

> 결과 확인함 (`experiments/2026-10-12_patrol_repro/`). 목표 앞 정지는 재현 안 됨(10/10), 위쪽 복도 MPPI 머뭇거림 4/9회는 노트북에서 이어서 봄. **서브 PC는 이 작업에서 해제** (다른 작업 예정).

자세한 지시: [`experiments/orders/2026-10-12_home_patrol_repro.md`](../experiments/orders/2026-10-12_home_patrol_repro.md)
(배경, 규칙, 준비, 1단계 사람 있는 상태 10회, 2단계 사람 없는 상태 10회, 결과 남기는 법)

- 도구 `tools/sim_trials/patrol_trial.sh`, `patrol_analyze.py`는 노트북에서 시험함. 1회차(OK, 193초)에서 문제 두 개를 찾아 고쳤음 (아래)
  - Nav2 상태 토픽이 숨김 토픽이라 녹화가 안 돼서, 분석이 "주행 중" 구간을 못 찾고 멈춘 구간을 0개로 냈음 → `--include-hidden-topics` 추가, 상태 토픽이 없으면 분석이 경고를 띄움
  - 녹화가 마무리되지 않아 bag을 못 읽음 → 자동 재색인
  - **이미 진행 중이면 다시 시작하지 않아도 됨** (서브 PC가 14:15에 시작한 것 확인). 성공·실패 기록은 그대로 유효. 수정 전 bag은 `ros2 bag reindex <bag> -s mcap` 후 `git pull`한 `patrol_analyze.py`로 분석하면 상태 토픽 없이 근사로 분석됨 (D 지점 5초 대기도 멈춤으로 나오니 위치로 구분). 다음 회차부터는 `git pull`한 도구로
- 진행 상태는 `reports.md`의 "진행 상태" 표에 적는다 (`진행` → `완료`/`막힘`)

---

## 서브 PC 질문에 대한 답

### Q1. 두 PC 동시 실행 시 ROS 도메인·Gazebo 파티션

> 노트북 답: 그대로 하세요. 서브 PC는 `ROS_DOMAIN_ID=98`, `GZ_PARTITION=desk`. `tools/sim_trials/*.sh`는 환경변수를 그대로 이어받으므로 시험 전에 `export ROS_DOMAIN_ID=98 GZ_PARTITION=desk`만 하면 됨 (지시서 "준비"에도 넣음).

### Q2. 서브 PC 작업 목록 위치

> 노트북 답: 요청은 앞으로 이 작업판 "요청"에 번호로 적고, 긴 지시는 `experiments/orders/`에 따로 두고 링크함. 지금은 R1.

### Q3. CHANGELOG 형식 (사소)

> 노트북 답: 노트북에서 고쳤음. 참고로 (19)는 lab에만 있는 항목이라(순찰 waypoint 선택은 dev 보류 중) dev 변경 기록과 번호가 어긋날 수 있음.

### Q4. `patrol_analyze.py`의 collision monitor 칸

> 노트북 답: 맞는 지적. 구간 시작 직전 마지막 상태를 포함하도록 노트북에서 고쳤음 (`cm_state.py`와 같은 방식).

### Q5. 시뮬레이션 시작 실패 빈도

> 노트북 답: 확인함. 노트북에서도 같은 계열(lifecycle 시간 초과)이 가끔 남. 재시도로 충분해서 당장은 손대지 않고 KNOWN_ISSUES 항목에 빈도(2/10)를 보탬.

