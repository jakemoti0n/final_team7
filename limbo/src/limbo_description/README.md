# limbo_description

로봇 모델(URDF/xacro)과 메시. launch의 `robot:=` 인자로 고른다.

| `robot:=` | 파일 | 로봇 |
|---|---|---|
| `v14` (기본) | `urdf/limbo.urdf.xacro`, `urdf/limbo.gazebo.xacro`, `meshes/v14/` | 이동형 2분할 쓰레기통 45×45×70 v14 (실제 로봇) |
| `legacy` | `urdf/legacy/`, `meshes/*.stl` | 이전 모델 (0.45 m 정사각형, 높이 약 0.7 m). 예전 실험과 비교할 때만 쓴다 |

```bash
ros2 launch limbo_bringup start_simulation.launch.py world:=aischool_2f map:=aischool_2f_map             # v14
ros2 launch limbo_bringup start_simulation.launch.py world:=aischool_2f map:=aischool_2f_map robot:=legacy
```

## v14 치수 (+X 앞, +Y 왼쪽, +Z 위, 원점은 바닥의 몸체 중심)

출처: `45x45x70_v14_ROS2_Jazzy_Gazebo.zip`의 `trash_robot_sim`. 센서만 실제 장착할 것으로 바꿨다.

| 항목 | 값 |
|---|---|
| 몸체 | 0.45 × 0.45 m, 바닥 간격 0.06 m, 윗면 0.835 m, 뚜껑 닫힌 높이 0.95 m |
| 구동 바퀴 | 지름 0.15 m, 폭 0.05 m, 간격 0.54 m (바퀴 포함 전체 폭 0.59 m) |
| 캐스터 | 앞뒤 ±0.115 m, 지름 0.125 m. 회전하지 않는 저마찰 구로 대체 |
| 뚜껑 | 경첩 (0.225, 0.23, 0.835), 0~1.972 rad. `/lid_angle` (std_msgs/Float64) |
| MID-360 + IMU (`mid360_link`) | 뚜껑 위 (0, 0, 0.926). **뚜껑을 열면 같이 기운다** → 주행 중에는 열지 않는다 |
| OAK-D Lite (`rgbd_camera_link`) | 앞 0.235, 왼쪽 0.1575, 높이 0.50 m, 수평. 가로 69° |
| 질량 | 약 22.6 kg. **원본 작성자의 임시 가정값** (몸체 20 kg, 바퀴 토크 4 N·m) |

Nav2 쪽 로봇 크기 값(`limbo_navigation/config/nav2_params.yaml`)은 v14 기준이다.
- 로봇 외곽 0.50 × 0.63 m (+ padding 0.02), 팽창 반지름 0.45 m, 장애물 높이 상한 1.00 m
- `robot:=legacy`면 launch가 외곽 0.45 m 정사각형, 팽창 0.40/0.35 m, 높이 상한 0.80 m로 바꿔 넣는다
- self filter: v14는 `self_filter.yaml` (`lid_link`), legacy는 `self_filter_legacy.yaml` (`roof_link`)

## 모델 바꿀 때
- 센서 위치는 `limbo.urdf.xacro` 위쪽의 `camera_*`, `mid360_above_hinge` 값만 바꾼다
- 몸체 크기가 바뀌면 `nav2_params.yaml`의 `footprint`, `inflation_radius`(바깥 반지름보다 크게)도 같이 바꾼다
- xacro가 경고를 stderr로 내면 launch가 시작하지 않는다. 바꾼 뒤 `xacro urdf/limbo.urdf.xacro > /dev/null`로 경고가 없는지 확인한다
