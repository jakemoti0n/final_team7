"""
Nav2 Goal이 끝날 때마다 주행 평가 지표를 CSV에 한 줄씩 남기는 노드 (시뮬레이션 전용).

Gazebo 정답 위치(/ground_truth/odom)와 월드 SDF의 사람 시간표를 기준으로
주행 시간·거리, 사람과의 최소 거리, 위치 추정 오차 등을 잰다.
위치 추정 오차는 TF(map → base_footprint)로 재므로 AMCL이 아닌 다른 위치 추정을 써도 같은 기준이다.
Goal은 RViz·순찰 노드 등 누가 보내든 Nav2 액션 상태를 보고 따라간다.
"""

import bisect
import math
import os
import time

from action_msgs.msg import GoalStatus, GoalStatusArray
from ament_index_python.packages import get_package_share_directory, PackageNotFoundError
from limbo_evaluation import actors, csv_log, goal_metrics
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import Odometry
from rcl_interfaces.msg import Log
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_action_status_default
from rclpy.time import Time
from std_msgs.msg import Bool
from tf2_ros import Buffer, TransformException, TransformListener

QUEUE = 10
# TF는 정답보다 늦게 도착할 수 있어 TF 시각의 정답 위치와 비교한다. 그만큼 지난 정답을 들고 있는다
TRUTH_HISTORY_SEC = 5.0
MAX_TRUTH_GAP_SEC = 0.1   # 이보다 시각 차이가 큰 정답과는 비교하지 않는다
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

        self.trajectories = self._load_actors()
        self.goal_id = None    # 따라가는 Goal의 uuid
        self.metrics = None
        self.truth_times = []
        self.truth_poses = []  # (시각, x, y)
        self.slipping = False
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.csv_path = os.path.join(
            os.path.expanduser(self.output_dir),
            f'nav_{self.world}_{time.strftime("%Y%m%d_%H%M%S")}.csv')

        action = self.navigate_action
        self.create_subscription(Odometry, self.truth_topic, self.truth_callback, QUEUE)
        self.create_subscription(
            GoalStatusArray, action + '/_action/status', self.status_callback,
            qos_profile_action_status_default)
        self.create_subscription(
            NavigateToPose.Impl.FeedbackMessage, action + '/_action/feedback',
            self.feedback_callback, QUEUE)
        self.create_subscription(Log, '/rosout', self.rosout_callback, QUEUE)
        self.create_subscription(Bool, self.slip_topic, self.slip_callback, QUEUE)

        self.get_logger().info(
            f'Nav recorder started: {len(self.trajectories)} people in {self.world}, '
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
        self.slip_topic = p('slip_topic', '/wheel_slip').value
        self.controller_node = p('controller_node', 'controller_server').value

        m = goal_metrics.MetricsConfig()
        self.metrics_config = goal_metrics.MetricsConfig(
            personal_space=p('personal_space', m.personal_space).value)

    def _load_actors(self):
        try:
            path = os.path.join(
                get_package_share_directory('limbo_simulation'), 'worlds', f'{self.world}.sdf')
            with open(path) as f:
                return actors.parse_actor_trajectories(f.read())
        except (OSError, PackageNotFoundError) as e:
            self.get_logger().warn(f'No people for {self.world} ({e}). Person metrics are empty')
            return {}

    def truth_callback(self, msg):
        t = stamp_sec(msg.header.stamp)
        x, y = msg.pose.pose.position.x, msg.pose.pose.position.y
        self.truth_times.append(t)
        self.truth_poses.append((t, x, y))
        cut = bisect.bisect_left(self.truth_times, t - TRUTH_HISTORY_SEC)
        del self.truth_times[:cut], self.truth_poses[:cut]

        if self.metrics is not None:
            name, distance = actors.nearest_person(self.trajectories, t, x, y)
            self.metrics.add_truth(t, x, y, name, distance)
            self._add_localization_error()

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

    def status_callback(self, msg):
        statuses = {bytes(s.goal_info.goal_id.uuid): s.status for s in msg.status_list}
        if self.goal_id is not None and statuses.get(self.goal_id) in FINISHED:
            self._finish(FINISHED[statuses[self.goal_id]])

        executing = [g for g, s in statuses.items() if s == GoalStatus.STATUS_EXECUTING]
        if executing and executing[-1] != self.goal_id:
            # 끝나기 전에 새 Goal이 들어오면 Nav2가 이전 Goal을 새 것으로 바꾼다
            if self.goal_id is not None:
                self._finish('PREEMPTED')
            self.goal_id = executing[-1]
            self.metrics = goal_metrics.GoalMetrics(self.metrics_config)
            self.get_logger().info('Goal started')

    def feedback_callback(self, msg):
        if self.metrics is not None and bytes(msg.goal_id.uuid) == self.goal_id:
            self.metrics.recoveries = max(
                self.metrics.recoveries, msg.feedback.number_of_recoveries)

    def rosout_callback(self, msg):
        if (self.metrics is not None and msg.name == self.controller_node
                and CONTROLLER_RATE_WARNING in msg.msg):
            self.metrics.controller_warnings += 1

    def slip_callback(self, msg):
        if self.metrics is not None and msg.data and not self.slipping:
            self.metrics.slip_events += 1
        self.slipping = msg.data

    def _finish(self, status):
        row = {'world': self.world, **self.metrics.row(status)}
        csv_log.append_row(self.csv_path, row)
        self.get_logger().info(
            f'Goal {status}: {row["duration_s"]} s, {row["path_length_m"]} m, '
            f'nearest person {row["min_person_distance_m"]} m, '
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
