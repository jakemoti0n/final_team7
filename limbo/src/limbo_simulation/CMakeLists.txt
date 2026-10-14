cmake_minimum_required(VERSION 3.8)
project(limbo_simulation)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)

# gz-sim 시스템 플러그인 (plugins/actor_pose_control.cpp): 토픽 명령대로 actor를 옮긴다.
# ROS Jazzy는 Gazebo를 vendor 패키지로 주므로 gz_sim_vendor를 먼저 찾아야 gz-sim이 잡힌다
find_package(gz_sim_vendor REQUIRED)
find_package(gz-sim REQUIRED)
find_package(gz_plugin_vendor REQUIRED)
find_package(gz-plugin REQUIRED COMPONENTS register)

add_library(actor_pose_control SHARED plugins/actor_pose_control.cpp)
target_link_libraries(actor_pose_control gz-sim::core gz-plugin::register)
install(TARGETS actor_pose_control DESTINATION lib)

install(
  DIRECTORY
    worlds
    config
    launch
    models
    scripts
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  # the following line skips the linter which checks for copyrights
  # comment the line when a copyright and license is added to all source files
  set(ament_cmake_copyright_FOUND TRUE)
  # the following line skips cpplint (only works in a git repo)
  # comment the line when this package is in a git repo and when
  # a copyright and license is added to all source files
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
