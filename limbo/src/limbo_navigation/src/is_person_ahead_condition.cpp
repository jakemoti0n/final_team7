#include "limbo_navigation/is_person_ahead_condition.hpp"

#include <cmath>

#include "behaviortree_cpp/bt_factory.h"

namespace limbo_navigation
{

namespace
{
// 두 위치로 다가옴을 잴 때 쓰는 최대 간격. 이보다 멀면 다른 사람이거나 끊긴 것으로 본다
constexpr double MAX_PAIR_GAP_SEC = 1.0;
// BT는 막혔을 때만 tick하므로 그 사이 들어온 사람 위치를 다 쌓아 두고 tick 때 순서대로 본다.
// 카메라 15 Hz × memory_sec 5 s보다 넉넉하게
constexpr size_t PERSON_QUEUE = 100;
}

IsPersonAheadCondition::IsPersonAheadCondition(
  const std::string & name, const BT::NodeConfiguration & conf)
: BT::ConditionNode(name, conf)
{
  node_ = config().blackboard->get<rclcpp::Node::SharedPtr>("node");
  callback_group_ = node_->create_callback_group(
    rclcpp::CallbackGroupType::MutuallyExclusive, false);
  callback_group_executor_.add_callback_group(callback_group_, node_->get_node_base_interface());

  std::string person_topic, tof_topic;
  getInput("person_topic", person_topic);
  getInput("tof_topic", tof_topic);
  rclcpp::SubscriptionOptions options;
  options.callback_group = callback_group_;
  person_sub_ = node_->create_subscription<geometry_msgs::msg::PointStamped>(
    person_topic, rclcpp::QoS(PERSON_QUEUE),
    [this](geometry_msgs::msg::PointStamped::SharedPtr msg) {onPerson(*msg);}, options);
  // ToF는 10 Hz로 늘 나오므로 마지막 값만 본다
  tof_sub_ = node_->create_subscription<std_msgs::msg::Bool>(
    tof_topic, rclcpp::QoS(1),
    [this](std_msgs::msg::Bool::SharedPtr msg) {tof_ahead_ = msg->data;}, options);
}

void IsPersonAheadCondition::onPerson(const geometry_msgs::msg::PointStamped & msg)
{
  double min_distance = 0.8, max_distance = 3.0, half_width = 1.0;
  getInput("min_distance", min_distance);
  getInput("max_distance", max_distance);
  getInput("half_width", half_width);

  const auto clock_type = node_->get_clock()->get_clock_type();
  const rclcpp::Time stamp(msg.header.stamp, clock_type);
  const auto & p = msg.point;
  // 로봇 기준 위치가 줄어들면 다가옴. 로봇이 앞으로 가는 것도 섞이지만, 앞에 서 있는 사람도 기다릴 대상이다
  bool approaching = false;
  if (previous_) {
    const double dt = (stamp - rclcpp::Time(previous_->header.stamp, clock_type)).seconds();
    approaching = dt > 0.0 && dt <= MAX_PAIR_GAP_SEC && p.x < previous_->point.x;
  }
  previous_ = msg;
  if (approaching && p.x >= min_distance && p.x <= max_distance && std::abs(p.y) < half_width) {
    last_seen_ = stamp;
    last_seen_point_ = p;
  }
}

BT::NodeStatus IsPersonAheadCondition::tick()
{
  callback_group_executor_.spin_some();

  double memory_sec = 5.0;
  getInput("memory_sec", memory_sec);
  const double since = last_seen_ ? (node_->now() - *last_seen_).seconds() : INFINITY;
  const bool seen = since <= memory_sec;
  const bool ahead = seen && tof_ahead_;
  if (shouldLog(ahead)) {
    RCLCPP_INFO(
      node_->get_logger(), "IsPersonAhead: %s (카메라 %s: %.1f s 전 x=%.2f y=%.2f, ToF %s)",
      ahead ? "사람 → 기다림" : "아님 → 복구", seen ? "봄" : "못 봄", since,
      last_seen_point_.x, last_seen_point_.y, tof_ahead_ ? "막힘" : "비었음");
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
