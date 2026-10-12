# lab 보고 (서브 PC → 노트북)

**이 파일은 서브 PC만 쓴다.** 노트북은 읽기만 하고, 요청·답변은 [`requests.md`](requests.md)에 쓴다. 규칙은 `requests.md` 맨 위.
(처음 한 번은 노트북이 `LAB_BOARD.md`에서 옮겨 적음, 2026-10-12)

---

## 진행 상태

| 요청 | 상태 | 시작 커밋 | 메모 |
|---|---|---|---|
| R1 학원 2층 순찰 반복 | 진행 | (서브 PC가 적음) | 14:15 시작 |

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

---

## 결과

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
