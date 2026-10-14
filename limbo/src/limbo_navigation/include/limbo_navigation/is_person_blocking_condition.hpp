#pragma once

#include <memory>
#include <optional>
#include <string>

#include "behaviortree_cpp/condition_node.h"
#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/bool.hpp"

namespace limbo_navigation
{

// 사람 때문에 막혔으면 참. BT가 경로 추종 자리에서 FollowPath를 멈추고 기다리는 데 쓴다 (PROJECT.md 2-1·2-2, R5 Q3).
// 판단은 tof_node의 /person_blocking이 막히기 시작한 순간에 정해 둔다(카메라 기억 + ToF 래치, R5 Q2).
class IsPersonBlockingCondition : public BT::ConditionNode
{
public:
  IsPersonBlockingCondition(const std::string & name, const BT::NodeConfiguration & conf);
  IsPersonBlockingCondition() = delete;

  BT::NodeStatus tick() override;

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<std::string>("topic", "/person_blocking", "사람 때문에 막힘 (tof_node 래치)"),
    };
  }

  // 한 트리에 이 노드가 여러 개(멈추기·costmap 비우기 막기·기다리기) 있으므로 구독은 BT 노드(rclcpp)·토픽마다 하나만 두고
  // 같이 본다. 따로 구독하면 막힌 순간 서로 다른 값을 봐서, 멈춘 뒤 기다리지 않고 목표가 실패한다 (R5 Q3 시험)
  struct Shared;

private:
  bool shouldLog(bool blocking);

  rclcpp::Node::SharedPtr node_;
  std::shared_ptr<Shared> shared_;
  std::optional<bool> was_blocking_;
};

}  // namespace limbo_navigation
