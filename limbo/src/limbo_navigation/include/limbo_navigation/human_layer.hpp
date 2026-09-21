#pragma once

#include <memory>
#include <mutex>

#include "rclcpp/rclcpp.hpp"
#include "nav2_costmap_2d/layer.hpp"
#include "nav2_costmap_2d/costmap_2d.hpp"

#include "limbo_interfaces/msg/person_prediction_array.hpp"

namespace limbo_navigation
{

class HumanLayer : public nav2_costmap_2d::Layer
{
public:
  HumanLayer() = default;

  void onInitialize() override;

  void updateBounds(
    double robot_x,
    double robot_y,
    double robot_yaw,
    double * min_x,
    double * min_y,
    double * max_x,
    double * max_y) override;

  void updateCosts(
    nav2_costmap_2d::Costmap2D & master_grid,
    int min_i,
    int min_j,
    int max_i,
    int max_j) override;

  void reset() override;

  bool isClearable() override
  {
    return true;
  }

private:
  using PredictionArray =
    limbo_interfaces::msg::PersonPredictionArray;

  void predictionCallback(
    const PredictionArray::SharedPtr msg);

  rclcpp::Subscription<PredictionArray>::SharedPtr prediction_sub_;

  PredictionArray::SharedPtr latest_predictions_;

  std::mutex prediction_mutex_;

  // updateBounds()에서 선택한 prediction을
  // 같은 cycle의 updateCosts()에서도 사용하기 위한 snapshot
  PredictionArray::SharedPtr cycle_predictions_;

  // 이전 cycle에서 Human cost가 존재했던 영역
  bool has_previous_bounds_{false};

  double previous_min_x_{0.0};
  double previous_min_y_{0.0};
  double previous_max_x_{0.0};
  double previous_max_y_{0.0};
};

}  // namespace limbo_navigation