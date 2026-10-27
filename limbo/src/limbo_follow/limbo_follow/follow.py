"""
따라가기 계산 (ROS 의존 없음). 운용자 위치로부터 로봇이 갈 목표점과 "갈지 설지"를 정한다 (PROJECT.md 2-9).

- 목표점은 운용자 자리가 아니라 **운용자에서 로봇 쪽으로 follow_distance 떨어진 점**이다. 운용자 자리는 HumanLayer 치명(0.25 m)
  + 팽창(0.45 m) 안이라 목표로 쓰면 경로 계획이 실패한다. 목표의 방향은 운용자를 바라보는 쪽.
- 가까우면 선다: 가는 중에 follow_distance 안으로 들어오면 서고, 선 채로 resume_distance 밖으로 멀어지면 다시 간다.
  두 값을 같게 두면(기본) 목표점이 운용자를 따라 조금씩 앞으로 가고 컨트롤러가 알아서 느려져 가다 서다가 없다.
  벌려 두면(1.2/1.5) 그 사이에서 완전히 서서 운용자 속도에 평균이 묶였다(2단계 4·5회차 홀 0.25 m/s).
- 서 있을 때의 목표점은 로봇 자신의 자리다 (운용자 쪽으로 더 가지 않음). 후진은 쓰지 않으므로(2-3) 운용자가 다가와도 물러나지 않는다.
- 놓쳤을 때(lost_plan): 가까이서 놓치면 자세 그대로, 마지막 자리가 정면에서 벗어나 있으면 먼저 그쪽으로 돌아보고, 운용자가 걷고
  있었으면 가던 방향으로 search_ahead만큼 내다보고, 멈춰 있었으면 그 자리를 보며 선다 (3단계 fw9·fw10의 구멍 둘을 막는 규칙).
- "걷고 있었나"는 추적기가 주는 한 프레임의 속도가 아니라 **최근 moving_window_sec 동안 본 위치의 이동량**(motion_from_history)으로
  정한다. 운용자가 벽 모서리 뒤로 들어가며 박스가 잘리면 보이는 부분의 위치가 0.6 s쯤 멈춘 것처럼 보여 추적기가 속도 0을 냈고, 걷던
  운용자를 "멈춤"으로 오판해 watch로 서 있다가 끝났다(fw18·fw20). 1 s 창이면 그 정체 구간을 넘어 그 전의 이동이 남는다.
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
    moving_speed: float = 0.1      # m/s, 운용자 속도가 이보다 크면 "걷는 중". 가던 방향도 이때만 기억한다. 멈춰 있던 운용자는 내다보지 않는다
    look_angle_deg: float = 25.0   # °, 놓쳤을 때 마지막 자리가 로봇 정면에서 이 각도 밖이면 먼저 그쪽으로 돌아본다 (카메라 반각 34° 안쪽)
    moving_window_sec: float = 1.0  # s, "걷는 중" 판단에 쓰는 위치 이력 창. 추적기 멈춤 창(0.6 s)보다 길어야 가려짐 정체를 넘어 본다.
                                    # 길수록 멈춘 운용자를 늦게 알아채 (멈춘 뒤 이 시간 안에 끊기면 아직 걷는 중으로 봄 → 내다보기)


def wrap_angle(angle):
    """각도를 -pi~pi로."""
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def lost_plan(robot_pose, last_xy, heading, target_moving, distance, config):
    """운용자를 놓쳤을 때 할 일. (mode, goal_xy, yaw)를 돌려준다.

    - hold:   가까이(distance ≤ resume_distance)서 놓침. 운용자가 카메라 아래쪽으로 벗어난 것이라 그 자리로 가면 파고들고,
              제자리 회전도 MPPI가 호를 그려 0.6 m 움직인다(2단계 6회차) → 자세 그대로 선다
    - look:   마지막 자리가 정면에서 look_angle_deg 밖. 경로가 꺾여 운용자가 좁은 시야(±34°) 밖으로 나간 것(3단계 fw10)
              → 제자리에서 그쪽으로 돌아본다. 돌아서 시야에 들어오면 다음 tick에 search/watch로 넘어간다
    - search: 운용자가 걷고 있었다(모퉁이 너머) → 마지막 자리에서 가던 방향으로 search_ahead만큼 더 간 점을 목표로(2단계 fw8)
    - watch:  운용자가 멈춰 있었다 → 내다보기를 쓰지 않고 마지막 자리를 보며 선다. 멈춘 운용자에게 옛 진행 방향으로
              내다보기를 쓰면 운용자를 지나쳐 달린다(3단계 fw9)
    """
    rx, ry, ryaw = robot_pose
    if distance <= config.resume_distance:
        return 'hold', (rx, ry), ryaw
    bearing = math.atan2(last_xy[1] - ry, last_xy[0] - rx)
    if abs(wrap_angle(bearing - ryaw)) > math.radians(config.look_angle_deg):
        return 'look', (rx, ry), bearing
    if target_moving and heading is not None:
        return 'search', search_goal(last_xy, heading, config.search_ahead), heading
    return 'watch', (rx, ry), bearing


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


def motion_from_history(history, window_sec, moving_speed):
    """최근 window_sec 동안 본 운용자 위치 이력으로 (걷는 중인가, 가던 방향, 이력 길이)를 정한다.

    history: [(t, x, y), ...] 시간순. 창 안의 가장 오래된 점과 마지막 점 사이의 평균 속도가 moving_speed보다 크면 걷는 중.
    이력이 창의 절반도 못 채우면(막 다시 본 직후) 판단을 보류하고 (None, None, span)을 돌려준다 — 그때는 이전 판단을 유지한다.
    한 프레임 속도(추적기)는 가려지며 잘린 박스에 속아 0이 되지만, 1 s 이동량은 그 전의 걸음이 남아 속지 않는다(fw18·fw20)."""
    if not history:
        return None, None, 0.0
    t1, x1, y1 = history[-1]
    t0, x0, y0 = next(h for h in history if h[0] >= t1 - window_sec)
    span = t1 - t0
    if span < window_sec / 2.0:
        return None, None, span
    dx, dy = x1 - x0, y1 - y0
    moving = math.hypot(dx, dy) / span > moving_speed
    return moving, (math.atan2(dy, dx) if moving else None), span
