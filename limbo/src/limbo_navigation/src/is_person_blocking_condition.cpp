#include "limbo_navigation/is_person_blocking_condition.hpp"

#include <map>
#include <mutex>
#include <utility>

#include "behaviortree_cpp/bt_factory.h"

namespace limbo_navigation
{

struct IsPersonBlockingCondition::Shared
{
  rclcpp::CallbackGroup::SharedPtr callback_group;
  rclcpp::executors::SingleThreadedExecutor executor;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr sub;
  bool blocking{false};
};

namespace
{
std::shared_ptr<IsPersonBlockingCondition::Shared> sharedFor(
  const rclcpp::Node::SharedPtr & node, const std::string & topic)
{
  // bt_navigator는 navigator마다 BT 노드(rclcpp)가 따로라 노드·토픽으로 나눈다
  static std::mutex mutex;
  static std::map<std::pair<rclcpp::Node *, std::string>,
    std::weak_ptr<IsPersonBlockingCondition::Shared>> table;
  std::lock_guard<std::mutex> lock(mutex);
  auto & slot = table[{node.get(), topic}];
  if (auto existing = slot.lock()) {
    return existing;
  }
  auto shared = std::make_shared<IsPersonBlockingCondition::Shared>();
  // BT는 tick 때만 이 그룹을 돌린다. tof_node가 10 Hz로 늘 내므로 마지막 값만 본다
  shared->callback_group = node->create_callback_group(
    rclcpp::CallbackGroupType::MutuallyExclusive, false);
  shared->executor.add_callback_group(shared->callback_group, node->get_node_base_interface());
  rclcpp::SubscriptionOptions options;
  options.callback_group = shared->callback_group;
  auto * raw = shared.get();
  shared->sub = node->create_subscription<std_msgs::msg::Bool>(
    topic, rclcpp::QoS(1),
    [raw](std_msgs::msg::Bool::SharedPtr msg) {raw->blocking = msg->data;}, options);
  slot = shared;
  return shared;
}
}  // namespace

IsPersonBlockingCondition::IsPersonBlockingCondition(
  const std::string & name, const BT::NodeConfiguration & conf)
: BT::ConditionNode(name, conf)
{
  node_ = config().blackboard->get<rclcpp::Node::SharedPtr>("node");
  std::string topic;
  getInput("topic", topic);
  shared_ = sharedFor(node_, topic);
}

BT::NodeStatus IsPersonBlockingCondition::tick()
{
  shared_->executor.spin_some();
  const bool blocking = shared_->blocking;
  if (shouldLog(blocking)) {
    RCLCPP_INFO(
      node_->get_logger(), "IsPersonBlocking(%s): %s", name().c_str(),
      blocking ? "참 → 멈춤·기다림" : "거짓 → 주행");
  }
  return blocking ? BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}

// 주행 중 매 tick(10 ms) 불리므로 판단이 바뀔 때만 남긴다
bool IsPersonBlockingCondition::shouldLog(bool blocking)
{
  if (was_blocking_ == blocking) {
    return false;
  }
  was_blocking_ = blocking;
  return true;
}

}  // namespace limbo_navigation

BT_REGISTER_NODES(factory)
{
  factory.registerNodeType<limbo_navigation::IsPersonBlockingCondition>("IsPersonBlocking");
  // 같은 "Bool 토픽이 참인가" 조건. 다가오는 사람(tof_node /person_approaching)에 쓴다 (전제 2-1, R5 Q4)
  factory.registerNodeType<limbo_navigation::IsPersonBlockingCondition>("IsPersonApproaching");
}
