"""ToF 근접 판단 (R5)."""

import math

from limbo_perception import tof

SENSOR_X = 0.25
CONFIG = tof.TofConfig()


def test_nearest_point_ignores_floor_and_invalid_returns():
    points = [
        [0.40, 0.0, 0.01],               # 바닥 반사 (min_obstacle_height 아래)
        [math.inf, math.inf, math.inf],  # 맞은 것 없음
        [0.70, 0.1, 0.10],
        [0.50, -0.2, 0.20],
    ]
    point, distance = tof.nearest_point(points, SENSOR_X, CONFIG)
    assert list(point) == [0.50, -0.2, 0.20]
    assert math.isclose(distance, 0.25)


def test_nothing_seen_is_infinitely_far():
    point, distance = tof.nearest_point([[math.nan, 0, 0]], SENSOR_X, CONFIG)
    assert point is None and distance == math.inf


def test_debounce_changes_only_after_consecutive_frames():
    d = tof.Debounce(3)
    assert [d.update(x) for x in [True, True, False, True, True, True]] == \
        [False, False, False, False, False, True]
    assert [d.update(x) for x in [False, True, False, False, False]] == \
        [True, True, True, True, False]


def _approach(blocking, start_t, xs, dt=0.1):
    for i, x in enumerate(xs):
        blocking.on_person(start_t + dt * i, x, 0.1)
    return start_t + dt * (len(xs) - 1)


def test_person_seen_just_before_blocking_latches_until_tof_clears():
    b = tof.PersonBlocking(tof.BlockingConfig())
    t = _approach(b, 0.0, [2.5, 2.3, 2.1, 1.9, 1.7])   # 다가오다 카메라에서 사라짐
    assert b.on_tof(t + 3.0, False) is False
    assert b.on_tof(t + 4.0, True) is True              # 4 s 뒤 코앞이 막힘
    assert b.on_tof(t + 30.0, True) is True             # 막혀 있는 동안 기억과 무관하게 유지
    assert b.on_tof(t + 30.5, False) is True            # 잠깐 빈 것은 무시
    assert b.on_tof(t + 31.1, False) is False           # 1 s 넘게 비면 풂


def test_blocked_without_a_person_is_a_box():
    b = tof.PersonBlocking(tof.BlockingConfig())
    assert b.on_tof(0.0, True) is False
    t = _approach(b, 10.0, [2.5, 2.3, 2.1])             # 막힌 뒤에 사람이 보여도 이미 막힌 것은 상자
    assert b.on_tof(t, True) is False


def test_person_seen_too_long_ago_or_walking_away_does_not_latch():
    b = tof.PersonBlocking(tof.BlockingConfig())
    t = _approach(b, 0.0, [1.7, 1.9, 2.1])              # 멀어지는 사람
    assert b.on_tof(t + 1.0, True) is False
    b = tof.PersonBlocking(tof.BlockingConfig())
    t = _approach(b, 0.0, [2.5, 2.3, 2.1])
    assert b.on_tof(t + 6.0, True) is False             # 5 s보다 오래 전


def test_latch_gives_up_after_max_hold():
    b = tof.PersonBlocking(tof.BlockingConfig())
    t = _approach(b, 0.0, [2.5, 2.3])
    assert b.on_tof(t + 1.0, True) is True
    assert b.on_tof(t + 62.0, True) is False


def test_closest_approach():
    t, d = tof.closest_approach(3.0, 0.3, -1.0, 0.0)    # 앞에서 곧장 다가옴
    assert math.isclose(t, 3.0) and math.isclose(d, 0.3)
    t, d = tof.closest_approach(3.0, 0.0, 1.0, 0.0)     # 멀어짐
    assert t < 0


def test_oncoming_person_stops_robot_until_they_pass():
    w = tof.ApproachWatch(tof.ApproachConfig())
    w.on_people(0.0, [(2.5, 0.2, -1.0, 0.0)])
    assert w.on_tick(0.05, False) is True                # 진로 위로 다가옴 → 정지
    assert w.on_tick(0.9, False) is True                 # 검출 끊겨도 잠깐은 유지
    assert w.on_tick(2.1, False) is False                # 다가옴·ToF 모두 1 s 넘게 없음 → 재개


def test_guest_standing_in_front_keeps_the_stop_through_tof():
    w = tof.ApproachWatch(tof.ApproachConfig())
    w.on_people(0.0, [(2.0, 0.0, -0.8, 0.0)])
    assert w.on_tick(0.1, False) is True
    for i in range(1, 300):                              # 손님이 와서 30 s 서 있음 (카메라는 못 봄, ToF 막힘)
        assert w.on_tick(0.1 + 0.1 * i, True) is True
    assert w.on_tick(30.5, False) is True                # 떠난 직후
    assert w.on_tick(31.2, False) is False               # 1 s 넘게 비면 재개


def test_passers_by_and_standing_people_do_not_stop():
    w = tof.ApproachWatch(tof.ApproachConfig())
    w.on_people(0.0, [(2.0, 1.5, 0.0, -1.0)])            # 옆에서 가로질러 감: 최근접 2.0 m
    w.on_people(0.1, [(1.5, 0.0, 0.0, 0.05)])            # 앞에 서 있는 사람 (속도 없음)
    w.on_people(0.2, [(2.0, 0.0, 1.0, 0.0)])             # 앞에서 멀어짐
    w.on_people(0.3, [(4.0, 0.0, -1.0, 0.0)])            # 아직 멂
    assert w.on_tick(0.35, True) is False                # ToF만으로는 정지 안 함 (그건 /person_blocking)


def test_approach_stop_gives_up_after_max_hold():
    w = tof.ApproachWatch(tof.ApproachConfig())
    w.on_people(0.0, [(2.0, 0.0, -1.0, 0.0)])
    assert w.on_tick(0.0, True) is True
    assert w.on_tick(61.0, True) is False
