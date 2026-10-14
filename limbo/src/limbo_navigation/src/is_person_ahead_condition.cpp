#include "limbo_navigation/is_person_ahead_condition.hpp"

#include <cmath>

#include "behaviortree_cpp/bt_factory.h"

namespace limbo_navigation
{

IsPersonAheadCondition::IsPersonAheadCondition(
  const std::string & name, const BT::NodeConfiguration & conf)
: BT::ConditionNode(name, conf)
{
  node_ = config().blackboard->get<rclcpp::Node::SharedPtr>("node");
  // BT는 tick 때만 이 그룹을 돌린다. 깊이 1이라 그때 쌓인 것 중 가장 최근 것만 남는다
  callback_group_ = node_->create_callback_group(
    rclcpp::CallbackGroupType::MutuallyExclusive, false);
  callback_group_executor_.add_callback_group(callback_group_, node_->get_node_base_interface());

  std::string topic;
  getInput("topic", topic);
  rclcpp::SubscriptionOptions options;
  options.callback_group = callback_group_;
  sub_ = node_->create_subscription<geometry_msgs::msg::PointStamped>(
    topic, rclcpp::QoS(1),
    [this](geometry_msgs::msg::PointStamped::SharedPtr msg) {last_ = msg;}, options);
}

BT::NodeStatus IsPersonAheadCondition::tick()
{
  callback_group_executor_.spin_some();
  if (!last_) {
    if (shouldLog(false)) {
      RCLCPP_INFO(node_->get_logger(), "IsPersonAhead: 아님 → 복구 (받은 사람 위치 없음)");
    }
    return BT::NodeStatus::FAILURE;
  }

  double max_distance = 2.0, half_width = 0.8, max_age = 1.0;
  getInput("max_distance", max_distance);
  getInput("half_width", half_width);
  getInput("max_age", max_age);

  // 받은 시각이 아니라 카메라 영상 시각으로 잰다 (tick 때 한꺼번에 받으므로 받은 시각은 늘 "방금"이다)
  const double age = (node_->now() - rclcpp::Time(last_->header.stamp, node_->get_clock()->get_clock_type())).seconds();
  const auto & p = last_->point;
  const bool ahead = age <= max_age && p.x > 0.0 && p.x < max_distance && std::abs(p.y) < half_width;
  if (shouldLog(ahead)) {
    RCLCPP_INFO(
      node_->get_logger(), "IsPersonAhead: %s (x=%.2f y=%.2f, %.1f s 전)",
      ahead ? "사람 → 기다림" : "아님 → 복구", p.x, p.y, age);
  }
  return ahead ? BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
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
