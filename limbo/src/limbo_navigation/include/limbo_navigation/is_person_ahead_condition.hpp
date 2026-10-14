#pragma once

#include <optional>
#include <string>

#include "behaviortree_cpp/condition_node.h"
#include "geometry_msgs/msg/point_stamped.hpp"
#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/bool.hpp"

namespace limbo_navigation
{

// 막혔을 때 "방금 다가오던 사람이 지금 코앞에 있다"면 참. 복구 분기 앞에서 기다리기를 고른다 (PROJECT.md 2-2, R5).
// (A) 최근 memory_sec 안에 카메라가 앞쪽 min~max_distance, 폭 half_width 안에서 다가오는 사람을 봤고
// (B) 지금 ToF가 코앞에 무언가 있다고 할 때.
// 카메라는 1.5 m 안 사람을 거의 못 보고(R4), ToF는 사람·상자를 못 가른다. 둘 다여야 사람 때문에 막힌 것이다.
class IsPersonAheadCondition : public BT::ConditionNode
{
public:
  IsPersonAheadCondition(const std::string & name, const BT::NodeConfiguration & conf);
  IsPersonAheadCondition() = delete;

  BT::NodeStatus tick() override;

  static BT::PortsList providedPorts()
  {
    return {
      BT::InputPort<std::string>("person_topic", "/person_detector/person_position_base", "로봇 기준 가장 가까운 사람"),
      BT::InputPort<std::string>("tof_topic", "/tof/obstacle_ahead", "코앞에 무언가 있음"),
      BT::InputPort<double>("memory_sec", 5.0, "카메라로 본 사람을 기억하는 시간 (s)"),
      BT::InputPort<double>("min_distance", 0.8, "사람을 본 앞쪽 거리 하한 (m)"),
      BT::InputPort<double>("max_distance", 3.0, "사람을 본 앞쪽 거리 상한 (m)"),
      BT::InputPort<double>("half_width", 1.0, "사람을 본 좌우 폭 절반 (m)"),
    };
  }

private:
  void onPerson(const geometry_msgs::msg::PointStamped & msg);
  bool shouldLog(bool ahead);

  rclcpp::Node::SharedPtr node_;
  rclcpp::CallbackGroup::SharedPtr callback_group_;
  rclcpp::executors::SingleThreadedExecutor callback_group_executor_;
  rclcpp::Subscription<geometry_msgs::msg::PointStamped>::SharedPtr person_sub_;
  rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr tof_sub_;
  std::optional<geometry_msgs::msg::PointStamped> previous_;
  std::optional<rclcpp::Time> last_seen_;   // 조건에 맞는 다가오는 사람을 마지막으로 본 영상 시각
  geometry_msgs::msg::Point last_seen_point_;
  bool tof_ahead_{false};
  std::optional<bool> was_ahead_;
  rclcpp::Time last_log_{0, 0, RCL_ROS_TIME};
};

}  // namespace limbo_navigation
