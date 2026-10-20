#pragma once

#include <memory>
#include <optional>
#include <string>

#include "behaviortree_cpp/condition_node.h"
#include "limbo_interfaces/msg/person_wait.hpp"
#include "rclcpp/rclcpp.hpp"

namespace limbo_navigation
{

// 사람 때문에 기다려야 하면 참. BT가 경로 추종·계획·복구 자리에서 멈추고 기다리는 데 쓴다 (PROJECT.md 2-7).
// 판단은 person_wait 노드의 상태 기계 하나가 하고(/person_wait의 wait), 이 노드는 그 결정을 그대로 옮긴다.
// 기다릴지를 BT 안에서 다시 따지지 않아야 "왜 안 움직이나"를 한 곳(person_wait 로그)에서 설명할 수 있다.
class IsWaitingForPersonCondition : public BT::ConditionNode
{
public:
  IsWaitingForPersonCondition(const std::string & name, const BT::NodeConfiguration & conf);
  IsWaitingForPersonCondition() = delete;

  BT::NodeStatus tick() override;

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<std::string>("topic", "/person_wait", "사람 기다리기 결정 (person_wait 노드)"),
    };
  }

  // 한 트리에 이 노드가 여러 개(멈추기·costmap 비우기 막기·기다리기·복구 막기) 있으므로 구독은 BT 노드(rclcpp)·토픽마다
  // 하나만 두고 같이 본다. 따로 구독하면 같은 tick에 서로 다른 값을 봐서, 멈춘 뒤 기다리지 않고 목표가 실패한다 (R5 Q3 시험)
  struct Shared;

private:
  bool shouldLog(bool waiting);

  rclcpp::Node::SharedPtr node_;
  std::shared_ptr<Shared> shared_;
  std::optional<bool> was_waiting_;
};

}  // namespace limbo_navigation
