"""nav2_params.yaml의 컨트롤러(FollowPath)를 바꾼다 (실험용, ktj2). 사용법: apply_controller.py rpp
되돌리기: cd ~/limbo && git checkout limbo/src/limbo_navigation/config/nav2_params.yaml"""
import os, sys
RPP = '''    FollowPath:
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
'''
p = os.path.expanduser('~/limbo/limbo/src/limbo_navigation/config/nav2_params.yaml')
lines = open(p).read().split('\n')
start = lines.index('    FollowPath:')
end = next(i for i in range(start + 1, len(lines)) if lines[i] and len(lines[i]) - len(lines[i].lstrip()) <= 4)
assert sys.argv[1] == 'rpp'
lines[start:end] = RPP.rstrip('\n').split('\n') + ['']
open(p, 'w').write('\n'.join(lines))
print('컨트롤러: RPP 적용')
