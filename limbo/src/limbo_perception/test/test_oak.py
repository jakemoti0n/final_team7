"""OAK 입력 경로(카메라 안 모델 출력 풀기·프레임 짝짓기·깊이 단위) 단위 테스트. 장치 없이 돈다."""

from limbo_perception import geometry, oak
import numpy as np


def _raw(candidates):
    """[cx, cy, w, h, person 점수, leg 점수] 후보 목록 → 모델 원시 출력 모양 (6 × 후보 수)."""
    return np.array(candidates, dtype=np.float32).T.flatten()


def test_decode_keeps_best_class_and_drops_low_scores():
    raw = _raw([
        [100, 200, 40, 120, 0.9, 0.1],   # person
        [300, 250, 60, 80, 0.2, 0.7],    # leg
        [500, 100, 30, 30, 0.1, 0.2],    # 문턱 아래
    ])

    dets = oak.decode_output(raw, conf=0.3)

    assert dets.shape == (2, 6)
    by_class = {int(c): row for *row, c in dets}
    np.testing.assert_allclose(by_class[0][:4], [80, 140, 120, 260])
    np.testing.assert_allclose(by_class[1][:4], [270, 210, 330, 290])
    assert abs(by_class[1][4] - 0.7) < 1e-6


def test_decode_nms_removes_overlapping_duplicate():
    raw = _raw([
        [100, 200, 40, 120, 0.9, 0.0],
        [102, 201, 40, 120, 0.8, 0.0],
    ])

    dets = oak.decode_output(raw, conf=0.3, iou=0.5)

    assert len(dets) == 1
    assert abs(dets[0, 4] - 0.9) < 1e-6


def test_decode_without_candidates_is_empty():
    assert oak.decode_output(_raw([[0, 0, 1, 1, 0.0, 0.0]])).shape == (0, 6)


def test_crop_depth_matches_preview_rows():
    depth = np.arange(oak.DEPTH_HEIGHT)[:, None].repeat(oak.DEPTH_WIDTH, 1)

    cropped = oak.crop_depth(depth)

    assert cropped.shape == (oak.HEIGHT, oak.WIDTH)
    assert cropped[0, 0] == oak.DEPTH_ROW_OFFSET
    assert cropped[-1, 0] == oak.DEPTH_ROW_OFFSET + oak.HEIGHT - 1


def test_matcher_pairs_by_sequence_and_picks_nearest_depth():
    m = oak.FrameMatcher(max_depth_gap=0.05)
    m.add_depth(0.90, 'depth_a')
    m.add_depth(1.02, 'depth_b')

    assert m.add_frame(7, 1.00, 'frame7') is None   # NN 결과가 아직 없음
    assert m.add_result(7, 'nn7') == (1.00, 'frame7', 'nn7', 'depth_b')


def test_matcher_result_may_arrive_before_frame():
    m = oak.FrameMatcher()
    m.add_depth(1.0, 'depth')

    assert m.add_result(3, 'nn3') is None
    assert m.add_frame(3, 1.0, 'frame3')[2] == 'nn3'


def test_matcher_without_close_depth_returns_none_depth():
    m = oak.FrameMatcher(max_depth_gap=0.05)
    m.add_depth(0.5, 'old_depth')
    m.add_frame(1, 1.0, 'frame')

    assert m.add_result(1, 'nn')[3] is None


def test_matcher_drops_unpaired_old_sequences():
    m = oak.FrameMatcher(keep=4)
    m.add_frame(1, 0.0, 'lost')   # NN이 이 프레임을 버려 결과가 끝내 안 옴
    for seq in range(2, 10):
        m.add_frame(seq, 0.0, 'f')
        m.add_result(seq, 'r')

    assert 1 not in m.frames
    assert not m.results


def test_depth_in_meters_converts_millimeters_only():
    mm = np.array([[0, 1500]], dtype=np.uint16)
    meters = np.array([[1.5]], dtype=np.float32)

    np.testing.assert_allclose(geometry.depth_in_meters(mm, '16UC1'), [[0.0, 1.5]])
    assert geometry.depth_in_meters(meters, '32FC1') is meters


def test_detections_array_filters_class_and_confidence():
    rows = [
        [0, 0, 10, 10, 0.9, 0],
        [0, 0, 10, 10, 0.2, 1],   # 신뢰도 낮음
        [0, 0, 10, 10, 0.9, 2],   # 안 쓰는 클래스
    ]

    dets = geometry.detections_array(rows, [0, 1], 0.3)

    assert dets.shape == (1, 6)
    assert geometry.detections_array([], [0, 1], 0.3).shape == (0, 6)


def test_backoff_doubles_up_to_max_and_resets():
    b = oak.ReconnectBackoff(min_delay=1.0, max_delay=5.0)

    assert [b.next_delay() for _ in range(5)] == [1.0, 2.0, 4.0, 5.0, 5.0]
    b.reset()
    assert b.next_delay() == 1.0
