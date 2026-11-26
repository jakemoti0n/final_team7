# Limbo 실물 로봇 초기 구축 및 첫 주행 공정

작성일: 2026-10-20 · 상태: 실행 계획 (실물에서 아직 검증하지 않음)

이 문서는 시뮬레이션에서 주행한 Limbo를 **Jetson Orin Nano Super 개발자 키트 + Livox MID-360S + Luxonis OAK-D Lite FF + RoboClaw 기반 2WD**로 옮기는 순서다. 실제 TF의 프레임 배치는 Gazebo와 동일하다는 전제를 사용한다. ToF 센서는 첫 주행에서 제외한다. 케이블의 핀 연결과 전원 분배는 하드웨어 담당자가 실물 부품의 정격과 커넥터를 확인해 확정한다.

> **보드 구분(2026-11-24 추가):** 이 문서의 1~2절과 참고 자료는 **Nano(원래 보드, Jetson Orin Nano Super 개발자 키트)** 기준으로 쓴 것이다. 2026-11-20부터 로봇에는 **NX(대여 보드, Jetson Orin NX 16 GB + Seeed reComputer J401 캐리어)**가 달려 있고, 실제로 세팅된 내용은 아래 "Orin NX(Seeed J401) 보드 세팅 기록" 절에 있다. Nano로 돌아가면 1~2절을 따른다.

> **현재 저장소에는 실물 RoboClaw 구동/엔코더 드라이버와 실물 전용 통합 launch가 없다.** 아래 명령을 모두 실행한다고 바로 주행하는 상태는 아니다. 7단계의 구현이 완료되어야 한다.

## 전체 순서와 통과 기준

| 순서 | 작업 | 다음 단계로 넘어갈 기준 |
| --- | --- | --- |
| 0 | 장비와 파라미터 기록 | 보드/저장장치/전원/모터/엔코더/센서 모델과 연결 방식 확인 |
| 1 | Jetson 펌웨어와 Ubuntu 설치 | Ubuntu 24.04, aarch64, JetPack/L4T 버전 확인 |
| 2 | ROS Jazzy와 Limbo 빌드 | Jetson에서 필요한 ROS 패키지와 자체 패키지가 빌드됨 |
| 3 | 전원·USB·Ethernet 연결 | 각 장치를 단독으로 켜고 Jetson에서 인식 확인 |
| 4 | RoboClaw 저속 단독 시험 | 바퀴를 띄운 상태에서 방향·엔코더·정지 동작 확인 |
| 5 | MID-360S 단독 시험 | 실제 PointCloud2가 수신되고 프레임·시간 확인 |
| 6 | OAK 단독 시험 | 영상·정렬된 깊이·CameraInfo·포인트클라우드 확인 |
| 7 | Limbo의 실물용 인터페이스 구현 | `/cmd_vel`→모터, 엔코더→`/odom`, 센서→기존 주행 입력 연결 |
| 8 | TF·시간·지도·Nav2 통합 | 각 데이터의 frame/stamp와 위치 추정 확인 |
| 9 | 제한된 공간에서 첫 주행 | 저속 수동 전진/회전, 정지, 자율 목표 순으로 통과 |

각 단계의 **통과 기준을 충족하기 전에는 다음 단계의 모터 구동을 하지 않는다.** 첫 주행에는 사람이 즉시 누를 수 있는 물리적 비상정지가 필요하다.

## 0. 먼저 기록할 값

아래 표를 팀 공유 문서에 실제 값으로 채운다. 값이 없으면 소프트웨어 파라미터를 확정할 수 없다.

| 항목 | 기록할 실제 값과 이유 |
| --- | --- |
| Jetson | 개발자 키트/캐리어 보드 모델, 저장장치(microSD 또는 NVMe), 전원 어댑터, 펌웨어·JetPack 버전. 설치 이미지와 핀/전원 조건이 달라진다. |
| LiDAR | MID-360S 시리얼 번호, 본체 IP, Jetson Ethernet 포트, 센서 전원·케이블. 정적 IP와 드라이버 설정에 필요하다. |
| 카메라 | OAK-D Lite FF 정확한 모델, USB 케이블/포트, 장착 방향과 실측 위치. 영상/깊이 프레임 검증에 필요하다. |
| 구동부 | RoboClaw 정확한 모델, 펌웨어, USB 포트, 모터 M1/M2와 좌우 대응, 엔코더 채널과 방향. 잘못 매핑하면 회전 방향이 뒤집힌다. |
| 차체 | 실제 바퀴 반지름, 좌우 바퀴 중심 간 거리, 감속비, 바퀴 1회전당 엔코더 카운트. `/cmd_vel` 변환과 `/odom` 계산에 필요하다. |
| 전원 | 배터리/BMS, 모터 컨트롤러 입력 전압, Jetson용 안정화 전원, LiDAR 전원, 퓨즈 및 물리적 비상정지 회로. 정격은 부품 실물 설명서로 확인한다. |
| ROS 네트워크 | Jetson 호스트명/IP, 개발 PC IP, `ROS_DOMAIN_ID`, 사용할 유선/무선 인터페이스. 원격 관찰과 DDS 통신에 필요하다. |

Gazebo의 TF 프레임 구조가 같아도 **실제 장착 위치·바퀴 치수·엔코더 분해능이 같은지는 별도 확인**한다. TF의 수치가 다르면 URDF를 실측값으로 갱신한다.

## 1. Jetson 펌웨어와 OS 설치

> Nano(원래 보드) 기준 절차다. NX(대여 보드, 2026-11-20~)는 2절 뒤 "Orin NX(Seeed J401) 보드 세팅 기록"을 본다.

1. 보드와 저장장치 모델을 확인한다. NVIDIA 공식 [Orin Nano 개발자 키트 빠른 시작](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/quick_start.html)의 해당 절차를 따른다. 현재 공식 절차는 **JetPack 7.2.1의 Ubuntu 24.04 기반 이미지**와 USB 설치 매체를 설명한다. ISO 파일을 목표 microSD에 그대로 굽는 절차가 아니다. 이미지 버전은 설치 당일 공식 페이지에서 다시 확인한다.
2. 새 보드의 UEFI/QSPI 펌웨어가 해당 이미지의 최소 버전을 만족하는지 확인한다. 구형 펌웨어라면 공식 [펌웨어 갱신 절차](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/update_firmware.html)를 먼저 따른다. 설치 과정은 목표 저장장치의 데이터를 지우므로 저장장치를 정확히 식별한다.
3. 설치 후 Jetson 터미널에서 확인한다.

```bash
uname -m                 # aarch64 예상
lsb_release -rs          # 24.04 예상
cat /etc/nv_tegra_release
uname -r
df -h
```

4. NVIDIA 저장소와 드라이버가 잡혔는지 확인하고, 공식 [JetPack 설정 안내](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/setup_jetpack.html)에 따라 필요한 SDK를 설치한다.

```bash
sudo apt update
sudo apt install nvidia-jetpack
```

**왜:** ROS Jazzy의 공식 Ubuntu 패키지와 현재 Limbo의 기준 환경을 맞추고, Jetson GPU/카메라 사용자 공간 라이브러리의 버전을 OS와 일치시킨다. 일반 PC의 Ubuntu 24.04 ISO를 Jetson에 직접 설치하는 방식으로 진행하지 않는다.

## 2. ROS Jazzy와 Limbo를 Jetson에서 빌드

1. [ROS 2 Jazzy Ubuntu 설치 지침](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html)에 따라 **Ubuntu Noble arm64용 ROS 저장소와 `ros-jazzy-ros-base` 또는 `ros-jazzy-desktop`**을 설치한다. 설치 페이지의 저장소 설정 명령은 최신 공식 지침을 그대로 따른다. 첫 확인:

```bash
source /opt/ros/jazzy/setup.bash
ros2 --help
printenv ROS_DISTRO
```

2. 저장소를 Jetson에 받고, 서브모듈을 포함해 소스를 준비한다. 이미 복사된 저장소가 있다면 그 저장소에서 동일하게 진행한다.

```bash
git clone --recurse-submodules https://github.com/jakemoti0n/final_team7.git ~/limbo
cd ~/limbo/limbo
```

3. `rosdep`으로 ROS/시스템 의존성을 확인하고 빌드한다. Jetson의 메모리에 맞춰 처음에는 순차 빌드한다.

```bash
sudo rosdep init                    # 최초 설치 시 한 번만; 이미 초기화됐다면 생략
rosdep update
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install --executor sequential
source install/setup.bash
ros2 pkg list | grep '^limbo_'
```

실패한 패키지는 에러와 의존성 이름을 기록해 해결한다. x86 PC의 `build/`, `install/`, Python 가상환경을 Jetson에 복사하지 않는다. Python wheel, C++ 바이너리, 네이티브 라이브러리는 **aarch64용으로 다시 설치/빌드**해야 한다.

4. 사람 검출용 PyTorch/torchvision/Ultralytics는 별도 검증한다. 저장소 최상위 `requirements.txt`는 CPU PyTorch 인덱스를 사용하고, `limbo/requirements.txt`는 PC 전체 환경을 담은 긴 freeze 파일이므로 Jetson에 그대로 설치하지 않는다. 설치한 JetPack 버전에 맞는 [NVIDIA Jetson PyTorch 설치 안내](https://docs.nvidia.com/deeplearning/frameworks/install-pytorch-jetson-platform/index.html)와 [호환성 표](https://docs.nvidia.com/deeplearning/frameworks/install-pytorch-jetson-platform-release-notes/pytorch-jetson-rel.html)를 확인한다. 해당 버전에서 제공되는 패키지/컨테이너 경로를 선택한 뒤 **`import torch`, `torch.cuda.is_available()`, 실제 YOLO 모델의 이미지 1장 추론**을 확인한다. GPU 설치가 바로 되지 않더라도 모터·LiDAR·카메라 기본 통합은 독립적으로 진행할 수 있다.

**왜:** 시뮬레이션 알고리즘은 ROS 메시지 인터페이스에 의존하지만, 드라이버와 Python/C++ 바이너리는 Jetson CPU 아키텍처·JetPack 버전에 의존한다.

## Orin NX(Seeed J401) 보드 세팅 기록 — 2026-11-20 팀원 세팅, 11-24 확인

팀원이 2026-11-19~20에 세팅하고 기록을 남기지 않아, 2026-11-24에 SSH로 보드 상태(apt 이력, 셸 이력, 설정 파일, systemd 유닛)를 읽어 재구성했다. 이력에 없는 것은 "(확인 필요)"로 둔다.

### 보드와 OS

| 항목 | 값 |
| --- | --- |
| 모듈 | `/proc/device-tree/model` = `NVIDIA Jetson Orin NX Engineering Reference Developer Kit Super`, 메모리 15 GB, CPU 8코어 |
| 캐리어 | Seeed reComputer J401 (팀 확인) |
| OS | `/etc/nv_tegra_release` R39 REVISION 2.0 (JetPack 7.2), Ubuntu 24.04.5, 커널 `6.8.12-1021-tegra` |
| 호스트명·사용자 | `automaton-jetson`, `automaton` (비밀번호는 팀 내 구두 전달) |
| 저장장치 | NVMe 128 GB (FORESEE XP1000F128G). 루트 79 GB 중 50 GB 사용, 26 GB 여유(11-24). rosbag을 오래 쌓으면 금방 찬다 |
| 전원 모드 | 현재 `nvpmodel` 40W. **J401에서는 MAXN SUPER 금지**(Seeed 안내: 캐리어 방열 부족) |

### 실제 수행된 설치 순서

apt 이력(`/var/log/apt/history.log`, 11-16 이후)과 팀원 셸 이력에서 재구성했다. 시각은 apt 이력 기준이다.

1. **11-19 17:36~17:44** `curl`, `docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin` 설치, `apt upgrade`. Docker를 어디에 쓰는지는 기록이 없다(확인 필요). 11-24에 돌고 있는 컨테이너는 없었다.
2. 저장소 받기: `git clone https://github.com/jakemoti0n/final_team7.git ~/limbo` (브랜치 jetson).
3. **ROS apt source**: 로케일 `en_US.UTF-8` 설정 → `software-properties-common`, `add-apt-repository universe` → `ros2-apt-source` deb(최신 릴리스)를 받아 `dpkg -i` → `apt full-upgrade`. ROS 2 Jazzy 공식 설치 지침과 같은 절차.
4. **11-20 09:47** `ros-dev-tools`, **09:49** `ros-jazzy-desktop`.
5. **11-20 09:56 Nav2 묶음**: `ros-jazzy-navigation2 ros-jazzy-nav2-bringup ros-jazzy-ros-gz ros-jazzy-cv-bridge ros-jazzy-pcl-ros ros-jazzy-pointcloud-to-laserscan ros-jazzy-spatio-temporal-voxel-layer ros-jazzy-slam-toolbox ros-jazzy-robot-localization ros-jazzy-vision-msgs ros-dev-tools python3-venv`. `ros-jazzy-nav2-mppi-controller`도 설치돼 있음(11-24 확인).
6. **venv `limbo_yolo`**(YOLO용):
   ```bash
   python3 -m venv --system-site-packages ~/limbo/venvs/limbo_yolo
   source ~/limbo/venvs/limbo_yolo/bin/activate
   # 최상위 requirements.txt의 CPU torch 인덱스 줄(--extra-index-url)만 빼고 설치
   grep -v -- '--extra-index-url' ~/limbo/requirements.txt > /tmp/limbo_req_gpu.txt && pip install -r /tmp/limbo_req_gpu.txt
   # JetPack 7.2(CUDA 13.2)용 GPU torch로 다시 설치
   python -m pip install --force-reinstall "torch==2.12.0+cu132" "torchvision==0.27.0+cu132" --index-url https://download.pytorch.org/whl/cu132
   python -m pip install cffi
   python -m pip install "scipy==1.16.3"
   ```
   이력상 맨 처음에는 `pip install -r ~/limbo/requirements.txt`(CPU torch)로 한 번 설치했다가 위처럼 바꿨다. 그 뒤 `torch.cuda.is_available()`, GPU 행렬곱·Conv2d, `human-leg/runs/person_leg_stage1/weights/best.pt`로 `device="cuda:0"` YOLO 추론을 확인하는 명령이 이력에 있다(출력은 남아 있지 않음). 11-24 venv 패키지: `torch 2.12.0+cu132`, `torchvision 0.27.0+cu132`, `ultralytics 8.4.158`, `depthai 2.34.0.0`, `numpy 1.26.4`, `opencv-python 4.10.0.84`. 시스템 `python3`에는 depthai가 없다. 이 venv의 depthai가 실제로 쓰이는지는 확인 필요.
   `~/.bashrc`의 `goyolo`·`limbo`·`build_limbo` 별칭으로 빌드했다(`build_limbo` = `python -m colcon build --symlink-install`, `~/limbo/limbo`에서). `~/limbo/limbo/install` 빌드 완료.
7. **11-20 12:47** `ros-jazzy-camera-info-manager ros-jazzy-image-pipeline ros-jazzy-ffmpeg-image-transport-msgs`.
8. **Livox 드라이버**: `~/livox_ws`에 `Livox-SDK/livox_ros_driver2` 커밋 `2144554`("Support Mid360L Lidar"). 빌드 명령은 이력에 없다(확인 필요). `~/livox_ws` 안 설정 JSON의 호스트 IP는 `192.168.1.5`지만, 실제 런치(`start_mid360.launch.py`)는 저장소의 `limbo_bringup/config/MID360s_limbo.json`(호스트 `192.168.1.50`)을 쓴다.
9. **OAK udev**: `/etc/udev/rules.d/80-limbo-oak.rules`
   ```
   SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTR{idVendor}=="03e7", GROUP="plugdev", MODE="0660"
   ```
   만든 명령은 이력에 없다. 부팅 스크립트가 쓰는 `~/limbo_oak_ros_compat`(DepthAI ROS v3 overlay)와 `~/limbo_stvl_compat`(STVL overlay)도 있어야 도는데, 만든 과정은 이력에 없다(확인 필요). 만드는 법은 `tools/oak/README_ROS_INPUT.md`, `tools/stvl/build_stvl_compat.sh`.
10. **openssh-server**: `sudo apt install openssh-server` → `ssh-copy-id`. apt 이력(11-16 이후)에는 이 설치가 없다(이미 깔려 있었는지 확인 필요).
11. **relay(관제 다리) venv·빌드**: 이력에는 `venvs/bridge` venv를 만들고 `relay_prog`에서 `colcon build --symlink-install --base-paths src`를 한 기록이 있다. 실제 부팅 스크립트는 `~/limbo/venvs/limbo_relay`를 쓴다. 두 venv의 관계는 확인 필요. 로봇 토큰은 `~/.config/limbo/robot_token`(권한 600)에 저장(값은 문서에 적지 않음). **11-20 15:43** `nano`.

`/etc/sysctl.d/60-limbo-dds.conf`는 없다.

### 네트워크

| 인터페이스 | 주소 | 용도 |
| --- | --- | --- |
| `wlP1p1s0` (Wi-Fi) | `192.168.20.18/23`, SSID `aischool class02(5Ghz)` | SSH 접속(`ssh automaton@192.168.20.18`), 관제 서버 |
| `enP8p1s0` (유선) | `192.168.1.50/24` | MID-360S 전용 |
| `l4tbr0` | `192.168.55.1` | USB 장치 모드, 안 씀 |
| `docker0` | — | Docker 기본 브리지 |

Nano(원래 보드)의 Wi-Fi 주소는 `192.168.20.210`이었다(`docs/REAL_PATROL_RUN.md`).

### USB 장치 (11-24 확인)

- RoboClaw 2x15A: `03eb:2404`, `/dev/serial/by-id/usb-Basicmicro_Inc._USB_Roboclaw_2x15A-if00 -> ttyACM0`, 드라이버 `cdc_acm`, 커널 USB 오류 없음. 부팅 서비스의 `roboclaw_drive` 노드가 포트를 잡고 있다.
- OAK: `03e7:f63b`. VIA Labs USB 2.0/3.1 허브가 보드에 내장.

### ModemManager 끔 (2026-11-24, PM 승인)

```bash
sudo systemctl disable --now ModemManager
```

ModemManager는 USB 시리얼 장치(RoboClaw는 `ID_MM_CANDIDATE=1`)를 모뎀인지 열어 본다. 이 동작이 RoboClaw 포트를 잠깐 점유하거나 잡음을 넣을 위험이 있어 껐다. 끈 뒤 RoboClaw 포트와 네트워크에 변화가 없음을 확인했다. 보드를 다시 만들면 이 명령을 다시 친다.

### 부팅 자동 기동(사용자 systemd 유닛 5개)

> **이 파일들의 원본은 저장소 `tools/nx_boot/`에 있고(2026-11-24, PM 승인), 설치는 `bash tools/nx_boot/install.sh`로 한다**(아래 "설치·확인·제거"). 실행 위치는 그대로 홈 아래이고, 설치 스크립트가 그 자리에 저장소 파일을 가리키는 심볼릭 링크를 만든다.
> - 유닛: `~/.config/systemd/user/limbo-nx-{drive,sensors,pose,navigation,dashboard}.service` → 저장소 `tools/nx_boot/systemd/`
> - 스크립트: `~/.config/limbo/boot/start`, `ready.py`, `corridor_pose.py`, `map_search.py` → 저장소 `tools/nx_boot/boot/`. 이전판(`start.bak_1120`, `corridor_pose.pre_global.py`, `corridor_pose.before_idle_relocation.py`)은 저장소에 넣지 않았고 NX 보드에만 있다
> - 관제 설정: `~/.config/limbo/bridge-nx.yaml`(예시 `tools/nx_boot/bridge-nx.example.yaml`에서 복사해 보드마다 고치는 파일), 토큰 `~/.config/limbo/robot_token`(git에 넣지 않음)
> - 상태 파일: `~/.local/state/limbo/`(저장소에 넣지 않음)
>
> `start`와 pose 유닛은 저장소가 `~/limbo`에 있다고 가정한다(`cd "$HOME/limbo"`, `WorkingDirectory=%h/limbo`).

사용자 단위(`systemctl --user`)이고 `loginctl` Linger=yes라 아무도 로그인하지 않아도 부팅 때 뜬다(11-20 17:52 부팅 로그에 5개 모두 Started). Nano에서 쓰던 시스템 단위 `limbo-real.service`는 NX에 없다. 모든 유닛은 `WantedBy=default.target`이고 **유닛끼리 `After=`/`Requires=` 의존은 없다.** 순서는 각 스크립트가 조건을 기다리는 방식으로 맞춘다. `start`는 공통으로 `cd ~/limbo`, `ROS_DOMAIN_ID=97 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`, `source tools/oak/ros_input_env.sh`(ROS·Limbo·OAK overlay를 source하고 Fast DDS 프로파일 지정)를 한 뒤 인자별로 갈린다.

| 유닛 | 하는 일 | 시작 전에 기다리는 조건(스크립트 그대로) |
| --- | --- | --- |
| `limbo-nx-drive` | `start drive` → `tools/drive/run_teleop.sh`: `teleop_drive.launch.py`(`roboclaw_drive` /cmd_vel→모터, `wheel_odometry` /odom·TF) | `until [[ -r "$port" && -w "$port" ]]; do sleep 2; done` (`$port` = `/dev/serial/by-id/usb-Basicmicro_Inc._USB_Roboclaw_2x15A-if00`) |
| `limbo-nx-sensors` | `start sensors` → `tools/drive/run_real.sh encoder_source:=external localization:=amcl map:=…/real_open_space_20261111.yaml`: `start_real.launch.py`(라이다·OAK·YOLO·AMCL·지도. 모터 출력 없음). `yolo`는 기본값(true) | `until ip -4 -o addr show dev enP8p1s0 \| grep -q '192\.168\.1\.50/' && lsusb -d 03e7: \| grep -q .; do sleep 2; done` (유선 IP + OAK USB) |
| `limbo-nx-pose` | `corridor_pose.py`: 정지 상태에서 스캔을 지도 전체와 맞춰 `/initialpose`를 보내고, 위치가 잡힌 뒤에는 검증된 위치를 1초마다 `corridor-pose.json`에 씀 | 없음(`/map`·`/scan`·`/odom`이 올 때까지 안에서 기다림) |
| `limbo-nx-navigation` | `start navigation` → `ready.py`로 기다린 뒤 `tools/drive/run_nav2_real.sh cmd_vel_out:=/cmd_vel`(`start_nav2_real.launch.py`, 기본 `nav2_real.yaml`) | `ready.py`: TF `map→base_footprint`의 나이가 −1.5~1.0 s **그리고** `corridor-pose.json`의 `time`이 지금부터 5초 이내이고 `boot`가 이번 부팅 id와 같을 때 |
| `limbo-nx-dashboard` | `start dashboard` → `relay_prog/install/local_setup.bash` source 후 `venvs/limbo_relay/bin/python -m limbo_telemetry_bridge.node --config ~/.config/limbo/bridge-nx.yaml`(관제 서버로 상태 전송, 관제 명령 받기) | 없음 |

이어지는 순서:

1. 전원이 들어오면 drive(RoboClaw 포트가 생기면)와 sensors(유선 IP와 OAK가 보이면)가 뜬다. dashboard와 pose도 같이 뜬다.
2. AMCL은 `/initialpose`를 받기 전에는 `map→odom`을 내지 않는다. pose(`corridor_pose.py`)가 지도·스캔·odom을 받은 뒤, **로봇이 3초 넘게 멈춰 있고** `/patrol/state` 발행자도 진행 중인 Nav2 목표도 없을 때 지도 전체 탐색(`map_search.py`)을 한다. 후보의 스캔 일치율이 0.85 이상이고 두 번째 후보보다 0.08 이상 높아야 하며, 이어지는 스캔 5개가 모두 0.85 이상이면 `/initialpose`를 보낸다. 실패하면 3초 뒤 다시 찾는다.
3. AMCL이 위치를 잡으면 pose가 일치율 0.80 이상일 때 `corridor-pose.json`을 1초마다 쓴다.
4. navigation의 `ready.py`가 이 파일(5초 이내, 같은 부팅)과 신선한 TF를 보고 빠지면 Nav2가 뜬다.
5. 위치가 잡힌 뒤에도 멈춰 있는 동안 일치율 0.80 미만이 스캔 6번 이어지면 pose가 다시 전역 탐색해 `/initialpose`를 보낸다(현재판의 "멈춰 있을 때 재위치" 기능. 이전판 두 개에는 없음).

상태 파일(`~/.local/state/limbo/`):
- `corridor-pose.json`: `boot`(부팅 id), `map`(지도 해시), `pose`([x, y, yaw]), `fit`(일치율, 11-24에 0.848), `time`.
- `patrol-progress.json`: 관제에서 시작한 순찰이 다음에 갈 경유점 번호. 저장소의 **미커밋** 변경(`limbo_patrol/corridor_checkpoint.py`, `patrol_node.py`)이 쓴다. 저장소에 반영할지는 PM 결정 대기.
- `map-backups/`: `real_open_space_20261111-8c197ad0.pgm`(11-20 09:24). 누가 무엇으로 만들었는지 확인 필요.

보는 법(젯슨 안에서):

```bash
systemctl --user status 'limbo-nx-*'            # 5개 상태
journalctl --user -u limbo-nx-sensors -f        # 한 유닛 로그 따라 보기 (drive·pose·navigation·dashboard도 같은 방식)
cat ~/.local/state/limbo/corridor-pose.json     # 마지막 검증 위치와 일치율
```

멈추는 법:

```bash
systemctl --user stop limbo-nx-navigation limbo-nx-sensors limbo-nx-drive limbo-nx-pose limbo-nx-dashboard
```

drive·sensors·navigation·dashboard는 `KillSignal=SIGINT`, `TimeoutStopSec=25`라 런치가 SIGINT로 정리된다. pose 유닛은 `KillSignal`을 정하지 않아 systemd 기본값(SIGTERM)으로 끝난다. 패턴 kill(`pkill -f` 등)은 쓰지 않는다. 다섯 개 모두 `Restart=on-failure`(pose 5초, 나머지 8초 뒤, drive·sensors·navigation·dashboard는 `StartLimitIntervalSec=0`이라 횟수 제한 없음)라 실패하면 다시 뜨지만, `stop`으로 내린 것은 다시 뜨지 않는다. 유닛은 enabled 상태라 **재부팅하면 다시 뜬다.**

다시 켜는 법:

```bash
systemctl --user start limbo-nx-drive limbo-nx-sensors limbo-nx-pose limbo-nx-navigation limbo-nx-dashboard
```

켜는 순서는 상관없다(각자 조건을 기다림). 부팅 때 안 뜨게 하려면 `systemctl --user disable <유닛>`, 되돌리려면 `enable`.

현재 `start`와 이전판 `start.bak_1120`의 차이: dashboard 줄에서 `--telemetry-only`가 빠졌다. 즉 지금 NX의 관제 다리는 상태 전송뿐 아니라 관제 화면의 명령(순찰 시작 등)도 받는다. `--telemetry-only` 옵션 자체가 저장소 미커밋 변경(`relay_prog` `node.py`)이다.

#### 설치·확인·제거

젯슨 안에서, 그 사용자로 로그인한 셸에서 실행한다. sudo는 쓰지 않는다.

```bash
cd ~/limbo
bash tools/nx_boot/install.sh          # 링크 9개 + bridge-nx.yaml(없을 때만 복사) + daemon-reload + 유닛 5개 enable
```

설치 스크립트가 하는 일:
1. `~/.config/limbo/boot/`에 `tools/nx_boot/boot/`의 파일 4개를, `~/.config/systemd/user/`에 유닛 5개를 **심볼릭 링크**로 연결한다. 그 자리에 일반 파일이 이미 있으면 `<이름>.bak_<날짜-시각>`으로 옮긴 뒤 링크한다(지금 NX 보드처럼 직접 둔 파일이 있는 경우).
2. `~/.config/limbo/bridge-nx.yaml`이 없으면 예시를 **복사**한다(링크 아님). 이미 있으면 건드리지 않는다.
3. `systemctl --user daemon-reload`, `systemctl --user enable` 유닛 5개. **유닛을 켜지는 않는다.**
4. `loginctl enable-linger`를 시도한다. 권한이 없어 실패하면 관리자가 `sudo loginctl enable-linger <사용자>`를 해야 한다는 안내만 출력한다(linger가 없으면 로그인해야 유닛이 뜬다).

설치 뒤 할 일:

```bash
# 1) 토큰 파일이 없으면 만든다(관제 담당에게 받은 값. 저장소·문서에 적지 않는다). 없으면 dashboard 유닛이 동작하지 않는다
ls -l ~/.config/limbo/robot_token
# 2) bridge-nx.yaml을 새로 복사했으면 server_url·token_file 경로가 이 보드에 맞는지 본다
# 3) 유닛 켜기
systemctl --user start limbo-nx-drive limbo-nx-sensors limbo-nx-pose limbo-nx-navigation limbo-nx-dashboard
```

확인(아무것도 바꾸지 않음): 링크 9개가 `링크 OK`인지, bridge·토큰 파일 유무, 유닛별 enabled/active, linger를 표로 보여 준다.

```bash
bash tools/nx_boot/install.sh --check
```

제거: 유닛 5개를 disable하고, 저장소를 가리키는 링크만 지운다. `bridge-nx.yaml`·`robot_token`·백업 파일은 남긴다. 떠 있는 유닛은 내리지 않으므로 필요하면 아래 "멈추는 법"을 먼저 한다.

```bash
bash tools/nx_boot/install.sh --uninstall
```

**고친 내용의 반영:** 링크라서 `git pull`만 하면 파일 내용은 바로 바뀐다. 하지만 **이미 떠 있는 유닛은 재시작해야 새 내용으로 돈다.** 유닛 파일(`*.service`)을 고쳤으면 `systemctl --user daemon-reload`도 먼저 한다.

```bash
systemctl --user daemon-reload                   # 유닛 파일이 바뀐 경우
systemctl --user restart limbo-nx-pose           # 바뀐 것만 (예: corridor_pose.py·map_search.py → pose, ready.py → navigation, start → 해당 인자 유닛)
```

설치 스크립트 검사(임시 HOME과 가짜 `systemctl`·`loginctl`로 돌리므로 실제 설정은 건드리지 않음): `bash tools/nx_boot/test_install.sh`

## 3. 전원과 통신 물리 연결: 장치별로 하나씩

하드웨어 담당자가 배선한 후, 멀티미터로 **극성·전압·공통 접지·퓨즈·비상정지 동작**을 확인하고 소프트웨어 담당자에게 연결표를 전달한다. 처음에는 바퀴가 바닥에 닿지 않도록 차체를 고정한다.

- **Jetson:** 공식 어댑터 또는 보드에 맞는 검증된 전원으로 단독 부팅한다. 배터리 전압을 임의로 Jetson 입력에 연결하지 않는다.
- **MID-360S:** [사용 설명서](https://terra-1-g.djicdn.com/65c028cd298f4669a7f0e40e50ba1131/Mid-360S/UM/20260601/Livox_Mid-360s_User_Manual_en.pdf)에 맞는 전원과 Ethernet 케이블을 사용한다. MID-360S는 Ethernet 커넥터에서 PoE로 전원 공급하는 장치가 아니다. 실제 구입한 케이블/분배기의 핀 배치는 모델과 설명서로 확인한다.
- **OAK-D Lite FF:** 데이터와 전원을 공급할 수 있는 USB 3 케이블/포트로 Jetson에 연결한다. 연결이 불안정하면 케이블, 포트, 전원 공급 가능한 허브를 점검한다. [Luxonis USB 배포 안내](https://docs.luxonis.com/hardware/platform/deploy/usb-deployment-guide)를 따른다.
- **RoboClaw:** USB 통신만으로 모터 전원이 공급되지 않는다. 모터 전원, 엔코더, 비상정지 결선을 [Basicmicro 시작 안내](https://resources.basicmicro.com/roboclaw-motor-controllers-getting-started-guide/)와 [운용 요구사항](https://resources.basicmicro.com/manual/roboclaw/operational-requirements/)에 맞춰 확인한다. 모터 전원 극성과 비상정지는 USB 연결 전에 검증한다.

Jetson에서 먼저 연결 상태를 확인한다.

```bash
lsusb
lsusb -t
ls -l /dev/serial/by-id/
nmcli device status
ip -4 addr
```

`/dev/ttyACM0` 같은 번호는 재부팅·재연결 시 바뀔 수 있다. 가능하면 `/dev/serial/by-id/...`의 안정적인 경로를 RoboClaw 설정에 사용한다. 장치 접근 권한이 없다면 해당 장치 파일의 그룹을 확인한 뒤 사용자 그룹을 설정하고 재로그인한다.

## 4. RoboClaw만으로 모터·엔코더 검증

1. Windows PC에서 Basicmicro **Motion Studio**로 RoboClaw 모델/펌웨어를 확인하고, 모터 채널·엔코더 채널·통신 모드를 설정한다. Linux USB 제어는 [RoboClaw USB 제어 문서](https://resources.basicmicro.com/manual/roboclaw/usb-control/)를 확인한다. 설정값은 파일/사진으로 남긴다.
2. 바퀴를 띄우고 좌/우 모터를 **한쪽씩 아주 낮은 속도**로 돌린다. `+` 명령이 로봇 전진 방향인지, 각 바퀴의 엔코더 카운트가 어느 방향으로 증가하는지 기록한다.
3. 모터 컨트롤러에서 읽은 엔코더 카운트와 실제 바퀴 1회전을 비교해 **바퀴 1회전당 카운트**를 구한다. 감속기와 quadrature 집계 배수를 포함한다.
4. 통신 끊김/명령 중단 시 모터가 멈추는 타임아웃과 물리적 비상정지를 실제로 시험한다. 소프트웨어 드라이버에도 명령 watchdog을 구현한다.

**왜:** 좌우·부호·엔코더 해석이 틀리면 Nav2가 정지 명령이나 선회 명령을 내도 로봇이 반대로 움직인다. 이 단계에서는 Nav2를 실행하지 않는다.

## 5. MID-360S Ethernet과 포인트클라우드

1. LiDAR 시리얼 번호의 끝 두 자리로 공장 IP를 확인한다. [MID-360S 설명서](https://terra-1-g.djicdn.com/65c028cd298f4669a7f0e40e50ba1131/Mid-360S/UM/20260601/Livox_Mid-360s_User_Manual_en.pdf)의 기본 주소 규칙은 `192.168.1.1XX`이다. 실제 센서가 이미 재설정되었을 수도 있으므로 현장 IP를 확인한다.
2. Jetson의 **LiDAR와 연결된 Ethernet 인터페이스**에 같은 서브넷의 미사용 정적 주소를 준다. 예: 센서가 `192.168.1.1XX/24`면 Jetson을 `192.168.1.50/24`로 설정한다. Wi-Fi와 IP 대역이 겹치지 않게 한다. 설정 전후 `nmcli device status`, `ip -4 addr`, `ping <센서-IP>`로 확인한다. ping에 응답하지 않더라도 LiDAR 전용 진단 도구와 UDP 패킷 수신 여부를 추가 확인한다.
3. 공식 [livox_ros_driver2](https://github.com/Livox-SDK/livox_ros_driver2)의 **MID-360S용** 설정 파일인 [`MID360s_config.json`](https://github.com/Livox-SDK/livox_ros_driver2/blob/master/config/MID360s_config.json)에서 `host_ip`를 Jetson 유선 IP로, `lidar_configs.ip`를 실제 센서 IP로 설정한다. README의 SDK 의존성·Jazzy 빌드 절차를 따른다. MID-360S와 Jazzy 지원은 드라이버 [변경 이력](https://github.com/Livox-SDK/livox_ros_driver2/blob/master/CHANGELOG.md)을 확인한다.
4. 센서 드라이버만 실행하고 실제 발행 토픽/타입/주기와 `header.frame_id`, stamp를 확인한다. 드라이버 출력 이름이 Limbo의 `/mid360/points`와 다르면 remap 또는 변환 노드를 둔다.

```bash
ros2 topic list
ros2 topic info /mid360/points
ros2 topic hz /mid360/points
ros2 topic echo /mid360/points --once
```

드라이버 기본 출력이 다른 이름이면 위 명령의 토픽을 **실제 출력 이름**으로 바꾼다. 센서가 보인다는 것만으로 충분하지 않다. PointCloud2를 RViz에서 보고 바닥/벽이 실제 방향과 일치하며, 로봇 자체 포인트를 제거하는 필터가 동작하는지 확인한다.

## 6. OAK-D Lite FF 영상·깊이·포인트클라우드

1. `lsusb`, `lsusb -t`에서 장치와 USB 연결 속도를 확인한다. 필요한 udev 권한을 [Luxonis USB 안내](https://docs.luxonis.com/hardware/platform/deploy/usb-deployment-guide)대로 설정하고 OAK Viewer 등으로 장치 단독 동작을 확인한다.
2. [DepthAI ROS 드라이버](https://docs.luxonis.com/software-v3/depthai/ros/driver)의 Jazzy용 버전을 **실제 Jetson arm64 배포 가능 여부**와 함께 확인해 설치한다. ROS v3 패키지에는 `_v3` 접미사가 붙는 경우가 있으므로 설치된 패키지와 launch 이름을 `ros2 pkg list`로 확인한다.
3. 컬러 영상, 컬러 프레임에 정렬된 깊이, 해당 `CameraInfo`, 포인트클라우드를 발행하도록 설정한다. 실물 드라이버의 출력 이름을 다음 Limbo 입력 계약에 remap한다.

| Limbo 입력 | 메시지/확인 내용 |
| --- | --- |
| `/rgbd_camera/image` | `sensor_msgs/Image`, 컬러 영상 |
| `/rgbd_camera/depth_image` | `sensor_msgs/Image`, 컬러 영상과 정렬된 깊이 |
| `/rgbd_camera/camera_info` | `sensor_msgs/CameraInfo`, 깊이 계산에 대응하는 내부 파라미터 |
| `/rgbd_camera/points` | `sensor_msgs/PointCloud2`. 시뮬에서는 Nav2 장애물·충돌 감시 입력. 실물(`nav2_real.yaml`)은 2026-11-26부터 넣지 않음(장애물 입력은 라이다만, `TROUBLESHOOTING.md` 2026-11-26) |
| `rgbd_camera_optical_link` | 영상과 깊이의 광학 프레임. TF가 실제 카메라 설치 위치를 나타냄 |

4. 깊이 이미지 `encoding`과 단위를 확인한다. 사람 위치 계산은 `16UC1`(mm)이면 m로 바꿔 쓴다(변경 기록 46). 그 밖의 encoding은 m로 본다. 저장소의 `oak_camera` 노드(`camera:=oak`)를 쓰면 이 계약대로 컬러·깊이·CameraInfo와 카메라 안 모델 결과(`/oak/detections`)가 나온다. 포인트클라우드는 아직 내지 않는다. 영상/깊이/CameraInfo의 `header.stamp` 차이도 확인한다. 현재 검출기 동기화 허용 폭은 약 **0.03초**다.

```bash
ros2 topic list
ros2 topic info /rgbd_camera/image
ros2 topic info /rgbd_camera/depth_image
ros2 topic info /rgbd_camera/camera_info
ros2 topic info /rgbd_camera/points
ros2 topic hz /rgbd_camera/image
ros2 topic echo /rgbd_camera/depth_image --once
```

**왜:** RGB 영상만 들어와도 사람 검출기가 시작될 수 있지만, 깊이 단위나 정렬이 틀리면 사람 거리와 지도 좌표가 잘못된다.

## 7. Limbo 저장소에서 필요한 변경

시뮬레이션 파일을 바로 덮어쓰기보다 **실물용 launch와 설정 파일을 별도로 추가**하면 두 환경을 비교해 검증할 수 있다. 아래는 현재 저장소를 기준으로 한 구현 목록이다.

| 파일/영역 | 해야 할 변경 | 이유/완료 기준 |
| --- | --- | --- |
| `limbo/src/limbo_bringup/launch/start_simulation.launch.py` | 이를 복사·참고하여 `start_robot.launch.py` 작성. Gazebo, `ros_gz_bridge`, ground truth, 시뮬레이션 전용 노드를 제외하고 실제 드라이버와 robot_state_publisher, 필터, EKF, 위치추정, Nav2를 연결. 타이머 4/6/8/11/14초 대신 센서/TF/lifecycle 준비 상태를 확인. | 부팅 속도가 달라도 선행 데이터 없이 Nav2가 시작되지 않음. |
| 새 RoboClaw ROS 노드 | `/cmd_vel` (`geometry_msgs/Twist`) 구독. 선속도 `v`, 각속도 `ω`, 바퀴 반지름 `r`, 바퀴 중심 거리 `b`로 `ω_L=(v-ωb/2)/r`, `ω_R=(v+ωb/2)/r` 계산 후 컨트롤러 단위로 변환. 엔코더에서 `/odom` (`nav_msgs/Odometry`) 발행. 포트 재연결/명령 타임아웃/모터 정지 구현. | 전진·회전 부호와 정지 동작이 실제 바퀴와 일치. `header.stamp`, `odom`/`base_footprint` 프레임, twist covariance가 유효함. |
| IMU 드라이버 | 실제 IMU를 `/imu` (`sensor_msgs/Imu`)로 발행. **BOM의 IMU 모듈/연결방식과 드라이버를 확인**하고 축·단위·중력·yaw-rate 부호를 검증. 아직 IMU가 없다면 EKF 구성과 최초 주행 가능 범위를 별도로 결정. | EKF가 기대하는 각속도가 들어오고 정지 시 값이 안정됨. |
| `limbo/src/limbo_navigation/config/ekf.yaml` | 실물용 설정에서 `use_sim_time: false`; `/odom`의 전진속도와 `/imu`의 각속도·공분산을 실제 데이터에 맞게 조정. | EKF가 `odom → base_footprint` 동적 TF를 한 곳에서 발행. |
| `limbo/src/limbo_description/urdf/limbo.urdf.xacro` | 프레임 구조는 유지하고 실측 wheel radius/separation 및 센서 장착 변환을 비교·수정. | TF 트리에 누락/중복 동적 변환이 없고 센서 관측 위치가 실물과 일치. |
| `limbo/src/limbo_navigation/config/nav2_params.yaml` | 실물용 복사본을 만들어 `use_sim_time: false`, 실제 footprint, 속도/가속도/장애물 거리, 센서 토픽을 설정. ToF의 `tof_mark` 제거. 충돌 감시 입력과 timeout을 실제 토픽 주기에 맞춤. | costmap과 collision monitor에 LiDAR/OAK 장애물이 표시됨. |
| `limbo/src/limbo_navigation/config/amcl.yaml` 및 지도 | `use_sim_time: false`, **실제 환경에서 만든 지도**와 실제 초기 위치를 사용. 새로운 공간에서는 먼저 SLAM으로 지도 작성. | RViz에서 로봇 pose와 실제 위치·방향이 일치. |
| `limbo/src/limbo_perception/limbo_perception/person_detector.py` | OAK의 토픽·깊이 단위·영상/깊이 정렬을 확인하고 필요한 변환 적용. Jetson용 모델 실행 경로/성능도 검증. | 사람이 없는/있는 단일 프레임에서 예측과 거리 계산이 합리적. |
| ToF 관련 노드와 행동 트리 | 첫 실물 launch에서 `tof_node`를 시작하지 않는다. ToF가 없으면 `/person_blocking`, `/person_approaching`이 생성되지 않으므로 이를 기다리는 사람 회피/대기 경로를 임시로 비활성화하거나 LiDAR/OAK 기반 신호로 대체. 두 행동 트리의 `<BackUp>` 동작도 현재 운영 방침과 맞는지 검토. | 없는 센서를 무한히 기다리지 않고, 후진 금지 정책이 있다면 실제 BT도 이를 지킴. |

**중요한 토픽 경계:** 현재 시뮬레이션의 `bridge.yaml`이 Gazebo와 ROS를 이어 준다. 실물에서는 각 드라이버가 같은 ROS 메시지를 직접 제공하거나 remap/변환 노드가 제공해야 한다. `/cmd_vel`을 발행하는 Nav2와 이를 받는 RoboClaw 브리지 사이에 명령 경로가 하나만 있어야 한다.

`/odom` 발행자와 `odom → base_footprint` TF 발행자는 구별한다. 현재 EKF가 해당 TF를 발행하도록 설정되어 있으므로 RoboClaw 노드가 같은 TF를 추가 발행하면 안 된다. `map → odom`은 AMCL 또는 SLAM 중 현재 사용하는 한 노드가 담당한다.

## 8. 소프트웨어 통합과 관찰 순서

아래 순서를 각자 별도 터미널에서 실행하고, **매 단계에서 데이터가 정상인 것을 보고 다음 단계로 진행**한다.

1. 모든 터미널에서 같은 ROS 환경을 source하고 `ROS_DOMAIN_ID`를 맞춘다. Jetson 내부 단일 컴퓨터 시험이면 기본값으로 시작해도 된다. 원격 PC에서 ROS를 볼 경우 두 기기의 네트워크와 DDS discovery를 확인한다.
2. `ros2 param get /<노드명> use_sim_time`으로 실물 노드가 모두 `false`인지 확인한다. Jetson 시간과 센서 메시지 stamp가 현재 시간과 일치해야 한다. 멀티 컴퓨터라면 NTP/chrony 등으로 시계를 동기화한다.
3. `robot_state_publisher`와 실물 센서 드라이버를 실행한다. `ros2 run tf2_ros tf2_echo base_footprint <센서프레임>`으로 고정 TF를 확인한다.
4. RoboClaw 브리지(모터 출력은 아직 차단하거나 바퀴를 띄움)를 실행하고 `/odom`, `/imu`의 타입·frame·stamp·속도 부호를 확인한다. EKF를 실행한 뒤 `ros2 run tf2_ros tf2_echo odom base_footprint`로 이동에 따른 변환을 확인한다.
5. LiDAR/OAK 관측을 RViz에서 확인한다. 포인트가 회전·주행에 따라 로봇 프레임에 고정된 올바른 방향으로 보이는지 확인한다. Nav2 local/global costmap과 collision monitor의 입력 토픽이 실제로 들어오는지 확인한다.
6. SLAM으로 실환경 지도를 만들거나 이미 검증한 지도를 로드한다. AMCL의 초기 위치는 RViz 등에서 **로봇의 실제 시작 위치**로 지정한다. 시뮬레이션의 `(0,0,0)`을 기계적으로 사용하지 않는다.
7. Nav2 lifecycle 노드가 active이고, global/local costmap과 `map → odom → base_footprint` 연결이 유지되는지 본다. 사람 검출/행동 트리는 기본 주행이 안정된 다음 추가한다.

빠른 관찰 명령:

```bash
ros2 topic list
ros2 topic hz /odom
ros2 topic hz /imu
ros2 topic echo /cmd_vel --once
ros2 run tf2_ros tf2_echo odom base_footprint
ros2 lifecycle get /bt_navigator
```

## 9. 첫 주행: 작은 단계로 검증

1. 비상정지 담당자를 지정하고, 주변을 비운 뒤 **바퀴를 띄운 상태**에서 `/cmd_vel` 소량 명령으로 전진·정지·좌회전·우회전 방향을 확인한다. 명령이 사라지거나 프로세스가 종료되면 정지하는지 확인한다.
2. 넓은 평지에서 수동/teleop으로 **저속 직진 짧은 거리**와 제자리 회전을 실시한다. 실제 이동거리·각도와 `/odom`·EKF·TF를 비교해 바퀴 반지름, 바퀴 간 거리, 엔코더 부호를 보정한다.
3. 장애물 앞에서 LiDAR/OAK 포인트가 costmap과 collision monitor에 반영되는지 확인한다. 정지 거리는 실제 최고속도, 제동거리, 지연을 고려해 현장에서 측정한다.
4. 검증한 지도와 시작 pose를 사용해 가까운 자율 목표 하나를 보낸다. 경로·속도·회피·정지를 관찰한다. 이어서 여러 목표와 사람 검출을 추가한다.
5. 각 시험의 rosbag, launch 로그, 파라미터, 성공/실패 조건을 기록한다. 실패가 발생한 단계의 센서→TF→추정→계획→명령 순으로 원인을 좁힌다.

## 흔한 증상과 먼저 볼 곳

| 증상 | 우선 확인 |
| --- | --- |
| `ros2 topic list`에 센서가 없음 | USB/Ethernet 인식, 전원, IP/방화벽, 드라이버 launch, `ROS_DOMAIN_ID` |
| LiDAR 드라이버는 실행되지만 데이터 없음 | MID-360S 실제 IP, Jetson 유선 IP, `host_ip`, 케이블/전원, UDP 포트 |
| OAK 영상은 있으나 사람 거리가 이상함 | 깊이 encoding과 mm↔m, 컬러 정렬, CameraInfo, optical frame, stamp 차이 |
| 바퀴가 반대로 돎 | M1/M2 좌우 대응, 모터 극성, 엔코더 부호, `v/ω` 변환 |
| 로봇이 움직여도 RViz pose가 고정됨 | `/odom`·`/imu` 주기, EKF 설정, TF 중복, `use_sim_time`, stamp |
| Nav2가 시작했지만 목표로 가지 않음 | map/AMCL 초기 pose, costmap 장애물, lifecycle 상태, collision monitor 명령 경로 |
| 명령이 멈춰도 바퀴가 돎 | RoboClaw 명령 timeout, 브리지 watchdog, 물리적 비상정지. 즉시 시험 중단 |
| 사람 대기 행동이 끝나지 않음 | ToF를 뺀 상태에서 `/person_blocking`·`/person_approaching` 의존성이 남아 있는지 확인 |

## 완료 시 팀이 남겨야 할 산출물

- Jetson OS/JetPack/ROS 버전과 설치 명령 기록
- 실제 배선도, 전원 정격 확인표, 비상정지 시험 결과
- MID-360S IP·설정 파일, OAK launch·토픽 remap, RoboClaw 설정 백업
- 차체 실측값, 모터·엔코더 방향 및 보정값
- 실물용 launch/파라미터, 지도, 첫 주행 rosbag과 결과 기록

## 참고 자료

- [NVIDIA Jetson Orin Nano 개발자 키트 빠른 시작](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/quick_start.html)
- [ROS 2 Jazzy Ubuntu 설치](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html)
- [Livox MID-360S 사용 설명서](https://terra-1-g.djicdn.com/65c028cd298f4669a7f0e40e50ba1131/Mid-360S/UM/20260601/Livox_Mid-360s_User_Manual_en.pdf)와 [livox_ros_driver2](https://github.com/Livox-SDK/livox_ros_driver2)
- [Luxonis USB 안내](https://docs.luxonis.com/hardware/platform/deploy/usb-deployment-guide)와 [DepthAI ROS 드라이버](https://docs.luxonis.com/software-v3/depthai/ros/driver)
- [Basicmicro RoboClaw 시작 안내](https://resources.basicmicro.com/roboclaw-motor-controllers-getting-started-guide/)
