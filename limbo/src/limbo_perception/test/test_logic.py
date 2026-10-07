"""ROS 없이 돌아가는 추적·예측·의도 로직 단위 테스트."""

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
