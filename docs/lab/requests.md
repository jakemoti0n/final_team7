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

