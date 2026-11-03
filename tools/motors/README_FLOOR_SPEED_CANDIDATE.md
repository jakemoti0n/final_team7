# 바닥 저속 제어 재현용 후보 설정

이 파일은 `ff025_speed003_forward_5s_01`·`ff025_speed003_forward_5s_02`에서 사용한 설정을 다시 비교하기 위한 후보이다. **엄격한 속도 추종 기준을 충족하지 못했으며, 기본 설정으로 채택하지 않았다.** 기존 실행 파일·launch 기본값·일반 주행 설정은 바꾸지 않는다.

첫 회차는 사용자가 부드러운 움직임을 관찰했고 마지막 구간의 평균 속도는 양쪽 모두 기준 안에 있었지만, 속도오차 p95는 기준을 넘었다. 같은 조건의 재현 회차에서는 사용자가 약간 삐뚤어진 움직임을 관찰했고 오른쪽 평균 오차도 약 +14%로 기준을 넘었다. 상대적 개선 관찰과 반복 가능한 정밀 추종 성공을 구분한다. 일정12% 출력 진단의 부드러운 움직임도 이 후보의 속도 제어 성공을 뜻하지 않는다.

## 저장된 값과 범위

`config/floor_speed_candidate.yaml`의 노드 이름은 `wheel_speed_bench`다. 좌우 반지름0.075m·중심 간격0.54m, 임시 CPR 왼쪽3688·오른쪽3607을 사용한다. 좌우 목표는0.4rad/s로, 이 반지름에서 전진0.03m/s·yaw0과 대응한다. Kp0.10·Ki0.20·속도 창0.10초·FF gain0.25·duty cap4915(약15%)이며, 요청 시간은최대5초다. `extended_observation=false`, `use_sim_time=false`다.

목표에서 FF항은10%지만 실제 출력은 PI·상승률·15% 상한의 영향을 받는다. 고정10% 출력 명령이 아니다. 기존 전류·속도·누적1500카운트·피드백 나이·정지 경계를 그대로 사용하며, 한계에 먼저 도달하면5초 전에 끝날 수 있다. 자동 재시도나 시간·거리 확장은 없다.

파일 자체에는 `enable_output=false`, 빈 `record_dir`를 둔다. 두 값을 명시적으로 바꾸지 않으면 실제 시험을 시작할 수 없다. 노드별 메타데이터를 ROS 파라미터에 추가하지 않았다.

## 재현 실행 절차

평평한 바닥에서 배터리를 고정하고 전방약1m의 빈 경로와 케이블 여유를 확보한다. 시작 위치·전진 방향선을 맞추고, 앞뒤 캐스터의 초기 방향을 기록한다. 확인된 +극 차단 장치 옆에 하드웨어 담당자가 대기한다. Motion Studio·읽기 전용 엔코더 노드·다른 구동 노드는 종료해 RoboClaw 직렬 포트를 한 프로그램만 사용하게 한다.

아래는 **수동으로 준비하고 한 회차씩 실행하는 예시**다. 실행 전 모터 명령을 보낼 예정임을 현장에 알리고, 두 터미널 모두 같은 Jetson·ROS 환경을 사용한다. 빌드 후 설치된 후보 파일을 불러온다.

두 터미널의 공통 환경:

```bash
source /opt/ros/jazzy/setup.bash
source /home/automaton/limbo/limbo/install/local_setup.bash
export ROS_DOMAIN_ID=102
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
```

먼저 터미널 B에서 준비 상태를 관찰한다. `status` 항목의 `message: ready`를 확인한다.

```bash
ros2 topic echo /limbo/drive_bench/status diagnostic_msgs/msg/DiagnosticArray
```

터미널 A에서 새 기록 경로를 정하고 노드를 실행한다. 아래 경로는 매번 새 이름이어야 하며, 기록 디렉터리를 미리 만들지 않는다.

```bash
LIMBO_TRIAL_DIR="/home/automaton/limbo_bench_records/floor_candidate_$(date +%Y%m%d_%H%M%S)"
test ! -e "$LIMBO_TRIAL_DIR" || exit 1
ros2 run limbo_hardware wheel_speed_bench --ros-args \
  --params-file /home/automaton/limbo/limbo/install/limbo_hardware/share/limbo_hardware/config/floor_speed_candidate.yaml \
  -p enable_output:=true \
  -p record_dir:="$LIMBO_TRIAL_DIR"
```

`enable_output=true`로 실행하면 장치를 열어 firmware를 확인하고 `ready` 상태로 기다린다. **그 자체로 전진하지 않는다.** 시작 후 약30초 안에 명령이 없으면 종료하므로, 현장 준비를 완료한 뒤 노드를 실행한다. `ready`는 아직 실제 구동 직전 preflight를 통과했다는 뜻이 아니다.

터미널 B의 상태 관찰을 Ctrl+C로 마친 뒤, 현장에 **이제 전진 명령을 보낸다**고 안내하고 아래 한 번의 Twist를 전송한다. 이는 일반 `/cmd_vel`이 아닌 별도 시험 토픽이다.

```bash
ros2 topic pub --once /limbo/drive_bench/cmd_vel geometry_msgs/msg/Twist \
  '{linear: {x: 0.03}, angular: {z: 0.0}}'
```

이 명령을 받은 뒤 보드 timeout·전압·정지 상태를 확인하는 preflight가 실행된다. 통과하면 단 한 번 arm하여 최대5초 구동하고 정지 검증 뒤 종료한다. 다른 목표나 추가 nonzero 명령을 보내지 않는다. 중단이 필요하면 같은 토픽의 zero Twist 또는 터미널 A의 Ctrl+C로 기존 정지 경로를 호출할 수 있다. 정지가 확인되지 않으면 현장 담당자가 준비된 차단 수단을 사용한다.

완료 후 기록의 `stop.zero_acked`, `stop.stationary_verified`, `stop.closed`와 실제 정지를 확인한다. `summary.passed=true`는 한 회차 실행·정지 결과이며 **속도 추종 합격 표시가 아니다**. raw count·duty·ROS 토픽과 평균/p95·현장 관찰을 별도로 분석한다. 위 최소 CLI 예시는 별도 odom observer나 추가2초 읽기 전용 검사를 자동 실행하지 않는다. 이전 시험과 같은 전체 검증을 원하면 검토된 observer·증거 수집 절차를 함께 사용한다.

이 후보는 자동 시작·연속 주행·Nav2 통합·일반 `/cmd_vel` 중단 감지 보완을 포함하지 않는다. 보드 PID·전류 제한·NVM 설정도 바꾸지 않는다. 전진0.03m/s의 한정된 비교 자료이며, 원래0.02m/s나 후진·회전·다른 하중에서 검증된 설정으로 일반화하지 않는다.
