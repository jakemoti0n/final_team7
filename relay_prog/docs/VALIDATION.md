# Bridge 구현·검증 보고서

검증일: 2026-10-06 (Asia/Seoul). 범위: LIMBO 상태 전달 Bridge, 독립 테스트 수신 서버, 재현 가능한 테스트 도구.

## 변경 내용

- `relay_prog/src/limbo_telemetry_bridge`: 독립 ament_python 패키지, 설정 검증, 네 토픽 구독, 유한 숫자 상태 저장소, 독립 HTTP 작업.
- 요청 전체 1초 제한, 새 스냅샷/새 순번 재시도, 1·2·4·8·10초 backoff, 4xx 및 종료 세션 10초 제한, 상태 전환 로그.
- ROS 헤더/UTC 표시/단조 증가 경과 시간 분리. 원본 메시지·data 버퍼를 콜백 이후 보관하지 않음. 전송 대기열 없음, 진행 중 요청 최대 1개, 토픽당 빈도 버킷 최대 51개.
- `tools/receiver.py`: ROS나 Bridge 모듈에 의존하지 않는 stdlib HTTP 테스트 서버. v1 필드/null 관계 검증, 세션/중복 처리, 장애 주입.
- `tests/`, `tools/`: 자동 테스트 및 실제 ROS2 발행·구독/성능/지연/재시작 검증.
- 설치·빌드·설정·실행·종료·재현 명령은 [README](../README.md)에 수록.

적용 범위에서 `AGENTS.md`는 발견되지 않았다. 기존 `limbo/src/limbo_simulation/config/bridge.yaml`과 `limbo/src/limbo_bringup/launch/start_simulation.launch.py`를 읽어 토픽 구성을 확인했다. `limbo/` 변경은 없다. 기존 `dashboard/` 및 두 PRD는 수정하지 않았다.

## 실행 환경과 명령

- AMD Ryzen 7 5800H, 논리 CPU 16개, Python 3.12.3, ROS2 Jazzy.
- `rclpy` 패키지 7.1.12, `rmw_fastrtps_cpp` 패키지 8.4.4, aiohttp 3.14.4.
- 기존 ROS 시스템 패키지를 공유하는 별도 `relay_prog/venvs/bridge` 환경. YOLO 의존성 변경 없음.
- 아래 명령은 `relay_prog/`에서 Jazzy를 source한 상태로 실행했다.

```bash
venvs/bridge/bin/python -m colcon build --symlink-install --base-paths src
venvs/bridge/bin/python -m pytest tests -q
venvs/bridge/bin/python tools/validate_ros.py --duration 600 --baseline 15 --output docs/ros_validation.json
venvs/bridge/bin/python tools/analyze_validation.py docs/ros_validation.json --output docs/ros_validation_summary.json
venvs/bridge/bin/python tools/compare_load.py --domain 88 --output docs/load_comparison.json
venvs/bridge/bin/python tools/check_ros_latency.py --domain 89 --output docs/ros_latency.json
```

빌드: 1 패키지 성공. 설치된 `ros2 run limbo_telemetry_bridge bridge --help` 동작 확인. ROS2/HTTP 소켓과 패키지 다운로드가 샌드박스에서 차단되어 승인된 외부 실행으로 검증했다.

## 자동 테스트

**40 passed**, ROS 어댑터 테스트를 포함하여 skip 없음.

| 검증 | 결과 |
|---|---|
| 최초 미수신 null/0, zero 헤더, 세션 초기화 | 통과 |
| 최근 5초 빈도·준비 기간·중단 시 0 Hz·51버킷 상한 | 통과 |
| 평면 선속도·제자리 회전·NaN/±Infinity 무효 처리 | 통과 |
| ROS 헤더 역행 및 UTC 역행과 monotonic age 분리 | 통과 |
| 제어 가능한 단조 시계로 실제 sender의 재시도/정상 주기 | 통과 |
| 실제 HTTP 정상·지연·조금씩 응답·연결 종료·503·422·비정상/과대 응답·복구 | 통과 |
| 장애 중 수집 지속, 최신 상태 복구, 요청 중 종료 시간 제한 | 통과 |
| 독립 수신기 스키마·HTTP 오류·중복/역순·종료 세션·heartbeat | 통과 |
| 설정 오류 거부, 원본 data 미접근 및 weakref로 메시지 미보관 | 통과 |

## 실제 ROS2 구독과 지연

격리 도메인 87의 실제 Jazzy 발행자/Bridge를 별도 프로세스로 실행했다. `ros2 topic info <topic> -v --no-daemon`으로 네 토픽 각각 발행자 1개와 구독자 1개, 형식, Best Effort/Volatile QoS를 확인했다. CLI가 History Depth를 UNKNOWN으로 출력했으므로 depth=1은 생성 설정으로 확인한 값이며 CLI 측정값으로 주장하지 않는다.

별도 도메인 89에서는 **Reliable 발행자 → Best Effort Bridge 구독자**를 실제 연결했다. 최초 미수신 heartbeat 후 0속도/회전/NaN/복구 메시지를 발행했고, 발행 직전의 단조 시각부터 HTTP 서버의 반영 단조 시각까지 측정했다.

| 입력 | 반영 지연 |
|---|---:|
| 0속도·0각속도 | 0.874초 |
| 0속도·0.75 rad/s | 1.000초 |
| NaN → motion 전체 null | 0.999초 |
| 유효값 복구 | 0.997초 |

**4회 모두 2초 미만**. Dashboard 화면이 아닌 독립 수신 서버까지의 실측이다. 근거: [ros_latency.json](ros_latency.json).

## 동일 크기 입력 전후 비교

도메인 88에서 각 LiDAR 1,048,576 B × 2, 이미지 921,600 B, 각 토픽 20 Hz 목표로 고정했다. 5초 준비 후 발행자 단독 15초, Bridge 추가 후 5초 준비와 30초 측정을 비교했다. CPU 100%는 논리 CPU 한 개다.

| 측정 | Bridge 실행 전 | Bridge 실행 후 |
|---|---:|---:|
| 발행자 CPU 평균 | 2.60% | 5.03% |
| 발행자 RSS 평균 | 76.67 MiB | 77.08 MiB |
| Bridge CPU 평균 | 해당 없음 | 19.40% |
| Bridge RSS 평균 | 해당 없음 | 86.83 MiB |
| Bridge odom 수신 | 해당 없음 | 19.99 Hz |
| 수신 서버에 반영된 JSON 본문 | 0 B/s | 983.95 B/s |

HTTP 헤더와 DDS 운송량은 위 JSON 바이트 수에 포함하지 않는다. ROS 원본의 수신/역직렬화 비용이 있으므로 CPU가 0에 가깝다고 가정하지 않는다. 다른 검증 작업도 동일 호스트에서 실행했으므로 실물의 부하 보증값으로 해석하지 않는다. 근거: [load_comparison.json](load_comparison.json).

실제 Bridge 프로세스 재시작 후 UUID 변경, `sequence=1`, 네 수신 횟수 0을 확인했다. 지연 응답 중 SIGTERM 종료는 **1.066초**, 종료 코드 0이었다.

## 10분 측정

**600초, 600회 프로세스 표본, 자동 판정 15/15 통과**. 원본 크기 증가, ROS 시계 정지/역행, 카메라/전체 토픽 중단, 503·지연·응답 유실·422, 수신 서버 완전 종료/복구를 포함한다.

| 측정 | 결과 |
|---|---:|
| Bridge CPU 전체 평균 | 18.96% |
| 안정 구간 RSS 최소/최대 | 86.97 / 89.96 MiB |
| 안정 구간 첫/마지막 RSS | 87.11 / 88.52 MiB |
| odom 수신 빈도 평균 | 19.65 Hz |
| lidar_raw 수신 빈도 평균 | 19.77 Hz |
| lidar_filtered 수신 빈도 평균 | 19.79 Hz |
| camera_raw 수신 빈도 평균 | 19.81 Hz |
| 기록된 스냅샷 JSON 최대 | 1,000 B |
| 서버가 반영한 JSON 본문 합계 | 482,813 B |
| 정상 구간 최대 heartbeat 간격 | 1.011초 |
| Ctrl+C 종료 | 0.214초, 종료 코드 0 |

빈도/RSS 안정 구간은 Bridge 시작 280초 이후다. RSS는 범위 내에서 오르내렸고 안정 구간 처음 대비 마지막은 약 1.41 MiB 증가했다. 10분 관측에서 계속 늘어나는 대기열이나 과거 스냅샷 축적은 관찰되지 않았다. 구조상 전송 대기열은 없고 유한 버킷만 보관하며, 테스트도 버킷 상한을 확인한다. 이 결과만으로 무기한 메모리 안정성을 주장하지 않는다.

처음 작은 원본에서 각 LiDAR 1 MiB/이미지 921,600 B로 늘려도 JSON은 8 KiB 미만이었다. ROS 시계 정지/역행에서도 전송이 지속됐다. 카메라만/전체 토픽을 중단했을 때 age 증가와 빈도 0을 확인했다. 수신 서버가 완전히 내려간 동안의 메시지도 누적 횟수에 반영됐고, 복구 후 최근 age를 가진 새 순번의 스냅샷이 도착했다.

근거: [원시 측정](ros_validation.json), [자동 판정 요약](ros_validation_summary.json). JSON 합계는 서버가 반영한 요청 기준으로 실패/거절 요청과 HTTP 헤더는 제외한다. 10분 도구의 초기 baseline은 작은 원본이므로 대용량 실행 전후 비교에는 앞 절의 별도 고정 크기 실험을 사용한다.

## 미검증 항목과 해석 제한

- 기존 Gazebo/LIMBO 센서 발행자의 실제 주기·QoS·부하. 현재 셸의 ROS graph 조회에는 `/parameter_events`, `/rosout`만 있어 테스트 발행자를 사용했다. 다른 도메인의 실행 여부까지 확인한 것은 아니다.
- 실물 로봇, 원격 PC 네트워크 및 장시간 WAN 장애.
- 실제 Dashboard 서버 및 화면의 2초 이내 표시. 이번 구현 범위는 Bridge와 독립 테스트 수신 서버다.
- 10분을 넘어서는 장기 운용, 여러 Bridge의 경쟁. v1의 단일 활성 Bridge 전제를 유지한다.

실제 제어 명령과 Dashboard UI는 구현하지 않았다.
