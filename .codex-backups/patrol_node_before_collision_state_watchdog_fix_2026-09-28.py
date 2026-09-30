import math
import os
import time
import yaml

import rclpy
from nav2_msgs.msg import CollisionMonitorState

from geometry_msgs.msg import PoseStamped

from nav2_simple_commander.robot_navigator import (
    BasicNavigator,
    TaskResult
)

from ament_index_python.packages import (
    get_package_share_directory
)


# ============================================================
# Stuck recovery 설정
# ============================================================

# 이 시간 동안 아래 거리만큼도 움직이지 못하면 stuck으로 판단
STUCK_TIMEOUT = 5.0

# 8초 동안 25cm 이상 이동했으면 정상 진행으로 판단
STUCK_DISTANCE = 0.25

# 한 구간에서 최대 재시도 횟수
MAX_RETRIES = 3
COLLISION_STATE_TIMEOUT = 2.0
COLLISION_CLEAR_GRACE = 3.0


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

    qz = math.sin(yaw / 2.0)
    qw = math.cos(yaw / 2.0)

    return qz, qw


def create_waypoint(
    navigator,
    x,
    y,
    yaw
):

    pose = PoseStamped()

    pose.header.frame_id = 'map'

    pose.header.stamp = (
        navigator.get_clock()
        .now()
        .to_msg()
    )

    pose.pose.position.x = x
    pose.pose.position.y = y
    pose.pose.position.z = 0.0

    qz, qw = yaw_to_quaternion(yaw)

    pose.pose.orientation.x = 0.0
    pose.pose.orientation.y = 0.0
    pose.pose.orientation.z = qz
    pose.pose.orientation.w = qw

    return pose


def distance_between(pose1, pose2):
    """
    두 PoseStamped 사이의 XY 거리 계산
    """

    dx = (
        pose1.pose.position.x
        - pose2.pose.position.x
    )

    dy = (
        pose1.pose.position.y
        - pose2.pose.position.y
    )

    return math.hypot(dx, dy)


def navigate_with_stuck_recovery(navigator, route_segment, target_name):
    """한 구간의 goal을 실행하고 실패 시 한도 내에서 복구한다."""
    current_route = list(route_segment)
    retry_count = 0

    while True:
        if not navigator.goThroughPoses(current_route):
            print(f'[RECOVERY] {target_name} goal rejected')
            return False

        anchor_pose = None
        anchor_time = time.monotonic()
        recovered_from_stuck = False

        while not navigator.isTaskComplete():
            feedback = navigator.getFeedback()
            if feedback is None:
                time.sleep(0.1)
                continue

            current_pose = feedback.current_pose
            now = time.monotonic()
            if anchor_pose is None or distance_between(current_pose, anchor_pose) >= STUCK_DISTANCE:
                anchor_pose = current_pose
                anchor_time = now

            state_age = (
                now - navigator.last_collision_state_time
                if navigator.last_collision_state_time is not None else None
            )
            state_is_fresh = state_age is not None and state_age <= COLLISION_STATE_TIMEOUT
            collision_active = navigator.collision_action != CollisionMonitorState.DO_NOTHING
            recently_cleared = now - navigator.last_collision_clear_time < COLLISION_CLEAR_GRACE

            # 상태를 모르면 안전 정지를 stuck으로 오인해 goal을 취소하지 않는다.
            if not state_is_fresh or collision_active or recently_cleared:
                anchor_pose = current_pose
                anchor_time = now
                time.sleep(0.1)
                continue

            if now - anchor_time >= STUCK_TIMEOUT:
                if retry_count >= MAX_RETRIES:
                    print('[STUCK] Maximum retries exceeded')
                    navigator.cancelTask()
                    return False

                remaining_count = getattr(feedback, 'number_of_poses_remaining', len(current_route))
                if 0 < remaining_count <= len(current_route):
                    remaining_route = current_route[-remaining_count:]
                else:
                    remaining_route = list(current_route)

                navigator.cancelTask()
                cancel_start = time.monotonic()
                while not navigator.isTaskComplete() and time.monotonic() - cancel_start < 2.0:
                    time.sleep(0.05)
                if not navigator.isTaskComplete():
                    print('[STUCK] Goal cancellation timed out')
                    return False

                navigator.clearLocalCostmap()
                current_route = remaining_route
                retry_count += 1
                recovered_from_stuck = True
                print(f'[STUCK] Retrying remaining {len(current_route)} poses ({retry_count}/{MAX_RETRIES})')
                break

            time.sleep(0.1)

        if recovered_from_stuck:
            continue

        result = navigator.getResult()
        if result == TaskResult.SUCCEEDED:
            print(f'Arrived at {target_name}')
            return True
        if result != TaskResult.FAILED:
            print(f'[RECOVERY] Navigation ended with result {result}')
            return False
        if retry_count >= MAX_RETRIES:
            print('[RECOVERY] Maximum retries exceeded')
            return False

        retry_count += 1
        print(f'[RECOVERY] Navigation action failed ({retry_count}/{MAX_RETRIES})')
        navigator.clearLocalCostmap()
        time.sleep(1.0)


def main(args=None):

    rclpy.init(args=args)

    navigator = BasicNavigator()

    navigator.collision_action = None
    navigator.last_collision_state_time = None
    navigator.last_collision_clear_time = time.monotonic()


    def collision_state_callback(msg):

        previous_action = navigator.collision_action

        navigator.collision_action = msg.action_type
        navigator.last_collision_state_time = time.monotonic()

        # Collision Monitor가 정상 상태로 돌아온 순간
        if (
            previous_action != CollisionMonitorState.DO_NOTHING
            and msg.action_type == CollisionMonitorState.DO_NOTHING
        ):
            navigator.last_collision_clear_time = time.monotonic()


    navigator.create_subscription(
        CollisionMonitorState,
        '/collision_monitor_state',
        collision_state_callback,
        10
    )

    print('Waiting for Nav2...')

    navigator.waitUntilNav2Active()

    print('Nav2 is active')

    waypoint_configs = load_waypoints()

    print('Starting waypoint mission')

    route_segment = []


    for waypoint_config in waypoint_configs:

        name = waypoint_config['name']


        # =============================================
        # waypoint PoseStamped 생성
        # =============================================

        waypoint = create_waypoint(
            navigator,
            x=waypoint_config['x'],
            y=waypoint_config['y'],
            yaw=math.radians(
                waypoint_config['yaw']
            )
        )


        route_segment.append(
            waypoint
        )


        # =============================================
        # pass waypoint
        # =============================================

        if waypoint_config['type'] == 'pass':

            continue


        # =============================================
        # stop waypoint
        # =============================================

        if waypoint_config['type'] == 'stop':

            print(
                f'Moving to waypoint {name}'
            )


            navigation_success = (
                navigate_with_stuck_recovery(
                    navigator,
                    route_segment,
                    name
                )
            )


            if not navigation_success:

                print(
                    f'Failed to reach waypoint {name}'
                )

                break


            # =========================================
            # 서비스 지점 대기
            # =========================================

            wait_sec = (
                waypoint_config['wait_sec']
            )


            if wait_sec > 0:

                print(
                    f'Waiting for {wait_sec} seconds'
                )

                time.sleep(
                    wait_sec
                )


            # 현재 segment 완료
            route_segment = []


    print(
        'Patrol mission completed'
    )


    navigator.destroyNode()

    rclpy.shutdown()


if __name__ == '__main__':
    main()