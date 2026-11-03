#!/usr/bin/env python3
"""Validate raw LiDAR clouds and optionally remove an explicit body envelope.

The pure parser and time gate import without ROS. Output keeps every finite,
nonzero XYZ point, its complete point record, original field layout and header.
Row padding is removed when the result is flattened to an unorganized cloud.
The optional axis-aligned box needs confirmed sensor-frame mounting geometry;
it is not a URDF self-filter and does not track moving lids or appendages.
No voxel reduction, point cap, extrinsic transform or motor interface is used.
"""

from collections import Counter
from dataclasses import dataclass
import json
import math
import signal
import time

import numpy as np


MAX_AGE_NS = 500_000_000
MAX_FUTURE_NS = 50_000_000
FIELD_SIZES = {1: 1, 2: 1, 3: 2, 4: 2, 5: 4, 6: 4, 7: 4, 8: 8}


class CloudRejected(ValueError):
    """Expected input rejection with a stable diagnostic reason."""

    def __init__(self, reason, detail=''):
        self.reason = reason
        super().__init__(detail or reason)


@dataclass(frozen=True)
class FilteredCloud:
    data: bytes
    width: int
    row_step: int
    input_points: int
    nonfinite_points: int
    zero_points: int


@dataclass(frozen=True)
class BodyFilteredCloud:
    data: bytes
    width: int
    row_step: int
    removed_points: int


def _cloud_views(data, width, height, point_step, row_step, is_bigendian, fields):
    """Validate a cloud and expose XYZ plus complete point-record byte views."""
    dimensions = (width, height, point_step, row_step)
    if any(isinstance(n, bool) or not isinstance(n, int) for n in dimensions):
        raise CloudRejected('invalid_layout', 'cloud dimensions must be integers')
    if width < 0 or height < 1 or point_step < 1 or row_step < width * point_step:
        raise CloudRejected('invalid_layout', 'invalid dimensions or strides')
    if not isinstance(is_bigendian, bool):
        raise CloudRejected('invalid_layout', 'endianness must be boolean')
    try:
        buffer = memoryview(data)
    except TypeError as error:
        raise CloudRejected('invalid_layout', 'data must be a byte buffer') from error
    if not buffer.c_contiguous or buffer.nbytes != row_step * height:
        raise CloudRejected('invalid_layout', 'data length/stride mismatch')

    offsets = {}
    seen_names = set()
    if not isinstance(fields, (list, tuple)):
        raise CloudRejected('invalid_layout', 'fields must be a sequence')
    for field in fields:
        if not isinstance(field, (list, tuple)) or len(field) != 4:
            raise CloudRejected('invalid_layout', 'malformed field declaration')
        name, offset, datatype, count = field
        if (not isinstance(name, str) or not name or name in seen_names
                or any(isinstance(n, bool) or not isinstance(n, int)
                       for n in (offset, datatype, count))
                or datatype not in FIELD_SIZES or count < 1 or offset < 0
                or offset + FIELD_SIZES[datatype] * count > point_step):
            raise CloudRejected('invalid_layout', 'invalid or duplicate field')
        seen_names.add(name)
        if name in ('x', 'y', 'z'):
            if datatype != 7 or count != 1:
                raise CloudRejected('invalid_layout', 'XYZ must be scalar float32')
            offsets[name] = offset
    if set(offsets) != {'x', 'y', 'z'}:
        raise CloudRejected('invalid_layout', 'XYZ fields missing')
    ordered_offsets = sorted(offsets.values())
    if any(b < a + 4 for a, b in zip(ordered_offsets, ordered_offsets[1:])):
        raise CloudRejected('invalid_layout', 'XYZ fields overlap')

    total = width * height
    if total == 0:
        return (np.empty((height, 0, point_step), dtype=np.uint8),
                [np.empty((height, 0), dtype=np.float32) for _ in range(3)])
    float_dtype = '>f4' if is_bigendian else '<f4'
    coords = [np.ndarray((height, width), dtype=float_dtype, buffer=buffer,
                         offset=offsets[name], strides=(row_step, point_step))
              for name in ('x', 'y', 'z')]
    records = np.ndarray((height, width, point_step), dtype=np.uint8,
                         buffer=buffer, strides=(row_step, point_step, 1))
    return records, coords


def filter_pointcloud_bytes(data, width, height, point_step, row_step,
                            is_bigendian, fields):
    """Pack finite, nonzero points; fields are (name, offset, type, count).

    Supports organized clouds, row padding, either byte order and arbitrary XYZ
    offsets. Empty input and empty filtered results do not establish free space.
    Non-XYZ fields and per-point padding are not changed.
    """
    records, coords = _cloud_views(
        data, width, height, point_step, row_step, is_bigendian, fields)
    total = width * height
    finite = np.isfinite(coords[0]) & np.isfinite(coords[1]) & np.isfinite(coords[2])
    zero = finite & (coords[0] == 0) & (coords[1] == 0) & (coords[2] == 0)
    keep = finite & ~zero
    kept = int(np.count_nonzero(keep))
    return FilteredCloud(records[keep].tobytes(), kept, kept * point_step,
                         total, int(total - np.count_nonzero(finite)),
                         int(np.count_nonzero(zero)))


def validate_body_bounds(body_min, body_max):
    """Validate explicit sensor-frame bounds; no physical defaults are inferred."""
    result = []
    for name, values in (('body_min', body_min), ('body_max', body_max)):
        if isinstance(values, (str, bytes)):
            raise ValueError(f'{name} must contain three finite numbers')
        try:
            values = tuple(values)
        except TypeError as error:
            raise ValueError(f'{name} must contain three finite numbers') from error
        if (len(values) != 3 or any(isinstance(v, bool) or not isinstance(v, (int, float))
                                   or not math.isfinite(v) for v in values)):
            raise ValueError(f'{name} must contain three finite numbers')
        result.append(tuple(float(v) for v in values))
    if any(low >= high for low, high in zip(*result)):
        raise ValueError('body_min must be strictly below body_max on every axis')
    return tuple(result)


def filter_body_box_bytes(data, width, point_step, is_bigendian, fields,
                          body_min, body_max):
    """Remove the inclusive configured box from already-valid packed points.

    Only points inside all three bounds are removed; all outside points retain
    their full original records, including points above/below the box. Padding
    belongs in explicit bounds supplied by the caller, not in this function.
    """
    minimum, maximum = validate_body_bounds(body_min, body_max)
    records, coords = _cloud_views(
        data, width, 1, point_step, width * point_step, is_bigendian, fields)
    finite = np.isfinite(coords[0]) & np.isfinite(coords[1]) & np.isfinite(coords[2])
    zero = (coords[0] == 0) & (coords[1] == 0) & (coords[2] == 0)
    if not finite.all() or zero.any():
        raise CloudRejected('invalid_body_input', 'body filter requires valid XYZ input')
    inside = np.ones((1, width), dtype=bool)
    for coordinate, low, high in zip(coords, minimum, maximum):
        # Compare decoded float32 coordinates to the supplied double bounds;
        # do not round the geometric boundary down to float32 implicitly.
        values = coordinate.astype(np.float64)
        inside &= (values >= low) & (values <= high)
    removed = int(np.count_nonzero(inside))
    kept = width - removed
    return BodyFilteredCloud(records[~inside].tobytes(), kept,
                             kept * point_step, removed)


def stamp_nanoseconds(sec, nanosec):
    if (any(isinstance(n, bool) or not isinstance(n, int) for n in (sec, nanosec))
            or sec < 0 or not 0 <= nanosec < 1_000_000_000):
        raise CloudRejected('invalid_stamp')
    stamp = sec * 1_000_000_000 + nanosec
    if stamp == 0:
        raise CloudRejected('invalid_stamp')
    return stamp


class FreshnessGate:
    """Check twice, and commit only after publication succeeds.

    Rejected input never advances the watermark, so a far-future malformed
    message cannot prevent subsequent valid data from being published.
    """

    def __init__(self, expected_frame):
        if not isinstance(expected_frame, str) or not expected_frame:
            raise ValueError('expected_frame must be a nonempty string')
        self.expected_frame = expected_frame
        self.last_published_stamp = None

    def check(self, stamp, frame_id, now_ns, after_processing=False):
        if isinstance(stamp, bool) or not isinstance(stamp, int) or stamp <= 0:
            raise CloudRejected('invalid_stamp')
        if frame_id != self.expected_frame:
            raise CloudRejected('frame_mismatch')
        age_ns = now_ns - stamp
        if age_ns < -MAX_FUTURE_NS:
            raise CloudRejected('future_after_processing' if after_processing else 'future')
        if age_ns > MAX_AGE_NS:
            raise CloudRejected('stale_after_processing' if after_processing else 'stale')
        if self.last_published_stamp is not None:
            if stamp == self.last_published_stamp:
                raise CloudRejected('duplicate_stamp')
            if stamp < self.last_published_stamp:
                raise CloudRejected('reversed_stamp')
        return age_ns

    def commit(self, stamp):
        if self.last_published_stamp is not None and stamp <= self.last_published_stamp:
            raise ValueError('publication watermark must increase')
        self.last_published_stamp = stamp


def cleanup_ros_resources(executor, node, shutdown_context):
    """Finish cleanup despite launch forwarding a second SIGINT.

    Only SIGINT is temporarily ignored. Executor waiting is limited to two
    seconds; the launch/supervisor retains its SIGTERM/SIGKILL process deadline
    for any middleware cleanup that does not return.
    """
    previous_sigint = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        try:
            executor.shutdown(timeout_sec=2.0)
        finally:
            try:
                if node is not None:
                    node.destroy_node()
            finally:
                shutdown_context()
    finally:
        signal.signal(signal.SIGINT, previous_sigint)


def main(args=None):
    # ROS imports stay here so parser/time-boundary tests run without ROS.
    import rclpy
    from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    from rcl_interfaces.msg import ParameterDescriptor
    from sensor_msgs.msg import PointCloud2
    from std_msgs.msg import String

    class LidarCloudGuard(Node):
        def __init__(self):
            super().__init__('lidar_cloud_guard')
            for name, default in (
                    ('expected_frame', 'mid360_link'), ('body_filter_enabled', False),
                    ('body_min', [0.0, 0.0, 0.0]), ('body_max', [0.0, 0.0, 0.0])):
                self.declare_parameter(name, default, ParameterDescriptor(read_only=True))
            self.gate = FreshnessGate(self.get_parameter('expected_frame').value)
            self.body_bounds = None
            if self.get_parameter('body_filter_enabled').value:
                # Invalid/missing geometry fails before any publisher is made.
                self.body_bounds = validate_body_bounds(
                    self.get_parameter('body_min').value,
                    self.get_parameter('body_max').value)
            qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=1,
                             reliability=ReliabilityPolicy.BEST_EFFORT,
                             durability=DurabilityPolicy.VOLATILE)
            self.cloud_pub = self.create_publisher(PointCloud2, '/mid360/points_valid', qos)
            self.body_pub = (self.create_publisher(PointCloud2, '/mid360/points_filtered', qos)
                             if self.body_bounds is not None else None)
            self.status_pub = self.create_publisher(String, '/mid360/input_status', 5)
            self.subscription = self.create_subscription(
                PointCloud2, '/mid360/points', self.cloud_callback, qos)
            self.counts = Counter()
            self.rejections = Counter()
            self.last_detail = None
            self.last_receive_mono = None
            self.last_publish_mono = None
            self.last_callback_ms = None
            self.max_callback_ms = 0.0
            self.last_arrival_age_ms = None
            self.last_publish_age_ms = None
            self.timer = self.create_timer(1.0, self.publish_status)

        def cloud_callback(self, message):
            began = time.monotonic_ns()
            self.last_receive_mono = began
            self.counts['received'] += 1
            try:
                stamp = stamp_nanoseconds(message.header.stamp.sec, message.header.stamp.nanosec)
                now = self.get_clock().now().nanoseconds
                self.last_arrival_age_ms = (now - stamp) / 1_000_000
                self.gate.check(stamp, message.header.frame_id, now)
                fields = [(f.name, f.offset, f.datatype, f.count) for f in message.fields]
                result = filter_pointcloud_bytes(
                    message.data, message.width, message.height, message.point_step,
                    message.row_step, message.is_bigendian,
                    fields)
                self.counts['parsed_input_points'] += result.input_points
                self.counts['removed_nonfinite_points'] += result.nonfinite_points
                self.counts['removed_zero_points'] += result.zero_points
                output = PointCloud2()
                output.header = message.header
                output.height = 1
                output.width = result.width
                output.fields = message.fields
                output.is_bigendian = message.is_bigendian
                output.point_step = message.point_step
                output.row_step = result.row_step
                output.data = result.data
                output.is_dense = True  # Every retained XYZ coordinate is finite.
                body_result = None
                body_output = None
                if self.body_bounds is not None:
                    body_result = filter_body_box_bytes(
                        result.data, result.width, message.point_step,
                        message.is_bigendian, fields, *self.body_bounds)
                    body_output = PointCloud2()
                    body_output.header = message.header
                    body_output.height = 1
                    body_output.width = body_result.width
                    body_output.fields = message.fields
                    body_output.is_bigendian = message.is_bigendian
                    body_output.point_step = message.point_step
                    body_output.row_step = body_result.row_step
                    body_output.data = body_result.data
                    body_output.is_dense = True
                # Both messages are fully prepared before the final age gate.
                now = self.get_clock().now().nanoseconds
                self.last_publish_age_ms = self.gate.check(
                    stamp, message.header.frame_id, now, after_processing=True) / 1_000_000
                self.cloud_pub.publish(output)
                if body_output is not None:
                    self.body_pub.publish(body_output)
                    self.counts['body_removed_points'] += body_result.removed_points
                    self.counts['body_filtered_published'] += 1
                    self.counts['body_filtered_points'] += body_result.width
                    self.counts['body_empty_published'] += int(body_result.width == 0)
                self.gate.commit(stamp)
                self.last_publish_mono = time.monotonic_ns()
                self.counts['published'] += 1
                self.counts['published_points'] += result.width
                self.counts['empty_published'] += int(result.width == 0)
            except CloudRejected as error:
                self.counts['rejected'] += 1
                self.rejections[error.reason] += 1
                self.last_detail = str(error)
            finally:
                self.last_callback_ms = (time.monotonic_ns() - began) / 1_000_000
                self.max_callback_ms = max(self.max_callback_ms, self.last_callback_ms)

        def publish_status(self):
            now = time.monotonic_ns()
            since = lambda value: None if value is None else (now - value) / 1_000_000_000
            status = {
                'scope': ('valid XYZ plus configured static body box; no TF, downsampling or navigation'
                          if self.body_bounds is not None else
                          'sensor-frame valid XYZ only; no body mask, TF, downsampling or navigation'),
                'expected_frame': self.gate.expected_frame,
                'body_filter_enabled': self.body_bounds is not None,
                'body_min': self.body_bounds[0] if self.body_bounds is not None else None,
                'body_max': self.body_bounds[1] if self.body_bounds is not None else None,
                'body_filter_note': 'Inclusive sensor-frame box; fixed startup config; not a full URDF self-filter.',
                'max_age_ms': MAX_AGE_NS / 1_000_000,
                'max_future_ms': MAX_FUTURE_NS / 1_000_000,
                'counts': dict(self.counts),
                'rejected_by_reason': dict(self.rejections),
                'last_rejection_detail': self.last_detail,
                'last_published_stamp_ns': self.gate.last_published_stamp,
                'last_arrival_age_ms': self.last_arrival_age_ms,
                'last_publish_age_ms': self.last_publish_age_ms,
                'last_callback_ms': self.last_callback_ms,
                'max_callback_ms': self.max_callback_ms,
                'seconds_since_receive': since(self.last_receive_mono),
                'seconds_since_publish': since(self.last_publish_mono),
                'header_age_note': 'Host-stamp age, not optical measurement latency.',
            }
            self.status_pub.publish(String(data=json.dumps(status, allow_nan=False, sort_keys=True)))

    rclpy.init(args=args)
    node = None
    executor = SingleThreadedExecutor()
    try:
        node = LidarCloudGuard()
        executor.add_node(node)
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        # Jazzy try_shutdown is idempotent and does not uninstall signal handlers.
        cleanup_ros_resources(executor, node, rclpy.try_shutdown)


if __name__ == '__main__':
    main()
