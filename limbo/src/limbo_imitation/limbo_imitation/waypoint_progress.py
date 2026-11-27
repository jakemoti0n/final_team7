"""
순찰 노드 없이 기록한 바퀴(패드 버튼 수동 바퀴)에서 "지금 향하는 경유점 번호"를 나중에 계산한다. rclpy를 쓰지 않는다.

순찰 노드가 /patrol/state로 넘기는 번호와 같은 뜻이 되게 한다(학습 때와 주행 때 입력 정의가 같아야 해서):
- pass 경유점: 실물 BT RemovePassedGoals 반경 안에 들면 다음으로(Nav2가 지난 목표를 지우는 규칙)
- 구간 끝(stop) 경유점: 도착 허용 오차(xy_goal_tolerance) 안에 들면 다음으로
- 더해서, 경유점 모서리의 이등분선을 지나면 다음으로. 사람은 Nav2와 달리 코너를 질러 반경 밖으로 지나가기도 해서
  (11-26·27 36바퀴 중 2바퀴: W3를 0.72 m, MID를 0.34 m로 지남) 반경만 보면 그 경유점에 묶여 이후 목표가 틀어진다.
  Nav2로 달린 바퀴는 반경 안으로 지나가므로 같은 결과다.
번호가 경유점 수와 같으면 경로 끝(목표 없음).
"""

import math


def crossed_corner(position, previous, waypoint, following):
    """position이 waypoint 모서리의 이등분선을 넘었는지. 들어오는 방향 + 나가는 방향 단위벡터 쪽이 앞."""
    ax, ay = waypoint[0] - previous[0], waypoint[1] - previous[1]
    bx, by = following[0] - waypoint[0], following[1] - waypoint[1]
    la, lb = math.hypot(ax, ay), math.hypot(bx, by)
    if la == 0.0 or lb == 0.0:
        return False
    nx, ny = ax / la + bx / lb, ay / la + by / lb
    return (position[0] - waypoint[0]) * nx + (position[1] - waypoint[1]) * ny > 0.0


def progress(positions, route, pass_radius, stop_tolerance):
    """Map 위치 목록 → 위치마다 경유점 번호(위치가 None이면 None).

    route = [(x, y, 구간 끝 여부)] 경유점 파일 순서. 출발점은 마지막 경유점(HOME)으로 본다(순찰 한 바퀴).
    """
    index, result = 0, []
    for position in positions:
        if position is None:
            result.append(None)
            continue
        while index < len(route):
            x, y, segment_end = route[index]
            tolerance = stop_tolerance if segment_end else pass_radius
            if math.hypot(position[0] - x, position[1] - y) < tolerance:
                index += 1
                continue
            if index + 1 < len(route) and crossed_corner(position, route[index - 1], route[index],
                                                         route[index + 1]):
                index += 1
                continue
            break
        result.append(index)
    return result
