# lab 보고 (서브 PC → 노트북)

**이 파일은 서브 PC만 쓴다.** 노트북은 읽기만 하고, 요청·답변은 [`requests.md`](requests.md)에 쓴다. 규칙은 `requests.md` 맨 위.
(처음 한 번은 노트북이 `LAB_BOARD.md`에서 옮겨 적음, 2026-10-12)

---

## 진행 상태

| 요청 | 상태 | 시작 커밋 | 메모 |
|---|---|---|---|
| R2 충장로 거리 2회차 (R2-b) + 복도 A3·B3 | 완료 | `781217e` → `06ed9e6` | 16:30~17:25. 충장로 A·B·C 노트북과 1~6초 차이로 재현. 복도는 축소 전 A3·B3만 (2/4씩) |
| R1 학원 2층 순찰 반복 | 완료 | `6372d97` (home1), `6808ade` (home2~10) | 14:15~15:00. 1단계 10/10 OK → 2단계 생략 |

---

## R2 결과 (2026-10-13 17:25, 서브 PC)

자세한 기록: [`experiments/2026-10-13_people_speed_sub/`](../../experiments/2026-10-13_people_speed_sub/README.md)

| 충장로 200 m 왕복 | 가는 길 | 오는 길 | 평균 속도 | 복구 |
|---|---|---|---|---|
| A | 252 s | 246 s | 0.40 / 0.41 m/s | 3 |
| B (`streetB2r`) | 170 s | 175 s | 0.59 / 0.57 m/s | 1 |
| C | 139 s | 145 s | 0.72 / 0.69 m/s | 0 |

- RTF 사실상 1.0 (1.01, 0.78, 1.20, 1.00, 0.99)
- 노트북 1회차와 1~6초 차이 → 재현됨
- B 첫 회차는 `nav_route.py`가 결과를 놓쳐 멈춤(로봇은 100 m 지점 도착) → 끊고 `streetB2r`로 다시
- 복도(축소 전): A3·B3 둘 다 2/4, 위쪽 복도 동쪽 구간 4번 모두 121초 시간 초과
- 참고: 브랜치를 `ktj` ↔ `lab`으로 바꾸면 `limbo_interfaces`(ktj에만 `PatrolState`)를 새로 빌드해야 함. 안 하면 `person_detector`가 시작하자마자 죽어 시뮬레이션 시작이 계속 실패

---

## 질문

### Q1. 두 PC 동시 실행 시 ROS 도메인·Gazebo 파티션 — 답변 있음 (requests.md)

두 PC 모두 `~/.bashrc` alias에서 `ROS_DOMAIN_ID=97`이고, `tools/sim_trials/*.sh`도 값이 없으면 97을 쓴다.
같은 네트워크에서 둘 다 시뮬레이션을 띄우면 토픽·Gazebo가 섞여 시험 결과가 오염된다 (`tools/sim_trials/README.md`에도 나눠야 한다고 적혀 있음).

제안: 서브 PC는 `ROS_DOMAIN_ID=98`, `GZ_PARTITION=desk`로 실행. 노트북은 그대로 97.
팀원과 통신해야 할 때만 서브 PC를 97로 돌린다. 이대로 할지 답 부탁.

### Q2. 서브 PC 작업 목록 위치 — 답변 있음 (requests.md)

`lab`에서 `dev`보다 앞선 것은 `tools/sim_trials/`와 순찰 waypoint 선택뿐이고, 서브 PC에 맡길 작업이 따로 적힌 곳을 찾지 못했다.
지금은 `PROJECT.md` "앞으로 할 일"과 `KNOWN_ISSUES.md`를 후보로 보고 있다. 맡길 일을 위 "요청"에 적어 주거나, 이미 적어 둔 곳이 있으면 위치를 알려 주세요.

### Q3. CHANGELOG 형식 (사소) — 답변 있음 (requests.md)

`docs/CHANGELOG.md`에서 (19) 항목이 (20) 바로 아래 빈 줄·`---` 없이 붙어 있다. 다른 항목은 `---`로 나뉘어 있음. lab에서 고쳐도 되는지.

### Q4. `patrol_analyze.py`의 collision monitor 칸이 거의 항상 "기록 없음" — 대기

`/collision_monitor_state`는 상태가 바뀔 때만 나오는데(회차당 10~20개), 분석은 멈춘 구간 **안**의 메시지만 본다(`patrol_analyze.py` 75행). 그래서 멈춘 동안 collision monitor가 막고 있었어도 "기록 없음"이 나와 원인 후보 1번을 가릴 수 없다.
제안: 구간 시작 직전 마지막 메시지(`bisect_right(ts, s) - 1`)를 포함. R1에서는 `experiments/2026-10-12_patrol_repro/cm_state.py`로 따로 계산했다. 도구는 노트북 담당이라 고치지 않았음. 서브 PC가 고쳐도 되면 알려 주세요.

### Q5. 시뮬레이션 시작 실패 빈도 — 참고

R1 10회 중 2회(home1, home7) Nav2 시작 실패: `Failed to activate global_costmap because transform from base_link to map did not become available before timeout`. `sim_ctl.sh` 재시도로 둘 다 회복. `KNOWN_ISSUES`의 "AMCL이 Configuring에서 멈춤(가끔)"과 증상은 다르지만(이번엔 map→base_link TF 대기 시간 초과) 시작 부하 계열로 보임. 회차 시간이 200초 → 430초로 늘어나는 정도라 반복 시험에는 지장 없음.

---

## 결과

### R1. 학원 2층 순찰 반복 — 완료 (2026-10-12)

자세히: [`experiments/2026-10-12_patrol_repro/`](../../experiments/2026-10-12_patrol_repro/README.md)

- **"목표 34cm 앞 정지 후 실패"는 재현 안 됨. 10/10 OK** (사람 3명). 실패가 없어 2단계(사람 없음)는 지시대로 생략
- **위쪽 복도 (x −3.5~−4.8, y 8.5)에서 3~5초 머뭇거림 9회 중 4회** (home1은 녹화 수정 전이라 제외). 원인 후보 **2번(MPPI)**: MPPI 명령부터 0.01~0.02 m/s, collision monitor 개입 없음, 위치 오차 0.05 m 이하. 매번 직전에 `APPROACH` 감속이 잠깐 켜짐 → 걷는 사람과 만나는 시각으로 추정 (사람 위치는 녹화 안 돼서 미확정). `KNOWN_ISSUES` "위쪽 복도 30초 붙잡힘"과 같은 구간
- 제안: 사람 없는 월드 10회로 머뭇거림이 사라지는지 확인, 녹화에 사람 예측 토픽 추가. 팀원 실패 회차 bag이 있으면 같은 분석 가능

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
