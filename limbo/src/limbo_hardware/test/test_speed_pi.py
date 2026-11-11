"""PI units, directional bounds, anti-windup and invalid-input tests; no hardware."""
import math
import unittest

from limbo_hardware.speed_pi import PIConfig, WheelSpeedPI


class SpeedPITests(unittest.TestCase):
    def test_start_is_small_without_a_kick_and_target_slews(self):
        pi = WheelSpeedPI()
        first = pi.step(.2666666667, 0., .05)
        self.assertAlmostEqual(first.ramped_rad_s, .02)
        self.assertAlmostEqual(first.integral, .0002)
        self.assertEqual(first.duty_raw, round(.0022*32767))
        self.assertLess(first.output, .01)
        second = pi.step(.2666666667, 0., .05)
        self.assertAlmostEqual(second.ramped_rad_s, .04)
        self.assertLessEqual(abs(second.output-first.output), .15*.05+1/32767)

    def test_sign_symmetry_and_normalized_feedback(self):
        positive, negative = WheelSpeedPI(), WheelSpeedPI()
        for measured in (0., .01, .03, .05, .09, .15, .21, .24, .27):
            a = positive.step(.2666666667, measured, .05)
            b = negative.step(-.2666666667, -measured, .05)
            self.assertEqual(a.duty_raw, -b.duty_raw)
            self.assertAlmostEqual(a.integral, -b.integral)
            self.assertGreaterEqual(a.duty_raw, 0)
            self.assertLessEqual(b.duty_raw, 0)

    def test_zero_resets_immediately_even_at_high_output(self):
        pi = WheelSpeedPI()
        for _ in range(200):
            pi.step(.4, 0., .05)
        self.assertGreater(pi.output, .05)
        zero = pi.step(0., .2, .05)
        self.assertEqual(zero.duty_raw, 0)
        self.assertEqual((pi.integral, pi.ramped_rad_s, pi.output, pi.direction),
                         (0., 0., 0., 0))
        self.assertEqual(zero.error_rad_s, -.2)

    def test_reversal_requires_zero_and_rejection_preserves_state(self):
        pi = WheelSpeedPI()
        pi.step(.2, .01, .05)
        before = vars(pi).copy()
        with self.assertRaisesRegex(ValueError, 'zero command'):
            pi.step(-.2, .01, .05)
        self.assertEqual(vars(pi), before)
        pi.step(0., .01, .05)
        reverse = pi.step(-.2, 0., .05)
        self.assertLess(reverse.duty_raw, 0)

    def test_hard_duty_limit_and_no_integral_windup(self):
        pi = WheelSpeedPI()
        values = [pi.step(.4, 0., .05) for _ in range(200)]
        self.assertTrue(all(0 <= v.duty_raw <= 3276 for v in values))
        # Integrate only to usable headroom, then stop accumulating hidden state.
        final_integral = pi.integral
        for _ in range(200):
            pi.step(.4, 0., .05)
        self.assertEqual(pi.integral, final_integral)
        self.assertLess(pi.integral, .1)

    def test_slew_antiwindup_and_recovery(self):
        pi = WheelSpeedPI(PIConfig(kp=1., ki=1.))
        first = pi.step(.4, 0., .05)
        self.assertTrue(first.rate_limited)
        self.assertEqual(first.integral, 0.)
        self.assertLessEqual(first.output, .0075+1/32767)
        for _ in range(30):
            pi.step(.4, 0., .05)
        before = pi.output
        after = pi.step(.4, .5, .05)
        self.assertLess(after.output, before)
        self.assertGreaterEqual(after.duty_raw, 0)

    def test_overspeed_never_commands_reverse_torque(self):
        for sign in (1,-1):
            pi = WheelSpeedPI()
            for _ in range(30):
                result = pi.step(sign*.2, sign*.8, .05)
                self.assertEqual(result.duty_raw, 0)
                self.assertEqual(result.integral, 0.)

    def test_a_low_gain_model_approaches_target_with_bounded_outputs(self):
        # A deliberately simple synthetic first-order plant catches feedback sign
        # errors and integration mistakes; it is not a model identified on Limbo.
        for sign in (1., -1.):
            pi=WheelSpeedPI()
            measured=0.
            for _ in range(200):
                result=pi.step(sign*.2666666667, measured, .05)
                measured+=(6.0*result.output-measured)*.05/.25
                self.assertLessEqual(abs(result.duty_raw), 3276)
            self.assertAlmostEqual(measured, sign*.2666666667, delta=.005)

    def test_invalid_runtime_input_does_not_change_state(self):
        pi=WheelSpeedPI()
        pi.step(.2,.01,.05)
        for args in ((float('nan'),0.,.05),(.2,float('inf'),.05),(.2,0.,float('nan')),
                     (.2,0.,.019),(.2,0.,.151),(.401,0.,.05),(True,0.,.05)):
            before=vars(pi).copy()
            with self.subTest(args=args), self.assertRaises(ValueError):
                pi.step(*args)
            self.assertEqual(vars(pi),before)

    def test_configuration_validation(self):
        for kwargs in ({'kp':-1},{'ki':float('nan')},{'kp':0.,'ki':0.},
                       {'max_duty_raw':32768},{'max_duty_raw':True},
                       {'output_slew_per_s':0},{'target_slew_rad_s2':float('inf')},
                       {'min_dt':.01},{'max_dt':.2},{'min_dt':.1,'max_dt':.05}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                PIConfig(**kwargs)

    def test_overflow_is_rejected_without_corrupting_state(self):
        pi=WheelSpeedPI(PIConfig(kp=1e308))
        before=vars(pi).copy()
        with self.assertRaisesRegex(ValueError,'overflow'):
            pi.step(.2,-1e308,.05)
        self.assertEqual(vars(pi),before)

    def test_partial_integration_reaches_cap_without_a_stationary_deadband(self):
        for cap in (3276,4095,4915):
            for sign in (1.,-1.):
                pi=WheelSpeedPI(PIConfig(max_duty_raw=cap))
                rows=[pi.step(sign*.2666666667,0.,.05) for _ in range(100)]
                self.assertEqual(rows[-1].duty_raw,sign*cap)
                self.assertTrue(any(r.integral_partial for r in rows))
                final=pi.integral
                for _ in range(50):
                    r=pi.step(sign*.2666666667,0.,.05)
                    self.assertEqual(r.duty_raw,sign*cap)
                    self.assertAlmostEqual(pi.integral,final)
                self.assertAlmostEqual(final,sign*(cap/32767-.1*.2666666667))

    def test_partial_integration_uses_only_available_slew_headroom(self):
        for sign in (1.,-1.):
            pi=WheelSpeedPI(PIConfig(ki=10.,max_duty_raw=4095))
            pi.direction=int(sign);pi.ramped_rad_s=sign*.2
            pi.output=sign*.02;pi.integral=sign*.019
            before=pi.integral
            r=pi.step(sign*.2,sign*.18,.05)
            self.assertTrue(r.integral_limited)
            self.assertTrue(r.integral_partial)
            self.assertAlmostEqual(r.integral,sign*(.0275-.002))
            self.assertGreater((r.integral-before)*sign,0.)
            self.assertLess(abs(r.integral-before),10.*abs(r.error_rad_s)*.05)
            self.assertLessEqual(abs(r.output),.0275+.5/32767)

    def test_p_beyond_bound_does_not_backcalculate_reverse_integral(self):
        for sign in (1.,-1.):
            pi=WheelSpeedPI(PIConfig(kp=1.,ki=1.))
            r=pi.step(sign*.4,0.,.05)
            self.assertEqual(r.integral,0.)
            self.assertTrue(r.integral_limited)
            self.assertFalse(r.integral_partial)

    def test_partial_integral_steps_preserve_error_direction_and_step_size(self):
        for sign in (1.,-1.):
            pi=WheelSpeedPI(PIConfig(max_duty_raw=4095))
            feedback=([0.]*60+[.6]*10+[.1]*10+[.4]*10+[0.]*30)*2
            for index,value in enumerate(feedback):
                dt=(.03,.05,.08)[index%3];before=pi.integral
                r=pi.step(sign*.2666666667,sign*value,dt)
                delta=r.integral-before
                self.assertGreaterEqual(delta*r.error_rad_s,-1e-15)
                self.assertLessEqual(abs(delta),.2*abs(r.error_rad_s)*dt+1e-15)
                self.assertGreaterEqual(sign*r.integral,-1e-15)
                self.assertGreaterEqual(sign*r.duty_raw,0)
                self.assertLessEqual(abs(r.duty_raw),4095)


if __name__=='__main__':
    unittest.main()
