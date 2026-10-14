# R6 비켜서 기다리기 (2026-10-14, 서브 PC) — 기준 미달, 트리에 안 넣음

## 왜 했나
복도 가운데로 정면에서 오는 안 비켜 주는 사람(no_yield) 앞에서 로봇이 가운데 멈춰 뚫린다. 전제 2-1·2-2대로 다가오는 사람이면 먼저 길을 비울 자리로 비켜선 뒤 기다린다. 요청 R6, 순서는 메인 PC 정리(e462868)·설계(`docs/lab/reports.md` R6 설계, Q12 답).

## 만든 것
- **`ComputePullOverPose`** (C++ BT 동기 액션, `limbo_navigation/src/compute_pull_over_pose_action.cpp`, 라이브러리 `limbo_compute_pull_over_pose_bt_node`): `/local_costmap/costmap_raw`로 로봇 옆 0.5·0.4·0.3 m, 앞 0.3 m 자리를 판정. 받아들이는 자리 = 중심 칸이 inscribed 미만 + 외곽 안 치명 칸 없음 + 중심에서 치명 칸까지 반폭 0.295 + 0.1 m 이상. 양쪽 다 되면 사람 반대쪽(모르면 오른쪽). `/person_approaching`이 참인 동안 한 번만(3 s 넘게 안 불리면 새 사람으로 봄)
- 정함: 설계의 "외곽 안 칸이 모두 inscribed 미만"은 1.8 m 복도에서 어느 자리도 통과 못 해서, Nav2가 실제로 충돌로 보는 기준(중심 inscribed 미만·외곽 치명 없음)으로 바꿈
- 정함: 비켜서는 이동(`ComputePathToPose`→`Timeout 8 s`→`FollowPath`)은 `ForceSuccess`로 감싸고 오류 코드를 따로 씀. 처음엔 이동이 8 s를 넘기면 목표 전체가 실패했다(smoke 3구간 ABORTED)
- 트리 자리(시험한 것): R5 `WaitForPerson` Fallback 맨 앞
```xml
<Sequence name="PullOverOnce">
  <IsPersonApproaching name="ApproachingSoPullOver" topic="/person_approaching"/>
  <ComputePullOverPose pose="{pull_over_pose}" side_offsets="0.5;0.4;0.3" forward="0.3"/>
  <ForceSuccess><Sequence>
    <ComputePathToPose goal="{pull_over_pose}" path="{pull_over_path}" planner_id="{selected_planner}" error_code_id="{pull_over_error_code}"/>
    <Timeout msec="8000"><FollowPath path="{pull_over_path}" controller_id="{selected_controller}" error_code_id="{pull_over_error_code}"/></Timeout>
  </Sequence></ForceSuccess>
</Sequence>
```
(`plugin_lib_names`에 `limbo_compute_pull_over_pose_bt_node` 추가 필요)

## 조건
- 커밋 `01d57c4` + 위 변경(작업 폴더), R5 기다리기 트리 켬, 카메라 0.7 m·0°, ToF costmap, 서브 PC
- `run.sh`: no_yield 복도(`zz_social_noyield` `people2`) 3회, 비켜 주는 사람 복도(`aischool_2f_social` `people2`) 3회, 손님 `hall` 1회, 상자 1회. 회차마다 녹화

## 결과

| 시험 | 결과 | 비켜서기 | 사람 최소 | 충돌 |
|---|---|---|---|---|
| no_yield 복도 1 | 3/3, 복도 41.3·34.6 s | 3 | 0.15·0.28 m | **2** |
| no_yield 복도 2 | 3/3, 복도 43.7·91.7 s | 3(자리 없음 1) | 0.10·0.23 m | **2** |
| no_yield 복도 3 | 3/3, 복도 37.9·41.1 s | 4(자리 없음 1) | 0.09·0.09 m | **2** |
| 비켜 주는 사람 복도 1 | 3/3, 복도 36.2·**67.6** s | 8 | 0.65 m | 0 |
| 비켜 주는 사람 복도 2 | 3/3, 복도 **86.0**·25.8 s | 2 | 0.69 m | 0 |
| 비켜 주는 사람 복도 3 | 3/3, 복도 28.5·32.8 s | 2 | 0.64 m | 0 |
| 손님 `hall` | 4/4 | 2 | 0.69 m | 0 |
| 상자 | 4/4, 닿음 0, 상자 최소 0.27 m | 0 | — | 0 |

모두 회전·후진 0.

### no_yield 충돌: 비켜서기가 늦다 (`closest_moments.py`)
6구간 모두 같은 모양: "다가옴"이 처음 참이 된 것이 사람이 **1.5~1.7 m 앞**(부딪히기 2 s 전)일 때, 로봇은 그 자리에서 서고(속도 0), 0.7 m/s 사람이 멈춘 로봇으로 걸어 들어옴. 최근접 순간 로봇 옆 위치가 사람 줄과 같다(비켜서기 전). 비켜서기 자체는 대부분 사람이 지나간 뒤에 실행됐다.
- 0.7 m/s 사람을 비켜서려면 비켜서는 이동(약 1.5 s)과 여유를 더해 **3 m 앞**에서 알아야 하는데, 이 장면의 사람을 카메라가 3~4 m에서 거의 못 잡는다(오늘 손님 장면 검출 19 %, `experiments/2026-10-14_camera_pitch_sub/`와 같은 문제)
- 비켜 주는 사람 복도는 R5만 켰을 때 3/3(`experiments/2026-10-14_tof_wait_sub/` 최종)이었는데 비켜서기를 넣자 1/3. 사람이 이미 돌아가는 중에 로봇이 옆으로 움직여 길이 다시 막힌 것으로 보임

## 결론
- 비켜서기 노드·자리 판정은 동작한다(자리를 고르고 비켜섬, 상자 앞에서는 안 함)
- **기준 미달**: no_yield 복도 충돌 6/6(사람이 멈춘 로봇에 걸어 들어옴), 비켜 주는 사람 복도 회귀(3/3 → 1/3)
- 원인은 판단 시점: 카메라가 다가오는 사람을 1.5 m 근처에서야 잡아서 비켜설 시간이 없다
- **정함**: 트리에는 넣지 않는다(R5 통과 상태 유지). 노드 코드는 남김

## 다음
- 다가오는 사람을 3 m 이상에서 알아야 R6이 성립한다. 카메라 검출(이 장면 actor 렌더·YOLO 문턱) 또는 다른 입력이 먼저 필요. no_yield가 멈춘 로봇을 뚫는 것은 사람 탓 충돌로도 볼 수 있음(최근접 순간 로봇 속도 0, 전제 2-5)

## 2차: 검출 조사와 판단 거리 4 m (같은 날 21:00~21:41) — 기준 미달, 되돌림
사용자가 "검출 먼저 조사"를 골라서 원인부터 봄.

### 검출 조사 (`det_probe.py`, `det_probe_noyield.csv`)
no_yield 복도 1회 동안 정답상 사람이 카메라 앞 1~5 m·시야 안이면 같은 프레임에 YOLO(`yolo11n.pt`, 문턱 0.05)를 돌림.

| 거리 | YOLO ≥ 0.3 | 파이프라인 예측에 그 사람 |
|---|---|---|
| 2~3 m | 8/8 | 6/8 |
| 3~4 m | 6/11 | 5/11 |
| 4~5 m | 25/30 | 22/30 |

3~4 m에서 놓친 프레임은 사람이 모퉁이 벽에 가린 장면(정답 시야각 안이지만 벽 뒤). 가려지지 않으면 3~5 m에서도 잡힌다. **1차에서 "카메라가 1.5 m에서야 잡는다"고 본 것은 틀린 진단**

### 진짜 원인: 판단 거리 상한 (`approach_trace.py`)
예측·정답 녹화로 조우를 따라가면 사람이 3.85 m에서 이미 예측에 잡히고 속도 0.67 m/s·직선 최근접 0.07 m로 정확한데, `/person_approaching`은 2.6 m에서야 참. `tof.yaml approach_max_range` 3.0 때문(메인 PC 정리 e462868은 1.5~4 m). 4.0으로 바꿔 비켜서기를 다시 넣고 같은 시험(라벨 r6b_)

| 시험 | 결과 |
|---|---|
| no_yield 복도 3회 | 6구간 모두 충돌(0.04~0.21 m) |
| 비켜 주는 사람 복도 3회 | +15 s 안 1/3(85.5·81.8 s 구간) |
| 손님 | 4/4·충돌 0 |
| 상자 | 4/4·닿음 0, 한 구간 **94.7 s**(60 s 정지) |

- 이번엔 다가옴이 사람 3 m 앞(부딪히기 4 s 전)에 켜졌고 비켜설 자리도 1 s 뒤 골랐다(첫 tick은 costmap을 아직 못 받아 실패 → Wait 1 s 뒤 계산)
- 그런데 **로봇이 옆으로 안 움직였다**(y 9.98~10.00 그대로, 앞으로 0.2 m). 앞 0.3·옆 0.4 m 짧은 대각 경로를 MPPI가 못 따라가 `Optimizer fail to compute path` 반복. 차동 구동이라 짧은 옆 이동은 돌고·가고·도는 동작인데 경로 추종으로는 안 됨
- 판단 거리 4 m는 R5(그 자리 정지)에도 걸려 더 멀리서부터 서게 해 복도·상자 시간이 나빠짐

### 정함
- 판단 거리 3 m·비켜서기 없는 R5 통과 상태로 되돌림(커밋에는 안 넣음)
- 다음 시도: 경로 추종 대신 Nav2 기본 동작 `Spin`(약 45°) → `DriveOnHeading`(약 0.6 m)으로 옆 0.4 m 비키기(후진 없음, 전제 2-3). 판단 거리 4 m는 비켜서기 판단에만 쓰고 R5 정지는 3 m 그대로 두도록 둘을 나눔
