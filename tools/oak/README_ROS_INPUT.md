# OAK-D Lite FF의 ROS 영상을 Limbo 입력으로 연결하기

이 경로는 OAK-D Lite FF의 RGB·깊이를 기존 `person_detector`가 사용하는 토픽으로 발행한다. 카메라만 실행하며, 사람 검출·모터·Nav2·Gazebo는 시작하지 않는다. 기본 설정은 USB 2, RGB·depth 640×400, 10 Hz다.

현재 Jetson에서는 별도 빌드한 DepthAI SDK 3.6.1·ROS v3 3.2.1 호환 작업공간을 사용한다. 기존 `/opt/ros/jazzy`의 SDK 3.10 조합은 이 카메라에서 스트림 시작 오류가 관찰됐다. 아래 실행 도구는 필요한 overlay가 선택됐는지 확인한다. 환경 설정 없이 드라이버를 직접 실행하면 이전 오류 조합을 선택할 수 있다.

## 빌드

아래 명령은 저장소가 `~/limbo`에 있는 현재 Jetson 환경의 변경분을 다시 빌드하는 절차다. 저장소 위치가 다르면 첫 줄을 바꾼다. ROS Jazzy, 기존 Limbo 의존성·인터페이스, 카메라 호환 작업공간은 이미 준비되어 있어야 한다.

```bash
cd ~/limbo
source /opt/ros/jazzy/setup.bash
source "${LIMBO_OAK_COMPAT_WS:-$HOME/limbo_oak_ros_compat}/install/setup.bash"
cd limbo
colcon build --symlink-install --executor sequential \
  --packages-select limbo_bringup limbo_perception \
  --cmake-args -DBUILD_TESTING=OFF
cd ..
```

`limbo_bringup`은 카메라 launch와 YAML·DDS 설정을 설치하고, `limbo_perception`은 추가 소비자 설정 `person_detector_oak_ros.yaml`을 설치한다. 설정 파일을 추가·변경한 뒤에는 위 두 패키지를 다시 빌드한다.

## 카메라 실행

저장소 루트에서 실행한다. Python 가상환경을 활성화하지 않은 터미널을 사용한다.

```bash
cd ~/limbo
export ROS_DOMAIN_ID=97 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
bash tools/oak/run_ros_input.sh
```

이 도구는 `ros_input_env.sh`를 읽은 뒤 `limbo_bringup/start_oak_camera.launch.py`를 실행한다. 종료는 해당 터미널에서 `Ctrl+C`다. 자동 실행 서비스는 등록하지 않는다.

`ros_input_env.sh`의 기본값은 다음과 같다. 이미 설정한 domain·discovery 값은 유지하므로, 여러 터미널에서 같은 값을 사용해야 한다.

| 항목 | 기본값·동작 |
|---|---|
| ROS domain | `ROS_DOMAIN_ID=97` |
| discovery 범위 | `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST` — 같은 Jetson 안에서 확인 |
| RMW | `rmw_fastrtps_cpp` |
| SHM | 설치된 `limbo_bringup/config/fastdds_camera.xml`의 16 MiB 설정 |
| 호환 작업공간 | `$HOME/limbo_oak_ros_compat`; `LIMBO_OAK_COMPAT_WS`로 변경 가능 |
| Limbo ROS 작업공간 | 저장소 아래 `limbo`; `LIMBO_ROS_WS`로 변경 가능 |
| 카메라 설정 | 설치된 `limbo_bringup/config/oak_usb2_rgbd.yaml` |

Fast DDS 프로파일은 카메라뿐 아니라 영상을 읽는 프로세스에도 필요하다. 새 관찰·소비자 터미널마다 다음을 먼저 실행한다. 실행 중인 ROS 프로세스에는 나중에 설정한 환경 변수가 적용되지 않으므로, 설정 후 다시 시작한다.

```bash
cd ~/limbo
export ROS_DOMAIN_ID=97 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
source tools/oak/ros_input_env.sh
ros2 topic list --no-daemon --spin-time 5
ros2 topic hz /rgbd_camera/image
```

`source` 도중 설정 파일이나 호환 패키지가 없다는 오류가 나오면 그 터미널에서 실행을 계속하지 않고 빌드 경로부터 확인한다. 환경 도구는 `depthai_v3`, `depthai_bridge_v3`, `depthai_ros_driver_v3`가 모두 지정한 호환 작업공간에서 선택되는지 확인한다. 경로를 바꿀 때는 실제 절대 경로를 사용한다.

## 입력 토픽과 메시지

launch 범위에 적용한 remap으로 드라이버가 직접 아래 이름에 발행한다. 별도 영상 relay나 재인코딩은 없다.

| 드라이버 원래 토픽 | Limbo 입력 토픽 | 형식 |
|---|---|---|
| `/oak/rgb/image_raw` | `/rgbd_camera/image` | `sensor_msgs/msg/Image`, `bgr8` |
| `/oak/stereo/image_raw` | `/rgbd_camera/depth_image` | `sensor_msgs/msg/Image`, `16UC1`, mm |
| `/oak/rgb/camera_info` | `/rgbd_camera/camera_info` | RGB `sensor_msgs/msg/CameraInfo` |
| `/oak/stereo/camera_info` | `/rgbd_camera/depth_camera_info` | RGB에 정렬된 depth `sensor_msgs/msg/CameraInfo` |

기존 `person_detector`는 `16UC1`을 확인해 깊이를 한 번만 mm→m로 변환한다. 이 launch에서는 깊이를 미리 미터로 바꾸지 않는다. 예를 들어 원본 1,000은 소비자 내부에서 1.0 m가 된다. 0과 설정한 유효 거리 범위를 벗어난 값은 소비자의 깊이 필터가 처리한다. 숫자 변환 검증과 실제 거리 정확도 검증은 별개다.

원본 픽셀, 촬영 stamp, CameraInfo 보정값, `oak_rgb_camera_optical_frame`을 그대로 보존한다. RGB와 depth의 촬영 stamp는 서로 다를 수 있다. 소비자는 기존 `ApproximateTimeSynchronizer`의 30 ms 허용 범위로 짝을 고른다. 두 CameraInfo를 한 토픽으로 합치거나 RGB·depth stamp를 임의로 같게 만들지 않는다.

이 네 remap은 raw 입력 연결이다. 설치된 image transport 플러그인의 `/compressed` 같은 보조 토픽은 원래 `/oak/...` 이름으로 보일 수 있다.

TF는 `oak_device_frame`을 루트로 하는 카메라 자체 트리만 발행한다. `oak_rgb_camera_optical_frame`을 임의로 `base_link`로 바꾸지 않는다. 로봇에 실제 장착한 위치·각도를 측정해 연결하는 TF와 `odom` 변환은 별도 단계다.

## 기존 OAK 경로와의 구분

기존 `start_simulation.launch.py camera:=oak`는 DepthAI v2의 `oak_camera` 노드가 장치를 직접 열고 카메라 내부 NN 결과 `/oak/detections`도 발행하는 경로다. 이번 ROS v3 카메라 실행과 동시에 사용하면 안 된다. 동일한 장치는 한 드라이버가 사용해야 하며, 같은 `/rgbd_camera/*` 토픽에 여러 공급자를 띄우지 않는다.

이번 v3 카메라 전용 파이프라인은 `/oak/detections`를 발행하지 않는다. 소비자를 `detector.source: oak`로 설정하면 검출 결과를 기다리게 된다. 새 `person_detector_oak_ros.yaml`은 기본 `person_detector.yaml` 뒤에 적용해 `detector.source: yolo`, 실제 카메라 frame, `use_sim_time: false`, GPU 0을 선택한다. 실제 `leg_640.pt`·BoT-SORT 실행과 관찰 절차, 확인한 성능 및 한계는 [README_ROS_YOLO.md](README_ROS_YOLO.md)에 정리되어 있다.

## 실제 소비자의 입력 처리 검증

카메라를 위 명령으로 실행해 둔 상태에서, 별도 터미널에서 다음 명령을 실행한다. 결과 JSON 파일은 아직 존재하지 않는 경로여야 하므로 새 임시 디렉터리를 만든다.

```bash
cd ~/limbo
export ROS_DOMAIN_ID=97 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
source tools/oak/ros_input_env.sh
limbo_perception_share=$(ros2 pkg prefix --share limbo_perception)
limbo_check_dir=$(mktemp -d /tmp/limbo-input-check.XXXXXX)
/usr/bin/python3 tools/oak/verify_ros_input.py \
  --seconds 30 \
  --out "$limbo_check_dir/result.json" \
  --params-file "$limbo_perception_share/config/person_detector.yaml" \
  --params-file "$limbo_perception_share/config/person_detector_oak_ros.yaml"
printf '검증 결과: %s\n' "$limbo_check_dir/result.json"
```

검증 도구는 실제 `PersonDetector` 생성자, 구독, RGB·depth 동기화, CameraInfo 콜백, 영상 변환과 깊이 단위 처리를 실행한다. YOLO 객체만 추론을 하지 않는 빈 결과 모델로 대체한다. 실제 영상 배열이 모델 입력 지점까지 전달되는지 확인하며, 검출 결과를 합성하지 않는다. 소비자 출력은 `/limbo_input_check/*` 아래로 옮겨 구분한다.

실물 장착 TF가 없는 현재 단계에서는 검증 프로세스 안에서 `tf_timeout=0.0`을 사용한다. TF 조회는 실제로 수행하지만, 없는 로봇 변환을 기다리느라 영상 처리가 지연되지 않게 한다. 후속 실제 YOLO 연결에서도 카메라 단독용 `person_detector_oak_ros.yaml`에 같은 값을 명시했다. 일반 기본 설정은 유지하며, 실물 장착 TF와 odom을 연결할 때는 해당 운용 설정을 다시 검토한다.

프로그램 종료 코드 0, JSON의 `status: passed`와 `error_count: 0`을 확인한다. 결과에는 구독·처리 횟수와 속도, 최대 수신 공백, stamp 이상, RGB·depth 시간 차이, 단위 변환, 그래프 검사 결과와 제외 범위가 기록된다. 실패하면 JSON의 `errors`와 실행 로그를 확인한다. 관찰 시간과 통과 기준은 결과 JSON에 함께 남는다.

이 도구 자체는 카메라→Limbo 입력 경로를 검증한다. 후속 실제 YOLO·BoT-SORT 실행 결과는 [README_ROS_YOLO.md](README_ROS_YOLO.md)를 참고한다. 사람 검출 정확도, 물리 RGB-depth 정렬·거리 오차, 실물 장착 TF, 로봇 좌표계 변환, 주행 동작은 별도 검증이 필요하다.
