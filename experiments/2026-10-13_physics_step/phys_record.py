"""정답 위치(/ground_truth/odom)와 바퀴 odom(/odom), EKF(/odometry/filtered), /cmd_vel을 시뮬 시간 0.1초마다 CSV로 남긴다. 사용법: phys_record.py 출력.csv"""
import sys, math, rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Twist
def yaw(q): return math.atan2(2*(q.w*q.z + q.x*q.y), 1 - 2*(q.y*q.y + q.z*q.z))
def rp(q):
    r = math.atan2(2*(q.w*q.x + q.y*q.z), 1 - 2*(q.x*q.x + q.y*q.y))
    p = math.asin(max(-1, min(1, 2*(q.w*q.y - q.z*q.x))))
    return r, p
rclpy.init(); n = Node('phys_record'); f = open(sys.argv[1], 'w')
f.write('t,gt_x,gt_y,gt_yaw,gt_z,gt_roll,gt_pitch,gt_v,od_x,od_y,od_yaw,od_v,ek_x,ek_y,ek_yaw,cmd_v\n')
st = {'od': None, 'ek': None, 'cmd': 0.0, 'last': -1.0}
def on_od(m): st['od'] = m
def on_ek(m): st['ek'] = m
def on_cmd(m): st['cmd'] = m.linear.x
def on_gt(m):
    t = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9
    if t - st['last'] < 0.1 or st['od'] is None or st['ek'] is None: return
    st['last'] = t
    p, q = m.pose.pose.position, m.pose.pose.orientation; r, pi = rp(q)
    o, oq = st['od'].pose.pose.position, st['od'].pose.pose.orientation
    e, eq = st['ek'].pose.pose.position, st['ek'].pose.pose.orientation
    f.write(f"{t:.2f},{p.x:.4f},{p.y:.4f},{yaw(q):.4f},{p.z:.5f},{r:.5f},{pi:.5f},{m.twist.twist.linear.x:.4f},"
            f"{o.x:.4f},{o.y:.4f},{yaw(oq):.4f},{st['od'].twist.twist.linear.x:.4f},"
            f"{e.x:.4f},{e.y:.4f},{yaw(eq):.4f},{st['cmd']:.3f}\n"); f.flush()
n.create_subscription(Odometry, '/ground_truth/odom', on_gt, 50)
n.create_subscription(Odometry, '/odom', on_od, 50)
n.create_subscription(Odometry, '/odometry/filtered', on_ek, 50)
n.create_subscription(Twist, '/cmd_vel', on_cmd, 10)
try: rclpy.spin(n)
except KeyboardInterrupt: pass
