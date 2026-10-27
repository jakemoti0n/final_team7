#include "limbo_navigation/run_when_goal_changed_decorator.hpp"

#include "behaviortree_cpp/bt_factory.h"

namespace limbo_navigation
{

namespace
{
bool samePose(const geometry_msgs::msg::Pose & a, const geometry_msgs::msg::Pose & b)
{
  // follow_node는 목표가 바뀔 때만 새 메시지를 보내므로 값 그대로 비교하면 된다 (문턱은 follow_node의 goal_min_move 한 곳에만)
  return a.position.x == b.position.x && a.position.y == b.position.y && a.position.z == b.position.z &&
         a.orientation.x == b.orientation.x && a.orientation.y == b.orientation.y &&
         a.orientation.z == b.orientation.z && a.orientation.w == b.orientation.w;
}
}  // namespace

RunWhenGoalChangedDecorator::RunWhenGoalChangedDecorator(
  const std::string & name, const BT::NodeConfiguration & conf)
: BT::DecoratorNode(name, conf)
{
  node_ = config().blackboard->get<rclcpp::Node::SharedPtr>("node");
}

BT::NodeStatus RunWhenGoalChangedDecorator::tick()
{
  if (child_node_->status() != BT::NodeStatus::RUNNING) {
    geometry_msgs::msg::PoseStamped goal;
    nav_msgs::msg::Path path;
    getInput("goal", goal);
    getInput("path", path);
    // 경로가 아직 없거나 계획이 실패해 빈 경로가 들어왔으면(ComputePathToPose는 실패 시 path를 비운다) 걸 것이 없다
    const bool new_path = !path.poses.empty() && path.header.stamp != last_run_path_stamp_;
    const bool goal_changed = !last_success_goal_ || !samePose(*last_success_goal_, goal.pose);
    if (!new_path || !(goal_changed || !last_run_succeeded_)) {
      return BT::NodeStatus::FAILURE;   // 할 일 없음 (서 있는 중이거나, 아직 새 경로가 안 옴)
    }
    if (!goal_changed) {
      RCLCPP_INFO(node_->get_logger(), "RunWhenGoalChanged(%s): 추종이 끝나지 못한 뒤 새 경로 → 다시 추종", name().c_str());
    } else {
      RCLCPP_DEBUG(node_->get_logger(), "RunWhenGoalChanged(%s): 목표가 바뀜 → 추종", name().c_str());
    }
    last_run_path_stamp_ = path.header.stamp;
    last_run_goal_ = goal.pose;
    last_run_succeeded_ = false;
  }
  const auto status = child_node_->executeTick();
  switch (status) {
    case BT::NodeStatus::RUNNING:
      return BT::NodeStatus::RUNNING;
    case BT::NodeStatus::SUCCESS:
      last_success_goal_ = last_run_goal_;
      last_run_succeeded_ = true;
      resetChild();
      return BT::NodeStatus::SUCCESS;
    case BT::NodeStatus::FAILURE:
      resetChild();
      return BT::NodeStatus::FAILURE;
    default:
      throw BT::LogicError("RunWhenGoalChanged: 자식이 IDLE/SKIPPED를 돌려줌");
  }
}

}  // namespace limbo_navigation

BT_REGISTER_NODES(factory)
{
  factory.registerNodeType<limbo_navigation::RunWhenGoalChangedDecorator>("RunWhenGoalChanged");
}
