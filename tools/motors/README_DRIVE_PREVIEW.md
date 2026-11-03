# 모터 출력 없는 ROS 목표 속도 미리보기

`drive_preview`는 Twist를 좌우 바퀴 목표 속도로 변환하고 읽기 전용 엔코더 속도와 비교합니다. 직렬 통신, 모터 출력, `/cmd_vel` 발행은 없습니다. PID 제어·RoboClaw 속도 명령·명령 중단 시 정지는 구현하지 않습니다.

```bash
bash ~/limbo/tools/motors/run_drive_preview.sh
```

다른 터미널에서 필요할 때 기존 읽기 전용 입력을 실행합니다. 포트 소유자는 이 엔코더 노드 한 개뿐이어야 합니다.

```bash
bash ~/limbo/tools/encoders/run_odometry.sh
```

두 실행은 기본 `ROS_DOMAIN_ID=97`, `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`입니다. 관측·발행 터미널도 같은 값을 설정하고 ROS Jazzy와 workspace의 `install/local_setup.bash`를 source해야 합니다.

| 인터페이스 | 타입·의미 |
|---|---|
| `/limbo/drive_preview/cmd_vel` | 입력 `geometry_msgs/Twist`: x 선속도(m/s), z 각속도(rad/s) |
| `/limbo/drive_preview/target_joint_states` | 출력 `sensor_msgs/JointState`: 왼쪽·오른쪽 목표 각속도(rad/s); position/effort 비어 있음 |
| `/wheel/joint_states` | 기존 실제 엔코더 입력; joint 이름으로 좌우를 구분 |
| `/limbo/drive_preview/status` | 출력 `diagnostic_msgs/DiagnosticArray`: 목표·실제 rad/s 및 counts/s, 차이, 데이터 나이, 무출력 상태 |

기본 입력은 실제 주행 토픽과 분리됩니다. 기존 `/cmd_vel`을 관측하려면 `command_topic:=/cmd_vel` 인자로 구독 대상을 바꿀 수 있지만 이 노드는 여전히 모터를 제어하지 않습니다. 시험 명령은 기본 미리보기 토픽에만 발행합니다.

먼저 관측 터미널에서 echo를 시작하고, 별도 터미널에서 명령을 발행합니다. 목표 토픽은 volatile이며 한 번만 발행하므로 나중에 구독하면 과거 목표를 받지 않습니다.

```bash
ros2 topic echo /limbo/drive_preview/target_joint_states
```

```bash
ros2 topic pub --once /limbo/drive_preview/cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.05}, angular: {z: 0.0}}'
ros2 topic echo /limbo/drive_preview/status
```

좌우 선속도는 `v_left=v-w*b/2`, `v_right=v+w*b/2`, 바퀴 각속도는 `v_wheel/r`, 초당 카운트는 `각속도*CPR/(2π)`입니다. 반지름·간격은 기존 `wheel_odometry.yaml`, CPR은 `encoders_readonly.yaml`에서 읽어 odom과 공유합니다. 현재 반지름은 양쪽 0.075m, 간격 0.54m, CPR은 왼쪽 3688·오른쪽 3607의 임시값입니다.

모든 출력은 바퀴 전진 양수입니다. 모터는 M1=오른쪽·M2=왼쪽이며 둘 다 양수 duty가 전진이지만, 원시 엔코더는 전진 시 M1+, M2−입니다. 여기의 정규화 counts/s를 그대로 RoboClaw의 특정 명령에 전달하면 안 됩니다. 모터 속도 제어와 원시 피드백 부호 처리는 별도 구현·검증 대상입니다.

Twist에는 촬영·생성 시각이 없으므로 목표 stamp는 이 노드의 수신 시각입니다. 명령마다 한 번만 목표를 발행하며 마지막 목표를 주기적으로 재발행하지 않습니다. 유효한 최근 목표와 엔코더 표본이 있을 때만 진단 차이를 계산하며, 차이는 `실제−목표`입니다. 시간이 지난 값은 비교 불가로 표시합니다. 이는 관측 데이터의 유효성 처리이며 모터 watchdog이 아닙니다. 정지한 바퀴에 0이 아닌 목표를 주면 차이가 나는 것이 정상이며 속도 추종 실패로 판정하지 않습니다.

현재 단계는 변환·토픽·비교 경로 검증입니다. 실제 속도 추종, PID/QPPS, 바닥 주행 및 명령 중단 시 정지는 이 도구로 검증되지 않습니다. 종료는 Ctrl+C입니다.
