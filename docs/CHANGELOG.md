# 변경 기록

2026-10-02 리팩터링을 기준으로 나눈다.
- **리팩터링 이후**: ktj 작업. dev에 push할 때마다 맨 위에 추가한다. pull 받은 뒤 해야 할 일은 "할 일"에 적는다.
- **리팩터링 이전**: 원작자 작업. git 히스토리로 정리해 둔 기록이며 더 이상 추가하지 않는다.

---

# 리팩터링 이후 (2026-10-02 ~, ktj 작업)

> 번호는 push 순서다. 2026-10-13에 lab과 ktj를 합치면서 ktj 쪽 (22)~(30) 뒤에 lab 쪽을 (31)부터 이어 붙였다.

## 2026-10-27 (137) `sim_ctl.sh stop`의 잔존 노드 정리 패턴에 `pcl_ros` 추가 — ktj 48의 `rgbd_voxel`(pcl_ros filter_voxel_grid_node)이 launch를 끈 뒤 혼자 남던 것

**할 일**
- 없음

**변경**
- `tools/sim_trials/sim_ctl.sh` `sweep_nodes`: `/opt/ros/jazzy/lib/(…)` 패턴에 `pcl_ros` 추가

**원인과 근거**
- 2026-10-26 ktj 48에서 PC 쪽에 `rgbd_voxel` 노드가 생겼는데 정리 패턴에 없어, 분리 시뮬을 끝낸 뒤 `stop`을 돌려도 `filter_voxel_grid_node`가 남았다(PID로 따로 종료). 남은 노드는 다음 시작 불안정의 주범(2026-10-14)이라 패턴에 넣는다

## 2026-10-26 (136) 분리 시뮬 기록 마무리(문서만): 점군 줄이기(ktj 48 `rgbd_voxel`) 결과와 "PC 런치 재시작이면 Jetson도" 주의를 TROUBLESHOOTING 항목에 덧붙임

**할 일**
- 없음

**변경**
- `docs/TROUBLESHOOTING.md` 분리 시뮬 항목: 남은 CPU·TF 문제의 해결 결과(유선 263 → 49 Mbit/s, Jetson CPU 59 %, TF 지연 최대 116 ms, 1 m 주행 성공)와 재시작 순서 주의

**원인과 근거**
- 구현은 ktj(두 대 분리 구성이 있는 브랜치)에 있고 lab에는 기록만 둔다. 재시작 순서 주의는 Gazebo 재시작으로 시뮬 시계가 0으로 돌아가 Jetson EKF가 멈춘 실측(2026-10-26)

## 2026-10-26 (135) 분리 시뮬에서 로봇이 서 있던 원인 기록(문서만): Jetson UDP 수신 버퍼 208 KB 넘침 → 점군 드롭 → collision_monitor 정지. 커널 상한 64 MB + FastDDS 소켓 버퍼 32 MB로 드롭 0

**할 일**
- B안(점군 양 줄이기: rgbd 219 Mbit/s·Mid-360 74 Mbit/s) 여부와 방식은 PM 결정 대기. Jetson CPU 72 %·TF 지연 튐(최대 388 ms)은 남아 있음

**변경**
- `docs/TROUBLESHOOTING.md` 시뮬레이션 절에 "분리 시뮬: 로봇이 서 있고 TF가 밀림 — Jetson UDP 수신 버퍼 넘침" 항목(증상·원인·해결·확인·재는 법). 설정 파일 자체는 Jetson과 노트북 홈에 있어 저장소 밖

**원인과 근거**
- 유선 263 Mbit/s 점군이 수백 개 UDP 조각으로 몰려 오는데 커널 기본 수신 버퍼가 208 KB라 `RcvbufErrors` 초당 45개. 버퍼를 키운 뒤 10 s 동안 드롭 0, `/imu` 63 → 191 Hz, 1 m 목표 주행 성공. 로봇이 서 있던 나머지 이유는 목표를 아무도 안 보낸 것


## 2026-10-26 (134) `sim_ctl.sh stop`의 잔존 노드 정리 패턴에 `limbo_follow` 추가 — launch를 끈 뒤 follow_node가 혼자 남던 것

**할 일**
- 없음

**변경**
- `tools/sim_trials/sim_ctl.sh` `sweep_nodes`: 실행 파일 경로 패턴 두 곳(install/lib, venv python)에 `limbo_follow` 추가

**원인과 근거**
- 따라가기 패키지(3단계)가 생긴 뒤 정리 패턴을 안 늘려서, 노트북에서 전체 런치를 끈 뒤 `follow_node`가 고아로 남았다(2026-10-26, Jetson 분리 시험 중 노트북 쪽 노드가 DDS에 계속 보임). 남은 노드는 다음 시뮬 시작 불안정의 주범(2026-10-14 기록)이라 패턴에 넣는다

## 2026-10-26 (133) 따라가기 남은 손질 정리(문서만): Smac 2D 팽창 오류 로그는 상류 고정값이라 무해, 서 있을 때 FollowPath 0.5 s 재호출은 PM 결정으로 유지

**할 일**
- 없음(문서만). 코드·설정 변경 없음

**변경**
- `docs/TROUBLESHOOTING.md`: Smac 2D 기동 시 `Inflation layer either not found…` 오류 1줄의 원인(설치된 nav2_smac_planner 1.3.13 `SmacPlanner2D::configure`가 충돌 검사기에 `possible_collision_cost=0.0`을 고정으로 넘김 → 2D 플래너는 설정과 무관하게 1회 찍음, 우리 팽창 0.45 m는 외접 0.39 m 조건도 만족)
- `experiments/2026-10-22_follow_operator/README.md` "남은 것": 위 항목 닫음, FollowPath 2 Hz 재호출은 구조적(길이 0 경로 → 즉시 도착 → 0.5 s 뒤 재호출 = 출발 반응 장치)이라 그대로 두기로 한 결정과 이유, 따라가기가 순찰에 남기는 흔적(플러그인 2개 로드)과 분리 방법 메모

**원인과 근거**
- PM 방침(10-26): 따라가기는 주행(순찰) 쪽에 영향을 최소로 주고 독립적으로 둔다. 재호출을 고치는 두 길(쉬는 시간 늘리기 → 출발 반응 최대 1 s 지연, 방향까지 보는 도착 조건 노드 신설 → fw11에서 고친 look 회전이 깨질 위험) 모두 따라가기 품질을 깎거나 새 노드를 늘려서, 부하가 작은 현재 상태를 유지한다
- 따라가기 전용 요소(`limbo_follow` 패키지, `limbo_follow.xml`, `FollowPlanner`·`FollowOperator` 블록)는 이름이 따로라 순찰의 `GridBased`·`FollowPath`·순찰 트리는 손대지 않았다

## 2026-10-26 (132) 따라가기 주행 손질: 놓침 대응 규칙(돌아보기·내다보기·마지막 자리 보기) + 트리 `TruncatePath` 제거(제자리 목표 yaw가 0°로 먹히던 것) + 따라가기 전용 Smac 2D 플래너(NavFn 시작부 지그재그) — 시뮬 완주 fw14·fw15 2/2(평균 거리 1.9 m, 놓침 최대 3.4 s, 충돌 0)

**할 일**
- pull 뒤 `build_limbo`는 필요 없음(파이썬·yaml·xml만). 노드를 다시 띄우면 적용
- `nav2_params.yaml`에 플래너 `FollowPlanner`가 늘었다(순찰 `GridBased`는 그대로). ktj로 옮길 때 이 파일은 `git diff origin/dev -- nav2_params.yaml`로 확인

**변경**
- `limbo_follow/follow.py`: `lost_plan()` — 놓쳤을 때 hold(가까이, 자세 그대로) / look(마지막 자리가 정면 `look_angle_deg` 25° 밖 → 제자리에서 돌아보기) / search(걷던 운용자 → 가던 방향 `search_ahead` 내다보기) / watch(멈춰 있던 운용자 → 마지막 자리를 보며 서기). `moving_speed` 0.1 m/s, `wrap_angle()`. 단위 시험 5개 추가(10개 통과)
- `follow_node.py`: 마지막으로 봤을 때 걷고 있었는지(`target_moving`) 기억, 놓침 모드를 매 tick lost_plan으로 정하되 look → search/watch로 넘어간 뒤엔 되돌리지 않음, 놓침 로그에 모드·목표·yaw
- `follow.yaml`: `moving_speed`, `look_angle_deg`
- `limbo_navigation/behavior_trees/limbo_follow.xml`: `TruncatePath` 제거(FollowPath가 `{path}`를 그대로 받음), `default_planner="FollowPlanner"`
- `nav2_params.yaml` `planner_server`: `FollowPlanner`(nav2_smac_planner::SmacPlanner2D, tolerance 0.25, use_final_approach_orientation false, smoother 기본)
- `experiments/2026-10-22_follow_operator/`: README "주행 손질" 절(회차 fw11~fw15, 배운 것 10~12), `run2.sh`에 `BAG=1`(코스트맵·cmd_vel·plan 녹화)
- `docs/TROUBLESHOOTING.md` 2026-10-26 항목 2개, `docs/KNOWN_ISSUES.md`에 NavFn 시작부 지그재그 메모, PROJECT.md 2-9

**원인과 근거**(실험 기록에 상세)
- fw9·fw10 규칙 구멍은 lost_plan으로 막았다. 그런데 look 목표를 보내도 로봇이 안 돌았다(fw11): 트리의 `TruncatePath`가 길이 0 경로의 마지막 자세 방향을 atan2(0,0)=0, 즉 지도 +x로 덮어썼다. 제자리 목표의 yaw는 2단계부터 한 번도 전달된 적이 없었다(fw6의 0.6 m 엉뚱한 회전도 이것)
- 그다음 복도 입구(4.9, 2.0)에서 **운용자를 보면서 7 s 서 있다** 놓쳤다(fw12·fw13). bag `/plan`을 보니 NavFn(A*) 경로가 시작점에서 2 cm 폭 지그재그(되돌림 14~43점)로 시작해 MPPI가 제자리에서 떨었다(v 0.00, w ±1.0). 코스트맵은 비어 있었다(목표·경로 앞 1 m 비용 0). fw10~fw13이 전부 이 자리에서 끝났고 fw8은 기다리기 덕에 운용자가 멀어진 뒤 들어가 피했다
- 값을 맞춘 게 아니라 원인을 바꿨다: 지그재그를 안 만드는 플래너(Smac 2D, 경로 다듬기 포함)를 따라가기 트리에만 썼다

**확인**(시뮬 zz_follow2, `run2.sh`, 운용자 0.5 m/s 홀→복도 모퉁이 2개→위쪽 복도 19 m 뒤 정지)

| 회차 | 활성 | 평균 거리 | 0.8~2.5 m | 놓침 | 끝 |
|---|---|---|---|---|---|
| fw11 (규칙만) | 39 s | 3.68 m | 36 % | 1회 14.8 s | 입구에서 look 목표가 안 먹혀 끝 |
| fw12 (+TruncatePath 제거) | 46 s | 4.30 m | 37 % | 1회 14.8 s | 입구에서 7 s 정지 뒤 놓침 |
| fw13 (+모드 되돌림 금지) | 42 s | 4.53 m | 28 % | 3회 14.8 s | 같은 자리, bag으로 원인 확인 |
| fw14 (+Smac 2D) | 157 s | 1.93 m | 90 % | 3회, 최대 3.4 s | **완주**, 운용자가 선 뒤 1.65 m에서 마주 보며 100 s |
| fw15 (같음) | 158 s | 1.87 m | 91 % | 2회, 최대 3.4 s | **완주**, 끝 1.60 m 마주 봄 |

충돌 0(다른 사람 최소 0.89 m), 가로지르는 사람 기다리기 정상. limbo_follow 단위 시험 10개 통과. Smac 2D 기동 시 팽창 반경 오류 로그 한 줄(2D는 중심 비용만 봐 영향 없음, 계획 실패 2회는 재시도로 지나감) — 실험 기록 "남은 것"

## 2026-10-23 (131) 따라가기 3단계(관제): 운용자 등록·시작·정지 버튼 + 따라가기 카드 + 텔레메트리 `follow` — 관제 경로 시뮬 2회 정상, 주행은 2단계 규칙 구멍 2개 발견

**할 일**
- `build_limbo`(`FollowState.msg`에 `enrolled`·`visible` 추가 → limbo_interfaces·limbo_follow·limbo_perception 다시 빌드)
- Bridge: `cd ~/limbo/relay_prog && venvs/bridge/bin/python -m colcon build --symlink-install --base-paths src`. `config/bridge.yaml`의 `control`에 `follow_*` 네 항목이 필수가 됨(없으면 설정 오류로 안 뜸)
- 화면: `cd ~/limbo/dashboard/ui && pnpm install --frozen-lockfile && pnpm build`. 서버는 그대로

**변경**
- `limbo_interfaces/FollowState.msg`: `enrolled`(시작 버튼 잠금 기준), `visible`(안내용). `follow_node`가 채움
- `person_wait_node`: 운용자 제외를 `/follow/state`의 target_id(5 Hz) 대신 `/follow/target`(프레임마다)으로. 인식이 끊겼다 새 번호로 잡히는 순간의 헛 기다리기 제거(2단계 남은 손질)
- Bridge(`relay_prog`): `/follow/state` 구독(reliable·volatile)과 발행자 생존 확인, 텔레메트리 v2 **선택 필드** `follow`(state·active·enrolled·visible·target_id·distance_m·reason·elapsed_s·lost_s·update_count·last_received_at·age_ms), 명령 `follow_start`·`follow_stop`·`follow_enroll` → `/follow/start`·`/follow/stop`·`/follow/enroll`, 결과에 `follow_update_count_at_call`. 시험 receiver 검증기 갱신, 시험 3개 추가(70 통과)
- 서버(`dashboard/server`): `Follow` 모델(v2 선택, v1 거부), 명령 3종 접수, 판정(시작=following·holding, 정지=idle·stopped+로봇 정지, 등록=enrolled), 따라가기 알림(운용자 놓침·주행 실패로 끝나면 경고 지속, 다시 시작하면 닫음), service_unavailable 문구에 노드 이름(순찰·따라가기·카메라). 시험 6개 추가(64 통과)
- 화면(`dashboard/ui`): 제어 카드 아래 따라가기 버튼 3개(잠금 사유: 미등록·이미 따라가는 중·따라가는 중 아님), **순찰 재개는 따라가는 동안 잠금**, 요약 줄에 따라가기 카드(상태·거리·등록·보임·등록 안내). 가상(/demo)은 순찰 명령만. 시험 4개 추가(29 통과), tsc·빌드 통과
- 문서: `docs/CONTROL_API_DRAFT.md`(follow 블록·명령·판정·알림), `docs/CONTROL_SCREEN.md` E절, PROJECT.md 2-9(용도: 한 사람을 거리 두고 따라가고 서면 선다, 순찰 미션 계획과 별개; 3단계·발견한 구멍), dashboard README 첫 줄 현행화
- 실험(`experiments/2026-10-22_follow_operator/`): `run3.sh`(2단계 장면 + 서버 + Bridge, 명령은 API로), `api3.py`

**PM 결정(2026-10-23)**: 등록 버튼 넣음. 따라가기 정지 뒤 순찰 자동 재개 안 함(관제가 순찰 재개를 누름).

**확인**(시뮬 zz_follow2, fw9·fw10)
- 관제 경로: 등록(카메라 준비 전 `no_camera_frame` 거절 2회 뒤 confirmed 0.4~0.6 s), 시작 confirmed 1.0 s, 정지 confirmed, 놓침 경고 알림. 두 회차 모두 설계대로
- 주행은 두 회차 다 완주 전에 끝남 — 관제와 무관한 2단계 규칙 구멍: (a) 운용자가 멈춘 뒤 잠깐 끊기면 "가던 방향 1.5 m 더" 규칙이 운용자를 지나쳐 등진 채 섬(fw9), (b) 가로지르는 사람을 피해 경로가 꺾이면 ±34° 시야 밖으로 나감(fw10). 실험 기록 3단계 절에 분석. 수정은 PM 결정 뒤
- 이 노트북에 시험 환경 새로 만듦(저장소 밖): `dashboard/.venv`, `relay_prog/venvs/bridge`, Node 22·pnpm은 `~/.local/opt`

## 2026-10-22 (130) 따라가기 2단계(주행): `limbo_follow` 노드 + `limbo_follow.xml` + 따라가기용 MPPI — 시뮬 홀·복도 모퉁이 2개 19 m 완주, 평균 거리 2.08 m, 충돌 0

**할 일**
- `build_limbo`(새 패키지 `limbo_follow`, 새 메시지 `FollowState`). 런치가 `follow_node`를 띄운다

**변경**
- 새 패키지 `limbo_follow`: `follow_node.py`(`/follow/start·stop` Trigger, 순찰 `/patrol/pause` 호출, NavigateToPose를 `behavior_tree=limbo_follow.xml`로, `/goal_update` 목표점 갱신 5 Hz 틱, `/follow/state` 5 Hz), `follow.py`(ROS 없음: 운용자에서 follow_distance 앞 목표점, 가다 서다 판정, 내다보기 목표; 단위 시험 5개), `config/follow.yaml`
- `limbo_navigation/behavior_trees/limbo_follow.xml`: Nav2 `follow_point` 꼴(GoalUpdater·TruncatePath) + `IsWaitingForPerson`(2-7) + 계획·추종 실패는 복구 없이 잠깐 쉬고 다시. 추종 성공 뒤 0.5 s 쉼(안 쉬면 20 Hz로 액션이 다시 걸려 MPPI가 매 tick 초기화)
- `nav2_params.yaml`: 따라가기용 컨트롤러 `FollowOperator`(FollowPath 사본, GoalCritic·PathFollowCritic threshold_to_consider 1.4 → 0.4, time_steps 80 → 32). 기본 `FollowPath`로는 경로 끝이 늘 1~2 m 앞이라 "목표 근처 감속"에 묶여 0.25 m/s. 순찰 컨트롤러는 그대로
- `limbo_interfaces/FollowState.msg`(state·active·target_id·distance·reason·elapsed·lost_sec), `person_wait_node.py`: `/follow/state` active면 운용자 트랙을 기다리기 구역에서 제외
- `limbo_bringup` 런치에 `follow_node` 추가. `moving_obstacles.py`: 사람 spec `start_on`(ROS 토픽 신호까지 첫 자리에 서 있음)
- lab 기본 하반신 모델 leg_512 → **leg_640**(dev 변경 기록 41과 같음). 가까운 거리 검출 때문
- PROJECT.md 2-9 "실제로는"에 2단계 반영, 1절 표에 `limbo_follow`. TROUBLESHOOTING: `timeout`으로 죽인 ros2 CLI가 DDS 공유 메모리 조각을 쌓아 기동 실패·시계 역행(해결 `svc.py`)

**확인**(`experiments/2026-10-22_follow_operator/` 2단계, 장면 `zz_follow2`: 운용자 0.5 m/s 홀 → 복도(모퉁이 2) → 위쪽 복도 19 m, 홀에 가로지르는 사람 1명, 8회차)
- fw8(채택 설정): 완주, 평균 거리 2.08 m(0.8~2.5 m 안 78 %), 놓침 2회 최대 6.8 s(모퉁이, 가던 방향 1.5 m 내다보기로 복귀), 운용자가 선 뒤 1.67 m에서 90 s 안정, 충돌 0, 가로지르는 사람 기다리기 7.5 s
- 회차별로 고친 것: 출발 신호 유실(구독자 대기) → 놓침 판정을 마지막 본 시각 기준 → 따라가기용 컨트롤러(0.20 → 0.30 m/s) → 예측 1.6 s(복도 0.5~0.6 m/s) → 가까운 놓침은 제자리 → 가다 서다 히스테리시스 제거(평균 거리 3.3 → 1.8 m) → 유지 거리 1.5 m(1.2 m 안은 카메라가 못 봄) → 내다보기 1.5 m
- 경계: 모퉁이 도착이 0.5~1 m 늦으면(fw7) 운용자가 카메라 범위 5 m 밖으로 나가 15 s 뒤 정지. 운용자가 0.5 m/s보다 빠르면 못 따라감(상한 0.6)
- 다음(3단계, 승인 뒤): 관제 시작·정지 버튼과 상태 표시. 남은 손질: 서 있는 동안 FollowPath 재호출(2 Hz 초기화), person_wait 제외를 트랙 번호 대신 판정으로

## 2026-10-22 (129) 따라가기 1단계: 등록한 운용자(발목 형광 밴드) 재식별 `/follow/target` — 시뮬 가로지르기 장면 바꿔치기 0, 맞게 찾음 98 %

**할 일**
- `build_limbo`(새 메시지 `limbo_interfaces/FollowTarget`, `limbo_perception` 의존 `std_srvs`)

**변경**
- 설계 전제 PROJECT.md **2-9**: 따라가기는 "등록한 한 사람(직원)"을 따라가고, 근거는 그 사람만 가진 신호(형광 밴드 + 깊이 마스크, 보조로 같은 트랙 번호)이며, 못 알아보면 잘못 따라가지 말고 선다. 색 서명은 옷이 같은 사람을 못 가르므로 거부 용도로만
- `limbo_perception/appearance.py`(새, ROS 없음): 깊이 마스크(사람 깊이 ±0.35 m 픽셀만 = 세그멘테이션 역할), 밴드 색 픽셀 수(HSV 범위), 하반신 H×S 색 서명(선형 보간 히스토그램)과 유사도, 운용자 판정 `OperatorIdentity`(등록·밴드 → 2 s 안 같은 트랙(서명 거부) → 놓침 → 5 s 뒤 대상 해제)
- `person_detector.py`: 검출마다 밴드·서명 계산, `/follow/enroll`·`/follow/forget`(Trigger, 별도 콜백 그룹 — 기본 그룹에 두면 등록이 기다리는 동안 카메라 콜백이 못 돌아 늘 실패), 서명 파일 `~/.limbo/follow_operator.json`, `/follow/target`(`FollowTarget`: odom 위치·속도·근거·밴드 px·유사도) 발행, 주석 영상에 OPERATOR 표시
- `config/person_detector.yaml` `follow:` 절(밴드 색 범위·최소 px·깊이 허용, 서명 문턱 0.6·hold 2 s·lost 5 s·게이트 0.8 m·등록 구역 0.5~2.5 m)
- 시뮬 `moving_obstacles.py`: 사람 spec `band`(월드 모델 이름)이면 그 모델을 발목 높이로 같이 옮김(set_pose_vector). 실험 월드 `zz_follow`는 `run.sh`가 소셜 월드 사본 + `band_model.sdf`로 만듦
- 단위 시험 `test/test_appearance.py` 7개

**확인**(`experiments/2026-10-22_follow_operator/`, 로봇은 서 있고 운용자 0.5 m/s 고리 + 가로지르는 사람 2명, 등록 뒤 180 s씩)
- 1회차(서명으로 다른 트랙에 갈아타는 규칙 있음): 맞게 찾음 98 %, 바꿔치기 7구간(합 4 s) — 전부 `signature` 근거로 시작, 밴드 근거 0건 → 규칙 제거
- 2회차(제거 뒤): 보임 2111 프레임 중 맞게 찾음 98 %, 놓침 2 %(최대 0.7 s), **바꿔치기 0**. 근거 band 2176·band_multi 13·track 9
- 자원(같은 장면 대조): 인식 노드 CPU 170 % vs 165 %(+5 %p, 추가 계산 프레임당 2.3 ms), RSS·GPU 같음. 사람 3명 장면이라 기존 100~109 %보다 높은 건 장면 탓
- 다음(2단계, 승인 뒤): follow 노드(사람에서 1.2 m 목표점, Nav2 follow_point 꼴 트리, 순찰 pause), 기다리기에서 운용자 트랙 제외

## 2026-10-21 (128) 시뮬 도구 LIMBO_WS: 다른 작업 공간 빌드(ktj worktree)로 벤치를 돌릴 수 있게. ktj 기본 모델 leg_640 전환 회귀 통과

**할 일**
- 없음(도구만)

**변경**
- `tools/sim_trials/sim_ctl.sh`·`patrol_trial.sh`: `LIMBO_WS=<작업 공간>`(기본 `~/limbo/limbo`)으로 source 경로·실행 폴더·잔존 노드 정리 패턴을 바꿈. ktj를 `git worktree add ~/limbo_ktj ktj`로 받아 따로 빌드해 두면 lab 빌드와 섞이지 않게 ktj 회귀를 돌릴 수 있음. worktree는 서브모듈(`robot_self_filter`)이 비어 있으니 `git submodule update --init` 필요(안 하면 런치가 패키지를 못 찾아 sim_ctl이 준비 대기만 함)
- lab 기본 모델은 그대로 leg_512(ktj가 lab에 병합될 때 따라옴)

**확인**(ktj `b856b7c` + 기본 leg_640, 별도 폴더 빌드, 상세는 ktj 변경 기록 41)
- 손님 4/4 × 3, 상자 4/4(최소 0.25~0.29 m), 순찰 3/3(200~234 s), 충돌 0. 두 사람 나란히는 leg_512 3/5·5/5 vs leg_640 2/5·3/5·0/5로 같은 양상(원래 못 지나가는 장면). 0/5 회차는 서 있는 사람(정답 1.54 m) 옆에서 "다가옴" 대기 406 s — ktj 기다리기 상태 기계에는 lab의 수정(ef73375·49a3851·2d90988: 서 있는 사람은 실제로 막혔을 때만, 구역 팽창 폭, 막힘 타이머 재시작)이 아직 없음. **다음 ktj 반영 후보**
- ktj 손님 회차는 이 월드의 시간표 actor(25.9 s 주기, 출발점 동쪽 1.9 m까지)와 시간이 안 맞아 실제 마주침 없음(최소 1.4~1.6 m). ktj에는 소셜 포스 사람이 없어 손님 앞 정지는 lab zz_social 결과로 갈음

## 2026-10-21 (127) 하반신 모델 5·6차: sgh 재학습 leg_640(640) vs 기본 leg_512(512) 손님·복도·충장로 군중 각 2회 + 자원 — 가까운 거리 같거나 우세, 먼 거리·군중 동급, 자원 차이 CPU +5~10 %p

**할 일**
- `build_limbo`(limbo_perception `setup.py` 설치 목록에 `models/leg_640.pt` 추가). 기본 모델은 그대로 leg_512·512

**변경**
- `origin/sgh`의 `leg_640/weights/best.pt`(yolo11n에서 coco_lower 100 epoch, 입력 640)와 학습 기록(args·results)을 가져오고 `limbo_perception/models/leg_640.pt`로 등록. `person_detector.yaml` 주석에 선택 방법(model·imgsz 640). dev의 "leg_640 (#20)" 커밋은 빈 커밋이라 파일이 없음(PR 올린 사람에게 알릴 것)
- 벤치 `experiments/2026-10-19_leg_model/run.sh`: `crowd` 시나리오(충장로 `chungjang_crowd` 50명, 경로 street, 목표당 600 s, nav 1500 s). `ana.py`: `HFOV=30`(시야 ±30°)·`HFOV_MIN=30`(가장자리 30~36°만) 환경변수
- 10-20 기록 정정: `pl_cand_*`는 leg_512를 640으로 돌린 참고 회차, leg_512@512는 `pl2_cand_*`

**확인**(`experiments/2026-10-19_leg_model/README.md` 5·6차, 기록 `~/limbo_bags/leg_model_rec/`)
- 손님 0~1.5 / 1.5~3 m: leg_512 52·42 / 52·75 %, leg_640 **67·89 / 58·77 %**. 복도 3~5 m: leg_512 97·95 %, leg_640 88·92 %(porto 61 %처럼 무너지지 않음). 겹침 0·오검출 0·주행 성공·충돌 0은 같음
- 충장로 군중(사람 50명, 100 m 왕복, 구간당 프레임 수백~수천): 0~3 m는 회차 편차 안(61~89 %), 3~5 m leg_640 75·75 % vs 72·65 %. 주행 473~530 s 모두 성공, 접촉 1~2(폰 보는 사람이 정지 로봇에 걸어 들어옴)로 모델과 무관. leg_512 한 회차는 5.5 m 지점에서 사람이 0.7 m 앞에 선 채 1,180 s 교착(KNOWN_ISSUES 서로 양보)이라 빼고 다시 돌림
- 자원(RTX 4060 Laptop): YOLO 단독 VRAM 53~66 vs 60~69 MB, CPU 6.6 vs 7.1 ms/장. 노드 CPU 평균 복도 73~81 vs 82~86 %, 군중 114~115 vs 123~125 %, RSS 1.65 GB 같음, GPU 메모리 280 vs 276~296 MB, 처리 속도 14.5 Hz 같음. 영상이 320×240이라 CPU 병목, Jetson에서 재측정 필요
- **가장자리(30~36°) 손실의 정체**: YOLO는 leg_640·porto 90~98 % 잡는데(leg_512만 50~75 %) 최종 예측은 36~62 %. 빠진 프레임 대부분이 5차에 넣은 "화면 끝에 닿은 40 px 미만 박스 제외" 필터(leg_640 16·19개 중 12·15), 나머지가 새 트랙 5프레임 워밍업. leg_640은 박스가 더 타이트(폭 중앙 33 px vs porto 40)해서 문턱에 더 걸림. 10-20의 "porto가 가장자리에서 낫다"는 절반 이상이 모델이 아니라 박스 폭 차이였음
- 정리: 기본 모델을 leg_640(입력 640)으로 바꿔도 잃는 것이 없음. 최종 선택은 실물 카메라 bag으로. 가장자리는 모델이 아니라 40 px 필터를 "버리기 → 잘린 박스는 보이는 부분으로 거리 재기"로 바꿔야 함(설계 뒤)

## 2026-10-20 (126) 하반신 모델 4차: 팀원 1단계 porto_leg(640) vs 기본 leg_512(512) 각 1회 — 0~3 m는 porto 같거나 우세, 3~5 m는 leg_512 우세

**할 일**
- 없음(기본 모델 그대로 leg_512·512)

**변경**
- `experiments/2026-10-19_leg_model/run.sh`: `porto` 모드(`MODEL=<.pt>`, 입력 640), zz_social 월드를 설치 폴더에 복사하는 단계(없으면 Gazebo가 못 찾아 3번 다 시작 실패)

**확인**(`experiments/2026-10-19_leg_model/README.md` 4차)
- 손님 1.5~3 m porto 82 % vs leg_512 52 %, 복도 3~5 m 61 % vs 97 %, 0~1.5 m 복도 100 % vs 88 %. 겹침·오검출·ID·주행은 같음. 1회씩이라 우열 판정은 보류, 최종 선택은 실물 bag으로
- 추론 입력 크기는 학습 크기와 맞춰야 함(leg_512를 640으로 돌리면 손님 52 %·43 %)
- leg_512 손님 52 %는 시야 가장자리(±33~36°)에서 반쯤 잘린 사람 프레임 탓. ±30° 안으로 세면 porto 88 % vs leg_512 82 %로 같은 수준. 벤치의 ±36° 기준은 다음 비교부터 ±30° 열을 같이 적기로
- 반쯤 잘린 사람(30~36°, 3 m 안)은 porto가 두 장면 모두 67 %로 leg_512(15·27 %)보다 일관되게 나음 → 옆에서 오는 손님을 더 일찍 보는 차이. 2단계 학습 데이터·입력 크기(512) 영향 분리는 후속 과제

## 2026-10-20 (125) 지역 STVL 잔상 vs 멈칫거림: 복도·가로지르기 A/B 3회 — 잔상은 절반으로 줄지만 주행 시간·멈춤은 같음

**할 일**
- 없음(설정 변경 없음, 실험 기록만)

**변경**
- `experiments/2026-10-20_stvl_trail/`: 실행기 `run_ab.sh`(A/B × 복도·가로지르기 × 3회, 꼬리 측정 동시), 가로지르기 사람 배치 `zz_cross_movers.json`
- `docs/KNOWN_ISSUES.md`: 서로 양보 교착의 재현 장면(홀 가로지르기 24구간 중 13) 추가

**확인**(`experiments/2026-10-20_stvl_trail/README.md`)
- 복도: A 28.7±2.3 s vs B 29.1±1.5 s, 사람 앞 멈춤 2.2 vs 2.3 s, 꼬리 71 → 39칸. 가로지르기 성공 구간: 15.5 vs 16.1 s. 잔상이 멈칫거림을 늘린다는 가설은 이 두 장면에서 성립하지 않음
- 가로지르기 실패는 전부 서로 양보 교착(A·B 무관), R6 시험대 후보
- B 채택은 설계 근거(사람은 트랙 층)로만 가능, 측정된 손해 없음 → 사용자 결정 대기

## 2026-10-20 (124) 지역 STVL 잔상 원인 가르기 A·B·C(군중 1회씩): 잔상은 실재·decay가 길이 결정, 주행 성적은 편차에 묻힘. 측정 도구 OOM 수정

**할 일**
- 없음(설정 변경 없음, 실험·도구·해결 기록만)

**변경**
- `stvl_trail.py`: 벽 판정을 지도 2칸 팽창 조회로(첫 판은 벽 전체와 거리 행렬을 만들어 28.8 GB → OOM → 시뮬 heartbeat 끊김, 회차 3개 무효). 자는 동안도 spin해 TF가 갱신되게
- `docs/TROUBLESHOOTING.md`: "주행 중 70~90 s에 Nav2 전체가 내려감 — 옆 측정 스크립트 OOM" 항목

**확인**(`experiments/2026-10-20_chungjang_crowd/README.md` A·B·C 절)
- 사람 뒤 0.5~1.5 m 치명 칸: A(지금) 67 → B(지역 STVL 사람 점 제외) 34 → C(decay 0.3) 27. B는 사람 몸 자리도 13 → 3
- 주행 시간·멈춤은 조건 차이보다 회차 편차(같은 설정 r2·A의 멈춤 54 s vs 29 s)가 큼. C 중단은 출발 직후 7~11명 몰림 탓
- 다음(사용자 결정): 복도 한 명 장면에서 A·B 3회 비교 뒤 B 채택 여부

## 2026-10-20 (123) 막힘 타이머 수정 뒤 군중 재확인(왕복 2/2, 꼬리물기 사라짐), STVL 사람 꼬리 측정 도구

**할 일**
- 없음(기록·도구만)

**변경**
- `tools/sim_trials/stvl_trail.py`: 지역 STVL 층의 비벽 치명 칸을 시뮬레이션 사람 실제 위치까지 거리로 나눠 찍음. 걷는 사람 뒤 `voxel_decay` 꼬리를 설정 바꾸기 전후로 비교하려는 것

**확인**(`experiments/2026-10-20_chungjang_crowd/README.md` 재확인 절)
- 군중 50명 100 m 왕복 2/2(263·252 s), 전역 계획 실패 0, 진짜 복구 Spin 1·BackUp 1, 경보 0(r1c는 막힘 대기 213 s·경보 21). 접촉 2는 정지 중 사람이 걸어 들어옴
- CSV `recoveries`는 BT 횟수라 기다리기 Wait 반복까지 세므로 군중에서는 의미 없음 → 로그의 Spin·BackUp으로 셀 것
- 열린 질문(사용자 RViz 관찰): 지역 STVL이 걷는 사람 뒤에 남기는 꼬리. 후보는 지역 STVL도 `*_nopeople`을 먹이고 decay는 사람 아닌 낮은 물체 기억으로만 남기기(설계 승인 뒤). 남은 것: 회귀 세트, ktj 반영

## 2026-10-20 (122) 2-8 규칙 1: 전역 계획은 사람을 트랙으로(person_filter + 전역 HumanLayer 통행료), 막힘 판정 구역·타이머 수정, 학습 예측 검토 기록

**할 일**
- `limbo_perception`·`limbo_navigation` 재빌드. 새 노드 `person_filter`(launch에 포함), 전역 costmap에 `human_layer` 추가, 전역 STVL mark 토픽이 `*_nopeople`로 바뀜

**변경**
- `person_filter.py`: 라이다·카메라 점구름에서 사람 트랙 반경 0.5 m 안의 점을 뺀 `*_nopeople` 복사본(바이트 행 복사, 필드 보존). 전역 STVL의 marking만 이것을 쓰고 clearing·지역·안전 정지는 원본. 단위 시험 4개
- `HumanLayer`: 통행료 모드 파라미터(`current_lethal`·`use_predictions`·서 있음/걷는 중 봉우리·반경·sigma). 전역 costmap에 HumanLayer 추가: 현재 위치만, 치명 아님, 반경은 치수 유도 0.55 m(사람 반경 + 로봇 반폭), 봉우리 150(서 있음, ≈ 돌아갈 가치 1.2 m)/50(걷는 중, 반경 0.5). 지역은 그대로
- `person_wait.py`: ① 막혔을 때 사람 여부를 보는 구역을 팽창 폭까지(`blocked_zone_margin` 0.45 = inflation_radius). 옆 0.75 m에 선 사람도 로봇을 막는데 진로 폭만 보면 복구(회전)를 돌렸음 ② 주행으로 돌아오면 막힘 타이머를 새로 잼. 기다리느라 선 시간을 막힘으로 세서 대기가 끝나자마자 `blocked_in_zone`으로 되돌아가 군중·손님에서 대기가 꼬리를 물었음. 단위 시험 2개 추가(총 65)
- `docs/PROJECT.md` 2-8: 전역에 HumanLayer가 없었다는 사실 정정, 규칙 3을 "로봇은 사람에게 움직여서 닿지 않는다" 원칙으로(가로지르는 사람에게도 선다), 비용의 뜻(도착 시점 존재 확률)·가변 비용 논의, 학습 궤적 예측을 검토하고 넣지 않은 이유, 결정 이력 2줄

**확인**(`experiments/2026-10-20_chungjang_crowd/README.md` 규칙 1 절)
- 군중 50명 100 m 왕복 2/2(전엔 중단), 상자 4/4, 복도 3/3(회전 0), 손님 4/4(타이머 수정 뒤). 충돌은 로봇 정지 중 사람이 걸어 들어온 것 외 0
- 남은 것: 타이머 수정 뒤 군중 1회 재확인, 회귀 세트, ktj 반영

## 2026-10-20 (121) 충장로 200 m + 소셜 사람 50명 군중 주행 관찰(설정 변경 없음), 군중 월드 생성기

**할 일**
- 없음(실험 전용). 월드는 `experiments/2026-10-20_chungjang_crowd/gen_crowd.py`로 설치 폴더에 만든다

**변경**
- `gen_crowd.py`: chungjang.sdf에 소셜 포스 사람 N명(actor + 플러그인 + movers json) 배치. world 이름을 json과 맞춰야 사람 스크립트가 시계를 받는다

**확인**(`experiments/2026-10-20_chungjang_crowd/README.md`)
- 2회: 전역 계획 실패(사람 50명 예측 경로가 폭 6 m 거리를 막음) → 복귀 목표만 성공, 74 s에 대기 11번(가로지르는 사람마다 정지), 접촉 2번은 로봇 정지 중 사람이 걸어 들어옴. 1회차는 collision_monitor 세그폴트(미재현). 설계 과제: 밀도 모드(전역 계획에서 사람 제외, 지나가는 사람/오는 사람 구분)

## 2026-10-20 (120) 기다리기 4단계: 서 있는 사람은 막혔을 때만, 안전 정지는 충돌 임박만, 준비 전 트랙 버림. 피팅 금지 규칙

**할 일**
- `limbo_perception`·`limbo_navigation` 재빌드. `person_wait.yaml`에 `odom_topic`·`stall_speed`·`stall_sec` 추가, `nav2_params.yaml` collision_monitor에서 `FrontStop`·`scan` 관측원 제거

**변경**
- `person_wait.py`: DRIVING → WAITING의 구역 안 정지 트랙 진입을 "로봇이 실제로 막혔을 때"(`/odometry/filtered` 속도 0.05 m/s 미만 2 s)만으로(`blocked_in_zone`). 서 있는 사람은 그 자체로 손님이 아니다(2-7). 단위 시험 3개 추가(막힘·옆 사람·오도메트리 없음), 기존 사례는 막힌 로봇 전제로 갱신
- `nav2_params.yaml`: 범퍼 앞 0.3 m 고정 정지 구역(FrontStop) 제거, approach 모델(1.2 s 앞 footprint) 관측원에 ToF 추가. 벽 옆 제자리 회전을 안 막음
- `person_wait_node.py`: 준비(TF 2 s) 전에 온 트랙 메시지는 버림(시작 직후 가짜 코앞 트랙)
- `docs/PROJECT.md`: 2-7 전이 문구(①다가옴 ②막혔을 때 구역 안 정지), 안전 정지 문구, 6절 "피팅 금지" 규칙. `docs/KNOWN_ISSUES.md`: 60 s 정지 항목 해결 표시, "서로 양보 교착" 신규

**확인**(`experiments/2026-10-19_person_wait/` 4단계, 각 1회)
- 상자+벽 옆 사람 4/4(벽 옆 사람 옆을 멈춤 없이 지나감), 손님 4/4(정지 7.1 s 뒤 출발), 앞에 서는 사람 3/3(막힌 뒤 대기 → ToF 비면 출발, 벽 앞 갇힘 없음). 복구·충돌 0
- 복도 1/3: 비켜 주는 시뮬 사람이 로봇 옆에 서고 로봇은 막혀 대기, 둘 다 안 움직여 225 s(경보 8번). 설계대로 작동한 결과이며 시뮬 사람을 고쳐 통과시키지 않음. 출구는 R6

## 2026-10-19 (119) 사람 기다리기 재설계(2-7) 1~3단계: 상태 기계 하나·`/person_wait`·`IsWaitingForPerson`, 래치 제거, 안전 정지 분리

**할 일**
- 전체 재빌드(venv colcon). 새 메시지 `limbo_interfaces/PersonWait`, 새 노드 `person_wait`, BT 플러그인 교체. `tof_node`는 점군 처리만 남음(`tof.yaml`에서 래치 파라미터 삭제)
- 미달 셋(아래)은 다음 커밋에서 보완

**변경**
- 1단계 `person_wait.py`: ROS 없는 순수 상태 기계(NOT_READY/DRIVING/WAITING/PULL_OVER). 설정은 치수에서 유도(구역 반폭 = 로봇 반폭 0.30 + 사람 반경 0.25, 구역 1.5 m, 신뢰 거리 3.0 m, 서비스 15 s, 경보 30 s). 타이머로 대기를 끝내는 전이 없음. 단위 시험 15개
- 2단계 `person_wait_node.py`: 트랙을 범퍼 기준 상대 위치로(속도는 회전만, 로봇 속도 안 뺌), 준비 신호 = 지도 + `map→base_link` TF 2 s. BT 세 자리(계획 중 대기·추종 중 정지·복구 전)를 `IsWaitingForPerson` 하나로. `collision_monitor`에 범퍼 앞 0.3 m `FrontStop`(ToF+라이다). `PersonBlocking`·`ApproachWatch`·띠 판정·`/person_blocking`·`/person_approaching`·옛 BT 플러그인 삭제. 벽 걸러내기·덩어리 판정·최근접점은 `geometry.py`로 보존
- 3단계 보완: BT `FollowPathOrWait`·`ComputePathOrWait` 반복 상한 60 → 사실상 무한(타이머는 출구가 아님). 코앞에서 카메라 트랙이 끊길 때(모델이 코앞 다리를 못 봄, 프레임으로 확인) "직전 3 s 안 구역 트랙 1.0 m 안 + ToF 막힘이면 대기 유지, ToF 비면 즉시 해제". 정지 판정 여유(0.2 미만 정지, 0.3 이상 1 s 지속 시 해제). 손님 시나리오 복귀 자리를 진로 밖으로, `moving_obstacles.py` served 해제를 로봇 3 m 밖으로. FrontStop은 stop → limit(전진 0, 회전 허용)
- `docs/PROJECT.md` 2-7 확정(서비스 15 s 뒤 비켜서기, 자리 없으면 계속 기다림 + 경보, 천천히 지나가기 없음), 결정 이력. `docs/TROUBLESHOOTING.md`에 래치 교훈

**확인**(`experiments/2026-10-19_person_wait/`)
- 손님 12/12(멈춤·출발 전이 로그로 설명, 복구 0), 사람 두 명 복도 9/9(대기 최대 4.3 s, 60 s 정지 0), 앞에 서는 사람 8/9(선 10 s 동안 기다렸다 ToF 비면 출발), 상자 9/12(상자 때문의 대기 0·접촉 0). 충돌 전부 0
- 미달 셋: ① 벽 옆에 서 있는 사람에게 `in_zone`으로 영영 대기(설계는 다가옴만 손님) ② 복도 끝 벽 앞 0.3 m 안전 정지가 제자리 회전과 겹쳐 갇힘 ③ 시작 직후 준비 전 메시지로 가짜 코앞 트랙

## 2026-10-19 (118) 하반신 모델 3~5차: 몸 중심 보정(박스 종류별 반경), 두 다리 합치기, 화면 가장자리 박스·거리 튐 거르기, 기본 모델을 하반신으로

**할 일**
- `limbo_perception` 재빌드(venv colcon). 기본 모델이 `models/leg_512.pt`(classes [0,1], imgsz 512)로 바뀜. 기존 모델로 돌리려면 yaml 주석대로

**변경**
- `geometry.push_to_body_center`: 깊이→3D 점 직후 카메라→사람 방향으로 반경만큼 밀어 몸 중심으로. leg 박스 0.25 m(`leg_radius`), 몸 전체 박스 0.12 m(`person_box_radius`)
- `merge_leg_boxes`: person 없이 leg 둘이 가로로 나란하면(중심 간격 ≤ 1.5×폭 합, 세로 겹침 ≥ 0.5) 하나로
- `geometry.clipped_at_edge`: 화면 좌우 끝에 닿고 폭 40 px 미만인 박스는 거리 계산 제외. `DepthJumpFilter`: 같은 트랙 거리가 한 프레임에 1.0 m 넘게 튀면 직전 값 유지(3프레임 연속이면 채택)
- 진단 토픽 `/person_detector/boxes`(시각·클래스·좌표·신뢰도·합친 뒤 박스), `experiments/2026-10-19_leg_model/diag.py`(박스 그린 PNG 저장), `run.sh DIAG`
- 단위 시험 7개 추가(총 55개)

**확인**
- 손님·복도(각 1~2회): 겹침 0 %, ID 바뀜 기존 모델 수준(3~5), 위치 오차 중앙값 손님 0.16~0.21 m·복도 0.07 m, 1.5 m 밖 치우침 ±0.02 m(3차 +0.13~0.17)
- 손님이 시야 가장자리에 걸쳤을 때 벽 자리를 사람으로 잡던 오검출 169 → 5개(새 트랙 첫 값). 원인은 가구가 아니라 잘린 박스의 깊이가 뒤 벽을 잰 것(지도 광선 추적으로 위치 일치 확인, 프레임 196장 저장)
- 복도 주행 3/3, 충돌 0. 손님 주행 2/4는 손님이 보여서 끝없이 기다리는 것(2-7 몫)

## 2026-10-19 (117) 하반신 검출 모델(leg_512) 적용 준비: 클래스·입력 크기 파라미터, 박스 합치기, leg 깊이 샘플링, 시뮬 비교 2차

**할 일**
- `limbo_perception` 빌드는 venv를 켠 `python -m colcon build --symlink-install`로(시스템 colcon이면 ultralytics를 못 찾아 노드가 죽음)
- 기본 모델은 아직 yolo11n. 하반신 모델은 `person_model:=<limbo_perception/models/leg_512.pt 절대 경로>` + `yolo.classes: [0, 1]`, `yolo.imgsz: 512`

**변경**
- `person_detector.py`: 고정 클래스 0을 `yolo.classes`(기본 [0])·`yolo.imgsz`(기본 640) 파라미터로. 시작 시 모델 경로·클래스 로그
- `geometry.merge_leg_boxes`: 같은 프레임에서 leg 박스가 person 박스 안에 70 % 이상 들어가면 버리고, leg끼리 IoU 0.5 이상이면 큰 것만. 추적기에 넣기 전에 적용(한 사람이 둘로 갈리던 문제)
- leg 박스 깊이: 가로 여백 5 %·percentile 10(`depth.leg_roi_margin_x`, `depth.leg_percentile`). person 박스는 종전대로
- `models/leg_512.pt`(팀원 학습, 5.4 MB) 설치. 단위 시험 6개 추가. 실험 기록 `experiments/2026-10-19_leg_model/`(rec.py·ana.py·err.py·run.sh)
- `aischool_2f_social_movers.json`: 비켜 주는 사람 반환점 (−6.0, 10.1) → (−5.0, 10.1). 로봇 2구간 출발 자리에서 0.57 m라 사람이 로봇 앞에 영영 서 있던 시험 쪽 결함
- `docs/PROJECT.md` 2-7(초안): 사람 기다리기를 "사람 트랙"만으로 결정하는 상태 기계 설계. 팀 합의 전

**확인**
- 손님·복도 × 2회, 카메라 0.60 m·0°. 1.5 m 안 검출 기존 0~49 % → 73~100 %, 멈춘 손님 0 → 62~80 %. 2차에서 한 사람에 예측 2개 이상 22~97 % → 0~5 %, ID 바뀜 20~115 → 1~37(기존 수준). 위치 오차 중앙값 0.22~0.26 m는 몸 앞면을 재서 카메라 쪽으로 일정하게 치우친 것(안전한 방향, 사람 반경 보정 후보). 추론 3.7 → 4.0 ms
- 손님 주행 3/4·1/4는 손님이 보이니 멈춘 뒤 끝낼 조건이 없어서(2-7 몫). 복도 3/3·2/3, 충돌 0

## 2026-10-15 (116) 하드웨어 최종 치수 반영: 라이다 0.70 m(몸체 높이 0.609)·카메라 0.60 m

**할 일**
- `build_limbo` (URDF·launch 기본값)

**변경**
- `limbo_description/urdf/limbo.urdf.xacro`: `body_top` 0.709 → 0.609로 MID-360을 바닥 0.70 m에(0.609 + 0.09094). 몸체 메시 z 배율은 `body_top / 0.835` 식 그대로라 자동으로 따라감. `camera_z` 기본값 0.70 → 0.60(수평 0° 그대로)
- `limbo_bringup/launch/start_simulation.launch.py`·`limbo_simulation/launch/gazebo.launch.py`: `camera_z` 기본값 0.60
- 바퀴 지름 15 cm(`wheel_radius` 0.075)·바퀴 축 높이는 그대로 둠: 실측 축 높이 0.08 m는 반지름 0.075와 0.5 cm 어긋나는데, `base_link` 원점이 바닥이라 축만 올리면 바퀴가 뜨고 몸체를 내리면 캐스터(0.0625)가 바닥에 박힘 → 실물 재측정 뒤 결정
- `docs/PROJECT.md`: 크기(높이 약 0.72 m)·MID-360(0.70 m, 낮은 물체 사각 0.3 m 높이 3.3 m 안·바닥 5.7 m 안)·카메라(0.60 m) 행

**확인** (메인 PC, `~/limbo_bags/sim_trials/logs/trial_lidar70_*`)
- xacro 전개 base_footprint 기준 높이: `mid360_link` 0.700, `rgbd_camera_link` 0.60, `tof_link` 0.10, `lid_link` 0.609. 바퀴 축 0.075·캐스터 중심 0.0625(둘 다 바닥 접지)
- 출발 자리 진단: scan 1.0 m 안 점 0개, 라이다·카메라 센서 0.6 m 안 점 0개(자기 몸체 안 봄). 0.80 m 때와 달리 앞-오른쪽 1.7 m 물체가 scan에 새로 잡혀 local costmap 1 m 가장자리에 팽창 비용이 생김(실제 물체)
- 복도 3/3(31.3·25.3·89.2 s, 사람 충돌 0, 사람 최소 0.70 m) — 3회차는 `person_approaching` 60 s 유지(위 알려진 문제, 라이다 무관). 상자 4/4(31~36 s, 장애물 최소 0.18 m, 충돌 0)

## 2026-10-15 (115) 주행 회귀 세트(dev 반영 전 점검)·라이다 0.80 m(몸체 높이 0.709)·default_server_timeout 100·잔존 bag 정리

**할 일**
- `build_limbo` (URDF·nav2 설정)

**변경**
- `limbo_description/urdf/limbo.urdf.xacro`: `body_top` 0.835 → 0.709로 MID-360을 바닥 0.80 m에(하드웨어 결정, 카메라 0.70 m 유지). 몸체 시각 메시 z 배율 `body_top / 0.835` — 메시가 높은 채면 Gazebo 라이다가 자기 몸체를 봐 출발 자리에서 못 움직임(`docs/TROUBLESHOOTING.md` "몸체를 낮추자…")
- `limbo_navigation/config/nav2_params.yaml`: `default_server_timeout` 20 → 100 ms. 시작 부하에서 계획 서버 응답을 놓쳐 목표를 바로 포기하던 것(손님 0/4)
- `tools/sim_trials/nav_route.py`: 수락 응답 60 s까지 대기, 재전송 없음(재전송하면 두 목표가 생겨 앞 목표가 취소됨). `tools/sim_trials/sim_ctl.sh`: stop 정리 패턴에 `ros2 bag record` 추가(20시간 남은 진단 녹화가 원인, TROUBLESHOOTING "진단용 `ros2 bag record`…")
- `docs/KNOWN_ISSUES.md` "기다리기 BT 60 s": 복도 다가옴 정지가 60 s 상한까지 안 풀리는 경우 간헐 재발 → dev에는 기다리기 트리를 끈 채 올리는 것이 안전
- `docs/PROJECT.md` 센서 표: MID-360 높이 0.80 m·몸체 0.709 m

**확인** (메인 PC, `~/limbo_bags/sim_trials/logs/trial_reg_*`·`trial_lidar80_*`)
- 비켜 주는 사람 복도 3회: 8/9 성공, 3회차 셋째 구간만 `person_approaching` 60 s 유지 → 89.8 s 중단(위 알려진 문제). 사람 충돌 0, 사람 최소 0.64~0.70 m
- 상자 4/4(29~35 s, 장애물 최소 0.21 m), 손님(`default_server_timeout` 100) 4/4(17~28 s, 사람 최소 0.56 m), 순찰 3/3(320·258·211 s, Goal failed 1·1·0)
- 라이다 0.80 m 뒤: 복도 3/3(25~31 s, 사람 최소 0.63 m), 상자 4/4(30~35 s, 장애물 최소 0.23 m) — 회귀 없음

## 2026-10-15 (114) NavFn A* vs 다익스트라 + 계획 계산 시간 측정 도구 (A* 유지)

**할 일**
- 없음(설정 그대로)

**변경**
- `tools/sim_trials/plan_time.py`: 주행 없이 `compute_path_to_pose`를 반복 호출해 순수 계산 시간(`planning_time`)·왕복·경로 길이를 CSV로. 계획기 비교 때 "계산 시간을 못 쟀다"를 메움
- `experiments/2026-10-14_planner_compare/` 추가 절: A* 1.0~2.4 ms vs 다익스트라 1.8~5.8 ms, 다익스트라 경로가 두 목표에서 0.3~1.3 m 짧으나 MPPI 후보 충돌 경고 10(A* 0) → A* 유지
- 복도·홀 주행 벤치는 기다리기 트리의 60 s 다가옴 정지(2/2 재발)로 계획기 비교에 못 씀 → 서브 PC R5에 로그 넘김(`docs/lab/requests.md`)

**확인**
- 계획 시간 10회×4목표×2, 성공 80/80

## 2026-10-14 (113) 서브 PC 10-14 마무리: R6는 이미 있는 손님/행인 판별에 행동을 연결하는 방향으로 10-15 이어서

**할 일**
- 없음 (문서만)

**변경**
- `docs/lab/reports.md` "10-14 마무리": 지금 상태, 사용자 설명으로 바로잡은 것(판별은 `person_detector`의 motion_state·approach_intent에 이미 있음, 서브 PC가 R5에서 다가옴 판단을 따로 만든 것은 중복, R9 근거 정정), 10-15 할 일 순서

**확인**
- 없음

## 2026-10-14 (112) R6 2차: 늦은 원인은 검출이 아니라 판단 거리 3 m와 짧은 비켜서기 경로라는 것을 찾음 (되돌림)

**할 일**
- 없음 (기록만, 설정·트리는 R5 통과 상태 그대로)

**변경**
- `experiments/2026-10-14_pull_over_sub/` "2차": YOLO는 가리지 않은 사람을 3~5 m에서 잡음(1차 진단 정정). 다가옴 판단 거리 3 → 4 m로 하자 제때 켜졌지만, 앞 0.3·옆 0.4 m 짧은 경로를 MPPI가 못 따라가 옆으로 안 움직임. 4 m는 R5 정지에도 걸려 복도·상자가 나빠짐
- `docs/lab/reports.md` R6 2차

**확인**
- no_yield 복도 3·비켜 주는 사람 복도 3·손님·상자, 예측·정답 녹화와 검출 진단 노드 ([기록](../experiments/2026-10-14_pull_over_sub/README.md))
## 2026-10-14 (111) 잔존 노드 정리에 설치 폴더 노드(self_filter·limbo_drive 등) 포함

**할 일**
- 없음

**변경**
- `sim_ctl.sh` 정리 패턴에 `limbo/install/(robot_self_filter|limbo_drive|…)/lib/`를 추가. `make_map.sh stop`이 끝에 같은 정리를 부름
- 왜: 오늘 여러 launch가 끝난 뒤 `self_filter`가 5개(4~6시간) 살아남아 있었다. 정리 패턴이 `/opt/ros` 아래 실행 파일만 봐서 우리 설치 폴더의 노드는 안 잡혔음

**확인**
- 남은 self_filter 5개를 PID로 끝낸 뒤 패턴 적용, 0개

## 2026-10-14 (110) 지도 작성 도구 `tools/make_map.sh` (slam_toolbox + 사람 조종, Nav2 없음)

**할 일**
- pull 후 `colcon build --symlink-install --packages-select limbo_drive limbo_bringup`
- 써 보기: `tools/make_map.sh start 지도이름 [월드]` → 다른 터미널 `drive`(키보드) 또는 게임패드 → `save` → `stop`. README "새 지도 만들기"

**변경**
- `limbo_bringup/launch/mapping.launch.py`: Gazebo+로봇 → ekf → self_filter → `/scan` → slam_toolbox 지도 작성 모드(갱신 1.5 s, `resume_from`으로 이어 하기) → 조종 관문·게임패드(joy + teleop_twist_joy, xbox 설정) → RViz(`rviz/mapping.rviz`: 지도·라이다·로봇·포즈그래프·판정문·map/odom 축). AMCL·Nav2·인지 노드 없음
- 새 패키지 `limbo_drive`: `drive_gate`(모든 입력 `/drive/cmd` → `/cmd_vel`, 데드맨 0.5 s, 상한 전진 0.3·후진 0.15 m/s·회전 0.8 rad/s, 가속 제한, enable/disable, 순찰 중 거절·자동 끔), `map_status`(로봇 위 판정문: `SLAM OK/STALE`, 지도 갱신 횟수·시각, 포즈그래프 노드 수, map→odom 보정 cm, 지도 크기·알려진 칸 %, 자동 저장 시각. RViz 마커 글꼴에 한글이 없어 영문)
- `tools/make_map.sh start/drive/save/status/stop/resume`: 스택은 뒤에서 돌고(PID·로그 `~/limbo_bags/mapping/`), 60 s마다 `*_autosave` 포즈그래프 자동 저장, 저장은 slam_toolbox `save_map`(pgm/yaml) + `serialize_map`(포즈그래프). `.gitignore`에 `*_autosave.*`
- README "새 지도 만들기" 절 교체(명령 4개, 잘 되고 있는지 보는 법, 이어 하기)
- (앞 push) 서브 PC R6 결과 확인·R9(라이다로 다가오는 사람 판정) 지시

**확인**
- 학원 2층 월드: 서쪽 복도로 몰자 지도 562×247 → 562×409칸, `save`로 pgm 230 KB·yaml·포즈그래프 18 MB 생성, 지도 그림에 홀·복도 벽선 또렷. `/map` 0.67 Hz, 자동 저장 동작
- 판정문 RViz 표시 확인(SLAM OK, 갱신 23회, 노드 4, 보정 3 cm). map_saver_cli는 지도 구독 2 s 안에 못 받아 실패해 save_map 서비스로 바꿈
- 네모 월드는 방이 작아 첫 스캔에 지도가 완성돼 "쌓이는" 게 안 보임(README에 적음)

## 2026-10-14 (109) (105) 되돌이 처리 뒤 학원 2층 순찰 3/3 완주, A 맴돎 없어짐

**할 일**
- 없음 (기록만)

**변경**
- `experiments/2026-10-14_aischool_regress_sub/` "(105) 뒤", `docs/lab/reports.md` R7 후속

**확인**
- `patrol_trial.sh` 3회(R5 트리 켬): 209·180·226 s, A 0.7 m 안 2~5 s 머물러 지난 지점 검사에 걸림, 다시 시도·회전·후진 0. 사람 0.3 m 미만 2구간은 시간표 사람이 걸어 들어온 것 ([기록](../experiments/2026-10-14_aischool_regress_sub/README.md))

## 2026-10-14 (108) R6 비켜서기 노드를 만들었지만 다가오는 사람을 1.5 m에서야 알아 늦어서 트리에는 안 넣음

**할 일**
- `build_limbo` (새 BT 라이브러리 `limbo_compute_pull_over_pose_bt_node`, 트리·주행 동작은 그대로)

**변경**
- `limbo_navigation`: `ComputePullOverPose`(local costmap으로 옆 0.5·0.4·0.3 m·앞 0.3 m 중 비켜설 자리, 사람 반대쪽, 다가오는 사람 한 명에 한 번). CMake·package.xml. 트리 주석만 바뀜
- `experiments/2026-10-14_pull_over_sub/`, `docs/lab/reports.md` R6 결과

**확인**
- 트리에 넣고 no_yield 복도 3회: 6구간 모두 충돌(다가옴이 1.5~1.7 m에서야 참, 로봇 정지 뒤 사람이 걸어 들어옴). 비켜 주는 사람 복도 3/3 → 1/3로 나빠짐. 손님·상자는 같음 ([기록](../experiments/2026-10-14_pull_over_sub/README.md))

## 2026-10-14 (107) R6 비켜서 기다리기 설계 (구현 전)

**할 일**
- 없음 (문서만)

**변경**
- `docs/lab/reports.md` R6 설계·Q12: 판단은 지금 `IsPersonApproaching`, 새 동작 노드 `ComputePullOverPose`(local costmap으로 옆 0.5·0.4·0.3 m·앞 0.3 m 후보 중 외곽이 inscribed 미만이고 벽에서 반폭+0.1 m 이상인 자리, 한 사람에 한 번), R5 트리 `WaitForPerson` 맨 앞에 "비켜서기 한 번" 단계. 자리가 없으면 지금처럼 그 자리 정지

**확인**
- 없음 (설계)

## 2026-10-14 (106) 네모 10명 AMCL vs slam(AMCL 유지 확정), 복도 코앞 정체 미재현, nav_route 수락 대기 제한

**할 일**
- 없음(문서·도구)

**변경**
- `experiments/2026-10-14_localization_compare/`: 사람 10명 네모 순찰 각 1회. AMCL 오차 0.035/0.084 m, slam 0.050/0.086 m, 둘 다 3/3 → **AMCL 유지 확정**. PROJECT 결정 표 갱신
- `experiments/2026-10-14_tof_costmap/`: 복도 3회 반복 9/9, 코앞 정체 미재현(5회 중 1회) → KNOWN_ISSUES 낮은 빈도로
- `tools/sim_trials/nav_route.py`: 목표 수락 응답을 10 s까지만 기다리고 한 번 재전송, 시간 초과 취소 뒤 응답까지 spin(서브 PC Q11 ③: 수락 응답 없이 6분 멈춤)

**확인**
- 네모 순찰 AMCL 145.7 s·slam 137.4 s 완주. 복도 3회 31~32·25~26·31~32 s, 사람 앞 기다림 4~5 s, 돌아가기 매회 3번

## 2026-10-14 (105) MPPI 경로 되돌이 처리 켬 — 순찰 통과 지점 A 앞 1.2 m 정체 해결

**할 일**
- pull만(yaml). 순찰(네모·학원 2층) 다시 돌릴 때 A 지점 맴돎이 사라졌는지 보기

**변경**
- `nav2_params.yaml` MPPI `enforce_path_inversion: true`, `inversion_xy_tolerance 0.2`, `inversion_yaw_tolerance 0.4`: 경로가 되돌아 꺾이는 점(통과 지점 A → 정반대 B)까지만 경로를 쓰고, 그 점에 닿은 뒤 다음 구간을 쓴다
- 왜: 네모 화면 순찰이 A(5.3, 5.4) 앞 1.2 m (4.1, 5.3)에서 "진전 없음"만 반복(AMCL 회차 3번 다 실패, **사람 없는 지도 작성 회차도 같은 자리**). `prune_distance` 1.7 → 2.5(84) 뒤 MPPI가 잘라 쓰는 2.5 m 경로에 A까지 1.2 m + 되돌아오는 1.3 m가 같이 들어와 경로 추종 기준점이 로봇 뒤를 가리켜 속도 0. 오전 네모 회차(1.7)는 같은 구간 54~72 s. 서브 PC R7의 "A 지점 맴돎"도 같은 원인
- `docs/TROUBLESHOOTING.md`에 기록

**확인**
- 켠 뒤 slam_toolbox 순찰(사람 10명) 3묶음 모두 성공 35.0·54.5·47.9 s, 진전 없음 0. AMCL 재실행은 뒤이어

## 2026-10-14 (104) R8: local STVL 기억 3 s는 ToF 사각 상자에 효과가 안 보여 1 s 유지 권고

**할 일**
- 없음 (기록만, 설정 안 바꿈)

**변경**
- `experiments/2026-10-14_stvl_local_sub/`: local `voxel_decay` 1 s·3 s 상자 각 3회. 둘 다 접촉 0, 반례 재현 안 됨, 3 s에서 상자 최소 0.14 m 1번. 3 s 복도 1회 81 s(R5 다가옴 정지 60 s 재발). `nav_route.py` 멈춤 1회 기록
- `docs/lab/reports.md` R8·Q11

**확인**
- 같은 커밋(트리 켬)에서 기준 1 s도 같이 돌림 ([기록](../experiments/2026-10-14_stvl_local_sub/README.md))
## 2026-10-14 (103) 순찰 노드가 AMCL 없는 구성(slam_toolbox)에서도 출발하게 함

**할 일**
- pull만(develop 링크)

**변경**
- `patrol_node.py` `wait_for_localization`: `/amcl_pose` 수신 조건을 빼고 `map → base_footprint` TF만 본다. AMCL은 위치를 잡아야 TF를 내므로 판정은 같고, slam_toolbox 위치 추정·지도 작성 모드에서는 `/amcl_pose`가 없어 30 s 뒤 "localization not ready"로 순찰이 실패하던 것을 고침(네모 화면 AMCL vs slam 비교 중 발견)

**확인**
- 네모 화면 slam 순찰 회차에서 출발 확인 예정(결과는 다음 항목)

## 2026-10-14 (102) R5 통과: 다가오는 사람·코앞을 막은 사람 앞에서 회전·후진 대신 멈춰 기다리는 트리를 켬

**할 일**
- `build_limbo`. **주행 동작이 바뀜**: 진로 위로 다가오는 사람(`/person_approaching`)이나 사람 때문에 막힌 코앞(`/person_blocking`)이면 경로 추종·계획 실패에도 1 s씩 멈춰 기다림(상한 60 s), 회전·후진 안 함. 사람이 아니면 기존 복구 그대로

**변경**
- `nav2_params.yaml` `bt_navigator`: 기다리기 트리 세 줄을 켬(꺼 둔 (90) 되돌림)

**확인**
- (101) 뒤 비켜 주는 사람 복도 3/3(복도 24.8~34.0 s, 60 s 정지 0, 충돌 0), 손님 4/4(손님 앞 기다림 1번), 상자 4/4·닿음 0·최소 0.22 m, 모두 회전·후진 0 ([기록](../experiments/2026-10-14_tof_wait_sub/README.md))

## 2026-10-14 (101) 비켜 주는 사람이 서 있는 로봇을 보면 2.5 m에서 미리 돌아감 (Q10)

**할 일**
- pull만. 서브 PC: R5 복도 3회 재확인

**변경**
- `moving_obstacles.py`: 로봇 속도를 추정해(연속 위치) 0.1 m/s 아래로 서 있는 로봇이 목표 방향 35°·2.5 m 안에 있으면 막히기 전에 돌아가기 시작(`SIDESTEP_AHEAD` 1.5 → 2.5, `ROBOT_STOPPED_SPEED`). 막혀서 못 나아가는 조건은 그대로 둠(움직이는 로봇에 밀릴 때)
- 왜: (98) 뒤에도 서브 PC 복도 2/3에서 사람이 로봇 앞 모서리 옆(앞 0.5 m·옆 0.5~0.6 m, 틈 0.08 m)까지 간 뒤 돌아가기 시작해 끼어 섰다. 실제 사람은 서 있는 로봇을 2~3 m 앞에서 보고 미리 비킨다

**확인**
- 오프라인 모의 8경우(폭 1.8/2.4 × 로봇 가운데/±0.3 정지, 마주 오는 로봇 0.4 m/s): 정지 로봇은 1.75 m 앞에서 돌아가기 시작해 7.7~8.7 s에 통과(로봇 최소 0.63~0.78 m), 마주 오는 로봇도 통과

## 2026-10-14 (100) R5 Q9: 앞 섹터를 진로 폭 띠로 바꿔 벽 모서리 오탐을 없앰. 복도는 1/3이라 트리는 꺼 둠

**할 일**
- `build_limbo` (`tof.yaml`의 `front_sector_half_angle_deg`가 `front_sector_half_width`로 바뀜). 주행 동작은 그대로(트리 꺼 둠)

**변경**
- `limbo_perception/tof.py` `sector_occupied`: ±30° 부채꼴 → 범퍼 앞 0~1.5 m, 중심선 좌우 0.55 m(로봇 반폭 0.3 + 사람 반경 0.25) 띠. 사람이 떠난 뒤 벽 모서리를 잡아 정지가 안 풀리던 것(Q8)을 없앰. 시험 갱신
- `docs/lab/reports.md` Q10

**확인**
- (98) 뒤 트리 켜고 복도 3회·손님·상자: 상자 60 s 정지 사라짐(4/4·닿음 0). 복도는 1/3 — 2·3회 서쪽 구간에서 사람이 로봇 앞 모서리 옆(옆 0.5~0.64 m)에 서서 60 s ([기록](../experiments/2026-10-14_tof_wait_sub/README.md))
## 2026-10-14 (99) ToF costmap 반례 1회 기록 (코너 30 cm 상자 정체), 종합 보고서 캡처

**할 일**
- 없음(문서만)

**변경**
- `experiments/2026-10-14_tof_costmap/`: 보고서 캡처용 재실행에서 ToF costmap을 켜고도 홀 입구 30 cm 상자(정면 기준 45°, ToF·카메라 사각)에 갇혀 90 s×3 시간 초과. 접촉 13회 중 1회로 정정. `docs/KNOWN_ISSUES.md`에 올림. 후보: local STVL 기억 1 → 3 s 또는 ToF 두 개
- 종합 보고서(알고리즘·설정 비교, RViz 화면 포함)를 Claude 문서로 작성(저장소 밖)

**확인**
- 같은 캡처 회차에서 ToF 없음 4/4(0.19~0.31 m), 15° 4/4(0.19~0.34 m)

## 2026-10-14 (98) 돌아가기: 로봇 양옆 여유로 쪽을 고르고, 어깨를 틀어(몸 반경 0.2) 목표 옆 자리까지 비례 힘으로 (Q9 ②)

**할 일**
- pull만. 서브 PC: Q9 ① 진로 폭 띠로 바꾼 뒤 비켜 주는 사람 복도 3회

**변경**
- `moving_obstacles.py`: (1) 막힘 판정을 속도 크기 대신 **목표 쪽 진행 속도** < 0.2 m/s로(밀려났다 다가가기를 반복하는 경우도 잡힘) (2) 돌아갈 쪽을 사람 위치가 아니라 **로봇 양옆 지나갈 자리의 벽 여유**로 고름(로봇이 복도 한쪽에 치우쳐 있으면 사람 기준으로는 양쪽이 같아 로봇 쪽으로 가던 버그) (3) 돌아가는 동안 몸 반경 0.3 → 0.2(어깨 틀기)로 벽·로봇 반발을 계산, 로봇 반발 B 0.15 (4) 옆 힘은 일정값 대신 목표 옆 자리(로봇 반경 0.4 + 0.2 + 여유 0.1)까지 남은 거리 × 8, 상한 8 m/s². 상수 `SIDESTEP_*`
- 왜: 서브 PC Q8 재확인에서 옆 힘 6에도 사람이 앞 1.0~1.5 m·옆 0.46~0.62 m에 다시 서서 40 s(3회 중 2회). 오프라인 모의로 재현: 1.8 m 복도에 0.8 m 로봇이 서면 한쪽 0.5 m뿐이라 몸 반경 0.3으로는 벽·로봇 힘에 끼어 멈춤(사람 (3.48, 0.55)에서 정지). 실제 사람은 어깨를 틀어 지나간다

**확인**
- 오프라인 모의(정지 로봇, 폭 1.8/2.4 m × 로봇 가운데/±0.3 m 치우침 6경우): 모두 통과 8.9~10.8 s, 로봇 최소 0.61~0.98 m, 벽 최소 0.26 m 이상. 전 값은 1.8 m 치우침 2경우에서 멈춤

## 2026-10-14 (97) R5 Q8 재확인: 손님 앞 기다림 3/4, 복도는 회차마다 60 s 정지 하나라 트리는 꺼 둠

**할 일**
- 없음 (기록만)

**변경**
- `experiments/2026-10-14_tof_wait_sub/` "Q8": (95)·(96) 뒤 트리를 켜고 복도 3회·손님·상자. 짧은 정지 후 재개는 자주 나옴. 60 s 정지 원인은 사람이 옆 0.46~0.62 m에 다시 서는 것(사람 모델) 둘과, 앞 섹터가 벽 모서리를 잡는 것(로봇 쪽) 하나
- `docs/lab/reports.md` Q9(앞 섹터를 진로 폭 띠로)

**확인**
- 복도 3회 녹화로 정지 동안 상태를 셈(`corridor_hold.py`) ([기록](../experiments/2026-10-14_tof_wait_sub/README.md))

## 2026-10-14 (96) 돌아가기 힘을 1.8 m 복도에서도 지나가게 올림 (Q8)

**할 일**
- pull만. 서브 PC: 기다리기 BT 켜고 비켜 주는 사람 복도 재확인

**변경**
- `moving_obstacles.py`: `SIDESTEP_FORCE` 3 → 6 m/s², 돌아가는 동안 로봇 반발을 `SIDESTEP_ROBOT_FORCE` (3.0, 0.2)로(B 반). 3.0은 1.8 m 복도에서 벽 힘·로봇 반발에 막혀 사람이 1.5 m 앞에 다시 섰다(서브 PC Q8, 오프라인 모의 재현)

**확인**
- 오프라인 모의(정지 로봇): 1.8 m 복도 11.9 s에 통과(로봇 최소 0.62 m, 벽 0.18 m), 2.4 m 10.6 s(0.88 m). 전 값은 1.8 m에서 멈춤

## 2026-10-14 (95) ToF 점군을 local costmap에(카메라 0°의 낮은 장애물 약점 해소), 돌아가기 시뮬 확인

**할 일**
- pull 후 빌드 불필요(yaml·셸). 서브 PC: 상자·복도 벤치에 ToF 표시가 들어가므로 R5 재확인은 pull 뒤에

**변경**
- `nav2_params.yaml` local costmap STVL `tof_mark` 관측원(`/tof/points`, 마킹만, 2.0 m, 바닥 0.03 m 거름). 상자 3회 12/12·접촉 0(전 11/12·64.8 s 접촉). KNOWN_ISSUES "0° 낮은 장애물" 내림, TROUBLESHOOTING에 기록
- 돌아가기(93) 시뮬 확인: 비켜 주는 사람 복도 2회에서 `로봇에 막혀 … 돌아감` 3번, 서로 기다림 0, 충돌 0. 1회 목표 코앞 정체(미재현, KNOWN_ISSUES)
- `experiments/2026-10-14_planner_compare/stop_run.sh`: `sim_ctl.sh start` 셸도 끝냄(남아서 launch를 두 벌 띄우던 문제, TROUBLESHOOTING)
- `experiments/2026-10-14_tof_costmap/` 기록

**확인**
- 상자 tof0 ×3 12/12, 복도 diag 3/3(31.0·26.5·35.4 s)

## 2026-10-14 (94) R5 Q6 ②: 사람 때문에 기다리는 동안 경로 계획이 실패해도 목표를 끝내지 않음. 복도 재확인은 1/3이라 트리는 꺼 둠

**할 일**
- `build_limbo`. 주행 동작은 그대로(트리 꺼 둠)

**변경**
- BT 사본 두 개: 경로 계획 RecoveryNode(원래 1번짜리)를 `RecoveryNode 60`(`WaitForPersonWhilePlanning`: 다가옴·코앞 막힘이면 1 s Wait)으로 감싸고, 사람 때문이면 전역 costmap을 안 비움. 사람 때문이 아니면 기존 동작 그대로
- `docs/lab/reports.md` Q8

**확인**
- (93) 옆 힘 받은 뒤 트리를 켜고(작업 폴더에서만) 비켜 주는 사람 복도 3회: 9구간 모두 완주(계획 실패로 끝나는 일 없음). 그러나 2·3회는 복도 구간마다 60 s 기다림 — yield 사람이 1.4~1.6 m 앞에 다시 서서 안 움직임(복도 1.8 m, 메인 PC 모의는 2.4 m). 손님 4/4·상자 4/4, 회전·후진 0 ([기록](../experiments/2026-10-14_tof_wait_sub/README.md))

## 2026-10-14 (93) 비켜 주는 사람이 멈춘 로봇 정면에 막히면 옆으로 돌아감 (Q7 가)

**할 일**
- 빌드 불필요(파이썬 스크립트). 서브 PC: 기다리기 BT를 켜고 비켜 주는 사람 복도 3/3 재확인(R5)

**변경**
- `moving_obstacles.py`: yield형이 목표 방향 35° 안·1.5 m 안의 로봇에 막혀 0.2 m/s 아래로 1 s 넘게 느려지면, 로봇 방향에 수직인 두 쪽 중 벽 여유(0.8 m 앞 거리 변환)가 큰 쪽으로 3 m/s² 옆 힘을 더한다. 로봇이 뒤로 가거나 2.5 m 넘게 멀어지면 끝. 상수는 파일 위 `SIDESTEP_*`
- 왜: 멈춘 로봇 앞에서 목표 힘과 로봇 반발이 상쇄돼 사람도 서 버리고(소셜 포스 국소 최소점), 로봇은 "1 m 안 1 s 멈춤 = 손님"으로 기다려 서로 60 s 기다림(서브 PC 회귀). 실제 사람은 옆으로 돌아간다

**확인**
- 오프라인 모의(복도 폭 2.4 m, 로봇 가운데 정지, 사람 정면 접근): 1 s 막힌 뒤 왼쪽으로 돌아 로봇과 0.87 m 간격으로 지나침. 시뮬레이션 눈 확인은 아직 (서브 PC 재확인 때 같이)

## 2026-10-14 (92) 기다리기 트리 회귀 원인: 비켜 주는 시뮬레이션 사람과 로봇이 서로 기다림

**할 일**
- 없음 (기록만, 트리는 꺼 둔 그대로)

**변경**
- `experiments/2026-10-14_tof_wait_sub/` "회귀": 복도에서 "다가옴 정지" 60.5 s 동안 yield 사람이 로봇 1.0 m 앞에 서 있었음. social force로만 피하는 yield가 복도 한가운데 선 로봇을 못 돌아가고, 로봇은 전제 2-1대로 손님으로 보고 기다림. 섹터가 벽을 잡는다는 가설은 틀림. (86)의 "MID-360이 뒤 모서리" 서술 정정(로봇 중심 위)
- `docs/lab/reports.md` Q7: 서로 기다림을 시뮬레이션 사람 쪽에서 풀지, 로봇 비켜서기(R6)로 풀지

**확인**
- 재현 1회 녹화(`/scan`·ToF·래치·정답 위치)로 정지 동안 상태를 0.5 s마다 셈(`corridor_hold.py`)
## 2026-10-14 (92) 카메라 0.7 m·0°(앞 push `4dd827d` 포함), 컨트롤러 RPP 재비교(MPPI 유지), 0°의 낮은 장애물 약점 확인

**할 일**
- pull 후 `colcon build --packages-select limbo_description` (URDF 기본값)

**변경**
- `limbo.urdf.xacro`·launch: 카메라 기본 피치 15° → **0°**(높이 0.7 m 유지). 서브 PC 손님 장면 측정 0° 19 % / 8° 8 % / 15° 3 %(`experiments/2026-10-14_tof_wait_sub/`). 하반신 모델이 오면 재측정
- `experiments/2026-10-14_controller_rpp/`: 채택 설정에서 MPPI vs RPP 1회씩. 둘 다 완주, RPP는 홀·상자 10~18 % 빠르지만 복도 복구 5·경로 변경 15, 상자 0.11~0.21 m → **MPPI 유지**. 젯슨 CPU 문제 때 기준표
- `experiments/2026-10-14_camera_angle/`: 0° 상자 3회 추가. 30 cm 상자 윗면이 0.78 m 안에서 시야를 벗어나 2회차에 64.8 s 접촉 → `docs/KNOWN_ISSUES.md`에 적음. 다음은 ToF 점군을 costmap에 넣고 재확인
- `docs/lab/requests.md`: R5 Q6·Q7 답(카메라 0°, 서로 기다림은 시뮬 사람 돌아가기(메인 PC) + R6 둘 다)

**확인**
- 0° 복도 3/3, 상자 11/12(접촉 1회). RPP 벤치 10/10

## 2026-10-14 (91) 위치 추정 비교 1차(AMCL 유지), launch `localization:=amcl|slam|mapping`, 포즈그래프 생성 도구

**할 일**
- pull 후 빌드 불필요(launch·yaml·셸 링크). `localization:=slam`을 쓰려면 `tools/sim_trials/make_posegraph.sh aischool_2f aischool_2f_map`으로 포즈그래프를 먼저 만든다(24 MB, 저장소에 없음)

**변경**
- `start_simulation.launch.py`: `localization` 인자. `slam`은 slam_toolbox 위치 추정 노드(포즈그래프, bond 끔), `mapping`은 정적 지도 서버 + slam_toolbox(지도는 `/slam_map`)로 주행하며 포즈그래프를 쌓음. `limbo_navigation/config/slam_toolbox.yaml`, `tools/sim_trials/make_posegraph.sh`. `.gitignore`에 포즈그래프
- `experiments/2026-10-14_localization_compare/`: AMCL vs slam_toolbox × 복도·홀 각 1회(`run.sh`). 결론 AMCL 유지 — 주행 성적 같음, 홀은 slam 오차 0.029 m(AMCL 0.055), 복도는 slam 0.16 m 치우침(포즈그래프 프레임이 정적 지도·정답과 어긋남)
- `docs/TROUBLESHOOTING.md`: slam_toolbox heartbeat·포즈그래프 경로·지도 작성 모드 항목. `experiments/2026-10-14_planner_compare/stop_run.sh` 라벨 일반화

**확인**
- 지도 작성 주행(상자 구간 + 복도 왕복) 9구간 모두 성공, 포즈그래프 저장. slam 복도·홀 완주, 충돌 0, slam IS DOWN 0

## 2026-10-14 (90) 기다리기 트리를 끔: 비켜 주는 사람 복도에서 60번 기다리다 실패 (메인 PC 회귀 보고)

**할 일**
- 없음 (설정만). 주행은 Nav2 기본 트리로 돌아감

**변경**
- `nav2_params.yaml` `bt_navigator`: 기다리기 트리 세 줄을 주석으로. 메인 PC 보고(16:15): `aischool_2f_social` `people2` 복도→서쪽이 기다림 60번 뒤 ABORTED, 사람이 지나간 뒤에도 정지가 안 풀림. 원인 조사·수정 뒤 복도 3/3 통과를 확인하고 다시 켬

**확인**
- 없음 (끄기만)

## 2026-10-14 (89) R5 Q5: 카메라 0.7 m에서 피치 0·8·15° 손님 검출 비교 — 0°의 80 %를 넘는 각 없음, 기다리는 동안 계획 실패로 목표가 끝나는 빈틈

**할 일**
- 없음 (기록만, URDF 기본값 안 바꿈)

**변경**
- `experiments/2026-10-14_camera_pitch_sub/`: 손님 장면 각 3회·복도 각 1회·상자 1회. 손님이 시야·0.8~3 m 안일 때 검출 0° 19 %, 8° 8 %(45 %), 15° 3 %(18 %). 0° 복도 1구간은 다가온 사람 앞에서 기다리는 동안 전역 계획이 계속 실패해 목표 실패
- `docs/lab/reports.md` R5 Q5·Q6

**확인**
- 정답 위치와 예측 메시지를 녹화로 맞춰 셈(`guest_detect.py`) ([기록](../experiments/2026-10-14_camera_pitch_sub/README.md))
## 2026-10-14 (88) 경로 계획기 비교(NavFn 유지), nav_recorder 벽 거리 열, 시험 도구의 잔존 노드·데몬 문제 수정

**할 일**
- pull 후 빌드 불필요. 시뮬을 손으로 띄웠다 내릴 때도 `tools/sim_trials/sim_ctl.sh stop`으로 마무리(잔존 노드 정리)

**변경**
- `experiments/2026-10-14_planner_compare/`: NavFn·Smac 2D·Theta* × 복도·홀 각 1회(`run.sh`, 단건 `one.sh`). 결론 NavFn 유지 — 복도는 셋이 같고(51~56 s, 경로 20.3~20.4 m, 충돌 0), Smac 2D는 전역 경로 변경 13(NavFn 4)·MPPI 경고 11(2), Theta*는 홀에서 복구 6·65.7 s(NavFn 53.5·0). 충장로는 최종 단계라 선별에서 뺌
- `limbo_evaluation`: `/map` 거리 변환으로 `min_wall_distance_m`·`mean_wall_distance_m` 열(`walls.py`, 테스트)
- `tools/sim_trials/sim_ctl.sh`: (1) stop이 노드 실행 파일 경로 기준으로 잔존 프로세스를 모두 끝냄(이전 런치의 ekf·bridge가 TF·`/clock`을 또 내서 AMCL이 스캔을 전부 버리던 원인), (2) start가 대기 직전에 ros2 데몬을 재시작(오래된 데몬이 새 노드를 못 봐 멀쩡한 Nav2를 시작 실패로 판정하던 원인), (3) DDS 정리 뒤 데몬 재시작. 해결 기록 2건
- `docs/lab/requests.md`: R5 회귀 보고(켜 둔 기다리기 BT가 비켜 주는 사람 복도에서 60번 기다리다 포기 → 분기 끄고 커밋 요청), Q5 답, R7
- `docs/KNOWN_ISSUES.md`: 시작 직후 `follow_path` 액션 응답 20 ms 초과로 첫 Goal 실패(1/7회)
- 계획기 비교 스크립트는 lab에 켜 둔 기다리기 BT를 끄고(Nav2 기본 BT) 돌림

**확인**
- 잔존 정리·데몬 재시작 뒤 연속 7회 시뮬 시작 성공(계획기 6회 + 재실행 1회), 시작 실패 0

## 2026-10-14 (87) R7: 학원 2층 순찰이 채택 설정에서 막히는 원인 둘(A 모서리 지난 지점 검사, B가 사람 길 위)을 찾음

**할 일**
- 없음 (기록만)

**변경**
- `experiments/2026-10-14_aischool_regress_sub/`: 순찰 3회(Nav2 기본 트리) 1회 실패. A: 로봇이 모서리를 질러 A 0.7 m 안에 2 s만 있는데 `RemovePassedGoals`가 3 s에 한 번이라 빗나가면 A가 남아 되돌아가는 경로에서 맴돎. B: `person_2` 시간표가 B를 지나서 B 칸이 치명이 되면 B→C 구간 계획 실패(메인 PC 증상). 카메라 15° 바닥 가설은 아님
- `docs/KNOWN_ISSUES.md` 행 추가, `PROJECT.md` 8절 "그 밖에 열린 것", `docs/lab/reports.md` R7

**확인**
- 전역 costmap을 업데이트로 이어 붙여 실패 순간을 다시 만들고, 시간표로 사람 위치를 계산함 ([기록](../experiments/2026-10-14_aischool_regress_sub/README.md))

## 2026-10-14 (86) R5 Q5: 손님이 ToF 밖(0.5~1.5 m)에 서 있어도 정지를 유지하도록 /scan 앞 섹터 점유를 래치에 더함 (시뮬레이션 시험은 R7 뒤)

**할 일**
- `build_limbo`

**변경**
- `limbo_perception/tof.py` `sector_occupied`·`SectorConfig`: base_link 기준 범퍼 앞 ±30°, 1.5 m 안 `/scan` 점이 2칸 이상이면 점유(라이다가 로봇 뒤 모서리에 있어 라이다 기준 각도 대신 범퍼 기준). `ApproachWatch`는 "다가옴으로 정지" 뒤 ToF 막힘 **또는** 앞 섹터 점유 동안 유지. 정지 시작은 다가옴만이라 상자 앞에서 안 섬. 시험 3개 추가(15개)
- `tof_node`가 `/scan` 구독, `tof.yaml`에 숫자. `/scan`은 라이다 높이 띠(약 0.9~1.1 m)라 30 cm 상자는 안 잡힘

**확인**
- 단위 시험 15개. `tof_node` CPU(코어 하나 기준, 60 s 평균) 붙이기 전 8.3 % → 뒤 9.0 %
- 손님 장면·카메라 각도 시험은 R7 뒤

## 2026-10-14 (85) R5 Q4: 진로 위로 다가오는 사람이면 그 자리에 멈춰 기다리게 하고 트리를 켬. 손님 앞 정지는 검출 부족으로 8번 중 1번

**할 일**
- `build_limbo`. **주행 동작이 바뀜**: 다가오는 사람(`/person_approaching`)이나 사람 때문에 막힌 코앞(`/person_blocking`)이면 경로 추종을 멈추고 1 s씩 기다림(최대 60 s), 회전·후진 안 함

**변경**
- `limbo_perception/tof.py` `ApproachWatch`·`closest_approach`(시험 5개 추가, 12개): 사람 속도 방향 직선이 로봇 0.6 m 안을 지나면(3 m 안, 0.2 m/s 이상) 정지, 정지 뒤에는 ToF 막힘 동안 유지(카메라가 1 m 안을 못 봄), 다가옴·ToF 1 s 없으면 재개, 상한 60 s. `tof_node`가 `/person_approaching`을 내고 `ExternalShutdownException`도 받음. `tof.yaml`에 숫자·근거
- BT XML 두 개: `IsPersonApproaching`(같은 클래스 다른 이름)을 `ReactiveSequence` 멈춤 조건·costmap 비우기 막기·`Fallback(StopAndWaitForApproaching, WaitWhileBlocked)`에. `nav2_params.yaml`에서 켬
- `KNOWN_ISSUES` 3번 행, `docs/lab/reports.md` R5·Q5. 변경 기록 (84)가 두 개(서브 PC R5 Q3, 메인 PC prune_distance)라 이 항목은 (85)

**확인**
- 손님 2회 정지 1/8, 비켜 주는 사람 복도 3/3·+3.2·+6.4 s, 상자 4/4·상자 앞 정지 0, 모두 회전·후진 0
- 녹화: 손님이 정면에서 3 m → 0.8 m 곧장 오는 동안 예측에 사람 0건. 같은 장면 카메라 0.5 m 수평이면 사람 든 예측 19건(15°는 4건), 정지 2/4 ([기록](../experiments/2026-10-14_tof_wait_sub/README.md))

## 2026-10-14 (84) R5 Q3: 사람 때문에 막히면 경로 추종 자리에서 멈춰 기다리게 함. 기다리기는 되지만 손님은 미리 비켜 가 대부분 못 잡음 (분기 꺼 둠)

**할 일**
- `build_limbo` (조건 노드 이름·라이브러리가 `IsPersonBlocking`·`limbo_is_person_blocking_condition_bt_node`로 바뀜). 주행 동작은 그대로(분기 꺼 둠)

**변경**
- BT XML 두 개: R4의 복구 앞 분기를 빼고, Nav2 원래 `FollowPath` RecoveryNode(costmap 비우기 1번)를 `RecoveryNode 60`(`WaitWhileBlocked`: 래치 참이면 1 s Wait)으로 감쌈. `ReactiveSequence`로 래치 참이면 FollowPath를 멈추고, 사람 때문이면 costmap을 비우지 않음. 답의 한 단 구조는 사람과 무관한 실패에서 비우기가 60번 반복돼 두 단으로 둠
- `IsPersonBlocking`: 트리 안 세 개가 BT 노드·토픽마다 구독 하나를 같이 봄(따로 구독하면 막힌 순간 서로 다른 값을 봐 목표가 바로 실패했음). 로그는 판단이 바뀔 때만
- `KNOWN_ISSUES` 3번 행, `docs/lab/reports.md` R5·Q4

**확인**
- 고친 뒤: 손님 4/4·충돌 0·회전·후진 0, 기다림 1번(나머지 3번은 래치 전에 돌아감). 두 명 복도 58번 기다린 뒤 통과. 상자 4/4·래치 0 ([기록](../experiments/2026-10-14_tof_wait_sub/README.md))

## 2026-10-14 (84) MPPI `prune_distance` 1.7 → 2.5 채택

**할 일**
- pull 후 그대로 뜸(yaml 링크). ktj 반영 후보(메인 PC): `nav2_params.yaml` MPPI `prune_distance` 한 줄

**변경**
- `limbo_navigation/config/nav2_params.yaml` MPPI `prune_distance` 1.7 → 2.5, 주석에 근거(1.7이면 4 s 예측 × 0.425 m/s가 사실상 속도 상한; 충장로 직선 0.42 → 0.58 m/s, 사람 있는 복도·홀에서 충돌 0·사람 거리 동일에 시간 −22~27 %; 상한 0.75는 MPPI 경고가 늘어 보류)
- `experiments/2026-10-14_speed_social/README.md` 채택 절 + CSV 2개, `docs/PROJECT.md` 8절 5번

**확인** (`people_one.sh prune25`, 각 1회, 전 = 같은 날 1.7 회차)
- 시간표 한 명 복도: 41.2·27.5·36.7 → 31.2·20.9·25.4 s, 충돌 0, 사람 최소 0.49~0.87 m, 복구는 costmap 비우기 1·1(회전·후진 0)
- 상자: 4/4, 41.9~42.8 → 27.4~31.0 s, 닿음 0. 최소 거리는 0.16~0.29 m로 전(0.28~0.32)보다 가까워짐(기준 0.15 m 안). 2회 더 돌려 0.15 밑이면 재검토
- MPPI 경고 12(1.7 때 9~14)로 같은 범위
- 상자 구간 2회 추가(15:18~15:23): 최소 0.23~0.35 / 0.25~0.27 m, 닿음 0. 3회 12구간 모두 0.15 m 이상이라 2.5 유지

## 2026-10-14 (83) 속도 설정 A·B·C를 사람 있는 조건에서 재비교: B(`prune_distance` 2.5) 채택 권고

**할 일**
- 없음 (설정 변경 없음, 기록만). B 채택은 메인 PC가 결정 → `nav2_params.yaml` MPPI `prune_distance` 1.7 → 2.5 한 줄

**변경**
- `experiments/2026-10-14_speed_social/`: `run.sh`(A/B/C 적용·원복, 복도+홀 각 1회), CSV 6개, 결과·결론
- `docs/PROJECT.md` 8절 5번, `docs/lab/requests.md` R5 참고(`tof_node` 종료 Traceback)

**확인** (소셜 포스 사람, 각 1회)
- B: 복도 2구간 70.1 → 54.8 s, 홀 4구간 79.0 → 57.5 s. 충돌 0, 사람 최소 0.80/0.56 m(A 0.81/0.58), 복구 1(A 1), MPPI 경고 2(A 1)
- C(0.75 + 3.0): 47.3 / 54.8 s로 더 빠르지만 MPPI "모든 후보 충돌" 경고 9번, 상한이 실물 평지 최고 0.8 m/s에 붙어 보류(전제 2-4)

## 2026-10-14 (82) 컴퓨터 이름 정리: 메인 PC(노트북)·서브 PC 둘뿐, "학원 PC" 표현 삭제

**할 일**
- 없음

**변경**
- `CLAUDE.md`, `docs/PROJECT.md` 3·4·6절, `docs/lab/requests.md` 머리: "학원 PC/학원 컴퓨터/노트북"을 **메인 PC**(이 노트북 `kim-laptop`)로 통일. ktj 반영도 메인 PC 몫. 서브 PC는 `automaton-desk`. 그동안 변경 기록 "할 일"에 적은 "학원 PC 몫"은 모두 메인 PC 몫

## 2026-10-14 (81) `nav_recorder` 순찰(NavigateThroughPoses) 기록, 사람 접근 속도 열, DDS 공유 메모리 잠금 정리

**할 일**
- pull 후 빌드 불필요(파이썬·yaml·셸). 순찰 회차도 이제 CSV가 남는다(정지 waypoint 사이 묶음 하나가 한 줄, `action` 열로 구분)

**변경**
- `limbo_evaluation/nav_recorder.py`: `/navigate_to_pose`와 `/navigate_through_poses` 둘 다 구독(상태·피드백을 액션별로). CSV `action` 열. `/sim/people`·시간표 어느 쪽이든 가장 가까운 사람의 위치를 지표에 넘김
- `goal_metrics.py`: `person_approach_speed_mps`(사람 최소 거리 순간, 사람이 로봇 쪽으로 다가온 속도, 양수 = 다가옴)·`robot_speed_at_min_mps`(그때 로봇 속도). 0.5 s 전 위치와 비교(`speed_window`). 사람이 멈춘 로봇에 걸어 들어온 충돌(사람 탓)과 로봇이 간 충돌(로봇 탓)을 가른다. 테스트 3개(23개 통과). nan은 CSV에 빈칸
- `tools/sim_trials/sim_ctl.sh stop`: ROS·gz 프로세스가 없을 때 `ros2 daemon stop` + `/dev/shm/fastrtps_*` 삭제. SIGKILL로 죽은 노드가 포트 파일을 잠근 채 남기면 다음 시작이 3번 다 실패함(해결 기록 항목 추가, 알려진 문제 갱신)
- `README.md` CSV 열 표 2행, `docs/lab/requests.md` R5 Q3 답(경로 추종 자리의 RecoveryNode), `docs/PROJECT.md` 8절 3번

**확인**
- 소셜 포스 월드 `aischool_2f_social`에서 학원 2층 순찰 1회(`patrol_trial.sh rec2`): 213 s 완주, 묶음 2개가 `navigate_through_poses` 행으로 기록. 사람 최소 0.88·0.84 m, 접근 속도 −0.05·0.02 m/s, 로봇 0.41·0.0 m/s, 충돌 0
- 그 전 회차(rec1)는 DDS 포트 잠금으로 3번 다 시작 실패 → 정리 뒤 1번에 시작

## 2026-10-14 (80) R5 Q2: 기다리기 판단을 막히기 시작한 순간의 래치(/person_blocking)로, ToF 정지 거리 0.5 m. 손님 앞 BT 기다림은 아직 안 돎

**할 일**
- `build_limbo`. 시뮬레이션에 `/person_blocking`이 새로 나옴. 주행 동작은 그대로(분기 꺼 둠)

**변경**
- `limbo_perception/tof.py` `PersonBlocking`: ToF가 비었다 → 막힘으로 바뀌는 순간 직전 5 s 안에 앞 0.8~3 m에서 다가오던 사람을 봤으면 참, ToF가 1 s 넘게 비거나 60 s면 풂. `tof_node`가 `/person_blocking`을 냄. 시험 4개 추가(7개)
- `tof.yaml` `stop_distance` 0.30 → 0.50(로봇이 사람 앞에서 서는 자리 ToF 0.32~0.40 + 0.1, 근거 주석). `nav2_params.yaml` `lethal_radius` 주석이 이를 가리킴
- `IsPersonAhead`: `/person_blocking`만 봄(포트 `topic`). BT XML 두 개 포트 바꿈

**확인**
- 손님 다가옴 2회 4/4·충돌 0·회전·후진 0, 래치 참 3번인데 BT 분기 tick 0(로봇이 1~3 s 멈췄다 돌아서 지나감). 두 명 복도 기다림 2/14. 상자 4/4·래치 참 0. 손님 시험 2회는 (79) 사람 이동 스크립트 잔존 수정 전이라 2회째에 사람이 겹쳐 있었을 수 있음 ([기록](../experiments/2026-10-14_tof_wait_sub/README.md))

## 2026-10-14 (79) 소셜 포스 사람 눈 확인: GUI 깜빡임·순간이동 원인 둘 고침, 사람끼리 간격 넓힘

**할 일**
- pull 후 `build_limbo` (플러그인 C++). 월드를 바꿨으면 `aischool_2f_social`의 actor도 `interpolate_x` false

**변경**
- `plugins/actor_pose_control.cpp`: 명령 때만 갱신 → 매 물리 스텝마다 목표 쪽으로 `max_speed`(2.0 m/s) × dt 보간하고 옮긴 거리만큼 애니메이션 진행. GUI가 그 사이 프레임을 다른 자세로 그려 깜빡이던 것을 없앰
- `scripts/moving_obstacles.py`: gz transport가 삼키던 SIGINT·SIGTERM을 `sys.exit`로 덮어 launch 종료 때 잔존하지 않게. 잔존 스크립트가 같은 actor에 다른 위치를 보내 "순간이동"으로 보였음. 사람끼리 미는 힘 2.0 → 3.0(복도에서 어깨 간격 0.54 m가 좁아 보임)
- 월드 `aischool_2f_social`, 시나리오 월드 2개: actor `interpolate_x` false (루트 이동이 위치에 더해져 미끄러짐). `README.md` 한 줄
- `docs/TROUBLESHOOTING.md` 항목 1, `experiments/2026-10-14_social_people/README.md` 눈 확인 절

**확인**
- 사람 4명 시험 월드(복도에 셋, 홀에 손님)를 gui로 봄. 사용자: "확실히 매끄럽다. 사람인 내 기준에 움직임의 95 %는 리얼. 둘이 마주쳤을 때 서로 피해 주려 살짝 움찔하는 것까지"
- 명령 위치 15 s: 한 스텝 최대 0.05 m, 방향 뒤집힘 0, 벽 0.45 m 이상, 사람끼리 0.54 m 이상
## 2026-10-14 (78) 학원 2층 반복 순찰이 2바퀴째부터 A 앞에서 막혀서, 반복용 waypoint 사본에서 A를 stop으로 둠

**할 일**
- `build_limbo`. 반복 시연은 `LOOP=1 tools/demo_patrol.sh`(새 사본이 기본)

**변경**
- `limbo_patrol/config/aischool_loop_waypoints.yaml`: `aischool_waypoints.yaml`에서 A만 `stop`. 2바퀴째부터 G → A → B가 같은 복도를 내려왔다 되돌아가서, A가 `pass`면 로봇이 A 0.8 m 앞에서 먼저 북쪽으로 돌아서고 지난 지점 판정 반경 0.7 m 밖이라 "진전 없음"을 반복했음. 반경을 늘리지 않고 목표를 A에서 끊음. 원본은 다른 시험이 쓰므로 그대로
- `tools/demo_patrol.sh`: `LOOP=1`이면 이 사본이 기본. `README.md` 한 줄
- `KNOWN_ISSUES`·`PROJECT.md` 8절의 A 앞 막힘 행을 지움

**확인**
- 시연 스택(사람 10명): 고치기 전 2·3바퀴째 G → A에서 세 번 막힘(collision monitor는 둘레 0.6 m 안 점 0이라 원인 아님). 고친 뒤 3바퀴 연속 다시 시도·복구 0 ([기록](../experiments/2026-10-14_loop_patrol/README.md))

## 2026-10-14 (77) 순찰이 이동 실패로 멈춰도 알림이 없어서, 서버가 순찰 상태로 알림을 만들게 함. 휴대폰 원격 제어 확인

**할 일**
- 관제 서버 다시 시작 (UI는 그대로)

**변경**
- `dashboard/server/state.py` `check_patrol`: 순찰 사유 `navigation failed, retry n/m` → 정보 "이동이 막혀 다시 시도합니다", `paused` + `navigation failed` → 경고(켜진 문제) "순찰이 멈췄습니다: 이동 실패 (다음 목표 X). 확인 후 재개해 주세요", `failed` → 오류. 다시 `patrolling`이면 풀고 복구 알림. 같은 (상태, 사유)는 한 번만. 요청에 의한 일시정지는 알림 안 만듦
- 시험 3개(`tests/test_control.py`)
- `KNOWN_ISSUES`: 학원 2층 A 앞 (-6.9, 0.55)에서 반복해서 막힘(collision monitor가 `/cmd_vel` 0). `PROJECT.md` 8절 "그 밖에 열린 것", `CONTROL_SCREEN.md`

**확인**
- 서버 시험 58개 통과
- 시연 스택: 휴대폰(ngrok + basic auth)에서 일시정지·재개 각각 1초 안에 확인됨. 알림 수정 뒤 멈춘 상태에서 경고가 뜨고 재개하면 풀림 ([기록](../experiments/2026-10-14_loop_patrol/README.md))

## 2026-10-14 (76) PROJECT.md 8절 "지금 상태와 다음"을 10-14 저녁 기준으로 다시 씀

**할 일**
- pull 받으면 `docs/PROJECT.md` 8절부터 읽는다

**변경**
- `docs/PROJECT.md` 8절: 되는 것·안 되는 것·다음을 오늘 결과로 갱신. 다음은 R5(래치+ToF 기다리기) → R6(비켜선 뒤 기다리기) → 소셜 포스 다듬기·nav_recorder 순찰 지원 → 실물 준비(카메라 실측·ToF 드라이버·하반신 모델) 순. 끝낸 것 한 줄 요약, 열린 것에 heartbeat·far clip 추가

## 2026-10-14 (75) 전역 STVL 기억 3초 vs 15초 × 복도 3회: 전역 경로 변경 횟수 같음, 0번 닫음

**할 일**
- 없음 (기록만, 설정은 3초 그대로)

**변경**
- `experiments/2026-10-14_stvl_plan_changes/`: `run.sh`(값 바꾸고 원복), CSV 6개, 결과·결론
- `docs/KNOWN_ISSUES.md` 맨 위 0번 닫음, `docs/PROJECT.md` 8절 0번 끝·안 되는 것 문구

**확인** (한 명 복도 `people2`, 조건당 3회)
- 복도 구간 전역 경로 변경: 3초 3.3·4.0, 15초 4.0·3.7 (회차별 2~6). 복구 합 2·2 vs 1·2, 사람 최소 0.39·0.41 vs 0.37·0.37, 충돌 1 vs 2. 18구간 모두 성공
- "사람 꼬리가 전역 경로를 흔든다"는 가설은 확인 안 됨. 경로가 바뀌는 건 사람의 현재 위치. 3초는 작은 값이라 유지

## 2026-10-14 (74) 카메라 기본 배치를 0.5 m 수평 → 0.7 m 아래 15°로 채택

**할 일**
- pull 후 그대로 뜸(xacro·launch 링크). 실물 카메라 마운트를 0.70 m·아래 15°로 맞추고 피치를 실측해 URDF와 같게 할 것(기울인 깊이 카메라는 1° 오차에 3 m 앞 바닥이 5 cm 떠 보임)

**변경**
- `limbo.urdf.xacro` `camera_z` 0.50 → 0.70, `camera_pitch_deg` 0 → 15 (왜: 짧은 치마 밑단보다 높게 두어 올려다보는 구도를 없애고, 근거리 바닥이 1.0 → 0.78 m 앞부터 보임. 12·15·18° 비교에서 사람 검출·상자 costmap은 전과 같음, 67). `gazebo.launch.py`·`start_simulation.launch.py` 인자 기본값도 같게
- `docs/PROJECT.md` 1절 카메라 사양, 열린 것(센서 배치 → 채택). `experiments/2026-10-14_camera_angle/README.md` 채택 절 + CSV 2개

**확인** (`people_one.sh cam15`, 각 1회)
- 한 명 복도: 3구간 성공, 복구 0(전 1·2), 사람 최소 0.50~0.69 m(전 0.34~0.55), 충돌 0
- 상자 구간: 4/4, 최소 0.28~0.32 m, 닿음 0 (전과 같음)

## 2026-10-14 (73) R5 ToF 근접 센서·노드를 넣었지만 "카메라 기억 + ToF" 기다리기 조건은 막힘 (분기는 꺼 둠)

**할 일**
- `build_limbo` (URDF·bridge·launch·C++). 시뮬레이션에 `/tof/points`, `/tof/obstacle_ahead`, `/tof/nearest`가 새로 나옴. 주행 동작은 그대로

**변경**
- `limbo_description`: `tof_link`(앞 x 0.25, z 0.10, 수평), gz `gpu_lidar` 8×8 ±31.5° 0.02~4 m 10 Hz. `bridge.yaml` `/tof/points`
- `limbo_perception`: `tof_node`·`tof.py`(바닥 0.03 m 위 점 중 센서 앞 0.30 m 안이면 막힘, 3프레임 연속이어야 바뀜)·`config/tof.yaml`·`test_tof.py` 3개. `start_simulation.launch.py`에 추가
- `IsPersonAhead`: 입력을 "최근 5 s 안 0.8~3 m에서 다가오던 사람(카메라) AND ToF 막힘"으로. 분기는 `nav2_params.yaml`에서 꺼 둔 그대로
- `KNOWN_ISSUES` 3번 행, `PROJECT.md` 8절 3번: 막힘 근거

**확인**
- ToF 단독(상자 0.485/0.235 m), tof1·tof2(상자 4/4·상자 앞 기다림 0, 한 명 복도는 분기 tick 0), 두 명 복도 2회(기다림 1/25). 멈춘 뒤 복구까지 약 20 s라 기억 5 s가 끝나 있고, 사람 앞 ToF 0.32~0.40 m에서 멈춤 ([기록](../experiments/2026-10-14_tof_wait_sub/README.md))

## 2026-10-14 (72) 서브 PC 요청 R6: 정면으로 오는 안 비켜 주는 사람 앞에서 비켜선 뒤 기다리기 (R5 뒤)

**할 일**
- 서브 PC: R5 끝난 뒤 지시서대로

**변경**
- `docs/lab/requests.md` R6, `experiments/orders/2026-10-14_sub_pull_over.md`: 조건 `IsPersonOncoming`(카메라가 잘 잡는 1.5~4 m에서 진로 위·다가옴), 액션 `ComputePullOverPose`(local costmap으로 좌·우 0.55 m 중 비용 낮은 쪽), BT 분기(비켜선 뒤 R5 조건이 거짓일 때까지 기다림, 상한 약 20 s), 손님과의 구분(approach_intent면 비켜서지 않고 R5 기다리기), 받아들이는 기준(no_yield 충돌 0·0.5 m 이상, 나머지 유지)
- `docs/PROJECT.md` 8절 3번에 R6 한 줄

## 2026-10-14 (71) 소셜 포스 시나리오(no_yield 복도·approach 홀) × HumanLayer 켬/끔: 정면 조우는 둘 다 뚫림

**할 일**
- 없음 (기록·시험 벤치). R5(BT)에 "비켜서 기다리기" 요구를 더할지 노트북이 정함

**변경**
- `experiments/2026-10-14_social_people/`: 시나리오 월드 `worlds/zz_social_noyield`(복도 가운데 폰 보는 사람), `zz_social_approach`(홀 손님) + 설정, `run_scenarios.sh`(켬/끔 × 2 시나리오, 설정 원복), 결과 CSV 4개와 해석
- `tools/sim_trials/nav_route.py`: `hall` 경로(홀 서쪽 ↔ 출발점 2왕복)
- `scripts/moving_obstacles.py`: launch 종료 때 ROS publish 예외를 조용히 넘김

**확인** (각 1회)
- no_yield 정면: 켬 0.02·0.02 m, 끔 0.09·0.09 m — 둘 다 충돌. 로봇은 사람 앞에서 멈추지만(켬 3.3·2.6 s, 끔 1.2·2.4 s) 복도 가운데라 그대로 뚫림. 치명 비용은 로봇이 사람에게 들어가는 것만 막고 옆으로 비켜서는 행동은 못 만듦
- approach 손님: 켬/끔 모두 충돌 0·복구 0, 최소 0.56~0.72 m. 로봇이 손님을 돌아서 지나감(멈춰 기다리기는 R5 BT 몫)
- HumanLayer 켬/끔 차이는 1회로는 못 가름. 두 시나리오를 BT 시험 벤치로 씀

## 2026-10-14 (70) 소셜 포스 사람: gz 플러그인 `ActorPoseControl` + `moving_obstacles.py` 유형 셋, 월드 `aischool_2f_social`

**할 일**
- pull 후 `build_limbo` (C++ 플러그인, 월드 사본). 비켜 주는 사람 월드: `world:=aischool_2f_social map:=aischool_2f_map`

**변경**
- `limbo_simulation/plugins/actor_pose_control.cpp`(+CMake, package.xml): 토픽 `/limbo/actor_poses`(Pose_V)대로 actor의 `TrajectoryPose`·`AnimationTime`을 바꾸는 gz-sim 시스템 플러그인. actor는 set_pose로 안 움직여서 필요(해결 기록 "Gazebo actor를 set_pose로 옮길 수 없음"). `gazebo.launch.py`가 `GZ_SIM_SYSTEM_PLUGIN_PATH`에 `install/limbo_simulation/lib` 추가
- `scripts/moving_obstacles.py`: 물체 고리 이동은 그대로, 사람(`people`) 추가 — 유형 `yield`(로봇을 사람처럼 피함) / `no_yield`(로봇을 안 봄) / `approach`(3 m 안이면 다가와 0.8 m에 멈춰 `wait`초 머물다 감). 힘은 Helbing 꼴(목표 τ 0.5 s, 사람 2.0/0.3, 로봇 3.0/0.4, 벽은 지도 거리 변환 5.0/0.15). 사람 위치를 `/sim/people`(PoseArray)·`/sim/people_names`로 ROS에도 발행(ROS 없으면 생략)
- `limbo_evaluation/nav_recorder.py`: `/sim/people`이 0.5 s 안에 왔으면 SDF 시간표 대신 그 위치로 사람 거리를 잼
- 월드 `aischool_2f_social.sdf`(시나리오 월드에서 actor 제거 + 플러그인 + 사람 2명), `aischool_2f_social_movers.json`
- `experiments/2026-10-14_social_people/`: 오프라인 점검과 첫 회차. `docs/TROUBLESHOOTING.md` 항목 1, `docs/PROJECT.md` 8절 4번·안 되는 것, `docs/KNOWN_ISSUES.md` 복도 행 대책, `README.md` 절 1

**확인**
- 오프라인(`Person.step`): 정지 로봇 옆 통과 yield 0.96 m / no_yield 0.05 m, approach 0.8 m 정지 후 재출발
- 한 명 복도 `people2` 1회(yield): 3구간 성공, 복구 0, 사람 최소 0.81·0.89 m(시간표 사람 때 0.34·0.55), "진전 없음" 0(2), MPPI 경고 1(14). YOLO·HumanLayer가 플러그인 actor를 그대로 잡음
## 2026-10-14 (69) 이동이 실패해도 순찰을 끝내지 않고 2번 다시 가 본 뒤 멈춰서 사람의 재개를 기다리게 함

**할 일**
- `build_limbo`, 관제 화면 `pnpm build`. 순찰 노드 파라미터 `retries`(2), `retry_delay_sec`(3.0) 추가

**변경**
- `limbo_patrol/patrol_node.py`: Nav2 실패 → `retry_delay_sec` 뒤 남은 지점으로 다시(지난 지점으로 안 돌아감), `retries`번 넘으면 `paused`(사유 `navigation failed`)로 대기, 재개하면 남은 지점부터·횟수 0부터. 대기 중 일시정지도 받음. `CONTROL_SCREEN.md` A 4단계 A안 그대로(계약 안 바꿈). 숫자 2·3초는 계획 문서 안 그대로
- `limbo_patrol/test/test_failure_handling.py`: 가짜 navigator로 4개(한 번 실패 → 계속, 다 실패 → 멈춤 → 재개, 지난 지점 안 감, 대기 중 일시정지)
- 관제 화면 순찰 카드: 사유로 "순찰 중 · 이동 다시 시도 (1/2)", "이동 실패 · 확인 후 재개"(주황) + 안내 문장. 긴 배지가 휴대폰 폭에서 줄바꿈되게
- `KNOWN_ISSUES`: "실패하면 순찰 끝냄" 행을 지우고, Nav2가 도달 못 하는 목표에서 실패를 20분 넘게 늦게 내는 행으로 바꿈. `PROJECT.md` 8절, `README.md`, `CONTROL_SCREEN.md`

**확인**
- 단위 시험 4개, UI 시험 25개 통과
- 학원 2층 B 위에 상자: 다시 시도 1/2·2/2와 화면 표시 확인, 상자 치우자 18초 뒤 이어서 순찰. 세 번째 실패는 17분 넘게 안 나서 멈춤 상태는 시뮬레이션에서 못 봄 ([기록](../experiments/2026-10-14_loop_patrol/README.md))

## 2026-10-14 (68) 서브 PC 요청 R5: ToF 근접 센서 + 기다리기 조건 입력(카메라 기억 + ToF)

**할 일**
- 서브 PC: 지시서대로. 노트북은 소셜 포스 사람(PROJECT 다음 4번) 시작

**변경**
- `docs/lab/requests.md` R5·R4 답, `experiments/orders/2026-10-14_sub_tof_wait.md`: 실물 ToF 결정(VL53L5CX 1개, 범퍼 높이 10 cm 전면 수평, 젯슨 오린 나노 I2C 직결)에 맞춘 시뮬레이션 센서(gpu_lidar 8×8, 63°)와 노드 인터페이스(`/tof/obstacle_ahead` Bool 연속 3프레임 확정, `/tof/nearest`), `IsPersonAhead` 조건을 "최근 5 s 카메라가 0.8~3 m에서 다가오는 사람을 봤음 AND ToF 0.3 m 안 물체"로. 받아들이는 기준은 R4와 같되 상자 앞 기다림 0
- `docs/PROJECT.md` 8절 3번: R4 결과와 R5 방향

## 2026-10-14 (67) 카메라 높이·피치 비교(0.5 m 수평 vs 0.7 m 12·15·18°): 네 조건 같음, URDF·launch에 카메라 인자

**할 일**
- 없음 (기본값은 그대로 0.5 m·0°). 각도를 정하면 `limbo.urdf.xacro`의 `camera_z`·`camera_pitch_deg` 기본값만 바꾸고 `build_limbo`

**변경**
- `limbo_description/urdf/limbo.urdf.xacro`: `xacro:arg camera_z`(0.50)·`camera_pitch_deg`(0) → 카메라 joint rpy에 피치 적용. `limbo_simulation/launch/gazebo.launch.py`, `limbo_bringup/launch/start_simulation.launch.py`: 같은 이름의 launch 인자를 xacro에 넘김(robot_state_publisher와 self_filter 둘 다). 기본값이 전과 같아 동작 변화 없음
- `experiments/2026-10-14_camera_angle/`: 측정 월드 2개(사람 한 명 정면 접근, 지도에 없는 상자 3개), 측정 노드 `camera_probe.py`(거리 구간별 검출 비율·위치 오차, 상자 costmap 최대 비용), 실행 `run_angles.sh`, 결과·결론
- `docs/KNOWN_ISSUES.md` "2 m 안 다리만 보임" 행에 측정값, `docs/PROJECT.md` 열린 것(센서 배치)

**확인** (조건당 1회, 로봇 정지)
- 사람 검출: 네 조건 모두 1.5 m 안 0 %, 2.5~4.5 m 50~100 %, 4.5 m 밖 0 %(시뮬 카메라 far clip 5 m). 위치 오차 2 m에서 0.6~0.7 m, 3.5 m에서 0.1~0.2 m
- 상자(30 cm 0.5 m, 30 cm 0.8 m, 10 cm 1.0 m): 네 조건 모두 치명(100)으로 찍힘
- 결론: 가까운 사람을 못 잡는 건 각도가 아니라 전신 YOLO 모델 문제(하반신 모델 필요). 각도는 개인정보·근거리 바닥·설명 가능성으로 정하면 되고 0.7 m 15°는 잃는 게 없음
## 2026-10-14 (66) R4 BT "사람이면 기다리기" 조건 노드·트리를 만들었지만 가까운 사람 인식이 끊겨 막힘 (분기는 꺼 둠)

**할 일**
- `build_limbo` (C++ 플러그인이 새로 생김). 주행 동작은 그대로(분기를 `nav2_params.yaml`에서 켜지 않음)

**변경**
- `limbo_navigation`: BT 조건 노드 `IsPersonAhead`(`src/is_person_ahead_condition.cpp`, 앞 2.0 m·폭 0.8 m 안 사람이 영상 시각 1.0 s 안이면 참, 세 값은 XML 포트), Nav2 기본 트리 사본 2개(`behavior_trees/`, 복구 앞에 사람이면 Wait 5 s), CMake·package.xml 의존성
- 판단 로그는 바뀔 때나 1초마다만(ReactiveFallback이 10 ms마다 다시 물어 1초 100줄이 나왔음)
- `KNOWN_ISSUES` 맨 위 3번, `PROJECT.md` 8절 다음 3번: 막힘 근거

**확인**
- 한 명 복도·상자 before/wait1/wait2: 상자 4/4·닿음 0·상자 앞 기다림 0. 한 명 복도는 바깥 복구까지 안 가서 분기 시험 불가
- 시험은 (63) HumanLayer 치명 비용 전 코드(`07f240f`)
- 두 명 복도 2회: 바깥 복구 때 사람 위치가 4~13초 전 것이라 대부분 회전·후진. 녹화로 1 m 안 사람 인식 10~16% 확인 ([기록](../experiments/2026-10-14_bt_wait_sub/README.md))

## 2026-10-14 (65) HumanLayer 네모 화면 확인: 로봇은 더 멈추지만 비켜 주지 않는 사람이 걸어 들어옴, 순찰 bag 사람 거리 도구

**할 일**
- 없음 (기록·도구). 사람 있는 평가는 소셜 포스 사람(PROJECT 다음 4번) 뒤에

**변경**
- `tools/sim_trials/bag_person.py <bag> <월드>`: 순찰 bag의 정답 위치와 월드 사람 시간표로 묶음별 사람 최소 거리·0.3 m 미만 시간·멈춤 시간, 최소 거리 순간의 로봇 속도와 사람 접근 속도. nav_recorder가 NavigateThroughPoses(순찰)를 안 받아서 만든 보조 도구
- `experiments/2026-10-14_human_layer_lethal/README.md`: 네모 화면 2회 표와 전체 결론
- `docs/KNOWN_ISSUES.md` 2번·collision_monitor 행, `docs/PROJECT.md` 8절 2·4번

**확인** (`human_test_world` 사람 10명, `test_waypoints.yaml`, 2회)
- 1회차: J 직전 실패 — 사람 탓이 아니라 `controller_server` heartbeat 4 s 끊김으로 lifecycle manager가 Nav2 전체를 내림(사람 두 명 새로 잡힌 직후). 2회차: 완주 247 s, heartbeat 끊김 없음
- 사람 최소 거리 0.03~0.57 m(전 0.01~0.07)로 같은 급. 최소 순간에 사람이 0.5~1.0 m/s로 로봇(0.04~0.4 m/s)에 걸어 들어옴 → 로봇이 멈춰도 actor가 뚫고 지나감. HumanLayer는 로봇이 사람에게 들어가는 쪽만 막음
- 로봇은 사람 앞에서 더 멈춤(2회차 A→C 멈춤 24.7 s 중 사람 앞 17.5 s)

## 2026-10-14 (64) HumanLayer 치명 비용 확인: 한 명 복도·상자 구간 유지, 사람 앞에서 멈춤

**할 일**
- 없음 (기록만). 네모 화면(사람 10명) 확인은 다음 회차

**변경**
- `experiments/2026-10-14_human_layer_lethal/`: 전(`c6fc8cd`)·후(`01bb310`) CSV와 요약
- `docs/KNOWN_ISSUES.md` 2번, `docs/PROJECT.md` 8절 2번: 확인 결과 반영

**확인** (조건당 1회, `people_one.sh hl1`)
- 한 명 복도: 3구간 성공, 시간 40.7·32.3·33.5 s(전 41.9·31.9·35.0), 충돌 0, 회전·후진 0. 사람 앞 멈춤 2.3 → 3.3 s, "진전 없음" 2번 → costmap 비우기 복구로 지나감(R4 BT Wait가 들어갈 자리)
- 상자 구간: 4/4, 상자 최소 0.28~0.31 m, 닿음 0 (R3 3초 회차와 같음)
- 복도→동 구간 사람 최소 0.34 m(전 0.53)는 원인 미확정(멈춘 로봇 쪽으로 actor가 걸어온 것 또는 카메라 시야 밖). 0.3 m 기준 충돌 아님

## 2026-10-14 (63) HumanLayer: 사람 몸 안을 치명 비용으로, 숫자 전부 yaml로 (알려진 문제 2번)

**할 일**
- pull 후 `build_limbo` (C++). 시뮬레이션에서 사람 통과 확인은 아직 안 함 — 다음 회차에 `people2`와 네모 화면으로 `person_collision`·시간 비교

**변경**
- `limbo_navigation/src/human_layer.cpp`, `include/.../human_layer.hpp`: 다시 씀(567 → 250줄)
  - 사람 **현재 위치**와 `lethal_time`(0.5 s) 안 예측점은 `lethal_radius`(0.25 m, 어깨 폭 기준 몸 반경) 안을 치명(254)으로. 전에는 현재 위치를 아예 안 칠하고(예측점 0.25 s부터) 최고 비용이 220이라 MPPI 장애물 critic의 충돌 판정(254)에 걸리지 않아 사람을 뚫는 궤적을 골랐음(10-13 복도 실험, 네모 화면 0.01~0.07 m)
  - 그 뒤 예측점은 전처럼 가우시안(220 → 110). 예측 경로 전부를 치명으로 하지 않는 이유는 PROJECT 2-1 "사람만 보면 우회" 금지
  - 치명 셀은 뒤에 오는 inflation 층이 로봇 반경만큼 부풀리므로 몸 반경만 칠함
  - 상수 9개를 `declare_parameter` + yaml로(`lethal_radius`, `lethal_time`, `radius`, `sigma`, `near/far_peak_cost`, `min/max_prediction_time`, `min_cost`). 기존 값은 그대로
  - 함수를 단계별로 나눔(bounds / 신선한 예측 고르기 / 사람 하나 / 원 하나). 2초마다 찍던 INFO 로그 2줄을 DEBUG로(시뮬 로그 1.7 MB 중 대부분이 이것이었음)
- `nav2_params.yaml` local costmap `human_layer`: 위 값과 이유
- `docs/KNOWN_ISSUES.md` 2번, `docs/PROJECT.md` 5절 4·8절 2번

**확인**
- `colcon build --packages-select limbo_navigation` 경고 없음. 동작 확인은 시뮬레이션 회차 뒤에
## 2026-10-14 (62) 따로 명령하지 않으면 waypoint를 끝없이 도는 반복 순찰(`loop:=true`)을 넣음

**할 일**
- `build_limbo`. 반복하려면 `-p loop:=true` 또는 `LOOP=1 tools/demo_patrol.sh` (기본은 지금처럼 한 바퀴)

**변경**
- `limbo_patrol/patrol_node.py`: `loop` 파라미터. 마지막 구간 뒤에 첫 구간부터 다시 돌고, 바퀴가 바뀌면 상태 사유 `lap N started`. 마지막 구간에서 정지했을 때 다음 waypoint 번호도 첫 번째로 돌림. 메시지는 그대로
- `tools/demo_patrol.sh`: `LOOP=1`, `README.md` 순찰 참고에 한 줄
- `docs/KNOWN_ISSUES.md`, `docs/PROJECT.md` 8절: 이동 한 번 실패하면 반복도 끝난다는 근거 추가

**확인**
- `aischool_2f`(사람 10명) 시연 스택: 1바퀴 약 155 s 뒤 A부터 2바퀴째, 2바퀴째 일시정지·재개 confirmed. 그 뒤 A 1.8 m 앞에서 2분간 진전 없음으로 Nav2 실패 → 순찰 끝남 ([기록](../experiments/2026-10-14_loop_patrol/README.md))

## 2026-10-14 (61) 서브 PC 요청 R4: BT "사람이면 기다리기" 분기 (알려진 문제 3번)

**할 일**
- 서브 PC: 지시서대로 pull → `build_limbo` → 구현 → `people_one.sh`로 전·후 비교

**변경**
- `docs/lab/requests.md` R4, `experiments/orders/2026-10-14_sub_bt_wait.md`: 설계(C++ BT 조건 노드 `IsPersonAhead`가 `/person_detector/person_position_base`로 앞 2.0 m·폭 0.8 m 안 사람을 보고, 복구 분기 앞에 Wait 5 s), 시험 방법, 받아들이는 기준(복도에서 회전·후진 0·충돌 0, 상자 구간은 전과 같아야 함), 하지 말 것(timeout 숫자로 때우기)
- `experiments/orders/people_one.sh <라벨>`: 한 명 복도 + 상자 구간을 설정 변경 없이 1회씩 도는 스크립트(R3 스크립트에서 설정 바꾸는 부분을 뺀 것)
- `docs/KNOWN_ISSUES.md` 1번 행: 시뮬레이션 확인 끝남으로

## 2026-10-14 (60) 해결 기록 보강(기술적 고생 10건), 시험 도구의 Nav2 active 검사 오류 수정, 새 지표 한 명 복도 확인

**할 일**
- 없음 (문서·스크립트만)

**변경**
- `docs/TROUBLESHOOTING.md`: 변경 기록·실험 기록에만 있던 기술적 고생을 해결 기록으로 옮겨 적음 — 물리 스텝(RTF 0.6→0.95), Nav2 configure 멈춤과 도구 우회, 프로세스 정리(pkill -f·gz gui·잔존 launch·SIGINT 무시), 충장로 월드 생성(격자·메모리·막힌 공간·메시 크기), 두 PC 도메인 분리, bag 숨김 토픽·재색인, `prune_distance` 속도 상한, 순찰 노드 30초 대기, 브랜치 전환 후 인터페이스 재빌드. 맨 끝에 H2로 붙어 있던 막다른 통로 항목을 주행 절로 옮김
- `docs/PROJECT.md` 4절: 해결 기록에 "기술적으로 고생한 것은 빠짐없이(원인 찾는 데 시간 든 것, 우회, 포기한 대안), 로그·숫자·커밋 포함, 단순 실수는 제외"
- `tools/sim_trials/sim_ctl.sh`, `tools/demo_patrol.sh`: `bt_navigator` 상태 확인을 `grep -q active` → `grep -q '^active'`. 전 것은 `inactive`에도 맞아 Nav2 활성화 실패를 "준비됨"으로 넘겼음(오늘 한 명 복도 1회차: Goal 3개 모두 `Action server is inactive` 거부)
- `docs/KNOWN_ISSUES.md` collision_monitor 행: 확인할 후보로 SIGKILL 뒤 남는 `/dev/shm/fastrtps_*` 조각(오늘 250개 있었음, 지우고 돌린 다음 회차는 1번에 시작) — 관련 여부 미확인

**확인** (한 명 복도 `people2`, `zz_single`, 전역 STVL 3초, `c6fc8cd`, 1회)

| 구간 | 시간 s | 속도 | 복구 | 사람 최소 m | 충돌 | 멈춤 s (사람 앞 / 그 외) | 경로 변경 / 수신 |
|---|---|---|---|---|---|---|---|
| 홀 → 왼쪽 복도 | 41.9 | 0.35 | 0 | 0.87 | 0 | 3.3 (0.0 / 3.2) | 5 / 41 |
| 복도 → 동쪽 | 31.9 | 0.31 | 0 | 0.53 | 0 | 4.0 (2.3 / 1.7) | 5 / 32 |
| 복도 → 서쪽 | 35.0 | 0.30 | 0 | 0.49 | 0 | 6.3 (0.7 / 5.6) | 1 / 35 |

- 새 열이 서로 맞음(멈춤 합 ≤ 시간, 사람 앞 ≤ 멈춤 합, 충돌 0 ↔ 최소 0.49 m 이상). 전역 경로는 1초마다 들어오고(수신 ≈ 시간) 그중 0.3 m 넘게 바뀐 게 1~5번
- "그 외 멈춤"에는 출발 직후·도착 직전의 정지가 들어감(구간마다 2~3초). 사람 없는 구간끼리 비교할 때 기준선으로 보면 됨
- 이번 회차는 복구 0·사람 0.49 m 이상으로 R3(3초: 복구 4, 0.24 m)보다 좋았지만 1회라 비교 아님

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
