"""Bounded, read-only RoboClaw USB transport and epoch-local counter tracking.

Only ReadVersion (21) and GetEncoders (78) can cross the serial write boundary.
The two counts returned by command 78 are unsigned 32-bit values; that command
does not return channel status bits. No motor/configuration/reset API is exposed.
"""

from dataclasses import dataclass
import math
import os
from pathlib import Path
import stat
import subprocess
import time
from typing import Callable, Optional, Tuple


DEFAULT_PORT = '/dev/serial/by-id/usb-Basicmicro_Inc._USB_Roboclaw_2x15A-if00'
VERSION_REQUEST = b'\x80\x15'
COUNTS_REQUEST = b'\x80\x4e'
ALLOWED_REQUESTS = frozenset((VERSION_REQUEST, COUNTS_REQUEST))
EXPECTED_USB = ('03eb', '2404', 'USB_Roboclaw_2x15A', 'cdc_acm')


class RoboClawError(RuntimeError):
    """Transport, identity or protocol failure; a new connection is required."""


class DeviceIdentityError(RoboClawError):
    """The selected port is not one unambiguous expected RoboClaw device."""


class ProtocolError(RoboClawError):
    """A response is incomplete, invalid, or cannot be trusted."""


class CounterDiscontinuity(ValueError):
    """A counter increment exceeded the configured per-sample limit."""


def validate_request(data: bytes) -> bytes:
    """The final write boundary rejects every packet other than two read queries."""
    packet = bytes(data)
    if packet not in ALLOWED_REQUESTS:
        raise ValueError('Only exact 0x80 ReadVersion/GetEncoders requests are allowed')
    return packet


def crc16(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1) & 0xffff
    return crc


def signed_delta(previous: int, current: int) -> int:
    """Shortest signed difference modulo 2**32 (less than half a wrap/sample)."""
    return ((current - previous + 2**31) % 2**32) - 2**31


def _usb_properties(device: str) -> dict:
    try:
        result = subprocess.run(
            ['udevadm', 'info', '--query=property', '--name=' + device],
            capture_output=True, text=True, timeout=2, check=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise DeviceIdentityError('Cannot verify USB identity: ' + str(error)) from error
    return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)


def _identity_tuple(properties: dict) -> tuple:
    return tuple(properties.get(key) for key in
                 ('ID_VENDOR_ID', 'ID_MODEL_ID', 'ID_MODEL', 'ID_USB_DRIVER'))


@dataclass(frozen=True)
class DeviceIdentity:
    resolved_port: str
    properties: dict
    device_number: Optional[int]


def check_device_identity(port: str) -> DeviceIdentity:
    """Verify product and reject multiple indistinguishable matching USB devices.

    This product's by-id name has no unique hardware serial. Enumerating matching
    ttyACM devices avoids silently selecting one when two such boards are present.
    """
    try:
        target = Path(port).resolve(strict=True)
        device_stat = target.stat()
    except OSError as error:
        raise DeviceIdentityError('Encoder port is unavailable: ' + str(error)) from error
    if not stat.S_ISCHR(device_stat.st_mode) or not target.name.startswith('ttyACM'):
        raise DeviceIdentityError('Expected a CDC ACM character device')
    properties = _usb_properties(str(target))
    if _identity_tuple(properties) != EXPECTED_USB:
        raise DeviceIdentityError('USB identity does not match the verified RoboClaw')
    candidates = list(Path('/sys/class/tty').glob('ttyACM*'))
    if len(candidates) > 16:
        raise DeviceIdentityError('Too many CDC ACM ports to verify unambiguously')
    matching = []
    for candidate in candidates:
        path = '/dev/' + candidate.name
        if _identity_tuple(_usb_properties(path)) == EXPECTED_USB:
            matching.append(path)
    if matching != [str(target)]:
        raise DeviceIdentityError('Expected exactly one matching RoboClaw USB device')
    return DeviceIdentity(str(target), properties, device_stat.st_rdev)


class ReadOnlyRoboClaw:
    """One exclusive serial connection; errors close it without retrying queries.

    ``wire_observer`` receives a dictionary for each attempted request. The caller
    may persist it for verification. Injected identity/serial factories are for
    deterministic tests; production uses udev verification and pyserial.Serial.
    """

    def __init__(self, port: str = DEFAULT_PORT, timeout: float = 0.2,
                 expected_firmware_prefix: str = 'USB Roboclaw 2x15A',
                 wire_observer: Optional[Callable[[dict], None]] = None,
                 *, serial_factory=None, identity_checker=check_device_identity):
        if not math.isfinite(timeout) or not 0.02 <= timeout <= 2.0:
            raise ValueError('Serial transaction timeout must be between 0.02 and 2 seconds')
        if not expected_firmware_prefix:
            raise ValueError('A firmware identity prefix is required')
        self.port = str(port)
        self.timeout = float(timeout)
        self.expected_firmware_prefix = expected_firmware_prefix
        self.wire_observer = wire_observer
        self._serial_factory = serial_factory
        self._identity_checker = identity_checker
        self._serial = None
        self.firmware = None
        self.identity = None

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def open(self) -> str:
        if self.is_open:
            return self.firmware
        self.close()
        try:
            self.identity = self._identity_checker(self.port)
            factory = self._serial_factory
            if factory is None:
                import serial
                factory = serial.Serial
            self._serial = factory(
                port=self.identity.resolved_port, baudrate=38400,
                timeout=self.timeout, write_timeout=self.timeout, exclusive=True,
            )
            if self.identity.device_number is not None:
                if os.fstat(self._serial.fileno()).st_rdev != self.identity.device_number:
                    raise DeviceIdentityError('USB device changed while opening the port')
            # Clear pre-existing input once, before the explicit firmware query.
            self._serial.reset_input_buffer()
            payload = self._exchange(VERSION_REQUEST)
            firmware = payload[:-1].decode('ascii')
            if not firmware.startswith(self.expected_firmware_prefix):
                raise DeviceIdentityError('Unexpected firmware identity: ' + repr(firmware))
            self.firmware = firmware.rstrip('\r\n')
            return self.firmware
        except Exception:
            self.close()
            raise

    def read_counts(self) -> Tuple[int, int]:
        if not self.is_open or self.firmware is None:
            raise RoboClawError('RoboClaw is not connected')
        payload = self._exchange(COUNTS_REQUEST)
        return int.from_bytes(payload[:4], 'big'), int.from_bytes(payload[4:8], 'big')

    def close(self) -> None:
        connection, self._serial = self._serial, None
        self.firmware = None
        if connection is not None:
            connection.close()

    def _exchange(self, request: bytes) -> bytes:
        request = validate_request(request)
        if not self.is_open:
            raise RoboClawError('RoboClaw is not connected')
        record = {'monotonic_ns': time.monotonic_ns(), 'tx_hex': request.hex(),
                  'rx_hex': '', 'written': 0, 'crc_valid': False,
                  'length_valid': False, 'success': False}
        response = bytearray()
        deadline = time.monotonic() + self.timeout

        def read_exact(size: int) -> bytes:
            data = bytearray()
            while len(data) < size:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ProtocolError('Serial transaction deadline expired')
                self._serial.timeout = remaining
                chunk = self._serial.read(size - len(data))
                response.extend(chunk)
                data.extend(chunk)
                if not chunk:
                    raise ProtocolError('Incomplete RoboClaw response')
            return bytes(data)

        try:
            record['written'] = self._serial.write(validate_request(request))
            if record['written'] != len(request):
                raise ProtocolError('Incomplete RoboClaw request write')
            if request == VERSION_REQUEST:
                for _ in range(48):
                    if read_exact(1) == b'\x00':
                        break
                else:
                    raise ProtocolError('Firmware response has no bounded NUL terminator')
                read_exact(2)
                record['length_valid'] = 3 <= len(response) <= 50 and response[-3] == 0
            else:
                read_exact(10)
                record['length_valid'] = len(response) == 10
            record['crc_valid'] = crc16(request + response[:-2]) == int.from_bytes(response[-2:], 'big')
            if not record['length_valid'] or not record['crc_valid']:
                raise ProtocolError('Invalid RoboClaw response length or CRC')
            record['success'] = True
            return bytes(response[:-2])
        except Exception as error:
            record['error'] = str(error)
            self.close()
            raise
        finally:
            record['rx_hex'] = response.hex()
            record['finished_monotonic_ns'] = time.monotonic_ns()
            if self.wire_observer is not None:
                try:
                    self.wire_observer(record)
                except Exception:
                    self.close()
                    raise


@dataclass(frozen=True)
class CounterReading:
    raw: Tuple[int, int]
    signed_forward_delta: Tuple[int, int]
    signed_forward_total: Tuple[int, int]
    baseline: bool


class CounterTracker:
    """Track relative counts inside an explicit connection epoch.

    Default signs map M1/right forward to positive and M2/left forward to
    positive. Reconnection must call reset() before accepting a fresh baseline.
    An increment limit can flag large discontinuities, but a small controller
    reset is indistinguishable from motion using command 78 alone.
    """

    def __init__(self, signs=(1, -1), max_delta_counts: int = 10000):
        if len(signs) != 2 or any(type(sign) is not int or sign not in (-1, 1) for sign in signs):
            raise ValueError('Exactly two signs of +1 or -1 are required')
        if type(max_delta_counts) is not int or not 0 < max_delta_counts < 2**31:
            raise ValueError('max_delta_counts must be a positive integer below 2**31')
        self.signs = tuple(signs)
        self.max_delta_counts = max_delta_counts
        self.reset()

    def reset(self) -> None:
        self._previous = None
        self._totals = (0, 0)

    def update(self, raw: Tuple[int, int]) -> CounterReading:
        if len(raw) != 2 or any(type(value) is not int or not 0 <= value < 2**32 for value in raw):
            raise ValueError('Two unsigned 32-bit integer counts are required')
        raw = tuple(raw)
        baseline = self._previous is None
        steps = (0, 0) if baseline else tuple(signed_delta(a, b) for a, b in zip(self._previous, raw))
        if any(abs(step) > self.max_delta_counts for step in steps):
            raise CounterDiscontinuity('Encoder increment exceeded max_delta_counts; start a new epoch')
        forward = tuple(step * sign for step, sign in zip(steps, self.signs))
        self._totals = tuple(total + step for total, step in zip(self._totals, forward))
        self._previous = raw
        return CounterReading(raw, forward, self._totals, baseline)
