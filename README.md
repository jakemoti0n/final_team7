## Gazebo 실행 후 필요한 명령어 모음!

### **처음 clone 받을 때 주의 사항**
- 같이 다운 받아야할 submodules가 있으니 git clone --recurse-submodules <저장소_URL> 와 같은 형태로 받을것!!!!!

### colcon build 할 때 주의 사항!!!!!
limbo_perception은 yolo를 통해 사람 인식하려고 만든 패키지인데 얘는 새로 받은 yolo용 python 써야해서 이제부터 빌드할 때
python -m colcon build --symlink-install 로 사용해야함. alias 만들어서 사용할 것을 추천...ㅠ

### 몇개 잊었지만 늦게라도 적어보는 받아야할 pkg 목록
1. sudo apt install ros-jazzy-cv-bridge python3-venv : openCV 관련 pkg
2. python3 -m venv --system-site-packages ~/limbo/venvs/limbo_yolo
3. source ~/limbo/venvs/limbo_yolo/bin/activate
4. pip install -r ~/limbo/requirements.txt : YOLO용 Python 환경 설치
5. python -m pip install --force-reinstall \
  "numpy==1.26.4" \
  "opencv-python==4.10.0.84" : python과 yolo 충돌 안나게 버전 고정

#### 통합 실행 명령어

ros2 launch limbo_bringup start_simulation.launch.py


#### PointCloud : 3D LiDAR 센서 2D로 변환

ros2 run pointcloud_to_laserscan pointcloud_to_laserscan_node \
  --ros-args \
  -r cloud_in:=/mid360/points_filtered \
  -r scan:=/scan \
  -p use_sim_time:=true \
  -p target_frame:=mid360_link \
  -p min_height:=-0.03 \
  -p max_height:=0.20 \
  -p angle_min:=-3.14159265 \
  -p angle_max:=3.14159265 \
  -p angle_increment:=0.0174533 \
  -p scan_time:=0.1 \
  -p range_min:=0.10 \
  -p range_max:=20.0


#### slam_toolbox 실행 : 주행할 지도를 만들 때만 사용

ros2 launch slam_toolbox online_async_launch.py \
  use_sim_time:=true \
  slam_params_file:=$HOME/limbo/install/limbo_navigation/share/limbo_navigation/config/slam.yaml


#### AMCL과 map_server 실행 : slam을 통해 만든 map 불러오기 + 로봇 위치 파악

ros2 launch limbo_navigation localization.launch.py

#### map을 교체하고 싶다??
navigation/launch에 있는 localization.launch.py 파일에서 default_map_file 변경하기

#### Nav2 실행

ros2 launch nav2_bringup navigation_launch.py   use_sim_time:=true   autostart:=true   params_file:=$HOME/limbo/limbo/install/limbo_navigation/share/limbo_navigation/config/nav2_params.yaml

#### self-filter 실행 : 로봇 몸체를 LiDAR가 인식하지 않도록 필터링

ros2 launch robot_self_filter self_filter.launch.py \
  robot_description:="$(xacro $HOME/limbo/limbo/src/limbo_description/urdf/limbo.urdf.xacro)" \
  filter_config:=$HOME/limbo/limbo/src/limbo_navigation/config/self_filter.yaml \
  in_pointcloud_topic:=/mid360/points \
  out_pointcloud_topic:=/mid360/points_filtered \
  lidar_sensor_type:=0 \
  zero_for_removed_points:=false \
  use_sim_time:=true


#### Collision Monitor on/off

ros2 service call /collision_monitor/toggle \
  nav2_msgs/srv/Toggle \
  "{enable: true}"   <-false로 고치면 끄기

#### 하드웨어 조립 후 조정해야할 파타미터 정리

- nav2_params.yaml -> source_timeout : 센서의 반영 속도 / 노트북 메모리 과열로 현재 2.0으로 설정. 이후 0.5까지 점차적으로 감소시켜 보기

- person_detector.py -> self.reassociate_max_age : tracking된 사람 정보 유지 시간. 3초로 설정했지만 실제 사람들이 많이 교차되는 환경에서 오랜 시간 유지되는 tracking 데이터가 어떤식으로 작동할지 몰라 주시 필요함

- SLAM을 통해 초기 map을 생성할 때 pointclaud에서 잘라오는 3D 데이터의 높이 설정을 수정할 필요 있음. 현재 LiDAR 기준 +20cm 까지 감지하기 때문에 충분히 지나갈 수 있는 높이의 장애물을 못 지나가거나 돌아가는 선택지가 발생

#### YOLO를 통한 사람 구별

ros2 run limbo_perception person_detector \
  --ros-args \
  -p use_sim_time:=true

#### waypoint 설정을 통한 주행 경로 설정: limbo_patrol

#### rviz에 찍힌 좌표 값을 가져오는 명령어
ros2 topic echo /clicked_point

#### 지정된 wayPoint로 이동하는 명령어
ros2 run limbo_patrol patrol_node

#### 제 alias 설정!
alias sb="source ~/.bashrc; echo \"bashrc is reloaded!\""
alias jazzy="source /opt/ros/jazzy/setup.bash && ros_domain && echo \"ROS2 Jazzy is activated!\""
alias ros_domain="export ROS_DOMAIN_ID=97; echo \"ROS_DOMAIN_ID=97\""
alias start_ros="jazzy; source ~/ros2_study/install/setup.bash; echo \"ros2_study is activated!\""
alias pink="jazzy && source ~/pinky/install/setup.bash && echo \"pinky is acticvated\""
alias nav="jazzy && source ~/pinky_ws/install/setup.bash && echo \"nav2 is activated\""
alias limbo="jazzy && goyolo && source ~/limbo/limbo/install/setup.bash && echo \"limbo is activated\""
alias goyolo="source ~/limbo/venvs/limbo_yolo/bin/activate && echo \"Lets start YOLO\""
alias build_limbo="cd ~/limbo/limbo && python -m colcon build --symlink-install"