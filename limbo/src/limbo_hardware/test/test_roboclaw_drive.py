"""연속 구동 직렬 계층 검사: 패킷·상한·상태 비트·timeout 설정. 실제 장치는 열지 않는다."""
import struct
import unittest

from limbo_hardware.roboclaw_drive import (DriveTransport, DriveError, DUTY_CEILING, STOP_STATUS_BITS,
                                           duty_packet, speed_packet, timeout_packet, status_names)
from limbo_hardware.roboclaw_readonly import crc16


class FakeSerial:
    """요청을 받아 미리 정한 응답을 돌려주는 가짜 포트. 보낸 패킷은 전부 기록한다."""

    def __init__(self):
        self.sent = []
        self.rx = bytearray()
        self.timeout = self.write_timeout = 0.1
        self.closed = False
        self.timeout_raw = 0
        self.counts = (1000, 4294000000)
        self.status = 0x03000000
        self.volts = 119
        self.pwm = (0, 0)
        self.currents = (0, 0)                  # 10 mA 단위
        self.encoder_modes = (0, 0)
        # 속도 제어 값 (P, I, D, QPPS). P·I·D는 16.16 고정소수점. 처음에는 한 번도 설정 안 된 보드처럼 0
        self.velocity = {55: (0, 0, 0, 0), 56: (0, 0, 0, 0)}
        self.voltage_limits = (59, 311, 20)     # 0.1 V: 최소, 최대, 자동 최대 오프셋 (11-06 실측 기본값)
        self.speed_error_limits = (0, 0)
        self.settings = []                      # write_setting으로 받은 (명령, 페이로드)

    def reset_input_buffer(self):
        self.rx.clear()

    def write(self, packet):
        self.sent.append(bytes(packet))
        command = packet[1]
        if command in (34, 14, 40, 28, 29, 57, 92, 93, 94):
            if command == 14:
                self.timeout_raw = packet[2]
            if command in (28, 29, 57, 92, 93, 94):
                self.settings.append((command, bytes(packet[2:-2])))
            if command in (28, 29):   # D, P, I, QPPS 순서로 받는다(매뉴얼) → 읽기(55·56)는 P, I, D, QPPS
                d, p, i, q = struct.unpack('>IIII', packet[2:-2])
                self.velocity[command + 27] = (p, i, d, q)
            if command in (92, 93):
                modes = list(self.encoder_modes)
                modes[command - 92] = packet[2]
                self.encoder_modes = tuple(modes)
            if command == 57:
                self.voltage_limits = struct.unpack('>HHB', packet[2:-2])
            self.rx += b'\xff'
            return len(packet)
        if command == 21:
            body = b'USB Roboclaw 2x15A v4.4.9\n\0'
        elif command == 15:
            body = bytes((self.timeout_raw,))
        elif command == 24:
            body = self.volts.to_bytes(2, 'big')
        elif command == 48:
            body = struct.pack('>hh', *self.pwm)
        elif command == 49:
            body = struct.pack('>hh', *self.currents)
        elif command in (55, 56):
            body = struct.pack('>IIII', *self.velocity[command])
        elif command == 91:
            body = bytes(self.encoder_modes)
        elif command == 59:
            body = struct.pack('>HHB', *self.voltage_limits)
        elif command == 110:
            body = struct.pack('>II', *self.speed_error_limits)
        elif command == 78:
            body = struct.pack('>II', *self.counts)
        elif command == 90:
            body = self.status.to_bytes(4, 'big')
        else:
            raise AssertionError('unexpected command %d' % command)
        self.rx += body + crc16(bytes(packet) + body).to_bytes(2, 'big')
        return len(packet)

    def read(self, size):
        data, self.rx = bytes(self.rx[:size]), self.rx[size:]
        return data

    def close(self):
        self.closed = True


def make():
    fake = FakeSerial()
    transport = DriveTransport(connection=fake, duty_cap=4915)
    transport.open()
    return transport, fake


class PacketTests(unittest.TestCase):
    def test_duty_packet_is_command_34_with_crc_and_respects_cap(self):
        packet = duty_packet(100, -200, 4915)
        self.assertEqual(packet[:2], bytes((128, 34)))
        self.assertEqual(struct.unpack('>hh', packet[2:6]), (100, -200))
        self.assertEqual(crc16(packet[:6]).to_bytes(2, 'big'), packet[6:])
        for bad in ((4916, 0, 4915), (0, 0, DUTY_CEILING + 1), (1.0, 0, 4915), (0, 0, 0)):
            with self.subTest(bad=bad), self.assertRaises(DriveError):
                duty_packet(*bad)

    def test_speed_packet_is_command_40_accel_then_signed_speeds(self):
        packet = speed_packet(765, -783, 1174, (5000, 5100))
        self.assertEqual(packet[:2], bytes((128, 40)))
        self.assertEqual(struct.unpack('>Iii', packet[2:14]), (1174, 765, -783))
        self.assertEqual(int.from_bytes(packet[14:], 'big'), crc16(packet[:14]))
        with self.assertRaises(DriveError):
            speed_packet(5001, 0, 1174, (5000, 5100))     # M1 한계(QPPS) 초과
        with self.assertRaises(DriveError):
            speed_packet(0, -5101, 1174, (5000, 5100))    # M2 한계 초과(부호 무관)
        with self.assertRaises(DriveError):
            speed_packet(100, 100, 0, (5000, 5100))       # 가속도 0은 "즉시"가 아니라 잘못된 값
        with self.assertRaises(DriveError):
            speed_packet(100.0, 100, 1174, (5000, 5100))  # 정수만

    def test_timeout_packet(self):
        packet = timeout_packet(5)
        self.assertEqual(packet[:3], bytes((128, 14, 5)))
        with self.assertRaises(DriveError):
            timeout_packet(256)

    def test_status_names(self):
        self.assertEqual(status_names(0x03000000, STOP_STATUS_BITS), [])
        self.assertEqual(status_names(0x03040000, STOP_STATUS_BITS), ['main_voltage_high_warning'])
        self.assertIn('e_stop', status_names(0x1, STOP_STATUS_BITS))


class TransportTests(unittest.TestCase):
    def test_open_checks_firmware_prefix(self):
        transport, fake = make()
        self.assertTrue(transport.firmware.startswith('USB Roboclaw 2x15A'))
        with self.assertRaises(DriveError):
            transport.open()

    def test_ensure_timeout_writes_only_when_zero(self):
        transport, fake = make()
        self.assertEqual(transport.ensure_timeout(), 0.5)
        writes = [p for p in fake.sent if p[1] == 14]
        self.assertEqual(len(writes), 1)
        self.assertEqual(transport.ensure_timeout(), 0.5)  # 이미 5라 다시 쓰지 않음
        self.assertEqual(len([p for p in fake.sent if p[1] == 14]), 1)

    def test_sample_reports_stop_reasons_and_pwm(self):
        transport, fake = make()
        fake.status = 0x03040000
        fake.pwm = (100, -100)
        row = transport.sample()
        self.assertEqual(row['counts'], [1000, 4294000000])
        self.assertEqual(row['stop_reasons'], ['main_voltage_high_warning'])
        self.assertEqual(row['pwms'], [100, -100])

    def test_write_duty_rejects_over_cap_before_sending(self):
        transport, fake = make()
        sent = len(fake.sent)
        with self.assertRaises(DriveError):
            transport.write_duty(4916, 0)
        self.assertEqual(len(fake.sent), sent)
        transport.write_duty(4915, -4915)
        self.assertEqual(fake.sent[-1][:6], bytes((128, 34)) + struct.pack('>hh', 4915, -4915))

    def test_thirty_percent_boundary_and_overshoot_never_reaches_serial(self):
        cap = 9830
        self.assertEqual(DUTY_CEILING, cap)
        fake = FakeSerial()
        transport = DriveTransport(connection=fake, duty_cap=cap)
        transport.open()
        transport.write_duty(cap, -cap)
        self.assertEqual(struct.unpack('>hh', fake.sent[-1][2:6]), (cap, -cap))
        sent = len(fake.sent)
        for pair in ((cap + 1, 0), (0, -cap - 1)):
            with self.subTest(pair=pair), self.assertRaises(DriveError):
                transport.write_duty(*pair)
        self.assertEqual(len(fake.sent), sent)
        for invalid_cap in (cap + 1, 11468, 16383):
            with self.subTest(cap=invalid_cap), self.assertRaises(DriveError):
                DriveTransport(connection=fake, duty_cap=invalid_cap)
        self.assertEqual(len(fake.sent), sent)
        transport.close()

    def test_sample_includes_motor_currents_in_amps(self):
        transport, fake = make()
        fake.currents = (123, 45)
        self.assertEqual(transport.sample()['currents_a'], [1.23, 0.45])

    def test_encoder_modes_are_read_from_the_board(self):
        transport, fake = make()
        fake.encoder_modes = (0, 0x40)
        self.assertEqual(transport.read_encoder_modes(), (0, 0x40))

    def test_speed_command_needs_velocity_settings_read_from_the_board(self):
        transport, fake = make()
        with self.assertRaises(DriveError):            # 아직 안 읽음
            transport.write_speed(100, 100, 1174)
        self.assertEqual([row['qpps'] for row in transport.read_velocity_settings()], [0, 0])
        with self.assertRaises(DriveError):            # 읽었지만 보드가 튜닝 전(QPPS 0)
            transport.write_speed(100, 100, 1174)
        fake.velocity = {55: (0x00018000, 0x00004000, 0, 5000), 56: (0x00010000, 0x00008000, 0, 5100)}
        settings = transport.read_velocity_settings()
        self.assertEqual(settings[0], {'p': 1.5, 'i': 0.25, 'd': 0.0, 'qpps': 5000})
        self.assertEqual(settings[1], {'p': 1.0, 'i': 0.5, 'd': 0.0, 'qpps': 5100})
        self.assertEqual(transport.speed_caps, (5000, 5100))
        sent = len(fake.sent)
        transport.write_speed(765, -783, 1174)
        self.assertEqual(fake.sent[-1], speed_packet(765, -783, 1174, (5000, 5100)))
        with self.assertRaises(DriveError):
            transport.write_speed(5001, 0, 1174)       # 한계를 넘는 값은 직렬로 나가지 않는다
        self.assertEqual(len(fake.sent), sent + 1)

    def test_close_sends_zero_and_closes_port(self):
        transport, fake = make()
        self.assertTrue(transport.close())
        self.assertEqual(fake.sent[-1][:6], bytes((128, 34, 0, 0, 0, 0)))
        self.assertTrue(fake.closed)
        self.assertFalse(transport.close())  # 두 번째는 아무것도 안 함

    def test_write_setting_builds_ack_packet_with_crc(self):
        transport, fake = make()
        transport.write_setting(93, b'\x40')
        self.assertEqual(fake.sent[-1][:3], bytes((128, 93, 0x40)))
        self.assertEqual(fake.sent[-1][3:], crc16(fake.sent[-1][:3]).to_bytes(2, 'big'))
        self.assertEqual(transport.read_encoder_modes(), (0, 0x40))
        with self.assertRaises(DriveError):
            transport.write_setting(300, b'')
        with self.assertRaises(DriveError):
            transport.write_setting(93, 'x')

    def test_voltage_limits_and_speed_error_limits_are_readable(self):
        transport, fake = make()
        self.assertEqual(transport.query(59), struct.pack('>HHB', 59, 311, 20))
        self.assertEqual(struct.unpack('>II', transport.query(110)), (0, 0))

    def test_crc_failure_raises(self):
        transport, fake = make()
        original = fake.write

        def corrupt(packet):
            n = original(packet)
            fake.rx[-1] ^= 0xff
            return n
        fake.write = corrupt
        with self.assertRaises(DriveError):
            transport.read_battery_volts()


if __name__ == '__main__':
    unittest.main()
