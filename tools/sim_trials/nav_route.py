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
    # people의 짧은 판: 복도 2구간만, 목표는 복도 안(벽에서 0.65~0.8 m). 목표를 둘 때는 지도 거리 변환으로 벽 거리를 확인한다
    'people2': [('왼쪽 복도 위쪽 끝', -6.8, 10.0), ('위쪽 복도 동쪽', 3.5, 9.8), ('왼쪽 복도 위쪽 끝', -6.8, 10.0)],
    # 홀 안 짧은 왕복 (다가오는 손님 시나리오: zz_social_approach의 approach 사람이 (-3, 1.3)에 서 있다)
    'hall': [('홀 서쪽', -5.0, 0.5), ('출발점', 0.0, 0.0), ('홀 서쪽', -5.0, 0.5), ('출발점', 0.0, 0.0)],
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
    t0 = time.time(); f = ac.send_goal_async(g)
    # 수락 응답을 기다린다. 시작 직후 부하로 수십 초 걸릴 수 있어 60 s까지 보고, 다시 보내지는 않는다
    # (다시 보내면 서버에는 두 목표가 생겨 앞 목표가 선점·취소된다 — 2026-10-15 손님 벤치 0/7 원인).
    # 서브 PC가 본 "6분 멈춤"은 제한 없는 대기 때문이라 60 s 상한으로 막는다
    rclpy.spin_until_future_complete(n, f, timeout_sec=60.0)
    if not f.done():
        print(f'{name:12s} → 수락 응답 없음 {time.time() - t0:5.1f}s', flush=True); continue
    if not f.result().accepted:
        print(f'{name:12s} → 거부됨', flush=True); continue
    r = f.result().get_result_async()
    while not r.done() and time.time() - t0 < GOAL_TIMEOUT: rclpy.spin_once(n, timeout_sec=0.1)
    if not r.done():   # 시간 초과: 취소를 보내고 취소 응답까지 spin해야 다음 목표가 깨끗이 시작된다
        c = f.result().cancel_goal_async(); rclpy.spin_until_future_complete(n, c, timeout_sec=5.0)
        rclpy.spin_until_future_complete(n, r, timeout_sec=5.0)
    print(f"{name:12s} → {({4: 'SUCCEEDED', 5: 'CANCELED', 6: 'ABORTED'}.get(r.result().status) if r.done() else 'TIMEOUT')} {time.time() - t0:5.1f}s", flush=True)
