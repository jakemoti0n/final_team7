"""Per-wheel PI configuration API; unchanged PI mathematics, no device access."""
from dataclasses import asdict
import unittest

from limbo_hardware.speed_bench_node import _resolve_wheel_pi_configs
from limbo_hardware.speed_pi import PIConfig, WheelSpeedPI


class WheelFeedforwardConfigTests(unittest.TestCase):
    def test_defaults_reuse_common_configuration_and_legacy_trajectory_exactly(self):
        common=PIConfig(feedforward_gain=.25,max_duty_raw=4915)
        configs=_resolve_wheel_pi_configs(common,-1.,-1.)
        self.assertTrue(all(config is common for config in configs))
        reference=WheelSpeedPI(common)
        controllers=[WheelSpeedPI(config) for config in configs]
        for target,actual,dt in [( .4,.03,.05)]*10+[(.4,.5,.07)]*4+[(0.,0.,.05),(-.4,-.1,.06)]*5:
            expected=asdict(reference.step(target,actual,dt))
            for controller in controllers:
                self.assertEqual(asdict(controller.step(target,actual,dt)),expected)

    def test_explicit_left_right_are_not_motor_channel_order_and_change_only_gain(self):
        common=PIConfig(feedforward_gain=.25,max_duty_raw=4915)
        configs=_resolve_wheel_pi_configs(common,.2375,.2625)
        for config,expected in zip(configs,(.2375,.2625)):
            self.assertEqual(asdict(config),dict(asdict(common),feedforward_gain=expected))
        self.assertEqual(common.feedforward_gain,.25)

    def test_only_exact_numeric_minus_one_inherits(self):
        common=PIConfig(feedforward_gain=.25)
        for values,expected in [((-1.,0.),(.25,0.)),((.375,-1),(.375,.25)),((0,0),(0,0))]:
            self.assertEqual(tuple(c.feedforward_gain for c in _resolve_wheel_pi_configs(common,*values)),expected)
        for invalid in (True,False,None,'-1','0.25',-2.,-.01,.375001,float('nan'),float('inf'),float('-inf')):
            for values in ((invalid,-1.),(-1.,invalid)):
                with self.subTest(values=values):
                    with self.assertRaisesRegex(ValueError,'feedforward_gain'):
                        _resolve_wheel_pi_configs(common,*values)

    def test_zero_target_still_resets_both_independent_controllers(self):
        controllers=[WheelSpeedPI(c) for c in _resolve_wheel_pi_configs(
            PIConfig(feedforward_gain=.25,max_duty_raw=4915),.2375,.2625)]
        for controller in controllers:
            for _ in range(20):controller.step(.4,.15,.05)
            result=controller.step(0.,0.,.05)
            self.assertEqual((result.duty_raw,result.integral,result.feedforward_output),(0,0.,0.))
            self.assertEqual((controller.output,controller.direction),(0.,0))


if __name__=='__main__':unittest.main()
