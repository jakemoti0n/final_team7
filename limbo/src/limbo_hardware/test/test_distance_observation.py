"""Fake-only cumulative-count bounds; no serial device is opened."""
import unittest

from limbo_hardware import roboclaw_bench as bench
from test_roboclaw_bench import Clock, FakeSerial


class DistanceObservationTests(unittest.TestCase):
    def test_explicit_flags_and_default_duration_extension_preserve_1500(self):
        self.assertEqual(bench.DEFAULT_ABSOLUTE_COUNTS, 1500)
        self.assertEqual(bench.EXTENDED_ABSOLUTE_COUNTS, 3000)
        for distance, extended, expected in ((False, False, 1500),
                                             (False, True, 1500),
                                             (True, True, 3000)):
            self.assertEqual(bench.observation_count_limit(distance, extended), expected)
            t = bench.BenchTransport(extended_distance_observation=distance,
                                     extended_observation=extended)
            self.assertEqual(t.absolute_count_limit, expected)
        self.assertEqual(bench.BenchTransport().absolute_count_limit, 1500)
        with self.assertRaisesRegex(ValueError, 'requires extended_observation'):
            bench.BenchTransport(extended_distance_observation=True)
        for invalid in (0, 1, None, 'true', .0):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, 'explicit bool'):
                    bench.observation_count_limit(invalid, True)
                with self.assertRaisesRegex(ValueError, 'explicit bool'):
                    bench.observation_count_limit(False, invalid)

    def make_ready(self, distance, counts=(1000, 2000)):
        clock = Clock()
        serial = FakeSerial(clock)
        serial.counts = list(counts)
        serial.counts_per_s = 0
        rows = []
        t = bench.BenchTransport(serial, clock=clock, sleep=clock.sleep,
                                 extended_observation=True,
                                 extended_distance_observation=distance,
                                 sample_sink=rows.append)
        t.open()
        t.preflight()
        t.arm(10.)
        t.write_duty(100, -100)
        return t, clock, serial, rows

    def advance(self, t, clock, serial, delta):
        serial.counts = [(int(c) + d) % 2**32 for c, d in zip(serial.counts, delta)]
        clock.sleep(.05)
        return t.sample()

    def test_exact_limits_wrap_and_latched_fault_cleanup(self):
        for distance, limit in ((False, 1500), (True, 3000)):
            with self.subTest(distance=distance):
                t, clock, serial, rows = self.make_ready(distance, (2**32 - 25, 25))
                for _ in range(limit // 50):
                    row = self.advance(t, clock, serial, (50, -50))
                    self.assertEqual(row['delta_counts'], [50, -50])
                self.assertEqual(row['absolute_counts'], [limit, limit])
                self.assertFalse(t.fault)
                with self.assertRaisesRegex(bench.GuardError, f'exceeds {limit}$'):
                    self.advance(t, clock, serial, (1, 0))
                self.assertEqual(rows[-1]['absolute_counts'], [limit + 1, limit])
                self.assertTrue(t.fault)
                self.assertFalse(t.armed)
                before = len(serial.writes)
                with self.assertRaises(bench.GuardError):
                    t.write_duty(1, 0)
                self.assertEqual(len(serial.writes), before)
                t.write_duty(0, 0)
                with self.assertRaises(bench.GuardError):
                    t.arm(10.)
                self.assertEqual(t.total_absolute, [limit + 1, limit])
                result = t.stop_and_close()
                self.assertTrue(result['zero_acked'])
                self.assertTrue(result['stationary_verified'])
                self.assertTrue(result['closed'])

    def test_reverse_travel_accumulates_instead_of_cancelling(self):
        for distance, limit in ((False, 1500), (True, 3000)):
            with self.subTest(distance=distance):
                t, clock, serial, rows = self.make_ready(distance)
                origin = list(t.previous['counts'])
                for i in range(limit // 50):
                    step = 50 if i % 2 == 0 else -50
                    row = self.advance(t, clock, serial, (step, -step))
                self.assertEqual(row['counts'], origin)
                self.assertEqual(row['absolute_counts'], [limit, limit])
                with self.assertRaisesRegex(bench.GuardError, f'exceeds {limit}$'):
                    self.advance(t, clock, serial, (0, -1))
                self.assertEqual(rows[-1]['absolute_counts'], [limit, limit + 1])
                self.assertTrue(t.stop_and_close()['stationary_verified'])


if __name__ == '__main__':
    unittest.main()
