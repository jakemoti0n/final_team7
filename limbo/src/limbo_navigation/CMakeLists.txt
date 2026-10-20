cmake_minimum_required(VERSION 3.8)
project(limbo_navigation)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
# uncomment the following section in order to fill in
# further dependencies manually.
# find_package(<dependency> REQUIRED)

find_package(nav2_costmap_2d REQUIRED)
find_package(pluginlib REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_lifecycle REQUIRED)
find_package(limbo_interfaces REQUIRED)
find_package(behaviortree_cpp REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav2_behavior_tree REQUIRED)
find_package(std_msgs REQUIRED)

add_library(human_layer SHARED
  src/human_layer.cpp
)

target_include_directories(human_layer
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)

ament_target_dependencies(human_layer
  nav2_costmap_2d
  pluginlib
  rclcpp
  rclcpp_lifecycle
  limbo_interfaces
)

pluginlib_export_plugin_description_file(
  nav2_costmap_2d
  human_layer_plugin.xml
)

# BT 조건 노드: 사람 때문에 기다리는가 (/person_wait, bt_navigator plugin_lib_names로 읽는다)
add_library(limbo_is_waiting_for_person_condition_bt_node SHARED
  src/is_waiting_for_person_condition.cpp
)
target_include_directories(limbo_is_waiting_for_person_condition_bt_node
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)
target_compile_definitions(limbo_is_waiting_for_person_condition_bt_node PRIVATE BT_PLUGIN_EXPORT)
ament_target_dependencies(limbo_is_waiting_for_person_condition_bt_node
  behaviortree_cpp
  limbo_interfaces
  nav2_behavior_tree
  rclcpp
)

install(
  DIRECTORY
    behavior_trees
    config
    maps
    launch
  DESTINATION share/${PROJECT_NAME}
)

install(
  TARGETS human_layer limbo_is_waiting_for_person_condition_bt_node
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

install(
  DIRECTORY include/
  DESTINATION include
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
