# Limbo RoboClaw 읽기 전용 ROS 입력

2026-10-29 실물 점검 기준. 모터 구동 API·명령 구독·카운터 초기화·보드 설정 쓰기가 없는 입력 노드다.

## 실행

```bash
cd ~/limbo
bash tools/encoders/run_readonly.sh
```

기본 ROS domain은 기존 OAK 검사와 같은 `97`, discovery 범위는 `LOCALHOST`다. 다른 터미널의 관찰에도 같은 설정을 사용한다. 기존 카메라 실행 환경을 먼저 source한 경우 해당 DDS 환경을 유지한다. 이 스크립트 자체는 카메라를 실행하지 않는다.

```bash
source /opt/ros/jazzy/setup.bash
source ~/limbo/limbo/install/local_setup.bash
export ROS_DOMAIN_ID=97 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
ros2 topic echo /wheel/encoder_counts --once
ros2 topic echo /wheel/joint_states --once
ros2 topic hz /wheel/encoder_counts
```

다른 설정 파일은 `bash tools/encoders/run_readonly.sh params_file:=/절대경로/설정.yaml`로 지정한다. 설정은 시작할 때 읽으며 실행 중 CPR 등 변환 설정 변경은 거부한다. 기본 파일은 `limbo/src/limbo_hardware/config/encoders_readonly.yaml`이다. 종료는 실행 터미널의 Ctrl+C다. 자동 부팅 서비스는 설치하지 않는다.

## 토픽 계약

| 토픽 | 타입 | 의미 |
|---|---|---|
| `/wheel/encoder_counts` | `limbo_interfaces/msg/WheelEncoderCounts` | M1·M2 원시 uint32, 좌우 전진 양수 변화량/누적량, 세션·순서·기준 표본 여부 |
| `/wheel/joint_states` | `sensor_msgs/msg/JointState` | `right_wheel_joint`의 상대 각도 rad·각속도 rad/s, 왼쪽 CPR 설정 시 `left_wheel_joint`도 추가 |
| `/diagnostics` | `diagnostic_msgs/msg/DiagnosticArray` | `limbo/roboclaw_readonly`의 연결 상태·오류·최종 읽기 경과시간·임시 보정 정보 |

양쪽 카운트는 RoboClaw의 한 번의 command 78 응답에서 읽는다. M1은 오른쪽, M2는 왼쪽이다. 원시 카운트는 그대로 보존하고 상대 카운트는 오른쪽 `+1`, 왼쪽 `-1`의 부호로 전진을 양수로 맞춘다. 원시값의 32비트 래핑을 처리한다.

오른쪽 환산은 `right_total × 2π / 3607`이다. **3,607은 사용자가 선택한 바퀴 1회전당 임시 카운트**이며 제조사 확정 사양이 아니다. 왼쪽은 `left_counts_per_revolution`이 양수로 설정된 경우 `left_total × 2π / left_counts_per_revolution`으로 환산한다.

현재 제공하는 설정 파일의 **왼쪽 임시값은 3,688 counts/rev**이다. 2026-10-29 같은 방향으로 손회전한 유효 1회전 3회의 절대 순카운트는 **3,697·3,670·3,696**이었고, 평균3,687.6667을 가장 가까운 정수로 반올림했다. 최댓값과 최솟값의 차이27을 평균으로 나눈 편차는 약0.7322%다. 최초 과회전 시도는 이 통계에서 제외했다. 이 세 측정의 실제 물리 방향이 전진인지 후진인지는 확인되지 않았으므로, 같은 방향의 절대 카운트로 환산 크기만 정했다. 기존 방향 검증에서 정한 오른쪽`+1`·왼쪽`-1`은 변경하지 않았다. 손회전 측정의 임시값이며 정밀 회전각이나 주행 거리 정확도를 확정하는 값은 아니다.

노드 내부 기본값인 왼쪽 CPR0은 미확정 상태를 뜻하며, 설정 파일에서도 명시적으로0을 지정하면 왼쪽 각도·각속도를 발행하지 않는다. 음수·무한대·NaN은 기동 시 거부한다.

왼쪽이 활성화되면 JointState의 이름과 값 순서는 항상 **오른쪽, 왼쪽**이다. 소비자는 배열 번호를 가정하기보다 `name`으로 바퀴를 구분한다. 두 바퀴가 각각의 CPR을 사용하고 같은 수신 시간 간격으로 각속도를 계산한다. 단위가 없는 카운트를 JointState의 rad 필드에 넣지 않는다. 바퀴 반지름이나 간격을 가정한 거리·속도·`/odom`·TF는 발행하지 않으며 이 토픽은 글로벌 `/joint_states`에 연결하지 않았다.

두 데이터 토픽의 header는 같은 **호스트 ROS 수신 시각**이며 보드의 측정 시각은 아니다. 각속도는 실제 연속 수신의 monotonic 시간 간격으로 계산한다. QoS는 reliable, volatile, keep-last 5이며 기본 수집은 20 Hz다.

## 연결과 오류

장치 경로는 `/dev/serial/by-id/usb-Basicmicro_Inc._USB_Roboclaw_2x15A-if00`이다. 제품 이름에 고유 serial이 없으므로 해당 제품이 둘 이상 연결되면 선택을 거부한다. USB VID/PID·제품·cdc_acm 및 firmware를 확인하고 독점 접근을 요청한다. 사용자에게 dialout 접근이 필요하고 주전원은 켜져 있어야 한다. 다른 프로그램이 포트를 사용하면 그 프로그램을 종료한 뒤 실행한다.

실제 송신 직전에 `80 15`(버전 조회) 또는 `80 4e`(두 카운트 조회)인지를 검사한다. 각 응답의 길이·CRC와 0.2초 트랜잭션 제한을 확인한다. 오류 시 데이터 토픽 발행을 중단하고 ERROR 진단을 내며 포트를 닫는다. 기본 2초 뒤 장치 식별부터 다시 시도한다. 마지막 정상 표본을 새 timestamp로 반복 발행하지 않는다.

프로세스 시작 또는 연결 복구마다 `session_id`가 새 UUID가 되고 sequence 0, `baseline=true`, 상대 누적량 0부터 시작한다. 이 첫 표본의 JointState velocity는 빈 배열이다. 끊긴 구간의 이동은 계산하지 않는다. 소비자는 세션을 넘겨 상대 위치를 그대로 적분하지 말아야 한다. 나중에 CPR을 보정할 수 있도록 원시 카운트를 저장하는 것이 좋다.

`max_delta_counts=10000`은 표본 간 큰 점프를 거르는 보조 검사다. 작은 보드 카운터 초기화는 정상 움직임과 구분되지 않을 수 있다. 이 노드는 위치·거리 정확도나 모터 정지 기능을 검증한 주행 제어기가 아니다.

## 개발 검증

```bash
source /opt/ros/jazzy/setup.bash
cd ~/limbo/limbo
colcon build --packages-select limbo_interfaces limbo_hardware --symlink-install
source install/local_setup.bash
python3 -m pytest -q src/limbo_hardware/test
```

테스트는 CRC·읽기 명령 제한·길이·시간 제한·USB 식별·포트 오류·래핑·부호·재연결 기준점·3,607 환산·왼쪽 별도 CPR의 전진/후진/정지·양쪽 재연결 기준점·오류 시 미발행을 다룬다. 왼쪽 CPR이0인 기존 오른쪽 전용 동작과 잘못된 CPR 거부도 확인한다. 모의 통신 장애 테스트와 실제 USB 분리 시험은 구분해야 한다.

## 엔코더 기반 raw odometry

카운트·JointState와 raw `/odom`을 함께 실행하려면 기존 encoder-only 실행을 종료한 뒤 다음 명령을 사용한다. 이 경로가 엔코더 노드도 함께 시작하므로 `run_readonly.sh`와 동시에 실행하지 않는다.

```bash
bash ~/limbo/tools/encoders/run_odometry.sh
```

새 `wheel_odometry` 노드는 `/wheel/encoder_counts`만 구독하고 `nav_msgs/msg/Odometry` 형식의 `/odom`과 `limbo/wheel_odometry` 진단을 발행한다. 직렬 포트에 접근하거나 모터 명령을 보내지 않는다. 메시지의 pose는 `odom` 프레임, twist는 `base_footprint` 프레임 기준이다. 기존 Limbo의 Gazebo raw odom 입력과 같은 토픽·프레임 계약을 사용한다.

기하학 설정은 `limbo_hardware/config/wheel_odometry.yaml`에 있다. 2026-10-29 사용자 실측 근사값은 좌우 지름15cm(반지름0.075m), 바퀴 자체 폭 각각5cm, 바깥 끝 전체 폭59cm다. 중심면 간격은 `59 - 5/2 - 5/2 = 54cm`이므로0.54m를 적용한다. 최초 전체 폭61cm·폭8cm·중심45cm 설명은 후속 실측 설명으로 정정됐다. 현재 값은 하중·타이어 변형·슬립을 포함한 주행 보정값이 아니다.

두 CPR은 새 launch가 **기존 `encoders_readonly.yaml`을 읽어** odom 노드에 전달한다. 현재 오른쪽3,607·왼쪽3,688 임시값을 별도 파일에 중복 저장하지 않는다. 다른 설정은 `encoder_params_file:=/절대경로/encoder.yaml odom_params_file:=/절대경로/odom.yaml`로 지정한다. CPR과 기하학 값이 양수가 아니면 실행을 거부하며 실행 중 설정 변경도 거부한다.

바퀴별 이동량은 `dl = left_delta × 2π × left_radius / left_CPR`, `dr = right_delta × 2π × right_radius / right_CPR`이다. `ds=(dr+dl)/2`, `dtheta=(dr-dl)/wheel_separation`을 이용해 일정한 바퀴 속도를 가정한 한 표본의 원호를 정확히 적분한다. 직진에 가까울 때도 수치적으로 안정적인 sinc 형태를 쓴다. twist는 `linear.x=ds/dt`, `linear.y=0`, `angular.z=dtheta/dt`이며 dt는 연속 엔코더 header 시각의 차이다. header는 엔코더 노드의 호스트 수신 시각을 그대로 복사하며 보드 측정 시각으로 해석하지 않는다.

최초 수신 표본에서는 기준만 잡고 odom을 발행하지 않는다. 다음 정상 연속 표본부터 발행한다. 새 엔코더 session·순번 누락·0.5초 초과 간격·시각 역행·누적량/증분 불일치가 발생하면 해당 간격을 적분하지 않고 새 기준을 잡으며 기존 x/y/yaw를 유지한다. 중복·역순 메시지와 이미 종료된 세션의 표본은 기존 기준을 건드리지 않고 버린다.0.5초보다 오래된 입력·50ms보다 미래인 시각도 거부한다. 입력이 끊기면 진단으로 표시하고 마지막 odom을 새 timestamp로 반복 발행하지 않는다. 이 정책은 연결이 끊긴 동안의 이동을 복구하지 않는다. **odom 노드 자체를 다시 시작하면 odom 원점이0으로 초기화되지만, 엔코더만 재연결되면 누적 pose는 유지된다.**

공분산은 실측 확률 모델이 아니라 명시적인 **임시 보수적 대각 예산**이다. pose x/y 초기분산0.0025m², yaw0.01rad²에서 시작해 평균 절대 바퀴 이동1m마다 각각0.01m²·0.02rad²를 더한다. 불연속 재기준마다 각각0.25m²·0.25rad²를 추가한다. twist 분산은 vx0.01·vy0.01(m/s)², wz0.04(rad/s)²이며, 관측하지 않는 z/roll/pitch에는1e6을 사용한다. 교차 공분산은0으로 둔다. 이 값들은 YAML에서 조정 가능하며 실제 센서 오차나 주행 정확도 검증을 대체하지 않는다.

이 launch는 **TF·EKF·Nav2를 시작하지 않는다.** 기존 시뮬레이션 EKF는 `/odom`의 vx/vy와 `/imu`의 회전속도를 융합하고 `use_sim_time=true`이며 odom→base_footprint TF를 담당한다. 현재 실물 IMU가 확인되지 않은 상태에서 그 설정을 그대로 실행하지 않는다. 새 wheel odom은 TF를 발행하지 않으므로 나중에 실물 EKF를 연결할 때 중복 TF가 생기지 않는다. 로봇을 들어 바퀴를 돌려 검사할 때 나오는 pose는 바퀴 움직임으로 계산한 가상의 이동량이며 실제 차체의 바닥 이동을 측정한 결과가 아니다.
