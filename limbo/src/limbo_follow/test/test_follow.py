"""따라가기 계산(follow.py) 단위 시험: 목표점 위치·방향, 가다 서다 히스테리시스, 놓쳤을 때 할 일."""

import math

from limbo_follow import follow

CFG = follow.FollowConfig(follow_distance=1.2, resume_distance=1.5)


def test_goal_is_follow_distance_short_of_person_and_faces_them():
    goal, yaw, dist = follow.standoff_goal((0.0, 0.0), (3.0, 0.0), 1.2)
    assert abs(goal[0] - 1.8) < 1e-6 and abs(goal[1]) < 1e-6
    assert abs(yaw) < 1e-6 and abs(dist - 3.0) < 1e-6
    goal, yaw, _ = follow.standoff_goal((1.0, 1.0), (1.0, 4.0), 1.2)
    assert abs(goal[0] - 1.0) < 1e-6 and abs(goal[1] - 2.8) < 1e-6
    assert abs(yaw - math.pi / 2) < 1e-6


def test_goal_stays_at_robot_when_person_is_already_close():
    # 운용자가 1.2 m 안에 있으면 목표점은 로봇 자리 (뒤로 물러나지 않음, 2-3 후진 없음)
    goal, yaw, dist = follow.standoff_goal((2.0, 0.0), (2.8, 0.0), 1.2)
    assert goal == (2.0, 0.0) and abs(dist - 0.8) < 1e-6 and abs(yaw) < 1e-6
    goal, _, _ = follow.standoff_goal((2.0, 0.0), (2.0, 0.0), 1.2)
    assert goal == (2.0, 0.0)


def test_move_stop_hysteresis():
    # 가는 중: 1.2 m 안에 들어와야 선다
    assert follow.should_move(1.4, True, CFG)
    assert not follow.should_move(1.1, True, CFG)
    # 선 채: resume_distance(여기선 1.5) 밖으로 나가야 다시 간다
    assert not follow.should_move(1.4, False, CFG)
    assert follow.should_move(1.6, False, CFG)
    # 기본값은 두 거리가 같아(1.5) 그 밖이면 바로 간다
    assert follow.should_move(1.55, False, follow.FollowConfig())
    assert not follow.should_move(1.45, False, follow.FollowConfig())


def test_goal_changed_threshold():
    assert follow.goal_changed(None, (0.0, 0.0), 0.15)
    assert not follow.goal_changed((0.0, 0.0), (0.1, 0.0), 0.15)
    assert follow.goal_changed((0.0, 0.0), (0.2, 0.0), 0.15)


def test_search_goal_extends_along_heading():
    gx, gy = follow.search_goal((4.5, 10.0), math.pi, 1.5)
    assert abs(gx - 3.0) < 1e-6 and abs(gy - 10.0) < 1e-6
    assert follow.search_goal((4.5, 10.0), None, 1.5) == (4.5, 10.0)


def test_lost_near_holds_pose():
    # 가까이서 놓침: 자세 그대로 (돌리면 MPPI가 호를 그려 운용자에게 파고듦)
    mode, goal, yaw = follow.lost_plan((0.0, 0.0, 0.3), (1.2, 0.5), 0.0, True, 1.3, follow.FollowConfig())
    assert mode == 'hold' and goal == (0.0, 0.0) and yaw == 0.3


def test_lost_out_of_view_turns_to_last_position_first():
    # 경로가 꺾여 로봇이 75° 돌았다(fw10): 마지막 자리가 정면에서 벗어나 있으면 먼저 그쪽으로 돌아본다. 걷고 있었어도 내다보기는 뒤
    mode, goal, yaw = follow.lost_plan((0.0, 0.0, math.radians(75)), (3.0, 0.0), 0.0, True, 3.0, follow.FollowConfig())
    assert mode == 'look' and goal == (0.0, 0.0) and abs(yaw) < 1e-6


def test_lost_in_view_and_walking_searches_ahead():
    # 모퉁이 너머로 사라짐(fw8): 마지막 자리가 시야 안이고 걷고 있었으면 가던 방향으로 1.5 m 더 간 점
    mode, goal, yaw = follow.lost_plan((0.0, 0.0, 0.0), (3.0, 0.5), math.pi / 2, True, 3.0, follow.FollowConfig())
    assert mode == 'search' and abs(yaw - math.pi / 2) < 1e-6
    assert abs(goal[0] - 3.0) < 1e-6 and abs(goal[1] - 2.0) < 1e-6


def test_lost_in_view_but_operator_was_standing_watches_last_position():
    # 운용자가 멈춘 뒤 검출이 끊김(fw9): 옛 진행 방향으로 내다보지 않고 마지막 자리를 보며 선다
    mode, goal, yaw = follow.lost_plan((0.0, 0.0, 0.0), (1.7, 0.1), 0.0, False, 1.62, follow.FollowConfig())
    assert mode == 'watch' and goal == (0.0, 0.0) and abs(yaw - math.atan2(0.1, 1.7)) < 1e-6
    # 방향을 모르면(한 번도 걷는 걸 못 봄) 걷는 중이라도 내다볼 수 없어 마지막 자리를 본다
    mode, _, _ = follow.lost_plan((0.0, 0.0, 0.0), (3.0, 0.0), None, True, 3.0, follow.FollowConfig())
    assert mode == 'watch'


def test_wrap_angle():
    assert abs(follow.wrap_angle(math.radians(190)) - math.radians(-170)) < 1e-9
    assert abs(follow.wrap_angle(-math.pi) + math.pi) < 1e-9 or abs(follow.wrap_angle(-math.pi) - math.pi) < 1e-9
