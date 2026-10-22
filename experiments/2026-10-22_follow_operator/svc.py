"""Trigger 서비스 호출/Empty 발행을 깨끗이 끝내는 도우미. `timeout`으로 죽인 ros2 CLI는 Fast DDS 공유 메모리 조각을 남겨
다음 기동을 망가뜨린다(2026-10-22, 233개 쌓여 lifecycle 실패·시계 역행). 사용법: svc.py call <서비스> [초] | svc.py pub <토픽>"""
import sys, rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger
from std_msgs.msg import Empty
rclpy.init(); n = Node('svc_helper'); code = 1
try:
    if sys.argv[1] == 'call':
        c = n.create_client(Trigger, sys.argv[2]); wait = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0
        if not c.wait_for_service(timeout_sec=wait):
            print('success=False, message=service_unavailable')
        else:
            f = c.call_async(Trigger.Request()); rclpy.spin_until_future_complete(n, f, timeout_sec=wait); r = f.result()
            if r is None: print('success=False, message=no_response')
            else: print(f"success={r.success}, message='{r.message}'"); code = 0 if r.success else 1
    elif sys.argv[1] == 'pub':
        p = n.create_publisher(Empty, sys.argv[2], 10)
        for _ in range(50):          # 구독자가 이 발행자를 발견할 때까지(최대 10 s) 기다렸다가 보낸다. 바로 보내면 유실된다
            rclpy.spin_once(n, timeout_sec=0.2)
            if p.get_subscription_count() > 0: break
        for _ in range(3): p.publish(Empty()); rclpy.spin_once(n, timeout_sec=0.2)
        print(f'published to {p.get_subscription_count()} subscribers'); code = 0 if p.get_subscription_count() > 0 else 1
finally:
    n.destroy_node(); rclpy.shutdown()
sys.exit(code)
