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
STUCK_TIMEOUT = 8.0

# 8초 동안 25cm 이상 이동했으면 정상 진행으로 판단
STUCK_DISTANCE = 0.25

# 한 구간에서 최대 재시도 횟수
MAX_RETRIES = 3


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


def navigate_with_stuck_recovery(
    navigator,
    route_segment,
    target_name
):
    """
    NavigateThroughPoses 실행.

    일정 시간 동안 로봇 위치가 거의 변하지 않으면:

    1. 현재 navigation 취소
    2. 남아 있는 waypoint 확인
    3. local costmap 초기화
    4. 남은 waypoint 재전송

    MAX_RETRIES를 넘으면 실패 처리.
    """

    current_route = list(route_segment)

    retry_count = 0

    # 처음 navigation 명령
    navigator.goThroughPoses(
        current_route
    )

    # stuck 판단 기준 위치 / 시간
    anchor_pose = None
    anchor_time = time.monotonic()

    while not navigator.isTaskComplete():

        feedback = navigator.getFeedback()

        if feedback is None:
            time.sleep(0.1)
            continue

        # =============================================
        # 현재 위치
        # =============================================

        current_pose = feedback.current_pose

        # 최초 위치 저장
        if anchor_pose is None:

            anchor_pose = current_pose
            anchor_time = time.monotonic()

            time.sleep(0.1)
            continue


        # =============================================
        # 기준 위치에서 얼마나 이동했는지 계산
        # =============================================

        moved_distance = distance_between(
            current_pose,
            anchor_pose
        )

        # 충분히 이동했다면
        # stuck 타이머 초기화
        if moved_distance >= STUCK_DISTANCE:

            anchor_pose = current_pose
            anchor_time = time.monotonic()

            # 정상적으로 진행 중이면
            # retry 횟수도 다시 초기화 가능
            retry_count = 0


        # =============================================
        # 거의 움직이지 않은 시간 계산
        # =============================================

        stuck_duration = (
            time.monotonic()
            - anchor_time
        )


        # =============================================
        # Stuck 감지
        # =============================================
        # ==================================================
        # Collision Monitor가 안전 개입 중이면
        # stuck으로 판단하지 않는다.
        # ==================================================

        if navigator.collision_action != CollisionMonitorState.DO_NOTHING:

            # 현재 위치부터 stuck 측정을 다시 시작
            anchor_pose = current_pose
            anchor_time = time.monotonic()

            time.sleep(0.1)
            continue

        COLLISION_CLEAR_GRACE = 3.0

        time_since_collision_clear = (
            time.monotonic()
            - navigator.last_collision_clear_time
        )

        if time_since_collision_clear < COLLISION_CLEAR_GRACE:

            anchor_pose = current_pose
            anchor_time = time.monotonic()

            time.sleep(0.1)
            continue

        if stuck_duration >= STUCK_TIMEOUT:

            retry_count += 1

            print(
                f'[STUCK] {STUCK_TIMEOUT:.1f}s 동안 '
                f'{STUCK_DISTANCE:.2f}m 이상 이동하지 못함'
            )

            print(
                f'[STUCK] recovery '
                f'{retry_count}/{MAX_RETRIES}'
            )


            # =========================================
            # 재시도 한도 초과
            # =========================================

            if retry_count > MAX_RETRIES:

                print(
                    '[STUCK] 최대 recovery 횟수 초과'
                )

                navigator.cancelTask()

                return False


            # =========================================
            # 아직 남아 있는 waypoint 개수 확인
            # =========================================

            try:

                remaining_count = (
                    feedback.number_of_poses_remaining
                )

            except AttributeError:

                remaining_count = len(
                    current_route
                )


            if (
                remaining_count > 0
                and remaining_count <= len(current_route)
            ):

                remaining_route = (
                    current_route[-remaining_count:]
                )

            else:

                # feedback 값이 이상한 경우
                # 최소한 최종 stop waypoint라도 재전송
                remaining_route = [
                    current_route[-1]
                ]


            print(
                f'[STUCK] 남은 waypoint '
                f'{len(remaining_route)}개 재전송'
            )


            # =========================================
            # 기존 navigation 취소
            # =========================================

            navigator.cancelTask()


            # cancel 완료 대기
            cancel_start = time.monotonic()

            while not navigator.isTaskComplete():

                if (
                    time.monotonic()
                    - cancel_start
                    > 2.0
                ):
                    break

                time.sleep(0.05)


            # =========================================
            # stale obstacle가 남아 있을 가능성이 있어
            # local costmap만 초기화
            # =========================================

            navigator.clearLocalCostmap()

            time.sleep(0.5)


            # =========================================
            # 남아 있는 route 다시 전송
            # =========================================

            current_route = remaining_route

            navigator.goThroughPoses(
                current_route
            )


            # stuck 검사 초기화
            anchor_pose = None
            anchor_time = time.monotonic()

            continue


        time.sleep(0.1)


    # =================================================
    # Navigation 종료
    # =================================================

    while True:

        navigator.goThroughPoses(current_route)

        anchor_pose = None
        anchor_time = time.monotonic()

        while not navigator.isTaskComplete():

            feedback = navigator.getFeedback()

            if feedback is None:
                time.sleep(0.1)
                continue

            current_pose = feedback.current_pose

            if anchor_pose is None:
                anchor_pose = current_pose
                anchor_time = time.monotonic()
                continue

            moved_distance = distance_between(
                current_pose,
                anchor_pose
            )

            if moved_distance >= STUCK_DISTANCE:

                anchor_pose = current_pose
                anchor_time = time.monotonic()

            stuck_duration = (
                time.monotonic()
                - anchor_time
            )

            if stuck_duration >= STUCK_TIMEOUT:

                print('[RECOVERY] Robot stuck')

                navigator.cancelTask()

                time.sleep(0.5)

                navigator.clearLocalCostmap()

                retry_count += 1

                break

            time.sleep(0.1)


        # ------------------------------------------
        # Action 결과 확인
        # ------------------------------------------

        result = navigator.getResult()


        if result == TaskResult.SUCCEEDED:

            print(
                f'Arrived at {target_name}'
            )

            return True


        # ==========================================
        # FAILED 역시 recovery 대상으로 처리
        # ==========================================

        if result == TaskResult.FAILED:

            retry_count += 1

            print(
                f'[RECOVERY] Navigation action failed '
                f'({retry_count}/{MAX_RETRIES})'
            )

            if retry_count > MAX_RETRIES:

                print(
                    '[RECOVERY] Maximum retries exceeded'
                )

                return False


            # 순간적인 TF / costmap 문제일 수 있으므로
            # 잠깐 기다린 뒤 재전송
            navigator.clearLocalCostmap()

            time.sleep(1.0)

            continue


        if result == TaskResult.CANCELED:

            # 우리가 stuck 때문에 cancel한 경우라면
            # 다시 시도
            if retry_count <= MAX_RETRIES:

                time.sleep(0.5)

                continue

            return False


def main(args=None):

    rclpy.init(args=args)

    navigator = BasicNavigator()

    navigator.collision_action = CollisionMonitorState.DO_NOTHING
    navigator.last_collision_clear_time = time.monotonic()


    def collision_state_callback(msg):

        previous_action = navigator.collision_action

        navigator.collision_action = msg.action_type

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