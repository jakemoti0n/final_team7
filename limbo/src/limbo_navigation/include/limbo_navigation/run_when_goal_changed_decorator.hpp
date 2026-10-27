#pragma once

#include <optional>
#include <string>

#include "behaviortree_cpp/decorator_node.h"
#include "builtin_interfaces/msg/time.hpp"
#include "geometry_msgs/msg/pose_stamped.hpp"
#include "nav_msgs/msg/path.hpp"
#include "rclcpp/rclcpp.hpp"

namespace limbo_navigation
{

// 따라가기 트리에서 FollowPath를 "시간이 지나면"이 아니라 "할 일이 생겼을 때" 다시 걸기 위한 데코레이터 (PROJECT.md 2-9).
// 자식(FollowPath)을 거는 조건: 마지막으로 걸었을 때와 다른 **새 경로**(path의 stamp)가 와 있고, 그러면서
//   - 목표(goal)가 자식이 마지막으로 성공했을 때의 목표와 다르거나        → 운용자가 움직였다, 돌아볼 방향이 생겼다
//   - 자식이 성공으로 끝나지 못했다(실패·기다리기로 중단)                → 새 경로로 다시 시도
// 둘 다 아니면 자식을 건드리지 않고 FAILURE("할 일 없음")를 돌려준다. 트리에서는 ForceSuccess로 감싸 쓴다.
// 서 있을 때(목표 = 로봇 자리) 0.5 s마다 FollowPath를 다시 걸어 MPPI가 초기화되던 것과, 계획 실패 Wait와 추종 뒤 Wait가
// behavior_server에서 서로 선점해 트리 전체가 죽던 것(3단계 fw16)을 타이머 없이 없앤다. 다시 시도하는 주기는 따로 두지 않고
// 재계획 주기(RateController 4 Hz)가 새 경로를 주는 때를 따른다. 계획이 실패해 경로가 비면(Nav2가 비운다) 서 있는다.
class RunWhenGoalChangedDecorator : public BT::DecoratorNode
{
public:
  RunWhenGoalChangedDecorator(const std::string & name, const BT::NodeConfiguration & conf);
  RunWhenGoalChangedDecorator() = delete;

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<geometry_msgs::msg::PoseStamped>("goal", "지금 목표점 (GoalUpdater의 output_goal)"),
      BT::InputPort<nav_msgs::msg::Path>("path", "지금 경로 (ComputePathToPose의 path). stamp가 바뀌면 새 경로"),
    };
  }

  BT::NodeStatus tick() override;
  // 기다리기(IsWaitingForPerson)로 중단되면 last_run_succeeded_가 false인 채라 새 경로가 오면 다시 건다 (halt 재정의 불필요)

private:
  rclcpp::Node::SharedPtr node_;
  builtin_interfaces::msg::Time last_run_path_stamp_;           // 자식을 마지막으로 걸었을 때의 경로 stamp (0 = 아직 없음)
  geometry_msgs::msg::Pose last_run_goal_;                      // 그때의 목표
  std::optional<geometry_msgs::msg::Pose> last_success_goal_;   // 자식이 마지막으로 성공했을 때의 목표. 없으면 아직 한 번도 성공 안 함
  bool last_run_succeeded_{false};
};

}  // namespace limbo_navigation
