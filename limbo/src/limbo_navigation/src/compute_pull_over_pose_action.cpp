#include "limbo_navigation/compute_pull_over_pose_action.hpp"

#include <cmath>

#include "behaviortree_cpp/bt_factory.h"
#include "tf2/utils.h"
#include "tf2_geometry_msgs/tf2_geometry_msgs.hpp"

namespace limbo_navigation
{

namespace
{
constexpr unsigned char LETHAL = 254;      // nav2_costmap_2d LETHAL_OBSTACLE
constexpr unsigned char INSCRIBED = 253;   // INSCRIBED_INFLATED_OBSTACLE
constexpr double SAMPLE = 0.05;            // 외곽·여유 검사 간격 (m), costmap 해상도와 같게
}

ComputePullOverPose::ComputePullOverPose(
  const std::string & name, const BT::NodeConfiguration & conf)
: BT::SyncActionNode(name, conf)
{
  node_ = config().blackboard->get<rclcpp::Node::SharedPtr>("node");
  tf_ = config().blackboard->get<std::shared_ptr<tf2_ros::Buffer>>("tf_buffer");
  group_ = node_->create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive, false);
  executor_.add_callback_group(group_, node_->get_node_base_interface());
  rclcpp::SubscriptionOptions options;
  options.callback_group = group_;

  std::string costmap_topic, approach_topic, predictions_topic;
  getInput("costmap_topic", costmap_topic);
  getInput("approach_topic", approach_topic);
  getInput("predictions_topic", predictions_topic);
  costmap_sub_ = node_->create_subscription<nav2_msgs::msg::Costmap>(
    costmap_topic, rclcpp::QoS(1),
    [this](nav2_msgs::msg::Costmap::SharedPtr msg) {costmap_ = msg;}, options);
  // 다가옴이 끝나면 다음 사람을 위해 "이미 시도함"을 지운다. 10 Hz로 늘 오므로 마지막 값만 본다
  approach_sub_ = node_->create_subscription<std_msgs::msg::Bool>(
    approach_topic, rclcpp::QoS(1),
    [this](std_msgs::msg::Bool::SharedPtr msg) {
      approaching_ = msg->data;
      if (!approaching_) {
        tried_ = false;
      }
    }, options);
  predictions_sub_ = node_->create_subscription<limbo_interfaces::msg::PersonPredictionArray>(
    predictions_topic, rclcpp::QoS(1),
    [this](limbo_interfaces::msg::PersonPredictionArray::SharedPtr msg) {
      if (!msg->predictions.empty()) {predictions_ = msg;}
    }, options);
}

double ComputePullOverPose::cost(double base_x, double base_y)
{
  const auto & m = costmap_->metadata;
  const double wx = rx_ + std::cos(ryaw_) * base_x - std::sin(ryaw_) * base_y;
  const double wy = ry_ + std::sin(ryaw_) * base_x + std::cos(ryaw_) * base_y;
  const int cx = static_cast<int>(std::floor((wx - m.origin.position.x) / m.resolution));
  const int cy = static_cast<int>(std::floor((wy - m.origin.position.y) / m.resolution));
  if (cx < 0 || cy < 0 || cx >= static_cast<int>(m.size_x) || cy >= static_cast<int>(m.size_y)) {
    return -1.0;
  }
  return costmap_->data[cy * m.size_x + cx];
}

bool ComputePullOverPose::acceptable(double x, double y)
{
  double half_width = 0.295, half_length = 0.25, margin = 0.1;
  getInput("half_width", half_width);
  getInput("half_length", half_length);
  getInput("margin", margin);

  // 중심: inscribed 미만 (원형 로봇 기준으로도 충돌이 아닌 자리)
  const double center = cost(x, y);
  if (center < 0.0 || center >= INSCRIBED) {
    return false;
  }
  // 외곽 안: 실제 장애물 없음
  for (double dx = -half_length; dx <= half_length + 1e-6; dx += SAMPLE) {
    for (double dy = -half_width; dy <= half_width + 1e-6; dy += SAMPLE) {
      const double c = cost(x + dx, y + dy);
      if (c < 0.0 || c >= LETHAL) {
        return false;
      }
    }
  }
  // 중심에서 치명 칸까지 반폭 + margin 이상 (벽·사람 몸에 붙지 않게, e462868 ④)
  const double clearance = half_width + margin;
  for (double dx = -clearance; dx <= clearance + 1e-6; dx += SAMPLE) {
    for (double dy = -clearance; dy <= clearance + 1e-6; dy += SAMPLE) {
      if (std::hypot(dx, dy) <= clearance && cost(x + dx, y + dy) >= LETHAL) {
        return false;
      }
    }
  }
  return true;
}

int ComputePullOverPose::personSide()
{
  if (!predictions_) {
    return 0;
  }
  std::string base_frame;
  getInput("base_frame", base_frame);
  double best = 1e9;
  int side = 0;
  for (const auto & p : predictions_->predictions) {
    geometry_msgs::msg::PointStamped in, out;
    in.header.frame_id = predictions_->header.frame_id;
    in.point = p.current_position;
    try {
      out = tf_->transform(in, base_frame, tf2::durationFromSec(0.1));
    } catch (const tf2::TransformException &) {
      continue;
    }
    // 앞쪽 사람 중 가장 가까운 사람
    const double d = std::hypot(out.point.x, out.point.y);
    if (out.point.x > 0.0 && d < best) {
      best = d;
      side = out.point.y >= 0.0 ? 1 : -1;
    }
  }
  return side;
}

BT::NodeStatus ComputePullOverPose::tick()
{
  executor_.spin_some();
  // 이 노드는 막혔을 때만 불려서 그 사이 "다가옴 끝" 메시지를 놓칠 수 있다.
  // 같은 사람 앞에서 기다리는 동안은 1 s마다 불리므로, 3 s 넘게 안 불렸으면 새 사람으로 본다
  const auto now = node_->now();
  if (last_tick_ && (now - *last_tick_).seconds() > 3.0) {
    tried_ = false;
  }
  last_tick_ = now;
  if (!approaching_ || tried_ || !costmap_) {
    return BT::NodeStatus::FAILURE;
  }
  tried_ = true;   // 자리가 있든 없든 이번 사람에 한 번만

  std::string base_frame, global_frame;
  getInput("base_frame", base_frame);
  getInput("global_frame", global_frame);
  std::vector<double> offsets;
  getInput("side_offsets", offsets);
  double forward = 0.3;
  getInput("forward", forward);

  geometry_msgs::msg::TransformStamped robot;
  try {
    robot = tf_->lookupTransform(costmap_->header.frame_id, base_frame, tf2::TimePointZero);
  } catch (const tf2::TransformException & ex) {
    RCLCPP_WARN(node_->get_logger(), "ComputePullOverPose: TF %s", ex.what());
    return BT::NodeStatus::FAILURE;
  }
  rx_ = robot.transform.translation.x;
  ry_ = robot.transform.translation.y;
  ryaw_ = tf2::getYaw(robot.transform.rotation);

  // 사람이 오는 쪽의 반대쪽을 먼저, 모르면 오른쪽(-1) 먼저 (Q12)
  const int person = personSide();
  const int first = person > 0 ? -1 : (person < 0 ? 1 : -1);
  std::optional<double> chosen_y;
  for (int side : {first, -first}) {
    for (double offset : offsets) {
      if (acceptable(forward, side * offset)) {
        chosen_y = side * offset;
        break;
      }
    }
    if (chosen_y) {
      break;
    }
  }
  if (!chosen_y) {
    RCLCPP_INFO(node_->get_logger(), "ComputePullOverPose: 비킬 자리 없음 → 그 자리 정지");
    return BT::NodeStatus::FAILURE;
  }

  geometry_msgs::msg::PoseStamped local, global;
  local.header.frame_id = base_frame;
  local.header.stamp = rclcpp::Time(0);
  local.pose.position.x = forward;
  local.pose.position.y = *chosen_y;
  local.pose.orientation.w = 1.0;
  try {
    global = tf_->transform(local, global_frame, tf2::durationFromSec(0.1));
  } catch (const tf2::TransformException & ex) {
    RCLCPP_WARN(node_->get_logger(), "ComputePullOverPose: TF %s", ex.what());
    return BT::NodeStatus::FAILURE;
  }
  global.header.stamp = node_->now();
  setOutput("pose", global);
  RCLCPP_INFO(
    node_->get_logger(), "ComputePullOverPose: %s으로 %.2f m 비킴 (사람 %s)",
    *chosen_y > 0 ? "왼쪽" : "오른쪽", std::abs(*chosen_y),
    person > 0 ? "왼쪽" : (person < 0 ? "오른쪽" : "모름"));
  return BT::NodeStatus::SUCCESS;
}

}  // namespace limbo_navigation

BT_REGISTER_NODES(factory)
{
  factory.registerNodeType<limbo_navigation::ComputePullOverPose>("ComputePullOverPose");
}
