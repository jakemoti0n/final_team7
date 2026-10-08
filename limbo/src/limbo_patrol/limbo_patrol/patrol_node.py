import math

import rclpy
from rclpy.time import Time

import time

from geometry_msgs.msg import PoseStamped
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

def load_waypoints():

    package_share_dir = get_package_share_directory(
        'limbo_patrol'
    )

    waypoint_file = os.path.join(
        package_share_dir,
        'config',
        'test_waypoints.yaml'
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


def main(args=None):

    rclpy.init(args=args)

    navigator = BasicNavigator()

    print('Waiting for AMCL pose and TF...')
    wait_for_localization(navigator)

    print('Waiting for Nav2...')
    # AMCL의 set_initial_pose가 이미 초기 위치를 지정한다.
    # BasicNavigator가 기본 초기 위치를 /initialpose로 다시 보내지 않게 한다.
    navigator.waitUntilNav2Active(localizer='robot_localization')

    print('Nav2 is active')

    waypoint_configs = load_waypoints()

    if not waypoint_configs or waypoint_configs[-1]['type'] != 'stop':
        raise ValueError('마지막 waypoint는 stop이어야 합니다')

    print('Starting waypoint mission')

    route_segment = []

    mission_succeeded = True

    for waypoint_config in waypoint_configs:

        name = waypoint_config['name']

        # =========================================
        # 현재 waypoint의 PoseStamped 생성
        # =========================================

        waypoint = create_waypoint(
            navigator,
            x=waypoint_config['x'],
            y=waypoint_config['y'],
            yaw=math.radians(waypoint_config['yaw'])
        )

        # 현재 waypoint를 경로에 추가
        route_segment.append(waypoint)

        # =========================================
        # Nav2에게 이 waypoint까지 이동 명령
        # =========================================

        if waypoint_config['type'] == 'pass' :
            continue

        if waypoint_config['type'] == 'stop' :

            print(
                f'Moving to waypoint {name}'
            )

            accepted =navigator.goThroughPoses(
                route_segment
            )

            if not accepted:
                print(f'Navigation goal rejected: {name}')
                mission_succeeded = False
                break

            # 주행 완료까지 기다린다.
            while not navigator.isTaskComplete():

                time.sleep(0.1)


            result = navigator.getResult()


            if result == TaskResult.SUCCEEDED:

                print(
                    f"Arrived at "
                    f"{waypoint_config['name']}"
                )


            elif result == TaskResult.CANCELED:

                print('Navigation canceled')
                mission_succeeded = False
                break


            elif result == TaskResult.FAILED:

                print('Navigation failed')
                mission_succeeded = False
                break

            else:
                print(f'Navigation {result}')
                mission_succeeded = False
                break

            # -------------------------------------
            # 서비스 지점 대기
            # -------------------------------------

            wait_sec = waypoint_config['wait_sec']

            if wait_sec > 0:

                print(
                    f'Waiting for {wait_sec} seconds'
                )

                time.sleep(
                    wait_sec
                )


            # 이번 구간은 끝났으므로 초기화
            route_segment = []

    if mission_succeeded:
        print('Patrol mission completed')
        print('Waypoint mission succeeded')
    else:
        print('Patrol mission failed')

    navigator.destroyNode()

    rclpy.shutdown()


if __name__ == '__main__':
    main()