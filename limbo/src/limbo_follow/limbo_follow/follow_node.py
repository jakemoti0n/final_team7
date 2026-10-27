"""
따라가기 노드: 등록한 운용자(/follow/target)를 일정 거리 두고 따라간다 (PROJECT.md 2-9).

ROS 입출력(서비스, 토픽, TF, Nav2 액션)만 여기서 하고 계산은 follow.py에 둔다.
- /follow/start (Trigger): 운용자가 보이면 순찰을 pause하고 NavigateToPose(behavior_tree=limbo_follow.xml)를 시작한다
- /follow/stop  (Trigger): Nav2 목표를 취소한다. 순찰은 자동으로 재개하지 않는다(관제가 resume)
- /goal_update  (PoseStamped): 트리의 GoalUpdater가 받는 새 목표점. 운용자에서 follow_distance 떨어진 점을 보낸다
- /follow/state (FollowState): 상태. person_wait가 active일 때 운용자 트랙을 기다리기에서 뺀다
놓치면(HOLDING) follow.lost_plan대로 자세 그대로 서기·돌아보기·내다보기·마지막 자리 보기 중 하나를 하고, lost_stop_sec가 지나면
끝낸다(STOPPED + 경보 로그). 잘못 따라가느니 선다.
"""

from collections import deque
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
            moving_speed=p('moving_speed', c.moving_speed).value,
            look_angle_deg=p('look_angle_deg', c.look_angle_deg).value,
            moving_window_sec=p('moving_window_sec', c.moving_window_sec).value,
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
        self.target_heading = None    # 그때 운용자가 가던 방향 (걷고 있을 때만 갱신, 멈춰도 마지막 방향을 기억)
        self.target_moving = False    # 마지막으로 봤을 때 걷고 있었나 (moving_speed 기준). 멈춰 있던 운용자는 내다보지 않는다
        self.target_history = deque()  # 최근 moving_window_sec 동안 본 (벽시계, map x, y). 걷는 중인지는 이 이동량으로 판단
        self.lost_mode = None         # 놓침 대응 모드 (follow.lost_plan): hold | look | search | watch
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
                    # 걷는 중인지는 추적기 속도(msg.velocity)가 아니라 최근 위치 이력의 이동량으로 (follow.motion_from_history 설명)
                    now = self.found_wall
                    self.target_history.append((now, xy[0], xy[1]))
                    while self.target_history and now - self.target_history[0][0] > self.config.moving_window_sec:
                        self.target_history.popleft()
                    moving, heading, _ = follow.motion_from_history(
                        self.target_history, self.config.moving_window_sec, self.config.moving_speed)
                    if moving is not None:          # 이력이 모자라면(막 다시 본 직후) 이전 판단 유지
                        self.target_moving = moving
                        if moving:
                            self.target_heading = heading

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
            self.lost_mode = None
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

        # 운용자를 못 보는 중. 매 tick lost_plan으로 할 일을 다시 정한다 (돌아보다 시야에 들어오면 search/watch로 넘어감)
        if self.lost_since is None:
            self.lost_since = now
            self.lost_mode = None
        if self.target_map is not None and pose is not None:
            mode, goal, yaw = follow.lost_plan(
                pose, self.target_map, self.target_heading, self.target_moving, self.distance, self.config)
            if mode == 'look' and self.lost_mode in ('search', 'watch'):
                # 한 번 내다보기/마지막 자리 보기로 넘어갔으면 되돌아가지 않는다. 내다보기 경로가 꺾여 정면이 잠깐 벗어나도
                # look으로 되돌리면 둘 사이를 1~2 s마다 오가며 제자리에 머문다(3단계 fw12)
                return self._lost_timeout_check(now)
            changed = mode != self.lost_mode
            if changed or (mode != 'hold' and follow.goal_changed(self.last_goal, goal, self.config.goal_min_move)):
                self.goal_pub.publish(self._pose(goal, yaw))
                self.last_goal = goal
            if changed:
                self.lost_mode = mode
                self.get_logger().info(
                    f'놓침 대응 {mode}: 거리 {self.distance:.2f} m, 운용자 {"걷는 중" if self.target_moving else "멈춤"}, '
                    f'목표 ({goal[0]:.2f}, {goal[1]:.2f}) yaw {math.degrees(yaw):.0f}°')
        self._lost_timeout_check(now)

    def _lost_timeout_check(self, now):
        """놓친 시간이 상한을 넘으면 끝내고(경보), 아니면 HOLDING 유지 + 주기 경고."""
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
            self.get_logger().warn(f'운용자 놓침 {lost:.1f} s: {self.lost_mode}')

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
        msg.enrolled = bool(self.target is not None and self.target.enrolled)
        msg.visible = self._target_visible()
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
