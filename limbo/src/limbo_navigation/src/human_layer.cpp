#include "limbo_navigation/human_layer.hpp"

#include <functional>

#include "pluginlib/class_list_macros.hpp"


namespace limbo_navigation
{

void HumanLayer::onInitialize()
{
  auto node = node_.lock();

  if (!node) {
    throw std::runtime_error(
      "HumanLayer: failed to lock parent node"
    );
  }

  // HumanLayer 전용 파라미터 선언
  declareParameter(
    "enabled",
    rclcpp::ParameterValue(true)
  );

  // nav2_params.yaml의
  // human_layer.enabled 값을 읽음
  node->get_parameter(
    name_ + ".enabled",
    enabled_
  );


  prediction_sub_ =
    node->create_subscription<PredictionArray>(
      "/person_detector/predictions",
      rclcpp::QoS(10),

      std::bind(
        &HumanLayer::predictionCallback,
        this,
        std::placeholders::_1
      )
    );

  current_ = true;

  RCLCPP_INFO(
    node->get_logger(),
    "HumanLayer initialized. "
    "Subscribing to /person_detector/predictions"
  );
}


void HumanLayer::predictionCallback(
  const PredictionArray::SharedPtr msg)
{
  {
    std::lock_guard<std::mutex> lock(
      prediction_mutex_
    );

    latest_predictions_ = msg;
  }

  auto node = node_.lock();

  if (node) {
    RCLCPP_INFO_THROTTLE(
      node->get_logger(),
      *node->get_clock(),
      2000,
      "HumanLayer received %zu person predictions",
      msg->predictions.size()
    );
  }
}


void HumanLayer::updateBounds(
  double robot_x,
  double robot_y,
  double robot_yaw,
  double * min_x,
  double * min_y,
  double * max_x,
  double * max_y)
{
  // 이번 단계에서는 아직 cost를 추가하지 않음.
  // 파라미터 unused warning 방지
  (void)robot_x;
  (void)robot_y;
  (void)robot_yaw;
  (void)min_x;
  (void)min_y;
  (void)max_x;
  (void)max_y;
}


void HumanLayer::updateCosts(
  nav2_costmap_2d::Costmap2D & master_grid,
  int min_i,
  int min_j,
  int max_i,
  int max_j)
{
  // 다음 단계에서 여기에서 실제 cost를 기록할 예정
  (void)master_grid;
  (void)min_i;
  (void)min_j;
  (void)max_i;
  (void)max_j;
}


void HumanLayer::reset()
{
  std::lock_guard<std::mutex> lock(
    prediction_mutex_
  );

  latest_predictions_.reset();
}

}  // namespace limbo_navigation


PLUGINLIB_EXPORT_CLASS(
  limbo_navigation::HumanLayer,
  nav2_costmap_2d::Layer
)