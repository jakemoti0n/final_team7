# 서브 PC 지시서: ToF 근접 센서 + "사람이면 기다리기" 입력 바꾸기 (R5, 2026-10-14)

## 배경
R4 결과: 카메라(전신 YOLO)가 1.5 m 안 사람을 거의 못 잡아(노트북 측정도 0 %, `experiments/2026-10-14_camera_angle/`) `IsPersonAhead`가 참이 안 됐다. Q1의 답은 **(다) + ToF**다.
실물에는 저가 ToF(VL53L5CX, 8×8 구역, 시야 63°, 4 m)를 **범퍼 높이 10 cm 전면 중앙에 수평**으로 하나 달아 젯슨 오린 나노 I2C에 직결하기로 했다(사용자 결정 10-14). 용도는 "코앞에 뭔가 있다"뿐이고 사람·상자 구분은 카메라 기억이 한다.
- 하지 말 것: 카메라 추적 유지 시간을 늘려 맞추기(사라진 사람이 HumanLayer에도 남음), `max_age`·timeout 숫자로 때우기, LiDAR 다리 인식(사람·상자 구분 못 함)

## 1. ToF 센서 (시뮬레이션 + 노드 인터페이스)
- URDF(`limbo.urdf.xacro` + `limbo.gazebo.xacro`): 전면 중앙 (x 본체 앞면, y 0, z 0.10), 수평. gz `gpu_lidar`로 **8줄 × 8칸, 수평·수직 시야 각 63°, 0.02~4 m, 10 Hz**. 토픽 `/tof/points`(PointCloud2)로 브리지(`bridge.yaml`)
- 노드 `tof_node`(파이썬, `limbo_perception` 또는 새 패키지 `limbo_tof` — 작게): 입력 `/tof/points`, 출력
  - `/tof/obstacle_ahead` (`std_msgs/Bool`): 8열 중 어느 열이든 최소 거리 < `stop_distance`(yaml, 0.30 m)면 참. **연속 `confirm_frames`(3) 프레임**이어야 참·거짓이 바뀜(실물 햇빛 튐 대비)
  - `/tof/nearest` (`geometry_msgs/PointStamped`, base_link): 가장 가까운 점
  - 실물 I2C 드라이버는 나중(인터페이스만 같게). 노드는 "점구름 → Bool" 계산을 `rclpy` 없는 파일에 두고 pytest
- 전제 2-3·2-5 그대로. 바닥 반사 오탐은 `min_obstacle_height`(0.03 m)로 거른다

## 2. `IsPersonAhead` 입력 바꾸기
조건 = **(A) 최근 `memory_sec`(5 s) 안에 카메라가 앞쪽 `x` 0.8~3.0 m, `|y|` < 1.0 m에서 사람을 봤고 그 사람이 다가오고 있었음**(속도의 x 성분 < 0, 또는 `/person_detector/approach_intent` 참) **AND (B) 지금 `/tof/obstacle_ahead`가 참**.
- (A)만 있으면 사람이 옆으로 빠진 뒤 상자 앞에서 기다릴 수 있고, (B)만 있으면 상자 앞에서 기다린다. 둘 다여야 "방금 다가오던 사람이 지금 코앞에 있다"가 된다
- 포트: `memory_sec`, `min_distance`, `max_distance`, `half_width`, `tof_topic`. 기억은 노드 안 변수(마지막으로 본 시각·위치)로, 토픽 유지 시간은 안 건드림
- 기다림 상한은 R4 그대로(RecoveryNode 재시도 6 × (10 s + 5 s))
- 켜기: R4 README "켜는 법" 세 줄을 `nav2_params.yaml`에 넣는다. **이번에는 켠 채로 커밋**(시험이 통과하면)

## 준비
```bash
cd ~/limbo && git pull --rebase origin lab && git rev-parse --short HEAD
build_limbo      # URDF·C++·bridge
export ROS_DOMAIN_ID=98 GZ_PARTITION=desk
```
- lab에는 HumanLayer 치명 비용(63)이 들어가 있어 한 명 복도에서도 "진전 없음" 복구가 난다(64: 2구간에서 2번). R4 때와 달리 분기가 발동할 것

## 시험 (바꾸기 전 1회는 R4 `before`·노트북 64 결과로 대신, 바꾼 뒤 2회)
```bash
experiments/orders/people_one.sh tof1
experiments/orders/people_one.sh tof2
```
- ToF 단독 확인: 상자 월드(`experiments/2026-10-14_camera_angle/worlds/zz_cam_box.sdf`, 로봇 정지)에서 `/tof/obstacle_ahead`가 0.5 m 30 cm 상자에 참이 되는지(앞면 0.5 m라 `stop_distance` 0.3이면 거짓이 맞음 — 상자를 0.25 m로 옮긴 사본으로 참 확인)
- 어떤 복구가 돌았는지: `grep -E "behavior_server\]: (Running|Attempting)|WaitForPerson|IsPersonAhead" ~/limbo_bags/sim_trials/logs/sim_<라벨>_single.log`

## 받아들이는 기준
| 경로 | 기대 | 깨지면 |
|---|---|---|
| 한 명 복도 | "진전 없음" 뒤 **기다림**이 돌고 회전·후진 0, `person_collision` 0, 시간 64 결과(32·34 s) +10 s 안 | 기다림이 한 번도 안 돌면 (A)·(B) 어느 쪽이 거짓인지 로그로 가른다 |
| 상자 구간 | 4/4, 닿음 0, **상자 앞 기다림 0**, `stopped_other_s`가 64 결과(0.7~2.6 s)보다 10 s 넘게 늘지 않음 | 상자 앞에서 기다리면 (A) 기억이 남은 것 → `memory_sec`·접근 판정 확인 |

## 결과 남기기
- `experiments/2026-10-14_tof_wait_sub/README.md` + CSV, `docs/lab/reports.md` R5, 변경 기록(번호 = pull 뒤 맨 위 + 1). 코드 커밋은 "왜" 한 줄. `git pull --rebase origin lab && git push origin lab`, **dev/ktj 금지**
- 실물 ToF 드라이버는 하지 않는다(하드웨어가 오면 노트북이). 인터페이스(토픽·메시지·yaml 이름)는 README에 적어 둔다
