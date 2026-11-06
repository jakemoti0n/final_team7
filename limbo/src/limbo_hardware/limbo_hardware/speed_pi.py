"""Bounded wheel-speed PI mathematics; no ROS, serial, or device access.

Speeds use wheel-forward-positive rad/s and outputs use signed duty fraction.
Encoder channel polarity belongs to the caller, never to this controller.
"""
from dataclasses import dataclass
import math

CONTROLLER_MODEL = 'partial_headroom_feedforward_v2'


def _finite(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')


@dataclass(frozen=True)
class PIConfig:
    kp: float = 0.10
    ki: float = 0.20
    max_duty_raw: int = 3276
    target_slew_rad_s2: float = 0.4
    output_slew_per_s: float = 0.15
    min_dt: float = 0.02
    max_dt: float = 0.15
    max_target_rad_s: float = 0.4
    feedforward_gain: float = 0.0
    # Optional forward (rad/s, duty fraction) anchors; reverse keeps the signed gain.
    forward_curve: tuple = ()

    def __post_init__(self):
        for name in ('kp', 'ki', 'target_slew_rad_s2', 'output_slew_per_s',
                     'min_dt', 'max_dt', 'max_target_rad_s', 'feedforward_gain'):
            value = getattr(self, name)
            _finite(name, value)
            invalid_sign = value < 0 if name in ('kp', 'ki', 'feedforward_gain') else value <= 0
            if invalid_sign:
                raise ValueError(f'{name} has an invalid sign')
        if self.forward_curve:
            if len(self.forward_curve) != 4:
                raise ValueError('forward_curve requires two speed/duty pairs')
            slow, slow_duty, fast, fast_duty = self.forward_curve
            for value in self.forward_curve:
                _finite('forward_curve', value)
            if not (0 < slow < fast and 0 < slow_duty <= fast_duty <= 1):
                raise ValueError('forward_curve needs increasing speeds and ordered positive duties')
        if self.kp == 0 and self.ki == 0:
            raise ValueError('At least one PI gain must be positive')
        if self.feedforward_gain > .375:
            raise ValueError('feedforward_gain must be within 0..0.375')
        # 물리 최대 32767. 벤치의 15 %(4915)·주행의 30 % 천장은 각 transport가 따로 검증한다
        if type(self.max_duty_raw) is not int or not 1 <= self.max_duty_raw <= 32767:
            raise ValueError('max_duty_raw must be an integer in 1..32767')
        if not 0.02 <= self.min_dt <= self.max_dt <= 0.15:
            raise ValueError('The dt interval must stay inside 0.02..0.15 seconds')


@dataclass(frozen=True)
class PIResult:
    requested_rad_s: float
    ramped_rad_s: float
    measured_rad_s: float
    error_rad_s: float
    integral: float
    unconstrained_output: float
    output: float
    duty_raw: int
    saturated: bool
    rate_limited: bool
    integral_limited: bool = False
    integral_partial: bool = False
    feedforward_output: float = 0.0


def _clip(value, lower, upper):
    return min(upper, max(lower, value))


class WheelSpeedPI:
    """One wheel's PI state. A valid zero command separates opposite directions.

    Saturation includes duty and output-rate bounds. A candidate integral step
    may use remaining headroom, but never moves farther than the ordinary step
    or in its opposite direction. A zero target immediately clears all state.
    """

    def __init__(self, config=PIConfig()):
        if not isinstance(config, PIConfig):
            raise TypeError('config must be PIConfig')
        self.config = config
        self.reset()

    def reset(self):
        self.integral = 0.0
        self.ramped_rad_s = 0.0
        self.output = 0.0
        self.direction = 0

    def step(self, target_rad_s, measured_rad_s, dt, *, forward_rise_scale=1.0):
        c = self.config
        for name, value in (('target_rad_s', target_rad_s),
                            ('measured_rad_s', measured_rad_s), ('dt', dt)):
            _finite(name, value)
        _finite('forward_rise_scale', forward_rise_scale)
        if not 0.0 <= forward_rise_scale <= 1.0:
            raise ValueError('forward_rise_scale must be in [0, 1]')
        if not c.min_dt <= dt <= c.max_dt:
            raise ValueError('dt outside the configured interval')
        if abs(target_rad_s) > c.max_target_rad_s:
            raise ValueError('Target exceeds the configured trial speed')
        if target_rad_s == 0:
            self.reset()
            return PIResult(0.0, 0.0, float(measured_rad_s), -float(measured_rad_s),
                            0.0, 0.0, 0.0, 0, False, False)
        direction = 1 if target_rad_s > 0 else -1
        if self.direction and direction != self.direction:
            raise ValueError('A zero command is required before a direction reversal')

        # Compute in locals so rejected/overflowing updates cannot corrupt state.
        ramp_delta = c.target_slew_rad_s2 * dt
        ramped = self.ramped_rad_s + _clip(
            target_rad_s - self.ramped_rad_s, -ramp_delta, ramp_delta)
        error = ramped - measured_rad_s
        feedforward = c.feedforward_gain * ramped
        if ramped > 0 and c.forward_curve:
            slow, slow_duty, fast, fast_duty = c.forward_curve
            if ramped <= slow:
                feedforward = slow_duty * ramped / slow
            else:
                fraction = min(1.0, (ramped - slow) / (fast - slow))
                feedforward = slow_duty + fraction * (fast_duty - slow_duty)
            feedforward = min(feedforward, c.max_duty_raw / 32767.0)
        base = feedforward + c.kp * error
        proposed_integral = self.integral + c.ki * error * dt
        cap = c.max_duty_raw / 32767.0
        duty_lower, duty_upper = (0.0, cap) if direction > 0 else (-cap, 0.0)
        slew_delta = c.output_slew_per_s * dt
        lower = max(duty_lower, self.output - slew_delta)
        rise = slew_delta * forward_rise_scale if direction > 0 else slew_delta
        upper = min(duty_upper, self.output + rise)
        proposed_raw = base + proposed_integral
        if not all(math.isfinite(v) for v in (ramped, error, feedforward, base, proposed_integral, proposed_raw)):
            raise ValueError('PI calculation overflow')
        proposed_limited = _clip(proposed_raw, lower, upper)
        # A product could itself overflow; compare signs instead.
        excess = proposed_raw - proposed_limited
        pushes_into_limit = (excess > 0 and error > 0) or (excess < 0 and error < 0)
        integral = proposed_integral
        if pushes_into_limit:
            # Admit the portion of the ordinary integration step that fits. If
            # FF+P is beyond the bound, do not back-calculate an integral in
            # the opposite direction merely to force the output onto that bound.
            boundary = upper if excess > 0 else lower
            available_integral = boundary - base
            if error > 0:
                integral = max(self.integral, min(proposed_integral, available_integral))
            else:
                integral = min(self.integral, max(proposed_integral, available_integral))
        integral_limited = integral != proposed_integral
        integral_partial = integral_limited and integral != self.integral
        unconstrained = base + integral
        if not math.isfinite(unconstrained):
            raise ValueError('PI calculation overflow')
        duty_limited = _clip(unconstrained, duty_lower, duty_upper)
        limited = _clip(duty_limited, lower, upper)
        raw = int(round(limited * 32767.0))
        raw = max(-c.max_duty_raw, min(c.max_duty_raw, raw))
        output = raw / 32767.0
        self.integral, self.ramped_rad_s = integral, ramped
        self.output, self.direction = output, direction
        return PIResult(float(target_rad_s), ramped, float(measured_rad_s), error,
                        integral, unconstrained, output, raw,
                        unconstrained != duty_limited, duty_limited != limited,
                        integral_limited, integral_partial, feedforward)
