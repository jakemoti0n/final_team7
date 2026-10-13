#!/usr/bin/env bash
# 조건 B(prune_distance 2.5)를 물리 스텝 1 ms 월드 사본으로 2회. 어제 결과 재현 확인용
T=/home/kim/limbo/tools/sim_trials; R=/home/kim/limbo
PREV=$(pgrep -f -o "people_bc.sh"); [ -n "$PREV" ] && while kill -0 $PREV 2>/dev/null; do sleep 10; done
sed 's|<max_step_size>0.002</max_step_size>|<max_step_size>0.001</max_step_size>|' /home/kim/limbo/limbo/install/limbo_simulation/share/limbo_simulation/worlds/aischool_2f_scenarios.sdf > /home/kim/limbo/limbo/install/limbo_simulation/share/limbo_simulation/worlds/zz_step1.sdf
grep -c "0.001" /home/kim/limbo/limbo/install/limbo_simulation/share/limbo_simulation/worlds/zz_step1.sdf
git -C $R checkout -- limbo/src/limbo_navigation/config/nav2_params.yaml limbo/src/limbo_description/urdf/limbo.gazebo.xacro
python3 $T/apply_mppi_tune.py prune_distance=2.5
for i in 1 2; do echo "=== B(1ms) $i $(date +%H:%M)"; WORLD=zz_step1 MAP=aischool_2f_map $T/trial.sh peopleB1ms$i people | tail -1; done
git -C $R checkout -- limbo/src/limbo_navigation/config/nav2_params.yaml
rm -f /home/kim/limbo/limbo/install/limbo_simulation/share/limbo_simulation/worlds/zz_step1.sdf; echo "=== 끝 $(date +%H:%M)"; git -C $R status --short
