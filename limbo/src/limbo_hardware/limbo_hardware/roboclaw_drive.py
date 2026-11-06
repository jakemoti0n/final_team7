"""연속 주행용 RoboClaw USB 직렬 계층 (/cmd_vel 브리지가 쓴다).

벤치용 BenchTransport(한 번·유한 시간·고정 목표)와 달리 세션 제한이 없다. 대신 보드 자체 안전장치(명령 timeout)를
켜고, 상태 비트로 출력을 막을 상황을 알려 준다. 모터 명령은 duty(명령 34)뿐이고 설정 쓰기는 명령 timeout(명령 14,
런타임 값·NVM 저장 안 함) 하나다. 정지는 호출자가 반드시 close()로 끝낸다.
"""
import math
import os
import struct
import subprocess
import time

from .roboclaw_readonly import DEFAULT_PORT, check_device_identity, crc16

ADDRESS = 128
FIRMWARE_PREFIX = 'USB Roboclaw 2x15A'
# 읽기 명령과 응답 길이(CRC 제외). 21 펌웨어 문자열, 15 명령 timeout, 24 주전원 전압, 48 PWM, 49 전류, 78 엔코더, 90 상태
READ_LENGTHS = {21: None, 15: 1, 24: 2, 48: 4, 49: 4, 78: 8, 90: 4}
DUTY_FULL = 32767
# 사용자 요청(2026-11-04): 연속 주행 출력은 30 %를 넘지 않는다.
# PWM 상한은 실제 속도·전류 보장이 아니며, 낮은 상한으로 실행할 수는 있다.
DUTY_CEILING = 9830
# 명령 timeout 단위는 0.1 s. 5 = 0.5 s: 노드가 죽어도 이 시간 안에 보드가 스스로 모터를 끊는다
TIMEOUT_UNIT_S = 0.1
TIMEOUT_RAW_DEFAULT = 5

# 펌웨어 4.x 32비트 상태 비트 중 "켜져 있으면 출력을 0으로 둘 것". 경고(warning)도 넣은 이유: 매뉴얼에
# Main Battery High Warning은 "조건이 지속되는 동안 모터를 제동으로 멈춤"이라 어차피 안 움직이고,
# 우리가 계속 duty를 밀면 보드와 싸우기만 한다 (11-03 아침 충전 후 무동작이 이 경우였다)
STOP_STATUS_BITS = {
    0x00000001: 'e_stop', 0x00000002: 'temperature_error', 0x00000004: 'temperature2_error',
    0x00000008: 'main_voltage_high_error', 0x00000010: 'logic_voltage_high_error',
    0x00000020: 'logic_voltage_low_error', 0x00000040: 'm1_driver_fault', 0x00000080: 'm2_driver_fault',
    0x00001000: 'm1_current_error', 0x00002000: 'm2_current_error',
    0x00040000: 'main_voltage_high_warning', 0x00080000: 'main_voltage_low_warning',
}
# 알려 주기만 하는 비트(보드가 알아서 출력을 줄이거나 duty 모드에서 의미 없는 것)
NOTE_STATUS_BITS = {
    0x00010000: 'm1_over_current_warning', 0x00020000: 'm2_over_current_warning',
    0x00100000: 'temperature_warning', 0x00200000: 'temperature2_warning',
    0x00400000: 's4_triggered', 0x00800000: 's5_triggered',
}


class DriveError(RuntimeError):
    """직렬 통신·장치 확인·응답 검증 실패. 호출자는 출력을 0으로 하고 끝낸다."""


def status_names(status, table):
    return [name for bit, name in table.items() if status & bit]


def duty_packet(m1, m2, cap):
    """명령 34(양쪽 duty) 패킷. 부호 있는 16비트, |값| ≤ cap ≤ DUTY_CEILING."""
    if type(cap) is not int or not 1 <= cap <= DUTY_CEILING:
        raise DriveError(f'duty 상한은 1..{DUTY_CEILING} 정수여야 함')
    if any(type(v) is not int or abs(v) > cap for v in (m1, m2)):
        raise DriveError('duty가 상한을 넘음')
    payload = bytes((ADDRESS, 34)) + struct.pack('>hh', m1, m2)
    return payload + crc16(payload).to_bytes(2, 'big')


def timeout_packet(raw):
    if type(raw) is not int or not 0 <= raw <= 255:
        raise DriveError('timeout raw는 0..255')
    payload = bytes((ADDRESS, 14, raw))
    return payload + crc16(payload).to_bytes(2, 'big')


class DriveTransport:
    """독점 직렬 연결 하나. 쓰기는 duty(34)와 명령 timeout(14)만 허용한다."""

    def __init__(self, *, port=DEFAULT_PORT, serial_timeout=0.09, duty_cap=DUTY_CEILING,
                 connection=None, clock=time.monotonic, wire_sink=None):
        if not math.isfinite(serial_timeout) or not 0.02 <= serial_timeout <= 0.2:
            raise ValueError('직렬 응답 대기는 0.02..0.2 s')
        duty_packet(0, 0, duty_cap)  # 상한 검증
        self.port, self.serial_timeout, self.duty_cap = port, serial_timeout, duty_cap
        self.serial, self.clock = connection, clock
        self.wire_sink = wire_sink or (lambda row: None)
        self.firmware = None
        self.closed = False
        self.device = None

    # ---- 연결 ----
    def open(self):
        if self.closed or self.firmware is not None:
            raise DriveError('이미 열렸거나 닫힌 연결은 다시 열 수 없음')
        if self.serial is None:
            import fcntl
            import termios
            import serial
            identity = check_device_identity(self.port)
            owners = subprocess.run(['fuser', identity.resolved_port], capture_output=True,
                                    text=True, timeout=2, check=False)
            if owners.returncode != 1 or owners.stdout.strip() or owners.stderr.strip():
                raise DriveError('직렬 포트를 다른 프로세스가 쓰고 있음: ' + identity.resolved_port)
            self.serial = serial.Serial(identity.resolved_port, 38400, timeout=self.serial_timeout,
                                        write_timeout=self.serial_timeout, exclusive=True)
            try:
                if os.fstat(self.serial.fileno()).st_rdev != identity.device_number:
                    raise DriveError('포트를 여는 사이 USB 장치가 바뀜')
                fcntl.ioctl(self.serial.fileno(), termios.TIOCEXCL)
                self.device = {'resolved_port': identity.resolved_port, 'properties': identity.properties}
            except BaseException:
                self.serial.close()
                self.closed = True
                raise
        self.serial.reset_input_buffer()
        firmware = self.query(21)[:-1].decode('ascii').strip()
        if not firmware.startswith(FIRMWARE_PREFIX):
            raise DriveError('예상 밖 펌웨어: ' + repr(firmware))
        self.firmware = firmware
        return firmware

    # ---- 저수준 교환 ----
    def _exchange(self, packet, expect_ack):
        if self.closed or self.serial is None:
            raise DriveError('직렬 연결이 없음')
        start = self.clock()
        row = {'monotonic_s': start, 'command': packet[1], 'tx_hex': packet.hex(), 'rx_hex': '', 'success': False}
        response = bytearray()
        end = start + self.serial_timeout

        def read_exact(size):
            data = bytearray()
            while len(data) < size:
                remaining = end - self.clock()
                if remaining <= 0:
                    raise DriveError('응답 대기 시간 초과 (명령 %d)' % packet[1])
                self.serial.timeout = remaining
                chunk = self.serial.read(size - len(data))
                if not chunk:
                    raise DriveError('응답이 끊김 (명령 %d)' % packet[1])
                data.extend(chunk)
                response.extend(chunk)
            return bytes(data)

        try:
            self.serial.write_timeout = self.serial_timeout
            if self.serial.write(packet) != len(packet):
                raise DriveError('직렬 쓰기가 끝나지 않음')
            if expect_ack:
                if read_exact(1) != b'\xff':
                    raise DriveError('ACK 0xff가 아님 (명령 %d)' % packet[1])
                result = b'\xff'
            else:
                length = READ_LENGTHS[packet[1]]
                if length is None:  # 펌웨어 문자열: NUL까지 + CRC 2
                    for _ in range(48):
                        if read_exact(1) == b'\0':
                            break
                    else:
                        raise DriveError('펌웨어 문자열 끝을 못 찾음')
                    read_exact(2)
                else:
                    read_exact(length + 2)
                if crc16(packet + response[:-2]) != int.from_bytes(response[-2:], 'big'):
                    raise DriveError('응답 CRC 불일치 (명령 %d)' % packet[1])
                result = bytes(response[:-2])
            row['success'] = True
            return result
        except BaseException as error:
            row['error'] = repr(error)
            raise
        finally:
            row['rx_hex'] = response.hex()
            row['finished_monotonic_s'] = self.clock()
            self.wire_sink(row)

    def query(self, command):
        if command not in READ_LENGTHS:
            raise DriveError('허용되지 않은 읽기 명령 %r' % (command,))
        return self._exchange(bytes((ADDRESS, command)), expect_ack=False)

    # ---- 읽기 ----
    def read_timeout_s(self):
        return self.query(15)[0] * TIMEOUT_UNIT_S

    def read_battery_volts(self):
        return int.from_bytes(self.query(24), 'big') / 10.0

    def sample(self):
        """엔코더·상태·PWM 한 벌. counts는 보드 원시값(uint32 M1, M2)."""
        counts = struct.unpack('>II', self.query(78))
        stamp = self.clock()
        status = int.from_bytes(self.query(90), 'big')
        pwm = struct.unpack('>hh', self.query(48))
        return {'monotonic_s': stamp, 'counts': list(counts), 'status': status,
                'status_hex': f'0x{status:08x}', 'pwms': list(pwm),
                'stop_reasons': status_names(status, STOP_STATUS_BITS),
                'notes': status_names(status, NOTE_STATUS_BITS)}

    # ---- 쓰기 ----
    def ensure_timeout(self, raw=TIMEOUT_RAW_DEFAULT):
        """보드 명령 timeout이 0(꺼짐)이면 켠다. 전원을 다시 넣으면 0으로 돌아오므로 시작 때마다 확인한다.
        돌려주는 값은 실제 적용된 초."""
        current = self.query(15)[0]
        if current == 0:
            self._exchange(timeout_packet(raw), expect_ack=True)
            current = self.query(15)[0]
            if current != raw:
                raise DriveError('명령 timeout 설정이 반영되지 않음 (읽힘 %d)' % current)
        return current * TIMEOUT_UNIT_S

    def write_duty(self, m1, m2):
        return self._exchange(duty_packet(m1, m2, self.duty_cap), expect_ack=True)

    def recover(self):
        """교환 하나가 실패한 뒤 다음 교환 전에 부른다. 늦게 도착한 응답 조각이 다음 응답에 섞이지 않게 입력 버퍼를 비운다.
        12 ms: 보드가 한 응답을 다 보내는 데 걸리는 시간(38400 bps에서 10바이트 ≈ 2.6 ms)보다 넉넉히."""
        if self.serial is not None and not self.closed:
            time.sleep(0.012)
            self.serial.reset_input_buffer()

    def stop(self, attempts=3):
        """양쪽 0을 ACK 받을 때까지 최대 attempts번. 실패하면 False (보드 timeout이 마지막 안전망)."""
        for index in range(attempts):
            try:
                if index:
                    time.sleep(0.012)
                    self.serial.reset_input_buffer()
                self.write_duty(0, 0)
                return True
            except Exception:
                continue
        return False

    def close(self):
        """0 출력 시도 후 포트를 닫는다. 몇 번을 불러도 안전하다."""
        acked = False
        if self.serial is not None and not self.closed:
            try:
                if self.firmware is not None:
                    acked = self.stop()
            finally:
                try:
                    self.serial.close()
                except Exception:
                    pass
                self.closed = True
        return acked
