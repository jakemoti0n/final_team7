"""시나리오 월드에서 정해진 경로를 Nav2로 돈다. 사용법: nav_route.py <box|people>"""
import os, sys, time, rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from nav2_msgs.action import NavigateToPose
ROUTES = {
    # 홀 ↔ 왼쪽 복도 위쪽 끝 왕복 2번 (홀 서쪽 낮은 상자, 왼쪽 복도 서 있는 사람)
    'box': [('왼쪽 복도 위쪽 끝', -6.8, 10.0), ('홀', 0.0, 0.0), ('왼쪽 복도 위쪽 끝', -6.8, 10.0), ('홀', 0.0, 0.0)],
    # 왼쪽 복도 위쪽 끝으로 간 뒤 위쪽 복도 왕복 2번 (나란히 걷는 두 사람)
    'people': [('왼쪽 복도 위쪽 끝', -6.8, 10.0), ('위쪽 복도 동쪽', 3.5, 9.8), ('왼쪽 복도 위쪽 끝', -6.8, 10.0),
               ('위쪽 복도 동쪽', 3.5, 9.8), ('왼쪽 복도 위쪽 끝', -6.8, 10.0)],
    # people과 같은 왕복이지만 목표를 북쪽 벽 쪽(y 11.8)으로 옮김. 원래 목표 (3.5, 9.8)·(-6.8, 10.0)은 pair_right가 걷는 줄(y 9.8) 위라
    # 도착해 있으면 사람이 걸어 들어와 끼인다 (experiments/2026-10-13_people_speed). 복도 빈 폭은 y 9.2~12.8
    'people_side': [('왼쪽 복도 위쪽 끝(벽쪽)', -6.8, 11.8), ('위쪽 복도 동쪽(벽쪽)', 3.5, 11.8), ('왼쪽 복도 위쪽 끝(벽쪽)', -6.8, 11.8),
                    ('위쪽 복도 동쪽(벽쪽)', 3.5, 11.8), ('왼쪽 복도 위쪽 끝(벽쪽)', -6.8, 11.8)],
    # people_side의 짧은 판: 복도 2구간만. "지나가는 능력"만 빨리 볼 때 (GOAL_TIMEOUT=60 권장)
    'people_side2': [('왼쪽 복도 위쪽 끝(벽쪽)', -6.8, 11.8), ('위쪽 복도 동쪽(벽쪽)', 3.5, 11.8), ('왼쪽 복도 위쪽 끝(벽쪽)', -6.8, 11.8)],
    # people의 짧은 판: 복도 2구간만, 목표는 복도 안(벽에서 0.65~0.8 m). people_side*는 목표가 복도 북쪽 방(y 11.8, 문 통과·벽 옆)이라 무효였음 (2026-10-13)
    'people2': [('왼쪽 복도 위쪽 끝', -6.8, 10.0), ('위쪽 복도 동쪽', 3.5, 9.8), ('왼쪽 복도 위쪽 끝', -6.8, 10.0)],
    # human_test_world (15m 방, 사람 10명) 네 모서리 근처를 돈다
    'room': [('북동', 5.0, 5.0), ('남서', -5.0, -5.0), ('남동', 5.0, -5.0), ('북서', -5.0, 5.0), ('가운데', 0.0, 0.0)],
    # chungjang (200 m 거리) 동쪽 100 m 갔다가 출발점으로. 사람 없음, 속도 실험용. 한 구간 200초 넘으니 GOAL_TIMEOUT=400
    'street': [('거리 100 m', 100.0, 0.0), ('출발점', 0.0, 0.0)],
}
GOAL_TIMEOUT = float(os.environ.get('GOAL_TIMEOUT', 120))   # 초. 구간이 길면 환경변수로 늘린다
rclpy.init(); n = Node('nav_route'); ac = ActionClient(n, NavigateToPose, '/navigate_to_pose'); ac.wait_for_server()
for name, x, y in ROUTES[sys.argv[1]]:
    g = NavigateToPose.Goal(); g.pose.header.frame_id = 'map'
    g.pose.pose.position.x, g.pose.pose.position.y, g.pose.pose.orientation.w = x, y, 1.0
    t0 = time.time(); f = ac.send_goal_async(g); rclpy.spin_until_future_complete(n, f)
    if not f.result().accepted:
        print(f'{name:12s} → 거부됨', flush=True); continue
    r = f.result().get_result_async()
    while not r.done() and time.time() - t0 < GOAL_TIMEOUT: rclpy.spin_once(n, timeout_sec=0.1)
    if not r.done(): f.result().cancel_goal_async(); time.sleep(1)
    print(f"{name:12s} → {({4: 'SUCCEEDED', 5: 'CANCELED', 6: 'ABORTED'}.get(r.result().status) if r.done() else 'TIMEOUT')} {time.time() - t0:5.1f}s", flush=True)
