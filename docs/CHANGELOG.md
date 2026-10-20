# 변경 기록

2026-10-02 리팩터링을 기준으로 나눈다.
- **리팩터링 이후**: ktj 작업. dev에 push할 때마다 맨 위에 추가한다. pull 받은 뒤 해야 할 일은 "할 일"에 적는다.
- **리팩터링 이전**: 원작자 작업. git 히스토리로 정리해 둔 기록이며 더 이상 추가하지 않는다.

---

# 리팩터링 이후 (2026-10-02 ~, ktj 작업)

## 2026-10-19 (38) dashboard README: v1 연결에서도 일시정지는 열린다고 버튼 잠금 설명 고침

**변경**
- 코드 변경 없음. (37)에서 "v1 송신기만 연결하면 버튼은 잠긴다"고 적었으나, 실제로는 순찰 재개만 잠긴다. `ui/src/control.ts`의 `pauseReason`은 순찰 상태를 모를 때도 일시정지를 열어 둔다(멈추는 쪽은 막지 않음, `control.test.ts` "모르면 누를 수 있음"). PR 리뷰(Copilot) 지적
- `dashboard/README.md` 세 곳: 소개, 「버튼 잠금」(순찰 상태를 모르면 일시정지는 열림), 「가상 송신기로 독립 검증」. 가상 송신기에서 일시정지를 누르면 요청은 만들어지지만 송신기가 `commands/next`로 가져가지 않으므로 `command_ttl_s`(5초) 뒤 `expired`(「정지 요청 실패: 로봇에 제때 전달되지 않아 실행 안 함」)로 끝나며, 실제 제어는 검증할 수 없음을 구분해 적음

**확인**
- 문서 내용을 `ui/src/control.ts`·`control.test.ts`·`server/state.py`(명령 `expired` 마감과 알림 문구)와 대조. 실제 화면에서 눌러 보지는 않음

## 2026-10-19 (37) dashboard·relay_prog README를 관제 기능(텔레메트리 v2·정지/재개·지도)에 맞게 갱신

**할 일**
- Bridge를 실행하거나 시험할 때 source 순서는 **Jazzy → `limbo/install/setup.bash` → `relay_prog/install/setup.bash`**. `limbo/`를 빠뜨리면 `ModuleNotFoundError: No module named 'limbo_interfaces'`
- UI 시험·빌드는 Node.js 22 또는 24. Node 18에서는 `pnpm test`가 `crypto is not defined`로 실패

**변경**
- 코드 변경 없음. `dashboard/README.md`는 처음 추가(2026-10-06) 뒤 한 번도 고치지 않아 (24)~(29)·(32)의 관제 기능이 빠져 있었음
- `dashboard/README.md`: 버튼 3개 항상 비활성 → 일시정지·순찰 재개 2개를 실제 제어로. 화면 구성(상태 한 줄 요약·순찰·지도·센서 수신 상세), 설정 `command_ttl_s`·`command_response_timeout_s`·`command_confirm_timeout_s`·`map_yaml`·`waypoints_yaml`, 상태 해석(순찰 카드·지도·버튼 잠금·명령 결과 단계), 명령 API 4개·지도 API 2개·스냅샷 새 필드. Bridge 실행·`validate_bridge.py` 명령에 `source limbo/install/setup.bash` 추가(없으면 Bridge가 안 뜸). 가상 송신기·`validate_bridge.py`는 v1 기준이라 순찰·위치·제어를 검증하지 않음을 적음
- `relay_prog/README.md`: v2·명령 구현과 `limbo_interfaces` 의존을 소개에. "0. 먼저: `limbo/` 빌드", source 순서, 추가 ROS 패키지(`geometry_msgs`·`std_srvs`·`tf2_ros`), `control` 설정 표, Mock 서버로 명령 넣기, 자주 나는 오류 표

**확인**
- 문서 내용을 코드(`dashboard/server`, `dashboard/ui/src`, `bridge.yaml`)와 대조
- 서버 시험 `dashboard/.venv/bin/python -m pytest -q` 58개 통과. UI 단위 시험 `pnpm test`는 Node 24.22.0에서 25개 통과

## 2026-10-19 (36) README: pull 뒤 재빌드·다른 브랜치 빌드 흔적 지우기 안내

**할 일**
- `git pull` 뒤 `build_limbo`. `package '…' not found`가 나면 README "2. 빌드"의 지우기 명령

**변경**
- README "2. 빌드"에 pull 뒤 매번 재빌드해야 하는 이유와, 다른 브랜치 빌드 흔적(없는 패키지) 지우는 명령 추가. "막히면"에 내 코드가 최신인지 확인하는 방법 추가
- 코드 변경 없음. dev에 (33)~(35)가 들어 있는데도 "안 고쳐졌다"는 보고가 있어, 옛 설치본으로 돌았을 가능성이 커서 적음

**확인**
- 이 PC에서 같은 증상 재현: 다른 브랜치에서 빌드한 패키지 흔적이 남아 `package 'limbo_drive' not found`로 launch가 멈췄고, 흔적을 지우고 재빌드하니 정상. 네모 월드 순찰·학원 2층 순찰 2회 완주, 사람·로봇 위치 급변 없음

## 2026-10-16 (35) 라이다로 "앞에 선 사람"을 잡고, 벽을 사람으로 오해해 60 s 서 있던 문제를 고침

**할 일**
- `colcon build --symlink-install --packages-select limbo_perception`
- 단위 시험: `colcon test --packages-select limbo_perception && colcon test-result --verbose` (test_tof.py 25개)

**변경**
- `tof.py`·`tof_node.py`: 라이다 `/scan` 점에서 **정적 지도의 벽**(`/map` 점유 칸에서 해상도 2칸 안)을 걸러 내고, 남은 점을 이웃 간격 0.15 m로 묶어 **사람 몸통 폭(0.15~0.6 m)** 덩어리만 "앞에 선 사람"으로 본다(`person_blob_ahead`). 전에는 띠 안에 점 2개만 있으면 사람으로 봐서 복도 벽 모서리에 60 s까지 섰다. 띠 반폭은 하드코딩 0.55 대신 `robot_half_width`(0.30, 바퀴 바깥면) + `person_radius`(0.25)
- `/person_blocking`(코앞 막힘) 확장: ToF 막힘 + (직전 5 s 다가옴 이력 **또는** 앞 사람 덩어리) → 참. 옆·뒤에서 와서 앞에 선 사람, 느린 사람, 카메라 밖에서 멈춘 사람도 잡는다. 덩어리만 근거이고 카메라가 그 자리(1 m 안) 사람을 못 봤으면 **5 s**(`blob_only_hold_sec`)만 기다리고 풀어 상자 앞 무한 대기를 막는다
- `/person_approaching`(다가옴) 풀기: 정지 뒤 유지 근거가 라이다 덩어리뿐이면 **15 s**(`approach_blob_only_hold_sec`), 카메라·ToF가 다시 보면 60 s. 유지 근거(seen/tof/blob)와 풀린 이유를 INFO 로그 한 줄로 남긴다
- `tof.yaml`: 새 파라미터와 근거 주석. `front_sector_*`는 `blob_*`·`robot_half_width`·`person_radius`로 대체. map TF가 없으면(위치 추정 전) 걸러내기 없이 종전처럼 동작
- `package.xml`: nav_msgs 의존 추가

**확인**
- 옆에서 와서 앞에 서는 사람(새 시나리오) 3회 모두 3/3: 다가옴 래치는 안 켜지고 덩어리로 코앞 막힘을 잡아 회전·후진 없이 기다렸다가 사람이 비키면 출발, 충돌 0, 사람 최소 0.43~0.53 m
- 손님 4/4(사람 앞 정지 27.5 s, 전과 같음), 낮은 상자 4/4(덩어리 래치 안 걸림), 사람 두 명 복도 2회 3/3·3/3(다가옴 최대 유지 4.8·5.5 s, 60 s 정지 없음)
- 복도 2회는 1/3: 시험 사람의 왕복 반환점이 로봇 출발 자리 0.61 m 앞이라 사람이 ToF 0.32 m에 60 s 내내 서 있던 경우. 설계대로 기다린 것이며 시험 시나리오 쪽 문제. "앞에서 계속 서 있는 사람"은 비켜서기(다음 작업)의 몫
- 남은 관찰: 시뮬이 뜨는 동안(TF 준비 전) ToF 0.04 m·로봇 앞면 크기 덩어리로 래치가 몇 번 켜졌다 꺼짐. 주행 영향 없음, KNOWN_ISSUES에 기록

## 2026-10-16 (34) 복구 전에 사람 여부를 먼저 물어 사람 앞에서는 회전·후진하지 않음

**할 일**
- `colcon build --symlink-install --packages-select limbo_navigation` (BT xml)

**변경**
- `limbo_navigate_to_pose_w_replanning_and_recovery.xml`: 복구 묶음(costmap 지우기 → 회전 1.57 rad → 5 s 대기 → 0.3 m 후진) 앞에 가지 하나 추가. `/person_approaching`(진로 위로 다가오는 사람)이나 `/person_blocking`(사람 때문에 코앞 막힘)이 참이면 복구 대신 1 s 기다리고 본 가지로 돌아가 "사람이면 기다리기"로 다시 들어간다. 복구 도중 사람이 다가오거나 코앞이 막히면 회전·후진을 멈추기 위한 것. 두 조건이 거짓이면 전과 똑같이 복구한다
- 이 가지는 기다리기 래치(`tof_node`)가 알아본 사람에만 듣는다. 래치가 못 알아본 사람(옆에서 와서 앞에 선 사람 등) 앞에서는 여전히 복구가 돈다. 그 부분은 다음 작업(라이다로 "앞에 선 사람" 잡기)에서 다룬다

**확인**
- 사람 두 명이 왕복하는 복도 3회 3/3·3/3·3/3(사람 최소 0.62~0.67 m, 충돌 0), 낮은 상자 4/4(최소 0.14 m, 접촉 0). 사람이 없을 때의 진전 실패 4회(복도 1회차, 사람 2.45 m 밖)는 새 조건이 거짓으로 찍히고 기존 복구(costmap 지우기 → 회전)로 넘어가 78.8 s에 도착
- 복도 1회차 출발 직후 정체는 알려진 문제(옆으로 스치는 코너의 30 cm 상자)의 재발이며 이 변경과 무관(KNOWN_ISSUES에 추가 기록)

## 2026-10-15 (33) 하드웨어 최종 치수(라이다 0.70 m·카메라 0.60 m), default_server_timeout 100, 충장로 맛보기

**할 일**
- `colcon build --symlink-install --packages-select limbo_description limbo_bringup limbo_navigation` (URDF·launch·nav2 설정), 또는 `build_limbo`
- 실물 카메라 마운트를 바닥 0.60 m·수평으로, MID-360을 바닥 0.70 m로 맞춘다 (URDF와 같아야 인식 좌표가 맞음)

**변경**
- **로봇 치수** (`limbo.urdf.xacro`): 몸체 윗면 `body_top` 0.835 → 0.609로 뚜껑 위 MID-360이 바닥 0.70 m(0.609 + 0.09094, 전 0.926 m). 카메라 `camera_z` 기본값 0.70 → 0.60(수평 0° 그대로). 몸체 시각 메시는 높이 0.835 m로 그려져 있어 z 배율 `body_top / 0.835`로 줄임 — 메시가 높은 채면 Gazebo 라이다가 자기 몸체를 봐 출발 자리에서 못 움직임(`docs/TROUBLESHOOTING.md` "몸체를 낮추자…"). 전체 높이 약 0.72 m
- `start_simulation.launch.py`·`gazebo.launch.py`: `camera_z` 기본값 0.60
- `nav2_params.yaml`: `bt_navigator`의 `default_server_timeout` 20 → 100 ms. 시작 직후 부하에서 계획·추종 서버 응답을 놓쳐 목표를 바로 포기하던 것(손님 장면 0/4). 주행 동작은 그대로, 서버 응답 대기만 여유
- **충장로 맛보기**: `limbo_simulation/tools/chungjang/gen_street.py`와 입력 자료 `osm_chungjang.json`(© OpenStreetMap contributors, ODbL 1.0). 충장로 보행자 거리 200 m 구간 월드 `chungjang`·지도 `chungjang_map`을 만든다. 산출물은 커서 저장소에 넣지 않음(`.gitignore`)
- 순찰 노드의 TF 출발(`/amcl_pose` 없이 `map → base_footprint` TF로 판단)은 (32)에 이미 들어 있어 그대로
- README "충장로 맛보기" 절 추가. `docs/PROJECT.md` 센서 표(크기 약 0.72 m, MID-360 0.70 m·사각 0.3 m 높이 3.3 m 안·바닥 5.7 m 안, 카메라 0.60 m)·결정 표(최종 치수, NavFn A* 유지)
- `docs/KNOWN_ISSUES.md`: 기다리기 BT "다가옴 정지"가 60 s 상한까지 안 풀리는 경우 간헐(0/3 → 2/2 → 1/3). 기다리기 BT는 켠 채 둠

**확인** (시뮬레이션)
- xacro 전개 base_footprint 기준 높이: MID-360 0.700, 카메라 0.60, ToF 0.10, 뚜껑 0.609. 출발 자리 scan 1.0 m 안 점 0개(자기 몸체 안 봄)
- 최종 치수에서 복도 3/3(25~89 s, 사람 충돌 0, 사람 최소 0.70 m), 상자 4/4(31~36 s, 장애물 최소 0.18 m, 충돌 0)
- `default_server_timeout` 100에서 손님 4/4(17~28 s, 사람 최소 0.56 m), 순찰 3/3(320·258·211 s)
- 계획기: NavFn A* 1.0~2.4 ms vs 다익스트라 1.8~5.8 ms(10회×4목표, 성공 80/80) → A* 유지

## 2026-10-14 (32) 저녁 채택분 반영: 사람이면 기다리기 BT, ToF costmap, 카메라 0°, MPPI 되돌이 처리, 순찰 반복·TF 출발, 관제 일시정지

**할 일**
- pull 후 `colcon build --packages-select limbo_navigation limbo_perception limbo_description limbo_patrol limbo_evaluation` (BT 조건 플러그인·ToF 노드·URDF·순찰)
- 학원 2층 순찰을 한 번 돌려 A 지점 맴돎이 사라졌는지 확인

**변경**
- **사람이면 기다리기 BT 켬** (`nav2_params.yaml`의 `limbo_navigate_*_w_replanning_and_recovery.xml`): 진로 폭 띠(범퍼 앞 0~1.5 m, 좌우 0.55 m)에 다가오는 사람이면 정지·기다림, 코앞을 막은 사람(ToF 0.5 m)은 카메라 기억 래치로 유지, 떠나거나 1 s 비면 재개(상한 60 s). 경로 계획 실패도 사람 때문이면 기다림. 조건 노드 `IsPersonBlocking`(`limbo_navigation`), 판단 노드 `tof_node`(`limbo_perception`, `/tof/points` → `/tof/obstacle_ahead`·`/person_blocking`·`/person_approaching`)
- **ToF 근접 센서**: URDF `tof_link`(범퍼 앞 0.25 m, 높이 0.10 m, 수평), 시뮬레이션 8×8 63° 4 m(`limbo.gazebo.xacro`, `bridge.yaml`). 점군을 local costmap STVL `tof_mark` 관측원으로도 넣음(0° 카메라가 0.78 m 안에서 놓치는 30 cm 상자, 상자 벤치 12/12·접촉 0)
- **카메라 0.7 m·0°**(전 15°): 기울이면 비스듬히 다가오는 손님의 상체가 잘려 검출 19 % → 3 %. launch 인자 `camera_z`·`camera_pitch_deg`
- **MPPI `enforce_path_inversion: true`**: 순찰 통과 지점에서 경로가 되돌아 꺾일 때 `prune_distance` 2.5가 그 앞 1.2 m 정체를 만들던 문제(A 지점 맴돎) 해결
- 순찰 노드: `loop` 파라미터(끝없이 반복, `aischool_loop_waypoints.yaml`), 이동 실패 시 2번 재시도 뒤 paused로 사람의 재개 대기, `/amcl_pose` 없이 TF만으로 출발. 관제 화면 일시정지·재개(`dashboard`, `docs/CONTROL_SCREEN.md`)
- `nav_recorder`: 순찰(`navigate_through_poses`) 지원, 벽 거리·사람 접근 속도·위치 추정 오차 열
- `start_simulation.launch.py`: `localization:=amcl|slam|mapping` 인자(slam_toolbox 비교용, 기본 amcl), ToF 노드

**확인**
- 비켜 주는 사람 복도 3회 9/9(사람 앞 기다림 4~5 s, 60 s 정지 0), 손님 4/4, 상자 4/4. 사람 10명 네모 순찰 AMCL 3묶음 완주 145.7 s(위치 오차 0.035 m)
- 열린 문제: ToF 시야 밖 코너의 30 cm 상자 정체 13회 중 1회, 복도 목표 코앞 정체 5회 중 1회 (`docs/KNOWN_ISSUES.md`)

## 2026-10-14 (31) 시뮬레이션에서 채택된 설정·코드 반영: 전역 STVL 3초, HumanLayer 치명 비용, prune_distance 2.5, 카메라 0.7 m 15°, nav_recorder 지표

**할 일**
- pull 후 `build_limbo` (HumanLayer C++). 실물 카메라 마운트를 0.70 m·아래 15°로 맞추고 피치를 실측해 URDF와 같게

**변경**
- `nav2_params.yaml`: 전역 costmap STVL `voxel_decay` 15 → 3초(3초·15초 성적 같음, 작은 값), MPPI `prune_distance` 1.7 → 2.5(1.7이면 4 s 예측 × 0.425 m/s가 사실상 속도 상한. 충장로 직선 0.42 → 0.58 m/s, 사람 있는 복도·홀에서 충돌 0·사람 거리 동일에 시간 −22~31 %), `human_layer` 파라미터 9개
- `human_layer.cpp/.hpp` 다시 씀: 사람 현재 위치와 0.5 s 안 예측점은 몸 반경 0.25 m 안을 치명(254)으로. 전에는 현재 위치를 안 칠하고 최고 비용 220이라 MPPI 충돌 판정에 안 걸려 사람을 뚫는 궤적을 골랐음. 상수는 yaml로, 2초마다 찍던 INFO 로그는 DEBUG로
- `limbo.urdf.xacro`·`gazebo.launch.py`·`start_simulation.launch.py`: 카메라 0.50 m 수평 → 0.70 m 아래 15°(짧은 치마 밑단보다 높게 두어 올려다보지 않음, 근거리 바닥 0.78 m부터. 12·15·18° 비교에서 사람 검출·상자 costmap 전과 같음). `camera_z`·`camera_pitch_deg` 인자
- `nav_recorder`: 순찰(`navigate_through_poses`)도 기록(`action` 열), 사람 충돌(0.3 m 미만)·사람 앞/그 외 멈춤·전역 경로 변경·최소 거리 순간의 사람 접근 속도와 로봇 속도 열. 테스트 23개
- `tools/demo_patrol.sh`: Nav2 준비 검사 `grep -q active`가 `inactive`에도 맞던 것을 `^active`로
- `README.md`(따라 하면 무엇이 뜨는지 흐름으로 다시 씀, CSV 열 표), `docs/PROJECT.md`(에이전트용 안내서: 설계 전제·기록 규칙·결정 이력·지금 상태), `docs/KNOWN_ISSUES.md`(맨 위 "지금 주행을 막는 것"), `docs/TROUBLESHOOTING.md`(10-13·14 항목 추가)

**확인**
- ktj에서 `colcon build` 10개 패키지, `limbo_evaluation` pytest 23개 통과, xacro 카메라 joint (0.235, 0.1575, 0.70) pitch 0.262 rad
- 학원 2층 순찰 1회 완주 (`tools/demo_patrol.sh`)

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
