#pragma once

#include <memory>
#include <mutex>

#include "rclcpp/rclcpp.hpp"
#include "nav2_costmap_2d/layer.hpp"
#include "nav2_costmap_2d/costmap_2d.hpp"

#include "limbo_interfaces/msg/person_prediction_array.hpp"

namespace limbo_navigation
{

// 사람 비용 설정. 전부 nav2_params.yaml의 human_layer 절에서 읽는다 (코드 기본값은 yaml 없이도 뜨게 하는 보험).
struct HumanCostConfig
{
  // 사람 중심에서 이 반경 안은 치명(LETHAL) 비용. 사람 몸 반경(어깨 폭 0.45~0.5 m)이다.
  // MPPI는 치명 비용만 "충돌"로 보고 그 밖은 가중치로만 보기 때문에, 이게 없으면 사람을 뚫는 궤적을 고른다.
  double lethal_radius{0.25};
  // 현재 위치부터 이 시간(초) 안의 예측점까지 치명으로 칠한다. 그보다 먼 미래는 가우시안으로만.
  // 예측 경로 전부를 치명으로 칠하면 로봇이 사람을 보기만 해도 우회한다 (PROJECT.md 2-1 "하지 말 것")
  double lethal_time{0.5};
  // 가우시안 비용을 계산하는 최대 반경과 퍼짐
  double radius{0.35};
  double sigma{0.15};
  // 예측점의 중심 비용. 가까운 미래일수록 높다 (near → far 선형)
  double near_peak_cost{220.0};
  double far_peak_cost{110.0};
  double min_prediction_time{0.25};
  double max_prediction_time{2.0};
  // 이보다 작은 비용은 쓰지 않는다 (가우시안 꼬리)
  double min_cost{10.0};
  // 이보다 오래된 예측은 버린다 (초)
  double max_prediction_age{1.0};
  // --- 전역 costmap용 "통행료" 모드 (설계 전제 2-8 규칙 1). 지역은 기본값(치명 + 예측 경로) 그대로.
  // current_lethal=false면 현재 위치를 치명이 아닌 가우시안으로만 칠한다. 봉우리·반경은 서 있는 사람/걷는 사람이 다르다:
  // 뜻은 "그 사람 한 명을 피하려고 몇 m까지 돌아가는가"(서 있음 3 m, 걷는 중 0.5 m. NavFn 칸당 기본 50 + 비용×0.8로 환산)
  bool current_lethal{true};
  bool use_predictions{true};
  double standing_speed{0.2};        // m/s, 이보다 느리면 서 있는 사람
  double standing_peak_cost{200.0};
  double standing_radius{0.8};
  double standing_sigma{0.35};
  double walking_peak_cost{60.0};
  double walking_radius{0.5};
  double walking_sigma{0.22};
};

class HumanLayer : public nav2_costmap_2d::Layer
{
public:
  HumanLayer() = default;

  void onInitialize() override;

  void updateBounds(
    double robot_x, double robot_y, double robot_yaw,
    double * min_x, double * min_y, double * max_x, double * max_y) override;

  void updateCosts(
    nav2_costmap_2d::Costmap2D & master_grid,
    int min_i, int min_j, int max_i, int max_j) override;

  void reset() override;

  bool isClearable() override {return true;}

private:
  using PredictionArray = limbo_interfaces::msg::PersonPredictionArray;

  struct Bounds
  {
    bool valid{false};
    double min_x{0.0}, min_y{0.0}, max_x{0.0}, max_y{0.0};
    void add(double x, double y, double r);
  };

  struct CellRange
  {
    int min_i, min_j, max_i, max_j;
  };

  void readParameters();
  void predictionCallback(const PredictionArray::SharedPtr msg);
  PredictionArray::SharedPtr takeFreshPredictions();
  Bounds predictionBounds(const PredictionArray & predictions) const;
  double peakCostAt(double time_offset) const;
  void paintPerson(
    nav2_costmap_2d::Costmap2D & grid, const CellRange & range,
    const limbo_interfaces::msg::PersonPrediction & person);
  void paintCircle(
    nav2_costmap_2d::Costmap2D & grid, const CellRange & range,
    double x, double y, bool lethal, double peak_cost, double radius, double sigma);

  HumanCostConfig config_;
  double paint_radius_{0.35};   // max(radius, lethal_radius, standing_radius, walking_radius)

  rclcpp::Subscription<PredictionArray>::SharedPtr prediction_sub_;
  std::mutex prediction_mutex_;
  PredictionArray::SharedPtr latest_predictions_;
  // updateBounds()에서 고른 예측을 같은 주기의 updateCosts()에서도 쓰기 위한 사본
  PredictionArray::SharedPtr cycle_predictions_;
  // 이전 주기에 사람 비용을 칠한 영역. 사람이 움직이면 이전 비용을 지워야 해서 다음 갱신 영역에 넣는다
  Bounds previous_bounds_;
  std::size_t modified_cells_{0};
};

}  // namespace limbo_navigation
