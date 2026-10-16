"""ToF 점구름 → /tof/obstacle_ahead, /tof/nearest, 그리고 사람 때문에 멈출지 두 가지 (R5).

/person_blocking: ToF가 막혔고 직전에 카메라가 다가오던 사람을 봤거나 /scan 앞에 사람 덩어리가 있으면 참
(래치, tof.PersonBlocking).
/person_approaching: 사람이 진로 위로 다가오면 참, 와서 서 있는 동안(ToF 막힘 또는 /scan 앞 사람 덩어리) 유지
(tof.ApproachWatch).
/scan 점은 /map 벽(점유 칸에서 해상도 2칸 안)을 걸러 낸 뒤 덩어리로 본다. map TF가 없으면 거르지 않는다.
BT 조건 노드 IsPersonBlocking·IsPersonApproaching이 이 둘을 본다. 실물 I2C 드라이버도 /tof/points만 내면 된다.
"""

import math

from geometry_msgs.msg import PointStamped
from limbo_interfaces.msg import PersonPredictionArray
from limbo_perception import tof
from nav_msgs.msg import OccupancyGrid
import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, qos_profile_sensor_data, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import LaserScan, PointCloud2
from sensor_msgs_py import point_cloud2
from std_msgs.msg import Bool
from tf2_ros import Buffer, TransformException, TransformListener


def rotation_matrix(q):
    x, y, z, w = q.x, q.y, q.z, q.w
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def yaw_of(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


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
        self.latched_reason = None
        self.blob = None
        self.sensor_x = 0.25   # 첫 ToF 프레임에서 TF로 바뀜
        self.debounce = tof.Debounce(self.config.confirm_frames)
        self.blocking = tof.PersonBlocking(tof.BlockingConfig(
            memory_sec=p('memory_sec', 5.0).value,
            min_distance=p('person_min_distance', 0.8).value,
            max_distance=p('person_max_distance', 3.0).value,
            half_width=p('person_half_width', 1.0).value,
            clear_sec=p('clear_sec', 1.0).value,
            max_hold_sec=p('max_hold_sec', 60.0).value,
            blob_only_hold_sec=p('blob_only_hold_sec', 5.0).value,
            camera_match_radius=p('camera_match_radius', 1.0).value))
        self.world_frame = p('world_frame', 'odom').value
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
            max_hold_sec=p('approach_max_hold_sec', 60.0).value,
            blob_only_hold_sec=p('approach_blob_only_hold_sec', 15.0).value))
        self.approaching = False
        self.approach_basis = None
        # 띠 폭 = 로봇 반폭 + 사람 반경: 로봇이 바뀌면 robot_half_width만 바꾼다
        robot_half_width = p('robot_half_width', 0.30).value
        person_radius = p('person_radius', 0.25).value
        self.blob_config = tof.BlobConfig(
            half_width=robot_half_width + person_radius,
            max_range=p('blob_max_range', 1.5).value,
            neighbor_gap=p('blob_neighbor_gap', 0.15).value,
            min_width=p('person_min_width', 0.15).value,
            max_width=p('person_max_width', 0.60).value)
        self.map_margin_cells = p('map_margin_cells', 2).value
        self.grid = None
        self.map_filter_on = None    # 로그용: 지도 걸러내기를 쓰는 중인가
        self.front = (None, None)    # (scan 시각, 앞 사람 덩어리 world 중심 또는 None)
        self.create_subscription(
            OccupancyGrid, p('map_topic', '/map').value, self.on_map,
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                       reliability=ReliabilityPolicy.RELIABLE))
        self.create_subscription(LaserScan, p('scan_topic', '/scan').value, self.on_scan,
                                 qos_profile_sensor_data)
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
        if msg.header.frame_id == self.world_frame:
            self.blocking.on_camera_people(
                seconds(msg.header.stamp),
                [(q.current_position.x, q.current_position.y) for q in msg.predictions])

    def on_map(self, msg):
        info = msg.info
        self.grid = tof.MapGrid(msg.data, info.width, info.height, info.resolution,
                                info.origin.position.x, info.origin.position.y,
                                yaw_of(info.origin.orientation))
        self.get_logger().info(
            f'map {info.width}x{info.height} res {info.resolution:.3f} m: scan points within '
            f'{self.map_margin_cells * info.resolution:.2f} m of walls are ignored for blobs')

    def to_frame(self, target, points_xy):
        """base_link 평면 점을 target 좌표계로. TF가 없으면 None."""
        try:
            t = self.tf_buffer.lookup_transform(target, self.base_frame, Time())
        except TransformException:
            return None
        yaw = yaw_of(t.transform.rotation)
        c, s = math.cos(yaw), math.sin(yaw)
        x, y = points_xy[:, 0], points_xy[:, 1]
        return np.column_stack([c * x - s * y + t.transform.translation.x,
                                s * x + c * y + t.transform.translation.y])

    def drop_wall_points(self, points):
        """지도 벽 근처 점을 뺀다. 지도·map TF가 없으면(위치 추정 전) 그대로."""
        on = False
        if self.grid is not None:
            in_map = self.to_frame('map', points[:, :2])
            if in_map is not None:
                points = points[tof.filter_map_points(in_map, self.grid, self.map_margin_cells)]
                on = True
        if on != self.map_filter_on:
            self.get_logger().info(f'scan wall filter {"on" if on else "off (no map or map TF)"}')
            self.map_filter_on = on
        return points

    def on_scan(self, msg):
        try:
            t = self.tf_buffer.lookup_transform(self.base_frame, msg.header.frame_id, Time())
        except TransformException:
            return
        ranges = np.asarray(msg.ranges, dtype=float)
        angles = msg.angle_min + msg.angle_increment * np.arange(len(ranges))
        valid = np.isfinite(ranges) & (ranges >= msg.range_min) & (ranges <= msg.range_max)
        points = np.column_stack([ranges * np.cos(angles), ranges * np.sin(angles),
                                  np.zeros(len(ranges))])[valid]
        offset = t.transform.translation
        points = points @ rotation_matrix(t.transform.rotation).T + [offset.x, offset.y, offset.z]
        points = self.drop_wall_points(points)
        found, cx, cy, width = tof.person_blob_ahead(points, self.sensor_x, self.blob_config)
        world = None
        if found:
            world = self.to_frame(self.world_frame, np.array([[cx, cy]]))
            world = (cx, cy) if world is None else tuple(world[0])
        self.front = (seconds(msg.header.stamp), world)
        self.blob = (cx, cy, width) if found else None

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
        self.sensor_x = offset.x
        point, distance = tof.nearest_point(points, offset.x, self.config)
        blocked = self.debounce.update(distance < self.config.stop_distance)
        self.ahead_pub.publish(Bool(data=blocked))
        now = seconds(msg.header.stamp)
        scan_time, blob_world = self.front
        if scan_time is None or abs(now - scan_time) >= 0.5:
            blob_world = None
        latched = self.blocking.on_tof(now, blocked, blob_world)
        reason = self.blocking.reason
        if latched != self.latched or (latched and reason != self.latched_reason):
            if latched:
                blob = '' if self.blob is None or blob_world is None else \
                    ' blob x %.2f y %.2f w %.2f' % self.blob
                self.get_logger().info(
                    f'person_blocking True by {reason}{blob} tof {distance:.2f} m')
            else:
                self.get_logger().info(f'person_blocking False ({self.blocking.release_reason})')
            self.latched, self.latched_reason = latched, reason
        self.blocking_pub.publish(Bool(data=latched))
        prev_basis, prev_since = self.approach.basis, self.approach.basis_since
        approaching = self.approach.on_tick(now, blocked, blob_world is not None)
        if approaching != self.approaching:
            why = 'seen' if approaching else self.approach.release_reason
            self.get_logger().info(f'person_approaching {approaching} ({why})')
            self.approaching = approaching
        elif approaching and self.approach.basis != prev_basis:
            self.get_logger().info(f'approaching hold by {self.approach.basis} '
                                   f'(after {prev_basis} {now - prev_since:.1f} s)')
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
