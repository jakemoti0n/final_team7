"""Fake-only transport fault and bounded session checks; no devices are opened."""
import struct
import unittest

from limbo_hardware import roboclaw_bench as bench


class Clock:
    def __init__(self):
        self.now = 10.

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        assert seconds >= 0
        self.now += seconds


class FakeSerial:
    def __init__(self, clock):
        self.clock = clock
        self.buffer = b''
        self.writes = []
        self.timeout = self.write_timeout = .09
        self.counts = [1000., 2000.]
        self.pwm = [0, 0]
        self.voltage = 121
        self.status = 0x03000000
        self.timeout_raw = 5
        self.firmware = bench.FIRMWARE
        self.current = 50
        self.counts_per_s = 250
        self.last_time = clock()
        self.closed = False
        self.bad_ack = self.partial = self.bad_crc = self.zero_fail = self.late = False

    def update(self):
        dt = self.clock() - self.last_time
        for i, value in enumerate(self.pwm):
            self.counts[i] += (1 if value > 0 else -1 if value < 0 else 0) * self.counts_per_s * dt
        self.last_time = self.clock()

    def write(self, packet):
        self.update()
        self.clock.sleep(.0005)
        self.writes.append(bytes(packet))
        cmd = packet[1]
        if cmd == 34:
            self.pwm = list(struct.unpack('>hh', packet[2:6]))
            self.buffer = b'' if self.zero_fail and not any(self.pwm) else b'\0' if self.bad_ack and any(self.pwm) else b'\xff'
            return 4 if self.partial and any(self.pwm) else len(packet)
        if cmd == 21:
            data = self.firmware.encode() + b'\n\0'
        elif cmd == 15:
            data = bytes((self.timeout_raw,))
        elif cmd == 24:
            data = struct.pack('>H', self.voltage)
        elif cmd == 48:
            data = struct.pack('>hh', *self.pwm)
        elif cmd == 49:
            data = struct.pack('>hh', *(self.current if v else 0 for v in self.pwm))
        elif cmd == 78:
            data = struct.pack('>II', *(int(v) % 2**32 for v in self.counts))
        elif cmd == 90:
            data = struct.pack('>I', self.status)
        else:
            raise AssertionError('Unknown command reached mock')
        crc = bench.crc16(packet + data) ^ (1 if self.bad_crc else 0)
        self.buffer = data + crc.to_bytes(2, 'big')
        return len(packet)

    def read(self, size):
        self.clock.sleep(.2 if self.late else .0005 if self.buffer else self.timeout)
        self.update()
        data, self.buffer = self.buffer[:size], self.buffer[size:]
        return data

    def reset_input_buffer(self):
        self.buffer = b''

    def close(self):
        self.closed = True


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.serial = FakeSerial(self.clock)
        self.wire = []
        self.rows = []
        self.t = bench.BenchTransport(self.serial, clock=self.clock, sleep=self.clock.sleep,
                                      wire_sink=self.wire.append, sample_sink=self.rows.append)

    def ready(self, channels=(1, 2), duration=1.):
        self.t.open()
        self.t.preflight()
        self.t.arm(duration, channels)

    def test_packet_crc_and_hard_cap(self):
        self.assertEqual(bench.duty_packet(0, 0).hex(), '8022000000009817')
        self.assertEqual(struct.unpack('>hh', bench.duty_packet(3276, -3276)[2:6]), (3276, -3276))
        for value in (3277, -3277, 1.0, True):
            with self.subTest(value=value), self.assertRaises(bench.GuardError):
                bench.duty_packet(value, 0)

    def test_valid_repeated_session_and_verified_stop(self):
        self.ready()
        for _ in range(4):
            self.t.write_duty(1000, -900)
            self.clock.sleep(.04)
            row = self.t.sample()
            self.assertEqual(len(row['delta_counts']), 2)
        result = self.t.stop_and_close()
        self.assertTrue(result['zero_acked'] and result['stationary_verified'] and result['closed'])
        self.assertTrue(self.serial.closed)
        self.assertTrue(all(r['success'] for r in self.wire))
        self.assertEqual({p[1] for p in self.serial.writes}, {21, 15, 24, 78, 49, 90, 48, 34})

    def test_nonzero_before_preflight_or_arm_rejected(self):
        self.t.open()
        writes = len(self.serial.writes)
        with self.assertRaises(bench.GuardError):
            self.t.write_duty(1000, 0)
        self.assertEqual(len(self.serial.writes), writes)
        self.assertTrue(self.t.fault)
        self.t.write_duty(0, 0)

    def test_inactive_channel_fault_cannot_be_cleared_by_zero(self):
        self.ready((1,))
        with self.assertRaises(bench.GuardError):
            self.t.write_duty(0, 1)
        self.t.write_duty(0, 0)
        with self.assertRaises(bench.GuardError):
            self.t.write_duty(1, 0)

    def test_expired_and_stale_feedback_block_nonzero(self):
        for advance in (.16, 1.1):
            with self.subTest(advance=advance):
                self.setUp()
                self.ready((1,))
                writes = len(self.serial.writes)
                self.clock.sleep(advance)
                with self.assertRaises(bench.GuardError):
                    self.t.write_duty(1, 0)
                self.assertEqual(len(self.serial.writes), writes)

    def test_single_session_and_duration_limit(self):
        self.ready()
        with self.assertRaises(bench.GuardError):
            self.t.arm(.5)
        for duration in (0, -1, 5.01, float('nan'), float('inf')):
            self.setUp()
            self.t.open()
            self.t.preflight()
            with self.subTest(duration=duration), self.assertRaises(bench.GuardError):
                self.t.arm(duration)

    def test_protocol_failures_latch_no_retry_but_zero_possible(self):
        for kind in ('bad_ack', 'partial'):
            with self.subTest(kind=kind):
                self.setUp()
                self.ready((1,))
                setattr(self.serial, kind, True)
                before = len(self.serial.writes)
                with self.assertRaises(bench.BenchError):
                    self.t.write_duty(100, 0)
                self.assertEqual(len(self.serial.writes), before + 1)
                self.assertTrue(self.t.fault)
                with self.assertRaises(bench.GuardError):
                    self.t.write_duty(100, 0)
                before_read = len(self.serial.writes)
                with self.assertRaises(bench.GuardError):
                    self.t.query(78)
                self.assertEqual(len(self.serial.writes), before_read)
                self.t.write_duty(0, 0)

    def test_crc_and_late_response_latch_fault(self):
        for kind in ('bad_crc', 'late'):
            with self.subTest(kind=kind):
                self.setUp()
                self.ready()
                setattr(self.serial, kind, True)
                with self.assertRaises(bench.BenchError):
                    self.t.sample()
                self.assertTrue(self.t.fault)

    def test_zero_ack_failure_disables_all_tx_and_closes(self):
        self.ready()
        self.t.write_duty(100, 0)
        self.serial.zero_fail = True
        start = len(self.serial.writes)
        result = self.t.stop_and_close()
        self.assertFalse(result['zero_acked'])
        self.assertTrue(result['closed'])
        stop_writes = self.serial.writes[start:]
        self.assertEqual(len(stop_writes), 3)
        self.assertTrue(all(p == bench.duty_packet(0, 0) for p in stop_writes))
        with self.assertRaises(bench.GuardError):
            self.t.query(78)
        self.assertEqual(len(self.serial.writes), start + 3)

    def test_settings_and_motion_preflight_rejections(self):
        for field, value in [('timeout_raw', 0), ('voltage', 129), ('voltage', 58),
                             ('status', 0x03040000), ('pwm', [1, 0])]:
            with self.subTest(field=field, value=value):
                self.setUp()
                setattr(self.serial, field, value)
                self.t.open()
                with self.assertRaises(bench.GuardError):
                    self.t.preflight()
                self.assertFalse(any(p[1] == 34 for p in self.serial.writes))

    def test_wrong_firmware_never_writes_output(self):
        self.serial.firmware = 'Wrong board'
        with self.assertRaises(bench.GuardError):
            self.t.open()
        result = self.t.stop_and_close()
        self.assertFalse(result['zero_acked'])
        self.assertEqual([p[1] for p in self.serial.writes], [21])

    def test_allowlist_rejects_settings_and_bad_crc_before_write(self):
        self.ready()
        for packet in (b'\x80\x0e', b'\x80\x5e', b'\x80\x22\0\0\0\0\0\0'):
            before = len(self.serial.writes)
            with self.subTest(packet=packet), self.assertRaises(bench.GuardError):
                self.t.exchange(packet)
            self.assertEqual(len(self.serial.writes), before)

    def test_sample_current_and_speed_guards_latch(self):
        for field, value in [('current', 301), ('counts_per_s', 2000)]:
            with self.subTest(field=field):
                self.setUp()
                self.ready()
                self.t.write_duty(100, 0)
                setattr(self.serial, field, value)
                self.clock.sleep(.05)
                with self.assertRaises(bench.GuardError):
                    self.t.sample()
                self.assertIn('guard_error', self.rows[-1])
                self.assertTrue(self.t.fault)

    def test_logging_failure_prevents_further_nonzero(self):
        self.ready()
        def fail(row):
            raise OSError('Disk full')
        self.t.wire_sink = fail
        with self.assertRaises(OSError):
            self.t.write_duty(100, 0)
        self.assertTrue(self.t.fault)
        with self.assertRaises(bench.GuardError):
            self.t.write_duty(100, 0)
        self.t.wire_sink = self.wire.append
        self.assertTrue(self.t.stop_and_close()['stationary_verified'])

    def test_stop_cleanup_is_idempotent(self):
        self.ready()
        first = self.t.stop_and_close()
        writes = len(self.serial.writes)
        self.assertEqual(self.t.stop_and_close(), first)
        self.assertEqual(len(self.serial.writes), writes)

    def test_extended_observation_is_explicit_and_duration_remains_bounded(self):
        for value in (1,0,'true',None):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'extended_observation'):
                bench.BenchTransport(self.serial,extended_observation=value)
        for extended,duration,allowed in ((False,5.,True),(False,5.01,False),
                                          (True,10.,True),(True,10.01,False),(True,True,False)):
            t=bench.BenchTransport(self.serial,clock=self.clock,extended_observation=extended)
            t.identified=t.preflight_passed=True;t.last_sample={'monotonic_s':self.clock()}
            if allowed:
                self.assertEqual(t.arm(duration),self.clock()+duration)
                with self.assertRaises(bench.GuardError):t.arm(duration)
            else:
                with self.assertRaises(bench.GuardError):t.arm(duration)
        self.assertEqual(self.serial.writes,[])

    def test_extended_observation_preserves_count_guard_and_cleanup(self):
        self.t=bench.BenchTransport(self.serial,clock=self.clock,sleep=self.clock.sleep,
                                   extended_observation=True,sample_sink=self.rows.append)
        self.ready(duration=10.)
        self.t.total_absolute=[1500,0]
        self.serial.counts[0]+=1
        self.clock.sleep(.05)
        with self.assertRaisesRegex(bench.GuardError,'1500'):self.t.sample()
        with self.assertRaises(bench.GuardError):self.t.write_duty(100,0)
        self.assertTrue(self.t.stop_and_close()['stationary_verified'])



if __name__ == '__main__':
    unittest.main()
