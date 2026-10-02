import math
import json

import rclpy

import time

from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

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


def publish_status(publisher, state, target='', detail=''):
    message = String()
    message.data = json.dumps({
        'state': state,
        'target': target,
        'detail': detail,
    }, ensure_ascii=False)
    publisher.publish(message)


def nav2_failure_detail(navigator):
    action = navigator.result_future.result() if navigator.result_future else None
    result = action.result if action else None
    message = getattr(result, 'error_msg', '')
    code = getattr(result, 'error_code', None)
    if message:
        return f'Nav2 이동 실패 (코드 {code}): {message}'
    return f'Nav2 이동 실패 (코드 {code})' if code is not None else 'Nav2 이동이 실패했습니다'


def main(args=None):

    rclpy.init(args=args)

    navigator = BasicNavigator()

    status_qos = QoSProfile(depth=1)
    status_qos.reliability = ReliabilityPolicy.RELIABLE
    status_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
    status_pub = navigator.create_publisher(
        String, 'limbo/patrol_status', status_qos
    )

    try:
        print('Waiting for Nav2...')
        publish_status(status_pub, 'waiting', detail='Nav2 활성화 대기 중')

        navigator.waitUntilNav2Active()

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
                publish_status(status_pub, 'moving', name, '목표 지점으로 이동 중')

                accepted =navigator.goThroughPoses(
                    route_segment
                )

                if not accepted:
                    print(f'Navigation goal rejected: {name}')
                    publish_status(status_pub, 'error', name, 'Nav2가 이동 목표를 거부했습니다')
                    mission_succeeded = False
                    break

                # 주행 완료까지 기다린다. Nav2 복구 횟수는 상태 표시에만 사용한다.
                last_recoveries = 0
                while not navigator.isTaskComplete():
                    feedback = navigator.getFeedback()
                    if feedback and feedback.number_of_recoveries > last_recoveries:
                        last_recoveries = feedback.number_of_recoveries
                        publish_status(
                            status_pub, 'recovering', name,
                            f'Nav2 복구 시도 {last_recoveries}회; 이동 상태를 확인하세요'
                        )
                    time.sleep(0.1)


                result = navigator.getResult()


                if result == TaskResult.SUCCEEDED:

                    print(
                        f"Arrived at "
                        f"{waypoint_config['name']}"
                    )


                elif result == TaskResult.CANCELED:

                    print('Navigation canceled')
                    publish_status(status_pub, 'error', name, '이동이 취소되었습니다')
                    mission_succeeded = False
                    break


                elif result == TaskResult.FAILED:

                    print('Navigation failed')
                    publish_status(status_pub, 'error', name, nav2_failure_detail(navigator))
                    mission_succeeded = False
                    break

                else:
                    print(f'Navigation {result}')
                    publish_status(status_pub, 'error', name, f'예상하지 못한 이동 결과: {result}')
                    mission_succeeded = False
                    break

                # -------------------------------------
                # 서비스 지점 대기
                # -------------------------------------

                wait_sec = waypoint_config['wait_sec']

                if wait_sec > 0:
                    publish_status(status_pub, 'paused', name, f'{wait_sec}초 동안 대기 중')

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
            publish_status(status_pub, 'completed', detail='모든 지점을 순찰했습니다')
        else:
            print('Patrol mission failed')

    except Exception as error:
        publish_status(status_pub, 'error', detail=str(error))
        raise
    finally:
        navigator.destroyNode()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
