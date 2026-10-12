"""헛돎 판단 재현용으로 /scan, 바퀴 /odom, 정답 위치, /wheel_slip을 녹화한다.
사용법: slip_record.py <출력.pkl> <멈춤 신호 파일>  (신호 파일이 생기면 저장하고 끝)"""
import os, pickle, sys, time, rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from nav_msgs.msg import Odometry
from std_msgs.msg import Bool
rclpy.init(); n = rclpy.create_node('slip_record'); data = {'scan': [], 'odom': [], 'truth': [], 'slip': []}
def st(h): return h.stamp.sec + h.stamp.nanosec * 1e-9
def pose(m):
    p = m.pose.pose; return (st(m.header), p.position.x, p.position.y, p.orientation.z, p.orientation.w)
n.create_subscription(LaserScan, '/scan', lambda m: data['scan'].append((st(m.header), m.angle_min, m.angle_increment, list(m.ranges))), qos_profile_sensor_data)
n.create_subscription(Odometry, '/odom', lambda m: data['odom'].append(pose(m)), 50)
n.create_subscription(Odometry, '/ground_truth/odom', lambda m: data['truth'].append(pose(m)), 50)
n.create_subscription(Bool, '/wheel_slip', lambda m: data['slip'].append((time.time(), m.data)), 10)
while not os.path.exists(sys.argv[2]): rclpy.spin_once(n, timeout_sec=0.05)
pickle.dump(data, open(sys.argv[1], 'wb'))
print({k: len(v) for k, v in data.items()})
