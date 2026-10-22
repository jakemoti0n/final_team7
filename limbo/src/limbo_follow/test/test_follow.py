"""따라가기 계산(follow.py) 단위 시험: 목표점 위치·방향, 가다 서다 히스테리시스."""

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
