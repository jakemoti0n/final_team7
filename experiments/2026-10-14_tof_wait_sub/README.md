# ToF 근접 센서 + "카메라 기억 + ToF" 기다리기 조건 (R5, 2026-10-14, 서브 PC) — 막힘

## 왜 했나
R4에서 카메라가 1 m 안 사람을 거의 못 봐 `IsPersonAhead`가 참이 안 됐다. 실물에 범퍼 높이 ToF(VL53L5CX)를 달기로 하고, 조건을 "(A) 최근 5 s 안에 카메라가 앞 0.8~3 m에서 다가오는 사람을 봤음 AND (B) 지금 ToF 0.3 m 안에 무언가"로 바꿔 시험한다. 요청 R5, 지시서 `experiments/orders/2026-10-14_sub_tof_wait.md`.

## 만든 것
- **ToF 센서(시뮬레이션)**: `limbo.urdf.xacro` `tof_link`(base_link 앞 x 0.25 — 차체 메시 앞면 0.245 바로 앞, y 0, z 0.10, 수평), `limbo.gazebo.xacro` gz `gpu_lidar` 8×8, 가로·세로 각 ±31.5°(대각 63°를 가로·세로로 근사), 0.02~4 m, 10 Hz, `bridge.yaml` `/tof/points`. 이전 로봇(legacy) 모델에는 안 넣음
- **`tof_node`** (`limbo_perception`, 실물 드라이버도 같은 인터페이스를 내면 된다):

  | 토픽 | 형 | 내용 |
  |---|---|---|
  | 입력 `/tof/points` | `sensor_msgs/PointCloud2` | 센서 프레임 점 |
  | `/tof/obstacle_ahead` | `std_msgs/Bool` | 바닥(`min_obstacle_height` 0.03 m) 위 점 중 센서 앞 거리 < `stop_distance` 0.30 m. `confirm_frames` 3번 연속이어야 바뀜 |
  | `/tof/nearest` | `geometry_msgs/PointStamped` | base_link 기준 가장 가까운 점 |

  설정 `limbo_perception/config/tof.yaml`, 계산 `tof.py`(rclpy 없음, `test/test_tof.py` 3개), launch에 추가
- **`IsPersonAhead`** 다시 씀: 포트 `person_topic`, `tof_topic`, `memory_sec` 5, `min_distance` 0.8, `max_distance` 3.0, `half_width` 1.0. 카메라 위치는 큐 100으로 받아 tick 때 순서대로 보고(BT는 막혔을 때만 tick), 1 s 안 연속 두 위치에서 x가 줄면 다가옴. 기억은 노드 변수(마지막으로 본 영상 시각·위치)
- 분기는 이번에도 `nav2_params.yaml`에서 **꺼 둠**(시험 통과 못 함). 켜는 세 줄은 [R4 기록](../2026-10-14_bt_wait_sub/README.md) "켜는 법"

## 조건
- 커밋 `5f05cc3`(HumanLayer 치명 비용(63) 포함) + 위 변경, 서브 PC, `ROS_DOMAIN_ID=98`, `GZ_PARTITION=desk`, v14
- ToF 단독: `zz_cam_box.sdf`(로봇 정지) 원본과 상자 a를 0.25 m 당긴 사본 (`tof_check.sh`)
- `experiments/orders/people_one.sh tof1|tof2`, 그리고 두 명 복도(`aischool_2f_scenarios` 원본 `people2`, 제한 200 s) `tofpair`, 녹화 붙인 `tofdiag`

## 결과

ToF 단독: 상자 앞면이 센서에서 0.485 m → `obstacle_ahead` 거짓(맞음), 0.235 m → 참, `/tof/nearest` x 0.485(base_link, 상자 앞면과 일치). `/tof/points` 10 Hz.

한 명 복도·상자 구간:

| 라벨 | 복도 동쪽 | 복도 서쪽 | 사람 최소·충돌 | 상자 4구간 | 조건 노드 tick |
|---|---|---|---|---|---|
| tof1 | 34.9 s | 37.8 s | **0.25 m(충돌 1)** · 0.42 m | 4/4, 닿음 0, 상자 최소 0.27 m | 0번 |
| tof2 | 31.7 s | 36.9 s | 0.56 · 0.48 m, 충돌 0 | 4/4, 닿음 0, 상자 최소 0.26 m | 0번 |

두 번 모두 한 명 복도에서 바깥 복구(회전·대기·후진)까지 간 적이 없다. 복구 수(1~3)는 내부 costmap 비우기다. 그래서 분기가 한 번도 안 돌았고, 충돌 1(tof1)도 분기와 무관하다. 상자 구간은 성적 그대로이고 상자 앞에서 기다리지 않았다(tick 0).

두 명 복도(분기 발동 확인):

| 라벨 | 복도 동쪽 | 복도 서쪽 | 사람 최소 | 회전 / 대기(분기 포함) / 후진 | 조건 노드 판단 |
|---|---|---|---|---|---|
| tofpair | 성공 62.3 s | 성공 116.8 s | 0.01 m (충돌) | 1 / 1 / 1 | "아님" 전부 |
| tofdiag | 성공 71.9 s | **실패(ABORTED)** 173.3 s | 0.01 m (충돌) | 3 / 3 / 1 | "기다림" 1번, "아님" 24번 |

"아님"일 때 로그(예): `카메라 못 봄: 7.0~33.4 s 전`, `카메라 봄: 3.0 s 전 x=1.05 y=0.12, ToF 비었음`. "기다림" 1번은 `카메라 봄: 1.4 s 전 x=1.66 y=-0.67, ToF 막힘`.

### 왜 거짓인가 (`tofdiag` 녹화, `tof_gap.py`)
정답 위치로 "로봇이 멈춰 있고(0.05 m/s 미만) 앞 1.5 m·폭 0.6 m 안에 사람"인 순간을 1 s 간격으로 뽑아 그때 ToF를 봤다(72순간).

| 사람 중심이 로봇 중심 앞 | 순간 | ToF가 사람 근처를 봄 | `obstacle_ahead` 참 | ToF 최근접 x(base_link) 예 |
|---|---|---|---|---|
| 0 ~ 0.3 m (차체 앞면 0.245 안 = 사람이 로봇과 겹침) | 18 | 3 | 2 | 0.9, 1.0, 1.1 (뒤 벽·다른 것) |
| 0.3 ~ 0.5 m | 8 | 5 | 3 | 0.27, 0.41, 0.53 |
| 0.5 ~ 0.8 m | 20 | 15 | 7 | **0.57, 0.58, 0.64, 0.65** |
| 0.8 ~ 1.5 m | 26 | 24 | 1 | 0.38~1.2 |

## 결론
- **막힘.** 조건 두 개가 구조적으로 같이 참이 되기 어렵다
- **(A) 카메라 기억 5 s가 바깥 복구에 닿기 전에 끝난다.** 로봇이 멈추고 나서 바깥 복구 분기에 오기까지 최소 약 20 s(진전 없음 10 s + 내부 FollowPath 재시도 10 s)가 걸린다. 그 사이 카메라는 1 m 안 사람을 못 본다(R4). 로그의 "못 봄 7~33 s 전"이 이것
- **(B) ToF 0.30 m 안에 사람이 잘 안 들어온다.** HumanLayer 치명 비용(63) 덕분에 로봇이 사람 몸 앞에서 멈추는데, 그 거리가 ToF 기준 0.32~0.40 m(base_link x 0.57~0.65)라 `stop_distance` 0.30을 조금 넘는다. 사람이 로봇과 겹칠 만큼 들어오면(시뮬레이션 actor는 로봇을 통과) 센서보다 안쪽이라 못 본다
- ToF 센서·`tof_node`는 상자로 확인한 대로 동작한다. 조건 노드도 두 입력이 맞을 때는 "기다림"을 골랐다(1번)
- `memory_sec`·`stop_distance`를 늘리면 둘 다 참이 되겠지만 지시서의 "숫자로 때우기"라 하지 않았다

## 다음 (노트북이 정할 것)
- (A)를 "막히기 시작한 순간"에 판단하게: 조건 노드가 아니라 상시 도는 작은 노드(또는 tof_node)가 "ToF가 막힘으로 바뀐 순간, 그 직전 `memory_sec` 안에 다가오는 사람을 봤으면 `person_blocking`을 참으로, ToF가 비면 거짓"을 내고, 조건 노드는 그 값만 본다. 기억 시간을 늘리지 않고도 20 s 지연을 피한다
- (B) `stop_distance`: 로봇이 사람 앞에서 실제로 멈추는 거리(ToF 0.32~0.40 m)를 보면 0.30은 짧다. HumanLayer 치명 반경 0.25 m + inflation에서 나오는 값이라 같이 정해야 한다. 상자 앞에서도 그 거리에 멈추므로 (A)가 사람·상자를 가른다
- 바깥 복구까지 20 s 걸리는 것 자체(진전 없음 판정 10 s, 내부 재시도)도 "사람 앞에서는 바로 기다리기"와 맞지 않는다. 지시서가 `progress_checker`를 건드리지 말라 해서 그대로 둠
