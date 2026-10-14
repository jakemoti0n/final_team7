#pragma once

#include <optional>
#include <string>

#include "behaviortree_cpp/condition_node.h"
#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/bool.hpp"

namespace limbo_navigation
{

// 막혔을 때 사람 때문이면 참. 복구 분기 앞에서 기다리기를 고른다 (PROJECT.md 2-2, R5).
// 판단은 tof_node의 /person_blocking이 막히기 시작한 순간에 정해 둔다(카메라 기억 + ToF 래치).
// BT는 멈춘 뒤 약 20 s 지나서야 여기에 오므로, 여기서 카메라 기억을 다시 보면 늘 지나 있다 (R5 Q2).
class IsPersonAheadCondition : public BT::ConditionNode
{
public:
  IsPersonAheadCondition(const std::string & name, const BT::NodeConfiguration & conf);
  IsPersonAheadCondition() = delete;

  BT::NodeStatus tick() override;

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<std::string>("topic", "/person_blocking", "사람 때문에 막힘 (tof_node 래치)"),
    };
  }

private:
  bool shouldLog(bool ahead);

  rclcpp::Node::SharedPtr node_;
  rclcpp::CallbackGroup::SharedPtr callback_group_;
  rclcpp::executors::SingleThreadedExecutor callback_group_executor_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr sub_;
  bool blocking_{false};
  std::optional<bool> was_ahead_;
  rclcpp::Time last_log_{0, 0, RCL_ROS_TIME};
};

}  // namespace limbo_navigation
