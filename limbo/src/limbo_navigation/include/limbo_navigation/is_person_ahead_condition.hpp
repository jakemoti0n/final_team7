#pragma once

#include <optional>
#include <string>

#include "behaviortree_cpp/condition_node.h"
#include "geometry_msgs/msg/point_stamped.hpp"
#include "rclcpp/rclcpp.hpp"

namespace limbo_navigation
{

// 막혔을 때 앞에 사람이 있으면 참. 복구 분기 앞에서 "사람이면 기다리기"를 고르는 데 쓴다 (PROJECT.md 2-2).
// person_detector는 사람을 봤을 때만 가장 가까운 한 명을 내므로, 오래된 위치는 "사람 없음"으로 본다.
class IsPersonAheadCondition : public BT::ConditionNode
{
public:
  IsPersonAheadCondition(const std::string & name, const BT::NodeConfiguration & conf);
  IsPersonAheadCondition() = delete;

  BT::NodeStatus tick() override;

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<std::string>("topic", "/person_detector/person_position_base", "로봇 기준 가장 가까운 사람"),
      BT::InputPort<double>("max_distance", 2.0, "앞쪽 거리 상한 (m)"),
      BT::InputPort<double>("half_width", 0.8, "좌우 폭 절반 (m)"),
      BT::InputPort<double>("max_age", 1.0, "이보다 오래된 위치는 버림 (s)"),
    };
  }

private:
  bool shouldLog(bool ahead);

  rclcpp::Node::SharedPtr node_;
  rclcpp::CallbackGroup::SharedPtr callback_group_;
  rclcpp::executors::SingleThreadedExecutor callback_group_executor_;
  rclcpp::Subscription<geometry_msgs::msg::PointStamped>::SharedPtr sub_;
  geometry_msgs::msg::PointStamped::SharedPtr last_;
  std::optional<bool> was_ahead_;
  rclcpp::Time last_log_{0, 0, RCL_ROS_TIME};
};

}  // namespace limbo_navigation
