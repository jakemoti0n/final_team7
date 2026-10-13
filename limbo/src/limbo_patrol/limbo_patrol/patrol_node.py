import math
import threading

import rclpy
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time

import time

from geometry_msgs.msg import PoseStamped
from limbo_interfaces.msg import PatrolState
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformListener

from nav2_simple_commander.robot_navigator import (
    BasicNavigator,
    TaskResult
)

import os
import yaml

from ament_index_python.packages import (
    get_package_share_directory
)

# 월드마다 waypoint 파일을 따로 두고 실행할 때 'waypoints' 파라미터로 고른다 (README "순찰", lab 1438bb3)
DEFAULT_WAYPOINTS = 'test_waypoints.yaml'   # human_test_world


def load_waypoints(file_name):

    package_share_dir = get_package_share_directory(
        'limbo_patrol'
    )

    waypoint_file = os.path.join(
        package_share_dir,
        'config',
        file_name
    )

    with open(
        waypoint_file,
        'r',
        encoding='utf-8'
    ) as file:

        data = yaml.safe_load(file)

    return data['waypoints']

def yaw_to_quaternion(yaw):
    """
    Z축 회전(yaw)을 quaternion으로 변환.

    평면 주행 로봇이므로
    roll = 0
    pitch = 0
    yaw만 사용한다.
    """

    qz = math.sin(yaw / 2.0)
    qw = math.cos(yaw / 2.0)

    return qz, qw


def create_waypoint(
    navigator,
    x,
    y,
    yaw
):
    """
    map 좌표계 기준 waypoint 생성
    """

    pose = PoseStamped()

    # ---------------------------------
    # 이 waypoint가 어느 좌표계 기준인지
    # ---------------------------------
    pose.header.frame_id = 'map'

    # 현재 ROS 시간 기록
    pose.header.stamp = (
        navigator.get_clock()
        .now()
        .to_msg()
    )

    # ---------------------------------
    # 위치
    # ---------------------------------
    pose.pose.position.x = x
    pose.pose.position.y = y
    pose.pose.position.z = 0.0

    # ---------------------------------
    # 방향
    # ---------------------------------
    qz, qw = yaw_to_quaternion(yaw)

    pose.pose.orientation.x = 0.0
    pose.pose.orientation.y = 0.0
    pose.pose.orientation.z = qz
    pose.pose.orientation.w = qw

    return pose


def wait_for_localization(navigator, timeout_sec=30.0):
    """AMCL pose와 TF를 기다리되 초기 위치를 다시 발행하지 않는다."""
    tf_buffer = Buffer()
    tf_listener = TransformListener(tf_buffer, navigator)
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if (navigator.initial_pose_received and
                tf_buffer.can_transform('map', 'base_footprint', Time())):
            return
        rclpy.spin_once(navigator, timeout_sec=0.2)
    raise TimeoutError(
        'Localization not ready. Check /amcl_pose and map -> base_footprint TF.'
    )


class PatrolControl(Node):
    """관제 화면의 일시정지·재개 요청을 받고 순찰 상태를 알린다.

    BasicNavigator는 자기 안에서 spin하므로 같은 노드에 서비스를 붙이면 콜백이 막힌다.
    그래서 별도 노드로 두고 백그라운드 스레드에서 spin한다.
    주행 루프와는 잠금으로 보호한 상태와 요청 플래그로만 주고받는다.
    서비스는 상태만 보고 바로 응답하고, Nav2 취소는 주행 루프가 한다.
    """

    def __init__(self, waypoint_names):
        super().__init__('patrol_control')
        self.lock = threading.Lock()
        self.names = waypoint_names
        self.state = PatrolState.WAITING_LOCALIZATION
        self.index = 0
        self.resumable = False
        self.pause_requested = False
        self.resume_requested = threading.Event()

        # 늦게 붙은 구독자(Bridge 재시작 등)도 마지막 상태를 바로 받는다
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.publisher = self.create_publisher(PatrolState, '/patrol/state', qos)
        self.create_service(Trigger, '/patrol/pause', self.on_pause)
        self.create_service(Trigger, '/patrol/resume', self.on_resume)
        self.publish('starting')

    def set(self, state, reason, index=None, resumable=None):
        with self.lock:
            changed = (state != self.state or
                       (index is not None and index != self.index))
            self.state = state
            if index is not None:
                self.index = index
            if resumable is not None:
                self.resumable = resumable
        if changed:
            self.publish(reason)

    def publish(self, reason):
        with self.lock:
            msg = PatrolState(
                stamp=self.get_clock().now().to_msg(), state=self.state,
                waypoint_index=self.index, waypoint_count=len(self.names),
                waypoint_name=self.names[self.index] if self.index < len(self.names) else '',
                has_resumable_task=self.resumable, reason=reason)
        self.publisher.publish(msg)
        print(f'[patrol state] {msg.state} next={msg.waypoint_name or "-"} ({reason})')

    def on_pause(self, request, response):
        with self.lock:
            state = self.state
            if state == PatrolState.PATROLLING:
                self.pause_requested = True
                self.state = PatrolState.PAUSING
        if state == PatrolState.PATROLLING:
            self.publish('pause requested')
            response.success, response.message = True, 'pause accepted'
        elif state in (PatrolState.PAUSING, PatrolState.PAUSED):
            response.success, response.message = False, 'already paused'
        else:
            response.success, response.message = False, 'not patrolling'
        return response

    def on_resume(self, request, response):
        with self.lock:
            state, resuming = self.state, self.resume_requested.is_set()
            accept = state == PatrolState.PAUSED and not resuming
            if accept:
                self.resume_requested.set()
        if accept:
            response.success, response.message = True, 'resume accepted'
        elif state == PatrolState.PAUSED:
            response.success, response.message = False, 'resume already requested'
        elif state == PatrolState.PATROLLING:
            response.success, response.message = False, 'already patrolling'
        elif state == PatrolState.PAUSING:
            response.success, response.message = False, 'still pausing'
        else:
            response.success, response.message = False, 'nothing to resume'
        return response

    def start_navigating(self, index):
        """새 구간 주행을 보낸 직후 호출한다.

        그 사이에 정지 요청이 들어와 이미 pausing이면 patrolling으로 되돌리지 않는다.
        (관제 화면이 정지 요청 뒤에 잠깐 '순찰 중'을 보지 않게)
        """
        with self.lock:
            if self.pause_requested:
                self.index = index
                return
        self.set(PatrolState.PATROLLING, 'navigating', index=index, resumable=True)

    def take_pause_request(self):
        with self.lock:
            requested, self.pause_requested = self.pause_requested, False
        return requested


def wait_while_paused(control, index):
    """정지 상태로 바꾸고 재개 요청이 올 때까지 기다린다."""
    control.resume_requested.clear()
    control.set(PatrolState.PAUSED, 'paused by request', index=index, resumable=True)
    while not control.resume_requested.wait(timeout=0.2):
        if not rclpy.ok():
            return False
    return True


def spin_control(executor):
    """서비스용 노드를 돌린다. Ctrl+C로 ROS가 먼저 꺼지면 조용히 끝낸다."""
    try:
        executor.spin()
    except Exception:
        if rclpy.ok():
            raise



def patrol(navigator, control, waypoint_configs):
    """위치 추정·Nav2 준비를 기다린 뒤 waypoint를 끝까지 돈다."""

    print('Waiting for AMCL pose and TF...')
    try:
        wait_for_localization(navigator)
    except TimeoutError as exc:
        # 상태가 waiting_localization에 멈춰 있으면 관제 화면이 이유를 알 수 없다
        print(exc)
        control.set(PatrolState.FAILED, 'localization not ready (30 s)', resumable=False)
        print('Patrol mission failed')
        time.sleep(0.5)  # 마지막 상태가 구독자에게 전달될 시간
        return False

    print('Waiting for Nav2...')
    # AMCL의 set_initial_pose가 이미 초기 위치를 지정한다.
    # BasicNavigator가 기본 초기 위치를 /initialpose로 다시 보내지 않게 한다.
    navigator.waitUntilNav2Active(localizer='robot_localization')

    print('Nav2 is active')

    print('Starting waypoint mission')

    # =========================================
    # pass waypoint를 모아 stop waypoint에서 끊은 구간들
    # 구간 = 그 구간에 속한 waypoint 번호 목록 (마지막이 stop)
    # =========================================

    segments = []
    route_segment = []

    for index, waypoint_config in enumerate(waypoint_configs):
        route_segment.append(index)
        if waypoint_config['type'] == 'stop':
            segments.append(route_segment)
            route_segment = []

    mission_succeeded = True
    failure_reason = ''

    for segment in segments:

        # 이번 구간에서 아직 지나지 않은 waypoint 번호
        remaining = list(segment)
        stop_config = waypoint_configs[segment[-1]]

        while remaining:

            # =========================================
            # Nav2에게 남은 waypoint들을 지나 stop까지 이동 명령
            # =========================================

            print(f"Moving to waypoint {stop_config['name']}")

            route = [
                create_waypoint(
                    navigator,
                    x=waypoint_configs[i]['x'],
                    y=waypoint_configs[i]['y'],
                    yaw=math.radians(waypoint_configs[i]['yaw'])
                )
                for i in remaining
            ]

            accepted = navigator.goThroughPoses(route)

            if not accepted:
                print(f"Navigation goal rejected: {stop_config['name']}")
                failure_reason = 'Navigation goal rejected'
                mission_succeeded = False
                break

            control.start_navigating(remaining[0])

            # 주행 완료까지 기다린다. 정지 요청이 오면 주행을 취소한다.
            pausing = False
            poses_left = len(remaining)

            while not navigator.isTaskComplete():

                if not pausing and control.take_pause_request():
                    pausing = True
                    navigator.cancelTask()

                feedback = navigator.getFeedback()

                if feedback is not None and 0 < feedback.number_of_poses_remaining <= len(remaining):
                    poses_left = feedback.number_of_poses_remaining
                    if not pausing:
                        control.set(PatrolState.PATROLLING, 'navigating',
                                    index=remaining[-poses_left])

                time.sleep(0.1)

            result = navigator.getResult()

            # 완료 직전에 들어온 정지 요청도 놓치지 않는다
            if not pausing and control.take_pause_request():
                pausing = True

            if result == TaskResult.SUCCEEDED:

                print(f"Arrived at {stop_config['name']}")
                remaining = []

            elif result == TaskResult.CANCELED and pausing:

                # 이미 지난 waypoint로 되돌아가지 않게 남은 것만 기억한다
                remaining = remaining[-poses_left:]

            elif result == TaskResult.CANCELED:

                print('Navigation canceled')
                failure_reason = 'Navigation canceled'
                mission_succeeded = False
                break

            elif result == TaskResult.FAILED:

                print('Navigation failed')
                failure_reason = 'Navigation failed'
                mission_succeeded = False
                break

            else:
                print(f'Navigation {result}')
                failure_reason = f'Navigation {result}'
                mission_succeeded = False
                break

            if pausing:
                next_index = remaining[0] if remaining else segment[-1] + 1
                if not wait_while_paused(control, next_index):
                    mission_succeeded = False
                    failure_reason = 'shutdown while paused'
                    break
                # stop 지점에 도착한 뒤 정지했다면 대기 없이 다음 구간으로 간다
                if not remaining:
                    stop_config = dict(stop_config, wait_sec=0)

        if not mission_succeeded:
            break

        # -------------------------------------
        # 서비스 지점 대기 (정지 요청이 오면 남은 대기는 버린다)
        # -------------------------------------

        wait_sec = stop_config['wait_sec']

        if wait_sec > 0:

            print(f'Waiting for {wait_sec} seconds')

            deadline = time.monotonic() + wait_sec
            while time.monotonic() < deadline:
                if control.take_pause_request():
                    if not wait_while_paused(control, segment[-1] + 1):
                        mission_succeeded = False
                        failure_reason = 'shutdown while paused'
                    break
                time.sleep(0.1)

        if not mission_succeeded:
            break

    if mission_succeeded:
        control.set(PatrolState.COMPLETED, 'mission completed',
                    index=len(waypoint_configs), resumable=False)
        print('Patrol mission completed')
        print('Waypoint mission succeeded')
    else:
        control.set(PatrolState.FAILED, failure_reason, resumable=False)
        print('Patrol mission failed')

    # 마지막 상태가 구독자에게 전달될 시간을 준다
    time.sleep(0.5)


def main(args=None):

    rclpy.init(args=args)

    navigator = BasicNavigator()

    # 파일 이름이 틀렸으면 Nav2를 기다리기 전에 바로 알 수 있게 먼저 읽는다
    waypoints_name = navigator.declare_parameter('waypoints', DEFAULT_WAYPOINTS).value
    print(f'Waypoints: {waypoints_name}')
    waypoint_configs = load_waypoints(waypoints_name)

    if not waypoint_configs or waypoint_configs[-1]['type'] != 'stop':
        raise ValueError('마지막 waypoint는 stop이어야 합니다')

    control = PatrolControl([w['name'] for w in waypoint_configs])
    executor = SingleThreadedExecutor()
    executor.add_node(control)
    threading.Thread(target=spin_control, args=(executor,), daemon=True).start()


    ready = True
    try:
        ready = patrol(navigator, control, waypoint_configs) is not False
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        executor.shutdown()
        control.destroy_node()
        navigator.destroyNode()
        rclpy.try_shutdown()

    # 위치 추정 준비 실패는 전처럼 0이 아닌 종료 코드로 끝낸다 (스크립트가 알 수 있게)
    if not ready:
        raise SystemExit(1)




if __name__ == '__main__':
    main()