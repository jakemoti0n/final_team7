"""정책 입력 특징 함수 단위 테스트. 기대값은 손으로 계산했다."""

import math

from limbo_imitation import features
import numpy as np
import pytest


def test_bin_scan_groups_eight_rays_into_four_bins():
    # 45°마다 한 점, 4구간(90°씩): 구간 0 = 0°·45°, 1 = 90°·135°, 2 = 180°·225°, 3 = 270°·315°
    ranges = [2.0, 1.0, 3.0, math.inf, 0.05, math.nan, 7.0, 6.0]
    result = features.bin_scan(ranges, 0.0, math.pi / 4, n_bins=4, range_min=0.1, range_max=6.0)
    # 0.05(range_min 밑)·nan·inf·7.0(range_max 위)은 모름 = 1.0
    np.testing.assert_allclose(result, [1.0 / 6.0, 3.0 / 6.0, 1.0, 1.0])


def test_bin_scan_starts_at_front_even_when_scan_starts_behind():
    # -180°에서 시작하는 스캔: 정면 점(인덱스 2, 0°)이 구간 0에 들어가야 한다
    ranges = [5.0, 5.0, 1.2, 5.0]
    result = features.bin_scan(ranges, -math.pi, math.pi / 2, n_bins=4, range_max=6.0)
    assert result[0] == pytest.approx(0.2)
    assert result[2] == pytest.approx(5.0 / 6.0)


def test_bin_scan_empty_bin_is_far():
    result = features.bin_scan([1.0], 0.0, 0.1, n_bins=4)
    np.testing.assert_allclose(result[1:], [1.0, 1.0, 1.0])


def test_goal_straight_ahead_one_meter():
    np.testing.assert_allclose(features.goal_features((1.0, 0.0), False, max_dist=5.0),
                               [0.2, 0.0, 1.0, 0.0], atol=1e-12)


def test_goal_left_ninety_degrees_stop_waypoint_far_away():
    np.testing.assert_allclose(features.goal_features((0.0, 8.0), True, max_dist=5.0),
                               [1.0, 1.0, 0.0, 1.0], atol=1e-12)


def test_velocity_features_clipped():
    np.testing.assert_allclose(features.velocity_features(0.3, -2.0, 0.6, 1.0), [0.5, -1.0])


def test_people_sorted_by_distance_and_padded():
    people = [(3.0, 0.0, -1.0, 0.0), (0.0, 1.0, 0.0, 0.5), (9.0, 0.0, 0.0, 0.0)]
    result = features.people_features(people, k=3, max_dist=5.0)
    np.testing.assert_allclose(result[:5], [0.0, 0.2, 0.0, 0.5, 1.0])
    np.testing.assert_allclose(result[5:10], [0.6, 0.0, -1.0, 0.0, 1.0])
    np.testing.assert_allclose(result[10:], [0.0] * 5)  # 9 m 사람은 max_dist 밖


def test_stack_frames_repeats_oldest_when_short():
    a, b = np.array([1.0]), np.array([2.0])
    np.testing.assert_allclose(features.stack_frames([a, b], n=3), [1.0, 1.0, 2.0])
    np.testing.assert_allclose(features.stack_frames([a, b, a, b], n=3), [2.0, 1.0, 2.0])
    with pytest.raises(ValueError):
        features.stack_frames([], n=3)


def test_frame_and_feature_sizes_agree():
    frame = features.frame_features(np.ones(features.SCAN_BINS),
                                    features.goal_features((1.0, 0.0), False),
                                    features.velocity_features(0.0, 0.0, 0.6, 1.0),
                                    features.people_features([]))
    assert frame.shape == (features.FRAME_SIZE,)
    assert features.stack_frames([frame]).shape == (features.FEATURE_SIZE,)


def test_map_to_base_yaw_ninety():
    # 로봇 (1, 1)에서 +y(지도 위쪽)를 봄. 지도 (1, 2)는 로봇 바로 앞 1 m, (0, 1)은 왼쪽 1 m
    np.testing.assert_allclose(features.map_to_base((1.0, 2.0), (1.0, 1.0, math.pi / 2)),
                               (1.0, 0.0), atol=1e-12)
    np.testing.assert_allclose(features.map_to_base((0.0, 1.0), (1.0, 1.0, math.pi / 2)),
                               (0.0, 1.0), atol=1e-12)
