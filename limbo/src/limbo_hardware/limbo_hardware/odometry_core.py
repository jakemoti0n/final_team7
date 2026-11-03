"""Wheel-count integration with explicit discontinuities; no ROS or device access."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class CountSample:
    stamp_ns: int
    session_id: str
    sequence: int
    baseline: bool
    right_delta: int
    left_delta: int
    right_total: int
    left_total: int


@dataclass(frozen=True)
class Estimate:
    stamp_ns: int
    x: float
    y: float
    yaw: float
    vx: float
    wz: float
    dt: float
    left_distance: float
    right_distance: float
    position_variance: float
    yaw_variance: float


class WheelOdometry:
    """Integrate only consecutive trustworthy intervals, retaining pose on rebases.

    A restart of this object starts a new odom origin. Encoder reconnects instead
    preserve its existing pose and omit motion across the unavailable interval.
    Covariance is an explicit provisional budget, not a calibrated noise model.
    """

    def __init__(self, *, left_radius, right_radius, separation,
                 left_cpr, right_cpr, max_dt=0.5, max_age=0.5,
                 future_tolerance=0.05, initial_position_variance=0.0025,
                 initial_yaw_variance=0.01, position_variance_per_meter=0.01,
                 yaw_variance_per_meter=0.02, gap_position_variance=0.25,
                 gap_yaw_variance=0.25):
        positive = dict(left_radius=left_radius, right_radius=right_radius,
                        separation=separation, left_cpr=left_cpr, right_cpr=right_cpr,
                        max_dt=max_dt, max_age=max_age,
                        initial_position_variance=initial_position_variance,
                        initial_yaw_variance=initial_yaw_variance,
                        gap_position_variance=gap_position_variance,
                        gap_yaw_variance=gap_yaw_variance)
        for name, value in positive.items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive')
        for name, value in dict(future_tolerance=future_tolerance,
                                position_variance_per_meter=position_variance_per_meter,
                                yaw_variance_per_meter=yaw_variance_per_meter).items():
            if not math.isfinite(value) or value < 0:
                raise ValueError(f'{name} must be finite and nonnegative')
        self.left_scale = 2.0 * math.pi * left_radius / left_cpr
        self.right_scale = 2.0 * math.pi * right_radius / right_cpr
        if not all(math.isfinite(value) and value > 0 for value in
                   (self.left_scale, self.right_scale, 1.0 / separation)):
            raise ValueError('Derived wheel scales and inverse separation must be finite and positive')
        self.separation = separation
        self.max_dt, self.max_age = max_dt, max_age
        self.future_tolerance = future_tolerance
        self.position_variance = initial_position_variance
        self.yaw_variance = initial_yaw_variance
        self.position_variance_per_meter = position_variance_per_meter
        self.yaw_variance_per_meter = yaw_variance_per_meter
        self.gap_position_variance = gap_position_variance
        self.gap_yaw_variance = gap_yaw_variance
        self.x = self.y = self.yaw = 0.0
        self.reference = None
        self.retired_sessions = set()
        self.force_rebase = False
        self.status = 'waiting_for_input'
        self.accepted = False
        self.integrated_intervals = self.rebases = self.rejected = 0

    def invalidate(self, reason='stale_input'):
        self.force_rebase = True
        self.status = reason

    def _reject(self, reason, invalidate=False):
        self.accepted = False
        self.rejected += 1
        self.status = reason
        if invalidate:
            self.force_rebase = True
        return None

    def _baseline(self, sample, reason):
        if self.reference is not None:
            position_variance = self.position_variance + self.gap_position_variance
            yaw_variance = self.yaw_variance + self.gap_yaw_variance
            if not all(math.isfinite(value) for value in (position_variance, yaw_variance)):
                return self._reject('nonfinite_covariance', invalidate=True)
            self.rebases += 1
            self.position_variance = position_variance
            self.yaw_variance = yaw_variance
            if sample.session_id != self.reference.session_id:
                self.retired_sessions.add(self.reference.session_id)
        self.reference = sample
        self.force_rebase = False
        self.accepted = True
        self.status = reason
        return None

    @staticmethod
    def _valid_sample(sample):
        if not isinstance(sample.session_id, str) or not sample.session_id:
            return False
        if type(sample.baseline) is not bool:
            return False
        for field in ('stamp_ns', 'sequence', 'right_delta', 'left_delta',
                      'right_total', 'left_total'):
            if type(getattr(sample, field)) is not int:
                return False
        if sample.stamp_ns <= 0 or not 0 <= sample.sequence < 2**64:
            return False
        if any(not -2**63 <= getattr(sample, name) < 2**63 for name in
               ('right_delta', 'left_delta', 'right_total', 'left_total')):
            return False
        if sample.baseline and (sample.sequence != 0 or any(getattr(sample, name)
                for name in ('right_delta', 'left_delta', 'right_total', 'left_total'))):
            return False
        return True

    def update(self, sample, now_ns):
        self.accepted = False
        if not self._valid_sample(sample) or type(now_ns) is not int:
            return self._reject('invalid_sample', invalidate=True)
        previous = self.reference
        if sample.session_id in self.retired_sessions:
            return self._reject('retired_session')
        if previous and sample.session_id == previous.session_id:
            if sample.sequence <= previous.sequence:
                return self._reject('duplicate_or_out_of_order')
        age = (now_ns - sample.stamp_ns) / 1e9
        if age > self.max_age:
            return self._reject('stale_sample', invalidate=True)
        if age < -self.future_tolerance:
            return self._reject('future_sample', invalidate=True)
        if previous is None:
            return self._baseline(sample, 'initial_reference')
        if sample.session_id != previous.session_id:
            return self._baseline(sample, 'session_changed')
        if self.force_rebase:
            return self._baseline(sample, 'recovered_after_unavailable_input')
        if sample.baseline:
            return self._baseline(sample, 'new_baseline')
        if sample.sequence != previous.sequence + 1:
            return self._baseline(sample, 'sequence_gap')
        dt = (sample.stamp_ns - previous.stamp_ns) / 1e9
        if not 0 < dt <= self.max_dt:
            return self._baseline(sample, 'time_discontinuity')
        if (sample.right_total - previous.right_total != sample.right_delta or
                sample.left_total - previous.left_total != sample.left_delta):
            return self._baseline(sample, 'inconsistent_count_delta')

        dl = sample.left_delta * self.left_scale
        dr = sample.right_delta * self.right_scale
        ds = (dl + dr) / 2.0
        dtheta = (dr - dl) / self.separation
        if not all(math.isfinite(value) for value in (dl, dr, ds, dtheta)):
            return self._reject('nonfinite_motion', invalidate=True)
        half = dtheta / 2.0
        sinc = 1.0 - half * half / 6.0 if abs(half) < 1e-6 else math.sin(half) / half
        heading = self.yaw + half
        x = self.x + ds * sinc * math.cos(heading)
        y = self.y + ds * sinc * math.sin(heading)
        yaw = math.atan2(math.sin(self.yaw + dtheta), math.cos(self.yaw + dtheta))
        travel = (abs(dl) + abs(dr)) / 2.0
        position_variance = self.position_variance + self.position_variance_per_meter * travel
        yaw_variance = self.yaw_variance + self.yaw_variance_per_meter * travel
        vx, wz = ds / dt, dtheta / dt
        if not all(math.isfinite(value) for value in
                   (x, y, yaw, position_variance, yaw_variance, vx, wz)):
            return self._reject('nonfinite_estimate', invalidate=True)
        self.x, self.y, self.yaw = x, y, yaw
        self.position_variance, self.yaw_variance = position_variance, yaw_variance
        self.reference = sample
        self.accepted = True
        self.status = 'integrated'
        self.integrated_intervals += 1
        return Estimate(sample.stamp_ns, self.x, self.y, self.yaw,
                        vx, wz, dt, dl, dr,
                        self.position_variance, self.yaw_variance)
