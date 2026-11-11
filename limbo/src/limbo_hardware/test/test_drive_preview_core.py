"""Target conversion tests requiring neither ROS nor a physical device."""
import math
import unittest

from limbo_hardware.drive_preview_core import calculate_drive_targets


class DrivePreviewCoreTests(unittest.TestCase):
    def targets(self, linear=0.0, angular=0.0, **overrides):
        geometry = dict(left_radius_m=0.075, right_radius_m=0.075,
                        wheel_separation_m=0.54,
                        left_counts_per_revolution=3688,
                        right_counts_per_revolution=3607)
        geometry.update(overrides)
        return calculate_drive_targets(linear, angular, **geometry)

    def test_zero_request_is_zero_on_both_wheels(self):
        result = self.targets()
        for wheel in (result.left, result.right):
            self.assertEqual(wheel.linear_m_s, 0.0)
            self.assertEqual(wheel.angular_rad_s, 0.0)
            self.assertEqual(wheel.counts_per_s, 0.0)

    def test_forward_uses_positive_wheel_convention_on_both_sides(self):
        result = self.targets(linear=0.15)
        self.assertAlmostEqual(result.left.angular_rad_s, 2.0)
        self.assertAlmostEqual(result.right.angular_rad_s, 2.0)
        self.assertAlmostEqual(result.left.counts_per_s, 3688 / math.pi)
        self.assertAlmostEqual(result.right.counts_per_s, 3607 / math.pi)
        self.assertGreater(result.left.counts_per_s, 0)
        self.assertGreater(result.right.counts_per_s, 0)

    def test_reverse_negates_every_wheel_quantity(self):
        forward = self.targets(linear=0.15)
        reverse = self.targets(linear=-0.15)
        for positive, negative in ((forward.left, reverse.left),
                                   (forward.right, reverse.right)):
            self.assertEqual(negative.linear_m_s, -positive.linear_m_s)
            self.assertEqual(negative.angular_rad_s, -positive.angular_rad_s)
            self.assertEqual(negative.counts_per_s, -positive.counts_per_s)

    def test_positive_yaw_turns_left_and_negative_yaw_turns_right(self):
        for angular, left_sign, right_sign in ((0.5, -1, 1), (-0.5, 1, -1)):
            with self.subTest(angular=angular):
                result = self.targets(angular=angular)
                self.assertAlmostEqual(result.left.linear_m_s, left_sign * 0.135)
                self.assertAlmostEqual(result.right.linear_m_s, right_sign * 0.135)
                self.assertGreater(result.left.counts_per_s * left_sign, 0)
                self.assertGreater(result.right.counts_per_s * right_sign, 0)

    def test_left_and_right_arcs_keep_inner_wheel_slower(self):
        left_arc = self.targets(linear=0.2, angular=0.5)
        right_arc = self.targets(linear=0.2, angular=-0.5)
        self.assertAlmostEqual(left_arc.left.linear_m_s, 0.065)
        self.assertAlmostEqual(left_arc.right.linear_m_s, 0.335)
        self.assertAlmostEqual(right_arc.left.linear_m_s, 0.335)
        self.assertAlmostEqual(right_arc.right.linear_m_s, 0.065)

    def test_tight_arc_can_reverse_inner_wheel(self):
        result = self.targets(linear=0.05, angular=0.5)
        self.assertAlmostEqual(result.left.linear_m_s, -0.085)
        self.assertAlmostEqual(result.right.linear_m_s, 0.185)
        self.assertLess(result.left.counts_per_s, 0)
        self.assertGreater(result.right.counts_per_s, 0)

    def test_each_side_uses_its_own_radius_and_counts_per_revolution(self):
        result = self.targets(linear=1.0,
                              left_radius_m=1 / math.tau,
                              right_radius_m=2 / math.tau,
                              left_counts_per_revolution=100,
                              right_counts_per_revolution=300)
        self.assertAlmostEqual(result.left.angular_rad_s, math.tau)
        self.assertAlmostEqual(result.right.angular_rad_s, math.pi)
        self.assertAlmostEqual(result.left.counts_per_s, 100)
        self.assertAlmostEqual(result.right.counts_per_s, 150)

    def test_count_targets_reconstruct_requested_body_velocity(self):
        geometry = dict(left_radius_m=0.08, right_radius_m=0.07,
                        wheel_separation_m=0.52,
                        left_counts_per_revolution=3688,
                        right_counts_per_revolution=3607)
        for linear in (-0.3, -0.1, 0.0, 0.1, 0.3):
            for angular in (-1.0, -0.25, 0.0, 0.25, 1.0):
                with self.subTest(linear=linear, angular=angular):
                    result = self.targets(linear, angular, **geometry)
                    left_speed = (result.left.counts_per_s / 3688
                                  * math.tau * 0.08)
                    right_speed = (result.right.counts_per_s / 3607
                                   * math.tau * 0.07)
                    self.assertAlmostEqual((left_speed + right_speed) / 2, linear)
                    self.assertAlmostEqual((right_speed - left_speed) / 0.52,
                                           angular)

    def test_nonfinite_body_velocity_is_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            for name in ('linear', 'angular'):
                with self.subTest(name=name, value=value):
                    with self.assertRaises(ValueError):
                        self.targets(**{name: value})

    def test_nonpositive_or_nonfinite_geometry_and_cpr_are_rejected(self):
        names = ('left_radius_m', 'right_radius_m', 'wheel_separation_m',
                 'left_counts_per_revolution', 'right_counts_per_revolution')
        for name in names:
            for value in (0.0, -0.01, math.nan, math.inf, -math.inf):
                with self.subTest(name=name, value=value):
                    with self.assertRaises(ValueError):
                        self.targets(**{name: value})

    def test_overflowing_derived_targets_are_rejected(self):
        cases = (
            dict(linear=1e308, angular=1e308, wheel_separation_m=4.0),
            dict(linear=1.0, left_radius_m=1e-320),
            dict(linear=1.0, left_counts_per_revolution=1e308),
        )
        for values in cases:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    self.targets(**values)


if __name__ == '__main__':
    unittest.main()
