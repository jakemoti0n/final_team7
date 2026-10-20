"""
사람 트랙 반경 안의 점을 점구름에서 뺀다 (설계 전제 2-8 규칙 1: 전역 계획은 사람을 센서 점이 아니라 트랙으로 본다).

self_filter가 로봇 몸 점을 빼듯, 이 노드는 person_detector 트랙(odom 기준) 둘레 person_radius 안의 점을 뺀
복사본(<입력 토픽>_nopeople)을 낸다. 전역 costmap의 STVL(marking)만 이 복사본을 쓴다. 지역 costmap·안전 정지는
원본을 그대로 쓰므로 회피·정지는 변하지 않는다. 검출을 놓친 사람은 점으로 남아 전과 같이 치명이 된다(안전 쪽).
점은 원래 필드(intensity 등)를 그대로 두려고 바이트 행을 골라 복사한다.
"""

import time

from limbo_interfaces.msg import PersonPredictionArray
import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import PointCloud2, PointField
from tf2_ros import Buffer, TransformException, TransformListener

FLOAT32 = PointField.FLOAT32


def rotation_matrix(q):
    """geometry_msgs Quaternion → 3x3 회전 행렬."""
    x, y, z, w = q.x, q.y, q.z, q.w
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def xyz_view(msg):
    """PointCloud2의 x·y·z(float32)만 (N, 3) float64로. 필드 오프셋으로 읽어 다른 필드는 건드리지 않는다."""
    offsets = {f.name: f.offset for f in msg.fields
               if f.name in ('x', 'y', 'z') and f.datatype == FLOAT32}
    if len(offsets) != 3:
        return None
    raw = np.frombuffer(msg.data, dtype=np.uint8).reshape(-1, msg.point_step)
    cols = [raw[:, offsets[k]:offsets[k] + 4].copy().view(np.float32).reshape(-1)
            for k in ('x', 'y', 'z')]
    return np.stack(cols, axis=1).astype(np.float64)


def keep_rows(msg, mask):
    """mask가 참인 점만 남긴 새 PointCloud2 (필드·바이트 그대로)."""
    raw = np.frombuffer(msg.data, dtype=np.uint8).reshape(-1, msg.point_step)
    out = PointCloud2()
    out.header = msg.header
    out.fields = msg.fields
    out.is_bigendian = msg.is_bigendian
    out.point_step = msg.point_step
    out.is_dense = msg.is_dense
    kept = raw[mask]
    out.height, out.width = 1, int(kept.shape[0])
    out.row_step = out.width * msg.point_step
    out.data = kept.tobytes()
    return out


def people_mask(points_xyz, people_xy, radius):
    """points_xyz(N,3)와 사람 xy(P,2)가 같은 좌표계일 때, 어느 사람 반경 안에도 없는 점이 참."""
    if len(people_xy) == 0 or len(points_xyz) == 0:
        return np.ones(len(points_xyz), dtype=bool)
    d2 = ((points_xyz[:, None, :2] - people_xy[None, :, :]) ** 2).sum(axis=2)   # (N, P)
    return (d2 > radius * radius).all(axis=1)


class PersonFilter(Node):

    def __init__(self):
        super().__init__('person_filter')
        p = self.declare_parameter
        self.radius = p('person_radius', 0.5).value          # m, 사람 중심에서 이 안의 점을 뺀다(어깨 폭 + 팔)
        self.max_age = p('max_prediction_age', 1.0).value    # s, 이보다 오래된 트랙은 안 씀(사라진 사람이 남지 않게)
        self.odom_frame = p('odom_frame', 'odom').value
        topics = p('in_topics', ['/mid360/points_filtered', '/rgbd_camera/points']).value
        self.people = None          # (xy 배열 odom 기준, 받은 벽시계)
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.create_subscription(
            PersonPredictionArray, p('predictions_topic', '/person_detector/predictions').value,
            self.on_predictions, 10)
        self.pubs = {}
        for topic in topics:
            out = topic + '_nopeople'
            self.pubs[topic] = self.create_publisher(PointCloud2, out, qos_profile_sensor_data)
            self.create_subscription(PointCloud2, topic, lambda m, t=topic: self.on_cloud(m, t),
                                     qos_profile_sensor_data)
            self.get_logger().info(f'{topic} → {out} (사람 반경 {self.radius} m 안 점 제거)')
        self.removed = 0
        self.create_timer(5.0, self.report)

    def on_predictions(self, msg):
        xy = np.array([[q.current_position.x, q.current_position.y] for q in msg.predictions],
                      dtype=np.float64).reshape(-1, 2)
        self.people = (xy, msg.header.frame_id, time.monotonic())

    def on_cloud(self, msg, topic):
        pub = self.pubs[topic]
        people = self.people
        if people is None or time.monotonic() - people[2] > self.max_age or len(people[0]) == 0:
            pub.publish(msg)      # 사람 없음: 그대로
            return
        xy, frame, _ = people
        try:
            # 사람(odom)을 점구름 좌표계로 옮긴다. 점 4만 개를 옮기는 것보다 사람 50명을 옮기는 쪽이 싸다
            t = self.tf_buffer.lookup_transform(msg.header.frame_id, frame, Time())
        except TransformException:
            pub.publish(msg)
            return
        points = xyz_view(msg)
        if points is None:
            pub.publish(msg)
            return
        rot = rotation_matrix(t.transform.rotation)
        tr = t.transform.translation
        off = np.array([tr.x, tr.y, tr.z])
        # 사람 위치는 바닥 높이. 점구름 좌표계가 기울어 있으면(카메라 광학 프레임) xy 거리가 수평 거리가 아니므로
        # 점을 odom으로 올려 수평 거리로 비교한다
        rot_inv = rot.T
        pts_odom = (points - off) @ rot_inv.T
        mask = people_mask(pts_odom, xy, self.radius)
        self.removed += int((~mask).sum())
        pub.publish(keep_rows(msg, mask))

    def report(self):
        if self.removed:
            self.get_logger().debug(f'5 s 동안 사람 점 {self.removed}개 제거')
            self.removed = 0


def main(args=None):
    rclpy.init(args=args)
    node = PersonFilter()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
