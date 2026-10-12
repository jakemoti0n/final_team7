"""시나리오 월드에서 정해진 경로를 Nav2로 돈다. 사용법: nav_route.py <box|people>"""
import sys, time, rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from nav2_msgs.action import NavigateToPose
ROUTES = {
    # 홀 ↔ 왼쪽 복도 위쪽 끝 왕복 2번 (홀 서쪽 낮은 상자, 왼쪽 복도 서 있는 사람)
    'box': [('왼쪽 복도 위쪽 끝', -6.8, 10.0), ('홀', 0.0, 0.0), ('왼쪽 복도 위쪽 끝', -6.8, 10.0), ('홀', 0.0, 0.0)],
    # 왼쪽 복도 위쪽 끝으로 간 뒤 위쪽 복도 왕복 2번 (나란히 걷는 두 사람)
    'people': [('왼쪽 복도 위쪽 끝', -6.8, 10.0), ('위쪽 복도 동쪽', 3.5, 9.8), ('왼쪽 복도 위쪽 끝', -6.8, 10.0),
               ('위쪽 복도 동쪽', 3.5, 9.8), ('왼쪽 복도 위쪽 끝', -6.8, 10.0)],
    # human_test_world (15m 방, 사람 10명) 네 모서리 근처를 돈다
    'room': [('북동', 5.0, 5.0), ('남서', -5.0, -5.0), ('남동', 5.0, -5.0), ('북서', -5.0, 5.0), ('가운데', 0.0, 0.0)],
}
rclpy.init(); n = Node('nav_route'); ac = ActionClient(n, NavigateToPose, '/navigate_to_pose'); ac.wait_for_server()
for name, x, y in ROUTES[sys.argv[1]]:
    g = NavigateToPose.Goal(); g.pose.header.frame_id = 'map'
    g.pose.pose.position.x, g.pose.pose.position.y, g.pose.pose.orientation.w = x, y, 1.0
    t0 = time.time(); f = ac.send_goal_async(g); rclpy.spin_until_future_complete(n, f)
    if not f.result().accepted:
        print(f'{name:12s} → 거부됨', flush=True); continue
    r = f.result().get_result_async()
    while not r.done() and time.time() - t0 < 120: rclpy.spin_once(n, timeout_sec=0.1)
    if not r.done(): f.result().cancel_goal_async(); time.sleep(1)
    print(f"{name:12s} → {({4: 'SUCCEEDED', 5: 'CANCELED', 6: 'ABORTED'}.get(r.result().status) if r.done() else 'TIMEOUT')} {time.time() - t0:5.1f}s", flush=True)
