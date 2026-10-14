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
