import math

import rclpy

import time

from geometry_msgs.msg import PoseStamped

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
        'waypoints.yaml'
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


def main(args=None):

    rclpy.init(args=args)

    navigator = BasicNavigator()

    print('Waiting for Nav2...')

    navigator.waitUntilNav2Active()

    print('Nav2 is active')

    waypoint_configs = load_waypoints()

    print('Starting waypoint mission')

    route_segment = []

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

            navigator.goThroughPoses(
                route_segment
            )


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
                break


            elif result == TaskResult.FAILED:

                print('Navigation failed')
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


    print('Patrol mission completed')


    result = navigator.getResult()


    if result == TaskResult.SUCCEEDED:

        print('Waypoint mission succeeded')

    elif result == TaskResult.CANCELED:

        print('Waypoint mission canceled')

    elif result == TaskResult.FAILED:

        print('Waypoint mission failed')

    else:

        print('Unknown result')


    navigator.destroyNode()

    rclpy.shutdown()


if __name__ == '__main__':
    main()