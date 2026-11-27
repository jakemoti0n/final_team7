"""
정책 노드: 스캔이 올 때마다 학습한 앙상블로 속도 명령을 내 /cmd_vel_policy로 보낸다.

- 입력 조립은 frame_builder(데이터셋과 같은 함수), 추론은 model.Ensemble, 가속 제한은 model.limit_acceleration.
- 입력 조립 설정(FrameSettings)과 속도 상한은 모델 파일의 값을 쓴다. 학습한 그대로여야 해서다.
- /policy/status: {"ok", "reason", "disagreement", "threshold"}. ok=false면 중재기가 nav로 넘긴다.
  입력이 모자라면(no_scan·no_scan_tf·no_tf·no_odom·no_people·no_waypoint) 명령을 내지 않는다.
  no_scan_tf = base에서 스캔 프레임으로 가는 TF가 없어 스캔을 base 기준으로 못 옮김(데이터셋과 같은 입력을 못 만듦).
  모델이 없으면(no_model) 경고 한 번, 명령 없이 status만.
"""

import json
import math
import os
import statistics
import time

from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import Twist
from limbo_imitation import frame_builder
from limbo_interfaces.msg import PatrolState, PersonPredictionArray
from nav_msgs.msg import Odometry
import rclpy
from rclpy.duration import Duration
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, qos_profile_sensor_data, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String
from tf2_ros import TransformException
from tf2_ros.buffer import Buffer
from tf2_ros.transform_listener import TransformListener

try:
    from limbo_imitation import model as policy_model
except ImportError as missing_torch:
    # torch가 없는 보드에서도 노드는 떠서 status no_model을 내야 중재기가 이유를 안다
    policy_model, TORCH_IMPORT_ERROR = None, missing_torch
else:
    TORCH_IMPORT_ERROR = None

MS_PER_SEC = 1000.0
TF_LOOKUP_TIMEOUT = Duration(seconds=0.0)  # 스캔 콜백을 막지 않는다. 없으면 no_tf


def default_waypoints():
    return os.path.join(get_package_share_directory('limbo_patrol'), 'config',
                        'real_loop_waypoints.yaml')


class PolicyNode(Node):

    def __init__(self):
        super().__init__('policy_node')
        p = self.declare_parameter
        self.input_timeout = p('input_timeout', 0.5).value
        self.ax_max = p('ax_max', 0.502).value
        self.aw_max = p('aw_max', 1.894).value
        self.frames = {name: p(name + '_frame', default).value for name, default in
                       (('map', 'map'), ('odom', 'odom'), ('base', 'base_footprint'))}
        self.timing_log_period = p('timing_log_period', 10.0).value
        self.waypoints = frame_builder.load_waypoints(p('waypoints_file', '').value
                                                      or default_waypoints())
        self.ensemble, self.model_info = self.load_model(p('model_path', '').value,
                                                         p('backend', 'torch').value)
        self.latest = {'odom': None, 'people': None, 'patrol': None, 'scan_time': None}
        self.mounts = {}
        self.history, self.previous, self.timings = [], None, []
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self._subscribe_and_advertise(p)
        self.create_timer(self.input_timeout, self.on_watchdog)
        self.create_timer(self.timing_log_period, self.on_timing_log)

    def load_model(self, path, backend):
        """(Ensemble, 파일 내용) 또는 (None, None). 실패는 경고 한 번만 남기고 노드는 계속 산다.

        노드가 죽으면 status가 끊겨 중재기가 원인을 모른 채 nav로 가고, no_model을 내면 이유가 남는다.
        """
        if policy_model is None:
            self.get_logger().warning(f'cannot load policy model ({TORCH_IMPORT_ERROR})')
            return None, None
        if not path or not os.path.isfile(path):
            self.get_logger().warning(f'no policy model file: "{path}" (status no_model)')
            return None, None
        try:
            ensemble, info = policy_model.load_policy(path, backend=backend)
        except (ValueError, RuntimeError, KeyError, OSError) as error:
            self.get_logger().warning(f'policy model load failed: {path}: {error}')
            return None, None
        info['frame_settings'] = frame_builder.settings_from_dict(info['frame_settings'])
        self.get_logger().info(f'policy model {path} ({len(ensemble.models)} models, '
                               f'backend {backend}, threshold {info["threshold"]:.4f})')
        return ensemble, info

    def _subscribe_and_advertise(self, p):
        sensor = qos_profile_sensor_data
        latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(LaserScan, p('scan_topic', '/scan').value, self.on_scan,
                                 sensor)
        self.create_subscription(Odometry, p('odom_topic', '/odom').value, self.on_odom, sensor)
        self.create_subscription(PatrolState, p('patrol_state_topic', '/patrol/state').value,
                                 self.on_patrol, latched)
        self.create_subscription(PersonPredictionArray,
                                 p('predictions_topic', '/person_detector/predictions').value,
                                 self.on_people, sensor)
        self.cmd_pub = self.create_publisher(Twist, p('cmd_topic', '/cmd_vel_policy').value, 10)
        self.status_pub = self.create_publisher(
            String, p('status_topic', '/policy/status').value, 10)

    def now(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def on_odom(self, msg):
        twist = msg.twist.twist
        self.latest['odom'] = (self.now(), (twist.linear.x, twist.angular.z))

    def on_people(self, msg):
        self.latest['people'] = (self.now(), [
            (p.current_position.x, p.current_position.y, p.velocity.x, p.velocity.y)
            for p in msg.predictions])

    def on_patrol(self, msg):
        """상태가 바뀔 때만 오는 래치 토픽이라 신선도를 보지 않는다(마지막 값이 지금 값)."""
        self.latest['patrol'] = msg.waypoint_index

    def lookup_pose(self, parent, now):
        """(x, y, yaw), 나이 초. 없으면 None."""
        try:
            stamped = self.tf_buffer.lookup_transform(parent, self.frames['base'], Time(),
                                                      TF_LOOKUP_TIMEOUT)
        except TransformException:
            return None
        tr, q = stamped.transform.translation, stamped.transform.rotation
        stamp = Time.from_msg(stamped.header.stamp).nanoseconds * 1e-9
        return (tr.x, tr.y, frame_builder.yaw_from_quaternion(q.x, q.y, q.z, q.w)), now - stamp

    def collect_inputs(self, now):
        """입력 원재료 dict 또는 모자란 이유. 판정은 데이터셋과 같은 frame_builder.input_problem."""
        pose_map = self.lookup_pose(self.frames['map'], now)
        pose_odom = self.lookup_pose(self.frames['odom'], now)
        tf_age = (max(pose_map[1], pose_odom[1]) if pose_map and pose_odom else None)
        goal = frame_builder.waypoint_goal(self.waypoints, self.latest['patrol'])
        ages = {'tf': tf_age}
        for key in ('odom', 'people'):
            ages[key] = None if self.latest[key] is None else now - self.latest[key][0]
        problem = frame_builder.input_problem(ages, goal, self.input_timeout)
        if problem is not None:
            return problem
        return {'pose_map': pose_map[0], 'pose_odom': pose_odom[0], 'goal': goal,
                'velocity': self.latest['odom'][1], 'people': self.latest['people'][1]}

    def on_scan(self, msg):
        now = self.now()
        previous_scan, self.latest['scan_time'] = self.latest['scan_time'], now
        if self.ensemble is None:
            self.publish_status('no_model')
            return
        started = time.perf_counter()
        inputs = self.collect_inputs(now)
        if isinstance(inputs, str):
            self.publish_status(inputs)
            return
        mount = self.scan_mount(msg.header.frame_id)
        if mount is None:
            self.publish_status('no_scan_tf')
            return
        frame = frame_builder.assemble_frame(
            (msg.ranges, msg.angle_min, msg.angle_increment), inputs['pose_map'],
            inputs['pose_odom'], inputs['goal'], inputs['velocity'], inputs['people'],
            self.model_info['frame_settings'], mount)
        x = frame_builder.push_and_stack(self.history, frame)
        v, w, disagreement = self.ensemble.predict(x)
        self.timings.append((time.perf_counter() - started) * MS_PER_SEC)
        scan_dt = 0.0 if previous_scan is None else now - previous_scan
        self.publish_command(now, (float(v), float(w)), scan_dt)
        ok = disagreement <= self.model_info['threshold']
        self.publish_status('ok' if ok else 'disagreement', float(disagreement))

    def scan_mount(self, scan_frame):
        """base에서 본 스캔 프레임 (x, y, yaw). 장착은 정적이라 한 번 얻으면 둔다. 아직 없으면 None."""
        if self.mounts.get(scan_frame) is None:
            try:
                tr = self.tf_buffer.lookup_transform(self.frames['base'], scan_frame, Time(),
                                                     TF_LOOKUP_TIMEOUT).transform
            except TransformException:
                return None
            q = tr.rotation
            self.mounts[scan_frame] = (tr.translation.x, tr.translation.y,
                                       frame_builder.yaw_from_quaternion(q.x, q.y, q.z, q.w))
        return self.mounts[scan_frame]

    def publish_command(self, now, target, scan_dt):
        """가속을 제한해 명령을 낸다.

        직전 명령이 input_timeout보다 오래됐으면(처음·끊겼다 다시 시작) 지금 odom 속도에서
        스캔 한 간격만큼만 바꾼다. 멈춰 있던 로봇에 갑자기 최고 속도를 내리지 않게.
        """
        if self.previous is None or now - self.previous[0] > self.input_timeout:
            start, dt = self.latest['odom'][1], scan_dt
        else:
            start, dt = self.previous[1], now - self.previous[0]
        v, w = policy_model.limit_acceleration(start, target, dt, self.ax_max, self.aw_max)
        self.previous = (now, (v, w))
        twist = Twist()
        twist.linear.x, twist.angular.z = v, w
        self.cmd_pub.publish(twist)

    def publish_status(self, reason, disagreement=math.nan):
        threshold = self.model_info['threshold'] if self.model_info else math.nan
        payload = {'ok': reason == 'ok', 'reason': reason,
                   'disagreement': None if math.isnan(disagreement) else disagreement,
                   'threshold': None if math.isnan(threshold) else threshold}
        self.status_pub.publish(String(data=json.dumps(payload)))

    def on_watchdog(self):
        """스캔이 끊기면 on_scan이 안 불려 status도 끊긴다. 이유를 남기려고 따로 낸다."""
        scan_time = self.latest['scan_time']
        if scan_time is None or self.now() - scan_time > self.input_timeout:
            self.publish_status('no_model' if self.ensemble is None else 'no_scan')

    def on_timing_log(self):
        if not self.timings:
            return
        self.get_logger().info(
            f'processing time (inputs + inference) over {len(self.timings)} scans: '
            f'median {statistics.median(self.timings):.2f} ms, max {max(self.timings):.2f} ms')
        self.timings = []


def main(args=None):
    rclpy.init(args=args)
    node = PolicyNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
