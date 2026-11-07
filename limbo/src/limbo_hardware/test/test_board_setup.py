"""tools/drive/board_setup.py: 패킷 바이트 순서, 단계 흐름, 계단 응답 지표를 가짜 보드로 검사한다."""
import importlib.util
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest

from limbo_hardware.roboclaw_drive import DriveTransport, DriveError, PID_SCALE
from limbo_hardware.roboclaw_readonly import crc16

from test_roboclaw_drive import FakeSerial

TOOL = Path(__file__).resolve().parents[4] / 'tools/drive/board_setup.py'
spec = importlib.util.spec_from_file_location('board_setup', TOOL)
board_setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(board_setup)


class SpinningFakeSerial(FakeSerial):
    """duty·속도 명령을 받으면 그에 맞게 카운트가 움직이는 가짜 보드. 배선처럼 M2는 전진이 카운트 감소(엔코더 반전 전)."""

    QPPS = (5000, 5200)

    def __init__(self):
        super().__init__()
        self.duty = (0, 0)
        self.speed = (0, 0)
        self.sign_m2 = -1    # 엔코더 방향 반전이 켜지면 +1

    def write(self, packet):
        command = packet[1]
        if command == 34:
            self.duty = struct.unpack('>hh', packet[2:6])
            self.speed = (0, 0)
        if command == 40:
            self.speed = struct.unpack('>ii', packet[6:14])
            self.duty = (0, 0)
        n = super().write(packet)
        if command == 93:
            self.sign_m2 = 1 if packet[2] & 0x40 else -1
        return n

    def read(self, size):
        return super().read(size)

    def advance(self, dt):
        """표본 사이에 dt초 동안 돈 만큼 카운트를 움직인다 (출력 비례, 속도 명령은 그대로 따라감)."""
        rates = [d / 32767 * q for d, q in zip(self.duty, self.QPPS)] if any(self.duty) else list(self.speed)
        signs = (1, self.sign_m2)
        self.counts = tuple((c + round(r * dt) * s) % 2**32 for c, r, s in zip(self.counts, rates, signs))
        self.pwm = tuple(round(r / q * 32767) for r, q in zip(rates, self.QPPS))


def fake_session(stage, fake, **overrides):
    """Session을 가짜 보드와 임시 기록 폴더로 만든다. 시간은 표본마다 0.05 s씩 흐르게 한다."""
    record = tempfile.mkdtemp()
    defaults = dict(port='x', record=record, check_duty_pct=10.0, check_seconds=0.3, levels=[50, 100],
                    level_seconds=0.3, p=1.0, i=0.5, d=0.25, qpps=None, min=10.0, max=16.0,
                    speeds=[0.03], step_seconds=1.5, accel_rad_s2=2.0, source=None)
    defaults.update(overrides)
    args = type('Args', (), defaults)()
    session = board_setup.Session(args, stage)
    clock = {'t': 0.0}
    session.connect = lambda: DriveTransport(connection=fake, clock=lambda: clock['t'])
    original_sample = DriveTransport.sample

    def sample(transport):
        fake.advance(0.05)
        clock['t'] += 0.05
        return original_sample(transport)
    board_setup.DriveTransport.sample = sample
    board_setup.time.sleep = lambda s: None
    session.reopen_after_reset = session.open
    return session, Path(record)


class PacketTests(unittest.TestCase):
    def test_pid_payload_is_d_p_i_qpps_order(self):
        payload = board_setup.pid_payload(1.0, 0.5, 0.25, 5000)
        self.assertEqual(struct.unpack('>IIII', payload), (0x4000, 0x10000, 0x8000, 5000))
        with self.assertRaises(ValueError):
            board_setup.pid_payload(1.0, 0.5, 0.25, 0)
        with self.assertRaises(ValueError):
            board_setup.pid_payload(-1.0, 0.5, 0.25, 5000)

    def test_voltage_payload_is_tenths_min_max_offset(self):
        self.assertEqual(board_setup.voltage_payload(10.0, 16.0), struct.pack('>HHB', 100, 160, 20))
        with self.assertRaises(ValueError):
            board_setup.voltage_payload(16.0, 10.0)
        with self.assertRaises(ValueError):
            board_setup.voltage_payload(5.0, 16.0)

    def test_nvm_payload_is_manual_key(self):
        self.assertEqual(board_setup.nvm_payload(), bytes.fromhex('e22eab7a'))

    def test_full_duty_bypasses_drive_ceiling_only_here(self):
        fake = FakeSerial()
        transport = DriveTransport(connection=fake)
        transport.open()
        board_setup.full_duty(transport, 32767, -32767)
        self.assertEqual(fake.sent[-1][:6], bytes((128, 34)) + struct.pack('>hh', 32767, -32767))
        with self.assertRaises(DriveError):
            transport.write_duty(32767, 0)
        with self.assertRaises(ValueError):
            board_setup.full_duty(transport, 32768, 0)


class StageTests(unittest.TestCase):
    def test_backup_reads_every_setting(self):
        fake = SpinningFakeSerial()
        session, record = fake_session('backup', fake)
        board_setup.stage_backup(session)
        session.close()
        data = json.loads(next(record.glob('backup_*.json')).read_text())
        self.assertEqual(data['encoder_modes'], [0, 0])
        self.assertEqual(data['main_voltage_min_v'], 5.9)
        self.assertEqual(data['main_voltage_max_v'], 31.1)
        self.assertEqual(data['velocity_m1_m2'][0]['qpps'], 0)
        self.assertEqual(data['forward_signs_m1_m2'], [1, -1])

    def test_encoder_stage_sets_only_m2_reverse_bit_and_checks_both_increase(self):
        fake = SpinningFakeSerial()
        session, record = fake_session('encoder', fake)
        board_setup.stage_encoder(session)
        session.close()
        self.assertEqual(fake.encoder_modes, (0, 0x40))
        self.assertEqual([c for c, _ in fake.settings], [93])
        data = json.loads(next(record.glob('encoder_*.json')).read_text())
        self.assertTrue(data['both_increase_forward'])
        self.assertEqual(data['forward_signs_m1_m2'], [1, 1])
        self.assertEqual(fake.sent[-1][:6], bytes((128, 34, 0, 0, 0, 0)))   # 끝은 duty 0

    def test_encoder_stage_refuses_motor_reverse_bit(self):
        fake = SpinningFakeSerial()
        fake.encoder_modes = (0, 0x20)
        session, _ = fake_session('encoder', fake)
        with self.assertRaises(DriveError):
            board_setup.stage_encoder(session)
        session.close()
        self.assertEqual(fake.settings, [])

    def test_qpps_stage_measures_each_motor_at_full_output(self):
        fake = SpinningFakeSerial()
        fake.encoder_modes = (0, 0x40)
        fake.sign_m2 = 1
        session, record = fake_session('qpps', fake)
        board_setup.stage_qpps(session)
        session.close()
        data = json.loads(next(record.glob('qpps_*.json')).read_text())
        for measured, truth in zip(data['qpps_m1_m2'], SpinningFakeSerial.QPPS):
            self.assertLess(abs(measured - truth) / truth, 0.05)
        full = [p for p in fake.sent if p[1] == 34 and struct.unpack('>hh', p[2:6]) == (32767, 0)]
        self.assertTrue(full)

    def test_qpps_stage_needs_encoder_stage_first(self):
        fake = SpinningFakeSerial()
        session, _ = fake_session('qpps', fake)
        with self.assertRaises(DriveError):
            board_setup.stage_qpps(session)
        session.close()

    def test_pid_stage_writes_both_motors_and_reads_back(self):
        fake = SpinningFakeSerial()
        session, record = fake_session('pid', fake, qpps=[5000, 5200], p=2.0, i=0.1, d=0.0)
        board_setup.stage_pid(session)
        session.close()
        self.assertEqual(fake.velocity[55], (round(2.0 * PID_SCALE), round(0.1 * PID_SCALE), 0, 5000))
        self.assertEqual(fake.velocity[56][3], 5200)
        data = json.loads(next(record.glob('pid_*.json')).read_text())
        self.assertTrue(data['match'])

    def test_pid_stage_takes_qpps_from_latest_qpps_summary(self):
        fake = SpinningFakeSerial()
        session, record = fake_session('pid', fake)
        (record / 'qpps_0101_000000.json').write_text(json.dumps({'qpps_m1_m2': [4800, 4900]}))
        board_setup.stage_pid(session)
        session.close()
        self.assertEqual((fake.velocity[55][3], fake.velocity[56][3]), (4800, 4900))

    def test_voltage_stage_writes_and_verifies(self):
        fake = SpinningFakeSerial()
        session, record = fake_session('voltage', fake)
        board_setup.stage_voltage(session)
        session.close()
        self.assertEqual(fake.voltage_limits, (100, 160, 20))

    def test_save_stage_sends_nvm_key_and_compares_after_reconnect(self):
        fake = SpinningFakeSerial()
        session, record = fake_session('save', fake)
        board_setup.stage_save(session)
        session.close()
        self.assertIn((94, bytes.fromhex('e22eab7a')), fake.settings)
        data = json.loads(next(record.glob('save_*.json')).read_text())
        self.assertTrue(data['all_kept'])

    def test_step_stage_sends_speed_commands_and_reports_metrics(self):
        fake = SpinningFakeSerial()
        fake.encoder_modes = (0, 0x40)
        fake.sign_m2 = 1
        fake.velocity = {55: (0x10000, 0x8000, 0, 5000), 56: (0x10000, 0x8000, 0, 5200)}
        session, record = fake_session('step', fake)
        board_setup.stage_step(session)
        session.close()
        data = json.loads(next(record.glob('step_*.json')).read_text())
        self.assertEqual([s['label'] for s in data['steps']], ['+0.03', '-0.03'])
        forward = data['steps'][0]['M1(오른쪽)']
        self.assertAlmostEqual(forward['target_m_s'], 0.03, places=2)
        self.assertIsNotNone(forward['reach_90pct_s'])
        self.assertLess(abs(forward['steady_error_pct']), 5)
        self.assertEqual(forward['stalled_after_0_5s_s'], 0.0)
        speed_packets = [p for p in fake.sent if p[1] == 40]
        self.assertTrue(speed_packets)
        self.assertEqual(fake.sent[-1][:6], bytes((128, 34, 0, 0, 0, 0)))

    def test_step_stage_refuses_untuned_board(self):
        fake = SpinningFakeSerial()
        fake.encoder_modes = (0, 0x40)
        session, _ = fake_session('step', fake)
        with self.assertRaises(DriveError):
            board_setup.stage_step(session)
        session.close()

    def test_restore_writes_backup_values_back(self):
        fake = SpinningFakeSerial()
        fake.encoder_modes = (0, 0x40)
        fake.velocity = {55: (0x10000, 0x8000, 0, 5000), 56: (0x10000, 0x8000, 0, 5200)}
        fake.voltage_limits = (100, 160, 20)
        backup = {'encoder_modes': [0, 0], 'velocity_m1_m2': [{'p': 0.0, 'i': 0.0, 'd': 0.0, 'qpps': 0}] * 2,
                  'main_voltage_min_v': 5.9, 'main_voltage_max_v': 31.1, 'main_voltage_auto_offset_v': 2.0}
        path = Path(tempfile.mkdtemp()) / 'backup.json'
        path.write_text(json.dumps(backup))
        session, _ = fake_session('restore', fake, source=str(path))
        board_setup.stage_restore(session)
        session.close()
        self.assertEqual(fake.encoder_modes, (0, 0))
        self.assertEqual(fake.velocity[55], (0, 0, 0, 0))
        self.assertEqual(fake.voltage_limits, (59, 311, 20))


class MetricTests(unittest.TestCase):
    def test_step_metrics_reach_overshoot_steady_stall(self):
        geometry = {'radius': (0.075, 0.075), 'cpr': (3687, 3674)}
        rows = [{'t': k * 0.05, 'speed_counts_s': [v, 0.0], 'pwm_pct': [20.0, 0.0], 'currents_a': [1.0, 0.0]}
                for k, v in enumerate([0, 50, 120, 200, 260, 240, 235] + [235] * 20)]
        m = board_setup.step_metrics(rows, 235, geometry, 0)
        self.assertEqual(m['reach_90pct_s'], 0.2)
        self.assertAlmostEqual(m['overshoot_pct'], (260 / 235 - 1) * 100, places=1)
        self.assertAlmostEqual(m['steady_error_pct'], 0.0, places=1)
        self.assertEqual(m['stalled_after_0_5s_s'], 0.0)
        stalled = board_setup.step_metrics([dict(r, speed_counts_s=[0.0, 0.0]) for r in rows], 235, geometry, 0)
        self.assertIsNone(stalled['reach_90pct_s'])
        self.assertGreater(stalled['stalled_after_0_5s_s'], 0.5)

    def test_counts_conversion_round_trips(self):
        geometry = {'radius': (0.075, 0.075), 'cpr': (3687, 3674)}
        counts = board_setup.counts_per_s(0.03, geometry, 0)
        self.assertEqual(counts, round(0.03 / 0.075 / math.tau * 3687))
        self.assertAlmostEqual(board_setup.m_per_s(counts, geometry, 0), 0.03, places=3)


if __name__ == '__main__':
    unittest.main()
