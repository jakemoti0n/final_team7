"""Deterministic odometry/fault tests, with no ROS or physical port dependency."""
import math
import unittest
from dataclasses import replace

from limbo_hardware.odometry_core import CountSample, WheelOdometry


def sample(seq, right=0, left=0, *, dr=0, dl=0, session='one', stamp=None, baseline=False):
    return CountSample(stamp or 1_000_000_000 + seq * 100_000_000,
                       session, seq, baseline, dr, dl, right, left)


class CoreTests(unittest.TestCase):
    def core(self, **kwargs):
        config = dict(left_radius=1/(2*math.pi), right_radius=1/(2*math.pi),
                      separation=1.0, left_cpr=1000, right_cpr=1000)
        config.update(kwargs)
        return WheelOdometry(**config)

    def feed(self, core, msg, age_ns=0):
        return core.update(msg, msg.stamp_ns + age_ns)

    def initialize(self, core):
        self.assertIsNone(self.feed(core, sample(0, baseline=True)))

    def test_unequal_cpr_equal_wheel_revolutions_are_straight(self):
        core = self.core(left_radius=.075, right_radius=.075, separation=.54,
                         left_cpr=3688, right_cpr=3607)
        self.initialize(core)
        result = self.feed(core, sample(1, 3607, 3688, dr=3607, dl=3688))
        self.assertAlmostEqual(result.x, .15*math.pi)
        self.assertAlmostEqual(result.y, 0)
        self.assertAlmostEqual(result.yaw, 0)
        self.assertAlmostEqual(result.vx, .15*math.pi/.1)
        self.assertAlmostEqual(result.wz, 0)

    def test_exact_arc_not_euler_translation(self):
        core = self.core()
        self.initialize(core)
        result = self.feed(core, sample(1, 1000, 0, dr=1000))
        self.assertAlmostEqual(result.x, .5*math.sin(1))
        self.assertAlmostEqual(result.y, .5*(1-math.cos(1)))
        self.assertAlmostEqual(result.yaw, 1)
        self.assertAlmostEqual(result.vx, 5)
        self.assertAlmostEqual(result.wz, 10)

    def test_pure_rotation_and_reverse_retrace(self):
        core = self.core()
        self.initialize(core)
        result = self.feed(core, sample(1, 500, -500, dr=500, dl=-500))
        self.assertEqual((result.x, result.y), (0, 0))
        self.assertAlmostEqual(result.yaw, 1)
        result = self.feed(core, sample(2, 0, 0, dr=-500, dl=500))
        self.assertAlmostEqual(result.yaw, 0)
        result = self.feed(core, sample(3, -100, -100, dr=-100, dl=-100))
        self.assertAlmostEqual(result.x, -.1)
        self.assertAlmostEqual(result.vx, -1)

    def test_straight_limit_and_angle_wrapping_are_finite(self):
        core = self.core(left_cpr=10**9, right_cpr=10**9)
        self.initialize(core)
        result = self.feed(core, sample(1, 1000001, 1000000, dr=1000001, dl=1000000))
        self.assertAlmostEqual(result.x, .0010000005)
        self.assertTrue(all(math.isfinite(v) for v in (result.x, result.y, result.yaw)))
        core = self.core()
        self.initialize(core)
        result = self.feed(core, sample(1, 4000, -4000, dr=4000, dl=-4000))
        self.assertTrue(-math.pi <= result.yaw <= math.pi)
        self.assertAlmostEqual(math.sin(result.yaw), math.sin(8))

    def test_first_nonbaseline_observation_does_not_integrate_pre_subscription_travel(self):
        core = self.core()
        self.assertIsNone(self.feed(core, sample(42, 5000, 5000, dr=20, dl=20)))
        result = self.feed(core, sample(43, 5020, 5020, dr=20, dl=20))
        self.assertAlmostEqual(result.x, .02)

    def test_encoder_reconnect_preserves_pose_and_rejects_retired_session(self):
        core = self.core()
        self.initialize(core)
        self.feed(core, sample(1, 100, 100, dr=100, dl=100))
        self.assertIsNone(self.feed(core, sample(0, session='two', stamp=1_200_000_000, baseline=True)))
        self.assertAlmostEqual(core.x, .1)
        self.assertEqual(core.rebases, 1)
        result = self.feed(core, sample(1, 10, 10, dr=10, dl=10,
                                       session='two', stamp=1_300_000_000))
        self.assertAlmostEqual(result.x, .11)
        reference = core.reference
        self.assertIsNone(self.feed(core, sample(2, 200, 200, dr=100, dl=100,
                                                stamp=1_400_000_000)))
        self.assertIs(core.reference, reference)
        self.assertEqual(core.status, 'retired_session')

    def test_sequence_gap_skips_unknown_path_and_covariance_increases(self):
        core = self.core()
        self.initialize(core)
        first = self.feed(core, sample(1, 100, 100, dr=100, dl=100))
        self.assertIsNone(self.feed(core, sample(3, 400, 400, dr=100, dl=100)))
        self.assertAlmostEqual(core.x, .1)
        result = self.feed(core, sample(4, 410, 410, dr=10, dl=10))
        self.assertAlmostEqual(result.x, .11)
        self.assertGreaterEqual(result.position_variance, first.position_variance+.25)
        self.assertGreaterEqual(result.yaw_variance, first.yaw_variance+.25)

    def test_duplicate_and_reordered_samples_do_not_poison_reference(self):
        core = self.core()
        self.initialize(core)
        first = sample(1, 100, 100, dr=100, dl=100)
        self.feed(core, first)
        self.assertIsNone(self.feed(core, first, age_ns=10**9))
        self.assertIsNone(self.feed(core, sample(0, baseline=True)))
        self.assertFalse(core.force_rebase)
        result = self.feed(core, sample(2, 120, 120, dr=20, dl=20))
        self.assertAlmostEqual(result.x, .12)

    def test_stale_future_and_explicit_staleness_do_not_publish_a_jump(self):
        for kind in ('stale', 'future', 'timer'):
            with self.subTest(kind=kind):
                core = self.core()
                self.initialize(core)
                self.feed(core, sample(1, 100, 100, dr=100, dl=100))
                if kind == 'timer':
                    core.invalidate()
                else:
                    age = 600_000_000 if kind == 'stale' else -60_000_000
                    self.assertIsNone(self.feed(core, sample(2, 200, 200, dr=100, dl=100), age))
                self.assertIsNone(self.feed(core, sample(3, 300, 300, dr=100, dl=100)))
                result = self.feed(core, sample(4, 320, 320, dr=20, dl=20))
                self.assertAlmostEqual(result.x, .12)

    def test_time_jump_and_inconsistent_totals_rebaseline(self):
        for changed in (sample(1, 1000, 1000, dr=1000, dl=1000, stamp=2_000_000_000),
                        sample(1, 1000, 1000, dr=1000, dl=1000, stamp=900_000_000),
                        sample(1, 1000, 1000, dr=10, dl=10)):
            core = self.core()
            self.initialize(core)
            self.assertIsNone(self.feed(core, changed))
            self.assertEqual(core.x, 0)
            follow = replace(changed, sequence=2, stamp_ns=changed.stamp_ns+100_000_000,
                             right_total=1010, left_total=1010, right_delta=10, left_delta=10)
            result = self.feed(core, follow)
            self.assertAlmostEqual(result.x, .01)

    def test_stationary_samples_retain_pose_have_zero_twist_and_positive_covariance(self):
        core = self.core()
        self.initialize(core)
        moving = self.feed(core, sample(1, 20, 20, dr=20, dl=20))
        stopped = self.feed(core, sample(2, 20, 20))
        self.assertEqual((moving.x, moving.y, moving.yaw), (stopped.x, stopped.y, stopped.yaw))
        self.assertEqual((stopped.vx, stopped.wz), (0, 0))
        self.assertGreater(stopped.position_variance, 0)
        self.assertGreater(stopped.yaw_variance, 0)

    def test_invalid_geometry_calibration_and_baseline_are_rejected(self):
        for name in ('left_radius', 'right_radius', 'separation', 'left_cpr', 'right_cpr'):
            for bad in (0, -1, float('nan'), float('inf')):
                with self.subTest(parameter=name, bad=bad):
                    with self.assertRaises(ValueError):
                        self.core(**{name: bad})
        core = self.core()
        self.assertIsNone(self.feed(core, sample(0, 1, 0, baseline=True)))
        self.assertIsNone(core.reference)
        self.assertEqual(core.status, 'invalid_sample')

    def test_extreme_derived_scales_and_nonfinite_estimates_are_rejected(self):
        for kwargs in ({'left_cpr': 1e-320}, {'right_radius': 1e308},
                       {'separation': 1e-320}):
            with self.subTest(parameters=kwargs):
                with self.assertRaises(ValueError):
                    self.core(**kwargs)
        core = self.core(position_variance_per_meter=1e308)
        self.initialize(core)
        self.assertIsNone(self.feed(core, sample(1, 4000, 4000, dr=4000, dl=4000)))
        self.assertEqual(core.x, 0)
        self.assertEqual(core.status, 'nonfinite_estimate')


if __name__ == '__main__':
    unittest.main()
