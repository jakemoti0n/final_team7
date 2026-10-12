# 컨트롤러 비교: MPPI vs RPP — 2026-10-12

## 결론
**MPPI 유지.** 사람이 있는 좁은 복도에서 RPP는 12번 중 6번 중단됐다. RPP는 장애물을 스스로 피하지 않고 멈추기만 하므로, 경로 계획기가 다른 길을 못 찾으면(복도를 사람이 막음) 재시도만 하다 중단된다. 장애물이 가만히 있는 구간은 RPP가 약 10초 빨랐다.

## 조건
- 브랜치 `lab` (dev `5854391` 기준: 전역 STVL 15초, 헛돎 감시 방어 수정 포함)
- 월드 `aischool_2f_scenarios`, `gui:=false record:=true`, 각 3회
- 경로 `people` (`tools/sim_trials/nav_route.py`): 홀 → 왼쪽 복도 위쪽 끝(첫 이동, 낮은 상자 2개 통과) → 위쪽 복도 동쪽 왕복 2번(나란히 걷는 두 사람, 로봇에 반응 안 함)
- 속도 한계는 같게: 0.6 m/s, 1.8 rad/s, 후진 금지
- MPPI: dev의 `nav2_params.yaml` 그대로. RPP: 아래 설정 (`python3 tools/sim_trials/apply_controller.py rpp`)

## 결과
| 항목 | MPPI | RPP |
|---|---|---|
| 상자 구간 성공 / 시간 | 3/3, 약 37초 | 3/3, 약 26초 |
| 상자와 최소 거리 | 0.20~0.23 m | 0.11~0.12 m |
| 위쪽 복도 성공 | 12/12 | 6/12 (ABORTED 6) |
| 이동당 복구 동작 평균 | 11.7 | 19.8 |
| 사람과 최소 거리 중앙값 | 0.20 m | 0.12 m (최소 0.05) |
| 컨트롤러 주기 경고 합계 | 4 | 32 |

원본 CSV: 이 폴더의 `mppi_people*.csv`, `rpp_people*.csv` (열 설명은 README "주행 평가 기록")

## CPU (2026-10-12 추가)
`tools/sim_trials/cpu_controller.sh <라벨>`: `controller_server` CPU를 서 있을 때 15초, 주행(홀 → 왼쪽 복도 끝) 25초 동안 1초 간격으로 잼. 이 프로세스에는 로컬 costmap(STVL)도 같이 돌아서 둘의 차이를 컨트롤러 계산으로 봄. 노트북(RTX 4060 노트북) 기준, CPU 한 코어 = 100%.

| | 서 있을 때 | 주행 중 | 컨트롤러 계산 (차이) | 주기 경고 |
|---|---|---|---|---|
| MPPI (batch 2000, 80단계) | 23.5% | 50.3% | **약 27%** | 0 |
| RPP | 23.4% | 25.8% | **약 2%** | 0 |

- RPP의 남은 강점은 계산량(약 13배 가벼움). 노트북에서는 둘 다 여유 있음
- Jetson은 코어가 2~3배 느리다고 보면 MPPI가 코어 하나의 55~80% 예상. 실측 필요. 모자라면 RPP보다 먼저 MPPI 경량화(`batch_size`, `time_steps`; 예측 시간을 줄이면 `prune_distance` 상한 관계도 같이 맞출 것)

## 다시 하려면
```bash
cd ~/limbo/tools/sim_trials
python3 apply_controller.py rpp            # MPPI면 생략
for k in 1 2 3; do ./trial.sh rpp_people$k people; done
python3 trial_summary.py ~/limbo_bags/sim_trials/logs/trial_rpp_people*.csv
git checkout ../../limbo/src/limbo_navigation/config/nav2_params.yaml
```

## RPP 설정
```yaml
    FollowPath:
      # 실험: MPPI와 같은 속도 한계(0.6 m/s, 1.8 rad/s)로 맞춘 Regulated Pure Pursuit
      plugin: "nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController"
      desired_linear_vel: 0.6
      lookahead_dist: 0.6
      min_lookahead_dist: 0.3
      max_lookahead_dist: 0.9
      lookahead_time: 1.5
      use_velocity_scaled_lookahead_dist: true
      rotate_to_heading_angular_vel: 1.8
      max_angular_accel: 4.0
      use_rotate_to_heading: true
      rotate_to_heading_min_angle: 0.785
      allow_reversing: false
      transform_tolerance: 0.5
      min_approach_linear_velocity: 0.05
      approach_velocity_scaling_dist: 0.6
      use_collision_detection: true
      max_allowed_time_to_collision_up_to_carrot: 1.0
      use_regulated_linear_velocity_scaling: true
      regulated_linear_scaling_min_radius: 0.9
      regulated_linear_scaling_min_speed: 0.25
      use_cost_regulated_linear_velocity_scaling: true
      cost_scaling_dist: 0.6
      cost_scaling_gain: 1.0
      # 로컬 costmap inflation의 cost_scaling_factor와 같아야 장애물까지 거리를 맞게 계산한다
      inflation_cost_scaling_factor: 5.0
      max_robot_pose_search_dist: 10.0
      use_fixed_curvature_lookahead: false
      curvature_lookahead_dist: 0.6
      interpolate_curvature_after_goal: false
```
