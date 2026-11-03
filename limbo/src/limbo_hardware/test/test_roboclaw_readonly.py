"""No hardware: exercise protocol rejection, signed wrap and epoch boundaries."""

from collections import deque
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from limbo_hardware import roboclaw_readonly as rc


def response(request, payload):
    return payload + rc.crc16(request + payload).to_bytes(2, 'big')


def counts(m1=17, m2=0xfffffff0):
    return response(rc.COUNTS_REQUEST, m1.to_bytes(4, 'big') + m2.to_bytes(4, 'big'))


VERSION = response(rc.VERSION_REQUEST, b'USB Roboclaw 2x15A v4.4.9\n\0')


class FakeSerial:
    def __init__(self, replies, **kwargs):
        self.replies = deque(replies)
        self.kwargs = kwargs
        self.is_open = True
        self.timeout = kwargs['timeout']
        self.writes = []
        self.buffer = b''
        self.reset_calls = 0
        self.short_write = False
        self.read_error = None
        self.max_fragment = 3

    def reset_input_buffer(self):
        self.reset_calls += 1
        self.buffer = b''

    def write(self, request):
        self.writes.append(request)
        self.buffer = self.replies.popleft()
        return 1 if self.short_write else len(request)

    def read(self, size):
        if self.read_error:
            raise self.read_error
        size = min(size, self.max_fragment)
        result, self.buffer = self.buffer[:size], self.buffer[size:]
        return result

    def close(self):
        self.is_open = False


class TransportTests(unittest.TestCase):
    def make_transport(self, replies=None, **kwargs):
        self.serials = []
        self.wire = []
        def factory(**serial_kwargs):
            fake = FakeSerial([VERSION, counts()] if replies is None else replies, **serial_kwargs)
            self.serials.append(fake)
            return fake
        identity = rc.DeviceIdentity('/dev/ttyACM0', {'verified': True}, None)
        return rc.ReadOnlyRoboClaw(
            serial_factory=factory, identity_checker=lambda port: identity,
            wire_observer=self.wire.append, **kwargs,
        )

    def test_crc_and_exact_packet_guard(self):
        self.assertEqual(rc.crc16(b'123456789'), 0x31c3)
        for address in (0x00, 0x7f, 0x80, 0x81, 0xff):
            for command in range(256):
                packet = bytes((address, command))
                if packet in rc.ALLOWED_REQUESTS:
                    self.assertEqual(rc.validate_request(packet), packet)
                else:
                    with self.assertRaises(ValueError):
                        rc.validate_request(packet)
        for packet in (b'', rc.COUNTS_REQUEST + b'\0', b'\0' + rc.VERSION_REQUEST):
            with self.assertRaises(ValueError):
                rc.validate_request(packet)

    def test_valid_fragmented_protocol_and_exclusive_open(self):
        transport = self.make_transport()
        self.assertEqual(transport.open(), 'USB Roboclaw 2x15A v4.4.9')
        self.assertEqual(transport.read_counts(), (17, 0xfffffff0))
        serial = self.serials[0]
        self.assertTrue(serial.kwargs['exclusive'])
        self.assertEqual(serial.kwargs['port'], '/dev/ttyACM0')
        self.assertEqual(serial.reset_calls, 1)
        self.assertEqual(serial.writes, [rc.VERSION_REQUEST, rc.COUNTS_REQUEST])
        self.assertTrue(all(row['crc_valid'] and row['length_valid'] and row['success'] for row in self.wire))
        transport.close()
        self.assertFalse(transport.is_open)
        self.assertFalse(serial.is_open)

    def test_crc_failure_closes_without_retry_or_extra_query(self):
        bad = bytearray(counts())
        bad[-1] ^= 1
        transport = self.make_transport([VERSION, bytes(bad)])
        transport.open()
        with self.assertRaises(rc.ProtocolError):
            transport.read_counts()
        self.assertFalse(transport.is_open)
        self.assertEqual(self.serials[0].writes, [rc.VERSION_REQUEST, rc.COUNTS_REQUEST])
        self.assertFalse(self.wire[-1]['crc_valid'])
        self.assertEqual(self.wire[-1]['rx_hex'], bytes(bad).hex())

    def test_truncated_response_closes(self):
        transport = self.make_transport([VERSION, counts()[:7]])
        transport.open()
        with self.assertRaises(rc.ProtocolError):
            transport.read_counts()
        self.assertFalse(transport.is_open)
        self.assertFalse(self.wire[-1]['length_valid'])
        self.assertEqual(len(bytes.fromhex(self.wire[-1]['rx_hex'])), 7)

    def test_version_requires_terminator_crc_and_matching_identity(self):
        bad_versions = [b'x' * 48, VERSION[:-1] + bytes((VERSION[-1] ^ 1,)),
                        response(rc.VERSION_REQUEST, b'Other device\0')]
        for reply in bad_versions:
            with self.subTest(reply=reply):
                transport = self.make_transport([reply])
                with self.assertRaises(rc.RoboClawError):
                    transport.open()
                self.assertFalse(transport.is_open)
                self.assertEqual(self.serials[0].writes, [rc.VERSION_REQUEST])

    def test_short_request_write_closes(self):
        transport = self.make_transport()
        transport.open()
        self.serials[0].short_write = True
        with self.assertRaises(rc.ProtocolError):
            transport.read_counts()
        self.assertFalse(transport.is_open)
        self.assertEqual(self.wire[-1]['written'], 1)

    def test_disconnect_read_error_closes(self):
        transport = self.make_transport()
        transport.open()
        self.serials[0].read_error = OSError('USB disconnected')
        with self.assertRaises(OSError):
            transport.read_counts()
        self.assertFalse(transport.is_open)
        self.assertEqual(self.wire[-1]['error'], 'USB disconnected')

    def test_busy_port_is_not_retried(self):
        calls = []
        def busy_factory(**kwargs):
            calls.append(kwargs)
            raise OSError('exclusive port already in use')
        transport = rc.ReadOnlyRoboClaw(serial_factory=busy_factory,
            identity_checker=lambda port: rc.DeviceIdentity('/dev/ttyACM0', {}, None))
        with self.assertRaises(OSError):
            transport.open()
        self.assertEqual(len(calls), 1)
        self.assertFalse(transport.is_open)

    def test_wrong_usb_identity_opens_nothing(self):
        called = []
        def reject(port):
            raise rc.DeviceIdentityError('wrong USB device')
        transport = rc.ReadOnlyRoboClaw(identity_checker=reject,
            serial_factory=lambda **kwargs: called.append(kwargs))
        with self.assertRaises(rc.DeviceIdentityError):
            transport.open()
        self.assertEqual(called, [])

    def test_version_has_whole_transaction_deadline(self):
        transport = self.make_transport([b'x' * 48])
        ticks = iter([10.0, 10.1, 10.21])
        with patch.object(rc.time, 'monotonic', side_effect=lambda: next(ticks)):
            with self.assertRaisesRegex(rc.ProtocolError, 'deadline'):
                transport.open()
        self.assertFalse(transport.is_open)
        self.assertEqual(bytes.fromhex(self.wire[-1]['rx_hex']), b'x')

    def test_reopen_does_not_send_reset_or_motion(self):
        transport = self.make_transport()
        for _ in range(2):
            transport.open()
            transport.read_counts()
            transport.close()
        self.assertEqual(len(self.serials), 2)
        for connection in self.serials:
            self.assertEqual(connection.writes, [rc.VERSION_REQUEST, rc.COUNTS_REQUEST])

    def test_wire_record_failure_closes_port(self):
        transport = self.make_transport()
        transport.open()
        def fail(record):
            raise OSError('audit log unavailable')
        transport.wire_observer = fail
        with self.assertRaisesRegex(OSError, 'audit log unavailable'):
            transport.read_counts()
        self.assertFalse(transport.is_open)


class IdentityTests(unittest.TestCase):
    def check(self, candidates, properties):
        target = MagicMock()
        target.name = 'ttyACM0'
        target.__str__.return_value = '/dev/ttyACM0'
        device_stat = SimpleNamespace(st_mode=rc.stat.S_IFCHR, st_rdev=123)
        target.stat.return_value = device_stat
        with patch.object(rc.Path, 'resolve', return_value=target), \
             patch.object(rc.Path, 'glob', return_value=candidates), \
             patch.object(rc, '_usb_properties', return_value=properties):
            return rc.check_device_identity(rc.DEFAULT_PORT)

    def test_expected_single_board(self):
        props = dict(zip(('ID_VENDOR_ID', 'ID_MODEL_ID', 'ID_MODEL', 'ID_USB_DRIVER'), rc.EXPECTED_USB))
        identity = self.check([Path('/sys/class/tty/ttyACM0')], props)
        self.assertEqual(identity.resolved_port, '/dev/ttyACM0')
        self.assertEqual(identity.device_number, 123)

    def test_multiple_matching_boards_rejected(self):
        props = dict(zip(('ID_VENDOR_ID', 'ID_MODEL_ID', 'ID_MODEL', 'ID_USB_DRIVER'), rc.EXPECTED_USB))
        with self.assertRaisesRegex(rc.DeviceIdentityError, 'exactly one'):
            self.check([Path('/sys/class/tty/ttyACM0'), Path('/sys/class/tty/ttyACM1')], props)

    def test_unexpected_model_rejected(self):
        with self.assertRaisesRegex(rc.DeviceIdentityError, 'identity'):
            self.check([Path('/sys/class/tty/ttyACM0')], {'ID_VENDOR_ID': '03eb', 'ID_MODEL_ID': '2404'})


class CounterTests(unittest.TestCase):
    def test_forward_mapping_and_reversal(self):
        tracker = rc.CounterTracker()
        first = tracker.update((100, 500))
        self.assertTrue(first.baseline)
        self.assertEqual(first.signed_forward_total, (0, 0))
        next_reading = tracker.update((3707, 400))
        self.assertFalse(next_reading.baseline)
        self.assertEqual(next_reading.signed_forward_delta, (3607, 100))
        self.assertEqual(next_reading.signed_forward_total, (3607, 100))
        backward = tracker.update((100, 500))
        self.assertEqual(backward.signed_forward_delta, (-3607, -100))
        self.assertEqual(backward.signed_forward_total, (0, 0))

    def test_uint32_wrap_both_directions(self):
        tracker = rc.CounterTracker()
        tracker.update((0xffffffff, 0))
        self.assertEqual(tracker.update((0, 0xffffffff)).signed_forward_delta, (1, 1))
        self.assertEqual(tracker.update((0xffffffff, 0)).signed_forward_delta, (-1, -1))

    def test_reconnection_resets_baseline_without_cross_epoch_delta(self):
        tracker = rc.CounterTracker()
        tracker.update((40000, 30000))
        tracker.update((41000, 29000))
        tracker.reset()
        fresh = tracker.update((0, 0))
        self.assertTrue(fresh.baseline)
        self.assertEqual(fresh.signed_forward_delta, (0, 0))
        self.assertEqual(fresh.signed_forward_total, (0, 0))
        self.assertEqual(tracker.update((5, 0xffffffff)).signed_forward_delta, (5, 1))

    def test_discontinuity_does_not_mutate_tracker(self):
        tracker = rc.CounterTracker(max_delta_counts=500)
        tracker.update((100, 100))
        with self.assertRaises(rc.CounterDiscontinuity):
            tracker.update((10000, 100))
        self.assertEqual(tracker.update((110, 90)).signed_forward_total, (10, 10))

    def test_reject_invalid_counts_and_limits(self):
        tracker = rc.CounterTracker()
        for raw in ((True, 0), (2**32, 0), (-1, 0), (1,), (0.0, 0)):
            with self.assertRaises(ValueError):
                tracker.update(raw)
        for limit in (0, -1, 2**31, 1.5, True):
            with self.assertRaises(ValueError):
                rc.CounterTracker(max_delta_counts=limit)


if __name__ == '__main__':
    unittest.main()
