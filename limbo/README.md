## Gazebo 실행 후 필요한 명령어 모음!

#### PointCloud : 3D LiDAR 센서 2D로 변환

ros2 run pointcloud_to_laserscan pointcloud_to_laserscan_node \
  --ros-args \
  -r cloud_in:=/mid360/points \
  -r scan:=/scan \
  -p use_sim_time:=true \
  -p target_frame:=mid360_link \
  -p min_height:=-0.25 \
  -p max_height:= 0.20 \
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