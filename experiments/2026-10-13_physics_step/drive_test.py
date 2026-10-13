"""Nav2 없이 /cmd_vel을 직접 보내 같은 동작을 시킨다: 직진 6 m → 제자리 5바퀴 → 후진 6 m → 반대로 5바퀴. 시뮬 시간 기준."""
import rclpy, math
from rclpy.node import Node
from geometry_msgs.msg import Twist
from rosgraph_msgs.msg import Clock
rclpy.init(); n = Node('drive_test'); pub = n.create_publisher(Twist, '/cmd_vel', 10)
clk = {'t': None}
n.create_subscription(Clock, '/clock', lambda m: clk.__setitem__('t', m.clock.sec + m.clock.nanosec*1e-9), 10)
phases = [('직진', 0.4, 0.0, 15.0), ('정지', 0, 0, 3.0), ('회전+', 0.0, 1.0, 10*math.pi), ('정지', 0, 0, 3.0),
          ('후진', -0.4, 0.0, 15.0), ('정지', 0, 0, 3.0), ('회전-', 0.0, -1.0, 10*math.pi), ('정지', 0, 0, 3.0)]
while clk['t'] is None: rclpy.spin_once(n, timeout_sec=0.1)
for name, v, w, dur in phases:
    t0 = clk['t']; print(f"{name} 시작 t={t0:.1f}", flush=True)
    while clk['t'] - t0 < dur:
        m = Twist(); m.linear.x = float(v); m.angular.z = float(w); pub.publish(m)
        rclpy.spin_once(n, timeout_sec=0.05)
pub.publish(Twist()); print('끝', flush=True)
