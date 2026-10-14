"""
Nav2 Goal이 끝날 때마다 주행 평가 지표를 CSV에 한 줄씩 남기는 노드 (시뮬레이션 전용).

Gazebo 정답 위치(/ground_truth/odom)와 월드 SDF의 사람 시간표를 기준으로
주행 시간·거리, 사람과의 최소 거리(0.3 m 미만은 충돌)와 그 순간 사람이 다가온 속도·로봇 속도(사람 탓/로봇 탓 구분),
멈춘 시간(사람 앞 / 그 외), 전역 경로가 바뀐 횟수, 위치 추정 오차 등을 잰다.
Goal은 navigate_to_pose(RViz·nav_route.py)와 navigate_through_poses(순찰) 둘 다 본다.
위치 추정 오차는 TF(map → base_footprint)로 재므로 AMCL이 아닌 다른 위치 추정을 써도 같은 기준이다.
Goal은 RViz·순찰 노드 등 누가 보내든 Nav2 액션 상태를 보고 따라간다.
"""

import bisect
import math
import os
import time

from action_msgs.msg import GoalStatus, GoalStatusArray
from ament_index_python.packages import get_package_share_directory, PackageNotFoundError
from geometry_msgs.msg import PoseArray
from limbo_evaluation import actors, csv_log, goal_metrics, obstacles, walls
from nav2_msgs.action import NavigateThroughPoses, NavigateToPose
from nav_msgs.msg import OccupancyGrid, Odometry, Path
from rcl_interfaces.msg import Log
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, qos_profile_action_status_default
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from std_msgs.msg import Bool, String
from tf2_ros import Buffer, TransformException, TransformListener

QUEUE = 10
# TF는 정답보다 늦게 도착할 수 있어 TF 시각의 정답 위치와 비교한다. 그만큼 지난 정답을 들고 있는다
TRUTH_HISTORY_SEC = 5.0
MAX_TRUTH_GAP_SEC = 0.1   # 이보다 시각 차이가 큰 정답과는 비교하지 않는다
# 소셜 포스로 움직이는 시뮬레이션 사람은 시간표가 없어 /sim/people로 위치를 받는다. 이보다 오래되면 안 쓴다
LIVE_PEOPLE_MAX_AGE_SEC = 0.5
FINISHED = {
    GoalStatus.STATUS_SUCCEEDED: 'SUCCEEDED',
    GoalStatus.STATUS_CANCELED: 'CANCELED',
    GoalStatus.STATUS_ABORTED: 'ABORTED',
}
CONTROLLER_RATE_WARNING = 'Control loop missed its desired rate'


def stamp_sec(stamp):
    return stamp.sec + stamp.nanosec * 1e-9


class NavRecorder(Node):

    def __init__(self):
        super().__init__('nav_recorder')
        self._declare_parameters()

        self.trajectories, self.boxes = self._load_world()
        self.goal_id = None    # 따라가는 Goal의 uuid
        self.goal_action = ''  # 그 Goal이 온 액션 이름
        self.metrics = None
        self.truth_times = []
        self.truth_poses = []  # (시각, x, y)
        self.slipping = False
        self.live_people = None        # (시각, [(이름, x, y), ...]) — /sim/people이 오면 SDF 시간표 대신 쓴다
        self.live_people_names = []
        self.wall_distance = None      # /map이 오면 지도 벽까지 거리 (경로가 벽에 붙는 정도)
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.csv_path = os.path.join(
            os.path.expanduser(self.output_dir),
            f'nav_{self.world}_{time.strftime("%Y%m%d_%H%M%S")}.csv')

        self.create_subscription(Odometry, self.truth_topic, self.truth_callback, QUEUE)
        # Goal 하나(RViz·nav_route.py)는 navigate_to_pose, 순찰 노드는 navigate_through_poses. 둘 다 본다
        for action, feedback_type in (
                (self.navigate_action, NavigateToPose.Impl.FeedbackMessage),
                (self.through_poses_action, NavigateThroughPoses.Impl.FeedbackMessage)):
            self.create_subscription(
                GoalStatusArray, action + '/_action/status',
                lambda msg, a=action: self.status_callback(msg, a),
                qos_profile_action_status_default)
            self.create_subscription(
                feedback_type, action + '/_action/feedback', self.feedback_callback, QUEUE)
        self.create_subscription(Log, '/rosout', self.rosout_callback, QUEUE)
        self.create_subscription(Bool, self.slip_topic, self.slip_callback, QUEUE)
        self.create_subscription(Path, self.plan_topic, self.plan_callback, QUEUE)
        self.create_subscription(PoseArray, '/sim/people', self.people_callback, QUEUE)
        self.create_subscription(String, '/sim/people_names', self.people_names_callback, QUEUE)
        self.create_subscription(
            OccupancyGrid, '/map', self.map_callback,
            QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                       durability=DurabilityPolicy.TRANSIENT_LOCAL))

        self.get_logger().info(
            f'Nav recorder started: {len(self.trajectories)} people, '
            f'{len(self.boxes)} obstacles in {self.world}, '
            f'results -> {self.csv_path}')

    def _declare_parameters(self):
        # 코드 기본값은 yaml 없이도 노드가 뜨게 하는 보험이다. 튜닝은 yaml에서 한다.
        p = self.declare_parameter

        self.world = p('world', 'human_test_world').value
        self.output_dir = p('output_dir', '~/limbo_results').value
        self.truth_topic = p('truth_topic', '/ground_truth/odom').value
        self.map_frame = p('map_frame', 'map').value
        self.base_frame = p('base_frame', 'base_footprint').value
        self.navigate_action = p('navigate_action', '/navigate_to_pose').value
        self.through_poses_action = p('through_poses_action', '/navigate_through_poses').value
        self.slip_topic = p('slip_topic', '/wheel_slip').value
        self.plan_topic = p('plan_topic', '/plan').value
        self.controller_node = p('controller_node', 'controller_server').value
        # 로봇 외곽 (정사각형 한 변의 절반). nav2_params.yaml의 footprint와 맞춘다
        self.robot_half_size = p('robot_half_size', 0.225).value

        m = goal_metrics.MetricsConfig()
        self.metrics_config = goal_metrics.MetricsConfig(
            personal_space=p('personal_space', m.personal_space).value,
            collision_distance=p('collision_distance', m.collision_distance).value,
            near_person_distance=p('near_person_distance', m.near_person_distance).value,
            stop_speed=p('stop_speed', m.stop_speed).value,
            plan_change_distance=p('plan_change_distance', m.plan_change_distance).value,
            speed_window=p('speed_window', m.speed_window).value)

    def _load_world(self):
        """(사람 시간표, 장애물 상자). 월드 파일을 못 읽으면 둘 다 비운다."""
        try:
            path = os.path.join(
                get_package_share_directory('limbo_simulation'), 'worlds', f'{self.world}.sdf')
            with open(path) as f:
                sdf = f.read()
        except (OSError, PackageNotFoundError) as e:
            self.get_logger().warn(f'Cannot read {self.world} ({e}). Person metrics are empty')
            return {}, []
        return actors.parse_actor_trajectories(sdf), obstacles.parse_boxes(sdf)

    def truth_callback(self, msg):
        t = stamp_sec(msg.header.stamp)
        x, y = msg.pose.pose.position.x, msg.pose.pose.position.y
        q = msg.pose.pose.orientation
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        dt = t - self.truth_times[-1] if self.truth_times else 0.0
        self.truth_times.append(t)
        self.truth_poses.append((t, x, y))
        cut = bisect.bisect_left(self.truth_times, t - TRUTH_HISTORY_SEC)
        del self.truth_times[:cut], self.truth_poses[:cut]

        if self.metrics is not None:
            name, distance, person_xy = self._nearest_person(t, x, y)
            self.metrics.add_truth(t, x, y, name, distance, person_xy)
            name, distance = obstacles.nearest_box(self.boxes, x, y, yaw, self.robot_half_size)
            self.metrics.add_obstacle(dt, name, distance)
            if self.wall_distance is not None:
                self.metrics.add_wall_distance(self.wall_distance.at(x, y))
            self._add_localization_error()

    def _nearest_person(self, t, x, y):
        """(이름, 거리, 사람 위치). /sim/people이 최근 것이면 그것, 아니면 월드 SDF 시간표."""
        live = self.live_people
        if live is not None and abs(t - live[0]) <= LIVE_PEOPLE_MAX_AGE_SEC:
            best = ('', math.inf, None)
            for name, px, py in live[1]:
                d = math.hypot(px - x, py - y)
                if d < best[1]:
                    best = (name, d, (px, py))
            return best
        name, d = actors.nearest_person(self.trajectories, t, x, y)
        xy = actors.position_at(self.trajectories[name], t) if name else None
        return name, d, xy

    def people_callback(self, msg):
        names = self.live_people_names
        people = [(names[i] if i < len(names) else f'p{i}', p.position.x, p.position.y)
                  for i, p in enumerate(msg.poses)]
        self.live_people = (stamp_sec(msg.header.stamp), people)

    def map_callback(self, msg):
        info = msg.info
        self.wall_distance = walls.WallDistance(
            info.width, info.height, info.resolution,
            info.origin.position.x, info.origin.position.y, msg.data)
        self.get_logger().info('map received: wall distance ready')

    def people_names_callback(self, msg):
        self.live_people_names = msg.data.split(',') if msg.data else []

    def _add_localization_error(self):
        # Nav2가 실제로 쓰는 위치(가장 최근 TF)를 같은 시각의 정답과 비교한다
        try:
            tf = self.tf_buffer.lookup_transform(self.map_frame, self.base_frame, Time())
        except TransformException:
            return
        t = stamp_sec(tf.header.stamp)
        truth = goal_metrics.nearest_in_time(self.truth_times, self.truth_poses, t)
        if truth is None or abs(truth[0] - t) > MAX_TRUTH_GAP_SEC:
            return
        p = tf.transform.translation
        self.metrics.add_localization_error(math.hypot(p.x - truth[1], p.y - truth[2]))

    def status_callback(self, msg, action):
        statuses = {bytes(s.goal_info.goal_id.uuid): s.status for s in msg.status_list}
        mine = self.goal_id is not None and action == self.goal_action
        if mine and statuses.get(self.goal_id) in FINISHED:
            self._finish(FINISHED[statuses[self.goal_id]])

        executing = [g for g, s in statuses.items() if s == GoalStatus.STATUS_EXECUTING]
        if executing and executing[-1] != self.goal_id:
            # 끝나기 전에 새 Goal이 들어오면 Nav2가 이전 Goal을 새 것으로 바꾼다
            if self.goal_id is not None:
                self._finish('PREEMPTED')
            self.goal_id = executing[-1]
            self.goal_action = action
            self.metrics = goal_metrics.GoalMetrics(self.metrics_config)
            self.get_logger().info(f'Goal started ({action})')

    def feedback_callback(self, msg):
        if self.metrics is not None and bytes(msg.goal_id.uuid) == self.goal_id:
            self.metrics.recoveries = max(
                self.metrics.recoveries, msg.feedback.number_of_recoveries)

    def rosout_callback(self, msg):
        if (self.metrics is not None and msg.name == self.controller_node
                and CONTROLLER_RATE_WARNING in msg.msg):
            self.metrics.controller_warnings += 1

    def plan_callback(self, msg):
        if self.metrics is not None:
            self.metrics.add_plan(
                [(p.pose.position.x, p.pose.position.y) for p in msg.poses])

    def slip_callback(self, msg):
        if self.metrics is not None and msg.data and not self.slipping:
            self.metrics.slip_events += 1
        self.slipping = msg.data

    def _finish(self, status):
        row = {'world': self.world, 'action': self.goal_action.strip('/'),
               **self.metrics.row(status)}
        csv_log.append_row(self.csv_path, row)
        self.get_logger().info(
            f'Goal {status}: {row["duration_s"]} s, {row["path_length_m"]} m, '
            f'nearest person {row["min_person_distance_m"]} m '
            f'(collision {row["person_collision"]}, '
            f'person approach {row["person_approach_speed_mps"]} m/s, '
            f'robot {row["robot_speed_at_min_mps"]} m/s), '
            f'stopped {row["stopped_time_s"]} s (near person {row["stopped_near_person_s"]} s), '
            f'plan changes {row["plan_changes"]}/{row["plan_updates"]}, '
            f'localization error max {row["localization_error_max_m"]} m')
        self.goal_id = None
        self.metrics = None


def main(args=None):
    rclpy.init(args=args)
    node = NavRecorder()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
