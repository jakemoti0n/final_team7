"""Differential-drive target preview, with no ROS, serial or motor access."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class WheelTarget:
    """Requested wheel motion in the forward-positive wheel convention."""

    linear_m_s: float
    angular_rad_s: float
    counts_per_s: float


@dataclass(frozen=True)
class DriveTargets:
    left: WheelTarget
    right: WheelTarget


def calculate_drive_targets(
        linear_m_s: float, angular_rad_s: float, *,
        left_radius_m: float, right_radius_m: float,
        wheel_separation_m: float, left_counts_per_revolution: float,
        right_counts_per_revolution: float) -> DriveTargets:
    """Convert body velocity to unrounded wheel targets for observation only.

    Positive body angular velocity turns left. Both wheel targets are positive
    for forward motion; raw encoder polarity and controller channel commands
    are deliberately outside this calculation. Targets are neither measured
    speeds nor proof that a controller can track the requested speeds.
    """
    for name, value in dict(linear_m_s=linear_m_s,
                            angular_rad_s=angular_rad_s).items():
        if not math.isfinite(value):
            raise ValueError(f'{name} must be finite')
    geometry = dict(
        left_radius_m=left_radius_m, right_radius_m=right_radius_m,
        wheel_separation_m=wheel_separation_m,
        left_counts_per_revolution=left_counts_per_revolution,
        right_counts_per_revolution=right_counts_per_revolution)
    for name, value in geometry.items():
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f'{name} must be finite and positive')

    turn_speed = angular_rad_s * (wheel_separation_m / 2.0)

    def wheel_target(speed, radius, counts_per_revolution):
        angular = speed / radius
        counts = angular / math.tau * counts_per_revolution
        if not all(math.isfinite(value) for value in (speed, angular, counts)):
            raise ValueError('Calculated wheel targets must be finite')
        return WheelTarget(speed, angular, counts)

    return DriveTargets(
        left=wheel_target(linear_m_s - turn_speed, left_radius_m,
                          left_counts_per_revolution),
        right=wheel_target(linear_m_s + turn_speed, right_radius_m,
                           right_counts_per_revolution))
