"""ToF 점구름 → /tof/obstacle_ahead, /tof/nearest, 그리고 사람 때문에 멈출지 두 가지 (R5).

/person_blocking: 막히기 시작한 순간 직전에 카메라가 다가오던 사람을 봤으면 참(래치, tof.PersonBlocking).
/person_approaching: 사람이 진로 위로 다가오면 참, 와서 서 있는 동안(ToF 막힘) 유지(tof.ApproachWatch).
BT 조건 노드 IsPersonBlocking·IsPersonApproaching이 이 둘을 본다. 실물 I2C 드라이버도 /tof/points만 내면 된다.
"""

from geometry_msgs.msg import PointStamped
from limbo_interfaces.msg import PersonPredictionArray
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


def seconds(stamp):
    """카메라·ToF 모두 메시지 시각(시뮬레이션 시각)으로 비교한다."""
    return stamp.sec + stamp.nanosec * 1e-9


class TofNode(Node):

    def __init__(self):
        super().__init__('tof_node')
        p = self.declare_parameter
        self.config = tof.TofConfig(
            stop_distance=p('stop_distance', 0.50).value,
            min_obstacle_height=p('min_obstacle_height', 0.03).value,
            confirm_frames=p('confirm_frames', 3).value)
        self.base_frame = p('base_frame', 'base_link').value
        self.latched = False
        self.debounce = tof.Debounce(self.config.confirm_frames)
        self.blocking = tof.PersonBlocking(tof.BlockingConfig(
            memory_sec=p('memory_sec', 5.0).value,
            min_distance=p('person_min_distance', 0.8).value,
            max_distance=p('person_max_distance', 3.0).value,
            half_width=p('person_half_width', 1.0).value,
            clear_sec=p('clear_sec', 1.0).value,
            max_hold_sec=p('max_hold_sec', 60.0).value))
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.ahead_pub = self.create_publisher(Bool, '/tof/obstacle_ahead', 10)
        self.nearest_pub = self.create_publisher(PointStamped, '/tof/nearest', 10)
        self.blocking_pub = self.create_publisher(Bool, '/person_blocking', 10)
        self.approach = tof.ApproachWatch(tof.ApproachConfig(
            cpa_radius=p('approach_cpa_radius', 0.6).value,
            max_range=p('approach_max_range', 3.0).value,
            min_speed=p('approach_min_speed', 0.2).value,
            seen_hold_sec=p('approach_seen_hold_sec', 1.0).value,
            release_sec=p('approach_release_sec', 1.0).value,
            max_hold_sec=p('approach_max_hold_sec', 60.0).value))
        self.approaching = False
        self.approach_pub = self.create_publisher(Bool, '/person_approaching', 10)
        self.create_subscription(
            PersonPredictionArray, p('predictions_topic', '/person_detector/predictions').value,
            self.on_predictions, 10)
        self.create_subscription(
            PointStamped, p('person_topic', '/person_detector/person_position_base').value,
            self.on_person, 10)
        self.create_subscription(
            PointCloud2, p('points_topic', '/tof/points').value, self.on_points, 10)

    def on_predictions(self, msg):
        # 예측은 odom 기준. 최근접 거리는 회전과 무관하므로 로봇 위치만 빼서 같은 축으로 본다
        if not msg.predictions:
            return
        try:
            t = self.tf_buffer.lookup_transform(msg.header.frame_id, self.base_frame, Time())
        except TransformException:
            return
        rx, ry = t.transform.translation.x, t.transform.translation.y
        people = [(q.current_position.x - rx, q.current_position.y - ry,
                   q.velocity.x, q.velocity.y) for q in msg.predictions]
        self.approach.on_people(seconds(msg.header.stamp), people)

    def on_person(self, msg):
        self.blocking.on_person(seconds(msg.header.stamp), msg.point.x, msg.point.y)

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
        latched = self.blocking.on_tof(seconds(msg.header.stamp), blocked)
        if latched != self.latched:
            self.get_logger().info(f'person_blocking {latched}')
            self.latched = latched
        self.blocking_pub.publish(Bool(data=latched))
        approaching = self.approach.on_tick(seconds(msg.header.stamp), blocked)
        if approaching != self.approaching:
            self.get_logger().info(f'person_approaching {approaching}')
            self.approaching = approaching
        self.approach_pub.publish(Bool(data=approaching))
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
