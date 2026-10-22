"""
따라가기 계산 (ROS 의존 없음). 운용자 위치로부터 로봇이 갈 목표점과 "갈지 설지"를 정한다 (PROJECT.md 2-9).

- 목표점은 운용자 자리가 아니라 **운용자에서 로봇 쪽으로 follow_distance 떨어진 점**이다. 운용자 자리는 HumanLayer 치명(0.25 m)
  + 팽창(0.45 m) 안이라 목표로 쓰면 경로 계획이 실패한다. 목표의 방향은 운용자를 바라보는 쪽.
- 가까우면 선다: 가는 중에 follow_distance 안으로 들어오면 서고, 선 채로 resume_distance 밖으로 멀어지면 다시 간다.
  두 값을 같게 두면(기본) 목표점이 운용자를 따라 조금씩 앞으로 가고 컨트롤러가 알아서 느려져 가다 서다가 없다.
  벌려 두면(1.2/1.5) 그 사이에서 완전히 서서 운용자 속도에 평균이 묶였다(2단계 4·5회차 홀 0.25 m/s).
- 서 있을 때의 목표점은 로봇 자신의 자리다 (운용자 쪽으로 더 가지 않음). 후진은 쓰지 않으므로(2-3) 운용자가 다가와도 물러나지 않는다.
"""

from dataclasses import dataclass
import math


@dataclass
class FollowConfig:
    follow_distance: float = 1.5   # m, 운용자와 유지할 거리 (목표점은 운용자에서 이만큼 앞). 1.2 m 안은 카메라가 하반신을 못 본다
    resume_distance: float = 1.5   # m, 선 채로 이보다 멀어지면 다시 간다 (follow_distance 이상. 크게 두면 가다 서다로 뒤처진다)
    target_stale_sec: float = 1.0  # s, 운용자 판정이 이보다 오래되면 "못 보는 중"
    lost_stop_sec: float = 15.0    # s, 놓친 채 이 시간이 지나면 따라가기를 끝낸다 (경보). 그 전엔 마지막 자리로 가서 본다
    goal_min_move: float = 0.15    # m, 목표점이 이보다 덜 움직였으면 다시 보내지 않는다 (재계획 떨림 방지)
    search_ahead: float = 1.5      # m, 멀리서 놓치면 마지막 자리에서 가던 방향으로 이만큼 더 간 점을 목표로 (모퉁이 너머를 내다봄)


def search_goal(last_xy, heading, ahead):
    """놓친 운용자가 마지막에 있던 자리에서 가던 방향으로 ahead만큼 더 간 점. 방향을 모르면 그 자리."""
    if heading is None:
        return last_xy
    return (last_xy[0] + math.cos(heading) * ahead, last_xy[1] + math.sin(heading) * ahead)


def standoff_goal(robot_xy, person_xy, follow_distance):
    """운용자에서 로봇 쪽으로 follow_distance 떨어진 점과, 운용자를 바라보는 yaw. 둘이 겹치면 로봇 자리."""
    dx = person_xy[0] - robot_xy[0]
    dy = person_xy[1] - robot_xy[1]
    dist = math.hypot(dx, dy)
    if dist < 1e-3:
        return (robot_xy[0], robot_xy[1]), 0.0, dist
    yaw = math.atan2(dy, dx)
    if dist <= follow_distance:
        return (robot_xy[0], robot_xy[1]), yaw, dist
    scale = (dist - follow_distance) / dist
    return (robot_xy[0] + dx * scale, robot_xy[1] + dy * scale), yaw, dist


def should_move(distance, moving, config):
    """히스테리시스: 가는 중이면 follow_distance 안에서 서고, 선 채면 resume_distance 밖에서 다시 간다."""
    if moving:
        return distance > config.follow_distance
    return distance > config.resume_distance


def goal_changed(prev_goal, goal, min_move):
    if prev_goal is None:
        return True
    return math.hypot(goal[0] - prev_goal[0], goal[1] - prev_goal[1]) >= min_move
