// 사람 비용 층 (local costmap 전용).
// person_detector의 예측(/person_detector/predictions)을 받아
//   - 현재 위치와 lethal_time 안의 예측점은 몸 반경 안을 치명(LETHAL)으로,
//   - 그 뒤 예측점은 시간이 멀수록 낮아지는 가우시안 비용으로
// 칠한다. 치명 비용은 뒤에 오는 inflation 층이 로봇 반경만큼 부풀린다.
// 왜 치명이 필요한가: MPPI 장애물 critic은 치명(254)만 "충돌"로 보고 그 밖은 가중치로만 본다.
// 2026-10-13 복도 실험에서 최고 비용 220으로는 로봇이 사람을 뚫는 궤적을 골랐다 (KNOWN_ISSUES 2번).

#include "limbo_navigation/human_layer.hpp"

#include <algorithm>
#include <cmath>
#include <functional>

#include "nav2_costmap_2d/cost_values.hpp"
#include "pluginlib/class_list_macros.hpp"

namespace limbo_navigation
{

void HumanLayer::Bounds::add(double x, double y, double r)
{
  if (!valid) {
    min_x = x - r; min_y = y - r; max_x = x + r; max_y = y + r;
    valid = true;
    return;
  }
  min_x = std::min(min_x, x - r);
  min_y = std::min(min_y, y - r);
  max_x = std::max(max_x, x + r);
  max_y = std::max(max_y, y + r);
}

void HumanLayer::onInitialize()
{
  auto node = node_.lock();
  if (!node) {
    throw std::runtime_error("HumanLayer: failed to lock parent node");
  }
  readParameters();

  prediction_sub_ = node->create_subscription<PredictionArray>(
    "/person_detector/predictions", rclcpp::QoS(10),
    std::bind(&HumanLayer::predictionCallback, this, std::placeholders::_1));
  current_ = true;

  RCLCPP_INFO(
    node->get_logger(),
    "HumanLayer: lethal radius %.2f m within %.2f s, gaussian radius %.2f m (sigma %.2f), peak %.0f -> %.0f",
    config_.lethal_radius, config_.lethal_time, config_.radius, config_.sigma,
    config_.near_peak_cost, config_.far_peak_cost);
}

void HumanLayer::readParameters()
{
  auto node = node_.lock();
  auto read = [&](const char * name, double & value) {
      declareParameter(name, rclcpp::ParameterValue(value));
      node->get_parameter(name_ + "." + name, value);
    };
  declareParameter("enabled", rclcpp::ParameterValue(true));
  node->get_parameter(name_ + ".enabled", enabled_);
  read("lethal_radius", config_.lethal_radius);
  read("lethal_time", config_.lethal_time);
  read("radius", config_.radius);
  read("sigma", config_.sigma);
  read("near_peak_cost", config_.near_peak_cost);
  read("far_peak_cost", config_.far_peak_cost);
  read("min_prediction_time", config_.min_prediction_time);
  read("max_prediction_time", config_.max_prediction_time);
  read("min_cost", config_.min_cost);
  read("max_prediction_age", config_.max_prediction_age);
  auto read_bool = [&](const char * name, bool & value) {
      declareParameter(name, rclcpp::ParameterValue(value));
      node->get_parameter(name_ + "." + name, value);
    };
  read_bool("current_lethal", config_.current_lethal);
  read_bool("use_predictions", config_.use_predictions);
  read("standing_speed", config_.standing_speed);
  read("standing_peak_cost", config_.standing_peak_cost);
  read("standing_radius", config_.standing_radius);
  read("standing_sigma", config_.standing_sigma);
  read("walking_peak_cost", config_.walking_peak_cost);
  read("walking_radius", config_.walking_radius);
  read("walking_sigma", config_.walking_sigma);
  paint_radius_ = std::max({config_.radius, config_.lethal_radius,
      config_.current_lethal ? 0.0 : std::max(config_.standing_radius, config_.walking_radius)});
}

void HumanLayer::predictionCallback(const PredictionArray::SharedPtr msg)
{
  std::lock_guard<std::mutex> lock(prediction_mutex_);
  latest_predictions_ = msg;
}

// 최신 예측이 max_prediction_age보다 오래됐으면 없는 것으로 본다.
// person_detector는 그 프레임에서 본 사람만 보내므로, 오래된 메시지를 쓰면 사라진 사람이 남는다
HumanLayer::PredictionArray::SharedPtr HumanLayer::takeFreshPredictions()
{
  PredictionArray::SharedPtr predictions;
  {
    std::lock_guard<std::mutex> lock(prediction_mutex_);
    predictions = latest_predictions_;
  }
  auto node = node_.lock();
  if (!predictions || !node) {
    return nullptr;
  }
  const auto age = node->get_clock()->now() -
    rclcpp::Time(predictions->header.stamp, RCL_ROS_TIME);
  if (age.nanoseconds() < 0 || age.seconds() > config_.max_prediction_age) {
    return nullptr;
  }
  return predictions;
}

HumanLayer::Bounds HumanLayer::predictionBounds(const PredictionArray & predictions) const
{
  Bounds bounds;
  for (const auto & person : predictions.predictions) {
    bounds.add(person.current_position.x, person.current_position.y, paint_radius_);
    for (const auto & point : person.predicted_positions) {
      bounds.add(point.x, point.y, paint_radius_);
    }
  }
  return bounds;
}

void HumanLayer::updateBounds(
  double /*robot_x*/, double /*robot_y*/, double /*robot_yaw*/,
  double * min_x, double * min_y, double * max_x, double * max_y)
{
  if (!enabled_) {
    return;
  }
  cycle_predictions_ = takeFreshPredictions();

  // 이전 주기 영역을 먼저 넣어야 움직인 사람의 옛 비용이 이번 주기에 지워진다
  if (previous_bounds_.valid) {
    *min_x = std::min(*min_x, previous_bounds_.min_x);
    *min_y = std::min(*min_y, previous_bounds_.min_y);
    *max_x = std::max(*max_x, previous_bounds_.max_x);
    *max_y = std::max(*max_y, previous_bounds_.max_y);
  }

  Bounds current;
  if (cycle_predictions_) {
    current = predictionBounds(*cycle_predictions_);
  }
  if (current.valid) {
    *min_x = std::min(*min_x, current.min_x);
    *min_y = std::min(*min_y, current.min_y);
    *max_x = std::max(*max_x, current.max_x);
    *max_y = std::max(*max_y, current.max_y);
  }
  previous_bounds_ = current;
}

void HumanLayer::updateCosts(
  nav2_costmap_2d::Costmap2D & master_grid,
  int min_i, int min_j, int max_i, int max_j)
{
  if (!enabled_ || !cycle_predictions_) {
    return;
  }
  modified_cells_ = 0;
  const CellRange range{min_i, min_j, max_i, max_j};
  for (const auto & person : cycle_predictions_->predictions) {
    paintPerson(master_grid, range, person);
  }

  auto node = node_.lock();
  if (node) {
    RCLCPP_DEBUG_THROTTLE(
      node->get_logger(), *node->get_clock(), 2000,
      "HumanLayer: people=%zu, modified cells=%zu",
      cycle_predictions_->predictions.size(), modified_cells_);
  }
}

// 가까운 미래(min_prediction_time)는 near_peak_cost, 먼 미래(max_prediction_time)는 far_peak_cost. 사이는 선형
double HumanLayer::peakCostAt(double time_offset) const
{
  const double span = config_.max_prediction_time - config_.min_prediction_time;
  const double ratio = span > 0.0 ?
    std::clamp((time_offset - config_.min_prediction_time) / span, 0.0, 1.0) : 0.0;
  return config_.near_peak_cost + ratio * (config_.far_peak_cost - config_.near_peak_cost);
}

void HumanLayer::paintPerson(
  nav2_costmap_2d::Costmap2D & grid, const CellRange & range,
  const limbo_interfaces::msg::PersonPrediction & person)
{
  if (!config_.current_lethal) {
    // 전역 "통행료" 모드(2-8): 현재 위치만, 치명 아님. 서 있는 사람은 로봇이 갈 때까지 거기 있을 확률이 높아 비싸고,
    // 걷는 사람은 곧 비키니 싸다. 예측 경로는 쓰지 않는다(군중에서 길을 없앰)
    const double speed = std::hypot(person.velocity.x, person.velocity.y);
    const bool standing = speed < config_.standing_speed;
    paintCircle(
      grid, range, person.current_position.x, person.current_position.y, false,
      standing ? config_.standing_peak_cost : config_.walking_peak_cost,
      standing ? config_.standing_radius : config_.walking_radius,
      standing ? config_.standing_sigma : config_.walking_sigma);
    if (!config_.use_predictions) {
      return;
    }
  } else {
    // 현재 위치: 사람이 지금 서 있는 곳이라 항상 치명
    paintCircle(
      grid, range, person.current_position.x, person.current_position.y,
      true, config_.near_peak_cost, config_.radius, config_.sigma);
  }

  const std::size_t count =
    std::min(person.predicted_positions.size(), person.time_offsets.size());
  for (std::size_t i = 0; i < count; ++i) {
    const double t = person.time_offsets[i];
    if (t < config_.min_prediction_time || t > config_.max_prediction_time) {
      continue;
    }
    const auto & p = person.predicted_positions[i];
    paintCircle(grid, range, p.x, p.y, t <= config_.lethal_time, peakCostAt(t), config_.radius, config_.sigma);
  }
}

// (x, y) 둘레를 칠한다. lethal이면 lethal_radius 안은 LETHAL, 그 밖(radius까지)은 가우시안.
// 기존 비용(정적 지도·STVL)은 낮추지 않는다
void HumanLayer::paintCircle(
  nav2_costmap_2d::Costmap2D & grid, const CellRange & range,
  double x, double y, bool lethal, double peak_cost, double radius, double sigma)
{
  unsigned int center_mx, center_my;
  if (!grid.worldToMap(x, y, center_mx, center_my)) {
    return;
  }
  const int cell_radius = static_cast<int>(std::ceil(radius / grid.getResolution()));
  const int start_x = std::max(range.min_i, static_cast<int>(center_mx) - cell_radius);
  const int end_x = std::min(range.max_i, static_cast<int>(center_mx) + cell_radius + 1);
  const int start_y = std::max(range.min_j, static_cast<int>(center_my) - cell_radius);
  const int end_y = std::min(range.max_j, static_cast<int>(center_my) + cell_radius + 1);
  const double two_sigma_sq = 2.0 * sigma * sigma;

  for (int my = start_y; my < end_y; ++my) {
    for (int mx = start_x; mx < end_x; ++mx) {
      double wx, wy;
      grid.mapToWorld(static_cast<unsigned int>(mx), static_cast<unsigned int>(my), wx, wy);
      const double distance = std::hypot(wx - x, wy - y);

      double cost;
      if (lethal && distance <= config_.lethal_radius) {
        cost = nav2_costmap_2d::LETHAL_OBSTACLE;
      } else if (distance <= radius) {
        cost = peak_cost * std::exp(-(distance * distance) / two_sigma_sq);
        if (cost < config_.min_cost) {
          continue;
        }
      } else {
        continue;
      }

      const auto new_cost = static_cast<unsigned char>(
        std::min(std::round(cost), static_cast<double>(nav2_costmap_2d::LETHAL_OBSTACLE)));
      const auto mx_u = static_cast<unsigned int>(mx);
      const auto my_u = static_cast<unsigned int>(my);
      if (grid.getCost(mx_u, my_u) < new_cost) {
        grid.setCost(mx_u, my_u, new_cost);
        modified_cells_++;
      }
    }
  }
}

void HumanLayer::reset()
{
  std::lock_guard<std::mutex> lock(prediction_mutex_);
  latest_predictions_.reset();
  cycle_predictions_.reset();
  previous_bounds_ = Bounds{};
  current_ = true;
}

}  // namespace limbo_navigation

PLUGINLIB_EXPORT_CLASS(limbo_navigation::HumanLayer, nav2_costmap_2d::Layer)
