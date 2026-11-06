"""One finite RoboClaw duty-control session; no settings, native PID, or reconnect.

The caller owns signal handling and must call stop_and_close in finally. Python
deadlines are host-side bounds, not guarantees during OS/USB/power failures.
"""
import math
import os
import struct
import subprocess
import time

from .roboclaw_readonly import DEFAULT_PORT, check_device_identity, crc16, signed_delta

ADDRESS = 128
FIRMWARE = 'USB Roboclaw 2x15A v4.4.9'
READ_LENGTHS = {21: None, 15: 1, 24: 2, 48: 4, 49: 4, 78: 8, 90: 4}
MAX_DUTY = 3276  # Default remains the previously tested ~10% cap.
ABSOLUTE_MAX_DUTY = 4915  # Explicit startup-margin comparison only; ~15%.
DUTY_ENVELOPE = 'duty_ceiling_4915_v1'
CPR = (3687, 3674)  # Right, left; 2026-11-05 provisional calibration.
ALLOWED_STATUS = 0x03000000
DEFAULT_ABSOLUTE_COUNTS = 1500
EXTENDED_ABSOLUTE_COUNTS = 3000


class BenchError(RuntimeError):
    pass


class GuardError(BenchError):
    pass


def validate_duty_limit(value):
    if type(value) is not int or not 1 <= value <= ABSOLUTE_MAX_DUTY:
        raise GuardError("Duty limit must be an integer in 1..4915")
    return value


def observation_duration_limit(extended_observation):
    if type(extended_observation) is not bool:
        raise ValueError('extended_observation must be an explicit bool')
    return 10.0 if extended_observation else 5.0


def observation_count_limit(extended_distance_observation, extended_observation):
    if type(extended_distance_observation) is not bool:
        raise ValueError('extended_distance_observation must be an explicit bool')
    observation_duration_limit(extended_observation)
    if extended_distance_observation and not extended_observation:
        raise ValueError('extended_distance_observation requires extended_observation')
    return EXTENDED_ABSOLUTE_COUNTS if extended_distance_observation else DEFAULT_ABSOLUTE_COUNTS


def duty_packet(m1, m2, *, max_duty_raw=MAX_DUTY):
    cap = validate_duty_limit(max_duty_raw)
    if any(type(value) is not int or abs(value) > cap for value in (m1, m2)):
        raise GuardError("Duty exceeds the configured session limit")
    payload = bytes((ADDRESS, 34)) + struct.pack('>hh', m1, m2)
    return payload + crc16(payload).to_bytes(2, 'big')


class BenchTransport:
    def __init__(self, connection=None, *, port=DEFAULT_PORT, timeout=.09,
                 max_duty_raw=MAX_DUTY, extended_observation=False,
                 extended_distance_observation=False,
                 clock=time.monotonic, sleep=time.sleep, wire_sink=None,
                 sample_sink=None):
        if not math.isfinite(timeout) or not .08 <= timeout <= .1:
            raise ValueError('Serial timeout must be 0.08..0.10 seconds')
        self.max_duration_s = observation_duration_limit(extended_observation)
        self.extended_observation = extended_observation
        self.absolute_count_limit = observation_count_limit(
            extended_distance_observation, extended_observation)
        self.extended_distance_observation = extended_distance_observation
        self.max_duty_raw = validate_duty_limit(max_duty_raw)
        self.serial, self.port, self.timeout = connection, port, timeout
        self.clock, self.sleep = clock, sleep
        self.wire_sink = wire_sink or (lambda row: None)
        self.sample_sink = sample_sink or (lambda row: None)
        self.identified = self.preflight_passed = self.armed = False
        self.fault = self.used = self.closed = self.tx_disabled = False
        self.deadline = None
        self.active_channels = ()
        self.previous = self.last_sample = None
        self.total_absolute = [0, 0]
        self.device = None
        self._stopping = self._stop_zero_acked = False
        self._stop_result = None

    def _fail(self, message):
        self.fault = True
        self.armed = False
        raise GuardError(message)

    def open(self):
        if self.closed or self.identified:
            self._fail('Transport cannot reopen')
        if self.serial is None:
            import fcntl
            import termios
            import serial
            identity = check_device_identity(self.port)
            owners = subprocess.run(['fuser', identity.resolved_port], capture_output=True,
                                    text=True, timeout=2, check=False)
            if owners.returncode != 1 or owners.stdout.strip() or owners.stderr.strip():
                self._fail('Cannot establish unowned serial port')
            self.serial = serial.Serial(identity.resolved_port, 38400, timeout=self.timeout,
                                        write_timeout=self.timeout, exclusive=True)
            try:
                if os.fstat(self.serial.fileno()).st_rdev != identity.device_number:
                    self._fail('USB device identity changed while opening')
                fcntl.ioctl(self.serial.fileno(), termios.TIOCEXCL)
                self.device = {'resolved_port': identity.resolved_port,
                               'properties': identity.properties}
            except BaseException:
                self.serial.close()
                self.closed = True
                raise
        self.serial.reset_input_buffer()
        firmware = self.query(21)[:-1].decode('ascii').strip()
        if firmware != FIRMWARE:
            self._fail('Unexpected firmware: ' + repr(firmware))
        self.identified = True
        return firmware

    def _boundary(self, packet):
        if self.closed or self.tx_disabled or self.serial is None:
            self._fail('Serial transmission is disabled')
        if len(packet) == 2 and packet[0] == ADDRESS and packet[1] in READ_LENGTHS:
            if self.fault and not (self._stopping and self._stop_zero_acked):
                self._fail('Post-fault reads require an acknowledged cleanup zero')
            return
        if len(packet) != 8 or packet[:2] != bytes((ADDRESS, 34)):
            self._fail('Packet outside the bench allowlist')
        pair = struct.unpack('>hh', packet[2:6])
        try:
            valid = duty_packet(*pair, max_duty_raw=self.max_duty_raw) == packet
        except GuardError:
            valid = False
        if not valid or not self.identified:
            self._fail('Invalid duty packet or unidentified firmware')
        if any(pair):
            now = self.clock()
            if (self.fault or not self.armed or not self.preflight_passed or
                    self.deadline is None or now >= self.deadline):
                self._fail('Nonzero duty is not in the single armed session')
            if any(value and index + 1 not in self.active_channels
                   for index, value in enumerate(pair)):
                self._fail('Nonzero output on an inactive channel')
            if self.last_sample is None or not 0 <= now - self.last_sample['monotonic_s'] <= .15:
                self._fail('Verified feedback is too old for another output')

    def exchange(self, packet, deadline=None):
        packet = bytes(packet)
        self._boundary(packet)
        start = self.clock()
        end = min(start + self.timeout, deadline) if deadline is not None else start + self.timeout
        nonzero = packet[1] == 34 and packet[2:6] != b'\0\0\0\0'
        if nonzero:
            end = min(end, self.deadline)
        if not math.isfinite(end) or end <= start:
            self._fail('Serial transaction deadline expired')
        row = {'monotonic_s': start, 'command': packet[1], 'tx_hex': packet.hex(),
               'rx_hex': '', 'written': 0, 'success': False, 'nonzero': nonzero,
               'deadline_s': end}
        response = bytearray()

        def read_exact(size):
            data = bytearray()
            while len(data) < size:
                remaining = end - self.clock()
                if remaining <= 0:
                    raise BenchError('Read deadline expired')
                self.serial.timeout = remaining
                chunk = self.serial.read(size - len(data))
                data.extend(chunk)
                response.extend(chunk)
                if self.clock() > end or not chunk:
                    raise BenchError('Incomplete or late response')
            return bytes(data)

        try:
            self.serial.write_timeout = end - self.clock()
            if self.serial.write_timeout <= 0:
                raise BenchError('Write deadline expired')
            row['written'] = self.serial.write(packet)
            if row['written'] != len(packet) or self.clock() >= end:
                raise BenchError('Partial or late serial write')
            if packet[1] == 34:
                ack = read_exact(1)
                row['ack_valid'] = ack == b'\xff'
                if not row['ack_valid']:
                    raise BenchError('Expected exact 0xff ACK')
                result = ack
            else:
                length = READ_LENGTHS[packet[1]]
                if length is None:
                    for _ in range(48):
                        if read_exact(1) == b'\0':
                            break
                    else:
                        raise BenchError('Unterminated firmware')
                    read_exact(2)
                else:
                    read_exact(length + 2)
                row['length_valid'] = (3 <= len(response) <= 50 and response[-3] == 0
                                       if length is None else len(response) == length + 2)
                row['crc_valid'] = crc16(packet + response[:-2]) == int.from_bytes(response[-2:], 'big')
                if not row['length_valid'] or not row['crc_valid']:
                    raise BenchError('Invalid response length or CRC')
                result = bytes(response[:-2])
            row['success'] = True
            return result
        except BaseException as error:
            self.fault = True
            self.armed = False
            row['error'] = repr(error)
            raise
        finally:
            row['rx_hex'] = response.hex()
            row['finished_monotonic_s'] = self.clock()
            try:
                self.wire_sink(row)
            except BaseException:
                self.fault = True
                self.armed = False
                raise

    def query(self, command, deadline=None):
        if command not in READ_LENGTHS:
            self._fail('Read command not allowed')
        return self.exchange(bytes((ADDRESS, command)), deadline)

    def write_duty(self, m1, m2):
        try:
            packet = duty_packet(m1, m2, max_duty_raw=self.max_duty_raw)
        except GuardError as error:
            self._fail(str(error))
        return self.exchange(packet)

    def sample(self, phase='control', deadline=None):
        if phase == 'control':
            if not self.armed or self.fault:
                self._fail('Control sampling requires an active session')
            deadline = self.deadline if deadline is None else min(deadline, self.deadline)
        counts = struct.unpack('>II', self.query(78, deadline))
        stamp = self.clock()
        currents = struct.unpack('>hh', self.query(49, deadline))
        status = int.from_bytes(self.query(90, deadline), 'big')
        pwm = struct.unpack('>hh', self.query(48, deadline))
        row = {'phase': phase, 'monotonic_s': stamp, 'completed_monotonic_s': self.clock(),
               'counts': list(counts), 'currents_raw': list(currents),
               'currents_a': [v / 100 for v in currents], 'status': status,
               'status_hex': f'0x{status:08x}', 'pwms': list(pwm)}
        error = None
        if status & ~ALLOWED_STATUS:
            error = 'Unexpected controller status ' + row['status_hex']
        elif any(abs(value) > 3.0 for value in row['currents_a']):
            error = 'Reported current exceeds 3 A trial guard'
        if phase == 'control' and self.previous is not None:
            dt = stamp - self.previous['monotonic_s']
            if not 0 < dt <= .15:
                error = 'Control sample interval outside (0, 0.15] seconds'
            else:
                delta = [signed_delta(a, b) for a, b in zip(self.previous['counts'], counts)]
                row.update(delta_counts=delta, interval_s=dt,
                           rev_per_s=[delta[i] / CPR[i] / dt for i in range(2)])
                self.total_absolute = [self.total_absolute[i] + abs(delta[i]) for i in range(2)]
                row['absolute_counts'] = self.total_absolute.copy()
                if any(value > self.absolute_count_limit for value in self.total_absolute):
                    error = f'Accumulated absolute count guard exceeds {self.absolute_count_limit}'
                if any(abs(delta[i]) > CPR[i] * .3 * dt + 2 for i in range(2)):
                    error = 'Wheel speed guard exceeds 0.3 rev/s plus 2 counts'
        if error:
            row['guard_error'] = error
        try:
            self.sample_sink(row)
        except BaseException:
            self.fault = True
            self.armed = False
            raise
        if error:
            self._fail(error)
        self.last_sample = row
        if phase == 'control':
            self.previous = row
        return row

    def _stationary(self, phase, seconds=1.2):
        end = self.clock() + seconds
        window = []
        while self.clock() < end:
            tick = self.clock()
            row = self.sample(phase, deadline=end)
            if phase == 'preflight' and any(row['pwms']):
                self._fail('Preflight requires zero PWM')
            window.append(row)
            while len(window) > 2 and row['monotonic_s'] - window[1]['monotonic_s'] >= .25:
                window.pop(0)
            if len(window) >= 2 and row['monotonic_s'] - window[0]['monotonic_s'] >= .25:
                deltas = [[signed_delta(window[0]['counts'][i], r['counts'][i]) for r in window]
                          for i in range(2)]
                if all(max(values) - min(values) <= 2 for values in deltas) and all(not any(r['pwms']) for r in window):
                    return {'verified': True, 'stable_since_s': window[0]['monotonic_s'],
                            'verified_at_s': self.clock(), 'last_counts': row['counts'],
                            'pwms': row['pwms'], 'samples': len(window)}
            self.sleep(max(0., min(.05 - (self.clock() - tick), end - self.clock())))
        self._fail('No stationary zero-PWM window within 1.2 seconds')

    def preflight(self):
        if not self.identified or self.fault or self.used or self.preflight_passed:
            self._fail('Preflight cannot run in this transport state')
        timeout_raw = self.query(15)[0]
        volts = int.from_bytes(self.query(24), 'big') / 10
        if timeout_raw != 5 or not 5.9 <= volts <= 12.8:
            self._fail('Require timeout raw 5 and battery within 5.9..12.8 V')
        stationary = self._stationary('preflight')
        self.write_duty(0, 0)
        self.preflight_passed = True
        return {'timeout_raw': timeout_raw, 'battery_volts': volts, 'stationary': stationary}

    def arm(self, duration_s, active_channels=(1, 2)):
        channels = tuple(active_channels)
        if (self.fault or not self.preflight_passed or self.used or self.closed or
                type(duration_s) not in (int, float) or not math.isfinite(duration_s) or
                not 0 < duration_s <= self.max_duration_s or
                not channels or len(set(channels)) != len(channels) or
                any(type(channel) is not int or channel not in (1, 2) for channel in channels)):
            self._fail('Invalid single-session arm request')
        if self.last_sample is None or not 0 <= self.clock() - self.last_sample['monotonic_s'] <= .15:
            self._fail('Stationary preflight sample is stale')
        self.active_channels = channels
        self.deadline = self.clock() + duration_s
        self.used = self.armed = True
        self.previous = self.last_sample
        return self.deadline

    def stop_and_close(self):
        if self._stop_result is not None:
            return self._stop_result
        self._stopping = True
        self.armed = False
        result = {'zero_acked': False, 'stationary_verified': False, 'closed': False, 'attempts': []}
        try:
            if not self.identified or self.closed or self.tx_disabled:
                result['error'] = 'No identified open connection for stop'
            else:
                for index in range(3):
                    attempt = {'index': index + 1, 'started_monotonic_s': self.clock()}
                    try:
                        if self.fault or index:
                            self.sleep(.012)
                            self.serial.reset_input_buffer()
                        self.write_duty(0, 0)
                        attempt['success'] = result['zero_acked'] = True
                        self._stop_zero_acked = True
                    except BaseException as error:
                        attempt.update(success=False, error=repr(error))
                    result['attempts'].append(attempt)
                    if result['zero_acked']:
                        break
                if result['zero_acked']:
                    result['observation'] = self._stationary('final_stop')
                    result['stationary_verified'] = True
                else:
                    self.tx_disabled = True
                    result['error'] = 'Zero ACK unavailable; all TX disabled; physical cutoff required'
        except BaseException as error:
            result['error'] = repr(error)
        finally:
            self.tx_disabled = True
            try:
                if self.serial is not None:
                    self.serial.close()
                result['closed'] = True
            except BaseException as error:
                result['close_error'] = repr(error)
            self.closed = True
        self._stop_result = result
        return result
