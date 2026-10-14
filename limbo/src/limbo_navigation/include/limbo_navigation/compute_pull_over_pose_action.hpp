#pragma once

#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "behaviortree_cpp/action_node.h"
#include "geometry_msgs/msg/pose_stamped.hpp"
#include "limbo_interfaces/msg/person_prediction_array.hpp"
#include "nav2_msgs/msg/costmap.hpp"
#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/bool.hpp"
#include "tf2_ros/buffer.h"

namespace limbo_navigation
{

// 진로 위로 다가오는 사람 앞에서 먼저 길을 비울 자리를 local costmap에서 고른다 (PROJECT.md 2-1·2-2, R6).
// 후보: 로봇 옆 side_offsets(큰 것부터)·앞 forward(후진 안 함), 방향 그대로. 받아들이는 자리:
//   중심 칸이 inscribed 미만, 외곽 안에 치명(실제 장애물) 칸 없음, 중심에서 치명 칸까지 반폭 + margin 이상.
// 양쪽 다 되면 사람이 오는 쪽의 반대쪽, 사람 위치를 모르면 오른쪽 (Q12).
// 다가오는 사람 한 명(/person_approaching이 참인 동안)에 한 번만 — 다시 부르면 실패해서 그 자리 정지로 넘어간다.
class ComputePullOverPose : public BT::SyncActionNode
{
public:
  ComputePullOverPose(const std::string & name, const BT::NodeConfiguration & conf);
  ComputePullOverPose() = delete;

  BT::NodeStatus tick() override;

  static BT::PortsList providedPorts()
  {
    return {
      BT::OutputPort<geometry_msgs::msg::PoseStamped>("pose", "비켜설 자리 (global_frame)"),
      BT::InputPort<std::vector<double>>("side_offsets", "0.5;0.4;0.3", "옆 거리 후보 (m, 큰 것부터)"),
      BT::InputPort<double>("forward", 0.3, "앞 거리 (m, 후진 안 함)"),
      BT::InputPort<double>("half_width", 0.295, "로봇 반폭 (m)"),
      BT::InputPort<double>("half_length", 0.25, "로봇 반길이 (m)"),
      BT::InputPort<double>("margin", 0.1, "치명 칸까지 반폭에 더하는 여유 (m)"),
      BT::InputPort<std::string>("costmap_topic", "/local_costmap/costmap_raw", "local costmap"),
      BT::InputPort<std::string>("approach_topic", "/person_approaching", "다가오는 사람"),
      BT::InputPort<std::string>("predictions_topic", "/person_detector/predictions", "사람 위치"),
      BT::InputPort<std::string>("global_frame", "map", "출력 좌표계"),
      BT::InputPort<std::string>("base_frame", "base_link", "로봇 좌표계"),
    };
  }

private:
  // 후보 자리(로봇 기준 x, y)를 costmap에서 판정
  bool acceptable(double x, double y);
  // 가장 가까운 사람이 로봇 왼쪽(+1)/오른쪽(-1)/모름(0)
  int personSide();
  double cost(double base_x, double base_y);   // 로봇 기준 점의 칸 비용, 밖이면 -1

  rclcpp::Node::SharedPtr node_;
  std::shared_ptr<tf2_ros::Buffer> tf_;
  rclcpp::CallbackGroup::SharedPtr group_;
  rclcpp::executors::SingleThreadedExecutor executor_;
  rclcpp::Subscription<nav2_msgs::msg::Costmap>::SharedPtr costmap_sub_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr approach_sub_;
  rclcpp::Subscription<limbo_interfaces::msg::PersonPredictionArray>::SharedPtr predictions_sub_;
  nav2_msgs::msg::Costmap::SharedPtr costmap_;
  limbo_interfaces::msg::PersonPredictionArray::SharedPtr predictions_;
  bool approaching_{false};
  bool tried_{false};   // 이번 다가옴에서 이미 시도함
  std::optional<rclcpp::Time> last_tick_;
  // 판정 중에 쓰는 costmap 기준 로봇 자세
  double rx_{0.0}, ry_{0.0}, ryaw_{0.0};
};

}  // namespace limbo_navigation
