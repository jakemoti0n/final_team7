cmake_minimum_required(VERSION 3.8)
project(limbo_human_costmap)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(nav2_costmap_2d REQUIRED)
find_package(pluginlib REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_lifecycle REQUIRED)
find_package(limbo_interfaces REQUIRED)

# 플러그인 클래스 이름은 limbo_navigation::HumanLayer 그대로 유지
# (nav2_params.yaml 과 기존 코드와의 호환을 위해)
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

install(
  TARGETS human_layer
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
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
