"""Exact-window count velocity tests; no ROS, device or invented plant."""
import math
import unittest

from limbo_hardware.speed_estimator import CountWindowEstimator


class CountWindowTests(unittest.TestCase):
    def test_baseline_and_warmup_use_actual_available_time(self):
        estimator=CountWindowEstimator(1000.,2000.,.1)
        self.assertIsNone(estimator.update(0.,0,0))
        r=estimator.update(.05,10,20)
        self.assertAlmostEqual(r.span_s,.05)
        self.assertEqual(r.window_start_s,0.)
        self.assertAlmostEqual(r.left_rad_s,math.tau*.2)
        self.assertAlmostEqual(r.right_rad_s,math.tau*.2)

    def test_jittered_linear_counts_keep_exact_window_and_velocity(self):
        estimator=CountWindowEstimator(1000.,2000.,.1)
        for ms in (0,53,104,155,204,258,307,361):
            r=estimator.update(ms/1000,ms,2*ms)
            if r is not None:
                self.assertAlmostEqual(r.left_rad_s,math.tau)
                self.assertAlmostEqual(r.right_rad_s,math.tau)
                self.assertAlmostEqual(r.span_s,min(ms/1000,.1))

    def test_boundary_is_interpolated_without_including_older_motion(self):
        estimator=CountWindowEstimator(1000.,1000.,.1)
        estimator.update(0.,0,0)
        estimator.update(.06,6,-6)
        estimator.update(.11,16,-16)
        r=estimator.update(.16,16,-16)
        self.assertAlmostEqual(r.window_start_s,.06)
        self.assertAlmostEqual(r.left_rad_s,10*math.tau/1000/.1)
        self.assertAlmostEqual(r.right_rad_s,-r.left_rad_s)
        r=estimator.update(.18,16,-16)
        # Boundary .08 lies 40% between .06/count6 and .11/count16.
        self.assertAlmostEqual(r.left_rad_s,6*math.tau/1000/.1)
        self.assertAlmostEqual(r.right_rad_s,-r.left_rad_s)

    def test_old_motion_leaves_window_and_stationary_speed_becomes_zero(self):
        estimator=CountWindowEstimator(1000.,1000.,.1)
        for t,c in ((0.,0),(.05,10),(.10,20),(.15,20),(.20,20),(.25,20)):
            r=estimator.update(t,c,c)
        self.assertAlmostEqual(r.left_rad_s,0.)
        self.assertAlmostEqual(r.right_rad_s,0.)
        self.assertAlmostEqual(r.span_s,.1)

    def test_large_signed_totals_preserve_small_count_differences(self):
        estimator=CountWindowEstimator(1000.,1000.,.1)
        offset=2**60
        estimator.update(0.,offset,-offset)
        estimator.update(.06,offset+6,-offset-6)
        r=estimator.update(.15,offset+15,-offset-15)
        self.assertAlmostEqual(r.left_rad_s,math.tau*.1)
        self.assertAlmostEqual(r.right_rad_s,-math.tau*.1)

    def test_invalid_input_preserves_history_and_can_recover(self):
        estimator=CountWindowEstimator(1000.,1000.)
        estimator.update(0.,0,0);estimator.update(.05,5,5)
        history=list(estimator._samples)
        for args in ((.05,6,6),(.04,6,6),(float('nan'),6,6),(.1,True,6),
                     (.1,6.,6),(.1,2**63,6),(1e100,6,6)):
            with self.subTest(args=args),self.assertRaises(ValueError):
                estimator.update(*args)
            self.assertEqual(list(estimator._samples),history)
        self.assertAlmostEqual(estimator.update(.1,10,10).left_rad_s,math.tau*.1)

    def test_window_limits_and_bounded_history(self):
        for bad in (.099,.201,0.,True,float('inf')):
            with self.assertRaises(ValueError):CountWindowEstimator(1000.,1000.,bad)
        for bad in (0.,-1.,True,float('nan')):
            with self.assertRaises(ValueError):CountWindowEstimator(bad,1000.)
        estimator=CountWindowEstimator(1000.,1000.)
        self.assertEqual(estimator.window_s,.2)
        for i in range(1001):estimator.update(i*.05,i,i)
        self.assertLessEqual(len(estimator._samples),6)
        with self.assertRaises(AttributeError):estimator.window_s=.1


if __name__=='__main__':unittest.main()
