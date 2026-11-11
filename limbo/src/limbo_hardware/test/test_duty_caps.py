"""Explicit cap boundary checks; fake serial only, no hardware access."""
import unittest
from limbo_hardware.roboclaw_bench import BenchTransport,GuardError,duty_packet
from limbo_hardware.speed_pi import PIConfig,WheelSpeedPI

class AckSerial:
    def __init__(self):self.writes=[]
    def write(self,packet):self.writes.append(packet);return len(packet)
    def read(self,n):return b'\xff'

def armed(cap=3276):
    serial=AckSerial()
    t=BenchTransport(serial,max_duty_raw=cap,clock=lambda:0.)
    t.identified=t.preflight_passed=t.armed=True
    t.deadline=5.;t.active_channels=(1,2);t.last_sample={'monotonic_s':0.}
    return t,serial

class DutyCapTests(unittest.TestCase):
    def test_default_keeps_10_percent_even_for_raw_exchange(self):
        t,s=armed()
        with self.assertRaises(GuardError):t.exchange(duty_packet(4095,0,max_duty_raw=4095))
        self.assertEqual(s.writes,[])
        with self.assertRaises(GuardError):duty_packet(3277,0)
        self.assertEqual(PIConfig().max_duty_raw,3276)

    def test_explicit_cap_allows_both_signs_and_zero(self):
        t,s=armed(4095)
        t.write_duty(4095,-4095);t.write_duty(0,0)
        self.assertEqual(s.writes,[duty_packet(4095,-4095,max_duty_raw=4095),duty_packet(0,0)])

    def test_never_crosses_selected_or_absolute_cap(self):
        t,s=armed(4000)
        with self.assertRaises(GuardError):t.write_duty(4001,0)
        self.assertEqual(s.writes,[])
        for cap in (True,4915.,0,-1,4916):
            with self.subTest(cap=cap),self.assertRaises((ValueError,GuardError)):
                BenchTransport(AckSerial(),max_duty_raw=cap)
        with self.assertRaises(GuardError):duty_packet(4096,0,max_duty_raw=4095)

    def test_pi_can_reach_explicit_cap_and_zero_resets(self):
        pi=WheelSpeedPI(PIConfig(max_duty_raw=4095))
        outputs=[pi.step(.2666666667,0.,.05) for _ in range(99)]
        self.assertGreater(max(v.duty_raw for v in outputs),3276)
        self.assertLessEqual(max(v.duty_raw for v in outputs),4095)
        self.assertEqual(pi.step(0.,0.,.05).duty_raw,0)
        self.assertEqual(pi.integral,0.)

    def test_higher_cap_does_not_bypass_expired_session(self):
        t,s=armed(4915);t.deadline=0.
        with self.assertRaises(GuardError):t.write_duty(4915,0)
        self.assertEqual(s.writes,[])

    def test_startup_cap_requires_explicit_selection_at_each_write_boundary(self):
        packet=duty_packet(4915,-4915,max_duty_raw=4915)
        for selected in (3276,4095):
            with self.subTest(selected=selected):
                t,s=armed(selected)
                with self.assertRaises(GuardError):t.exchange(packet)
                self.assertEqual(s.writes,[])
                t,s=armed(selected)
                with self.assertRaises(GuardError):t.write_duty(4915,-4915)
                self.assertEqual(s.writes,[])
        t,s=armed(4915)
        t.write_duty(4915,-4915);t.write_duty(0,0)
        self.assertEqual(s.writes,[packet,duty_packet(0,0)])
        for pair in ((4916,0),(0,-4916)):
            with self.assertRaises(GuardError):duty_packet(*pair,max_duty_raw=4915)

    def test_feedforward_at_new_ceiling_preserves_slew_sign_and_zero(self):
        for selected in (3276,4095,4915):
            for sign in (1.,-1.):
                pi=WheelSpeedPI(PIConfig(kp=.06,ki=.20,max_duty_raw=selected,feedforward_gain=.3375))
                previous=0.
                for _ in range(60):
                    row=pi.step(sign*.2666666667,0.,.05)
                    self.assertGreaterEqual(row.duty_raw*sign,0.)
                    self.assertLessEqual(abs(row.duty_raw),selected)
                    self.assertLessEqual(abs(row.output-previous),.15*.05+1/32767)
                    previous=row.output
                self.assertEqual(row.duty_raw,sign*selected)
                zero=pi.step(0.,sign*.1,.05)
                self.assertEqual((zero.duty_raw,zero.feedforward_output,pi.integral),(0,0.,0.))

if __name__=='__main__':unittest.main()
