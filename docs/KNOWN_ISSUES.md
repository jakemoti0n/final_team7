# 알려진 문제

시뮬레이션과 코드 점검 중에 발견했지만 아직 고치지 않은 문제를 모은다.
고치면 이 표에서 지우고 커밋 메시지에 남긴다.

마지막 갱신: 2026-10-06 (왼쪽 복도 AMCL 점프 해결 → TROUBLESHOOTING으로 이동)

## 주행·위치 추정

| 문제 | 근거 | 영향 | 대책 후보 |
|---|---|---|---|
| 로봇이 위쪽 복도에서 30초간 붙잡힘 (원인 미확정) | `aischool_2f` (−4.14, 8.38)에서 바퀴는 도는데 정지(2026-10-02). 근처 정적 벽 없음(코어 벽까지 0.52m). **걷는 사람은 원인이 아님**(사람 모델은 충돌이 없어 로봇을 통과함, 2026-10-06 확인). 당시 AMCL이 틀어져 있었을 가능성 있음 | 시뮬레이션 테스트가 중간에 멈춤 | beamskip 적용 후 다시 발생하는지 지켜봄 |
| 바퀴 마찰 계수가 낮음 (`mu1`, `mu2` = 0.5) | `limbo_description/urdf/limbo.gazebo.xacro` | 회전·가속 시 바퀴가 미끄러짐. 바퀴 odom 회전 오차 약 10%의 원인으로 추정(EKF로 보정 중) | 실제 바퀴·바닥에 맞는 값으로 조정 |
| 좁은 복도(1.54m)에서 제자리 회전 실패 | `aischool_2f` 왼쪽 복도에서 `behavior_server: Collision Ahead - Exiting Spin`. 로봇이 정사각형(0.45m)이라 돌 때 모서리가 그리는 원(반지름 0.32m)이 벽 inflation에 걸림 | 좁은 곳에서 방향을 돌려야 하는 Goal이 실패 | 복구 동작 순서(후진 먼저), footprint·inflation 조정, 실제 복도 폭 실측 |
| MPPI 컨트롤러가 목표 주기를 못 냄 | `Control loop missed its desired rate of 20.0000 Hz. Current loop rate is 6.4935 Hz` (CPU 부하 평균 14~16/16코어일 때) | 부하가 높을 때 경로 추종이 나빠지고 `Failed to make progress` | 시뮬레이션 CPU 줄이기(YOLO 10Hz, LiDAR 해상도, wheel_slip_monitor), MPPI `batch_size`·`time_steps` 조정 |
| 사람이 많아 LiDAR 시야 대부분이 가려지는 상황 | AMCL beamskip은 안 맞는 빔이 90%를 넘으면 꺼지고 원래 방식으로 계산함 | 혼잡한 곳에서 위치 추정이 다시 불안정해질 수 있음 | 실제 환경에서 확인 |
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
| `person_detector`의 남는 실행기 스레드가 YOLO가 도는 동안 헛돎 (약 20%p) | `person_detector.py` `main()`의 `MultiThreadedExecutor`. 콜백이 한 그룹이라 동시에 못 도는데 다른 스레드가 "실행할 게 있나"를 계속 확인함 | 그냥 싱글스레드로 바꾸면 YOLO 동안 TF를 못 받아 위치 조회가 0.1초씩 기다려 처리량이 절반(14→6.7Hz). TF 대기를 0으로 하면 처리량은 돌아오지만 TF 실패가 0→54번으로 늘어 동작이 바뀜. tf2 `spin_thread=True`는 오히려 CPU 173%. TF만 따로 받는 구조가 필요 |
| MID-360 LiDAR가 설정은 10Hz인데 실제 약 5Hz | `limbo.gazebo.xacro` `update_rate`, 측정: `/mid360/points` 5.4Hz | AMCL·costmap 업데이트가 드묾. 시뮬레이션 부하 때문일 수 있음 |
| 모델 경로가 상대경로 (`yolo11n.pt`) | `person_detector.yaml`의 `yolo.model` | 실행 위치에 따라 모델을 새로 내려받음 |
