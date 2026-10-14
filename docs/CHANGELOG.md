# 변경 기록

2026-10-02 리팩터링을 기준으로 나눈다.
- **리팩터링 이후**: ktj 작업. dev에 push할 때마다 맨 위에 추가한다. pull 받은 뒤 해야 할 일은 "할 일"에 적는다.
- **리팩터링 이전**: 원작자 작업. git 히스토리로 정리해 둔 기록이며 더 이상 추가하지 않는다.

---

# 리팩터링 이후 (2026-10-02 ~, ktj 작업)

> 번호는 push 순서다. 2026-10-13에 lab과 ktj를 합치면서 ktj 쪽 (22)~(30) 뒤에 lab 쪽을 (31)부터 이어 붙였다.

## 2026-10-14 (59) `nav_recorder` 지표 분리: 사람 충돌, 멈춘 시간(사람 앞 / 그 외), 전역 경로 변경 횟수

**할 일**
- pull 후 `build_limbo` 불필요(파이썬·yaml, 심볼릭 링크 설치). 새 CSV부터 열이 늘어남
- 한 명 복도(`people2`)에서 `record:=true`로 돌려 새 열 값이 눈으로 본 것과 맞는지 확인 (아직 안 함)

**변경**
- `limbo_evaluation/goal_metrics.py`: `person_collision`/`person_collision_time_s`(사람 중심과 0.3 m 미만 = 충돌. 시뮬레이션 사람은 충돌이 없어 뚫고 지나가도 SUCCEEDED가 되므로), `stopped_time_s`/`stopped_near_person_s`/`stopped_other_s`(0.05 m/s 미만으로 멈춘 시간을 사람 1.5 m 안/밖으로 나눔 — 전제 2-1·2-2에서 "사람 앞 멈춤"은 서비스, 그 밖은 낭비), `plan_updates`/`plan_changes`(전역 경로가 직전에서 0.3 m 넘게 벗어난 횟수. 0.2 m 간격으로 점을 골라 비교). 기존 열은 그대로
- `nav_recorder.py`: `/plan` 구독, 파라미터 5개(`collision_distance`, `near_person_distance`, `stop_speed`, `plan_change_distance`, `plan_topic`). 끝날 때 로그에 충돌·멈춤·경로 변경을 같이 찍음
- `config/nav_recorder.yaml`: 위 값과 이유. `README.md` CSV 열 표에 3행
- `test/test_logic.py`: 충돌·멈춤 분리, 경로 점 간격 추출, 경로 벗어남, 경로 변경 횟수 테스트 5개 (18개 통과)
- `docs/KNOWN_ISSUES.md` 1번, `docs/PROJECT.md` 8절 1번: 넣었음·시뮬레이션 확인 남음으로

**확인**
- pytest 18개·ament flake8·pep257 통과. 노드를 시뮬레이션 없이 yaml로 띄워 파라미터가 읽히는 것까지 봤음. 실제 주행에서 값 확인은 아직

## 2026-10-14 (58) ktj 점검 3: 학원 2층 시연 순찰 완주 확인 (전역 STVL 3초로 첫 완주)

**할 일**
- 없음. ktj 점검 1(문서)·2(네모 화면)·3(학원 2층)이 끝남. 관제 일시정지·재개 확인은 학원 PC 몫

**변경**
- `tools/demo_patrol.sh`: 주석 한 줄. 백그라운드로 띄우면 launch가 SIGINT를 무시해 Ctrl+C 방식으로는 안 내려가니 `kill -TERM`으로

**확인**
- `tools/demo_patrol.sh` 기본값(`aischool_2f`, `aischool_waypoints.yaml`)으로 1회: "Patrol mission completed". A→B→C→D 82 s, D 5초 정지, E→F→G 69 s, 복구 0. 띄운 뒤 준비까지 약 2분
- 위쪽 복도에서 전역 계획기가 한 번 계획 실패를 냈지만 다음 주기에 다시 계획해 통과. 복구 동작 없음
- 시연 스크립트는 `record`를 켜지 않아 nav_recorder 수치(사람 거리 등)는 없음. 시연 용도라 그대로 둠

## 2026-10-14 (57) 전역 costmap STVL 기억 15 → 3초 채택

**할 일**
- pull 후 `build_limbo` (설정 파일이 바뀜). 학원 PC: ktj 반영 후보 — `nav2_params.yaml` 전역 costmap `stvl_layer.voxel_decay` 한 줄

**변경**
- `limbo_navigation/config/nav2_params.yaml`: 전역 costmap `voxel_decay` 15.0 → 3.0. 서브 PC R3(55)에서 3초도 상자 회피를 유지했고(최소 0.24 m, 닿음 0) 복도 복구가 15초와 같아, "같은 성적이면 작은 값" 규칙대로 작은 쪽을 택함. 걷는 사람(0.7 m/s)이 전역 costmap에 남기는 꼬리가 10 m → 2 m
- `docs/KNOWN_ISSUES.md` 0번 행, `docs/PROJECT.md` 8절 0번·결정 이력, `docs/TROUBLESHOOTING.md`, `docs/lab/requests.md` R3: 채택으로 고침. 남은 일은 효과 확인(전역 경로 바뀐 횟수 열 → 복도 3회 반복)
- `experiments/orders/stvl_decay_one.sh`: 기존 값이 15.0이 아니어도 바꾸게 정규식 수정

**확인**
- 설정 파일 diff가 한 값(+주석)뿐인지 봤음. 주행 재확인은 안 했음(R3가 같은 값으로 돌린 결과가 근거)

## 2026-10-14 (56) ktj 점검: 네모 화면 순찰 완주 확인, R3 판단(전역 STVL 3초는 후보로 두고 설정은 그대로)

**할 일**
- 학원 PC: ktj에서 네모 화면(`human_test_world`) 순찰은 그대로 쓰면 됨. 사람 최소 거리 수치는 KNOWN_ISSUES 1·2번 근거로만 봄

**변경**
- `docs/KNOWN_ISSUES.md`: 복도 행 근거에 네모 화면 결과 추가, 전역 STVL 행에 R3 결과(3초·15초 성적 같음, 상자 회피 유지) 추가
- `docs/PROJECT.md` 8절 0번: R3가 끝났으니 다음 단계(복도 3회 반복 또는 전역 경로 바뀐 횟수 측정)로 고침
- `docs/lab/requests.md` R3: 결과 받음. 전역 `voxel_decay`는 아직 15초 그대로 둠 — 1회씩이라 복구·경로 흔들림 차이를 말할 수 없고, 작은 값(3초)을 채택하려면 경로 바뀐 횟수를 같이 잰 뒤에 함

**확인**
- 노트북에서 ktj 병합 뒤 lab 코드로 네모 화면(`human_test_world`, 사람 10명) 기본 순찰(`test_waypoints.yaml`) 1회: C·G·J 도착, "Patrol mission completed", 5구간 모두 성공, 19~42 s, 0.34~0.39 m/s, 복구 0. Gazebo 모델 목록에 `limbo` 있음(spawn 정상)
- 다만 5구간 중 4구간에서 사람 최소 거리 0.01~0.07 m(0.5 m 안 0.9~6.0 s). 사람이 충돌 없이 통과되는 시뮬레이션이라 "성공"에 뚫고 간 것이 섞여 있음 — KNOWN_ISSUES 1·2번과 같은 현상, 새 문제 아님

## 2026-10-13 (55) 서브 PC R3 결과: 전역 STVL 기억 3초도 상자 회피 유지, 복도 복구는 15초와 같음

**할 일**
- 없음

**변경**
- `experiments/2026-10-13_stvl_decay_sub/`: 3초·15초 각 1회. 상자 4/4 회피·닿음 0으로 둘 다 유지, 복도 복구 합 4 대 4로 차이 없음. 둘 다 복도 한 구간에서 사람 0.3 m 미만(충돌로 셈). 성적이 같아 작은 쪽(3초)이 후보, 채택은 노트북이 정함
- `docs/lab/reports.md`: R3 진행 → 완료와 결과 표

**확인**
- 학원 2층 시나리오(한 명 복도, 상자 구간)를 서브 PC에서 3초·15초 연달아 돌리고 `nav_recorder` CSV로 봤음. 설정 파일은 원복 확인(`git status` 깨끗)

## 2026-10-13 (54) 서브 PC 요청 R3: 전역 STVL 기억 15 → 3초 시험

**할 일**
- 서브 PC: 지시서대로 pull → `build_limbo` → 실행

**변경**
- `docs/lab/requests.md` R3, `experiments/orders/2026-10-13_sub_stvl_decay.md`, `experiments/orders/stvl_decay_one.sh`: 전역 `voxel_decay`를 인자로 바꿔 한 명 복도(`people2`)와 상자 구간(`box`)을 1회씩 돌리고 설정을 원복하는 스크립트. 3초·15초를 같은 날 같은 PC에서 비교하도록 둘 다 돌림

## 2026-10-13 (53) 문서 점검: 부작용이 묻히지 않게 알려진 문제·PROJECT·변경 기록을 손봄

**할 일**
- `docs/KNOWN_ISSUES.md` 맨 위 "지금 주행을 막는 것" 4개를 읽고 시작한다

**변경**
- 같은 문제(전역 STVL 15초가 남기는 사람 꼬리)로 두 번 막힌 원인을 찾아보니, 10-12에 부작용을 해결 기록의 "대가"와 알려진 문제에만 적고 할 일에 올리지 않았고, 기억 5초·15초가 같은 성적인데 15초를 택한 근거가 없었음
- `docs/KNOWN_ISSUES.md`: 맨 위에 "지금 주행을 막는 것" 4개와 PROJECT.md 다음 번호를 둠. 전역 STVL 행을 원인·이력·대책(A/B/C)까지 다시 씀. 끝난 행 2개 삭제(10-02 위쪽 복도 30초 붙잡힘, 옛 rosbag)
- `docs/PROJECT.md`: 4절에 "부작용·임시 조치는 알려진 문제와 다음 할 일 두 곳에, 같은 성적이면 작은 값과 이유, 실험 전에 막는 것부터 읽기" 규칙. 8절 다음에 0번(전역 STVL 꼬리) 추가, 열린 것에 헛돎 감시 취소 꺼 둠·순찰 이동 실패 종료·센서 배치·코드 개선 추가. 결정 이력 보강
- `docs/TROUBLESHOOTING.md`: 낮은 장애물 항목의 "대가"에 위 이력 추가, 시험 도구 경로를 `tools/sim_trials/`로 고침
- `docs/CHANGELOG.md`: lab·ktj 두 줄기로 나뉘어 겹치던 번호를 하나로 이어 붙임(ktj (22)~(30) 뒤에 lab (31)~(52)). lab 표시와 구분선 제거. 다른 문서의 번호 참조 2곳 수정

## 2026-10-13 (52) `docs/PROJECT.md` 보강: 전제마다 왜·실제로는·하지 말 것, 기록 양식, 작업 절차, 결정 이력

**할 일**
- 없음

**변경**
- `docs/PROJECT.md`: (51)의 초안이 짧아 에이전트가 오해할 여지가 있어, 설계 전제 6개에 각각 "왜 / 실제로는 이렇게 / 하지 말 것"을 붙이고, 변경 기록 항목 양식, 실험 절차 8단계, 설정값 채택 기준, push 전 점검, 에이전트 작업 습관, 결정 이력 표(10-02~10-13, 이유 포함), 패키지별 핵심 파일 표를 추가. 107 → 약 230줄

## 2026-10-13 (51) `docs/PROJECT.md`를 "이 저장소에서 일하는 사람·에이전트의 안내서"로 다시 씀

**할 일**
- pull 받으면 `docs/PROJECT.md`부터 읽는다

**변경**
- `docs/PROJECT.md`: 9월 23일 기준 내용(서점 순찰, 외곽 0.45 m, 설정 파일 축별 분해 구조)이 지금과 달라 전부 다시 씀. 무엇을 만드는가(쓰레기통 로봇, v14 사양) / 바꾸면 안 되는 설계 전제 6개(다가오는 사람은 손님, 막히면 기다리기, 후진 금지, 속도 상한, 사람 있는 환경 평가·0.3 m 미만은 충돌, ID에 기대지 않기) / 브랜치 흐름과 lab 전용 목록 / 무엇을 어디에 쓰나(문서 여섯 곳, 새 .md 금지, 실수·무효 실험 기록 금지, 큰 파일 금지) / 코드 원칙 8개 / 작업 습관 / 지금 상태와 다음 우선순위 / 알려진 제약
- `CLAUDE.md`(lab): PROJECT.md를 먼저 읽으라는 줄 추가

## 2026-10-13 (50) README를 "따라 하면 무엇이 뜬다" 흐름으로 다시 씀

**할 일**
- 없음

**변경**
- `README.md`: 위쪽은 처음부터 돌려 보는 5단계(설치 → 빌드 → 시뮬레이션 → 순찰 → 관제 화면)로, 각 단계는 명령 블록과 "그러면 무엇이 열린다" 한 줄. 자주 쓰는 변형(학원 2층, 시연 한 줄, 이전 로봇, 사람 인식 모델, 주행 기록)은 명령 + 한 줄 설명. 패키지 구성·토픽·튜닝 값·CSV 열·SLAM·생성 월드·하드웨어 메모는 "자세히" 절로 내림. 내용은 빠뜨리지 않고 자리만 바꿈
- 관제 화면 띄우는 명령(서버·Bridge·브라우저 주소)을 README에 처음 넣음 (dashboard·relay_prog README에서 가져옴). 구동부 사양(83 RPM, 1:71, 바퀴 15 cm → 0.65 m/s) 한 줄 추가

## 2026-10-13 (49) 충장로·레이싱 트랙의 생성 산출물(메시·월드·지도)을 저장소에서 뺌, 생성기만 남김

**할 일**
- 충장로·레이싱 트랙 월드를 쓰려면 생성기를 한 번 돌린다 (README "생성해서 쓰는 월드"). 학원 월드는 그대로

**변경**
- `git rm --cached`로 46개 파일 추적 해제 + `.gitignore`: `models/chungjang_terrain`, `models/chungjang_all_terrain`, `models/race_track_terrain`, `worlds/chungjang*.sdf`, `worlds/race_track.sdf`, `maps/chungjang*`, `maps/race_track_map.*`. 메시 26 MB가 월드를 다시 만들 때마다 쌓여 `.git`이 311 MB가 됐기 때문. 남긴 것: `tools/chungjang/gen_street.py`와 OSM 자료 2개, `tools/race_track/gen_track.py`, `*_movers.json`
- 이미 들어간 이력은 그대로라 `.git` 크기는 줄지 않음 (이력 정리는 force push가 필요해서 하지 않음)

## 2026-10-13 (48) ktj를 lab으로 병합 (관제·순찰 일시정지·재개를 lab 실험 기반으로)

**할 일**
- `build_limbo` (`PatrolState` 메시지와 순찰 노드가 바뀜)

**변경**
- ktj의 (22)~(30)을 lab에 합쳤음: 순찰 노드 일시정지·재개 서비스와 `PatrolState`, 관제(dashboard·relay_prog·Bridge), 이동 실패 시 순찰 종료 처리. lab의 실험 도구·충장로·레이싱 월드·`moving_obstacles.py`는 lab에만 남음(연구용)
- 충돌 해결: 순찰 노드는 ktj 것(마지막 waypoint stop 검사는 ktj가 이미 다른 곳에 가짐), README는 ktj 것, 알려진 문제는 양쪽 행 모두, 변경 기록은 ktj 항목 (22)~(30) 뒤에 lab 항목을 (31)부터 이어 붙임
- `nav2_params.yaml`·waypoint yaml은 양쪽이 같아서 변화 없음

## 2026-10-13 (47) 복도 사람 통과 실험: 한 명은 v14 통과, 두 명 나란히는 이전 로봇도 불가, "성공"이 사람을 뚫은 경우가 있음

**할 일**
- 없음

**변경**
- `experiments/2026-10-13_pass_people/README.md`: `people2` 경로(복도 안 목표)로 한 명·두 명·30초 대기·이전 로봇 각 1회. 한 명이면 v14가 31~39초에 사람과 0.3~0.4 m 두고 통과, 두 명 나란히(폭 1.8 m 복도)는 v14·이전 로봇(`robot:=legacy`) 모두 60초 초과이고 사람 안 0.03·0.11 m까지 들어감
- 사람 최소 거리 0.3 m 미만은 실제로는 충돌임(사람 모델은 충돌 없음, HumanLayer 비용은 가우시안). 어제 이전 로봇 12/12(0.13~0.30 m)도 일부 그랬음 → nav_recorder에 충돌 열, HumanLayer 사람 몸 반경 안 치명 비용, BT "사람이면 멈춰 기다리기", 소셜 포스 사람 순으로 할 일 정리. `docs/KNOWN_ISSUES.md` 항목 갱신

## 2026-10-13 (46) 사람 있는 복도 실험 정리: 폭 1.8 m 복도에서 두 명 나란히는 통과 불가, 쓰레기통 용도 전제, 시험 도구 보강

**할 일**
- 없음

**변경**
- `experiments/2026-10-13_people_speed/README.md`: 학원 시나리오 `people` 경로에서 지금 설정(A)부터 위쪽 복도 4구간 중 1구간만 성공. 지도를 재 보니 위쪽 복도는 y 9.2~11.0(폭 약 1.8 m)이고 두 사람(y 9.79·10.5)이 나란히 오면 남는 틈이 0.25~0.35 m라 어떤 로봇도 못 지나감 → 이 시나리오는 "통과"가 아니라 "기다리기" 시험. 속도 설정 B·C 비교는 여기서 의미 없어 중단
- `experiments/2026-10-13_pass_people/README.md`: 설계 전제 기록. 이 로봇은 움직이는 쓰레기통이라 다가오는 사람은 손님이고 멈춰 기다리는 건 서비스. 사람을 "지나가는 사람/다가오는 사람"으로 나눠 BT 분기로 처리, 사람 ID에 기대지 않음, timeout 숫자는 진단용. 한 명(틈 0.95 m) 통과 실험은 `people2` 경로로 진행 중
- `docs/KNOWN_ISSUES.md`: 해당 항목 추가. `docs/lab/requests.md` R2는 충장로 2회차만으로 축소
- `tools/sim_trials/nav_route.py`: `people2`(복도 2구간 짧은 판) 추가. `sim_ctl.sh`: Nav2가 active가 아니면 준비됨으로 넘기지 않고, stop 때 남은 launch·gz를 PID로 정리. HuNavSim은 Jazzy/Harmonic 미지원이라 쓰지 않고 소셜 포스 사람은 `moving_obstacles.py`에 직접 넣기로 함

## 2026-10-13 (45) 서브 PC R2 결과: 충장로 거리 A·B·C 2회차 재현, 복도 A3·B3

**할 일**
- 없음

**변경**
- `experiments/2026-10-13_people_speed_sub/`: 충장로 200 m 왕복 A 252/246 s, B 170/175 s, C 139/145 s로 노트북 1회차와 1~6초 차이로 재현했음. 축소 전에 돌린 복도 A3·B3(둘 다 2/4)도 넣었음. RTF 사실상 1.0
- `docs/lab/reports.md`: R2 완료와 결과 표, 브랜치 전환 시 `limbo_interfaces` 다시 빌드 필요

## 2026-10-13 (44) 요청 R2에 Nav2 멈춤 회차 대처를 추가 (문서만)

**할 일**
- 없음

**변경**
- `docs/lab/requests.md` R2: 시뮬레이션이 준비됐다고 해도 Nav2가 configure에서 멈춰 로봇이 출발하지 않는 회차가 있으니, 회차 사이에 pull 받아 고친 `sim_ctl.sh`를 쓰거나 그 회차를 버리고 다시 돌리라고 적었음

## 2026-10-13 (43) `sim_ctl.sh`가 Nav2가 active가 아니면 준비됨으로 넘기지 않게 고침

**할 일**
- 없음 (서브 PC: R2 시작 전에 pull 받으면 좋음)

**변경**
- `tools/sim_trials/sim_ctl.sh`: `bt_navigator`가 3분 안에 active가 안 되면 실패로 보고 다시 띄움. 전에는 그 뒤 TF만 확인하고 "준비됨"을 냈음
  - 2026-10-13 16:18 회차: collision_monitor의 `change_state` 응답이 시간 초과로 끊겨 lifecycle manager가 configure 단계에서 멈춤. AMCL·TF는 정상이라 도구는 준비됐다고 보고 목표를 보냈고, Nav2가 inactive라 응답 없이 12분 대기함
- `docs/KNOWN_ISSUES.md`: collision_monitor 항목에 "configure 단계에서 멈춤" 경우 추가

## 2026-10-13 (42) 사람 복도 목표를 벽 쪽으로 옮긴 `people_side` 경로, 서브 PC 요청 R2

**할 일**
- 없음 (서브 PC는 R2 지시서대로 `build_limbo` 후 실행)

**변경**
- `tools/sim_trials/nav_route.py`: `people_side` 경로 추가. `people`과 같은 왕복이지만 목표를 북쪽 벽 쪽(y 11.8)으로 옮겼음. 원래 목표가 걷는 사람 줄(y 9.8) 위라 도착해 있으면 사람이 걸어 들어와 끼였기 때문
- `docs/lab/requests.md` R2, 지시서 `experiments/orders/2026-10-13_sub_people_side.md`, 실행 스크립트 `experiments/orders/people_side_one.sh`: 서브 PC가 A·B·C 3회차를 맡음 (한 세트가 한 시간 가까워 두 PC로 나눔)
- `experiments/2026-10-13_people_speed/README.md`, `docs/KNOWN_ISSUES.md`: 목표를 옮긴 건 실험용 분리 조치이고 실물에서는 "사람이 막으면 멈춰 기다렸다 재개" BT 동작·HumanLayer 지연 확인이 본질이라는 논의를 적었음

## 2026-10-13 (41) 사람 있는 복도 속도 비교 중단, v14가 두 사람 사이에 끼는 문제를 알려진 문제에 추가 (설정 변경 없음)

**할 일**
- 없음

**변경**
- 실험 기록 `experiments/2026-10-13_people_speed/`: 학원 시나리오 `people` 경로에서 `prune_distance` 2.5(B)·상한 0.75(C)를 3회씩 돌렸는데, 지금 설정(A)부터 위쪽 복도 4구간 중 1구간만 성공해서 비교를 중단했음
- `docs/KNOWN_ISSUES.md`: v14 로봇이 나란히 걷는 두 사람 사이에 끼여 못 움직이는 문제 추가
- `experiments/2026-10-12_mppi_speed/README.md`: 어제 결과가 이전 로봇·이전 월드 기준이라 지금과 비교할 수 없다는 주의 추가

**확인**
- 사람 없는 첫 구간은 충장로와 같은 경향 (A 0.35 → B 0.47 → C 0.53 m/s, 상자와 거리 같음)
- 물리 스텝 2 ms는 원인이 아님: 1 ms 사본으로 B를 2회 돌려도 같음
- 원인 후보: 복도 빈 폭 3.6 m에서 두 사람이 1.7 m를 차지하면 v14(폭 0.59 + inflation 0.45 × 2 = 1.49 m)의 여유가 0.3 m. 목표 지점이 `pair_right`가 걷는 줄 위라 도착해 있으면 사람이 걸어 들어옴

## 2026-10-13 (40) 충장로 거리 속도 실험 (설정 변경 없음, 기록만)

**할 일**
- 없음

**변경**
- `tools/sim_trials/nav_route.py`: `street` 경로(충장로 (0,0)→(100,0)→(0,0)) 추가, 구간 제한 시간을 환경변수 `GOAL_TIMEOUT`(기본 120초)으로 바꿀 수 있게 했음
- 실험 기록 `experiments/2026-10-13_chungjang_speed/` (실행·분석 스크립트, 결과 CSV)

**확인** (사람 없는 직선 200 m 왕복, 조건당 1회)
- 현재 설정: 평균 0.42 m/s, 왕복 500 s. 평활기·collision monitor가 깎은 게 아니라 MPPI `prune_distance` 1.7이 원인 (어제 복도 결과와 같음)
- `prune_distance` 2.5: 평균 0.58 m/s(상한 0.6), 왕복 351 s → dev 반영 후보 확정
- 상한 0.75 + `prune_distance` 3.0: 평균 0.72 m/s, 왕복 284 s, 복구 0. 실물은 평지에서만 0.8 m/s가 나오니 0.6~0.7 사이가 안전
- 녹화 주의: 백그라운드 `ros2 bag record`는 `kill -INT`로 안 멈추고 `kill -TERM`이어야 함

## 2026-10-13 (39) 월드 물리 스텝 1 ms → 2 ms (시뮬레이션 실시간 비율 0.6 → 0.95)

**할 일**
- `build_limbo` (월드 sdf는 install에 복사되므로 다시 빌드해야 적용됨)

**변경**
- 월드 7개(`aischool_2f`, `aischool_2f_furnished`, `aischool_2f_scenarios`, `human_test_world`, `race_track`, `chungjang`, `chungjang_all`)의 `max_step_size`를 0.001 → 0.002로 바꿨음. `bookstore_world`는 원래 0.003이라 그대로
  - 시연 화면에서 로봇이 너무 느려 보여서 재 보니 Gazebo 실시간 비율이 0.6이었음(MPPI 실속 0.4 m/s가 화면에서는 0.24 m/s). 병목은 gz 서버의 물리 스레드가 한 코어를 다 쓰는 것이라(1 ms = 시뮬 1초에 1,000번 계산) 코어 수·GPU로는 해결이 안 됨. 2 ms면 계산이 반으로 줄어 실시간을 따라옴
  - 정확도 확인: 같은 순찰(가구 학원 E→G→J 65 m)과 통제 시험(직진 6 m·제자리 5바퀴)을 1 ms·2 ms로 비교. 직진 6 m에 8 mm, 제자리 5바퀴 회전 오차는 둘 다 +150°로 같음. 속도 추종·최고 속도도 같음. 기록 `experiments/2026-10-13_physics_step/`
- 실험 기록과 측정 스크립트 추가: `experiments/2026-10-13_physics_step/` (`speed_probe.py` 실시간 비율·속도, `phys_record.py` 정답 대 odom, `drive_test.py` 통제 주행)

**확인**
- 가구 학원 월드, 화면 켠 상태: 실시간 비율 정지 0.92~0.98, 주행 0.95 (전 0.60). 화면 없이 0.96. 주행 최고 속도 0.44 m/s로 전과 같음
- 따로 알게 된 것: 바퀴 odom이 제자리 회전 때 실제보다 9 % 더 돈 것으로 셈(스텝과 무관, 실린더 바퀴 옆미끄러짐으로 보임). 순찰 중 바퀴 odom이 3~4 m 틀어지는 원인. EKF(IMU)가 1 m, AMCL이 보정하므로 주행엔 영향 없음
- Gazebo 화면(gz gui) 프로세스만 PID로 끄면 서버까지 같이 종료됨. 화면은 처음부터 `gui:=false`로 띄울 것

## 2026-10-13 (38) 시연 스크립트 `tools/demo_patrol.sh`, 가구 월드 순찰 통로 끝을 stop으로

**할 일**
- 없음 (스크립트·waypoint yaml만. 설치 폴더가 symlink가 아니면 `build_limbo`)

**변경**
- `tools/demo_patrol.sh [월드] [지도] [waypoint]`: 시뮬레이션을 띄우고 Nav2·위치 추정이 준비되면 순찰을 자동으로 시작함. Ctrl+C 한 번이면 전부 내려감. 기본은 `aischool_2f` + `aischool_waypoints.yaml`
  - 그냥 launch 뒤에 순찰 노드를 이어서 치면 안 됨: 순찰 노드는 위치 추정을 30초만 기다리는데 시뮬레이션은 뜨는 데 1~2분 걸림
- `aischool_furnished_waypoints.yaml`: 왼쪽 책상 통로 끝 G를 `pass` → `stop`(0초 대기)으로 바꿨음
  - pass로 두면 F→G→H→I→J가 경로 하나로 묶여 통로를 올라가는 경로와 내려오는 경로가 겹침. MPPI가 그 사이에서 갈피를 못 잡아 G 0.8 m 앞에서 "진전 없음" 6번·회전·후진 반복 (어제 "통로 끝 돌아 나오기 150초"와 같은 현상). 같은 좌표를 단독 목표로 주면 3/3 성공했던 곳이라 좌표 문제가 아님. 닫힌 고리 경로 때와 같은 원인

**확인** (`demo_patrol.sh`, 화면 없이)
- `aischool_2f` 순찰 4구간 성공 ("Patrol mission completed")
- `aischool_2f_furnished` 순찰: 수정 전 G 앞에서 막힘 → 수정 후 E·G·J 모두 도착, 진전 없음 0번, 복구 0번. 문 들어가기(A→E)도 통과 (순찰 경로는 문 앞 지점을 거쳐 들어가서 됨)

**참고**
- 막다른 곳에서 되돌아오는 waypoint는 항상 `stop`으로 둘 것 (NavigateThroughPoses에 되돌아오는 경로를 넣지 않기)

---

## 2026-10-13 (37) 충장로 번화가 전체 월드 `chungjang_all` (10 cm 격자)

**할 일**
- `build_limbo` (새 모델·월드·지도)

**변경**
- `gen_street.py --all`: 큰길(금남로·중앙로·서석로·천변우로) 안쪽 번화가 전체를 월드 `chungjang_all`·지도 `chungjang_all_map`으로 만듦. 자료는 더 넓게 받은 `osm_chungjang_all.json` (© OpenStreetMap contributors, ODbL 1.0)
  - 띄우기: `world:=chungjang_all map:=chungjang_all_map`. 200 m 월드와 원점·방향이 같아 좌표를 그대로 씀
  - 실제 크기 거리 방향 약 470 m × 가로 약 530 m (처음 추정 400 × 350보다 큼). 격자 5,700 × 6,100 칸
  - **격자를 10 cm로 한 이유**: 5 cm면 약 1억 4천만 칸(400 × 350 m만 잡아도 5,600만 칸)이라 Nav2 costmap·경로 계획이 너무 무거움. 10 cm는 약 3,500만 칸이고 로봇 폭 0.5 m에 충분함
  - 큰길은 중심선 양옆 12 m(차도+보도)를 바깥으로 보고 그 가장자리에 울타리(1,501 m). 큰길 너머 건물 242채는 세우지 않음 (울타리에 가려 안 보이고 메시만 무거워짐). 안쪽 건물 495채
  - 큰길이 격자를 다 막지 못해 구역이 가장자리까지 새면 생성이 멈추고 알려 줌
- 건물을 건물마다 격자 마스크로 들지 않고 **번호 라벨 이미지 하나**로 다루도록 고침. 처음 방식은 전체 월드에서 131 s·30 GB, 바꾼 뒤 5.7 s·1.4 GB. 200 m 월드 결과는 그대로 (울타리만 한 칸 안쪽으로 옮겨짐: 바깥 띠와 울타리를 같은 방식으로 다루게 되어서)
- 거리 폭 통계에서 양 끝(울타리 바로 앞)을 뺌

**확인**
- 시뮬레이션+Nav2 1번에 시작, 메모리 6 GB, Gazebo 실시간 0.68~0.95배
- NavFn 경로 계산 0.21~0.37 s (527 m 경로까지). 자세히: `experiments/2026-10-13_chungjang_all/README.md`
- 실제 주행은 아직 안 함

**참고**
- 메시 26 MB(56만 면)가 저장소에 들어감. 다시 만들 때마다 기록이 그만큼 늘어나니 자주 재생성하지 말 것

---

## 2026-10-13 (36) 충장로 월드: 거리와 이어지지 않은 막힌 빈 공간 채우기

**할 일**
- `build_limbo` (지도·건물 메시가 바뀜. 설치 폴더가 symlink면 생략 가능)

**변경**
- `tools/chungjang/gen_street.py`에 막힌 공간 채우기 단계를 넣었음. 로봇 출발점(원점)과 이어진 빈 칸만 남기고, 나머지 빈 칸(건물 블록 안 구멍 10곳, 676 m²)은 가장 가까운 건물에 붙여 그 건물 높이·색을 따르게 했음
  - 실제로는 건물 안마당·지붕이라 로봇이 갈 수 없는 곳인데, 비워 두면 경로 계획이 후보로 보고 지도도 헷갈림
  - 틈 메우기(1.2 m 미만)도 같은 함수(`attach_to_nearest_building`, 거리 변환으로 가장 가까운 건물 찾기)를 쓰도록 정리했음. 전에는 건물 번호를 한 칸씩 넓혀 가며 붙였음
- 지도 `chungjang_map.png`와 건물 메시를 다시 만들었음. 빈 공간이 1개(5,492 m²)로 이어짐. 거리 폭·건물 수는 그대로 (62채, 최소 5.5 m · 중간 8.2 m)

**확인**
- Gazebo 서버만 띄워 300스텝 돌림: 메시 읽기 오류·충돌 없음

**남은 일**
- 충장로 번화가 전체(약 400 × 350 m)를 10 cm 격자로 별도 월드(`chungjang_all`)

---

## 2026-10-13 (35) 광주 충장로 보행자 거리 200 m 월드 (OpenStreetMap)

**할 일**
- `build_limbo` (새 모델·월드·지도)

**변경**
- 충장로 보행자 거리(전체 472 m) 가운데 200 m를 OpenStreetMap 건물·길 자료로 재현한 월드 `chungjang`과 지도 `chungjang_map`을 추가했음 (`tools/chungjang/gen_street.py`, 자료 `osm_chungjang.json`)
  - 띄우기: `world:=chungjang map:=chungjang_map`
  - 실제 크기 1:1. 거리가 월드 +x 방향, 구간 시작이 원점(로봇 출발). 양옆 40 m 안의 건물 62채, 거리 폭(벽 사이) 최소 5.5 m · 보통 8.2 m
  - OSM에 층수가 거의 없어 3~5층(층당 3.2 m)으로 정했음. 질감 없는 상자 건물, 색 4가지
  - 건물 외곽선 사이 1.2 m 미만 틈은 메우고(실제로는 붙은 건물), OSM에 길로 등록된 골목은 폭 3 m까지 넓혔음 (외곽선이 처마·보도 끝까지 그려져 실제보다 좁게 나옴)
  - 구간 경계는 높이 1.2 m 울타리, 걷는 사람 6명이 양방향으로 다님
  - 지도는 PNG로 저장 (pgm 6.5 MB → 53 KB)
- **자료 출처: © OpenStreetMap contributors, ODbL 1.0.** 월드·모델 파일에도 적어 두었음

**확인**
- 시뮬레이션 실시간 0.92배, 50 m 주행 123 s(0.41 m/s), 멈춤 없음 (틈 메우기 전 월드에서)

**남은 일**
- 거리와 이어지지 않은 막힌 빈 공간(건물 블록 안 구멍) 채우기
- 충장로 번화가 전체(약 400 × 350 m)를 10 cm 격자로 별도 월드(`chungjang_all`)

---

## 2026-10-13 (34) 작은 레이싱 트랙 월드, 물체를 경로대로 움직이는 스크립트

**할 일**
- `build_limbo` (새 모델·월드·스크립트 폴더가 설치되어야 함)

**변경**
- 레이싱 트랙 월드 `race_track`과 지도 `race_track_map`을 추가했음 (`tools/race_track/gen_track.py`로 만듦)
  - 띄우기: `world:=race_track map:=race_track_map`
  - 약 18 × 16 m, 한 바퀴 55.6 m, 트랙 폭 1.6 m, 가장 급한 코너 반지름 0.87 m. 출발 직선 → 오른쪽 긴 직선(약 7 m) → 가운데 헤어핀·S자 → 왼쪽 굽이
  - 방호벽 높이 1.0 m (MID-360 0.926 m보다 높아 가까이서도 보임), 빨강·흰색 번갈아. 지도에는 방호벽만 들어감
  - 트랙 모양은 `CONTROL`(중심선 조절점)만 바꾸면 됨. 트랙끼리 너무 가까운 곳·가장 급한 코너를 생성할 때 검사함. `--preview 그림.png`로 미리보기
  - 벽·바닥을 종류마다 메시 하나로 합쳤음 (상자 수천 개로 두면 센서가 하나씩 그려 시뮬레이션이 실시간 0.16배까지 느려졌음). 메시에는 법선을 넣어야 함 (없으면 Gazebo 물리 엔진이 충돌 메시를 읽다 죽음)
- `limbo_simulation/scripts/moving_obstacles.py`: 월드 안 물체를 정해진 고리 경로대로 일정 속도로 움직임 (Gazebo `set_pose_vector`, 시뮬레이션 시간 기준). `worlds/<월드>_movers.json`이 있으면 `gazebo.launch.py`가 자동으로 띄움
  - Gazebo의 힘으로 미는 방식(TrajectoryFollower)은 속도를 못 맞췄고, 사람 모델 크기 줄이기(scale)는 Gazebo가 지원하지 않았음
- 시험 도구 `tools/sim_trials/race_lap.py`: 트랙 한 바퀴를 3구간으로 나눠 돌고 시간을 잼
- 협곡 느낌 맵 초안(`tools/rift/`)은 지웠음

**확인**
- 트랙 한 바퀴 성공, 시뮬레이션 143.2 s (평균 약 0.41 m/s), 복구 동작·진전 없음 0번

**참고**
- **닫힌 고리 경로 주의**: 한 바퀴를 경로 하나(NavigateThroughPoses)로 주면 끝부분이 출발점 근처를 지나서 MPPI가 그쪽을 따라가 바로 도착으로 끝난다. 구간을 나눠 줄 것
- 속도 0.41~0.43 m/s는 MPPI `prune_distance: 1.7`에서 오는 상한과 같다 (`experiments/2026-10-12_mppi_speed`)

---

## 2026-10-13 (33) v14 로봇 외곽을 실제 크기로, 가구 월드 순찰 경로

**할 일**
- 없음 (설정·waypoint yaml만 바뀜. 설치 폴더가 symlink가 아니면 `build_limbo`)

**변경**
- Nav2 로봇 외곽을 받은 패키지 값(0.50 × 0.63 m + 여유 0.02)에서 **실제 크기 0.50 × 0.59 m, 여유 0**으로 바꿨음. 0.9 m 문·1.3 m 책상 통로에서 MPPI가 경로를 못 찾던 문제(경로 계산 실패 1,399번 → 0번)
  - 레거시 모델(`robot:=legacy`)은 launch에서 여유 0.02를 그대로 넣음
- 가구 월드용 순찰 waypoint `aischool_furnished_waypoints.yaml`을 추가했음. 208 교실은 위쪽 문 → 오른쪽 통로 → 뒤쪽 서쪽 구석(5초 정지) → 왼쪽 통로 왕복 → 아래쪽 문. 가구가 지도에 없어서 꺾이는 곳마다 pass 지점을 둠
- 좁은 곳 시험 도구: `tools/sim_trials/tight_trial.py`(문·통로 구간별 성공·시간), `apply_footprint.py`(외곽 바꾸기), `run_tight.sh`(설정 여러 개를 차례로)

**확인**
- 통로 끝 돌아 나오기·문 나가기 3/3 (전에는 1/3, 0/3). 기록: `experiments/2026-10-13_tight_spaces/`
- 가구 월드 순찰 OK (외곽 바꾸기 전, 588 s)

**참고**
- 복도에서 비스듬히 문 들어가기는 아직 실패한다 (0~1/3). 경로 계획 알고리즘 비교에서 다룬다
- 막다른 통로도 후진 없이 제자리 회전으로 돌아 나온다

---

## 2026-10-12 (32) 학원 2층 가구 월드 (실제 가구 모델)

**할 일**
- `build_limbo` (새 모델 폴더가 설치되어야 Gazebo가 찾음)

**변경**
- 가구를 넣은 월드 `aischool_2f_furnished`와 지도 `aischool_2f_furnished_map`을 추가했음. 기존 `aischool_2f`·`aischool_2f_scenarios`는 그대로
  - 띄우기: `world:=aischool_2f_furnished map:=aischool_2f_furnished_map`
- 배치는 사용자가 그린 대략적인 그림을 따르고, 통로는 실제 기준으로 맞췄음 (`tools/aischool_2f/furniture.py`): 가구와 벽 0.9 m, 가구끼리 1.2 m(사람 둘이 엇갈림)
  - 206·208·205·202 교실: 그린 띠마다 1인용 책상을 2자리씩 나란히 줄지어 놓고 의자는 책상 뒤(반쯤 밀어 넣음), 모두 교탁(문 쪽 끝)을 봄. 208·205는 북쪽이 앞
  - 세 줄 중 양쪽 줄은 벽에 붙이고(실제 교실 구조) 가운데 줄은 방 가운데. 줄 사이 통로 1.30~1.33 m
  - 207·204: 책상을 붙인 모둠, 209 상담실: 테이블·소파, 203 휴게실: 테이블, 복도·홀: 정수기 2개
  - 합계 334개 (의자 170, 1인용 책상 140, 접이식 책상 10, 나무 테이블 10, 소파 2, 정수기 2)
- 가구는 Nav2 지도에 넣지 않았음 (센서로 보고 피함). 안 움직이는 정수기만 지도에 넣었음
- Gazebo Fuel의 OpenRobotics 가구(`foldable_table`, `foldable_chair`, `Table`, `Sofa`)를 `limbo_simulation/models/`에 복사했음 (인터넷 없이 열림). 1인용 책상(`student_desk`)은 접이식 책상 메시를 줄였고, 정수기(`water_dispenser`)는 단순 도형으로 만들었음. 출처: `models/CREDITS.md` (CC BY 4.0은 출처 표시 필수)
- 협곡 느낌 맵 배치 초안 `tools/rift/layout.py` (게임 파일 없이 구조만 따라 새로 만듦. 월드는 아직 안 만듦)

**확인**
- 시뮬레이션 실시간 비율: 가구 194개일 때 0.97, 334개일 때 0.60 (둘 다 Gazebo 화면을 켠 상태). 화면 없이 재는 건 아직 안 함. 느리면 의자 메시(4.8 MB)를 가벼운 것으로 바꿀 것

**참고**
- 의자 다리가 가는 금속이라 센서에는 다리만 보인다. MID-360(0.926 m, 아래 −7°)은 책상(0.69 m)을 약 1.9 m보다 가까우면 못 본다
- 208 교실 순찰 waypoint(C·D·E·F)는 책상과 겹친다. 가구 월드로 순찰하려면 경로를 다시 잡아야 함
- 나무 테이블(`Table`)은 원본 높이가 1.0 m라 교탁·바 테이블 정도로 높다

---

## 2026-10-12 (31) 새 로봇 v14 모델, 학원 2층 도면을 문 0.9 m 기준으로 다시 만들기

**할 일**
- `build_limbo` (새 파일: 모델, self filter 설정)
- 학원 2층 지도가 바뀌었음. 예전 지도로 만든 waypoint 파일이 있으면 좌표에 1.168을 곱할 것

**변경**
- 실제 로봇(이동형 쓰레기통 45×45×70 v14)을 기본 모델로 넣었음 (`limbo_description/urdf/limbo.urdf.xacro`). MID-360+IMU는 뚜껑 위 0.926 m, OAK-D Lite는 바닥에서 0.50 m
- 예전 모델은 `urdf/legacy/`로 옮겼고 `robot:=legacy`로 띄울 수 있음. launch가 Nav2 외곽·팽창·장애물 높이를 예전 값으로 바꿔 넣음
- Nav2를 v14 크기에 맞췄음: 외곽 0.50 × 0.63 m, 팽창 반지름 0.45 m, 장애물 높이 상한 1.00 m. self filter는 `lid_link`
- 학원 2층 월드·지도를 문 0.9 m(법정 유효폭) 기준 축척으로 다시 만들었음 (1.168배, 28.8 × 27.5 m). 문 13개 모두 0.90 m. 사용자가 그림판으로 고친 벽(`tools/aischool_2f/walls_edited.png`)을 씀
- 순찰 waypoint, `nav_route.py` 학원 경로 좌표를 같은 배율로 바꿨음
- `patrol_analyze.py`가 멈춘 시간을 시뮬레이션 시간으로 재고, Gazebo가 멈춘 구간을 따로 보여 줌

**확인**
- v14 학원 2층 순찰 OK (234 s). 기록: `experiments/2026-10-12_v14_robot/`

**참고**
- 벽을 고칠 때는 `walls_edited.png`(검정 = 벽, 1 m = 80 px)를 고치고 `python3 gen_world.py`. 참고 그림은 `python3 export_guide.py`
- 시험 도중 Gazebo 화면을 붙이면 Gazebo가 몇 초 멈춘다. 볼 거면 처음부터 `gui:=true`
## 2026-10-13 (30) lab에서 실제 로봇 v14 모델·학원 2층 지도·waypoint 선택 가져옴 (실험 기록은 뺌)

**할 일**
- **`build_limbo`** (새 메시·월드·모델·waypoint 파일이 들어옴)
- 이제 시뮬레이션 로봇이 **v14(실제 로봇)가 기본**. 예전 모델로 비교하려면 `robot:=legacy`
- 학원 2층으로 순찰하려면 `-p waypoints:=aischool_waypoints.yaml` (기본은 그대로 `test_waypoints.yaml`)

**변경** (lab 커밋 880bc1e, 4f45201, 0222337, 12301be, 1438bb3, 815bab9, 26f790e에서 파일 단위로 가져옴. lab 전체를 merge하지 않음)
- **로봇 모델 v14**: `limbo_description/` (v14 메시, URDF, 예전 모델은 `urdf/legacy/`). `start_simulation.launch.py`·`gazebo.launch.py`에 `robot:=v14|legacy`, 시뮬레이션 브리지에 뚜껑 각도(`lid_angle`)
- **Nav2**: `nav2_params.yaml` 로봇 외곽을 v14 실제 크기로 (0.9 m 문·1.3 m 책상 통로를 지나가게), `self_filter.yaml` v14 몸체, `self_filter_legacy.yaml` 예전 모델용
- **학원 2층**: 월드·지도를 문 0.9 m 기준으로 다시 만듦 (`aischool_2f`, `aischool_2f_scenarios`), 가구 월드 `aischool_2f_furnished`와 지도·waypoint, 가구 모델 6종(출처 `models/CREDITS.md`), 생성 도구 `tools/aischool_2f/`
- **순찰 노드**: waypoint 파일을 `waypoints` 파라미터로 고름 (일시정지·재개 코드와 손으로 합침)
- **월드 물리 스텝 1 ms → 2 ms** (`human_test_world`, 학원 2층 월드): 실시간 비율 0.6 → 0.95, odom 정확도 차이 없음 (lab 실험)
- **`tools/demo_patrol.sh`**: 시뮬레이션이 준비되면 순찰을 자동 시작하는 시연용 한 줄 실행
- README(월드 표·순찰·로봇 모델), TROUBLESHOOTING(가구 월드 통로 끝 "Failed to make progress")
- **가져오지 않은 것**: `experiments/`, `tools/sim_trials/`, `docs/LAB_BOARD.md`·`docs/lab/`, lab 전용 `CLAUDE.md`, 충장로·레이싱 트랙 월드와 지형·OSM 자료, 움직이는 장애물 스크립트(`gazebo.launch.py`에서도 그 부분을 뺌)

**시험**
- `build_limbo` 성공, 시뮬레이션에서 로봇 모델이 v14인 것 확인 (`robot_description`에 `v14/body.stl`, `lid_link`)
- **v14로 관제 화면 일시정지·재개 다시 확인**: 일시정지 1.39초, 재개 0.86초 만에 "확인됨", 재개 4초 뒤 0.42 m/s
- Bridge·대시보드 설정은 바꾸지 않음 (v14도 프레임 `base_footprint`, `rgbd_camera_optical_link`와 센서 토픽 이름이 같음)

---

## 2026-10-13 (29) 관제 화면 UI/UX 다듬기

**할 일**
- 화면 다시 빌드(5분 넘게 걸림), 서버 다시 실행 (알림 문구·명령 경과 시간이 바뀜)

**변경** (설계: `docs/CONTROL_SCREEN.md` "UI/UX 다듬기")
- **이미 일시정지면 일시정지 버튼을 잠금**: 순찰 노드가 `paused`·`pausing`이라고 알려 준 경우만. "이미 일시정지 상태입니다". 순찰 상태를 모르면 누를 수 있게 둠 (멈추는 쪽은 막지 않음). 전에는 눌리고 "요청 실패: already paused"가 떴음
- **결과 상자에 경과 시간**("요청 시각 15:34:51 · 4초 전"), 끝난 지 1분이 지나면 한 줄("재개 확인됨 · 1분 19초 전 · 자세히")로 접음. 경과 시간은 서버가 잰 값(`command.age_s`, 새 필드)을 써서 브라우저 시계와 비교하지 않음
- **좁은 화면(999px 이하)에서는 로봇 제어를 맨 위로**: 휴대폰 첫 화면에 일시정지 버튼이 보임 (전에는 지도 아래)
- **"추정 이동 속도"와 "이동 상태" 카드를 "이동" 하나로** 합치고, 순찰 카드를 앞에 둠
- **"상태 전달 프로그램" → "로봇"**: 머리글("로봇 연결됨"), 안내 띠, 서버 알림("로봇 연결 끊김", "로봇 상태 수신 지연", "로봇 연결 복구", "로봇 연결됨")
- **"전달 안 됨"(`expired`)을 실패로 표시**: (28)의 claim 덕분에 `expired`는 "실행 안 함"이 확실함. "정지 요청 실패 · 로봇에 제때 전달되지 않아 실행하지 않았습니다. 필요하면 다시 눌러 주세요" (전에는 "확인 불가")
- **순찰 카드**: 로봇 연결이 지연·끊김이면 회색 "순찰 중 (마지막 상태)" + "지금 상태는 알 수 없습니다" (전에는 초록 "순찰 중" 그대로)
- **지도**: 로봇 아이콘을 키우고 "로봇 따라가기"(로봇 중심 10 m) / "전체 지도 보기" 버튼
- `/demo`의 가상 순찰 시작 상태를 "순찰 중"으로 (일시정지 잠금 때문에)
- `tools/observe_ui.mjs`(Bridge 통합 검증용)를 새 머리글·카드에 맞춤

**시험**
- 화면 단위 시험 24개(새 1: 일시정지 잠금), 서버 55개, 브라우저 e2e 17개 통과
- 실제 화면 + 시뮬레이션: 휴대폰 폭(390px) 첫 화면에 일시정지 버튼 보임, 일시정지 후 버튼 잠김·사유 표시, 로봇 따라가기, 1분 뒤 결과 접힘 확인
- 시험 중 고친 것: 합친 "이동" 카드에서 연결이 끊긴 화면일 때 "마지막 수신 값" 표시가 768·390px에서 화면 밖으로 넘침 → 줄바꿈되게 함

---

## 2026-10-13 (28) 일시정지 문제 1·2 수정: 늦게 읽은 명령은 실행 안 함, 순찰 노드 꺼짐 표시

**할 일**
- **서버·Bridge·화면을 함께 올릴 것**. 새 Bridge는 서버에 "아직 유효한가"를 묻는데, 예전 서버는 이 주소가 없어서 **모든 명령을 실행하지 않음**
- Bridge 다시 빌드, 화면 다시 빌드(5분 넘게 걸림), 서버 다시 실행

**변경** (설계: `docs/CONTROL_API_DRAFT.md` §2.4, `docs/CONTROL_SCREEN.md` 실패 시험 표)
- **문제 1**: Bridge가 서비스를 부르기 직전에 `POST /api/v1/commands/{id}/claim`으로 서버에 묻고, **왕복 시간을 Bridge가 직접 잼**. 서버가 거절하거나(이미 "응답 없음"으로 끝남 등) 1초 안에 답이 없으면 부르지 않고 `expired`로 보고. 서버는 허락한 시각부터 응답 제한(5초)을 다시 셈
- **문제 2**: Bridge가 0.5초마다 `/patrol/state` 발행자(순찰 노드)가 있는지 봄. 없으면 순찰 상태를 "받았지만 알 수 없음"(필드 null, 계약 그대로)으로 보냄. 화면 순찰 카드 "순찰 상태 확인 불가 · 순찰 프로그램이 꺼져 있거나 상태를 알 수 없습니다", 재개 버튼 사유도 같이

**시험**
- 서버 55개(새 1), Bridge 66개(새 4), 화면 단위 23개, 브라우저 e2e 17개 통과
- 실제 화면 + 시뮬레이션에서 다시 돌림
  - Bridge를 얼린 뒤 일시정지: 화면 "정지 여부 확인 불가" → Bridge를 풀어도 **로봇이 실행하지 않음** (Bridge 로그 `claim refused`). 고치기 전에는 6초 늦게 멈췄음
  - 순찰 노드 끔: 순찰 카드 "순찰 상태 확인 불가", 재개 사유 "순찰 프로그램 상태를 확인할 수 없습니다", 일시정지 → **바로** "정지 요청 실패: 순찰 프로그램이 꺼져 있어 요청을 실행하지 않았습니다" (고치기 전: "순찰 중"으로 남고 3초 뒤 "응답 없음")
  - 정상 경로: 일시정지 1.38초, 재개 0.86초 만에 확인됨

**참고**
- **새로 본 것**: 순찰 노드가 꺼져도 Nav2가 하던 목표를 계속 가는 경우가 있음 (이번엔 속도 0.4 m/s로 계속 이동). 이때 일시정지 버튼은 "실패"를 사실대로 보여 주지만 **로봇을 멈추지는 못함**. Bridge가 이 경우 Nav2 목표를 직접 취소할지 정해야 함
- 문제 3(재개 직후 내비게이션 실패로 순찰 종료)은 그대로. 시험 중 두 번 더 일어남

---

## 2026-10-13 (27) 일시정지 버튼 실패·경계 상황 시험 (코드 변경 없음)

**할 일**
- 없음 (시험만 함). 아래 문제 1~3은 고칠 방법을 정한 뒤 따로 작업

**시험** (실제 화면 + 시뮬레이션, Chromium으로 버튼 클릭, 자세한 표는 `docs/CONTROL_SCREEN.md` "일시정지 실패·경계 상황 시험")
- 정상: 브라우저 두 개 동시 클릭(명령 하나만), 정지 지점 대기 중 정지(0.87초, 대기가 끝나도 계속 정지), 상태 보고 전에 Bridge가 멈춤("확인 불가", 늦은 보고로 성공으로 안 바뀜), Bridge 끔(4초 뒤 버튼 잠김, 11초 뒤 "연결 끊김", 다시 켜면 풀림)
- **문제 1**: Bridge가 명령을 늦게 읽으면 화면은 "정지 여부 확인 불가"로 끝났는데 **약 6초 뒤 로봇이 실제로 실행**함. 유효 시간을 Bridge가 읽은 순간부터 세기 때문. 재개 명령이면 예고 없이 출발할 수 있음
- **문제 2**: 순찰 노드가 꺼져도 화면은 계속 "순찰 중", 재개 버튼 사유 "이미 순찰 중입니다", 일시정지 결과는 "로봇 응답 없음"
- **문제 3**: 재개 직후 Nav2 컨트롤러가 TF 시각 10 ms 차이로 목표를 포기해 순찰 전체가 "순찰 실패"로 끝남 (내비게이션 쪽)
- 개선할 점: 이미 일시정지일 때 버튼이 눌려 "요청 실패"가 뜸, 연결이 지연·끊김이어도 순찰 카드가 초록 "순찰 중"으로 남음

**참고**
- 시험 도구: `~/limbo_bags/pause_fail/` (`scenarios.cjs`: 시나리오, `proc.sh`: 순찰 노드·Bridge만 끄기·얼리기·다시 켜기, 프로세스 그룹 단위)
- 시뮬레이션 중 `collision_monitor`가 카메라 점군이 15초 늦다고 계속 경고함 (시뮬레이션 부하). 이번 시험 결과와는 관계없음

---

## 2026-10-13 (26) Bridge: 로봇 위치를 TF로 읽음 (멈춰 있어도 위치 표시)

**할 일**
- **Bridge 다시 빌드**: `cd ~/limbo/relay_prog && venvs/bridge/bin/python -m colcon build --symlink-install --base-paths src` (의존성 `tf2_ros` 추가, ROS Jazzy에 이미 있음)
- 직접 만든 `bridge.yaml`을 쓰면 `control:`에 `map_frame: map`, `base_frame: base_footprint` 두 줄을 넣을 것. 없으면 설정 오류로 시작하지 않음

**변경** (설계: `docs/CONTROL_SCREEN.md` B)
- 위치·방향을 `/amcl_pose` 대신 **TF `map → base_footprint`에서 0.5초마다** 읽음. `/amcl_pose`는 로봇이 움직일 때만 나와서, 일시정지·순찰 완료 뒤 화면에 "위치 확인 불가"가 떴음
- `/amcl_pose`는 위치 불확실성(오차 원)에만 씀. 한 번도 못 받았으면(AMCL이 위치를 잡기 전) 위치를 보내지 않음
- 최신 TF가 1초보다 오래됐으면(오도메트리 끊김) 위치를 갱신하지 않음 → 3초 뒤 화면이 "위치 확인 불가"
- `/amcl_pose` 구독을 AMCL과 같은 **transient_local**로 바꿈. volatile이면 Bridge를 나중에 켰을 때 로봇이 움직이기 전까지 마지막 값을 못 받았음
- 텔레메트리 형식(v2)은 그대로. 서버·화면 변경 없음

**시험**
- Bridge 시험 62개 통과 (기존 58 + 새 4: 프레임 이름 검사 3, TF 위치 읽기 1 — AMCL 전·오래된 TF·TF 없음이면 안 보냄)
- 실제 연결(시뮬레이션): **일시정지 중에도 위치가 0.4~1.4초 전 값으로 계속 갱신**되고 화면 로봇이 흐려지지 않음. 재개하면 이동하는 위치를 따라감(2초마다 약 0.5 m), 정지·재개 확인도 그대로 `confirmed`

**참고**
- 처음 고친 뒤 실제 연결에서 위치가 안 나왔음. 원인은 위 transient_local 문제였고, 단위 시험으로는 안 잡혀서 실제 연결에서 찾음

---

## 2026-10-13 (25) 관제 화면: 일시정지·재개 버튼, 지도, 순찰 상태, 상태 한 줄 요약

**할 일**
- **화면 다시 빌드**: `cd ~/limbo/dashboard/ui && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm build` (5분 넘게 걸릴 수 있음, 아래 참고). 서버는 그대로 두고 브라우저만 새로고침하면 됨
- 버튼이 실제 로봇에 명령을 보냄. 시뮬레이션이 아닌 로봇에 붙일 때 조심할 것 (인증은 아직 없음)

**변경** (설계: `docs/CONTROL_SCREEN.md` A-3단계·B·D)
- **실제 화면 버튼 연결**: 일시정지·순찰 재개가 `POST /api/v1/commands`를 부름. 결과 상자(요청 전송 → 로봇 응답 → 상태 확인)는 서버의 명령 단계로 표시

  | 서버 단계 | 화면 |
  |---|---|
  | `queued` / `delivered` / `accepted` | 정지(재개) 요청 중. 진행 중인 칸만 바뀜 |
  | `confirmed` | 정지 상태 확인됨 / 재개 확인됨 (**이때만 성공**) |
  | `rejected`, `service_unavailable` | 정지 요청 실패 / 재개 실패 (사유 표시) |
  | `no_response`, `expired`, `unconfirmed`, `connection_lost` | 정지(재개) 여부 확인 불가 |

  - 연결이 `connected`가 아니거나 요청 처리 중이면 버튼을 잠금. 서버가 거절(409)하거나 서버에 못 보내면 "요청 실패"로 보여 주고 **자동으로 다시 보내지 않음**
  - 재개 버튼은 순찰 노드의 `has_resumable_task`로만 허용 ("이미 순찰 중입니다", "재개할 작업이 없습니다", "순찰 상태를 확인할 수 없습니다")
- **"프로그램 재시작" 버튼 삭제** (실제 화면, `/demo` 모두). 로봇 쪽 기능이 없고 설계에서 범위 밖으로 뺐음. 버튼 이름 "원격 정지" → **"일시정지"**
- **지도 카드** 추가 (`src/map.ts`, App의 `MapCard`): SLAM 지도 위에 순찰 경로(점선), 지점(○ 통과, □ 정지), 지난 지점 흐리게, 다음 목표 강조, 로봇 위치·방향·불확실성 원(표준편차 2배). 위치가 오래되면 로봇을 흐리게 하고 "위치 확인 불가"
- **순찰 카드** 추가: 순찰 중 / 멈추는 중 / 일시정지 / 순찰 완료 / 순찰 실패(사유), 다음 목표(몇 번째/전체)
- **상태 한 줄 요약**(머리글): 정상 / 확인 필요(이유: "카메라 원본 수신 지연" 등) / 연결 끊김. 토픽 4개 표는 맨 아래 "센서 수신 상세"로 접어 둠
- `/demo`도 같은 화면: 그림 없는 지도에 가상 로봇이 순찰 지점을 따라 움직임. 서버는 계속 부르지 않음
- "실제 수신 · 제어 미연동" 표시 삭제

**시험**
- 단위 시험 23개 통과 (기존 17 + 새 6, `src/control.test.ts`): 서버 단계 10종 → 화면 결과(`confirmed`만 성공), 잠금 이유, 재개 허용 기준(속도 무관), 보내기·거절·네트워크 실패 시 한 번만 보냄, 지도 좌표 변환, 한 줄 요약
- 실제 연결(시뮬레이션 → 순찰 노드 → Bridge → 서버 → 화면, 헤드리스 Firefox 화면 캡처): 순찰 중 지도에 로봇·다음 목표 B 표시, 일시정지 요청 → "정지 상태 확인됨" 세 칸 모두 완료, 순찰 카드 "일시정지", 재개 버튼 활성
- 브라우저 시험(e2e, Playwright Chromium) **17개 통과**: 실제 화면에서 일시정지 버튼을 누르면 서버에 명령이 생기고, 로봇이 안 가져가면 5초 뒤 "정지 여부 확인 불가"(성공으로 안 바뀜). `/demo`는 서버를 부르지 않음, 재개 사유, 센서 표 접기, 화면 폭 1440·1024·768·390px에서 가로 넘침 없음, 데모 결과 8가지
- **실제 화면에서 버튼 클릭**(시뮬레이션 연결, Chromium): "순찰 재개" 클릭 → 0.89초 만에 "재개 확인됨", 4초 뒤 속도 0.30 m/s·순찰 카드 "순찰 중". "일시정지" 클릭 → 1.87초 만에 "정지 상태 확인됨", 속도 0.00, 멈춘 동안에도 위치 표시 정상
  - 처음 돌릴 때: `node_modules/.bin/playwright install chromium` (사용자 폴더에 약 100 MB). 실행은 ROS를 source하지 않은 터미널이나 `env -u PYTHONPATH -u AMENT_PREFIX_PATH`로

**참고**
- **빌드가 5분 넘게 걸림**: rollup 4.64.0의 tree-shaking이 오래 걸림 (예전 코드로 빌드해도 같음, 코드 문제 아님). 멈춘 게 아니니 기다릴 것
- 멈춰 있으면 "위치 확인 불가"가 뜨던 문제는 (26)에서 고침

---

## 2026-10-13 (24) 대시보드 서버: 텔레메트리 v2·관제 명령·지도 API

**할 일**
- **서버 의존성 다시 설치** (PyYAML이 늘었음): `cd ~/limbo/dashboard && .venv/bin/python -m pip install -r requirements.lock`
- 서버를 다시 실행하면 적용됨. 화면(UI)은 아직 그대로라 버튼·지도는 다음 단계에서 보임
- 다른 월드로 시험할 때는 `dashboard/config.json`의 `map_yaml`, `waypoints_yaml`을 그 월드 것으로 바꿀 것 (기본은 `human_test_world`)

**변경** (설계: `docs/CONTROL_API_DRAFT.md`)
- 텔레메트리 v1·v2를 모두 받음. v2의 `patrol`(순찰 상태)·`pose`(위치)를 검사해 화면 스냅샷에 넣음. 위치가 3초 넘게 안 오면 `pose.stale: true`
- **관제 명령 API** 추가
  - `POST /api/v1/commands` `{"command": "pause"|"resume"}`: 화면이 부름. Bridge가 연결돼 있고 진행 중인 명령이 없을 때만 접수(아니면 409)
  - `GET /api/v1/commands/next`: Bridge가 부름. 최대 10초 기다렸다 명령을 한 번만 내줌 (남은 유효 시간 `ttl_ms` 포함)
  - `POST /api/v1/commands/{id}/result`: Bridge의 결과 보고. 끝난 명령에 늦게 온 보고는 결과를 바꾸지 않음
- **명령 판정**: `queued → delivered → accepted → confirmed`. 정지는 "명령 뒤에 온 순찰 상태가 `paused` + 실제 속도 정지 기준 미만"일 때만 확인됨, 재개는 "명령 뒤 `patrolling`"(속도로 판단 안 함). 안 되면 `rejected` / `service_unavailable` / `no_response` / `expired` / `unconfirmed` / `connection_lost`. 결과는 알림에 한 번 남김
  - "명령 뒤에 온 상태"는 시각이 아니라 Bridge가 센 순찰 상태 수신 횟수로 판단 (로봇·서버 시계를 비교하지 않는 v1 원칙)
  - 제한 시간: 유효 5초, 응답 5초, 상태 확인 5초 (`config.json`에서 바꿀 수 있음)
- **지도 API**: `GET /api/v1/map`(해상도·원점·크기·waypoint), `GET /api/v1/map.png`. 서버 시작 때 `map_yaml`의 pgm을 PNG로 한 번 바꿔 둠
- 실패하던 서버 시험 4개를 고침 (10-12 motion·odom 일치 검사가 들어온 뒤 시험 데이터를 안 맞춰서 422가 났음)

**시험**
- 서버 시험 54개 통과 (기존 38 + 새 16, `tests/test_control.py`), HTTP 통합 검증 `tools/validate_http.py` 통과
- 실제 연결(시뮬레이션 → 순찰 노드 → Bridge → 서버): 정지 요청 후 **1.13초 만에 `confirmed`**(로봇이 실제로 멈춘 것까지 확인), 두 번째 정지는 `rejected: already paused`, 재개 0.88초 만에 `confirmed`. 지도 302 × 302, waypoint 10개

**참고**
- 서버 시험은 ROS를 source한 터미널에서 돌리면 ROS의 pytest 플러그인 때문에 바로 멈춤. `env -u PYTHONPATH .venv/bin/python -m pytest -q`로 돌릴 것
- 손으로 확인: 서버·Bridge를 띄우고 `curl -X POST -H 'Content-Type: application/json' -d '{"command":"pause"}' http://127.0.0.1:8000/api/v1/commands`, 결과는 `curl http://127.0.0.1:8000/api/v1/state`의 `command`

---

## 2026-10-13 (23) Bridge: 텔레메트리 v2(순찰 상태·위치)와 관제 명령 처리

**할 일**
- **Bridge 다시 빌드** (`relay_prog`에서, YOLO venv 끈 터미널): `venvs/bridge/bin/python -m colcon build --symlink-install --base-paths src`
- **Bridge 실행 전에 limbo 워크스페이스도 source**: `source ~/limbo/limbo/install/setup.bash` (순찰 상태 메시지 `PatrolState`를 읽어야 함). 안 하면 Bridge가 시작하자마자 죽음
- 지금 대시보드 서버는 아직 v1만 받아서 **이 Bridge를 붙이면 422로 거절됨**. 서버 v2 작업이 끝날 때까지는 이전 Bridge를 쓰거나 Mock 서버(`tools/receiver.py`)로 시험

**변경** (설계: `docs/CONTROL_API_DRAFT.md`)
- 텔레메트리를 **v2**로 올림 (`schema_version: 2`). v1 필드는 그대로, 두 객체를 추가
  - `patrol`: 순찰 상태(`/patrol/state`) — 상태, 다음 waypoint, 재개 가능 여부, 이유, **받은 횟수(`update_count`)**
  - `pose`: 로봇 위치(`/amcl_pose`) — x, y, 방향, 위치 불확실성(m)
  - 못 받았거나 값이 이상하면(NaN 등) 전부 `null` (v1 `motion`과 같은 규칙)
- **관제 명령 작업**을 추가함. 텔레메트리와 연결을 따로 씀
  - 서버에 `GET /api/v1/commands/next`로 명령을 묻고(최대 10초 기다림), 받으면 `/patrol/pause` 또는 `/patrol/resume`을 한 번 부름(3초 제한)
  - 결과(`accepted` / `rejected` / `no_response` / `service_unavailable` / `expired`)를 `POST /api/v1/commands/{id}/result`로 **한 번만** 보냄. 다시 부르거나 다시 보내지 않음
  - 서버가 준 유효 시간(`ttl_ms`)이 지난 명령은 부르지 않음 (끊겼다 붙었을 때 오래된 정지가 뒤늦게 실행되지 않게)
- 설정 `bridge.yaml`에 `control:` 블록 추가 (토픽·서비스 이름, 기다리는 시간)
- Mock 서버(`tools/receiver.py`)가 v1·v2를 모두 받고, 명령 API를 흉내 냄 (`POST /api/v1/commands`로 명령을 넣을 수 있음)

**시험**
- 단위 시험 58개 통과 (기존 40 + 새 18, `tests/test_control.py`)
- 실제 ROS 연결(시뮬레이션 → 순찰 노드 → Bridge → Mock 서버): 정지 명령이 서비스 12 ms 만에 접수되고 2.5초 뒤 상태 `paused`·속도 0. 재개도 정상

**참고**
- 시험 방법
  ```bash
  cd ~/limbo/relay_prog
  source /opt/ros/jazzy/setup.bash; source ~/limbo/limbo/install/setup.bash
  venvs/bridge/bin/python -m pytest tests -q
  ```
- 손으로 확인: Mock 서버를 띄우고 Bridge를 붙인 뒤 `curl -X POST -H 'Content-Type: application/json' -d '{"command":"pause"}' http://127.0.0.1:8000/api/v1/commands`, 결과는 `curl http://127.0.0.1:8000/status`

---

## 2026-10-12 (22) 순찰 일시정지·재개 서비스와 순찰 상태 토픽

**할 일**
- **빌드 필요** (메시지가 새로 생김): `build_limbo`. `limbo_interfaces`를 빌드하지 않으면 순찰 노드가 `PatrolState`를 못 찾아 바로 죽음

**변경**
- 순찰 노드에 서비스 두 개를 추가했음. 관제 화면의 일시정지·순찰 재개 버튼이 쓸 것 (설계: `docs/CONTROL_SCREEN.md` A)
  - `/patrol/pause`: 순찰 중이면 Nav2 주행을 취소하고 멈춤
  - `/patrol/resume`: 멈춘 곳부터 이어서 순찰. 이미 지난 waypoint로 되돌아가지 않음
  - 둘 다 `std_srvs/srv/Trigger`. 안 되는 경우는 사유와 함께 거절함 (`already paused`, `not patrolling`, `already patrolling`, `nothing to resume` 등)
- 순찰 상태를 `/patrol/state`(`limbo_interfaces/msg/PatrolState`, 새 메시지)로 냄: 상태(`patrolling`·`paused`·`completed`·`failed` 등), 다음 waypoint, 재개 가능 여부, 바뀐 시각·이유. 늦게 붙은 구독자도 마지막 상태를 바로 받음
- 명령을 안 보내면 동작은 전과 같음 (Nav2가 실패·취소하면 순찰 실패로 끝나는 것도 같음)
- `Ctrl+C`로 끌 때 나던 오류 메시지를 없앴음
- 위치 추정이 30초 안에 준비되지 않으면 상태를 `failed`(이유 `localization not ready (30 s)`)로 내고 끝냄. 전에는 `waiting_localization`에 멈춘 채 오류로 종료돼 관제 화면이 이유를 알 수 없었음 (종료 코드 1은 그대로)

**시험** (시뮬레이션 `human_test_world`)
- 주행 중 정지 7번 모두 성공. **정지 요청부터 실제로 멈출 때까지 평균 0.55초, 최대 0.66초**
- 정지·재개 5개 동시, 0.1~0.5초 간격 섞어 40번: 접수는 매번 1개만, 응답 없음 0번, 응답 평균 4 ms. 마지막 명령대로 상태가 정리되고 노드가 멈추지 않음
- 15초마다 정지·재개하며 순찰 5번 모두 완주 (정지 없음 5번과 시간 차이는 멈춘 시간만큼). stop 지점 대기 중 정지 후 재개도 다음 구간으로 정상 진행

**참고**
- 서비스를 직접 시험해 보려면
  ```bash
  ros2 topic echo /patrol/state
  ros2 service call /patrol/pause std_srvs/srv/Trigger
  ros2 service call /patrol/resume std_srvs/srv/Trigger
  ```
- (21) 전에는 정지 지점 0.2~0.4 m 앞 갇힘이 정지·재개 회차에서 더 자주 났음(5번 중 3번 5~7분). (21)을 합친 뒤에는 0번
- 아직 확인 못 한 것: 구간 사이(대기 끝 → 다음 구간 출발 직전)에 정지가 들어오는 순간. 코드로는 막아 둠
- 관제 화면 버튼과는 아직 연결 안 됨 (Bridge·서버 작업이 다음 단계)

---

## 2026-10-12 (21) 순찰 정지 지점 방향 수정 정리 (원작자 PR #9)

**할 일**
- 없음 (waypoint yaml만 바뀜. 순찰 노드만 다시 실행하면 됨. 설치 폴더가 symlink가 아니면 `build_limbo`)

**변경 (원작자 PR #9)**
- 순찰 중 정지 waypoint 0.3 m 앞에서 멈춘 뒤 실패하던 문제를 원작자가 해결했음. `test_waypoints.yaml`의 정지 지점 C·G·J의 방향(yaw)을 들어가는 방향으로 바꿨음 (C −124°, G −89°, J −179°)
  - 원인: 목표가 로봇 옆·뒤에 남았는데 목표 방향은 이미 맞아 있어서, 후진이 꺼진 MPPI가 돌아서 다가가는 것보다 멈추는 쪽을 골랐음
  - 확인: 원래 월드 순찰 10/10 완주

**정리 (ktj)**
- `docs/TROUBLESHOOTING.md`에 위 문제를 "증상 → 원인 → 해결 → 확인"으로 추가하고 원작자 문서 두 개(`NAV2_NEAR_GOAL_FAILURE_2026-10-12.md`, `NAV2_YAW_10_RUN_VALIDATION_2026-10-12.md`)를 링크했음
- `docs/KNOWN_ISSUES.md`에서 해결된 안내 단락을 빼고, 원작자가 남긴 남은 문제 두 개를 표로 정리했음 (사람이 아주 가까울 때 MPPI 경고, launch 고정 시간 때문에 가끔 시작 실패)

**참고**
- **새 waypoint 파일을 만들 때 정지 지점의 yaw는 들어가는 방향으로** 둘 것. yaml의 yaw는 도 단위

---

## 2026-10-12 (20) 헛돎 감시 오탐 방어 수정

**할 일**
- 없음 (Python·yaml만 바뀜. 시뮬레이션만 다시 띄우면 적용됨)

**변경**
- 헛돎 확정에 필요한 연속 의심을 1초(0.5초 × 2) → **2초(0.5초 × 4)**로 늘렸음. 사람이 지나가며 생기는 순간적인 오판을 거름 (`slip.consecutive_windows: 4`)
- 두 스캔의 점이 잘 안 맞으면(사람이 가리는 등) 그 구간은 판단을 보류함 (`slip.min_inlier_ratio: 0.8`)
- 녹화 데이터로 확인: 상자에 막힌 진짜 헛돎은 1초 늦게 잡을 뿐 모두 감지, 사람 경로·사람 10명 방에서 오탐 0

**참고**
- 팀원 환경의 오탐 원인은 아직 확정 못 했음. 이번 수정 후에도 오탐이 나면 터미널의 `[wheel_slip_monitor]: SUSPECT/SLIP: wheel ... m, scan ... m` 줄을 보내 주세요
- 주행 취소는 계속 꺼져 있음 (진짜로 막혀도 로봇이 계속 밈). 오탐이 사라진 게 확인되면 다시 켤 예정

---

## 2026-10-12 (19) 순찰 waypoint 파일을 월드별로 고르기

**할 일**
- **빌드 한 번 필요** (`aischool_waypoints.yaml`이 설치되도록): `build_limbo`
- 로컬에서 `patrol_node.py`의 파일 이름을 바꿨거나 `test_waypoints.yaml`을 학원 좌표로 덮어썼다면, pull 전에 그 수정을 되돌리거나 따로 보관할 것 (충돌 날 수 있음)

**변경**
- 순찰 노드가 `test_waypoints.yaml`만 읽도록 코드에 고정돼 있어서 학원 waypoint로는 순찰할 수 없었음. `waypoints` 파라미터로 파일을 고르게 했음. 기본값은 그대로 `test_waypoints.yaml`
  - human_test_world: `ros2 run limbo_patrol patrol_node --ros-args -p use_sim_time:=true`
  - 학원 2층: `... -p waypoints:=aischool_waypoints.yaml`
  - 서점: `... -p waypoints:=waypoints.yaml`
- 시뮬레이션에서 학원 waypoint로 순찰이 시작되는 것을 확인했음

**참고**
- 월드별 파일 표와 새 파일 추가 방법은 README "순찰"
- `patrol_node.py`는 아직 리팩터링 전이라 코드 스타일 검사(flake8, pep257)가 실패함 (이번 수정 전부터)

---

## 2026-10-12 (18) launch에 사람 인식 모델 선택 인자 추가

**할 일**
- 없음 (launch 파일만 바뀜)

**변경**
- `start_simulation.launch.py`에 `person_model` 인자를 추가했음. 경로를 주면 yaml을 고치지 않고 그 모델로 사람 인식을 돌림. 비우면(기본) 지금처럼 `person_detector.yaml`의 yolo11n
  ```bash
  ros2 launch limbo_bringup start_simulation.launch.py world:=aischool_2f_scenarios map:=aischool_2f_map \
    person_model:=$HOME/limbo/human-leg/runs/person_leg_stage1/weights/best.pt
  ```
- 하반신 모델은 아직 학습 중이라 기본으로 바꾸지 않았음. 새 모델이 나오면 경로만 바꿔 같은 시험을 반복하면 됨

---

## 2026-10-12 (17) 사람 거리 계산 수정 (다리만 보일 때), 하반신 모델 평가

**할 일**
- 없음 (Python·yaml만 바뀜. 시뮬레이션만 다시 띄우면 적용됨)

**변경**
- 사람까지 거리를 박스 가운데 영역 depth의 **중앙값** 대신 **가까운 순 25% 위치 값**으로 재게 했음 (`person_detector.yaml`의 `depth.percentile: 25.0`, 50이면 예전과 같음). 다리만 보이는 박스는 가운데가 다리 사이로 보이는 벽이라 중앙값이 벽까지 거리가 됐음
- 팀원의 하반신 모델(`human-leg/.../best.pt`)을 시뮬레이션에서 평가했음. 1.4m 앞에 멈춘 사람(다리만 보임)을 기존 모델은 65%, 하반신 모델은 100% 검출. 이번 거리 수정과 같이 쓰면 4초 동안 끊김 없이 추적함 (자세한 표는 `docs/TROUBLESHOOTING.md`)
- **기본 모델은 그대로 yolo11n**임. 실제 사람으로 확인한 뒤 바꾸기로 했음

**참고**
- 하반신 모델을 시험해 보려면: `ros2 launch ... ` 후 사람 인식 노드의 `yolo.model`을 `~/limbo/human-leg/runs/person_leg_stage1/weights/best.pt`로 지정 (yaml 또는 `-p yolo.model:=...`)
- 사람 몸이 박스 가운데의 25%보다 적으면 다시 배경을 잼 → `docs/KNOWN_ISSUES.md`

---

## 2026-10-12 (16) 전역 costmap에 장애물 층(STVL) 추가

**할 일**
- 없음 (설정 파일만 바뀜. 시뮬레이션만 다시 띄우면 적용됨)

**변경**
- 전역 costmap(경로 계획기가 보는 지도)에 로컬과 같은 STVL 층을 추가했음 (기억 15초). 전에는 지도의 벽만 알아서, 지도에 없는 낮은 상자를 관통하는 경로를 그렸고 로봇이 상자 앞에서 머뭇거리다 부딪혔음
- 시험: 상자 6/6 회피 (전에는 2/2 부딪힘), 위쪽 복도 사람 왕복 24/24 성공

**참고**
- 좁은 복도를 사람이 막으면 경로 계획이 실패하고 재시도함. 이동당 복구 동작이 0~1번에서 약 12번으로 늘고 2~3초 더 걸림. 순찰 시험에서 복구 횟수나 실패가 늘면 알려 주세요
- 로봇 바로 앞(약 1m 안쪽)에 처음부터 있던 낮은 물체는 여전히 못 봄 → `docs/KNOWN_ISSUES.md`
- dev에 합쳐진 PR #7·#8(대시보드, 중계 프로그램, 학습 결과)도 ktj에 받았음

---

## 2026-10-12 (15) 헛돎 감시 시각 어긋남 수정, 오탐 조사 결과

**할 일**
- 없음 (`limbo_monitor`에 Python 파일이 하나 늘었지만 symlink 빌드라 시뮬레이션만 다시 띄우면 됨. 안 되면 `build_limbo`)

**변경**
- 헛돎 감시가 스캔을 **도착한 순간의 최신 바퀴 odom**과 비교하고 있었음. 스캔은 포인트클라우드 변환을 거쳐 늦게 도착하므로, 멈췄다 출발하는 순간에는 스캔은 아직 정지인데 바퀴는 출발한 상태라 헛돎으로 보일 수 있었음. 최근 2초 odom을 보관해 **스캔을 찍은 시각의 odom**과 비교하도록 고쳤음
- 상자에 막혀 바퀴만 도는 진짜 헛돎은 수정 후에도 그대로 감지됨

**참고 (팀원이 겪은 오탐 조사)**
- 시뮬레이션에서 사람 경로, `human_test_world`(사람 10명), 스캔 지연 0.5초 재현까지 해 봤지만 오탐을 재현하지 못했음. 원인 확정에는 오탐이 날 때의 로그가 필요함
  - 터미널의 `[wheel_slip_monitor]: SUSPECT: wheel ... m, scan ... m` / `SLIP: ...` 줄
  - 가능하면 그 상황 녹화: `ros2 bag record /scan /odom /ground_truth/odom /wheel_slip -o slip_case`
- **주의**: 주행 취소를 꺼 둔 지금은 로봇이 진짜로 막혀도 멈추지 않음 (시험에서 상자를 2분 동안 계속 밀었음). Nav2의 "진전 없음" 판단도 바퀴 odom을 봐서 막지 못함 → `docs/KNOWN_ISSUES.md` "바퀴 헛돎 감시"

---

## 2026-10-12 (14) 헛돎 감시 주행 취소 임시로 끔, 낮은 장애물 시험 월드

**할 일**
- **빌드 한 번 필요** (`limbo_evaluation`에 새 파일): `build_limbo`

**변경**
- `wheel_slip_monitor.yaml`의 `cancel_navigation_on_slip`을 `false`로 바꿨음. 사람이 로봇 가까이 지나가면 스캔 비교가 속아 헛돎으로 잘못 판단하고 주행을 취소하던 문제 때문임 (팀원 주행 시험과 시뮬레이션에서 확인). 감지, `/wheel_slip` 발행, 로그는 그대로임
- 시나리오 월드 홀 서쪽에 지도에 없는 낮은 상자 2개(0.1m, 0.3m)를 두었음. 측정 도구 CSV에 상자까지 최소 거리(`min_obstacle_distance_m`)와 닿은 시간(`obstacle_contact_time_s`)이 추가됐음
- dev에 병합된 순찰 노드 개선(PR #6)을 ktj에도 받았음

**참고**
- 지금 설정(로컬 costmap에만 장애물 층)으로는 로봇이 0.1m 상자에 부딪힘. 전역 costmap에 장애물 층을 넣으면 피하지만 좁은 복도에서 사람 때문에 경로 계획이 자주 실패해서, 반복 시험 후 정할 예정
- 헛돎 오탐 수정과 "진짜로 막혔을 때 취소할지"는 `docs/KNOWN_ISSUES.md` "바퀴 헛돎 감시"

---

## 2026-10-07 (13) 멈춘 사람 예측 개선, 센서 사각지대 기록

**할 일**
- 없음 (Python·yaml만 바뀜. 시뮬레이션만 다시 띄우면 적용됨)

**변경**
- `person_detector`가 멈춘 사람을 빨리 알아채게 했음. 최근 0.6초 동안 측정 위치가 0.15m 미만으로 움직였으면 속도를 0으로 하고 위치를 최근 측정 평균으로 맞춤 (`person_detector.yaml`의 `tracking.stop_window`, `tracking.stop_max_displacement`)
  - 멈춘 뒤 1~2초 추정 속도 0.37 → 0.03m/s. 걷는 사람 출력은 수정 전과 같음
- 검출이 잠깐 끊겼다 다시 잡힐 때 "그 자리에 멈췄을 경우"도 고려해 같은 사람으로 재연결하게 했음 (전에는 새 ID가 붙었음)
- 시나리오 분석에서 찾은 센서 사각지대를 `docs/KNOWN_ISSUES.md` "센서 배치"에 수치와 함께 기록했음
  - 카메라가 낮아(0.5m, 수평) 2m 안의 사람은 다리만 보여 YOLO 검출이 끊김
  - MID-360 아래쪽 시야가 −7°라 0.1m 방지턱은 5.1m, 0.3m 상자는 3.5m보다 가까우면 안 보임
- URDF 카메라 주석이 실제 값(0.50m, 수평)과 달라서 고쳤음

**참고**
- 센서 높이·기울기는 하드웨어 담당과 정해야 함. 결정에 필요한 표가 KNOWN_ISSUES에 있음
- 실제 카메라는 위치가 시뮬레이션보다 많이 흔들리므로, 서 있는 사람이 걷는 것으로 나오면 `stop_max_displacement`를 키울 것

---

## 2026-10-07 (12) 주행 평가 기록 도구 `limbo_evaluation`

**할 일**
- **빌드 한 번 필요** (새 패키지, 로봇 모델에 정답 위치 플러그인 추가): `build_limbo`

**변경**
- Nav2 Goal이 끝날 때마다 주행 지표를 CSV 한 줄로 남기는 `nav_recorder`를 추가했음. launch에 `record:=true`를 붙이면 켜지고, 결과는 `~/limbo_results/nav_<월드>_<날짜_시각>.csv`에 쌓임
  - 결과, 시간, 주행 거리, 사람과의 최소 거리와 개인 공간(0.5m) 침범 시간, 위치 추정 오차, 복구 횟수, 컨트롤러 주기 경고, 헛돎 감지
  - 위치 추정 오차는 TF(`map → base_footprint`)로 재서 AMCL을 다른 방식으로 바꿔도 같은 기준으로 비교됨
  - 열 설명은 README "주행 평가 기록"
- 로봇 모델에 Gazebo 정답 위치 플러그인을 달고 `/ground_truth/odom`으로 브리지했음. 평가 전용이고 주행 노드는 쓰지 않음
- 확인: `aischool_2f_scenarios`에서 왕복 4번 → CSV 4줄, 위치 오차 최대 0.11~0.12m, 서 있는 사람 옆 0.70m. 나란히 걷는 두 사람이 로봇에 0.33m까지 붙은 순간과 그때의 복구 1번도 기록됐음

**참고**
- 시뮬레이션 전용이고, 지도 원점과 Gazebo 월드 원점이 같다고 가정함 (`human_test_world`, `aischool_2f*`는 같음)
- 이전에 임시 스크립트로 잰 AMCL 오차(0.24~0.28m)는 정답을 느리게 받아 시각이 다른 위치끼리 비교해서 부풀려진 값이었음

---

## 2026-10-07 (11) MPPI 주기 저하 해결 확인, LiDAR 5Hz 원인 정정

**할 일**
- 없음 (문서만 바뀜)

**변경**
- 어제 기록한 MPPI 컨트롤러 주기 저하(20Hz → 6.5Hz, 주행 실패)를 다시 시험했음. Gazebo 창을 켠 기본 상태에서 홀 ↔ 왼쪽 복도 왕복 4/4 성공, 주기 경고는 1번(12.5Hz)뿐이었음. 오늘 줄인 CPU(헛돎 감시, 사람 인식) 덕분이라 KNOWN_ISSUES에서 TROUBLESHOOTING으로 옮겼음
- LiDAR가 10Hz 설정인데 5Hz로 나오는 문제는 Gazebo 창을 꺼도 같고 GPU도 남아서 부하 때문이 아니었음. 원인 추정을 Gazebo 센서 스케줄링으로 고쳤음

**참고**
- 주기 경고 확인 방법: `~/.ros/log/controller_server_*.log`에서 `Control loop missed` 줄 수 세기

---

## 2026-10-07 (10) 시나리오 월드 추가, Gazebo 창 끄기 옵션

**할 일**
- **빌드 한 번 필요** (새 월드 파일 설치): `build_limbo`

**변경**
- 시험용 월드 `aischool_2f_scenarios`를 추가했음. 같은 학원 2층 건물·지도에 사람 6명이 장소마다 상황 하나씩을 반복함
  - 로봇 시작 위치 1.6m 앞에 와서 4초 멈춤 / 홀에서 오른쪽 복도로 90° 꺾음 / 왼쪽 복도 벽에 붙어 서 있음 / 위쪽 복도에 둘이 0.6m 간격으로 천천히 / 왼쪽 아래 복도를 빨리(1.6m/s)
  - 모두 정해진 시간표대로만 움직이고 로봇에 반응하지 않음 (매번 같은 상황을 재현하려고)
  - 실행: `ros2 launch limbo_bringup start_simulation.launch.py world:=aischool_2f_scenarios map:=aischool_2f_map`
  - 기존 `aischool_2f` 월드는 그대로임. 경로는 `tools/aischool_2f/gen_world.py`의 `SCENARIO_PATHS`
- launch에 `gui` 옵션을 추가했음. `gui:=false`면 Gazebo 3D 창 없이 서버만 뜸. 센서·사람·주행은 그대로이고 Gazebo CPU가 285% → 110%로 줄었음. 기본은 켬이라 지금처럼 쓰면 됨

**참고**
- 창을 끄면 Gazebo가 가벼워져 depth 카메라가 원래 설정대로 15Hz로 나오고(전에는 약 10Hz), 그만큼 person_detector가 프레임을 더 처리해 CPU가 늘어 보일 수 있음
- 멈추거나 꺾는 사람은 예상 위치와의 차이가 평균 0.4m로, 직진하는 사람(0.15m)보다 큼. 이걸 시험하려고 만든 시나리오이고 분석은 다음 작업

---

## 2026-10-06 (9) person_detector CPU 감소 (sim time 해제)

**할 일**
- 없음 (Python·launch 파일만 바뀜. symlink 빌드라 시뮬레이션만 다시 띄우면 적용됨)

**변경**
- `person_detector`가 예측 메시지(`/person_detector/predictions`) 시각을 노드 시계 대신 **그 카메라 이미지를 찍은 시각**으로 찍게 했음. 노드 시계를 안 쓰게 돼서 launch에서 `use_sim_time: False`로 실행함. Gazebo `/clock`(초당 약 740번)을 받지 않아 CPU가 약 30%p 줄었음 (나란히 띄운 비교 139% → 109%)
- 녹화 bag 재생 비교에서 출력 870프레임이 기존과 같았음. human_layer가 예측의 나이를 잴 때도 카메라 시각이 더 정확함

**참고**
- 실행기(`MultiThreadedExecutor`)의 남는 스레드가 헛도는 문제(약 20%p)도 찾았지만, 고치는 방법마다 처리량이나 TF 실패 횟수가 바뀌어 적용하지 않았음. 시도한 내용은 `docs/KNOWN_ISSUES.md`

---

## 2026-10-06 (8) 헛돎 감시 CPU 감소, 안 쓰는 LiDAR 브리지 삭제

**할 일**
- 없음 (launch·설정 파일만 바뀜. 시뮬레이션만 다시 띄우면 적용됨)

**변경**
- `wheel_slip_monitor`를 `use_sim_time: False`로 실행하게 했음. sim time을 켜면 Gazebo `/clock`(초당 약 740번)을 Python이 전부 처리해 CPU를 50% 썼음 → 5%. 판단 로직은 스캔 메시지 시각만 써서 동작은 같음
- 아무도 구독하지 않던 MID-360 LaserScan 브리지(`mid360`)를 삭제했음. 포인트클라우드(`mid360/points`)와 `/scan`은 그대로. CPU 효과는 측정 오차 수준

**참고**
- 같은 `/clock` 부담이 sim time이 꼭 필요한 `person_detector`에도 있음. Gazebo 물리 스텝을 늘리는 방법을 검토 중 (`docs/KNOWN_ISSUES.md`)
- CPU를 잴 때는 Gazebo가 일시정지 상태가 아닌지 먼저 확인할 것 (`docs/TROUBLESHOOTING.md`)

---

## 2026-10-06 (7) AMCL beamskip, 왼쪽 복도 멈춤 해결

**할 일**
- 없음 (설정 파일만 바뀜. 시뮬레이션만 다시 띄우면 적용됨)

**변경**
- `amcl.yaml`에 beamskip을 적용했음 (`laser_model_type: likelihood_field_prob`, `do_beamskip: true`). 사람처럼 지도에 없는 장애물에 맞은 빔을 위치 계산에서만 뺌. 장애물 회피는 모든 빔을 그대로 씀
- 원인: 좁은 복도에서 걷는 사람과 마주치면 AMCL 파티클이 앞뒤로 퍼졌다가, 복도 끝 교차로에서 위치가 크게 튀었음 (방향 51~68° 오차)
- 확인: 같은 마주침 시험에서 방향 오차 1.5° 이내, `aischool_2f` 왼쪽 복도 Nav2 왕복 4/4 성공
- 조사 과정과 배제한 원인은 `docs/TROUBLESHOOTING.md`에 있음

**참고**
- 좁은 복도(1.54m)에서 제자리 회전 실패, CPU가 몰릴 때 MPPI 주기 저하(20Hz → 6.5Hz)를 새로 찾아 `docs/KNOWN_ISSUES.md`에 기록했음
- `Ctrl+C` 후 Gazebo 서버가 남는 경우가 있음. 다시 띄우기 전에 `ps aux | grep "gz sim"`으로 확인

---

## 2026-10-06 (6) 왼쪽 복도 멈춤 조사 기록

**할 일**
- 없음 (문서만 바뀜)

**변경**
- `aischool_2f` 왼쪽 복도 멈춤 문제를 조사해 `docs/KNOWN_ISSUES.md`에 기록했음. 원인은 AMCL 내부로 좁혀졌고(odom·EKF·지도·스캔은 정상), 다음 실험 계획을 적어 두었음
- `wheel_slip_monitor` CPU 사용량(약 54%)과 LiDAR 실제 주기(약 5Hz) 문제를 추가했음

**참고**
- `aischool_2f`에서 왼쪽 복도 위쪽(y 5~7.5)을 지나는 Goal은 아직 실패할 수 있음

---

## 2026-10-06 (5) README 새로 작성, requirements.txt 복원

**할 일**
- 기존 팀원은 없음
- 새로 설치하는 사람은 README "설치"를 위에서부터 따라 하면 됨

**변경**
- README를 설치 → 실행 → 구성 순서로 새로 썼음. 문서 안내, 월드 선택표, 패키지·토픽·튜닝 파일 위치를 넣었고, 원작자의 하드웨어 조정 메모는 그대로 살렸음
- PR #5에서 지워졌던 `requirements.txt`를 되살렸음 (`setuptools<80` 고정 추가). 지워진 상태에서는 README대로 YOLO 환경을 만들 수 없었음
- 설치 단계에 `ros-dev-tools`(colcon), `rosdep`, HTTPS clone, GPU용 torch 설치 명령을 넣었음
- 새 셸·새 venv에서 README 명령 그대로 clone → venv → 빌드 → 테스트까지 통과하는 것을 확인했음 (apt 단계와 새 설치본의 시뮬레이션 실행은 미확인)

---

## 2026-10-06 (4) 바퀴 헛돎 감시, 문제 해결 기록

**할 일**
```bash
build_limbo
```

**변경**
- 바퀴 헛돎 감시 노드 `limbo_monitor/wheel_slip_monitor`를 추가했음. 0.5초마다 바퀴 이동량과 LiDAR 스캔(ICP) 이동량을 비교해, 바퀴만 돌고 로봇이 안 움직이면 `/wheel_slip`을 True로 내고 Nav2 Goal을 취소함. 시뮬레이션 실행 시 자동으로 같이 뜸
- 시험 결과: 벽에 밀어붙였을 때 1.0초 만에 감지, Goal 취소 0.017초. `aischool_2f` 복도 4분 주행(22m 왕복 포함) 오경보 0건
- 긴 복도처럼 스캔으로 앞뒤 이동을 알 수 없는 구간에서는 판단을 보류함
- 튜닝값은 `limbo_monitor/config/wheel_slip_monitor.yaml`
- 겪은 문제의 원인·해결 과정을 모은 `docs/TROUBLESHOOTING.md`를 추가했음

**참고**
- `aischool_2f` 왼쪽 복도 (−5.8, 4.4) 부근에서 Nav2가 Goal을 포기하고 멈추는 문제가 있음. 원인 조사 중 (`docs/KNOWN_ISSUES.md`)

---

## 2026-10-02 (3) IMU 추가, 바퀴 odom + IMU 융합(EKF)

**할 일**
```bash
sudo apt install ros-jazzy-robot-localization   # 처음 한 번만
build_limbo
```

**변경**
- 시뮬레이션 로봇에 MID-360 내장 IMU를 추가했음 (`/imu`, 200Hz, 노이즈·바이어스 포함)
- 바퀴 odom(전진 속도)과 IMU(회전 속도)를 EKF로 합쳤음. 회전 오차가 360° 회전 기준 31°에서 0.4°로 줄었음
- `odom → base_footprint` TF는 이제 EKF(`ekf_filter_node`)가 발행함. Gazebo diff-drive TF는 브리지하지 않음

**참고**
- 로봇이 걸려서 바퀴만 헛도는 문제는 IMU로도 못 잡아서 남아 있음 (`docs/KNOWN_ISSUES.md`)
- 바퀴 마찰 계수(0.5)가 낮아 회전 시 미끄러짐. 회전 오차의 원인으로 추정

---

## 2026-10-02 (2) 학원 2층 월드, 월드·지도 선택 인자

**할 일**
```bash
build_limbo
```

**변경**
- 피난안내도 사진으로 학원 2층 월드 `aischool_2f`를 만들었음 (교실 7개, 홀, 복도, 걷는 사람 3명). 같은 도면으로 만든 지도도 있어서 SLAM 없이 바로 주행 가능함
  ```bash
  ros2 launch limbo_bringup start_simulation.launch.py world:=aischool_2f map:=aischool_2f_map
  ```
- launch에 `world`, `map` 인자를 추가했음. 인자 없이 실행하면 기존 `human_test` 그대로임
- 월드 생성 스크립트를 `limbo_simulation/tools/aischool_2f/`에 넣었음. 축척은 교실 깊이 실측(약 6.1m)과 복도 폭(약 1.5m)으로 맞췄음
- 미해결 문제 목록 `docs/KNOWN_ISSUES.md`를 만들었음

**참고**
- 새 월드 주행 중 로봇이 걸려 바퀴만 헛돌면 AMCL이 위치를 놓치는 문제를 확인했음

---

## 2026-10-02 (1) person_detector 리팩터링, 버그 수정

**할 일**
```bash
build_limbo
```

**변경**
- person_detector를 기능별 파일로 나눴음 (`tracking`, `kalman`, `motion`, `intent`, `geometry`, `visualization`, `messages`). 같은 rosbag으로 전후 출력이 같은 것을 확인했음
- 튜닝값을 `limbo_perception/config/person_detector.yaml`로 뺐음. 빌드 없이 바꿀 수 있음
- 시뮬레이션을 켜면 2D Pose Estimate 없이 바로 주행 가능함 (AMCL 초기 위치 = 스폰 위치)
- Gazebo가 일시정지 없이 바로 재생됨
- person_detector CPU 사용량을 줄였음 (시뮬레이션 중 약 775% → 116%). torch·numpy 스레드 풀이 서로 헛돌던 문제였음
- 새로 clone하면 `limbo_description` 빌드가 실패하던 문제를 고쳤음
- `.gitignore`에 `__pycache__`, `*.pyc`를 추가했음

**참고**
- 리팩터링 전 원본은 `kkh` 브랜치에 있음

---

# 리팩터링 이전 (2026-08-18 ~ 2026-09-30, 원작자 작업)

더 이상 추가하지 않는 기록이다. 이 문서를 만들기 전 커밋을 보고 2026-10-02에 정리했음. 커밋 메시지가 짧은 경우("수정본", "지금 안됨" 등)는 바뀐 파일로 내용을 추정했음. 틀린 부분은 작성자가 고쳐 주면 됨.

## 2026-09-30 PR #5 (kkh → dev)

- 폴더 구조를 다시 평평하게 되돌렸음 (`src/common`, `src/navigation`, `src/perception` → `src/limbo_*`)
- Nav2 파라미터를 축별 yaml 조합에서 `limbo_navigation/config/nav2_params.yaml` 한 파일로 되돌렸음
- `human_layer`를 `limbo_human_costmap`에서 `limbo_navigation`으로 옮기고, 오래된 예측을 버리는 `max_prediction_age` 검사를 넣었음
- person_detector가 RGB와 depth를 `ApproximateTimeSynchronizer`로 같은 시점끼리 묶고, TF를 이미지 시각으로 조회하게 바꿨음. 실행기를 `MultiThreadedExecutor`(2스레드)로 바꿨음
- patrol_node를 stuck 재시도 로직이 없는 단순 버전(232줄)으로 바꿨음. stuck 로직이 있던 이전 버전은 `.codex-backups/`에 백업으로 남아 있음
- `limbo_patrol/config/test_waypoints.yaml` 추가
- `limbo/requirements.txt`, `limbo/README.md`를 지우고 루트 `README.md`를 정리했음

## 2026-09-23 PR #4, 구조 개편, ktj 트랙

- 폴더를 담당별로 나눴음 (`src/common`, `src/navigation`, `src/perception`). Nav2 파라미터를 축별 yaml로 쪼개 launch에서 조합하게 했음 (`config/common`, `costmap`, `planner`, `controller`, `localization`, `robot`)
- `human_layer`를 별도 패키지 `limbo_human_costmap`으로 분리했음
- YOLO용 `requirements.txt`, 상세 `limbo/README.md`(주행·인지 투트랙 가이드) 추가
- (ktj) Gazebo diff-drive 각속도·각가속도 한계를 Nav2 값(1.8 / 3.0)에 맞췄음. MPPI 사람 회피 오버레이를 `mppi.yaml`로 흡수했음
- (ktj) `docs/PROJECT.md`(프로젝트 개요와 할 일) 추가
- (kkh) patrol_node에 stuck 감지 후 재시도 로직 추가(9/30 PR #5에서 단순 버전으로 다시 바뀜), `human_test_world` 걷는 사람을 1명에서 10명으로 늘림, MPPI 값 조정

## 2026-09-22 1차 테스트

- MPPI 회전 한계를 올렸음 (`wz_max` 1.0 → 1.8, `az_max` 1.5 → 4.0), `visualize` 끔
- 기본 월드를 `bookstore_world`로 바꿔 시험했음
- README에 alias 사용법 추가

## 2026-09-21 사람 회피 주행

- `human_layer`가 예측 시점별로 cost를 다르게 주게 확장했음 (가까운 미래일수록 높게)
- 사람 회피 시험용 `human_test_world`와 `human_test_map` 추가

## 2026-09-18 사람 이동 경로에 cost 부여

- 사람 예측 메시지 `limbo_interfaces/PersonPrediction(Array)` 추가
- local costmap 플러그인 `human_layer` 첫 버전 추가 (예측 위치에 cost 부여)
- person_detector가 사람별 예측 경로를 발행하게 했음

## 2026-09-17 순찰, 장애물 레이어 변경

- `limbo_patrol` 패키지 추가 (waypoint 순찰, `config/waypoints.yaml`)
- local costmap 장애물 레이어를 STVL(3D 복셀)로 바꿨음. 이전 설정은 `nav2_params_before_stvl.yaml`로 남겼음

## 2026-09-14 사람 인식

- `limbo_perception` 패키지와 `person_detector` 첫 버전 추가 (YOLO + RGB-D depth로 사람 3D 위치 추정)

## 2026-09-11 RGB-D 카메라, self filter

- 로봇에 RGB-D 카메라 추가, 카메라 포인트클라우드를 local costmap에 반영했음
- `robot_self_filter` 서브모듈 추가 (LiDAR가 로봇 몸체를 장애물로 보지 않게 함)
- `nav2_params.yaml`, 통합 실행 `start_simulation.launch.py` 정비

## 2026-09-10 README

- 루트 `README.md` 추가

## 2026-09-08 Gazebo 환경, SLAM

- 패키지 4개 추가: `limbo_description`(로봇 URDF), `limbo_simulation`(bookstore 월드, ros_gz 브리지), `limbo_navigation`, `limbo_bringup`
- SLAM으로 `bookstore_map`을 만들고 AMCL 위치 추정(`amcl.yaml`, `localization.launch.py`) 추가
- 처음 커밋에 `build/`, `install/`이 들어갔다가 같은 날 `.gitignore`로 뺐음

## 2026-08-18 저장소 생성

- 저장소와 `CODEOWNERS.txt` 생성
