"""실시간 비율(/clock 대 벽시계)과 /cmd_vel, /odom 속도를 지정 초 동안 1초마다 찍는다."""
import sys, time, rclpy
from rclpy.node import Node
from rosgraph_msgs.msg import Clock
from geometry_msgs.msg import Twist, TwistStamped
from nav_msgs.msg import Odometry
rclpy.init(); n = Node('speed_probe')
st = {'clk': None, 'cmd': 0.0, 'odom': 0.0, 'cmd_n': 0, 'odom_n': 0}
def on_clk(m): st['clk'] = m.clock.sec + m.clock.nanosec * 1e-9
def on_cmd(m):
    t = m.twist if hasattr(m, 'twist') else m
    st['cmd'] = t.linear.x; st['cmd_n'] += 1
def on_odom(m): st['odom'] = m.twist.twist.linear.x; st['odom_n'] += 1
n.create_subscription(Clock, '/clock', on_clk, 10)
tn = dict(n.get_topic_names_and_types())
cmd_type = TwistStamped if 'geometry_msgs/msg/TwistStamped' in tn.get('/cmd_vel', []) else Twist
n.create_subscription(cmd_type, '/cmd_vel', on_cmd, 10)
n.create_subscription(Odometry, '/odom', on_odom, 10)
while st['clk'] is None: rclpy.spin_once(n, timeout_sec=0.1)
w0, c0 = time.monotonic(), st['clk']; last_w, last_c = w0, c0
dur = float(sys.argv[1]); print('벽초 시뮬초 RTF cmd_vx odom_vx cmdHz odomHz')
while time.monotonic() - w0 < dur:
    rclpy.spin_once(n, timeout_sec=0.05)
    w = time.monotonic()
    if w - last_w >= 1.0:
        rtf = (st['clk'] - last_c) / (w - last_w)
        print(f"{w-w0:5.1f} {st['clk']-c0:6.1f} {rtf:4.2f} {st['cmd']:5.2f} {st['odom']:5.2f} {st['cmd_n']:3d} {st['odom_n']:3d}", flush=True)
        last_w, last_c = w, st['clk']; st['cmd_n'] = st['odom_n'] = 0
