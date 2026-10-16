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


def _arc(cx, cy, width, n=12):
    """라이다가 본 몸통 앞면: 중심 (cx, cy), 좌우 폭 width인 점 n개."""
    return [[cx, cy - width / 2 + width * i / (n - 1)] for i in range(n)]


def _wall(x0, x1, y, step=0.03):
    """y에 놓인 벽 (x0~x1)."""
    n = int((x1 - x0) / step) + 1
    return [[x0 + step * i, y] for i in range(n)]


BLOB = tof.BlobConfig()


def test_blob_ahead_finds_a_person_sized_cluster_in_the_path():
    found, cx, cy, width = tof.person_blob_ahead(_arc(1.2, 0.1, 0.4), SENSOR_X, BLOB)
    assert found and math.isclose(cx, 1.2) and math.isclose(cy, 0.1) and math.isclose(width, 0.4)
    assert tof.person_blob_ahead(_arc(1.2, 0.0, 1.0), SENSOR_X, BLOB)[0] is False    # 폭 1.0 m 상자
    assert tof.person_blob_ahead(_arc(1.2, 0.0, 0.05), SENSOR_X, BLOB)[0] is False   # 기둥·잡음
    assert tof.person_blob_ahead(_arc(2.0, 0.0, 0.4), SENSOR_X, BLOB)[0] is False    # 1.75 m 앞
    assert tof.person_blob_ahead(_arc(-0.5, 0.0, 0.4), SENSOR_X, BLOB)[0] is False   # 뒤
    assert tof.person_blob_ahead(_arc(1.2, 0.8, 0.4), SENSOR_X, BLOB)[0] is False    # 진로 밖
    assert tof.person_blob_ahead([[math.inf, 0.0], [math.nan, 0.0]], SENSOR_X, BLOB)[0] is False
    assert tof.person_blob_ahead([], SENSOR_X, BLOB)[0] is False


def test_wall_running_through_the_band_is_not_a_person():
    # 띠 안에 걸친 벽 모서리 조각도 띠 밖까지 이어진 전체 폭으로 재므로 사람이 아니다
    assert tof.person_blob_ahead(_wall(0.4, 3.0, -0.5), SENSOR_X, BLOB)[0] is False


def _corridor_map(resolution=0.05):
    """폭 1.8 m 복도: y = -0.9, +0.9에 벽, x -1~4 m."""
    width, height = int(5.0 / resolution), int(2.4 / resolution)
    data = [0] * (width * height)
    for row in (int(0.3 / resolution), int(2.1 / resolution)):
        for col in range(width):
            data[row * width + col] = 100
    return tof.MapGrid(data, width, height, resolution, -1.0, -1.2)


def test_map_filter_drops_wall_points_and_keeps_the_rest():
    grid = _corridor_map()
    wall = _wall(0.4, 2.0, -0.88)                       # 벽면 (지도 칸 안)
    person = _arc(1.2, 0.0, 0.4)
    points = wall + person + [[10.0, 10.0]]             # 지도 밖 점은 남김
    keep = tof.filter_map_points(points, grid)
    assert not keep[:len(wall)].any()
    assert keep[len(wall):].all()
    near = tof.filter_map_points([[1.0, -0.8], [1.0, -0.6]], grid)   # 벽에서 1칸 안 / 4칸 밖
    assert list(near) == [False, True]


def test_wall_points_alone_are_not_a_person_after_map_filter():
    grid = _corridor_map()
    points = _wall(0.4, 1.0, -0.88) + _wall(0.4, 1.0, 0.88)   # 벽 모서리 조각만
    kept = [p for p, k in zip(points, tof.filter_map_points(points, grid)) if k]
    assert tof.person_blob_ahead(kept, SENSOR_X, BLOB)[0] is False


def test_wall_and_person_leave_only_the_person():
    grid = _corridor_map()
    points = _wall(0.4, 0.75, -0.88) + _arc(1.0, -0.2, 0.45)
    kept = [p for p, k in zip(points, tof.filter_map_points(points, grid)) if k]
    found, cx, cy, width = tof.person_blob_ahead(kept, SENSOR_X, BLOB)
    assert found and math.isclose(cx, 1.0) and math.isclose(cy, -0.2) and math.isclose(width, 0.45)


def test_blob_alone_latches_blocking_but_gives_up_after_5_s():
    b = tof.PersonBlocking(tof.BlockingConfig())
    assert b.on_tof(0.0, True, (3.0, 0.0)) is True       # 옆에서 와서 선 사람 (다가옴 이력 없음)
    assert b.reason == 'blob'
    assert b.on_tof(4.9, True, (3.0, 0.0)) is True
    assert b.on_tof(5.1, True, (3.0, 0.0)) is False       # 확인 못 한 물체 앞 5 s 예의 뒤 풂
    assert b.release_reason.startswith('blob hold limit')
    assert b.on_tof(10.0, True, (3.0, 0.0)) is False      # ToF가 비기 전엔 다시 안 잡음 (상자 앞 무한 대기 방지)
    assert b.on_tof(10.1, False) is False
    assert b.on_tof(11.2, False) is False                  # 1 s 넘게 비었음
    assert b.on_tof(11.3, True, (3.0, 0.0)) is True       # 새 막힘은 다시 잡음


def test_blob_seen_by_camera_holds_up_to_60_s():
    b = tof.PersonBlocking(tof.BlockingConfig())
    b.on_camera_people(-2.0, [(3.4, 0.3)])                 # 2 s 전 카메라가 그 자리에서 본 사람 (서 있음)
    assert b.on_tof(0.0, True, (3.0, 0.0)) is True
    assert b.reason == 'camera'
    assert b.on_tof(30.0, True, (3.0, 0.0)) is True
    assert b.on_tof(59.0, True, None) is True             # 덩어리가 잠깐 안 보여도 ToF가 막혀 있으면 유지
    assert b.on_tof(61.0, True, (3.0, 0.0)) is False


def test_blob_far_from_camera_person_stays_blob_only():
    b = tof.PersonBlocking(tof.BlockingConfig())
    b.on_camera_people(-1.0, [(5.0, 2.0)])                 # 다른 곳에 있는 사람
    assert b.on_tof(0.0, True, (3.0, 0.0)) is True
    assert b.reason == 'blob'
    assert b.on_tof(5.1, True, (3.0, 0.0)) is False


def test_blob_without_tof_does_not_block():
    b = tof.PersonBlocking(tof.BlockingConfig())
    assert b.on_tof(0.0, False, (3.0, 0.0)) is False      # 코앞이 비어 있으면 /person_blocking 아님


def test_guest_outside_tof_range_keeps_the_stop_through_the_blob():
    w = tof.ApproachWatch(tof.ApproachConfig())
    w.on_people(0.0, [(2.0, 0.0, -0.8, 0.0)])
    assert w.on_tick(0.1, False) is True
    for i in range(1, 100):                              # 1 m 앞에 10 s 서 있음: ToF 밖, 라이다 덩어리만 참
        assert w.on_tick(0.1 + 0.1 * i, False, True) is True
    assert w.basis == 'blob'
    assert w.on_tick(11.5, False, False) is False        # 떠나고 1 s 넘게 비면 재개
    assert w.release_reason == 'clear'


def test_approach_held_by_blob_alone_releases_after_15_s():
    w = tof.ApproachWatch(tof.ApproachConfig())
    w.on_people(0.0, [(2.0, 0.0, -0.8, 0.0)])
    assert w.on_tick(0.1, False) is True
    t = 0.1
    while t < 20.0:                                      # 다가옴은 1 s 뒤 끊기고 덩어리만 남음
        t += 0.1
        if not w.on_tick(t, False, True):
            break
    assert 16.0 < t < 16.4                               # 덩어리만 근거가 된 1.1 s부터 15 s
    assert w.release_reason.startswith('blob-only hold limit')


def test_approach_held_by_tof_keeps_60_s_even_with_blob():
    w = tof.ApproachWatch(tof.ApproachConfig())
    w.on_people(0.0, [(2.0, 0.0, -0.8, 0.0)])
    assert w.on_tick(0.1, False) is True
    for i in range(1, 500):                              # 손님이 코앞(ToF)에 50 s
        assert w.on_tick(0.1 + 0.1 * i, True, True) is True
    assert w.basis == 'tof'


def test_front_blob_alone_never_starts_a_stop():
    w = tof.ApproachWatch(tof.ApproachConfig())
    assert w.on_tick(0.0, True, True) is False           # 상자·벽 앞: 다가온 사람이 없으면 정지 안 함
