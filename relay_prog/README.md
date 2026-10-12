# LIMBO 상태 전달 Bridge

[PRD의 공통 전송 계약 v1](docs/PRD.md)을 구현하는 독립 ROS2 Jazzy 워크스페이스다. 기존 `limbo/` launch나 코드를 수정하지 않는다. 네 구독 콜백은 헤더·수신 UTC·누적 횟수와 odom의 평면 선속도/각속도 숫자만 추출한다. 원본 `Image.data`/`PointCloud2.data`에 접근하거나 메시지를 추가 저장·변환·전송하지 않는다. ROS2 자체 수신·역직렬화 비용은 발생한다.

> **`tools/receiver.py`는 실제 Server Program(Dashboard 서버)을 대신하는 테스트용 Mock 서버(Mockup)다.** 실제 서버가 준비되지 않아도 Bridge의 JSON 전송과 장애 복구를 검증할 수 있도록 제공한다. 운영용 서버나 Dashboard UI가 아니며, 실제 서버에 연결할 때는 실행하지 않는다.

## 설치와 빌드

Ubuntu의 기존 ROS2 Jazzy와 시스템 Python 3.12를 사용한다. 아래 명령은 저장소 루트에서 시작한다. YOLO 가상환경을 활성화한 터미널이라면 먼저 `deactivate`한다.

```bash
source /opt/ros/jazzy/setup.bash
cd relay_prog
/usr/bin/python3 -m venv --system-site-packages venvs/bridge
venvs/bridge/bin/python -m pip install -r requirements.txt
venvs/bridge/bin/python -m colcon build --symlink-install --base-paths src
source install/setup.bash
```

`rclpy`, `nav_msgs`, `sensor_msgs`, `rosgraph_msgs`, colcon은 기존 Jazzy 설치를 사용한다. 새 PC에서 빠진 도구는 다음으로 설치한다. 검증 도구만 `pytest`, `psutil`을 추가로 사용한다.

```bash
sudo apt install python3-venv python3-colcon-common-extensions python3-pytest python3-psutil \
  python3-yaml ros-jazzy-rclpy ros-jazzy-nav-msgs ros-jazzy-sensor-msgs ros-jazzy-rosgraph-msgs
```

빌드를 가상환경 Python으로 실행해야 설치된 `bridge` 실행 파일도 같은 Python과 HTTP 의존성을 사용한다. 기존 YOLO 환경에는 설치하지 않는다. 패키지 다운로드에는 인터넷 접속이 필요하다.

## 설정

기본 설정: [`src/limbo_telemetry_bridge/config/bridge.yaml`](src/limbo_telemetry_bridge/config/bridge.yaml).

| 설정 | 기본값 / 의미 |
|---|---|
| `robot_id` | `LIMBO-01`; 수신 서버 설정과 일치 |
| `server_url` | `http://127.0.0.1:8000`; 경로 없는 서버 주소. `/api/v1/telemetry`를 자동 추가 |
| `send_interval_s` | 1초; 정상 시 전송 시작 간격 |
| `request_timeout_s` | 1초; DNS·연결·응답 본문 포함 전체 요청 제한. v1에서는 1초 이하 |
| `source_clock` | `ros_sim`; `use_sim_time=true`. 실물은 `ros_system` |
| `topics.<key>.name` | 아래 표의 절대 토픽명 |
| `reliability` | `best_effort` 또는 `reliable` |
| `durability` | `volatile` 또는 `transient_local` |
| `depth` | Keep Last 깊이, 기본 1 |

| 키 | 기본 토픽 | 형식 |
|---|---|---|
| odom | `/odom` | `nav_msgs/msg/Odometry` |
| lidar_raw | `/mid360/points` | `sensor_msgs/msg/PointCloud2` |
| lidar_filtered | `/mid360/points_filtered` | `sensor_msgs/msg/PointCloud2` |
| camera_raw | `/rgbd_camera/image` | `sensor_msgs/msg/Image` |

원본 토픽은 `../limbo/src/limbo_simulation/config/bridge.yaml`, 필터 출력은 `../limbo/src/limbo_bringup/launch/start_simulation.launch.py`에서 확인했다. 실제 발행자 QoS는 실행 시 확인한다. Best Effort 구독은 Reliable/Best Effort 발행자와 연결 가능하며, 반대 조합은 호환되지 않는다. [ROS2 QoS 문서](https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Quality-of-Service-Settings.html).

운영 환경의 `ROS_DOMAIN_ID`, RMW 및 discovery 설정을 기존 LIMBO와 동일하게 사용한다. Bridge는 도메인을 설정하지 않는다. 설정 변경은 Bridge를 종료한 뒤 다시 실행해 적용한다. ROS 인수로 토픽 remap은 가능하지만 시계 모드는 YAML의 `source_clock`으로 관리한다.

## 실행과 종료

### 로컬 검증: Mock 서버 사용

아래 절차는 실제 Server Program 대신 `tools/receiver.py`를 실행하는 로컬 테스트다.

```text
ROS2 토픽 → Bridge → receiver.py (Server Program을 대신하는 Mock 서버)
```

첫 터미널: ROS 설치 없이 실행 가능한 Mock 서버를 시작한다. 이 서버는 Bridge의 `POST /api/v1/telemetry` 요청을 받아 계약 v1 형식과 세션·순번을 검증하고 응답한다. 장애 모드로 지연·오류·응답 유실을 재현할 수도 있다.

```bash
cd relay_prog  # 저장소 루트 기준
/usr/bin/python3 tools/receiver.py --host 127.0.0.1 --port 8000
```

둘째 터미널: 기존 LIMBO와 같은 ROS 환경을 준비하고 Bridge를 실행한다. 기본 `server_url`인 `http://127.0.0.1:8000`으로 위 Mock 서버에 연결한다.

```bash
source /opt/ros/jazzy/setup.bash
cd relay_prog  # 저장소 루트 기준
source install/setup.bash
ros2 run limbo_telemetry_bridge bridge --config src/limbo_telemetry_bridge/config/bridge.yaml
```

ROS 메시지가 없어도 기본 주기인 1초마다 null/0 스냅샷을 전송한다. `curl http://127.0.0.1:8000/status`로 Mock 서버가 받은 최신 계약 JSON을 확인할 수 있다. `/status`는 이 Mock 서버의 검증용 기능이다.

### 실제 Server Program에 연결

실제 Dashboard 서버가 준비되면 **`tools/receiver.py`를 실행하지 않고** Bridge를 실제 서버에 직접 연결한다.

```text
ROS2 토픽 → Bridge → 실제 Server Program(Dashboard 서버)
```

1. 실제 서버가 [공통 전송 계약 v1](docs/PRD.md)의 `POST /api/v1/telemetry` 수신 API와 응답 규격을 구현했는지 확인한다.
2. Bridge 설정 파일의 `server_url`을 실제 서버의 주소로 변경한다. 주소에는 `/api/v1/telemetry` 경로를 붙이지 않는다. 예를 들어 서버 PC의 주소가 `192.168.0.10`, 포트가 `8000`이면 `http://192.168.0.10:8000`으로 설정한다.
3. 실제 서버를 실행하고, 위와 동일한 Bridge 실행 명령으로 시작한다. 이미 실행 중인 Bridge는 설정 변경 후 다시 시작한다.

Jetson에서 Bridge를 실행하고 다른 PC에서 서버를 운영한다면 `server_url`은 그 서버 PC를 가리켜야 한다. `127.0.0.1`은 Bridge가 실행 중인 Jetson 자신을 가리킨다. 서버는 Jetson에서 접근할 수 있는 네트워크 인터페이스에 바인딩한다. Mock 서버는 실제 서버 연결이나 Jetson 자동 시작 구성의 필수 구성요소가 아니다.

### 종료와 토픽 진단

각 터미널에서 `Ctrl+C`로 종료한다. Bridge는 전송 재시도를 중단하고 진행 중 요청의 제한 시간 내 완료 후 구독을 해제한다. `SIGTERM`도 ROS2 종료 처리를 거친다. 서버 장애에서도 종료가 무한 대기하지 않는지 자동 테스트한다.

토픽·QoS 진단:

```bash
ros2 topic list --no-daemon
ros2 topic info /odom -v --no-daemon
ros2 topic info /mid360/points -v --no-daemon
ros2 topic info /mid360/points_filtered -v --no-daemon
ros2 topic info /rgbd_camera/image -v --no-daemon
```

`ros2 topic hz`는 추가 구독자를 만들어 원본 수신 부하가 발생하므로 필요할 때만 사용한다. 로그 디렉터리를 바꿀 때는 `export ROS_LOG_DIR="$PWD/log/ros"`를 사용할 수 있다.

## 상태와 전송 동작

- 콜백과 HTTP 전송은 별도 스레드다. 잠금 아래 복사하는 것은 숫자·문자열과 유한 버킷뿐이다. 직렬화·네트워크 I/O는 잠금 밖에서 수행한다.
- 최신 숫자 상태 한 세트, 토픽당 최대 51개 0.1초 버킷, HTTP 요청 한 개만 유지한다. 전송 대기 스냅샷은 0개다. 재시도 시 과거 본문을 재생하지 않고 새 순번의 최신 스냅샷을 만든다.
- `receive_hz`는 최근 5초 콜백 수신 횟수/5초다. 첫 5초 또는 해당 토픽 미수신이면 `null`, 멈춘 토픽은 `0`이 된다. 버킷 경계 오차는 0.1초 미만이다.
- 헤더는 ROS sec/nanosec 그대로 유지한다. 수신/전송 표시는 UTC, age·빈도·주기·재시도는 단조 증가 시계를 사용한다. `/clock` 정지·역행과 무관하게 전송한다.
- 선속도는 `hypot(linear.x, linear.y)`, 각속도는 `angular.z`다. 어느 성분이든 무효이면 motion 네 필드 전체를 null로 보내며, odom 수신 횟수는 계속 증가한다.
- 실패 후 완료 시점부터 1·2·4·8·10초 간격으로 재시도한다. 4xx/종료 세션은 10초 간격이다. 성공 후 기본 주기로 복귀한다. 동일 오류는 상태가 바뀔 때만 로그에 남긴다.
- HTTP 200의 응답 필드·세션·순번·UTC를 검증한다. 리다이렉트를 따라가지 않는다. 요청/응답 본문은 각각 8 KiB로 제한한다. [aiohttp의 전체 timeout](https://docs.aiohttp.org/en/stable/client_reference.html#aiohttp.ClientTimeout)에 더해 전체 비동기 작업 deadline을 적용한다.

## 독립 HTTP 검증

이 절은 실제 Server Program 없이 Mock 서버로 Bridge를 검증하는 절차다. 아래 장애 모드는 `tools/receiver.py`의 테스트 기능이다.

```bash
# relay_prog/에서 실행
source /opt/ros/jazzy/setup.bash
venvs/bridge/bin/python -m pytest tests -q

# Mock 서버를 중지한 뒤 같은 포트에 원하는 장애 모드 하나로 다시 시작
/usr/bin/python3 tools/receiver.py --mode delay --delay 1.5
/usr/bin/python3 tools/receiver.py --mode error
/usr/bin/python3 tools/receiver.py --mode disconnect
# 복구
/usr/bin/python3 tools/receiver.py --mode ok
```

한 포트에는 서버 한 개만 실행한다. 추가 모드: `client_error`(422), `malformed`, `oversized`, `retired`, `drip`(조금씩 응답). `disconnect`는 요청을 반영한 뒤 응답 연결을 닫아 응답 유실을 재현한다. Mock 서버는 별도 v1 검증기로 필드/숫자/null 관계를 검증하고, 순번·세션과 최근 100개 종료 세션을 처리한다. 이 검증은 실제 Dashboard 서버나 UI의 동작 검증을 대신하지 않는다.

## 실제 ROS2 구독·성능 검증

```bash
# relay_prog/에서, Jazzy를 source한 상태
venvs/bridge/bin/python tools/validate_ros.py \
  --duration 600 --baseline 15 --domain 87 --output docs/ros_validation.json
venvs/bridge/bin/python tools/analyze_validation.py docs/ros_validation.json \
  --output docs/ros_validation_summary.json
# 동일 크기 입력 전후 비교, 프로세스 재시작과 SIGTERM 확인
venvs/bridge/bin/python tools/compare_load.py --domain 88 --output docs/load_comparison.json
# 실제 ROS 발행부터 수신 서버 반영까지의 지연, Reliable 발행자 호환 확인
venvs/bridge/bin/python tools/check_ros_latency.py --domain 89 --output docs/ros_latency.json
```

`--domain`은 테스트 하네스가 자식 프로세스에만 적용하는 격리 도메인이다. 운영 도메인과 겹치지 않는 값으로 바꾼다. 이 도구는 실제 Jazzy/rclpy 발행자와 Bridge를 별도 프로세스로 실행하며, 로봇 제어 명령은 발행하지 않는다. 서버는 임시 로컬 포트를 사용한다. 발행자는 토픽당 20 Hz를 목표로 한다. 테스트 중 각 LiDAR 1 MiB, 이미지 921,600 B로 원본 크기를 늘린다. 발행자만 실행한 baseline과 Bridge 실행 후 CPU/RSS·수신 빈도·전송량을 기록한다. CPU 100%는 논리 CPU 한 개다.

시나리오: ROS 시계 정지/역행, odom NaN, 카메라만 중단, 전체 토픽 중단, 503·타임아웃·응답 유실·422, 수신 서버 완전 종료/재시작. `log/bridge_validation.log`에서 전송 상태 변화를 확인한다. 테스트 발행자의 시작 시점은 baseline만큼 Bridge보다 빠르다.

10분 원시 측정과 판정 결과는 `docs/ros_validation*.json`에 기록한다. 초기 baseline에서는 작은 원본을 사용하므로 큰 원본의 부하 차이는 별도 동일 크기 비교 결과와 함께 해석해야 한다. 테스트 수신 서버까지의 검증은 실제 Dashboard 화면 반영 검증과 구분한다. 최종 결과와 미검증 항목은 [검증 보고서](docs/VALIDATION.md)에 정리한다.
