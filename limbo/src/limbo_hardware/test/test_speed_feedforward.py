"""Bounded proportional feedforward tests, without ROS or hardware."""
import unittest

from limbo_hardware.speed_pi import PIConfig,WheelSpeedPI


class FeedforwardTests(unittest.TestCase):
    def test_forward_curve_and_reverse_fallback(self):
        cfg = PIConfig(kp=.02, ki=.10, feedforward_gain=.25,
                       forward_curve=(.9, .22, 1.7, .30), max_duty_raw=9830,
                       max_target_rad_s=3., target_slew_rad_s2=80.)
        pi = WheelSpeedPI(cfg)
        for target, expected in [(.45, .11), (.9, .22), (1.3, .26), (1.8, 9830/32767)]:
            result = pi.step(target, target, .05)
            self.assertAlmostEqual(result.feedforward_output, expected)
            self.assertLessEqual(abs(result.duty_raw), 9830)
        self.assertEqual(pi.step(0., .5, .05).duty_raw, 0)
        self.assertAlmostEqual(pi.step(-.8, -.8, .05).feedforward_output, -.2)
        for curve in ((1., .24), (1., .22, .9, .30), (.9, .4, 1.7, .30),
                      (.9, .22, float('nan'), .3)):
            with self.subTest(curve=curve), self.assertRaises(ValueError):
                PIConfig(forward_curve=curve)

    def test_gain_is_explicit_bounded_and_defaults_off(self):
        self.assertEqual(PIConfig().feedforward_gain,0.)
        for value in (-.001,.376,True,float('nan'),float('inf'),'0.3375'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                PIConfig(feedforward_gain=value)
        self.assertEqual(PIConfig(feedforward_gain=.375).feedforward_gain,.375)

    def test_feedforward_follows_signed_target_ramp_and_all_output_limits(self):
        pos=WheelSpeedPI(PIConfig(kp=.06,max_duty_raw=4095,feedforward_gain=.3375))
        neg=WheelSpeedPI(PIConfig(kp=.06,max_duty_raw=4095,feedforward_gain=.3375))
        previous=0.
        for _ in range(100):
            a=pos.step(.26666666666666666,0.,.05)
            b=neg.step(-.26666666666666666,0.,.05)
            self.assertAlmostEqual(a.feedforward_output,.3375*a.ramped_rad_s)
            self.assertAlmostEqual(a.feedforward_output,-b.feedforward_output)
            self.assertEqual(a.duty_raw,-b.duty_raw)
            self.assertLessEqual(abs(a.output-previous),.15*.05+1/32767)
            self.assertGreaterEqual(a.duty_raw,0)
            self.assertLessEqual(a.duty_raw,4095)
            previous=a.output
        self.assertAlmostEqual(a.feedforward_output,.09)

    def test_overspeed_can_cancel_feedforward_to_zero_without_reverse_torque(self):
        for sign in (1.,-1.):
            pi=WheelSpeedPI(PIConfig(kp=.06,max_duty_raw=4095,feedforward_gain=.3375))
            for _ in range(40):pi.step(sign*.2666666667,0.,.05)
            before=pi.output
            first=pi.step(sign*.2666666667,sign*.6,.05)
            self.assertLess(abs(first.output),abs(before))
            for _ in range(80):
                r=pi.step(sign*.2666666667,sign*.6,.05)
                self.assertGreaterEqual(sign*r.duty_raw,0)
            self.assertEqual(r.duty_raw,0)
            self.assertGreater(abs(r.feedforward_output),0.)
            self.assertLess(sign*r.integral,0.)

    def test_zero_removes_feedforward_and_resets_all_dynamic_state(self):
        pi=WheelSpeedPI(PIConfig(feedforward_gain=.3375,max_duty_raw=4095))
        for _ in range(40):pi.step(.2666666667,0.,.05)
        z=pi.step(0.,.2,.05)
        self.assertEqual((z.duty_raw,z.feedforward_output,z.integral),(0,0.,0.))
        self.assertEqual((pi.integral,pi.ramped_rad_s,pi.output,pi.direction),(0.,0.,0.,0))
        reverse=pi.step(-.2666666667,0.,.05)
        self.assertLess(reverse.feedforward_output,0.)
        self.assertLessEqual(abs(reverse.output),.15*.05+1/32767)


if __name__=='__main__':unittest.main()
