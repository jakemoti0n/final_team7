#include "limbo_navigation/is_waiting_for_person_condition.hpp"

#include <map>
#include <mutex>
#include <utility>

#include "behaviortree_cpp/bt_factory.h"

namespace limbo_navigation
{

struct IsWaitingForPersonCondition::Shared
{
  rclcpp::CallbackGroup::SharedPtr callback_group;
  rclcpp::executors::SingleThreadedExecutor executor;
  rclcpp::Subscription<limbo_interfaces::msg::PersonWait>::SharedPtr sub;
  bool waiting{false};
  std::string reason;
};

namespace
{
std::shared_ptr<IsWaitingForPersonCondition::Shared> sharedFor(
  const rclcpp::Node::SharedPtr & node, const std::string & topic)
{
  // bt_navigator는 navigator마다 BT 노드(rclcpp)가 따로라 노드·토픽으로 나눈다
  static std::mutex mutex;
  static std::map<std::pair<rclcpp::Node *, std::string>,
    std::weak_ptr<IsWaitingForPersonCondition::Shared>> table;
  std::lock_guard<std::mutex> lock(mutex);
  auto & slot = table[{node.get(), topic}];
  if (auto existing = slot.lock()) {
    return existing;
  }
  auto shared = std::make_shared<IsWaitingForPersonCondition::Shared>();
  // BT는 tick 때만 이 그룹을 돌린다. person_wait가 10 Hz로 늘 내므로 마지막 값만 본다
  shared->callback_group = node->create_callback_group(
    rclcpp::CallbackGroupType::MutuallyExclusive, false);
  shared->executor.add_callback_group(shared->callback_group, node->get_node_base_interface());
  rclcpp::SubscriptionOptions options;
  options.callback_group = shared->callback_group;
  auto * raw = shared.get();
  shared->sub = node->create_subscription<limbo_interfaces::msg::PersonWait>(
    topic, rclcpp::QoS(1),
    [raw](limbo_interfaces::msg::PersonWait::SharedPtr msg) {
      raw->waiting = msg->wait;
      raw->reason = msg->reason;
    }, options);
  slot = shared;
  return shared;
}
}  // namespace

IsWaitingForPersonCondition::IsWaitingForPersonCondition(
  const std::string & name, const BT::NodeConfiguration & conf)
: BT::ConditionNode(name, conf)
{
  node_ = config().blackboard->get<rclcpp::Node::SharedPtr>("node");
  std::string topic;
  getInput("topic", topic);
  shared_ = sharedFor(node_, topic);
}

BT::NodeStatus IsWaitingForPersonCondition::tick()
{
  shared_->executor.spin_some();
  const bool waiting = shared_->waiting;
  if (shouldLog(waiting)) {
    RCLCPP_INFO(
      node_->get_logger(), "IsWaitingForPerson(%s): %s (%s)", name().c_str(),
      waiting ? "참 → 멈춤·기다림" : "거짓 → 주행", shared_->reason.c_str());
  }
  return waiting ? BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}

// 주행 중 매 tick(10 ms) 불리므로 판단이 바뀔 때만 남긴다
bool IsWaitingForPersonCondition::shouldLog(bool waiting)
{
  if (was_waiting_ == waiting) {
    return false;
  }
  was_waiting_ = waiting;
  return true;
}

}  // namespace limbo_navigation

BT_REGISTER_NODES(factory)
{
  factory.registerNodeType<limbo_navigation::IsWaitingForPersonCondition>("IsWaitingForPerson");
}
