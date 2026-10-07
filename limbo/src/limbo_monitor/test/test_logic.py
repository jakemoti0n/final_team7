"""ROS 없이 도는 스캔 이동 추정과 헛돎 판단 테스트."""

import math

from limbo_monitor import scan_motion, slip
import numpy as np

ANGLES = np.linspace(-math.pi, math.pi, 720, endpoint=False)


def _ray_box(px, py, angle, x0, y0, x1, y1):
    """(px, py)에서 angle 방향 광선이 직사각형 벽 안쪽에 닿는 거리."""
    dx, dy = math.cos(angle), math.sin(angle)
    hits = []
    if abs(dx) > 1e-9:
        hits += [(x - px) / dx for x in (x0, x1)]
    if abs(dy) > 1e-9:
        hits += [(y - py) / dy for y in (y0, y1)]
    return min(t for t in hits if t > 1e-9)


def _scan(px, py, yaw, room):
    ranges = [_ray_box(px, py, yaw + a, *room) for a in ANGLES]
    return scan_motion.scan_to_points(ranges, ANGLES[0], ANGLES[1] - ANGLES[0], 0.1, 30.0)


ROOM = (-4.0, -3.0, 6.0, 2.5)          # 10m × 5.5m 방
CORRIDOR = (-40.0, -0.9, 40.0, 0.9)    # 80m 직선 복도


def test_estimates_forward_motion_in_room():
    prev = _scan(0.0, 0.0, 0.0, ROOM)
    cur = _scan(0.20, 0.0, 0.0, ROOM)
    m = scan_motion.estimate_motion(prev, cur, scan_motion.IcpConfig())

    assert abs(m.dx - 0.20) < 0.01
    assert abs(m.dy) < 0.01
    assert abs(m.dyaw) < 0.01
    assert m.forward_constraint > 0.1


def test_estimates_rotation_and_sideways_motion():
    prev = _scan(1.0, 0.5, 0.3, ROOM)
    cur = _scan(1.0 + 0.1 * math.cos(0.3), 0.5 + 0.1 * math.sin(0.3), 0.4, ROOM)
    m = scan_motion.estimate_motion(prev, cur, scan_motion.IcpConfig())

    assert abs(m.dx - 0.10) < 0.01
    assert abs(m.dyaw - 0.1) < 0.01


def test_long_corridor_has_no_forward_constraint():
    prev = _scan(0.0, 0.0, 0.0, CORRIDOR)
    cur = _scan(0.20, 0.0, 0.0, CORRIDOR)
    m = scan_motion.estimate_motion(prev, cur, scan_motion.IcpConfig())

    assert m.forward_constraint < 0.1


def _motion(dx, constraint=0.5):
    return scan_motion.MotionEstimate(dx, 0.0, 0.0, constraint, 1.0)


def test_slip_needs_consecutive_windows():
    detector = slip.SlipDetector(slip.SlipConfig(consecutive_windows=2))

    assert detector.update(0.2, 0.0, _motion(0.0)) == slip.SUSPECT
    assert detector.update(0.2, 0.0, _motion(0.0)) == slip.SLIP


def test_real_motion_resets_suspicion():
    detector = slip.SlipDetector(slip.SlipConfig(consecutive_windows=2))

    detector.update(0.2, 0.0, _motion(0.0))
    assert detector.update(0.2, 0.0, _motion(0.19)) == slip.OK
    assert detector.update(0.2, 0.0, _motion(0.0)) == slip.SUSPECT


def test_unknown_in_corridor_and_slow_motion_is_ok():
    detector = slip.SlipDetector(slip.SlipConfig())

    assert detector.update(0.2, 0.0, _motion(0.0, constraint=0.01)) == slip.UNKNOWN
    assert detector.update(0.2, 0.0, None) == slip.UNKNOWN
    assert detector.update(0.05, 0.0, _motion(0.0)) == slip.OK
