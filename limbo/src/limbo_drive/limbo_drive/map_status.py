"""지도 작성이 잘 되고 있는지 사람이 RViz에서 읽을 수 있게 로봇 위에 판정문을 띄운다.

글자는 영문이다: RViz 텍스트 마커 글꼴에 한글이 없어 한글은 빈칸으로 나온다 (2026-10-14 확인).

  SLAM 작동 중 / SLAM 갱신 없음 (초록/빨강)  — 지도가 stale_sec 안에 갱신됐는가
  지도 갱신 n회 · n s 전                      — /map이 온 횟수와 마지막 시각
  포즈그래프 노드 n개                         — 로봇이 0.5 m 갈 때마다 1개씩 늘어야 정상 (/slam_toolbox/graph_visualization)
  위치 보정 n cm                              — map→odom 차이. 0에 고정이면 SLAM이 아무것도 고치지 않는 것
  지도 W×H m · 알려진 칸 n %
  자동 저장 n s 전                             — tools/make_map.sh의 자동 저장 시각
"""
import math
import os
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time

from nav_msgs.msg import OccupancyGrid
from visualization_msgs.msg import Marker, MarkerArray
from tf2_ros import Buffer, TransformListener


class MapStatus(Node):

    def __init__(self):
        super().__init__('map_status')
        self.stamp_file = self.declare_parameter('autosave_stamp_file', '').value
        self.map_name = self.declare_parameter('map_name', '').value
        self.stale_sec = self.declare_parameter('stale_sec', 10.0).value
        self.map_text = 'waiting for map'
        self.map_updates = 0
        self.last_map_time = None      # 벽시계(time.monotonic). 시뮬 시간이 멈춰도 "안 온다"가 보이게
        self.graph_nodes = 0
        latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(OccupancyGrid, '/map', self.on_map, latched)
        self.create_subscription(MarkerArray, '/slam_toolbox/graph_visualization', self.on_graph, 10)
        self.pub = self.create_publisher(Marker, '/map_status', 1)
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.create_timer(1.0, self.tick)

    def on_map(self, msg):
        self.map_updates += 1
        self.last_map_time = time.monotonic()
        n = len(msg.data)
        known = sum(1 for v in msg.data if v >= 0)
        w = msg.info.width * msg.info.resolution
        h = msg.info.height * msg.info.resolution
        self.map_text = f'map {w:.0f}x{h:.0f} m, known {100 * known / max(n, 1):.0f}%'

    def on_graph(self, msg):
        # slam_toolbox는 노드마다 SPHERE 마커 하나(또는 SPHERE_LIST의 점), 간선은 LINE_LIST
        self.graph_nodes = sum(1 if m.type == Marker.SPHERE else len(m.points)
                               for m in msg.markers if m.type in (Marker.SPHERE, Marker.SPHERE_LIST))

    def correction_cm(self):
        """map→odom 이동량(cm). SLAM이 오도메트리를 얼마나 고쳤는지."""
        try:
            t = self.tf_buffer.lookup_transform('map', 'odom', Time())
            return 100.0 * math.hypot(t.transform.translation.x, t.transform.translation.y)
        except Exception:
            return None

    def tick(self):
        if self.last_map_time is None:
            verdict, color = 'SLAM: NO MAP YET', (0.8, 0.5, 0.0)
            ago = '-'
        else:
            since = time.monotonic() - self.last_map_time
            ago = f'{since:.0f} s ago'
            if since < self.stale_sec:
                verdict, color = 'SLAM OK', (0.0, 0.5, 0.0)
            else:
                verdict, color = f'SLAM STALE ({since:.0f} s)', (0.8, 0.0, 0.0)
        corr = self.correction_cm()
        corr_text = f'correction {corr:.0f} cm' if corr is not None else 'correction: no map->odom TF'
        saved = 'autosave: none'
        if self.stamp_file and os.path.exists(self.stamp_file):
            saved = f'autosave {time.time() - os.path.getmtime(self.stamp_file):.0f} s ago'
        m = Marker()
        m.header.frame_id = 'base_footprint'
        m.header.stamp = self.get_clock().now().to_msg()
        m.ns, m.id, m.type, m.action = 'map_status', 0, Marker.TEXT_VIEW_FACING, Marker.ADD
        m.pose.position.z = 2.2
        m.pose.orientation.w = 1.0
        m.scale.z = 0.45
        m.color.r, m.color.g, m.color.b, m.color.a = color[0], color[1], color[2], 1.0
        m.text = '\n'.join([
            verdict,
            f'map updates {self.map_updates} ({ago})',
            f'graph nodes {self.graph_nodes}',
            corr_text,
            f'{self.map_name}: {self.map_text}',
            saved,
        ])
        self.pub.publish(m)


def main(args=None):
    rclpy.init(args=args)
    node = MapStatus()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):   # Ctrl+C·launch 종료 때 조용히 끝낸다
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
