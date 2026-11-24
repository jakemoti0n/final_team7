"""
정책 입력 한 프레임을 원재료(스캔·자세·경유점·속도·사람)에서 조립한다. rclpy를 쓰지 않는다.

데이터셋(dataset.py, bag에서)과 정책 노드(policy_node.py, 실시간 토픽에서)가 이 파일의 함수를
그대로 import해 쓴다. 학습 때 본 입력과 실행 때 받는 입력이 한 글자라도 다르면(좌표계 하나,
나누는 상수 하나, 빈칸 채우는 법 하나) 신경망은 본 적 없는 입력을 받아 엉뚱한 명령을 내는데,
검증 손실에는 그게 드러나지 않아 실물에서야 알게 된다. 그래서 조립 단계는 여기 한 곳에만 둔다.

조립 설정(FrameSettings)도 데이터셋이 npz에, 학습이 모델 파일에 그대로 실어 나르고 정책 노드는
모델 파일의 값을 쓴다. 노드 yaml로 따로 두면 두 값이 어긋날 수 있어서다.
"""

from dataclasses import asdict, dataclass
import math

from limbo_imitation import features
import yaml

WAYPOINT_STOP_TYPE = 'stop'


@dataclass
class FrameSettings:
    """입력 한 프레임을 만들 때 나누는 상수들. 바꾸면 모델을 다시 학습한다."""

    scan_range_min: float = 0.1   # m. 이보다 가까운 점은 자기 몸·잡음
    scan_range_max: float = 6.0   # m. 실내 복도 폭·사람 회피에 필요한 거리
    goal_max_dist: float = 5.0    # m. 이보다 먼 목표는 "멀다" 하나로 본다
    people_max_dist: float = 5.0  # m. personal_space 0.5 m의 열 배, 카메라 인식 거리 안
    v_max: float = 0.5            # m/s. nav2_real.yaml vx_max·조이스틱 최고 속도와 같음
    w_max: float = 0.8            # rad/s. nav2_real.yaml wz_max·조이스틱 최고 각속도와 같음


def settings_from_dict(data):
    """dict(npz·모델 파일에 실린 값) → FrameSettings. 모르는 키는 오류로 알린다."""
    return FrameSettings(**data)


def settings_to_dict(settings):
    return asdict(settings)


def load_waypoints(path):
    """경유점 yaml(limbo_patrol 형식) → [(x, y, 정지 여부)]. patrol_node의 waypoint_index와 같은 순서."""
    with open(path, encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return [(float(w['x']), float(w['y']), w.get('type') == WAYPOINT_STOP_TYPE)
            for w in data['waypoints']]


def waypoint_goal(waypoints, index):
    """/patrol/state의 waypoint_index → (x, y, 정지 여부). 끝났거나(index == 개수) 범위 밖이면 None."""
    if index is None or not 0 <= index < len(waypoints):
        return None
    return waypoints[index]


def yaw_from_quaternion(x, y, z, w):
    """평면 로봇이라 z축 회전만 본다."""
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def compose_poses(a, b):
    """평면 자세 합성: a(부모→중간) 다음 b(중간→자식) = 부모→자식. 자세는 (x, y, yaw)."""
    ax, ay, ayaw = a
    bx, by, byaw = b
    cos_a, sin_a = math.cos(ayaw), math.sin(ayaw)
    yaw = math.atan2(math.sin(ayaw + byaw), math.cos(ayaw + byaw))
    return (ax + cos_a * bx - sin_a * by, ay + sin_a * bx + cos_a * by, yaw)


def people_in_base(people_odom, robot_pose_odom):
    """사람 [(x, y, vx, vy)](odom 좌표) → 로봇 기준 [(x, y, vx, vy)].

    속도는 로봇 몸 방향으로 돌리기만 하고 로봇 자신의 속도는 빼지 않는다. 로봇 속도는 입력의 속도 칸에
    따로 있어서 신경망이 둘을 함께 보고, 빼면 서 있는 사람도 로봇이 달릴 때마다 움직이는 것처럼 보인다.
    person_detector의 예측은 odom 좌표다(odom_frame 파라미터).
    """
    _, _, yaw = robot_pose_odom
    cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
    result = []
    for x, y, vx, vy in people_odom:
        bx, by = features.map_to_base((x, y), robot_pose_odom)
        result.append((bx, by, cos_yaw * vx + sin_yaw * vy, -sin_yaw * vx + cos_yaw * vy))
    return result


def input_problem(ages, goal, timeout):
    """입력이 모자란 이유(/policy/status reason) 또는 None.

    ages = {'odom', 'tf', 'people'}: 마지막으로 받은 지 몇 초(None = 한 번도 못 받음).
    사람 예측이 끊긴 것도 문제로 본다. 사람이 없는 것(빈 목록)과 카메라가 멈춰 모르는 것은 다르고,
    모르는 채로 사람 곁을 달리면 안 된다(설계 2-1).
    """
    reasons = (('tf', 'no_tf'), ('odom', 'no_odom'), ('people', 'no_people'))
    for key, reason in reasons:
        age = ages.get(key)
        if age is None or age > timeout:
            return reason
    if goal is None:
        return 'no_waypoint'
    return None


def assemble_frame(scan, robot_pose_map, robot_pose_odom, goal, velocity, people_odom,
                   settings):
    """원재료 → 한 프레임(features.FRAME_SIZE칸).

    scan = (ranges, angle_min, angle_increment), robot_pose_* = (x, y, yaw),
    goal = (x, y, 정지 여부) 지도 좌표, velocity = (v, w) odom 측정값,
    people_odom = [(x, y, vx, vy)] odom 좌표.
    """
    ranges, angle_min, angle_increment = scan
    scan_bins = features.bin_scan(ranges, angle_min, angle_increment,
                                  range_min=settings.scan_range_min,
                                  range_max=settings.scan_range_max)
    goal_base = features.map_to_base((goal[0], goal[1]), robot_pose_map)
    return features.frame_features(
        scan_bins,
        features.goal_features(goal_base, goal[2], max_dist=settings.goal_max_dist),
        features.velocity_features(velocity[0], velocity[1], settings.v_max, settings.w_max),
        features.people_features(people_in_base(people_odom, robot_pose_odom),
                                 max_dist=settings.people_max_dist))


def push_and_stack(history, frame):
    """프레임을 기록(리스트)에 넣고 최근 STACK_FRAMES개를 쌓은 정책 입력을 낸다.

    입력이 모자라 프레임을 못 만든 스캔은 넣지 않는다(양쪽이 이 규칙을 같이 따른다).
    """
    history.append(frame)
    del history[:-features.STACK_FRAMES]
    return features.stack_frames(history)
