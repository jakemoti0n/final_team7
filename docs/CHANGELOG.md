# 변경 기록

dev에 push할 때마다 위에 추가한다. 최신이 맨 위.
pull 받은 뒤 해야 할 일이 있으면 "할 일"에 적는다.

---

## 2026-10-02 (3) IMU 추가, 바퀴 odom + IMU 융합(EKF)

**할 일**
```bash
sudo apt install ros-jazzy-robot-localization   # 처음 한 번만
build_limbo
```

**변경**
- 시뮬레이션 로봇에 MID-360 내장 IMU를 추가했음 (`/imu`, 200Hz, 노이즈·바이어스 포함)
- 바퀴 odom(전진 속도)과 IMU(회전 속도)를 EKF로 합쳤음. 회전 오차가 360° 회전 기준 31°에서 0.4°로 줄었음
- `odom → base_footprint` TF는 이제 EKF(`ekf_filter_node`)가 발행함. Gazebo diff-drive TF는 브리지하지 않음

**참고**
- 로봇이 걸려서 바퀴만 헛도는 문제는 IMU로도 못 잡아서 남아 있음 (`docs/KNOWN_ISSUES.md`)
- 바퀴 마찰 계수(0.5)가 낮아 회전 시 미끄러짐. 회전 오차의 원인으로 추정

---

## 2026-10-02 (2) 학원 2층 월드, 월드·지도 선택 인자

**할 일**
```bash
build_limbo
```

**변경**
- 피난안내도 사진으로 학원 2층 월드 `aischool_2f`를 만들었음 (교실 7개, 홀, 복도, 걷는 사람 3명). 같은 도면으로 만든 지도도 있어서 SLAM 없이 바로 주행 가능함
  ```bash
  ros2 launch limbo_bringup start_simulation.launch.py world:=aischool_2f map:=aischool_2f_map
  ```
- launch에 `world`, `map` 인자를 추가했음. 인자 없이 실행하면 기존 `human_test` 그대로임
- 월드 생성 스크립트를 `limbo_simulation/tools/aischool_2f/`에 넣었음. 축척은 교실 깊이 실측(약 6.1m)과 복도 폭(약 1.5m)으로 맞췄음
- 미해결 문제 목록 `docs/KNOWN_ISSUES.md`를 만들었음

**참고**
- 새 월드 주행 중 로봇이 걸려 바퀴만 헛돌면 AMCL이 위치를 놓치는 문제를 확인했음

---

## 2026-10-02 (1) person_detector 리팩터링, 버그 수정

**할 일**
```bash
build_limbo
```

**변경**
- person_detector를 기능별 파일로 나눴음 (`tracking`, `kalman`, `motion`, `intent`, `geometry`, `visualization`, `messages`). 같은 rosbag으로 전후 출력이 같은 것을 확인했음
- 튜닝값을 `limbo_perception/config/person_detector.yaml`로 뺐음. 빌드 없이 바꿀 수 있음
- 시뮬레이션을 켜면 2D Pose Estimate 없이 바로 주행 가능함 (AMCL 초기 위치 = 스폰 위치)
- Gazebo가 일시정지 없이 바로 재생됨
- person_detector CPU 사용량을 줄였음 (시뮬레이션 중 약 775% → 116%). torch·numpy 스레드 풀이 서로 헛돌던 문제였음
- 새로 clone하면 `limbo_description` 빌드가 실패하던 문제를 고쳤음
- `.gitignore`에 `__pycache__`, `*.pyc`를 추가했음

**참고**
- 리팩터링 전 원본은 `kkh` 브랜치에 있음
