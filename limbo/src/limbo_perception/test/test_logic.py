"""ROS 없이 돌아가는 추적·예측·의도 로직 단위 테스트."""

import math

from limbo_perception import geometry, intent, motion, tracking
import numpy as np


def _walk(manager, raw_id, start_x, vx, start_t, steps, dt=0.1):
    matched = None
    obs = None
    for i in range(steps):
        matched = set()
        obs = manager.observe(
            raw_id, start_x + vx * dt * i, 0.0, start_t + dt * i, matched)
    return obs


def test_track_becomes_stable_and_estimates_velocity():
    manager = tracking.TrackManager(tracking.TrackerConfig())
    obs = _walk(manager, raw_id=7, start_x=1.0, vx=1.0, start_t=0.0, steps=30)

    assert obs.stable
    assert abs(obs.vx - 1.0) < 0.1
    assert abs(obs.vy) < 0.1


def test_botsort_id_switch_keeps_person_id():
    manager = tracking.TrackManager(tracking.TrackerConfig())
    before = _walk(manager, raw_id=1, start_x=1.0, vx=0.5, start_t=0.0,
                   steps=10)
    # 같은 사람이 이어서 걷는데 BoT-SORT ID만 바뀜
    after = manager.observe(2, 1.0 + 0.5 * 1.0, 0.0, 1.0, set())

    assert after.person_id == before.person_id
    assert manager.raw_to_person_id == {2: before.person_id}


def test_person_who_stopped_and_was_missed_keeps_person_id():
    # 시나리오 월드에서 본 상황: 걷다가 멈춘 사람이 1.5초 검출이 끊긴 뒤 같은 자리에서 다시 잡힘
    manager = tracking.TrackManager(tracking.TrackerConfig())
    walked = _walk(manager, raw_id=1, start_x=0.0, vx=1.0, start_t=0.0,
                   steps=20)
    stop_x = 0.1 * 19
    _walk(manager, raw_id=1, start_x=stop_x, vx=0.0, start_t=2.0, steps=5)

    seen_again = manager.observe(1, stop_x, 0.0, 2.4 + 1.5, set())

    assert seen_again.person_id == walked.person_id


def test_walking_person_is_not_treated_as_stopped():
    manager = tracking.TrackManager(tracking.TrackerConfig())
    obs = _walk(manager, raw_id=1, start_x=0.0, vx=0.5, start_t=0.0,
                steps=30)

    assert abs(obs.vx - 0.5) < 0.1


def test_stopped_person_velocity_drops_to_zero_quickly():
    # 칼만 필터만으로는 멈춘 뒤 2초가 지나도 0.4 m/s가 남았다 (시나리오 월드)
    config = tracking.TrackerConfig()
    manager = tracking.TrackManager(config)
    _walk(manager, raw_id=1, start_x=0.0, vx=1.0, start_t=0.0, steps=20)
    stop_x = 0.1 * 19
    steps = int((config.stop_window + 0.2) / 0.1)
    obs = _walk(manager, raw_id=1, start_x=stop_x, vx=0.0, start_t=2.0,
                steps=steps)

    assert abs(obs.vx) < 0.05
    assert abs(obs.x - stop_x) < 0.1


def test_person_who_walks_again_gets_velocity_back():
    manager = tracking.TrackManager(tracking.TrackerConfig())
    _walk(manager, raw_id=1, start_x=0.0, vx=0.0, start_t=0.0, steps=20)
    obs = _walk(manager, raw_id=1, start_x=0.0, vx=1.0, start_t=2.0,
                steps=15)

    assert obs.vx > 0.7


def test_far_detection_gets_new_person_id():
    manager = tracking.TrackManager(tracking.TrackerConfig())
    first = _walk(manager, raw_id=1, start_x=1.0, vx=0.0, start_t=0.0,
                  steps=5)
    other = manager.observe(2, 3.0, 2.0, 0.5, set())

    assert other.person_id != first.person_id


def test_cleanup_removes_timed_out_tracks_and_mappings():
    config = tracking.TrackerConfig()
    manager = tracking.TrackManager(config)
    _walk(manager, raw_id=1, start_x=1.0, vx=0.0, start_t=0.0, steps=3)

    manager.cleanup(0.2 + config.track_timeout + 0.01)

    assert manager.tracks == {}
    assert manager.raw_to_person_id == {}
    assert manager.person_to_raw_id == {}


def test_predict_trajectory_covers_horizon():
    config = motion.PredictionConfig(horizon=2.0, dt=0.25)
    points = motion.predict_trajectory(0.0, 0.0, 1.0, 0.0, config)

    assert len(points) == 8
    assert points[-1] == (2.0, 0.0, 2.0)


def test_classify_motion_toward_robot():
    config = motion.MotionConfig()
    state, speed = motion.classify_person_motion(
        2.0, 0.0, -0.5, 0.0, 0.0, 0.0, config)

    assert state == 'APPROACHING'
    assert speed > 0.0


def test_intent_confirms_after_hold_time():
    config = intent.IntentConfig()
    track = tracking.Track(kalman=None, last_time=0.0, last_seen=0.0)

    first = intent.update_approach_intent(
        track, 'APPROACHING', 1.0, 0.0, 0.0, config)
    later = intent.update_approach_intent(
        track, 'APPROACHING', 1.0, 0.0, config.approach_hold_time, config)

    assert first == (False, 0.0)
    assert later[0] is True
    assert track.intent_confirmed


def test_person_depth_ignores_invalid_values():
    depth = np.full((100, 100), 2.0, dtype=np.float32)
    depth[40:60, 40:60] = np.nan
    config = geometry.DepthConfig()

    assert geometry.person_depth(depth, 20, 20, 80, 80, config) == 2.0
    assert geometry.person_depth(None, 0, 0, 10, 10, config) is None


def test_person_depth_legs_only_box_measures_the_legs():
    # 다리만 보이는 박스: 가운데 영역의 절반 이상이 다리 사이로 보이는 뒤쪽 벽(4m)
    depth = np.full((100, 100), 4.0, dtype=np.float32)
    depth[:, 30:42] = 1.5   # 왼쪽 다리
    depth[:, 58:70] = 1.5   # 오른쪽 다리
    config = geometry.DepthConfig()

    assert abs(geometry.person_depth(depth, 20, 0, 80, 100, config) - 1.5) < 0.01


def test_person_depth_full_body_is_unchanged():
    depth = np.full((100, 100), 4.0, dtype=np.float32)
    depth[10:95, 25:75] = np.linspace(1.9, 2.1, 50, dtype=np.float32)  # 몸통 (조금 둥근 면)
    config = geometry.DepthConfig()

    assert abs(geometry.person_depth(depth, 25, 10, 75, 95, config) - 2.0) < 0.05


LEG = 1


def _merge_boxes(boxes, classes):
    return geometry.merge_leg_boxes(
        boxes, classes, leg_class=LEG, leg_inside_ratio=0.7, leg_iou=0.5)


def _merge(boxes, classes):
    return [i for i, _ in _merge_boxes(boxes, classes)]


def test_merge_drops_leg_box_inside_person_box():
    # 하반신 모델이 한 사람에 person(전신)과 leg(하반신)를 같이 냄 → person 하나만
    person = (100, 50, 200, 400)
    leg = (105, 250, 195, 400)
    assert _merge([leg, person], [LEG, 0]) == [1]


def test_merge_keeps_leg_box_without_person():
    # 가까워서 다리만 보임 → leg를 사람으로 씀. 같은 다리에 겹친 leg 박스는 큰 것만
    big = (100, 200, 220, 470)
    small = (110, 210, 215, 460)
    assert _merge([small, big], [LEG, LEG]) == [1]


def test_merge_keeps_two_separate_people():
    # 떨어진 두 사람: 한 사람은 person, 다른 사람은 leg만 → 둘 다 남음
    person = (50, 50, 150, 400)
    other_leg = (400, 250, 500, 470)
    assert _merge([person, other_leg], [0, LEG]) == [0, 1]


def test_merge_keeps_leg_only_partly_inside_person():
    # 앞사람 person 박스에 뒷사람 다리가 조금만 걸침 → 다른 사람이라 남김
    person = (100, 50, 200, 400)
    leg = (180, 250, 280, 400)  # 면적의 20%만 person 안
    assert _merge([person, leg], [0, LEG]) == [0, 1]


def test_person_depth_leg_box_ignores_gap_between_legs():
    # 두 다리를 감싼 leg 박스: 양옆 1/3은 다리(1.0 m), 가운데 1/3은 다리 사이로 보이는 벽(4.0 m)
    depth = np.full((100, 90), 4.0, dtype=np.float32)
    depth[:, 0:30] = 1.0
    depth[:, 60:90] = 1.0
    config = geometry.DepthConfig()

    leg = geometry.person_depth(depth, 0, 0, 90, 100, config, leg=True)
    assert abs(leg - 1.0) < 0.01
    # 종전 방식(가운데 40%)이면 벽 거리를 잰다
    assert geometry.person_depth(depth, 0, 0, 90, 100, config) > 3.0


def test_person_depth_single_leg_box_measures_the_leg():
    # 다리 하나만 감싼 박스: 다리가 가운데, 양 끝에 배경이 조금
    depth = np.full((100, 40), 4.0, dtype=np.float32)
    depth[:, 5:35] = 1.2
    config = geometry.DepthConfig()

    leg = geometry.person_depth(depth, 0, 0, 40, 100, config, leg=True)
    assert abs(leg - 1.2) < 0.01


def test_merge_joins_two_legs_side_by_side():
    # 가까운 사람의 두 다리가 따로 잡힘 → 둘을 감싼 박스 하나
    left = (100, 200, 140, 470)
    right = (165, 210, 200, 465)
    assert _merge_boxes([left, right], [LEG, LEG]) == [(0, (100, 200, 200, 470))]


def test_merge_keeps_legs_of_two_distant_people():
    # 멀리 떨어진 두 사람의 다리 하나씩 → 합치지 않음
    left = (100, 200, 140, 470)
    right = (400, 200, 440, 470)
    assert _merge_boxes([left, right], [LEG, LEG]) == [(0, left), (1, right)]


def test_push_to_body_center_moves_away_from_camera():
    # 정면 2 m 겉면 → 2.25 m. 높이(y)는 그대로
    x, y, z = geometry.push_to_body_center(0.0, 0.3, 2.0, 0.25)
    assert (abs(x) < 1e-9, y, abs(z - 2.25) < 1e-9) == (True, 0.3, True)
    # 비스듬한 점은 같은 방향으로 수평 거리만 0.25 m 늘어남
    x, y, z = geometry.push_to_body_center(0.6, 0.0, 0.8, 0.25)
    assert abs(np.hypot(x, z) - 1.25) < 1e-9
    assert abs(x / z - 0.75) < 1e-9


def test_body_center_radius_depends_on_box_kind():
    # leg 박스는 다리 앞면 → 몸 중심(0.25 m), person 박스는 몸 두께 절반(0.12 m)
    config = geometry.DepthConfig()
    _, _, z_leg = geometry.push_to_body_center(
        0.0, 0.0, 2.0, geometry.body_center_radius(config, leg=True))
    _, _, z_person = geometry.push_to_body_center(
        0.0, 0.0, 2.0, geometry.body_center_radius(config, leg=False))
    assert abs(z_leg - 2.25) < 1e-9
    assert abs(z_person - 2.12) < 1e-9


def test_clipped_at_edge_only_for_narrow_boxes_touching_edge():
    # 320 폭 화면 오른쪽 끝에 걸친 좁은 박스 → 제외, 넓으면(사람이 많이 보임) 사용, 가운데 좁은 박스도 사용
    assert geometry.clipped_at_edge((290, 50, 320, 240), 320, 2, 40)
    assert geometry.clipped_at_edge((0, 50, 25, 240), 320, 2, 40)
    assert not geometry.clipped_at_edge((200, 50, 320, 240), 320, 2, 40)
    assert not geometry.clipped_at_edge((150, 50, 175, 240), 320, 2, 40)


def test_depth_jump_is_ignored_until_it_repeats():
    # 0.7 m에 있던 사람이 한 프레임 3.2 m(뒤쪽 벽)로 튀면 0.7 m 유지, 3프레임 연속이면 3.2 m 채택
    f = geometry.DepthJumpFilter(jump_m=1.0, confirm_frames=3)
    assert f.update(7, 0.7, 0.0) == (0.7, False)
    assert f.update(7, 3.2, 0.1) == (0.7, True)
    assert f.update(7, 0.8, 0.2) == (0.8, False)
    assert f.update(7, 3.2, 0.3) == (0.8, True)
    assert f.update(7, 3.2, 0.4) == (0.8, True)
    assert f.update(7, 3.2, 0.5) == (3.2, False)


def test_depth_jump_filter_accepts_new_value_after_track_was_gone():
    f = geometry.DepthJumpFilter(jump_m=1.0, confirm_frames=3, max_age_s=1.0)
    f.update(7, 0.7, 0.0)
    assert f.update(7, 3.2, 2.0) == (3.2, False)


# 라이다 점 덩어리·지도 벽 걸러내기(R9 전처리용)와 다가옴 최근접점 (예전 tof_node에서 옮김)
SENSOR_X = 0.25


def test_closest_approach():
    t, d = geometry.closest_approach(3.0, 0.3, -1.0, 0.0)    # 앞에서 곧장 다가옴
    assert math.isclose(t, 3.0) and math.isclose(d, 0.3)
    t, d = geometry.closest_approach(3.0, 0.0, 1.0, 0.0)     # 멀어짐
    assert t < 0


def _arc(cx, cy, width, n=12):
    """라이다가 본 몸통 앞면: 중심 (cx, cy), 좌우 폭 width인 점 n개."""
    return [[cx, cy - width / 2 + width * i / (n - 1)] for i in range(n)]


def _wall(x0, x1, y, step=0.03):
    """y에 놓인 벽 (x0~x1)."""
    n = int((x1 - x0) / step) + 1
    return [[x0 + step * i, y] for i in range(n)]


BLOB = geometry.BlobConfig()


def _blob(points):
    return geometry.person_blob_ahead(points, SENSOR_X, BLOB)


def test_blob_ahead_finds_a_person_sized_cluster_in_the_path():
    found, cx, cy, width = geometry.person_blob_ahead(_arc(1.2, 0.1, 0.4), SENSOR_X, BLOB)
    assert found and math.isclose(cx, 1.2) and math.isclose(cy, 0.1) and math.isclose(width, 0.4)
    assert _blob(_arc(1.2, 0.0, 1.0))[0] is False    # 폭 1.0 m 상자
    assert _blob(_arc(1.2, 0.0, 0.05))[0] is False   # 기둥·잡음
    assert _blob(_arc(2.0, 0.0, 0.4))[0] is False    # 1.75 m 앞
    assert _blob(_arc(-0.5, 0.0, 0.4))[0] is False   # 뒤
    assert _blob(_arc(1.2, 0.8, 0.4))[0] is False    # 진로 밖
    assert _blob([[math.inf, 0.0], [math.nan, 0.0]])[0] is False
    assert _blob([])[0] is False


def test_wall_running_through_the_band_is_not_a_person():
    # 띠 안에 걸친 벽 모서리 조각도 띠 밖까지 이어진 전체 폭으로 재므로 사람이 아니다
    assert _blob(_wall(0.4, 3.0, -0.5))[0] is False


def _corridor_map(resolution=0.05):
    """폭 1.8 m 복도: y = -0.9, +0.9에 벽, x -1~4 m."""
    width, height = int(5.0 / resolution), int(2.4 / resolution)
    data = [0] * (width * height)
    for row in (int(0.3 / resolution), int(2.1 / resolution)):
        for col in range(width):
            data[row * width + col] = 100
    return geometry.MapGrid(data, width, height, resolution, -1.0, -1.2)


def test_map_filter_drops_wall_points_and_keeps_the_rest():
    grid = _corridor_map()
    wall = _wall(0.4, 2.0, -0.88)                       # 벽면 (지도 칸 안)
    person = _arc(1.2, 0.0, 0.4)
    points = wall + person + [[10.0, 10.0]]             # 지도 밖 점은 남김
    keep = geometry.filter_map_points(points, grid)
    assert not keep[:len(wall)].any()
    assert keep[len(wall):].all()
    near = geometry.filter_map_points([[1.0, -0.8], [1.0, -0.6]], grid)   # 벽에서 1칸 안 / 4칸 밖
    assert list(near) == [False, True]


def test_wall_points_alone_are_not_a_person_after_map_filter():
    grid = _corridor_map()
    points = _wall(0.4, 1.0, -0.88) + _wall(0.4, 1.0, 0.88)   # 벽 모서리 조각만
    kept = [p for p, k in zip(points, geometry.filter_map_points(points, grid)) if k]
    assert _blob(kept)[0] is False


def test_wall_and_person_leave_only_the_person():
    grid = _corridor_map()
    points = _wall(0.4, 0.75, -0.88) + _arc(1.0, -0.2, 0.45)
    kept = [p for p, k in zip(points, geometry.filter_map_points(points, grid)) if k]
    found, cx, cy, width = geometry.person_blob_ahead(kept, SENSOR_X, BLOB)
    assert found and math.isclose(cx, 1.0) and math.isclose(cy, -0.2) and math.isclose(width, 0.45)


def test_tracks_ahead_of_bumper_rotates_position_and_velocity_only():
    # 로봇 (1, 2)에서 북쪽(+y)을 봄. 사람은 북쪽 2 m에서 남쪽으로 1 m/s → 로봇 축으로 앞 2 m, 다가옴
    (x, y, vx, vy), = geometry.tracks_ahead_of_bumper(
        [(1.0, 4.0, 0.0, -1.0)], 1.0, 2.0, math.pi / 2, 0.25)
    assert math.isclose(x, 1.75) and abs(y) < 1e-9
    assert math.isclose(vx, -1.0) and abs(vy) < 1e-9
    # 서 있는 사람은 로봇이 다가가도 속도 0 그대로 (로봇 속도를 빼지 않음)
    (_, _, vx, vy), = geometry.tracks_ahead_of_bumper([(3.0, 0.0, 0.0, 0.0)], 0.0, 0.0, 0.0, 0.25)
    assert vx == 0.0 and vy == 0.0
