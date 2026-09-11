## Gazebo 실행 후 필요한 명령어 모음!

### **처음 clone 받을 때 주의 사항**
- 같이 다운 받아야할 submodules가 있으니 git clone --recurse-submodules <저장소_URL> 와 같은 형태로 받을것!!!!!

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