#!/usr/bin/env bash
# 두 대로 나눈 시뮬이 붙었는지 한 번에 본다. 어느 쪽에서 돌려도 된다 (limbo 별칭으로 ROS 환경을 잡은 뒤)
ros2 daemon stop >/dev/null 2>&1; ros2 daemon start >/dev/null 2>&1; sleep 2
echo "노드 수: $(ros2 node list 2>/dev/null | wc -l)  (20개 이상이어야 양쪽이 다 보이는 것)"
for t in /scan /clock /cmd_vel; do
  hz=$(timeout 8 ros2 topic hz $t --window 30 2>/dev/null | grep -m1 -oE "average rate: [0-9.]+" | awk '{print $3}')
  echo "$t: ${hz:-없음} Hz"
done
echo "bt_navigator: $(timeout 10 ros2 lifecycle get /bt_navigator 2>&1 | head -1)"
echo "amcl: $(timeout 10 ros2 lifecycle get /amcl 2>&1 | head -1)"
echo "TF map→base_footprint: $(timeout 6 ros2 run tf2_ros tf2_echo map base_footprint 2>&1 | grep -m1 Translation || echo 없음)"
echo "TF odom→base_footprint: $(timeout 6 ros2 run tf2_ros tf2_echo odom base_footprint 2>&1 | grep -m1 Translation || echo 없음)"
