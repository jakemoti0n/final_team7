"""Read-only RoboClaw feedback; no motor command or odometry interfaces."""
import json
import math
import signal
import time
import uuid
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from rcl_interfaces.msg import ParameterDescriptor, SetParametersResult
from sensor_msgs.msg import JointState
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from limbo_interfaces.msg import WheelEncoderCounts

from .roboclaw_readonly import ReadOnlyRoboClaw, CounterTracker, DEFAULT_PORT


class EncoderNode(Node):
    def __init__(self, reader_factory=ReadOnlyRoboClaw, monotonic=time.monotonic,
                 parameter_overrides=None):
        super().__init__('roboclaw_encoder', parameter_overrides=parameter_overrides)
        self._mono = monotonic
        self._wire_file = None
        descriptor = ParameterDescriptor(read_only=True)
        defaults = {
            'port': DEFAULT_PORT,
            'poll_hz': 20.0,
            'serial_timeout': 0.2,
            'reconnect_seconds': 2.0,
            'right_counts_per_revolution': 3687.0,
            # Zero leaves the left angle unavailable until explicitly calibrated.
            'left_counts_per_revolution': 0.0,
            'max_delta_counts': 10000,
            'wire_log': '',
        }
        self.settings = {key: self.declare_parameter(key, value, descriptor).value
                         for key, value in defaults.items()}
        for key in ('poll_hz', 'serial_timeout', 'reconnect_seconds',
                    'right_counts_per_revolution'):
            value = self.settings[key]
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{key} must be finite and positive')
        left_cpr = self.settings['left_counts_per_revolution']
        if not math.isfinite(left_cpr) or left_cpr < 0:
            raise ValueError('left_counts_per_revolution must be finite and nonnegative')
        self.left_angle_enabled = left_cpr > 0
        if not 1 <= self.settings['poll_hz'] <= 50:
            raise ValueError('poll_hz must be within 1..50')
        if not 0.02 <= self.settings['serial_timeout'] <= 1.0:
            raise ValueError('serial_timeout must be within 0.02..1.0 seconds')
        if not 1 <= self.settings['max_delta_counts'] < 2**31:
            raise ValueError('max_delta_counts must be within 1..2^31-1')
        if self.get_parameter('use_sim_time').value:
            raise ValueError('Physical encoder requires use_sim_time=false')
        self.add_on_set_parameters_callback(self._parameter_change)
        if self.settings['wire_log']:
            path = Path(self.settings['wire_log'])
            # A fresh explicit filename prevents overwriting previous wire evidence.
            self._wire_file = path.open('x', encoding='utf-8', buffering=1)
        self.reader = reader_factory(
            port=self.settings['port'], timeout=self.settings['serial_timeout'],
            wire_observer=self._wire_observer if self._wire_file else None)
        self.tracker = CounterTracker(signs=(1, -1),
                                      max_delta_counts=self.settings['max_delta_counts'])
        self.session_id = ''
        self.sequence = 0
        self.connected = False
        self.firmware = ''
        self.next_retry = 0.0
        self.last_success = None
        self.previous_sample = None
        self.successful_reads = 0
        self.failures = 0
        self.connections = 0
        self.last_error = 'Waiting for first verified reading'
        self.last_read_duration = 0.0
        qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=5,
                         reliability=ReliabilityPolicy.RELIABLE)
        self.count_pub = self.create_publisher(WheelEncoderCounts, '/wheel/encoder_counts', qos)
        self.joint_pub = self.create_publisher(JointState, '/wheel/joint_states', qos)
        self.diag_pub = self.create_publisher(DiagnosticArray, '/diagnostics', 5)
        self.poll_timer = self.create_timer(1.0 / self.settings['poll_hz'], self._poll)
        self.diag_timer = self.create_timer(1.0, self._diagnostics)
        self.get_logger().info(
            'Read-only encoders: right=M1(+), left=M2(-); right CPR=%s provisional; '
            '%s; no motor commands, /odom or TF' %
            (self.settings['right_counts_per_revolution'],
             'left CPR=%s provisional' % left_cpr if self.left_angle_enabled
             else 'left angle unavailable'))

    @staticmethod
    def _parameter_change(parameters):
        if any(p.name == 'use_sim_time' and p.value for p in parameters):
            return SetParametersResult(successful=False, reason='Physical input requires wall time')
        return SetParametersResult(successful=True)

    def _wire_observer(self, record):
        if self._wire_file:
            self._wire_file.write(json.dumps(record, ensure_ascii=True) + '\n')

    def _poll(self):
        if not self.context.ok() or self._mono() < self.next_retry:
            return
        try:
            if not self.connected:
                self.firmware = self.reader.open()
                self.tracker.reset()
                self.session_id = str(uuid.uuid4())
                self.sequence = 0
                self.previous_sample = None
                self.connected = True
                self.connections += 1
                self.get_logger().info('Connected %s; new count session %s' %
                                       (self.firmware.strip(), self.session_id))
            started = self._mono()
            raw = self.reader.read_counts()
            completed = self._mono()
            if not self.context.ok():
                self.reader.close()
                return
            reading = self.tracker.update(raw)
            stamp = self.get_clock().now().to_msg()
            counts = WheelEncoderCounts()
            counts.header.stamp = stamp
            counts.session_id = self.session_id
            counts.sequence = self.sequence
            counts.baseline = reading.baseline
            counts.m1_raw, counts.m2_raw = reading.raw
            counts.right_delta, counts.left_delta = reading.signed_forward_delta
            counts.right_total, counts.left_total = reading.signed_forward_total
            joints = JointState()
            joints.header.stamp = stamp
            joints.name = ['right_wheel_joint']
            scale = 2.0 * math.pi / self.settings['right_counts_per_revolution']
            joints.position = [counts.right_total * scale]
            deltas_scaled = [counts.right_delta * scale]
            if self.left_angle_enabled:
                left_scale = 2.0 * math.pi / self.settings['left_counts_per_revolution']
                joints.name.append('left_wheel_joint')
                joints.position.append(counts.left_total * left_scale)
                deltas_scaled.append(counts.left_delta * left_scale)
            if self.previous_sample is not None and completed > self.previous_sample:
                dt = completed - self.previous_sample
                joints.velocity = [delta / dt for delta in deltas_scaled]
            else:
                joints.velocity = []
            self.count_pub.publish(counts)
            self.joint_pub.publish(joints)
            self.previous_sample = completed
            self.last_success = completed
            self.last_read_duration = completed - started
            self.last_error = ''
            self.successful_reads += 1
            self.sequence += 1
        except Exception as exc:
            self.failures += 1
            self.last_error = f'{type(exc).__name__}: {exc}'
            self.reader.close()
            self.connected = False
            self.previous_sample = None
            self.tracker.reset()
            self.next_retry = self._mono() + self.settings['reconnect_seconds']
            if self.context.ok():
                self.get_logger().warning('Encoder read unavailable; retrying: ' + self.last_error)
                self._diagnostics()

    def _diagnostics(self):
        if not self.context.ok():
            return
        message = DiagnosticArray()
        message.header.stamp = self.get_clock().now().to_msg()
        status = DiagnosticStatus()
        status.name = 'limbo/roboclaw_readonly'
        status.hardware_id = 'USB_Roboclaw_2x15A'
        age = None if self.last_success is None else self._mono() - self.last_success
        healthy = self.connected and not self.last_error and age is not None and age < 1.0
        status.level = DiagnosticStatus.OK if healthy else DiagnosticStatus.ERROR
        calibration_status = ('wheel calibrations provisional' if self.left_angle_enabled
                              else 'right calibration provisional')
        status.message = ('CRC-verified readings; ' + calibration_status) if healthy else (
            self.last_error or 'No recent verified reading')
        values = {
            'connected': self.connected, 'session_id': self.session_id,
            'successful_reads': self.successful_reads, 'failures': self.failures,
            'connections': self.connections, 'last_success_age_seconds': age,
            'last_read_seconds': self.last_read_duration, 'firmware': self.firmware.strip(),
            'right_channel': 'M1', 'right_forward_sign': 1,
            'left_channel': 'M2', 'left_forward_sign': -1,
            'right_counts_per_revolution': self.settings['right_counts_per_revolution'],
            'right_calibration': 'provisional',
            'left_counts_per_revolution': self.settings['left_counts_per_revolution']
                if self.left_angle_enabled else 'unconfirmed',
            'left_calibration': 'provisional' if self.left_angle_enabled else 'unconfirmed',
            'left_angle_enabled': self.left_angle_enabled,
            'stamp_source': 'host_ros_receive_time', 'motor_commands_enabled': False,
            'poll_hz': self.settings['poll_hz'],
        }
        status.values = [KeyValue(key=str(k), value=str(v)) for k, v in values.items()]
        message.status = [status]
        self.diag_pub.publish(message)

    def destroy_node(self):
        if hasattr(self, 'reader'):
            self.reader.close()
        if self._wire_file:
            self._wire_file.close()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = EncoderNode()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        # A terminal process group and ros2 launch can deliver the same shutdown
        # signal twice. Finish releasing the serial port even after that second signal.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
