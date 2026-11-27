"""11-27 데이터 규칙: 발판·스캔 장착·정후방 가림·경유점 사후 계산·정지 경유점 뜻·제외 목록."""

import math

from limbo_imitation import dataset, features, frame_builder, metrics, robot_geometry
from limbo_imitation import waypoint_progress
import numpy as np
import pytest

FOOTPRINT = '[[0.25, 0.295], [0.25, -0.295], [-0.25, -0.295], [-0.25, 0.295]]'
MID360 = (0.0, 0.0, math.pi / 2)   # 실물 base_footprint → mid360_link


def test_footprint_inside_and_edge_distance():
    poly = robot_geometry.parse_footprint(FOOTPRINT)
    x = np.array([0.10, 0.27, 0.0, 0.30])
    y = np.array([0.0, 0.0, 0.32, 0.35])
    inside = robot_geometry.inside_polygon(x, y, poly)
    np.testing.assert_array_equal(inside, [True, False, False, False])
    np.testing.assert_allclose(robot_geometry.edge_distance(x[1:], y[1:], poly),
                               [0.02, 0.025, math.hypot(0.05, 0.055)])


def test_real_nav2_settings_give_footprint_and_patrol_radii():
    pytest.importorskip('ament_index_python')
    try:
        text = robot_geometry.footprint_text()
    except LookupError:
        pytest.skip('limbo_navigation not installed')
    assert robot_geometry.parse_footprint(text).shape == (4, 2)
    assert robot_geometry.patrol_radii() == (0.7, 0.25)


def test_bin_scan_uses_mount_yaw_so_bin_zero_is_robot_front():
    # 라이다 프레임 0° = base 왼쪽(+90°). 라이다 −90° 방향 점은 base 정면
    ranges = np.full(360, 5.0)
    angles = -math.pi + np.arange(360) * (2 * math.pi / 360)
    ranges[np.argmin(np.abs(angles + math.pi / 2))] = 1.2
    bins = features.bin_scan(ranges, -math.pi, 2 * math.pi / 360, mount=MID360)
    assert bins[0] == pytest.approx(1.2 / 6.0) and bins.argmin() == 0


def test_rear_mask_hides_eighteen_bins_around_straight_back():
    masked = features.rear_masked_bins(72, math.radians(45))
    assert len(masked) == 18 and masked[0] == 27 and masked[-1] == 44
    bins = features.bin_scan(np.full(72, 1.0), math.pi / 72, 2 * math.pi / 72,  # 광선을 구간 가운데에
                             rear_mask_half_width=math.radians(45))
    assert np.all(bins[masked] == 1.0) and np.all(np.delete(bins, masked) == pytest.approx(1 / 6))


def test_scan_mount_follows_static_chain_and_reports_missing():
    pairs = {('base_footprint', 'mid360_link'): (0.1, 0.0, math.pi / 2),
             ('mid360_link', 'lidar_optical'): (0.0, 0.0, math.pi / 2)}
    assert frame_builder.scan_mount(pairs, 'base_footprint', 'base_footprint') == (0.0, 0.0, 0.0)
    x, y, yaw = frame_builder.scan_mount(pairs, 'base_footprint', 'lidar_optical')
    assert (x, y) == pytest.approx((0.1, 0.0)) and abs(yaw) == pytest.approx(math.pi)
    assert frame_builder.scan_mount(pairs, 'base_footprint', 'camera') is None


def test_policy_stop_flag_only_for_waiting_stop_or_route_end(tmp_path):
    path = tmp_path / 'w.yaml'
    path.write_text('waypoints:\n'
                    '  - {name: W1, type: pass, x: 1, y: 0, yaw: 0, wait_sec: 0}\n'
                    '  - {name: MID, type: stop, x: 2, y: 0, yaw: 0, wait_sec: 0}\n'
                    '  - {name: D, type: stop, x: 3, y: 0, yaw: 0, wait_sec: 5}\n'
                    '  - {name: HOME, type: stop, x: 4, y: 0, yaw: 0, wait_sec: 0}\n')
    assert [w[2] for w in frame_builder.load_waypoints(str(path))] == [False, False, True, True]
    # 순찰 노드 규칙(구간 끝)은 파일의 type 그대로
    assert [w[2] for w in frame_builder.load_route(str(path))] == [False, True, True, True]


SQUARE = [(10.0, 0.0, False), (10.0, 10.0, False), (0.0, 10.0, True), (0.0, 0.0, True)]


def test_progress_by_radius_like_patrol_node():
    path = [(5.0, 0.0), (9.5, 0.2), (10.0, 5.0), (9.9, 9.7), (5.0, 10.0), (0.1, 10.0),
            (0.0, 5.0), (0.05, 0.1)]
    assert waypoint_progress.progress(path, SQUARE, 0.7, 0.25) == [0, 1, 1, 2, 2, 3, 3, 4]


def test_progress_corner_cut_outside_radius_still_advances():
    # 첫 코너(10, 0)를 1 m 안쪽으로 질러 감: 반경 0.7 밖이지만 이등분선을 넘으면 다음 경유점
    path = [(5.0, 0.0), (8.5, 0.5), (9.2, 1.5), (9.5, 3.0)]
    assert waypoint_progress.progress(path, SQUARE, 0.7, 0.25) == [0, 0, 1, 1]
    assert waypoint_progress.progress([None, (5.0, 0.0)], SQUARE, 0.7, 0.25) == [None, 0]


def test_exclusions_file_whole_lap_and_interval(tmp_path):
    path = tmp_path / dataset.EXCLUSIONS_FILE
    path.write_text('- {lap: a_manual, whole_lap: true, reason: broken test record}\n'
                    '- {lap: b_manual, start_s: 1.0, end_s: 2.0, reason: unexplained stop}\n')
    assert dataset.load_exclusions(str(path)) == {
        'a_manual': 'whole', 'b_manual': [(1.0, 2.0, 'unexplained stop')]}
    assert dataset.load_exclusions(str(tmp_path / 'none.yaml')) == {}
    path.write_text('- {lap: c, start_s: 1, end_s: 2}\n')
    with pytest.raises(ValueError):
        dataset.load_exclusions(str(path))


def manual_lap_without_patrol():
    """버튼 수동 바퀴: /patrol/state 없음, 라이다 프레임 mid360_link(+90°)."""
    s = dataset.BagStreams(start_time=0.0, end_time=4.0)
    s.tf_static[('map', 'odom')] = (0.0, 0.0, 0.0)
    s.tf_static[('base_footprint', 'mid360_link')] = MID360
    s.tf[('odom', 'base_footprint')] = dataset.Series()
    for i in range(80):
        t = i * 0.05
        s.tf[('odom', 'base_footprint')].add(t, (0.4 * t, 0.0, 0.0))
        s.odom.add(t, (0.4 * t, 0.0, 0.4, 0.0))
        s.teleop.add(t, (0.4, 0.0))
    for i in range(40):
        t = i * 0.1 + 0.01
        s.scans.add(t, (np.full(36, 3.0), -math.pi, 2 * math.pi / 36, 0.1, 10.0, 'mid360_link'))
        s.predictions.add(t, [])
    s.drive_modes.add(0.0, ('teleop', 'manual', 'deadman held'))
    return s


def test_manual_lap_gets_derived_waypoints_and_exclusion_interval():
    cfg = {**dataset.DEFAULTS, 'pass_radius': 0.7, 'stop_tolerance': 0.25}
    ms = {**metrics.DEFAULT_SETTINGS, 'footprint': FOOTPRINT}
    route = [(1.0, 0.0, False), (5.0, 0.0, True)]
    waypoints = [(1.0, 0.0, False), (5.0, 0.0, True)]
    s = manual_lap_without_patrol()
    xs, ys, _, stamps, dropped, _ = dataset.lap_samples(s, waypoints, cfg, ms, route,
                                                        excluded=[(2.0, 3.0)])
    # 0.3 m(1.0 − 0.7)를 지나면 W1 다음으로. 목표가 생겨 표본이 남고, 제외 구간 10스캔만 빠진다
    assert s.derived_waypoint.values[0] == 0 and s.derived_waypoint.values[-1] == 1
    assert dropped == {'excluded_by_list': 10} and len(xs) == 30
    assert not any(2.0 <= t <= 3.0 for t in stamps)


def test_missing_scan_mount_drops_frames():
    cfg = {**dataset.DEFAULTS, 'pass_radius': 0.7, 'stop_tolerance': 0.25}
    ms = {**metrics.DEFAULT_SETTINGS, 'footprint': FOOTPRINT}
    s = manual_lap_without_patrol()
    del s.tf_static[('base_footprint', 'mid360_link')]
    xs, _, _, _, dropped, _ = dataset.lap_samples(s, [(5.0, 0.0, True)], cfg, ms,
                                                  [(5.0, 0.0, True)])
    assert xs == [] and dropped == {'no_scan_tf': 40}
