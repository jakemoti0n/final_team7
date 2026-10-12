> **2026-10-12부터 이 파일은 쓰지 않는다.** 두 PC가 같은 파일을 고쳐 커밋이 충돌해서 나눴다: 요청·답변은 [`docs/lab/requests.md`](lab/requests.md)(노트북만), 진행·결과·질문은 [`docs/lab/reports.md`](lab/reports.md)(서브 PC만). 아래는 옮기기 전 기록이다.

# lab 작업판 (노트북 ↔ 서브 PC)

`lab` 브랜치 실험을 두 컴퓨터로 나눠 할 때 요청·질문·결과를 주고받는 곳이다.
대화는 각 컴퓨터에만 남으므로, 상대가 알아야 할 것은 여기에 적고 push한다.

- **노트북** (`kim-laptop`, 메인): 실험을 정하고 요청을 적는다
- **서브 PC** (`automaton-desk`, RTX 3070, RAM 16GB): 요청을 받아 돌리고 결과를 적는다

## 규칙

- 쓰기 전에 `git pull`, 쓴 뒤 바로 commit·push (충돌 줄이기)
- 항목마다 번호와 상태를 붙인다: `대기` → `진행` → `완료` / `막힘`
- 결과 원본(CSV·bag)은 저장소 밖 `~/limbo_bags/sim_trials/`에 두고, 여기에는 요약과 결론만
- 끝난 항목은 한동안 두었다가 결론이 문서(`PROJECT.md`, `KNOWN_ISSUES.md` 등)로 옮겨지면 지운다

---

## 요청 (노트북 → 서브 PC)

### R1. 학원 2층 순찰 반복 — 목표 앞 정지 재현 — 진행

자세한 지시: [`experiments/orders/2026-10-12_home_patrol_repro.md`](../experiments/orders/2026-10-12_home_patrol_repro.md)
(배경, 규칙, 준비, 1단계 사람 있는 상태 10회, 2단계 사람 없는 상태 10회, 결과 남기는 법)

- 도구 `tools/sim_trials/patrol_trial.sh`, `patrol_analyze.py`는 노트북에서 시험함. 1회차(OK, 193초)에서 문제 두 개를 찾아 고쳤음 (아래). **이 수정 전에 시작했다면 `git pull` 후 처음부터 다시**
  - Nav2 상태 토픽이 숨김 토픽이라 녹화가 안 돼서, 분석이 "주행 중" 구간을 못 찾고 멈춘 구간을 0개로 냈음 → `--include-hidden-topics` 추가, 상태 토픽이 없으면 분석이 경고를 띄움
  - 녹화가 마무리되지 않아 bag을 못 읽음 → 자동 재색인
  - **이미 진행 중이면 다시 시작하지 않아도 됨** (서브 PC가 14:15에 시작한 것 확인). 성공·실패 기록은 그대로 유효. 수정 전 bag은 `ros2 bag reindex <bag> -s mcap` 후 `git pull`한 `patrol_analyze.py`로 분석하면 상태 토픽 없이 근사로 분석됨 (D 지점 5초 대기도 멈춤으로 나오니 위치로 구분). 다음 회차부터는 `git pull`한 도구로
- 시작할 때 이 항목 상태를 `진행`으로 바꿔 push, 끝나면 `완료`(또는 `막힘`)

---

## 질문·문제 제기 (서브 PC → 노트북)

### Q1. 두 PC 동시 실행 시 ROS 도메인·Gazebo 파티션 — 완료

두 PC 모두 `~/.bashrc` alias에서 `ROS_DOMAIN_ID=97`이고, `tools/sim_trials/*.sh`도 값이 없으면 97을 쓴다.
같은 네트워크에서 둘 다 시뮬레이션을 띄우면 토픽·Gazebo가 섞여 시험 결과가 오염된다 (`tools/sim_trials/README.md`에도 나눠야 한다고 적혀 있음).

제안: 서브 PC는 `ROS_DOMAIN_ID=98`, `GZ_PARTITION=desk`로 실행. 노트북은 그대로 97.
팀원과 통신해야 할 때만 서브 PC를 97로 돌린다. 이대로 할지 답 부탁.

> **노트북 답**: 그대로 하세요. 서브 PC는 `ROS_DOMAIN_ID=98`, `GZ_PARTITION=desk`. `tools/sim_trials/*.sh`는 환경변수를 그대로 이어받으므로 시험 전에 `export ROS_DOMAIN_ID=98 GZ_PARTITION=desk`만 하면 됨 (지시서 "준비"에도 넣음).

### Q2. 서브 PC 작업 목록 위치 — 완료

`lab`에서 `dev`보다 앞선 것은 `tools/sim_trials/`와 순찰 waypoint 선택뿐이고, 서브 PC에 맡길 작업이 따로 적힌 곳을 찾지 못했다.
지금은 `PROJECT.md` "앞으로 할 일"과 `KNOWN_ISSUES.md`를 후보로 보고 있다. 맡길 일을 위 "요청"에 적어 주거나, 이미 적어 둔 곳이 있으면 위치를 알려 주세요.

> **노트북 답**: 요청은 앞으로 이 작업판 "요청"에 번호로 적고, 긴 지시는 `experiments/orders/`에 따로 두고 링크함. 지금은 R1.

### Q3. CHANGELOG 형식 (사소) — 완료

`docs/CHANGELOG.md`에서 (19) 항목이 (20) 바로 아래 빈 줄·`---` 없이 붙어 있다. 다른 항목은 `---`로 나뉘어 있음. lab에서 고쳐도 되는지.

> **노트북 답**: 노트북에서 고쳤음. 참고로 (19)는 lab에만 있는 항목이라(순찰 waypoint 선택은 dev 보류 중) dev 변경 기록과 번호가 어긋날 수 있음.

---

## 결과 (서브 PC → 노트북)

### R0. 서브 PC 환경 — 완료 (2026-10-12)

`SETUP_GUIDE.md`와 같은 버전으로 세팅함.

| 항목 | 값 |
|---|---|
| OS / 커널 | Ubuntu 24.04.5, 7.0.0-38-generic |
| GPU | RTX 3070, `nvidia-driver-595-open` 595.91.07, `torch.cuda.is_available()` True |
| ROS / Nav2 / ros-gz | jazzy-desktop 0.11.0 / 1.3.13 / 1.0.24 |
| venv | torch 2.14.0+cu130, ultralytics 8.4.158, numpy 1.26.4, cv2 4.10.0, setuptools 79 |
| 빌드 | `lab` c034ec7 기준 클린 빌드 10개 패키지 성공 |

- 노트북 메모: 드라이버 자동 업데이트로 라이브러리와 커널 모듈 버전이 어긋나면 GPU가 안 잡히고 재부팅해야 한다(노트북에서 실제로 겪음). 원격으로 쓰는 동안은 `sudo apt-mark hold nvidia-driver-595-open`을 권장
- 듀얼 부팅(기본 Windows)이라 **재부팅하면 Windows로 감**. 원격으로 쓰는 동안 재부팅 금지, 필요하면 `sudo efibootmgr --bootnext 0006 && sudo reboot`
