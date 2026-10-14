#include "limbo_navigation/is_person_ahead_condition.hpp"

#include "behaviortree_cpp/bt_factory.h"

namespace limbo_navigation
{

IsPersonAheadCondition::IsPersonAheadCondition(
  const std::string & name, const BT::NodeConfiguration & conf)
: BT::ConditionNode(name, conf)
{
  node_ = config().blackboard->get<rclcpp::Node::SharedPtr>("node");
  // BT는 tick 때만 이 그룹을 돌린다. tof_node가 10 Hz로 늘 내므로 마지막 값만 본다
  callback_group_ = node_->create_callback_group(
    rclcpp::CallbackGroupType::MutuallyExclusive, false);
  callback_group_executor_.add_callback_group(callback_group_, node_->get_node_base_interface());

  std::string topic;
  getInput("topic", topic);
  rclcpp::SubscriptionOptions options;
  options.callback_group = callback_group_;
  sub_ = node_->create_subscription<std_msgs::msg::Bool>(
    topic, rclcpp::QoS(1),
    [this](std_msgs::msg::Bool::SharedPtr msg) {blocking_ = msg->data;}, options);
}

BT::NodeStatus IsPersonAheadCondition::tick()
{
  callback_group_executor_.spin_some();
  if (shouldLog(blocking_)) {
    RCLCPP_INFO(
      node_->get_logger(), "IsPersonAhead: %s", blocking_ ? "사람 → 기다림" : "아님 → 복구");
  }
  return blocking_ ? BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}

// ReactiveFallback이 매 tick(10 ms) 다시 묻기 때문에 판단이 바뀌었거나 1초 지났을 때만 남긴다
bool IsPersonAheadCondition::shouldLog(bool ahead)
{
  const auto now = node_->now();
  if (was_ahead_ == ahead && (now - last_log_).seconds() < 1.0) {
    return false;
  }
  was_ahead_ = ahead;
  last_log_ = now;
  return true;
}

}  // namespace limbo_navigation

BT_REGISTER_NODES(factory)
{
  factory.registerNodeType<limbo_navigation::IsPersonAheadCondition>("IsPersonAhead");
}
