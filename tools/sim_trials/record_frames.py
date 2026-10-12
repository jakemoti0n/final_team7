"""카메라 이미지를 시뮬레이션 시각과 함께 저장한다. 사용법: record_frames.py <출력.npz> <초> [몇 장마다 1장]"""
import sys, time, numpy as np, rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
rclpy.init(); n = rclpy.create_node('record_frames'); frames, stamps = [], []; step = int(sys.argv[3]) if len(sys.argv) > 3 else 1; k = [0]
def cb(m):
    k[0] += 1
    if k[0] % step: return
    frames.append(np.frombuffer(bytes(m.data), np.uint8).reshape(m.height, m.width, -1)[:, :, :3].copy())
    stamps.append(m.header.stamp.sec + m.header.stamp.nanosec * 1e-9)
n.create_subscription(Image, '/rgbd_camera/image', cb, qos_profile_sensor_data)
end = time.time() + float(sys.argv[2])
while time.time() < end: rclpy.spin_once(n, timeout_sec=0.05)
np.savez_compressed(sys.argv[1], frames=np.array(frames), stamps=np.array(stamps))
print(len(frames), '장 저장')
