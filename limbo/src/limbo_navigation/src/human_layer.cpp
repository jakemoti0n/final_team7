#include "limbo_navigation/human_layer.hpp"

#include <functional>
#include <algorithm>
#include <cmath>

#include "pluginlib/class_list_macros.hpp"


namespace limbo_navigation
{

namespace
{

// Human prediction cost를 계산할 최대 반경
constexpr double HUMAN_RADIUS = 0.35;

// Gaussian의 퍼짐 정도
constexpr double HUMAN_SIGMA = 0.15;

// 너무 작은 cost는 실제 costmap에 기록하지 않음
constexpr unsigned char MIN_HUMAN_COST = 10;

// 시간에 따른 Human cost
constexpr double MIN_PREDICTION_TIME = 0.25;
constexpr double MAX_PREDICTION_TIME = 2.0;

// 가장 가까운 미래의 중심 cost
constexpr double NEAR_PEAK_COST = 220.0;

// 가장 먼 미래의 중심 cost
constexpr double FAR_PEAK_COST = 110.0;

}  

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
  (void)robot_x;
  (void)robot_y;
  (void)robot_yaw;

  if (!enabled_) {
    return;
  }

  // ============================================================
  // 1. 이번 costmap cycle에서 사용할 prediction snapshot
  // ============================================================

  {
    std::lock_guard<std::mutex> lock(prediction_mutex_);
    cycle_predictions_ = latest_predictions_;
  }

  // ============================================================
  // 2. 현재 prediction들의 bounds 계산
  // ============================================================

  bool has_current_bounds = false;

  double current_min_x = 0.0;
  double current_min_y = 0.0;
  double current_max_x = 0.0;
  double current_max_y = 0.0;

  if (cycle_predictions_) {

    for (const auto & person : cycle_predictions_->predictions) {

      for (const auto & point : person.predicted_positions) {

        const double point_min_x =
          point.x - HUMAN_RADIUS;

        const double point_min_y =
          point.y - HUMAN_RADIUS;

        const double point_max_x =
          point.x + HUMAN_RADIUS;

        const double point_max_y =
          point.y + HUMAN_RADIUS;

        if (!has_current_bounds) {

          current_min_x = point_min_x;
          current_min_y = point_min_y;
          current_max_x = point_max_x;
          current_max_y = point_max_y;

          has_current_bounds = true;
        }
        else {

          current_min_x =
            std::min(current_min_x, point_min_x);

          current_min_y =
            std::min(current_min_y, point_min_y);

          current_max_x =
            std::max(current_max_x, point_max_x);

          current_max_y =
            std::max(current_max_y, point_max_y);
        }
      }
    }
  }

  // ============================================================
  // 3. 이전 cycle 영역도 update 대상에 포함
  //
  // 사람이 이동했을 때 이전 cost를 지우기 위해 필요
  // ============================================================

  if (has_previous_bounds_) {

    *min_x = std::min(
      *min_x,
      previous_min_x_
    );

    *min_y = std::min(
      *min_y,
      previous_min_y_
    );

    *max_x = std::max(
      *max_x,
      previous_max_x_
    );

    *max_y = std::max(
      *max_y,
      previous_max_y_
    );
  }

  // ============================================================
  // 4. 현재 prediction 영역도 update 대상에 포함
  // ============================================================

  if (has_current_bounds) {

    *min_x = std::min(
      *min_x,
      current_min_x
    );

    *min_y = std::min(
      *min_y,
      current_min_y
    );

    *max_x = std::max(
      *max_x,
      current_max_x
    );

    *max_y = std::max(
      *max_y,
      current_max_y
    );

    // 다음 cycle에서 "이전 영역"으로 사용
    previous_min_x_ = current_min_x;
    previous_min_y_ = current_min_y;
    previous_max_x_ = current_max_x;
    previous_max_y_ = current_max_y;

    has_previous_bounds_ = true;
  }
  else {

    // 이번 cycle에는 사람이 없음.
    //
    // 위에서 previous bounds를 한 번 update 영역에 넣었으므로
    // 이전 Human cost가 이번 cycle에서 제거된다.
    //
    // 다음 cycle에는 더 이상 갱신할 이전 영역이 없음.
    has_previous_bounds_ = false;
  }
}


void HumanLayer::updateCosts(
  nav2_costmap_2d::Costmap2D & master_grid,
  int min_i,
  int min_j,
  int max_i,
  int max_j)
{
  if (!enabled_) {
    return;
  }

  // updateBounds()에서 잡아둔
  // 같은 cycle의 prediction 사용
  const auto predictions =
    cycle_predictions_;

  if (!predictions) {
    return;
  }

  if (predictions->predictions.empty()) {
    return;
  }

  const double resolution =
    master_grid.getResolution();

  // 0.25m 반경이 costmap 기준 몇 cell인지 계산
  const int cell_radius = static_cast<int>(
    std::ceil(
      HUMAN_RADIUS / resolution
    )
  );

  std::size_t used_people = 0;
  std::size_t used_prediction_points = 0;
  std::size_t checked_cells = 0;
  std::size_t modified_cells = 0;

  // ============================================================
  // 모든 사람
  // ============================================================

  for (const auto & person : predictions->predictions) {

    const std::size_t point_count =
      std::min(
        person.predicted_positions.size(),
        person.time_offsets.size()
      );

    if (point_count == 0) {
      continue;
    }

    used_people++;

    // ==========================================================
    // 모든 미래 예측점
    // ==========================================================

    for (std::size_t i = 0; i < point_count; ++i) {

      const auto & point =
        person.predicted_positions[i];

      const double time_offset =
        static_cast<double>(
          person.time_offsets[i]
        );

      // ========================================================
      // 시간에 따른 연속적인 peak cost 계산
      // ========================================================

      if (
        time_offset < MIN_PREDICTION_TIME ||
        time_offset > MAX_PREDICTION_TIME)
      {
        continue;
      }

      const double time_ratio =
        (
          time_offset -
          MIN_PREDICTION_TIME
        )
        /
        (
          MAX_PREDICTION_TIME -
          MIN_PREDICTION_TIME
        );

      // 선형 보간
      //
      // time_ratio = 0 → 220
      // time_ratio = 1 → 110
      const double peak_cost =
        NEAR_PEAK_COST
        +
        time_ratio *
        (
          FAR_PEAK_COST -
          NEAR_PEAK_COST
        );

      unsigned int center_mx;
      unsigned int center_my;

      // prediction 중심이 현재 local costmap 안에 있는지 확인
      if (!master_grid.worldToMap(
          point.x,
          point.y,
          center_mx,
          center_my))
      {
        continue;
      }

      used_prediction_points++;

      // ========================================================
      // 해당 prediction 주변 cell 범위만 계산
      // ========================================================

      const int start_x = std::max(
        min_i,
        static_cast<int>(center_mx) - cell_radius
      );

      const int end_x = std::min(
        max_i,
        static_cast<int>(center_mx) + cell_radius + 1
      );

      const int start_y = std::max(
        min_j,
        static_cast<int>(center_my) - cell_radius
      );

      const int end_y = std::min(
        max_j,
        static_cast<int>(center_my) + cell_radius + 1
      );

      // ========================================================
      // 이 작은 영역 안에서만 정확한 원 거리 계산
      // ========================================================

      for (int my = start_y; my < end_y; ++my) {

        for (int mx = start_x; mx < end_x; ++mx) {

          checked_cells++;

          double wx;
          double wy;

          master_grid.mapToWorld(
            static_cast<unsigned int>(mx),
            static_cast<unsigned int>(my),
            wx,
            wy
          );

          const double distance =
            std::hypot(
              wx - point.x,
              wy - point.y
            );

          // 우리가 계산할 최대 Human 영역 밖이면 무시
          if (distance > HUMAN_RADIUS) {
            continue;
          }

          // ========================================================
          // Gaussian spatial cost
          //
          // 중심에서 가까울수록 1에 가깝고,
          // 멀어질수록 0에 가까워진다.
          //
          //                 d²
          // exp( - ---------------- )
          //           2 * sigma²
          // ========================================================

          const double gaussian =
            std::exp(
              -(
                distance * distance
              ) / (
                2.0 *
                HUMAN_SIGMA *
                HUMAN_SIGMA
              )
            );

          // 시간에 따른 peak cost
          // ×
          // 공간에 따른 Gaussian 감쇠
          const double calculated_cost =
            static_cast<double>(peak_cost)
            * gaussian;

          // 바깥쪽의 너무 작은 cost는 무시
          if (
            calculated_cost <
            static_cast<double>(MIN_HUMAN_COST)
          ) {
            continue;
          }

          const unsigned char human_cost =
            static_cast<unsigned char>(
              std::round(calculated_cost)
            );

          const unsigned char current_cost =
            master_grid.getCost(
              static_cast<unsigned int>(mx),
              static_cast<unsigned int>(my)
            );

          // Static/STVL 등의 기존 높은 cost를 낮추지 않는다.
          if (current_cost < human_cost) {

            master_grid.setCost(
              static_cast<unsigned int>(mx),
              static_cast<unsigned int>(my),
              human_cost
            );

            modified_cells++;
          }
        }
      }
    }
  }

  auto node = node_.lock();

  if (node) {

    RCLCPP_INFO_THROTTLE(
      node->get_logger(),
      *node->get_clock(),
      2000,
      "HumanLayer: people=%zu, points=%zu, checked=%zu, modified=%zu",
      used_people,
      used_prediction_points,
      checked_cells,
      modified_cells
    );
  }
}


void HumanLayer::reset()
{
  std::lock_guard<std::mutex> lock(prediction_mutex_);

  latest_predictions_.reset();
  cycle_predictions_.reset();

  has_previous_bounds_ = false;

  current_ = true;
}

}

PLUGINLIB_EXPORT_CLASS(
  limbo_navigation::HumanLayer,
  nav2_costmap_2d::Layer
)