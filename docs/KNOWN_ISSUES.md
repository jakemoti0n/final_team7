# 알려진 문제

시뮬레이션과 코드 점검 중에 발견했지만 아직 고치지 않은 문제를 모은다.
고치면 이 표에서 지우고 커밋 메시지에 남긴다.

마지막 갱신: 2026-10-02

## 주행·위치 추정

| 문제 | 근거 | 영향 | 대책 후보 |
|---|---|---|---|
| 바퀴가 헛돌면 odom이 계속 전진한다고 보고해서 AMCL이 위치를 놓칠 수 있음 | `aischool_2f` 월드에서 로봇이 실제로는 30초간 멈춰 있는데 odom은 0.40m/s 전진. 첫 주행에서 AMCL 위치가 실제와 3.6m, 60° 어긋나 Goal 실패 | 실제 로봇도 문턱·카펫·충돌에서 같은 일이 생길 수 있음. 틀린 위치로 계속 주행하면 위험 | MID-360 내장 IMU를 `robot_localization`(EKF)로 odom과 융합 / AMCL 불확실성이 커지면 주행 정지 |
| 로봇이 걷는 사람 경로 위에서 붙잡힘 (원인 미확정) | `aischool_2f` (−4.14, 8.38)에서 정지. 근처 정적 벽 없음(코어 벽까지 0.52m). person_2 경로(y 8.60) 위 | 시뮬레이션 테스트가 중간에 멈춤 | 사람 경로에 로봇을 세워 두고 재현해서 원인 확인 |
| 회전할 때 odom 방향 오차 약 8% | `human_test_world`에서 실제 67.6° 회전에 odom 73.1° | 방향이 틀어지면 대칭 구조(복도·교실)에서 반대편으로 착각하기 쉬움 | IMU 융합 / AMCL `alpha1`, `alpha2` 조정 |
| 시작 직후 `collision_monitor` 응답 끊김 → Nav2 전체 재시작 (약 5초) | `CRITICAL FAILURE: SERVER collision_monitor IS DOWN after not receiving a heartbeat for 4000 ms` | 그 사이 보낸 Goal은 거절됨 | 시작 순서·CPU 부하 확인, bond timeout 조정 |

## 시뮬레이션·월드

| 문제 | 근거 | 영향 | 대책 후보 |
|---|---|---|---|
| `human_test_world`는 정사각형 방이라 스캔만으로 방향 구분이 안 됨 | (0,0)에서 0°/90°/−90°/180° 모두 스캔 일치 94~95% | Pose Estimate를 손으로 찍으면 크게 틀리기 쉬움 (실제로 두 번 다 틀림: 일치 9%, 4%) | 초기 위치는 `amcl.yaml` 값 사용 (적용 완료) |
| `aischool_2f`는 피난안내도 사진 기반 근사 | 축척은 교실 깊이 실측(약 6.1m, 보폭 기준)과 복도 폭(약 1.5m)으로 맞춤. 문은 0.9m로 통일 | 벽 위치 오차 수십 cm 가능 | 실측 치수를 더 받으면 `tools/aischool_2f/build_mask.py`에서 보정 |
| 이전에 녹화한 rosbag 두 개는 Pose Estimate가 틀린 상태 | 스캔-지도 일치 9%, 4% | 그 bag으로 Nav2 성능을 비교했다면 결과를 다시 봐야 함. person_detector 비교는 카메라 기준이라 영향 없음 | 새로 녹화 |

## 코드 (리뷰에서 발견, 미수정)

| 문제 | 위치 | 영향 |
|---|---|---|
| YOLO를 카메라 15Hz 매 프레임 콜백 안에서 실행, costmap은 5Hz로만 사용 | `limbo_perception/person_detector.py` `image_callback` | 예측의 약 2/3가 쓰이지 않음. 10Hz 타이머로 줄이면 연산 약 1/3 감소 |
| 주석 이미지를 구독자가 없어도 매 프레임 그림 | 같은 파일 `visualization.draw_detection` 호출부 | 불필요한 CPU |
| 3D LiDAR 720×60 @10Hz (실제 MID-360의 약 2배) | `limbo_description/urdf/limbo.gazebo.xacro` | 브리지·필터·costmap 전체 부하 |
| 아무도 구독하지 않는 `mid360` LaserScan 브리지 | `limbo_simulation/config/bridge.yaml` | 불필요한 변환 |
| 모델 경로가 상대경로 (`yolo11n.pt`) | `person_detector.yaml`의 `yolo.model` | 실행 위치에 따라 모델을 새로 내려받음 |
