"""
ToF 점구름 → /tof/obstacle_ahead, /tof/nearest (R5).

ToF는 사람인지 모르는 장애물 신호라 사람 기다리기 판단에는 쓰지 않는다(설계 2-7, 그 판단은 person_wait_node).
코앞 안전 정지는 Nav2 collision_monitor가 /tof/points를 직접 본다. 이 노드는 관제·로그용 요약만 낸다.
실물 I2C 드라이버도 /tof/points만 내면 된다.
"""

from geometry_msgs.msg import PointStamped
from limbo_perception import tof
import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.time import Time
from sensor_msgs.msg import PointCloud2
from sensor_msgs_py import point_cloud2
from std_msgs.msg import Bool
from tf2_ros import Buffer, TransformException, TransformListener


def rotation_matrix(q):
    x, y, z, w = q.x, q.y, q.z, q.w
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


class TofNode(Node):

    def __init__(self):
        super().__init__('tof_node')
        p = self.declare_parameter
        self.config = tof.TofConfig(
            stop_distance=p('stop_distance', 0.50).value,
            min_obstacle_height=p('min_obstacle_height', 0.03).value,
            confirm_frames=p('confirm_frames', 3).value)
        self.base_frame = p('base_frame', 'base_link').value
        self.debounce = tof.Debounce(self.config.confirm_frames)
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.ahead_pub = self.create_publisher(Bool, '/tof/obstacle_ahead', 10)
        self.nearest_pub = self.create_publisher(PointStamped, '/tof/nearest', 10)
        self.create_subscription(
            PointCloud2, p('points_topic', '/tof/points').value, self.on_points, 10)

    def on_points(self, msg):
        # 센서는 로봇에 고정이라 시각과 무관하게 최신 변환을 쓴다
        try:
            t = self.tf_buffer.lookup_transform(self.base_frame, msg.header.frame_id, Time())
        except TransformException as ex:
            self.get_logger().warn(f'TF {msg.header.frame_id} -> {self.base_frame}: {ex}',
                                   throttle_duration_sec=5.0)
            return
        points = point_cloud2.read_points_numpy(msg, field_names=('x', 'y', 'z'))
        offset = t.transform.translation
        points = points @ rotation_matrix(t.transform.rotation).T + [offset.x, offset.y, offset.z]
        point, distance = tof.nearest_point(points, offset.x, self.config)
        blocked = self.debounce.update(distance < self.config.stop_distance)
        self.ahead_pub.publish(Bool(data=blocked))
        if point is not None:
            nearest = PointStamped()
            nearest.header.stamp = msg.header.stamp
            nearest.header.frame_id = self.base_frame
            nearest.point.x, nearest.point.y, nearest.point.z = map(float, point)
            self.nearest_pub.publish(nearest)


def main(args=None):
    rclpy.init(args=args)
    node = TofNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
