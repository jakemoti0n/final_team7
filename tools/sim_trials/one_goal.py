"""Goal 하나를 보내고 지정한 초만큼 기다린 뒤 취소한다. 사용법: one_goal.py x y 초"""
import sys, time, rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from nav2_msgs.action import NavigateToPose
rclpy.init(); n = Node('one_goal'); ac = ActionClient(n, NavigateToPose, '/navigate_to_pose'); ac.wait_for_server()
g = NavigateToPose.Goal(); g.pose.header.frame_id = 'map'
g.pose.pose.position.x, g.pose.pose.position.y, g.pose.pose.orientation.w = float(sys.argv[1]), float(sys.argv[2]), 1.0
f = ac.send_goal_async(g); rclpy.spin_until_future_complete(n, f); h = f.result(); r = h.get_result_async(); t0 = time.time()
while not r.done() and time.time() - t0 < float(sys.argv[3]): rclpy.spin_once(n, timeout_sec=0.1)
if not r.done(): c = h.cancel_goal_async(); rclpy.spin_until_future_complete(n, c, timeout_sec=3)
print('결과', r.result().status if r.done() else f'{sys.argv[3]}초 후 취소')
