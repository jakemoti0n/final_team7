# OAK ROS 입력으로 Jetson YOLO 실행하기

이 경로는 OAK-D Lite FF의 실제 RGB·깊이 토픽을 기존 `PersonDetector`에 연결하고, Jetson에서 기존 `leg_640.pt` 모델과 BoT-SORT를 실행한다. 카메라 실행 절차와 토픽 형식은 [README_ROS_INPUT.md](README_ROS_INPUT.md)에 정리되어 있다. 카메라와 검출기만 실행하며 Gazebo·Nav2·모터는 시작하지 않는다.

## 준비된 환경과 기본 설정

2026-10-28 점검에서는 저장소의 기존 `venvs/limbo_yolo`를 사용했다. 패키지를 새로 설치하거나 버전을 바꾸지 않았다. 이 가상환경은 시스템 패키지를 함께 읽도록 준비되어 있으며, ROS Jazzy·cv_bridge와 다음 추론 패키지를 함께 사용한다.

| 항목 | 확인한 값 |
|---|---|
| Python | 3.12.3 |
| PyTorch / torchvision | `2.13.0+cu132` / `0.28.0+cu132` |
| Ultralytics / lap | `8.4.184` / `0.5.13` |
| NumPy / OpenCV | `1.26.4` / `4.10.0` |
| JetPack / CUDA Toolkit | 7.2.1 / 13.2.2 |
| GPU | Orin, compute capability 8.7 |
| 모델 | `limbo_perception/models/leg_640.pt`, `0=person`, `1=leg` |
| 선택 장치 | `yolo.device: "0"` — CUDA GPU 0 |
| 카메라 입력 | USB 2, RGB·depth 640×400, 10 Hz |

모델의 저장소 원본은 `limbo/src/limbo_perception/models/leg_640.pt`다. 상대 모델 경로는 설치된 `limbo_perception` share에서 먼저 찾는다. 기본 `person_detector.yaml` 뒤에 `person_detector_oak_ros.yaml`을 적용해 `detector.source: yolo`, 실제 영상 토픽·optical frame, `use_sim_time: false`, GPU 0을 선택한다.

실물 로봇 TF가 없는 카메라 단독 단계에서는 override에 `tf_timeout: 0.0`을 사용한다. 실제 TF 조회는 수행하지만 없는 변환을 기다리지 않는다. `base_link`·`odom`을 임의로 만들지 않으며, 로봇 장착 후에는 측정한 장착 TF와 실제 odometry를 연결하고 해당 운용 설정을 다시 검토해야 한다.

소스나 설정을 변경했으면 먼저 [입력 README의 빌드 절차](README_ROS_INPUT.md#빌드)로 `limbo_bringup`·`limbo_perception`을 다시 빌드한다. 별도 빌드한 `$HOME/limbo_oak_ros_compat`의 SDK 3.6.1·ROS v3 3.2.1 조합이 필요하다. 환경 도구는 세 DepthAI 패키지의 선택 경로를 검사한다.

## 실행: Jetson 터미널 두 개

아래는 저장소가 `~/limbo`에 있는 경우다. 위치가 다르면 `cd` 경로를 바꾼다. 두 터미널 모두 다른 Python 가상환경을 활성화하지 않은 상태에서 시작한다. 모든 카메라·검출기·관찰 프로세스에 같은 domain과 discovery 값을 적용한다.

첫 번째 터미널에서 카메라를 시작한다.

```bash
cd ~/limbo
export ROS_DOMAIN_ID=97 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
bash tools/oak/run_ros_input.sh
```

두 번째 터미널에서 실제 YOLO 소비자를 시작한다.

```bash
cd ~/limbo
export ROS_DOMAIN_ID=97 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
bash tools/oak/run_ros_yolo.sh
```

`run_ros_yolo.sh`는 `ros_input_env.sh`로 ROS·Limbo·DepthAI 호환 overlay와 Fast DDS 16 MiB SHM 프로파일을 적용한 뒤, `venvs/limbo_yolo/bin/python -m limbo_perception.person_detector`를 실행한다. 가상환경을 따로 활성화할 필요가 없다. 다른 설치 위치를 사용할 때는 `LIMBO_YOLO_PYTHON`에 해당 Python의 절대 경로를 지정할 수 있지만, 그 환경의 ROS·NumPy·cv_bridge 호환성은 따로 확인해야 한다.

실행 도구는 `YOLO_AUTOINSTALL=false`를 설정한다. 추론 중 의존성을 자동 설치해 NumPy 등 기존 패키지가 바뀌는 것을 막기 위한 설정이다. GPU 선택을 바꾸는 ROS 인자는 뒤에 덧붙일 수 있다. 다음 CPU 실행은 선택 방법의 예시이며, 이번 검증에서 CPU 경로의 실행·성능을 확인하지는 않았다.

```bash
bash tools/oak/run_ros_yolo.sh -p yolo.device:=cpu
```

현재 경로와 기존 `start_simulation.launch.py camera:=oak`를 동시에 실행하면 안 된다. 기존 경로는 장치를 직접 여는 DepthAI v2·카메라 내부 NN 경로다. 이번 v3 카메라 전용 드라이버는 `/oak/detections`를 발행하지 않으므로 `detector.source: oak` 소비자는 해당 검출 결과를 기다리게 된다.

종료할 때는 검출기 터미널에서 `Ctrl+C`를 누르고 종료를 기다린 뒤 카메라 터미널에서도 `Ctrl+C`를 누른다. 검출기는 SIGINT·SIGTERM을 받으면 새 spin을 멈추고 실행 중인 executor 작업을 마친 뒤 노드와 ROS context를 정리한다. 이는 추론 콜백이 publish하는 도중 context가 먼저 종료되는 문제를 보완한 것이다. 설치된 Jazzy의 executor는 guard를 파괴한 뒤 worker pool을 기다리는 순서이므로, 마지막 spin 반환 후 내부 pool을 먼저 drain하는 제한된 우회 처리를 추가했다. 마지막 작업의 예외는 수집해 다시 발생시키며 숨기지 않는다. 이 코드는 rclpy 내부 구현에 의존하므로 rclpy 버전을 변경할 때 SIGINT·SIGTERM 종료 검사를 다시 수행해야 한다. 자동 실행 서비스는 등록하지 않는다.

## 출력 확인과 해석

세 번째 관찰 터미널에서도 환경 설정이 필요하다. 특히 Fast DDS SHM 프로파일은 영상을 읽는 프로세스에도 적용되어야 한다. `LOCALHOST`는 같은 Jetson 안의 확인을 위한 설정이며, 다른 PC에서 직접 토픽을 보는 설정은 별도로 구성해야 한다.

```bash
cd ~/limbo
export ROS_DOMAIN_ID=97 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
source tools/oak/ros_input_env.sh
ros2 param get /person_detector yolo.device
ros2 topic hz /person_detector/annotated_image
```

기본 장치 파라미터는 문자열 `0`이어야 한다. 파라미터 값만으로 실제 GPU 연산을 입증하는 것은 아니다. 이번 점검에서는 아래 GPU 증거를 별도로 확인했다.

| 토픽 | 해석 |
|---|---|
| `/person_detector/annotated_image` | 실제 추론·후처리를 거친 `bgr8` 영상. 원본 RGB의 촬영 stamp와 optical frame 유지 |
| `/person_detector/boxes` | JSON 진단. track ID가 붙은 **추적 box**이며 모든 원시 YOLO 후보를 나타내지 않음 |
| `/person_detector/person_position` | geometry 필터 후 채택한 가장 가까운 결과의 `PointStamped`; `oak_rgb_camera_optical_frame` 기준 |
| `/person_detector/person_position_base` | 실제 카메라→`base_link` 변환이 있을 때의 위치 |
| `/person_detector/person_position_odom` | 실제 `odom` 변환이 있을 때의 위치 |

`/boxes`의 `kept` 배열은 person·leg 병합 후의 후보이며 surface·깊이·가장자리·물리 폭 필터를 모두 통과했다는 뜻은 아니다. 채택된 optical 위치와 실제 영상 속 사람을 별도로 확인해야 한다. optical 위치는 기존 모델·깊이·몸체 반경 보정을 적용한 결과이므로, 메시지가 발행된 사실이 거리 정확도 검증을 뜻하지는 않는다.

사람이 없는 장면에서는 주석 영상과 빈 box 진단이 계속 발행되고 optical 위치 메시지는 없을 수 있다. 현재 없는 `odom` 변환 때문에 주석의 `v=0`·`WARMUP`이 기본값에 남을 수 있다. 이를 실제 속도 0 또는 사람이 정지했다는 측정으로 해석하지 않는다. `base_link`·`odom` 위치, 속도·궤적·접근 판단은 이번 카메라 단독 검증의 통과 항목이 아니다.

## 실제 ROS 출력 기록

`observe_ros_yolo.py`는 실제 발행 메시지만 구독한다. 모델을 대체하거나 영상·box·TF를 합성하지 않는다. 카메라와 검출기를 실행해 둔 뒤 세 번째 터미널에서 다음을 실행한다. 기록 디렉터리는 새 경로나 빈 디렉터리여야 한다.

```bash
cd ~/limbo
export ROS_DOMAIN_ID=97 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
source tools/oak/ros_input_env.sh
limbo_yolo_check_dir=$(mktemp -d /tmp/limbo-yolo-check.XXXXXX)
/usr/bin/python3 tools/oak/observe_ros_yolo.py \
  --seconds 60 \
  --out-dir "$limbo_yolo_check_dir" \
  --scene-label "person visible; inspect saved images" \
  --require-detection
printf '관찰 결과: %s\n' "$limbo_yolo_check_dir/summary.json"
```

사람이 실제로 보이는 장면에서 양성 출력을 확인할 때 `--require-detection`을 사용한다. 이 옵션은 optical 결과와 대응 영상 등의 구조를 검사하지만, 사람이 실제로 존재하거나 box가 정확하다는 정답 판정은 하지 않는다. 빈 공간 검사에서는 `--seconds 30`을 사용하고 `--require-detection`을 빼며 장면 설명도 바꾼다.

종료 코드 0, `summary.json`의 `status: completed`와 `error_count: 0`을 확인한다. 이는 관찰 도구의 측정 완료 상태다. 검출 성공 여부는 `counters`, 수신 수·속도·지연, 저장된 원본·주석 PNG 쌍을 함께 보고 판단한다. PNG 쌍은 같은 촬영 stamp로 연결되며 bounded cache에 없는 원본은 누락 사실이 기록된다. 장면 설명은 사람이 입력한 맥락이며 자동 정답 라벨이 아니다.

기존 `verify_ros_input.py`는 YOLO 객체를 추론하지 않는 모델로 대체해 입력 형식만 검사한다. 실제 추론 검증에는 위의 정상 검출기와 읽기 전용 observer를 사용한다.

## 2026-10-28 확인 결과와 남은 범위

| 검사 | 관찰 결과 |
|---|---|
| 사람이 있는 장면, 60초 | RGB·주석 영상·box 진단·optical 위치 각 600개, 주석 영상 약 9.992 Hz, observer 오류 0 |
| 해당 양성 장면 지연 | 촬영→주석 영상 수신 p95 약 0.539초; 카메라·전송·추론·추적·스케줄링 포함 |
| 사람이 없는 장면, 30초 | 주석 영상·box 진단 각 275개, tracked box와 optical 위치 0개, observer 오류 0 |
| 로봇 좌표계 위치 | `base_link`·`odom` 위치 메시지 0개; 실물 TF 미연결 상태 유지 |

양성 장면의 저장 원본·주석 표본에서 실제 사람과 검출 box의 대응을 확인했다. 이는 라벨을 부여한 전체 평가 데이터셋의 정밀도·재현율 검증이 아니다. 음성 장면의 box 0개 결과도 다른 배경·조도·거리에서 오탐이 없다는 뜻은 아니다. 음성 검사의 입력·출력 실제 수신 구간이 달라 입력 286개와 출력 275개 차이를 그대로 유실 프레임으로 계산하지 않는다. 약 10 Hz 출력과 지연 p95 0.539초도 함께 보아야 하며, 로봇 주행에 필요한 지연 기준 통과를 주장하지 않는다.

CUDA 텐서 계산과 torchvision CUDA NMS, 실제 모델 `track()`이 실행됐다. 실제 촬영 영상의 별도 backend 검사에서 predictor와 실제 backend 파라미터가 `cuda:0`, forward 입력이 CUDA 0 FP32 `[1, 3, 416, 640]`임을 확인했다. CUDA event 측정은 약 39.4 ms였다. 처음 로드한 모델 객체의 파라미터가 CPU에 남는 것과 실제 predictor backend의 실행 장치는 구별해야 한다. 개별 CUDA kernel trace는 확보하지 못했으므로, 확인한 연산·모델 범위의 GPU 실행 증거로 기록한다.

설치된 Torch는 Orin SM87을 지원하지 않는 빌드라는 경고를 출력한다. 경고를 숨기지 않았고 해결됐다고 판정하지 않았다. 현재 실제 연산이 통과한 결과를 모든 Torch 연산의 호환성 보증으로 확대하지 않는다. `pip check`의 PyNaCl용 `cffi` 누락과 `nvidia-cusparselt-cu13` 플랫폼 metadata 경고도 미해결 상태다. cuSPARSELt 라이브러리는 실제 프로세스에 로드됐지만 이것만으로 전체 의존성 검사가 통과한 것은 아니다. 이번에는 패키지를 추가 설치하거나 일괄 업그레이드하지 않았다.

실물 장착 TF, 물리 RGB-depth 정렬·거리 정확도, 로봇 좌표계 속도·궤적, 주행·모터 동작은 별도 단계에서 검증한다.

## 2026-10-28 지연 개선 추가 기록

위의 최초 60초 사람 장면 검증 뒤, USB 2·640×400·10 FPS와 모델·의존성·25 W 전력 모드를 유지한 채 입력 처리 대기를 줄였다. 실행 명령은 위와 같다. 카메라 전용 `person_detector_oak_ros.yaml`에 다음 설정을 추가했다.

```yaml
processing:
  latest_only: true
  max_result_age_sec: 0.5
```

`latest_only`는 동기화된 RGB-D 쌍을 하나의 worker에서 순차 처리하고 대기 중인 입력은 최신 한 쌍만 보관한다. 새 쌍이 들어오면 대기 쌍을 통째로 교체하므로 RGB·depth 대응은 유지한다. 처리 중인 쌍은 끝까지 처리한다. 모델을 동시에 여러 worker에서 호출하지 않으며, 모든 촬영 프레임의 처리를 보장하는 방식은 아니다. 공통 기본값은 `false`로 기존 경로를 유지하고 이 OAK 카메라 설정에서만 켠다.

`max_result_age_sec`는 **발행 직전 판단 시점**에 원래 촬영 stamp로부터 지난 시간을 검사한다. 0.5초를 넘긴 결과는 box·예측·접근 진단·optical 위치·주석 영상의 첫 발행 전에 해당 프레임의 출력 전체를 건너뛴다. 0 또는 현재 ROS 시각보다 미래인 stamp도 출력하지 않는다. 추적기는 실제로 처리한 프레임을 이미 반영한 상태로 유지한다. 공통 기본값 `0.0`은 이 촬영 후 경과시간 검사를 끈다.

이 제한은 모델 초기화 시간을 줄이거나 subscriber 수신까지 반드시 0.5초 이하임을 보장하지 않는다. 처음의 긴 모델 준비 도중 처리한 오래된 프레임이 현재 결과처럼 발행되는 일을 막기 위한 설정이다. 기동 중 출력이 잠시 없을 수 있고, 과부하 때도 오래된 프레임 출력은 생략된다. 원래 촬영 stamp를 현재 시각으로 바꾸지 않는다.

### 같은 관찰 방식의 90초 비교

측정 중에는 이미지를 파일로 쓰지 않고 관찰이 끝난 뒤 저장했다. 실제 모델·원래 stamp·관찰 방법을 유지했으며, 아래 변경 후 90초 비교는 **촬영 후 경과시간 제한을 켜기 전** 최신 한 쌍 worker만 적용한 결과다. 늦은 결과를 임계값으로 잘라낸 통계가 아니다.

| 항목 | 변경 전 | worker 변경 후 |
|---|---:|---:|
| optical 위치 수신 / 실제 수신률 | 869개 / 9.91891 Hz | 899개 / 9.98887 Hz |
| 촬영→optical 수신 중앙값 / p95 / 최대 | 507.354 / 609.087 / 642.797 ms | 131.637 / 138.085 / 150.337 ms |
| optical 최대 수신 공백 | 123.872 ms | 202.941 ms |
| RGB 촬영→수신 p95 | 55.538 ms | 54.986 ms |
| observer 오류·stamp 역행·중복·0 값 | 0 | 0 |

두 장면의 카메라 각도와 사람 위치·거리는 달랐으므로 엄격한 동일 장면 A/B나 정확도 비교는 아니다. 프로파일에서 촬영→처리 시작 중앙값/p95가 412.358/510.001 ms에서 57.231/58.728 ms로 줄어 입력 대기 감소를 확인했다. 처리 본체와 YOLO·추적 호출 시간도 달라졌지만 그 차이를 전부 worker 변경의 효과로 해석하지 않는다. 후보 프로세스의 대기 쌍 교체 43회는 모두 첫 모델 처리의 약 4.447초 기동 구간에서 발생했고 정상 90초 비교 구간에는 없었다. 따라서 이번 정상 구간 개선을 프레임을 계속 버려서 얻은 결과로 해석하지 않는다. 입력·출력 구독 시작 시점 차이로 수신 수가 달라질 수 있으며, 수신 수 차이를 그대로 유실 수로 계산하지 않는다.

정상 처리 구간의 약 9.99 Hz와 낮아진 지연은 이 관찰 구간의 결과다. 모든 환경의 지연 상한, 사람 ID 지속성·거리 정확도·전체 검출 정확도, 로봇 주행 성능은 별도 검증이 필요하다. 위의 기존 `observe_ros_yolo.py`는 영상 증거 확인에 사용할 수 있지만 측정 중 파일 저장을 포함하므로 이번 경량 관찰 도구와 동일한 지연 측정 방식은 아니다. 이번 경량 observer와 profiler는 작업 증거에 보관했으며 저장소 실행 경로의 필수 도구로 추가하지 않았다.

### 종료 시 통계 읽기

종료 시 `Latest-frame processing statistics` 로그에서 다음 수치를 확인할 수 있다. 계수는 **그 검출기 프로세스 전체 수명**에 대한 것으로, 특정 관찰 구간의 처리율·유실률과 같지 않다.

| 필드 | 의미 |
|---|---|
| `submitted`, `started`, `processed` | worker가 수락한 쌍, 처리를 시작한 쌍, 콜백이 오류 없이 반환한 쌍 |
| `overwritten` | 새 입력 때문에 처리 전 대기 쌍이 교체된 횟수 |
| `output_frames` | 촬영 후 경과시간 검사를 통과해 해당 프레임 출력 경로를 완료한 횟수; optical 위치 개수와는 다름 |
| `stale_result_dropped`, `invalid_timestamp_dropped` | 오래된 결과 또는 0·미래 stamp로 출력 전체를 생략한 횟수 |
| `shutdown_dropped`, `failure_dropped`, `rejected_after_stop` | 종료·오류 때 버린 대기 쌍 또는 중지 뒤 거절된 입력 |
| `failed`, `pending`, `active` | worker 오류 횟수, 아직 대기 중인 쌍, 처리 중인 쌍 |

`processed`에는 오래되어 출력하지 않은 프레임이나 calibration 준비 전 반환한 프레임도 포함될 수 있다. 따라서 `processed`와 `output_frames`가 반드시 같지는 않다. 사람이 없는 장면은 출력된 주석 영상·빈 box와 optical 0개가 함께 나올 수 있다.

종료 요청을 받으면 새 처리 수락을 멈추고 대기 쌍을 버린 뒤 진행 중인 worker를 기다린다. worker 예외는 제어 스레드로 전달하며, ROS publisher·context를 살아 있게 유지한 상태에서 처리 종료를 마친다. 이후 기존 executor/node/context 정리 순서를 따른다. 카메라 단독 실제 production 진입점의 cold start와 SIGINT·SIGTERM 검사에서 각각 첫 오래된 결과 한 개를 차단했고 종료 코드 0을 확인했다. 당시 빈 장면이었으므로 해당 검사는 사람 위치 발행 성공을 의미하지 않는다. 카메라·rclpy·PyTorch 환경을 갱신할 때 입력·지연·종료 검사를 다시 수행한다.

최종 카메라 설정(`latest_only=true`, `max_result_age_sec=0.5`)을 켠 정상 production 진입점에서도 실제 사람이 보이는 cold start를 별도로 확인했다. 35초 관찰 중 첫 optical 출력은 관찰 시작 약 14.180초 후였고, 이후 실제 수신 구간 20.775초에서 optical 209개·10.01220 Hz를 받았다. 촬영→optical 수신 중앙값/p95/최대는 130.064/134.041/152.731 ms, 최대 수신 공백은 110.462 ms였다. 같은 stamp의 원본·주석 표본에서 실제 전경 사람과 box 대응을 확인했다. 프로세스 전체 처리 221쌍 중 첫 오래된 결과 1개를 차단하고 220프레임 출력 경로를 완료했으며, SIGINT 종료 코드 0을 확인했다. 14초가량의 초기 출력 대기 자체는 남아 있으므로 이 변경을 즉시 기동하는 기능으로 해석하지 않는다. 이 결과도 전체 정확도·거리 정확도 평가를 대신하지 않는다.

## 2026-10-28 Torch·의존성 경고 영향 점검

지연 개선 이후 남은 세 경고를 별도로 점검했다. 실제 변경은 YOLO 가상환경에 `cffi==2.0.0`, `pycparser==2.23`을 추가한 것이다. Torch 2.13.0+cu132·torchvision 0.28.0+cu132·NumPy 1.26.4·Ultralytics·cuSPARSELt·모델·카메라 설정은 유지했다.

| 항목 | 확인 결과와 조치 |
|---|---|
| PyNaCl의 cffi 누락 | 변경 전 `import cffi`가 실제 실패했다. PyNaCl 서명·검증 자체는 이미 통과했으므로 기존 YOLO 장애 원인으로 단정하지 않는다. cffi·pycparser 추가 후 import·FFI 메모리 할당·정상/변조 서명 검사를 통과했다. |
| Torch의 Orin SM87 미지원 경고 | 설치된 진단 코드는 CUDA 13.2에서 SBSA 바이너리를 Jetson에 사용할 수 있다는 규칙을 반영하지 않는다. [공식 수정 4a2074d](https://github.com/pytorch/pytorch/commit/4a2074d6edfcbb359c0590af70897440529f327a)과 설치 파일을 대조했다. 대표 CUDA 연산과 실제 저장 영상 추론이 통과해 현재 사용 경로의 실행 실패는 확인되지 않았다. 경고를 숨기거나 설치 코드를 변경하지 않았다. |
| cuSPARSELt 0.8.1 플랫폼 경고 | 공식 wheel 내부 태그가 `manylinux2014_sbsa`여서 pip 지원 태그와 맞지 않는다. 수정된 공식 0.8.1.post1은 현재 Torch의 정확한 `==0.8.1` 의존성 조건에 맞지 않아 설치하지 않았다. 설치 라이브러리의 실제 SHA256은 원본·post1의 공식 RECORD에 기재된 값과 같았다. sparse 연산 전체를 검증한 것은 아니다. |

따라서 현재 `pip check`에는 **cuSPARSELt 플랫폼 경고 1건이 남고 exit 1**이다. 이는 의존성 검사가 깨끗하게 통과한 상태가 아니다. Torch의 GPU 경고도 계속 표시된다. 두 경고의 원인과 실제 검사 통과 범위를 구분하며, 경고 필터나 패키지 metadata 수동 수정으로 감추지 않는다. 후속 Torch 계열 업그레이드 시에는 torchvision·CUDA 라이브러리 의존성을 함께 맞추고 실제 카메라 회귀 검사를 다시 수행한다. 공식 2.14 계열 소스의 진단 수정 포함 여부는 확인했지만 그 버전을 이 Jetson에 설치·검증하지 않았다.

동일 환경에 이번 누락 의존성만 재현하려면 다음을 사용한다. 전체 YOLO 환경을 새로 구축하는 명령은 아니다.

```bash
cd ~/limbo
venvs/limbo_yolo/bin/python -m pip install 'cffi==2.0.0' 'pycparser==2.23'
venvs/limbo_yolo/bin/python -m pip check
```

이번 설치는 다운로드한 ARM64 wheel과 순수 Python wheel의 해시·설치 보고서를 보관하고 해당 로컬 wheel로 수행했다. 추가된 두 패키지만 변경 전 상태로 되돌려야 한다면 YOLO 프로세스 종료 후 `venvs/limbo_yolo/bin/python -m pip uninstall cffi pycparser`를 사용할 수 있다. 이 경우 원래의 cffi 누락 상태가 다시 생긴다. 시스템 Python 패키지는 변경하지 않았다.

변경 전후 모두 대표 FP32 CPU/GPU 계산 비교, torchvision CUDA NMS, 실제 저장된 사람 영상의 YOLO·BoT-SORT, cv_bridge 색·깊이 변환을 확인했다. `CUDA_DISABLE_PTX_JIT=1`을 Python 시작 전에 설정한 별도 프로세스에서도 같은 사용 경로가 통과했다. 이는 검사한 경로가 드라이버 PTX JIT 비활성 상태에서 실행됐다는 뜻이며, 모든 Torch 연산이나 모든 종류의 런타임 컴파일을 검증한 것은 아니다. 같은 저장 영상의 네 호출에 대한 box 데이터는 변경 전후 정확히 같았다. 이 시험은 계산 확인용으로 TF32를 끈 별도 프로세스이며 production 지연 비교나 전체 정확도 평가가 아니다.

최종 실제 카메라 45초 관찰에서 optical 위치 308개·약 10.0185 Hz, 촬영→수신 지연 중앙값 133.786 ms·p95 145.156 ms·최대 183.553 ms를 확인했다. 첫 출력 대기 약 14.318초는 남았다. 동일 stamp의 실제 사람 원본·주석 표본을 확인했고 observer 오류·stamp 역행·중복·0 값은 없었다. SIGINT 정상 종료와 별도 재시작 후 SIGTERM 정상 종료가 모두 exit 0으로 통과했다. 두 기동에서 오래된 첫 결과를 각각 1개 차단했다. USB 2·640×400·10 FPS와 기존 지연 개선 설정을 유지했다. 다른 장면의 이전 측정과 엄격한 성능 A/B로 비교하지 않는다.

카메라 optical 좌표 출력까지의 검사이며 실제 장착 TF·거리 정확도·주행 성능은 별도 범위다. 이번 증거와 세부 명령은 `~/limbo_package_audit_20261028` 및 함께 전달한 보고서 §15에 보존했다.

