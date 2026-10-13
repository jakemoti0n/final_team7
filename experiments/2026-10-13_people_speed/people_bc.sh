#!/usr/bin/env bash
# 학원 시나리오(사람 있음) people 경로를 조건 B·C로 3회씩. 결과 logs/trial_peopleB1..3.csv, trial_peopleC1..3.csv
T=/home/kim/limbo/tools/sim_trials; R=/home/kim/limbo
NAV=$R/limbo/src/limbo_navigation/config/nav2_params.yaml; XACRO=$R/limbo/src/limbo_description/urdf/limbo.gazebo.xacro
restore() { git -C $R checkout -- limbo/src/limbo_navigation/config/nav2_params.yaml limbo/src/limbo_description/urdf/limbo.gazebo.xacro; }
restore
python3 $T/apply_mppi_tune.py prune_distance=2.5
for i in 1 2 3; do echo "=== B$i $(date +%H:%M)"; $T/trial.sh peopleB$i people | tail -1; done
restore
python3 $T/apply_mppi_tune.py prune_distance=3.0 vx_max=0.75
sed -i 's|max_velocity: \[0.6, 0.0, 1.8\]|max_velocity: [0.75, 0.0, 1.8]|' $NAV
sed -i 's|<max_linear_velocity>0.6<|<max_linear_velocity>0.8<|; s|<min_linear_velocity>-0.6<|<min_linear_velocity>-0.8<|' $XACRO
for i in 1 2 3; do echo "=== C$i $(date +%H:%M)"; $T/trial.sh peopleC$i people | tail -1; done
restore
echo "=== 끝 $(date +%H:%M)"; git -C $R status --short
