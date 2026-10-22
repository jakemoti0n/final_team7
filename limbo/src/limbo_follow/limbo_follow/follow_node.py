"""
따라가기 노드: 등록한 운용자(/follow/target)를 일정 거리 두고 따라간다 (PROJECT.md 2-9).

ROS 입출력(서비스, 토픽, TF, Nav2 액션)만 여기서 하고 계산은 follow.py에 둔다.
- /follow/start (Trigger): 운용자가 보이면 순찰을 pause하고 NavigateToPose(behavior_tree=limbo_follow.xml)를 시작한다
- /follow/stop  (Trigger): Nav2 목표를 취소한다. 순찰은 자동으로 재개하지 않는다(관제가 resume)
- /goal_update  (PoseStamped): 트리의 GoalUpdater가 받는 새 목표점. 운용자에서 follow_distance 떨어진 점을 보낸다
- /follow/state (FollowState): 상태. person_wait가 active일 때 운용자 트랙을 기다리기에서 뺀다
놓치면 마지막 목표점으로 가서 기다리고(HOLDING), lost_stop_sec가 지나면 끝낸다(STOPPED + 경보 로그). 잘못 따라가느니 선다.
"""

import math
import threading
import time

from action_msgs.msg import GoalStatus
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped
from limbo_follow import follow
from limbo_interfaces.msg import FollowState, FollowTarget
from nav2_msgs.action import NavigateToPose
import rclpy
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.time import Time
from std_srvs.srv import Trigger
import tf2_geometry_msgs  # noqa: F401  PoseStamped용 tf2 변환 등록
from tf2_ros import Buffer, TransformException, TransformListener

TARGET_TOPIC = '/follow/target'
STATE_TOPIC = '/follow/state'
GOAL_UPDATE_TOPIC = '/goal_update'      # Nav2 GoalUpdater 기본 토픽 이름
START_SERVICE = '/follow/start'
STOP_SERVICE = '/follow/stop'
PATROL_PAUSE_SERVICE = '/patrol/pause'
TICK_SEC = 0.2
ALARM_PERIOD_SEC = 5.0


def yaw_to_quat(yaw):
    return math.sin(yaw / 2.0), math.cos(yaw / 2.0)


class FollowNode(Node):

    def __init__(self):
        super().__init__('follow_node')
        p = self.declare_parameter
        c = follow.FollowConfig()
        self.config = follow.FollowConfig(
            follow_distance=p('follow_distance', c.follow_distance).value,
            resume_distance=p('resume_distance', c.resume_distance).value,
            target_stale_sec=p('target_stale_sec', c.target_stale_sec).value,
            lost_stop_sec=p('lost_stop_sec', c.lost_stop_sec).value,
            goal_min_move=p('goal_min_move', c.goal_min_move).value,
            search_ahead=p('search_ahead', c.search_ahead).value,
        )
        self.map_frame = p('map_frame', 'map').value
        self.robot_frame = p('robot_frame', 'base_link').value
        self.bt_xml = p('behavior_tree', '').value or \
            get_package_share_directory('limbo_navigation') + '/behavior_trees/limbo_follow.xml'

        self.lock = threading.Lock()
        self.state = FollowState.IDLE
        self.reason = 'idle'
        self.state_since = time.monotonic()
        self.target = None            # 마지막 FollowTarget
        self.found_wall = None        # 마지막으로 found였던 벽시계. 한 프레임 못 본 것으로는 놓침이 되지 않게 이 시각으로 판단
        self.target_map = None        # 마지막으로 본 운용자 map 위치 (x, y)
        self.target_heading = None    # 그때 운용자가 가던 방향 (속도 0.1 m/s 넘을 때만)
        self.target_id = -1           # 마지막으로 본 운용자 트랙 번호 (못 본 프레임의 -1로 덮지 않는다)
        self.lost_since = None
        self.moving = False
        self.last_goal = None
        self.distance = 0.0
        self.goal_handle = None
        self.last_alarm = 0.0

        self.tf_buffer = Buffer()
        TransformListener(self.tf_buffer, self)
        group = ReentrantCallbackGroup()
        self.create_subscription(FollowTarget, TARGET_TOPIC, self.on_target, 10, callback_group=group)
        self.state_pub = self.create_publisher(FollowState, STATE_TOPIC, 10)
        self.goal_pub = self.create_publisher(PoseStamped, GOAL_UPDATE_TOPIC, 10)
        self.nav = ActionClient(self, NavigateToPose, 'navigate_to_pose', callback_group=group)
        self.patrol_pause = self.create_client(Trigger, PATROL_PAUSE_SERVICE, callback_group=group)
        self.create_service(Trigger, START_SERVICE, self.on_start, callback_group=group)
        self.create_service(Trigger, STOP_SERVICE, self.on_stop, callback_group=group)
        self.create_timer(TICK_SEC, self.on_tick, callback_group=group)
        self.get_logger().info(
            f'따라가기 준비: 거리 {self.config.follow_distance} m(재출발 {self.config.resume_distance} m), '
            f'놓침 {self.config.lost_stop_sec} s, 트리 {self.bt_xml}')

    # ---- 입력 ----

    def on_target(self, msg):
        with self.lock:
            self.target = msg
            if msg.found:
                xy = self._to_map(msg.header.frame_id, msg.header.stamp, msg.position.x, msg.position.y)
                if xy is not None:
                    self.target_map = xy
                    self.found_wall = time.monotonic()
                    self.target_id = int(msg.person_id)
                    if math.hypot(msg.velocity.x, msg.velocity.y) > 0.1:
                        self.target_heading = self._heading_to_map(msg.header.frame_id, msg.velocity.x, msg.velocity.y)

    def _to_map(self, frame, stamp, x, y):
        pose = PoseStamped()
        pose.header.frame_id = frame
        pose.header.stamp = stamp
        pose.pose.position.x, pose.pose.position.y = float(x), float(y)
        pose.pose.orientation.w = 1.0
        try:
            out = self.tf_buffer.transform(pose, self.map_frame, timeout=rclpy.duration.Duration(seconds=0.1))
        except TransformException as ex:
            self.get_logger().warn(f'TF {frame} -> {self.map_frame} 실패: {ex}', throttle_duration_sec=2.0)
            return None
        return out.pose.position.x, out.pose.position.y

    def _heading_to_map(self, frame, vx, vy):
        """odom 기준 속도 방향을 map 기준 yaw로 (회전만 적용)."""
        try:
            tf = self.tf_buffer.lookup_transform(self.map_frame, frame, Time())
        except TransformException:
            return None
        q = tf.transform.rotation
        return math.atan2(vy, vx) + 2.0 * math.atan2(q.z, q.w)

    def _robot_xy(self):
        pose = self._robot_pose()
        return None if pose is None else pose[:2]

    def _robot_pose(self):
        """로봇의 map 자세 (x, y, yaw), TF 실패 시 None."""
        try:
            tf = self.tf_buffer.lookup_transform(self.map_frame, self.robot_frame, Time())
        except TransformException as ex:
            self.get_logger().warn(f'TF {self.map_frame} -> {self.robot_frame} 실패: {ex}', throttle_duration_sec=2.0)
            return None
        t, q = tf.transform.translation, tf.transform.rotation
        return t.x, t.y, 2.0 * math.atan2(q.z, q.w)

    def _target_visible(self):
        """운용자를 최근(target_stale_sec 안)에 본 적이 있는가. 한두 프레임 못 본 것은 놓침으로 치지 않는다."""
        return (self.found_wall is not None
                and time.monotonic() - self.found_wall <= self.config.target_stale_sec)

    # ---- 서비스 ----

    def on_start(self, request, response):
        with self.lock:
            if self.state in (FollowState.FOLLOWING, FollowState.HOLDING):
                response.success, response.message = False, 'already_following'
                return response
            if self.target is None or not self.target.enrolled:
                response.success, response.message = False, 'operator_not_enrolled'
                return response
            if not self._target_visible() or self.target_map is None:
                response.success, response.message = False, 'operator_not_visible'
                return response
            robot = self._robot_xy()
            if robot is None:
                response.success, response.message = False, 'no_robot_pose'
                return response
            goal, yaw, dist = follow.standoff_goal(robot, self.target_map, self.config.follow_distance)
        self._pause_patrol()
        if not self.nav.wait_for_server(timeout_sec=2.0):
            response.success, response.message = False, 'nav2_not_ready'
            return response
        if not self._send_nav_goal(goal, yaw):
            response.success, response.message = False, 'nav2_rejected'
            return response
        with self.lock:
            self.moving = follow.should_move(dist, False, self.config)
            self.last_goal = goal
            self.distance = dist
            self.lost_since = None
            self._set_state(FollowState.FOLLOWING, 'started')
        response.success, response.message = True, f'following person {self.target_id} at {dist:.2f} m'
        self.get_logger().info(f'따라가기 시작: {response.message}')
        return response

    def on_stop(self, request, response):
        with self.lock:
            active = self.state in (FollowState.FOLLOWING, FollowState.HOLDING)
            self._set_state(FollowState.STOPPED, 'stop_requested')
        self._cancel_nav()
        response.success, response.message = True, 'stopped' if active else 'was_not_following'
        self.get_logger().info('따라가기 정지 (명령)')
        return response

    def _pause_patrol(self):
        if not self.patrol_pause.wait_for_service(timeout_sec=0.5):
            self.get_logger().info('순찰 노드 없음: pause 생략')
            return
        future = self.patrol_pause.call_async(Trigger.Request())
        future.add_done_callback(
            lambda f: self.get_logger().info(f'순찰 pause: {f.result().message if f.result() else "응답 없음"}'))

    # ---- Nav2 ----

    def _send_nav_goal(self, goal_xy, yaw):
        goal = NavigateToPose.Goal()
        goal.pose = self._pose(goal_xy, yaw)
        goal.behavior_tree = self.bt_xml
        future = self.nav.send_goal_async(goal)
        done = threading.Event()
        future.add_done_callback(lambda f: done.set())
        if not done.wait(3.0) or future.result() is None or not future.result().accepted:
            return False
        self.goal_handle = future.result()
        self.goal_handle.get_result_async().add_done_callback(self._on_nav_result)
        return True

    def _on_nav_result(self, future):
        status = future.result().status
        with self.lock:
            if self.state not in (FollowState.FOLLOWING, FollowState.HOLDING):
                return
            name = {GoalStatus.STATUS_SUCCEEDED: 'succeeded', GoalStatus.STATUS_ABORTED: 'aborted',
                    GoalStatus.STATUS_CANCELED: 'canceled'}.get(status, str(status))
            self._set_state(FollowState.STOPPED, f'nav_{name}')
        self.get_logger().warn(f'따라가기 끝: Nav2 목표가 끝남 ({name})')

    def _cancel_nav(self):
        handle = self.goal_handle
        self.goal_handle = None
        if handle is not None:
            handle.cancel_goal_async()

    def _pose(self, xy, yaw):
        pose = PoseStamped()
        pose.header.frame_id = self.map_frame
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x, pose.pose.position.y = float(xy[0]), float(xy[1])
        pose.pose.orientation.z, pose.pose.orientation.w = yaw_to_quat(yaw)
        return pose

    # ---- 주기 ----

    def on_tick(self):
        with self.lock:
            if self.state in (FollowState.FOLLOWING, FollowState.HOLDING):
                self._tick_active()
            self._publish_state()

    def _tick_active(self):
        now = time.monotonic()
        pose = self._robot_pose()
        robot = None if pose is None else pose[:2]
        if self._target_visible() and self.target_map is not None and robot is not None:
            self.lost_since = None
            goal, yaw, dist = follow.standoff_goal(robot, self.target_map, self.config.follow_distance)
            self.distance = dist
            self.moving = follow.should_move(dist, self.moving, self.config)
            if self.moving:
                if follow.goal_changed(self.last_goal, goal, self.config.goal_min_move):
                    self.goal_pub.publish(self._pose(goal, yaw))
                    self.last_goal = goal
                self._set_state(FollowState.FOLLOWING, 'moving', keep_time=True)
            else:
                # 가까우면 제자리: 목표점을 로봇 자리로 보내 멈춘다 (운용자 쪽으로 더 가지 않음)
                if follow.goal_changed(self.last_goal, robot, self.config.goal_min_move):
                    self.goal_pub.publish(self._pose(robot, yaw))
                    self.last_goal = robot
                self._set_state(FollowState.FOLLOWING, 'near_hold', keep_time=True)
            return

        # 운용자를 못 보는 중: 마지막으로 있던 자리까지 가서 가던 방향을 본다 (모퉁이를 돌았으면 거기서 다시 보인다).
        # 표준 목표점(1.2 m 앞)에 서면 모퉁이 너머가 안 보여 2단계 2회차에서 5 s 뒤 끝났다
        if self.lost_since is None:
            self.lost_since = now
            if self.target_map is not None and robot is not None:
                face = math.atan2(self.target_map[1] - robot[1], self.target_map[0] - robot[0])
                if self.distance <= self.config.resume_distance:
                    # 가까이서 놓침: 운용자는 바로 앞에 있는데 카메라 아래쪽(발목 밴드)으로 벗어난 것이다. 그 자리로 가면
                    # 운용자 몸으로 파고든다(2단계 4회차 0.77 m). 지금 자세 그대로 선다 (돌리면 MPPI가 호를 그리며 0.6 m 움직였다, 6회차)
                    self.goal_pub.publish(self._pose(robot, pose[2]))
                    self.last_goal = robot
                else:
                    # 멀리서 놓침(모퉁이): 마지막 자리에서 가던 방향으로 search_ahead만큼 더 간 점을 목표로 두어 모퉁이 너머를
                    # 내다본다. 마지막 자리에 서면 돌아서는 사이 운용자가 5 m(카메라 범위) 밖으로 나갔다(2단계 7회차)
                    yaw = self.target_heading if self.target_heading is not None else face
                    goal = follow.search_goal(self.target_map, self.target_heading, self.config.search_ahead)
                    self.goal_pub.publish(self._pose(goal, yaw))
                    self.last_goal = goal
        lost = now - self.lost_since
        if lost > self.config.lost_stop_sec:
            self._set_state(FollowState.STOPPED, 'lost_timeout')
            self._cancel_nav()
            self.get_logger().error(f'운용자를 {lost:.1f} s 넘게 놓쳐 따라가기를 끝냄 (경보)')
            return
        if self.state != FollowState.HOLDING:
            self._set_state(FollowState.HOLDING, 'target_lost')
        elif now - self.last_alarm >= ALARM_PERIOD_SEC:
            self.last_alarm = now
            self.get_logger().warn(f'운용자 놓침 {lost:.1f} s: 마지막 자리에서 기다림')

    def _set_state(self, state, reason, keep_time=False):
        if state != self.state or not keep_time:
            if state != self.state:
                self.state_since = time.monotonic()
                self.get_logger().info(f'따라가기 {self.state} → {state} ({reason})')
        self.state = state
        self.reason = reason

    def _publish_state(self):
        msg = FollowState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.map_frame
        msg.state = self.state
        msg.active = self.state in (FollowState.FOLLOWING, FollowState.HOLDING)
        msg.target_id = self.target_id if msg.active else -1
        msg.distance = float(self.distance)
        msg.reason = self.reason
        msg.elapsed_sec = float(time.monotonic() - self.state_since)
        msg.lost_sec = float(time.monotonic() - self.lost_since) if self.lost_since is not None else 0.0
        self.state_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = FollowNode()
    executor = MultiThreadedExecutor(num_threads=3)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == '__main__':
    main()
