"""데이터셋 조립 테스트. 실제 bag 대신 손으로 만든 메시지 시퀀스(BagStreams)를 쓴다."""

import json
import math

from limbo_imitation import arbiter_logic, dataset, features, metrics, run_files
import numpy as np
import pytest

SCAN_DT = 0.1
CMD_DT = 0.05


def make_streams(seconds=3.0, modes=(('teleop', 'manual'),), mode_times=(0.0,), teleop_v=0.4):
    """직진하는 로봇. map→odom 정적, 사람 예측 빈 목록, teleop 20 Hz, 스캔 10 Hz."""
    s = dataset.BagStreams(start_time=0.0, end_time=seconds)
    s.tf_static[('map', 'odom')] = (0.0, 0.0, 0.0)
    s.tf[('odom', 'base_footprint')] = dataset.Series()
    for i in range(int(round(seconds / CMD_DT))):
        t = i * CMD_DT
        s.tf[('odom', 'base_footprint')].add(t, (0.4 * t, 0.0, 0.0))
        s.odom.add(t, (0.4 * t, 0.0, 0.4, 0.0))
        s.teleop.add(t, (teleop_v, 0.1))
        s.cmd.add(t, (teleop_v, 0.1))
        s.cmd_out.add(t, (teleop_v, 0.1))
    for i in range(int(round(seconds / SCAN_DT))):
        t = i * SCAN_DT + 0.01
        s.scans.add(t, (np.full(36, 3.0), 0.0, 2 * math.pi / 36, 0.1, 10.0))
        s.predictions.add(t, [])
    s.patrol.add(0.0, ('patrolling', 0))
    for t, mode in zip(mode_times, modes):
        s.drive_modes.add(t, mode)
    return s


WAYPOINTS = [(10.0, 0.0, False)]
CFG = dict(dataset.DEFAULTS)


def test_series_latest_includes_same_time():
    series = dataset.Series([(1.0, 'a'), (2.0, 'b')])
    assert series.latest(0.5) is None
    assert series.latest(2.0) == (2.0, 'b')
    assert series.latest(5.0) == (2.0, 'b')


def test_tf_composition_hand_calculated():
    s = dataset.BagStreams()
    s.tf[('map', 'odom')] = dataset.Series([(0.0, (2.0, 0.0, math.pi / 2))])
    s.tf[('odom', 'base_footprint')] = dataset.Series([(0.8, (1.0, 0.0, 0.0)),
                                                       (1.2, (9.0, 9.0, 0.0))])
    pose_map, pose_odom, age = dataset.robot_poses(s, 1.0, CFG)
    np.testing.assert_allclose(pose_map, (2.0, 1.0, math.pi / 2), atol=1e-12)
    assert pose_odom == (1.0, 0.0, 0.0)
    assert age == pytest.approx(1.0)  # 오래된 쪽(map→odom, 0.0 s)의 나이


def test_tf_missing_link_gives_none():
    s = dataset.BagStreams()
    s.tf[('odom', 'base_footprint')] = dataset.Series([(0.0, (1.0, 0.0, 0.0))])
    assert dataset.robot_poses(s, 1.0, CFG) is None


def test_label_from_teleop_within_window_only():
    s = make_streams()
    assert dataset.label_at(s, 1.01, 0.2) == ((0.4, 0.1), None)
    s.teleop = dataset.Series([(0.5, (0.3, 0.0))])
    assert dataset.label_at(s, 1.01, 0.2) == (None, 'no_command')


def test_label_source_decides_nav_and_policy_excluded():
    s = make_streams(modes=(('nav', 'policy'),))
    assert dataset.label_at(s, 1.0, 0.2) == (None, 'nav')
    s = make_streams(modes=(('policy', 'policy_assist'),))
    assert dataset.label_at(s, 1.0, 0.2) == (None, 'not_teleop')


RELEASED = ('none', 'manual', arbiter_logic.REASON_NO_DEADMAN)
PRESSED = ('teleop', 'manual', 'deadman held')


def test_manual_release_between_presses_is_a_stop_label():
    # 0~1 s 출발 전 대기(뗌) → 1~2 s 운전(누름) → 2~3 s 손님 앞 정지(뗌) → 3~4 s 운전 → 4~5 s 도착 뒤(뗌)
    s = make_streams(seconds=5.0, modes=(RELEASED, PRESSED, RELEASED, PRESSED, RELEASED),
                     mode_times=(0.0, 1.0, 2.0, 3.0, 4.0))
    xs, ys, weights, stamps, dropped, _ = dataset.lap_samples(s, WAYPOINTS, CFG,
                                                              metrics.DEFAULT_SETTINGS)
    stops = [t for t, y in zip(stamps, ys) if y == (0.0, 0.0)]
    assert len(stops) == 10 and all(2.0 < t < 3.0 for t in stops)
    assert all(y == (0.4, 0.1) for t, y in zip(stamps, ys) if 1.0 < t < 2.0 or 3.0 < t < 4.0)
    assert dropped == {'released_before_first_press': 10, 'released_after_last_press': 10}
    # 정지 정답에도 새 가중치를 두지 않는다(끼어들기 가중은 policy_assist에서만)
    assert set(weights) == {1.0}


def test_release_in_policy_modes_stays_excluded():
    # policy·policy_assist에서 데드맨 뗌은 "정책에 맡김"이다. 중재기 reason도 다르다
    for mode in ('policy', 'policy_assist'):
        s = make_streams(seconds=3.0, modes=(('teleop', mode, 'deadman held'),
                                             ('policy', mode, 'policy ok'),
                                             ('teleop', mode, 'deadman held')),
                         mode_times=(0.0, 1.0, 2.0))
        span = dataset.teleop_span(s.drive_modes)
        assert dataset.label_at(s, 1.5, 0.2, span) == (None, 'not_teleop')


def test_only_deadman_release_counts_as_a_stop():
    # 누르고 있는데 teleop 명령이 끊긴 것(고장)은 사람의 멈춤 결정이 아니다
    lost = ('none', 'manual', 'teleop command lost')
    s = make_streams(seconds=3.0, modes=(PRESSED, lost, PRESSED), mode_times=(0.0, 1.0, 2.0))
    span = dataset.teleop_span(s.drive_modes)
    assert dataset.label_at(s, 1.5, 0.2, span) == (None, 'not_teleop')


def test_label_clips_reverse_to_zero():
    s = make_streams(teleop_v=-0.2)
    assert dataset.label_at(s, 1.0, 0.2) == ((0.0, 0.1), None)


def test_lap_samples_keeps_teleop_drops_nav_and_weights_intervention():
    # 0~1 s policy(정책 자신의 명령: 뺌), 1~2 s 끼어들기(teleop, 가중 2), 2~3 s nav(뺌)
    s = make_streams(modes=(('policy', 'policy_assist'), ('teleop', 'policy_assist'),
                            ('nav', 'policy_assist')), mode_times=(0.0, 1.0, 2.0))
    xs, ys, weights, stamps, dropped, _ = dataset.lap_samples(s, WAYPOINTS, CFG,
                                                              metrics.DEFAULT_SETTINGS)
    assert all(1.0 < t < 2.0 for t in stamps)
    assert len(stamps) == 10
    assert set(weights) == {CFG['intervention_weight']}
    assert dropped == {'not_teleop': 10, 'nav': 10}
    assert xs[0].shape == (features.FEATURE_SIZE,)
    assert ys[0] == (0.4, 0.1)


def test_lap_samples_drops_bad_intervals():
    s = make_streams(seconds=20.0)
    s.monitor_states = dataset.Series([(10.0, metrics.COLLISION_MONITOR_STOP), (10.5, 0)])
    settings = {**metrics.DEFAULT_SETTINGS, 'collision_margin': 2.0}
    _, _, weights, stamps, dropped, n_bad = dataset.lap_samples(s, WAYPOINTS, CFG, settings)
    assert n_bad == 1
    assert not any(8.0 <= t <= 12.5 for t in stamps)
    assert dropped['bad_interval'] == 45  # 8.01 ~ 12.41 s 스캔
    assert set(weights) == {1.0}  # manual 모드의 teleop은 끼어들기가 아님


def test_lap_samples_drops_stale_people_input():
    s = make_streams()
    s.predictions = dataset.Series([(0.0, [])])
    _, _, _, stamps, dropped, _ = dataset.lap_samples(s, WAYPOINTS, CFG, metrics.DEFAULT_SETTINGS)
    assert max(stamps) <= CFG['input_timeout']
    assert dropped['no_people'] > 0


def test_split_laps_by_whole_lap_and_reproducible():
    val = dataset.split_laps([0, 1, 2, 3, 4], 0.2, seed=7)
    assert len(val) == 1 and val == dataset.split_laps([0, 1, 2, 3, 4], 0.2, seed=7)
    assert len(dataset.split_laps([0, 1], 0.2, seed=0)) == 1  # 적어도 하나
    assert len(dataset.split_laps([0, 1], 0.9, seed=0)) == 1  # 학습도 적어도 하나
    assert dataset.split_laps([0], 0.2, seed=0) == set()


def write_lap_folder(root, name, waypoints_path):
    folder = root / name
    (folder / run_files.BAG_DIR).mkdir(parents=True)
    meta = run_files.build_meta('manual', 'kim', str(waypoints_path), '', '', '', 'x')
    run_files.write_json(folder / run_files.META_FILE, meta)
    return folder


def test_build_dataset_writes_lap_split_npz(tmp_path):
    waypoints = tmp_path / 'w.yaml'
    waypoints.write_text('waypoints:\n  - {name: A, type: pass, x: 10, y: 0, yaw: 0}\n')
    folders = [str(write_lap_folder(tmp_path, f'lap{i}', waypoints)) for i in range(3)]
    out = tmp_path / 'out' / 'data.npz'
    cfg = {**CFG, 'val_fraction': 0.34}
    laps = dataset.build_dataset(folders, str(out), cfg, metrics.DEFAULT_SETTINGS,
                                 reader=lambda path: make_streams())
    with np.load(out) as data:
        assert data['X'].shape == (90, features.FEATURE_SIZE) and data['X'].dtype == np.float32
        assert data['y'].shape == (90, 2)
        for lap in range(3):
            assert len(set(data['is_val'][data['lap_id'] == lap])) == 1  # 바퀴 안은 한쪽으로만
        assert data['is_val'].sum() == 30
        info = json.loads(str(data['info']))
    assert info['frame_settings']['v_max'] == 0.5
    assert info['feature_layout'] == features.__doc__
    assert len(info['folders']) == 3 and sum(lap['val'] for lap in laps) == 1


def test_waypoints_hash_mismatch_stops(tmp_path):
    waypoints = tmp_path / 'w.yaml'
    waypoints.write_text('waypoints: []\n')
    meta = run_files.build_meta('manual', '', str(waypoints), '', '', '', 'x')
    other = tmp_path / 'other.yaml'
    other.write_text('waypoints: [1]\n')
    with pytest.raises(ValueError):
        dataset.resolve_waypoints(meta, str(other))
    assert dataset.resolve_waypoints(meta, None) == str(waypoints)
