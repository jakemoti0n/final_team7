"""Trailing encoder-count velocity with an exact interpolated time boundary.

Pure mathematics only. Counts are already unwrapped, forward-positive totals;
the caller owns serial, sample-interval and motion plausibility guards.
"""
from collections import deque
from dataclasses import dataclass
import math

VELOCITY_ESTIMATOR = 'exact_window_linear_v1'


def _finite(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} must be finite')


@dataclass(frozen=True)
class WindowSpeed:
    left_rad_s: float
    right_rad_s: float
    span_s: float
    window_start_s: float


class CountWindowEstimator:
    """Interpolate cumulative counts at now-window, never beyond observations.

    Before a full window exists, use all available time since the baseline.
    Keep one sample at/before the boundary and every sample after it. Count
    differences are formed before float conversion, preserving small deltas
    even when absolute signed totals are large.
    """
    def __init__(self, left_cpr, right_cpr, window_s=.20):
        for name, value in (('left_cpr', left_cpr), ('right_cpr', right_cpr)):
            _finite(name, value)
            if value <= 0:
                raise ValueError(f'{name} must be positive')
        _finite('velocity_window_s', window_s)
        if not .10 <= window_s <= .20:
            raise ValueError('velocity_window_s must be within 0.10..0.20 seconds')
        self._window_s = float(window_s)
        self._scales = (math.tau / left_cpr, math.tau / right_cpr)
        if not all(math.isfinite(value) for value in self._scales):
            raise ValueError('CPR produces nonfinite scale')
        self._samples = deque()

    @property
    def window_s(self):
        return self._window_s

    def update(self, monotonic_s, left_total, right_total):
        _finite('monotonic_s', monotonic_s)
        for value in (left_total, right_total):
            if type(value) is not int or not -(2**63) <= value < 2**63:
                raise ValueError('Count totals must be signed 64-bit integers')
        row = (float(monotonic_s), left_total, right_total)
        if self._samples and row[0] <= self._samples[-1][0]:
            raise ValueError('Count timestamps must strictly increase')
        if not self._samples:
            self._samples.append(row)
            return None

        # Compute in locals so rejected input cannot partially change history.
        samples = list(self._samples) + [row]
        cutoff = max(samples[0][0], row[0] - self._window_s)
        span = row[0] - cutoff
        if not math.isfinite(span) or span <= 0:
            raise ValueError('Empty or unrepresentable count velocity window')
        index = 0
        while index + 1 < len(samples) and samples[index + 1][0] <= cutoff:
            index += 1
        old, following = samples[index], samples[index + 1]
        fraction = (cutoff - old[0]) / (following[0] - old[0])
        delta = tuple((row[i] - old[i]) - fraction * (following[i] - old[i])
                      for i in (1, 2))
        velocity = tuple(value * scale / span for value, scale in zip(delta, self._scales))
        if not all(math.isfinite(value) for value in (*velocity, span, cutoff)) or span <= 0:
            raise ValueError('Nonfinite or empty count velocity window')
        self._samples = deque(samples[index:])
        return WindowSpeed(velocity[0], velocity[1], span, cutoff)
