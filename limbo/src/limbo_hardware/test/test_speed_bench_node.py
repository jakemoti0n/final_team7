"""Finite ROS trial adapter tests with a fake transport; no serial access."""
from dataclasses import asdict
import json
import math
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import Mock

import rclpy
from geometry_msgs.msg import Twist
from rclpy.parameter import Parameter
from rclpy.exceptions import InvalidParameterTypeException

from limbo_hardware.speed_bench_node import SpeedBenchNode, PER_WHEEL_CONTROLLER_MODEL
from limbo_hardware.speed_pi import PIConfig, WheelSpeedPI, CONTROLLER_MODEL
from limbo_hardware.roboclaw_bench import GuardError


class FakeTransport:
    def __init__(self, owner, *, wire_sink, sample_sink, max_duty_raw, extended_observation, extended_distance_observation=False):
        self.owner = owner
        self.max_duty_raw = max_duty_raw
        self.extended_observation = extended_observation
        self.extended_distance_observation = extended_distance_observation
        self.absolute_count_limit = 3000 if extended_distance_observation else 1500
        self.queries = []
        self.voltage_raw = 121
        self.query_error = None
        self.query_delay = 0.
        self.sample_sink = sample_sink
        self.open_calls = self.preflight_calls = self.stop_calls = 0
        self.arm_calls = []
        self.writes = []
        self.last_sample = None
        self.next_counts = [1000, 2000]
        self.closed = False
        self.serial = Mock()
        self.sample_error = None
        self.stop_error = None
        self.stop_signal_states = None
        self.stop_result = {'zero_acked': True, 'stationary_verified': True, 'closed': True}

    def open(self):
        self.open_calls += 1
        return 'USB Roboclaw 2x15A v4.4.9'

    def row(self, phase):
        return {'phase': phase, 'monotonic_s': self.owner.now,
                'completed_monotonic_s': self.owner.now,
                'counts': list(self.next_counts), 'pwms': [0, 0],
                'currents_raw': [0, 0], 'currents_a': [0., 0.],
                'status': 0x03000000, 'status_hex': '0x03000000'}

    def preflight(self):
        self.preflight_calls += 1
        self.last_sample = self.row('preflight')
        self.sample_sink(self.last_sample)
        return {'timeout_raw': 5, 'battery_volts': 12.1, 'stationary': {'verified': True}}

    def arm(self, duration, active_channels):
        self.arm_calls.append((duration, tuple(active_channels)))
        return self.owner.now + duration

    def sample(self, phase):
        if self.sample_error:
            raise self.sample_error
        self.last_sample = self.row(phase)
        self.sample_sink(self.last_sample)
        return self.last_sample

    def query(self, command, deadline=None):
        self.queries.append((command,deadline,self.owner.now))
        self.owner.now += self.query_delay
        if self.query_error:raise self.query_error
        return self.voltage_raw.to_bytes(2,'big')

    def write_duty(self, m1, m2):
        self.writes.append((m1, m2))

    def stop_and_close(self):
        self.stop_calls += 1
        self.stop_signal_states = tuple(signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM))
        if self.stop_error:
            raise self.stop_error
        self.writes.append((0, 0))
        # Emit the same stationary observations a real transport would provide.
        for _ in range(6):
            self.owner.now += .05
            self.last_sample = self.row('final_stop')
            self.sample_sink(self.last_sample)
        self.closed = True
        return dict(self.stop_result)


class SpeedBenchNodeTests(unittest.TestCase):
    def setUp(self):
        rclpy.init()
        self.temp = tempfile.TemporaryDirectory()
        self.now = 100.
        self.nodes = []
        self.transports = []

    def tearDown(self):
        for node in self.nodes:
            if not node.done:
                node._finish('test_cleanup')
            node.close_logs()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        self.temp.cleanup()

    def make(self, left=0., right=.2666666667, **overrides):
        values = {'enable_output': True, 'duration_seconds': 5.,
                  'record_dir': str(Path(self.temp.name) / str(len(self.nodes))),
                  'left_wheel_radius': .075, 'right_wheel_radius': .075,
                  'wheel_separation': .54, 'left_counts_per_revolution': 3688.,
                  'right_counts_per_revolution': 3607.,
                  'left_target_rad_s': left, 'right_target_rad_s': right}
        values.update(overrides)

        def factory(**kwargs):
            fake = FakeTransport(self, **kwargs)
            self.transports.append(fake)
            return fake

        node = SpeedBenchNode(parameter_overrides=[Parameter(k, value=v) for k, v in values.items()],
                              transport_factory=factory, monotonic=lambda: self.now)
        self.nodes.append(node)
        node.count_pub, node.joint_pub, node.target_pub, node.status_pub = Mock(), Mock(), Mock(), Mock()
        return node, self.transports[-1]

    @staticmethod
    def command(left=0., right=.2666666667):
        msg = Twist()
        msg.linear.x = .075 * (left + right) / 2
        msg.angular.z = .075 * (right - left) / .54
        return msg

    def ready_and_start(self, node, left=0., right=.2666666667):
        node._tick()
        self.assertEqual(node.state, 'ready')
        node._command(self.command(left, right))
        self.assertEqual(node.state, 'running')

    def step(self, node, seconds=.05):
        self.now += seconds
        node._tick()

    def test_default_distance_and_voltage_preserve_legacy_no_extra_queries(self):
        node,fake=self.make()
        self.assertFalse(fake.extended_distance_observation)
        self.assertEqual(fake.absolute_count_limit,1500)
        self.assertEqual(node.summary['distance_envelope'],'finite_distance_1500_counts_v1')
        self.assertEqual(node.summary['limits']['absolute_counts_per_motor'],1500)
        self.assertEqual(node.summary['voltage_telemetry'],{'enabled':False,
                          'every_guard_passed_control_samples':0,'range_volts':[5.9,12.8]})
        self.assertNotIn('voltage',node.files)
        self.assertFalse((node.folder/'voltage.jsonl').exists())
        self.ready_and_start(node)
        for _ in range(12):self.step(node)
        self.assertEqual(fake.queries,[])
        node._command(Twist())
        self.assertEqual(fake.queries,[])

    def test_extended_distance_requires_exact_reviewed_configuration_and_is_readonly(self):
        node,fake=self.make(left=.4,right=.4,duration_seconds=10.,extended_observation=True,
                            extended_distance_observation=True,record_voltage=True)
        self.assertTrue(fake.extended_distance_observation)
        self.assertEqual(fake.absolute_count_limit,3000)
        self.assertEqual(node.summary['limits']['absolute_counts_per_motor'],3000)
        self.assertEqual(node.summary['distance_envelope'],'finite_distance_3000_counts_v1')
        for name in ('extended_distance_observation','record_voltage'):
            self.assertTrue(node.describe_parameter(name).read_only)
            self.assertFalse(node.set_parameters([Parameter(name,value=False)])[0].successful)
        self.ready_and_start(node,left=.4,right=.4)
        self.assertEqual(fake.arm_calls,[(10.,(1,2))])
        self.step(node)
        node._command(Twist())
        self.assertEqual(fake.writes[-1],(0,0))

    def test_bad_new_flags_or_mixed_distance_configuration_refuse_before_device(self):
        base={'left':.4,'right':.4,'duration_seconds':10.,'extended_observation':True,
              'extended_distance_observation':True}
        invalid=[{'extended_observation':False},{'duration_seconds':5.},{'duration_seconds':9.},
                 {'left':0.},{'right':-.4},{'left_wheel_radius':.076},
                 {'right_wheel_radius':.076},{'wheel_separation':.55},
                 {'left_counts_per_revolution':3689.}]
        invalid += [{key:value} for key in ('extended_distance_observation','record_voltage')
                    for value in (0,1,'true',.0)]
        for changes in invalid:
            with self.subTest(changes=changes):
                values=dict(base);values.update(changes)
                with self.assertRaises((ValueError,InvalidParameterTypeException)):
                    self.make(**values)
                self.assertEqual(self.transports,[])
                self.assertEqual(list(Path(self.temp.name).iterdir()),[])

    def test_voltage_query_sequence_5_and_10_deadlines_and_record_fields(self):
        node,fake=self.make(record_voltage=True)
        self.ready_and_start(node)
        for _ in range(10):self.step(node)
        rows=[json.loads(x) for x in (node.folder/'voltage.jsonl').read_text().splitlines()]
        self.assertEqual([x['control_index'] for x in rows],[5,10])
        self.assertEqual([x[0] for x in fake.queries],[24,24])
        for row,query in zip(rows,fake.queries):
            self.assertEqual(query[1],min(row['sample_monotonic_s']+.15,node.deadline-.05))
            self.assertTrue(row['query_succeeded']);self.assertTrue(row['within_range'])
            self.assertEqual((row['raw_decivolts'],row['battery_volts']),(121,12.1))
            self.assertLessEqual(row['sample_monotonic_s'],row['query_started_monotonic_s'])
            self.assertLessEqual(row['query_started_monotonic_s'],row['query_finished_monotonic_s'])
            self.assertNotIn('error',row)
        self.assertEqual(node.summary['voltage_telemetry']['every_guard_passed_control_samples'],5)
        node._command(Twist())
        self.assertEqual(len(fake.queries),2)  # No extra queries during cleanup.

    def test_direction_guard_precedes_fifth_voltage_query(self):
        node,fake=self.make(record_voltage=True)
        self.ready_and_start(node)
        for _ in range(4):self.step(node)
        fake.next_counts[0]-=11
        self.step(node)
        self.assertTrue(node.done)
        self.assertEqual(fake.queries,[])
        self.assertEqual(fake.writes[-1],(0,0))
        self.assertEqual(node.control_steps,4)

    def test_voltage_crc_failure_or_range_fault_records_and_stops_before_next_output(self):
        for raw,error in ((121,GuardError('Invalid response length or CRC')),(58,None),(129,None)):
            with self.subTest(raw=raw,error=error):
                node,fake=self.make(record_voltage=True)
                self.ready_and_start(node)
                for _ in range(4):self.step(node)
                before=[x for x in fake.writes if any(x)]
                fake.voltage_raw=raw;fake.query_error=error
                self.step(node)
                self.assertEqual([x for x in fake.writes if any(x)],before)
                self.assertEqual(fake.writes[-1],(0,0))
                self.assertEqual(node.control_steps,4)
                self.assertEqual(node.summary['stop_reason'],'control_error')
                self.assertFalse(node.summary['passed'])
                rows=[json.loads(x) for x in (node.folder/'voltage.jsonl').read_text().splitlines()]
                self.assertEqual(len(rows),1)
                self.assertEqual(rows[0]['control_index'],5)
                self.assertIn('error',rows[0])
                self.assertEqual(rows[0]['query_succeeded'],error is None)
                self.assertIsNotNone(rows[0]['query_finished_monotonic_s'])
                if error is not None:self.assertIsNone(rows[0]['raw_decivolts'])
                else:self.assertFalse(rows[0]['within_range'])

    def test_late_successful_voltage_query_stops_at_reserved_deadline_without_write(self):
        node,fake=self.make(record_voltage=True)
        self.ready_and_start(node)
        for _ in range(4):self.step(node)
        node.deadline=self.now+.11
        fake.query_delay=.02
        before=[x for x in fake.writes if any(x)]
        self.step(node)
        self.assertEqual(node.summary['stop_reason'],'duration_complete')
        self.assertEqual([x for x in fake.writes if any(x)],before)
        self.assertEqual(node.control_steps,4)
        self.assertEqual(fake.writes[-1],(0,0))
        self.assertEqual(len(fake.queries),1)
        self.assertEqual(fake.queries[0][1],node.deadline-.05)

    def test_successful_but_stale_voltage_query_never_sends_output(self):
        node,fake=self.make(record_voltage=True)
        self.ready_and_start(node)
        for _ in range(4):self.step(node)
        fake.query_delay=.151
        before=[x for x in fake.writes if any(x)]
        self.step(node)
        self.assertEqual(node.summary['stop_reason'],'control_error')
        self.assertTrue(any('too old' in x for x in node.errors))
        self.assertEqual([x for x in fake.writes if any(x)],before)
        self.assertEqual(fake.writes[-1],(0,0))
        self.assertEqual(node.control_steps,4)

    def test_explicit_duty_limit_reaches_both_loops_and_transport(self):
        node, fake = self.make(max_duty_raw=4095)
        self.assertEqual(fake.max_duty_raw,4095)
        self.assertEqual([p.config.max_duty_raw for p in node.controllers],[4095,4095])
        self.assertEqual(node.summary['settings']['max_duty_raw'],4095)
        self.assertTrue(node.describe_parameter('max_duty_raw').read_only)

    def test_startup_ceiling_is_explicit_immutable_and_versioned(self):
        node,fake=self.make(max_duty_raw=4915,kp=.06,feedforward_gain=.3375,velocity_window_s=.1)
        self.assertEqual(fake.max_duty_raw,4915)
        self.assertEqual([p.config.max_duty_raw for p in node.controllers],[4915,4915])
        self.assertEqual(node.summary['settings']['max_duty_raw'],4915)
        self.assertEqual(node.summary['envelope'],'duty_ceiling_4915_v1')
        self.assertFalse(node.set_parameters([Parameter('max_duty_raw',value=3276)])[0].successful)
        self.ready_and_start(node)
        node._status()
        values={v.key:v.value for v in node.status_pub.publish.call_args.args[0].status[0].values}
        self.assertEqual(values['envelope'],'duty_ceiling_4915_v1')
        self.assertEqual(values['max_duty_raw'],'4915')
        self.step(node)
        node._command(Twist())
        self.assertEqual(fake.writes[-1],(0,0))

    def test_extended_observation_is_immutable_versioned_and_still_finite(self):
        node,fake=self.make(extended_observation=True,duration_seconds=10.)
        self.assertTrue(fake.extended_observation)
        self.assertEqual(node.summary['duration_envelope'],'finite_observation_10s_v1')
        self.assertEqual(node.summary['limits']['duration_ceiling_s'],10.)
        self.assertEqual(node.summary['limits']['absolute_counts_per_motor'],1500)
        self.assertFalse(node.set_parameters([Parameter('extended_observation',value=False)])[0].successful)
        self.ready_and_start(node)
        self.assertEqual(fake.arm_calls,[(10.,(1,))])
        self.step(node)
        self.now=node.deadline-.04;node._tick()
        self.assertEqual(node.summary['stop_reason'],'duration_complete')
        self.assertEqual(fake.writes[-1],(0,0))
        self.assertTrue(node.done)

    def test_default_duration_envelope_and_extension_boundaries(self):
        with self.assertRaisesRegex(ValueError,'duration'):self.make(duration_seconds=5.01)
        with self.assertRaisesRegex(ValueError,'duration'):self.make(extended_observation=True,duration_seconds=10.01)
        self.assertEqual(self.transports,[])
        node,fake=self.make()
        self.assertFalse(fake.extended_observation)
        self.assertEqual(node.summary['duration_envelope'],'finite_trial_5s_v1')
        self.assertEqual(node.summary['limits']['duration_ceiling_s'],5.)

    def test_exact_window_is_logged_immutable_and_used_with_interpolation(self):
        node,fake=self.make(velocity_window_s=.1)
        self.assertEqual(node.summary['controller_model'],'partial_headroom_feedforward_v2')
        self.assertEqual(node.summary['velocity_estimator'],'exact_window_linear_v1')
        result=node.set_parameters([Parameter('velocity_window_s',value=.15)])
        self.assertFalse(result[0].successful)
        self.assertEqual(node.velocity_estimator.window_s,.1)
        self.ready_and_start(node)
        fake.next_counts[0]+=3;self.step(node,.06)
        fake.next_counts[0]+=5;self.step(node,.05)
        # At t=.11, the .01 boundary interpolates .5 counts between 0 and 3.
        self.assertAlmostEqual(node.last_control['filter_span_s'],.1)
        self.assertAlmostEqual(node.last_control['measured_left_right_rad_s'][1],7.5*math.tau/3607/.1)
        self.step(node,.05)
        self.assertAlmostEqual(node.last_control['measured_left_right_rad_s'][1],5.*math.tau/3607/.1)
        self.assertAlmostEqual(node.last_control['filter_start_s'],self.now-.1)
        self.assertEqual(node.last_control['velocity_window_s'],.1)

    def test_invalid_velocity_window_refuses_before_transport_creation(self):
        with self.assertRaisesRegex(ValueError,'velocity_window_s'):
            self.make(velocity_window_s=.09)
        self.assertEqual(self.transports,[])

    def test_feedforward_reaches_controllers_and_is_immutable(self):
        node,fake=self.make(feedforward_gain=.3375,velocity_window_s=.1,kp=.06)
        self.assertEqual([p.config.feedforward_gain for p in node.controllers],[.3375,.3375])
        self.assertEqual(node.summary['settings']['feedforward_gain'],.3375)
        self.assertFalse(node.set_parameters([Parameter('feedforward_gain',value=0.)])[0].successful)
        self.ready_and_start(node);self.step(node)
        self.assertGreater(node.last_control['pi_left_right'][1]['feedforward_output'],0.)
        self.assertEqual(node.last_control['pi_left_right'][0]['feedforward_output'],0.)
        node._command(Twist())
        self.assertEqual(fake.writes[-1],(0,0))

    def test_per_wheel_feedforward_is_explicit_readonly_and_maps_left_to_m2(self):
        node,fake=self.make(left=.4,right=.4,feedforward_gain=.25,
                            left_feedforward_gain=.2375,right_feedforward_gain=.2625,
                            kp=.1,ki=.2,max_duty_raw=4915,velocity_window_s=.1)
        self.assertEqual([p.config.feedforward_gain for p in node.controllers],[.2375,.2625])
        self.assertEqual(node.summary['effective_left_right_feedforward_gain'],[.2375,.2625])
        self.assertEqual(node.summary['controller_model'],PER_WHEEL_CONTROLLER_MODEL)
        self.assertEqual(node.summary['settings']['feedforward_gain'],.25)
        for name in ('left_feedforward_gain','right_feedforward_gain'):
            self.assertTrue(node.describe_parameter(name).read_only)
            self.assertFalse(node.set_parameters([Parameter(name,value=.25)])[0].successful)
        self.ready_and_start(node,left=.4,right=.4)
        for _ in range(4):self.step(node)
        left,right=node.last_control['pi_left_right']
        self.assertAlmostEqual(left['feedforward_output'],.2375*left['ramped_rad_s'])
        self.assertAlmostEqual(right['feedforward_output'],.2625*right['ramped_rad_s'])
        self.assertGreater(right['duty_raw'],left['duty_raw'])
        self.assertEqual(fake.writes[-1],(right['duty_raw'],left['duty_raw']))
        node._status()
        values={v.key:v.value for v in node.status_pub.publish.call_args.args[0].status[0].values}
        self.assertEqual(values['effective_left_feedforward_gain'],'0.2375')
        self.assertEqual(values['effective_right_feedforward_gain'],'0.2625')
        self.assertEqual(values['controller_model'],PER_WHEEL_CONTROLLER_MODEL)
        node._command(Twist())
        self.assertEqual(fake.writes[-1],(0,0))
        self.assertTrue(node.summary['stop']['stationary_verified'])

    def test_one_explicit_feedforward_overrides_only_its_side_and_versions_selection(self):
        for side,expected in (('left',[0.,.25]),('right',[.25,0.])):
            node,_=self.make(feedforward_gain=.25,**{side+'_feedforward_gain':0.})
            self.assertEqual([p.config.feedforward_gain for p in node.controllers],expected)
            self.assertEqual(node.summary['effective_left_right_feedforward_gain'],expected)
            self.assertEqual(node.summary['controller_model'],PER_WHEEL_CONTROLLER_MODEL)

    def test_default_feedforward_is_exactly_legacy_for_complete_control_results(self):
        node,fake=self.make(left=.4,right=.4,feedforward_gain=.25,max_duty_raw=4915)
        legacy=[WheelSpeedPI(PIConfig(feedforward_gain=.25,max_duty_raw=4915)) for _ in range(2)]
        self.assertEqual(node.summary['controller_model'],CONTROLLER_MODEL)
        self.assertEqual(node.summary['effective_left_right_feedforward_gain'],[.25,.25])
        for key in ('left_feedforward_gain','right_feedforward_gain'):
            self.assertEqual(node.summary['settings'][key],-1.)
        self.ready_and_start(node,left=.4,right=.4)
        for _ in range(12):
            self.step(node)
            row=node.last_control
            expected=[asdict(pi.step(target,measured,row['dt'])) for pi,target,measured in
                      zip(legacy,node.expected,row['measured_left_right_rad_s'])]
            self.assertEqual(row['pi_left_right'],expected)
            self.assertEqual(fake.writes[-1],(expected[1]['duty_raw'],expected[0]['duty_raw']))
        node._command(Twist())
        self.assertEqual(fake.writes[-1],(0,0))

    def test_bad_per_wheel_or_common_feedforward_refuses_before_device_or_record_creation(self):
        for side in ('left','right'):
            for value in (-2.,-.1,.376,float('nan'),float('inf'),float('-inf'),True,False,'0.25'):
                with self.subTest(side=side,value=value):
                    with self.assertRaises((ValueError,InvalidParameterTypeException)):
                        self.make(**{side+'_feedforward_gain':value})
                    self.assertEqual(self.transports,[])
                    self.assertEqual(list(Path(self.temp.name).iterdir()),[])
        with self.assertRaisesRegex(ValueError,'feedforward_gain'):
            self.make(feedforward_gain=.376,left_feedforward_gain=.2375,right_feedforward_gain=.2625)
        self.assertEqual(self.transports,[])
        self.assertEqual(list(Path(self.temp.name).iterdir()),[])

    def test_invalid_feedforward_refuses_before_transport_creation(self):
        with self.assertRaisesRegex(ValueError,'feedforward_gain'):
            self.make(feedforward_gain=.376)
        self.assertEqual(self.transports,[])

    def test_invalid_duty_limit_refuses_before_transport_creation(self):
        with self.assertRaisesRegex(ValueError,'max_duty_raw'):
            self.make(max_duty_raw=4916)
        self.assertEqual(self.transports,[])

    def test_enable_false_refuses_before_transport_creation(self):
        with self.assertRaisesRegex(ValueError, 'enable_output'):
            self.make(enable_output=False)
        self.assertEqual(self.transports, [])

    def test_expected_one_command_starts_single_finite_session(self):
        node, fake = self.make()
        self.assertEqual(fake.open_calls, 0)
        self.assertEqual(fake.writes, [])
        self.ready_and_start(node)
        self.assertEqual(fake.open_calls, 1)
        self.assertEqual(fake.preflight_calls, 1)
        self.assertEqual(fake.arm_calls, [(5., (1,))])
        deadline = node.deadline
        self.step(node)
        self.assertEqual(len(fake.writes), 1)
        self.assertGreater(fake.writes[0][0], 0)
        self.assertEqual(fake.writes[0][1], 0)
        self.assertEqual(node.deadline, deadline)
        self.assertEqual(node.control_steps, 1)
        self.assertEqual(node.target_pub.publish.call_args.args[0].name,
                         ['left_wheel_joint', 'right_wheel_joint'])

    def test_explicit_zero_stops_and_cannot_restart(self):
        node, fake = self.make()
        self.ready_and_start(node)
        self.step(node)
        node._command(Twist())
        self.assertTrue(node.done)
        self.assertEqual(node.summary['stop_reason'], 'explicit_zero')
        self.assertTrue(node.summary['passed'])
        self.assertEqual(fake.stop_calls, 1)
        self.assertEqual(fake.writes[-1], (0, 0))
        writes = list(fake.writes)
        node._command(self.command())
        self.step(node)
        self.assertEqual(fake.writes, writes)
        self.assertEqual(len(fake.arm_calls), 1)

    def test_wrong_or_malformed_command_stops_without_arming(self):
        for kind in ('wrong', 'nonfinite', 'sideways'):
            with self.subTest(kind=kind):
                node, fake = self.make()
                node._tick()
                msg = self.command(right=.2) if kind == 'wrong' else self.command()
                if kind == 'nonfinite': msg.linear.x = math.nan
                if kind == 'sideways': msg.linear.y = .01
                node._command(msg)
                self.assertTrue(node.done)
                self.assertFalse(node.summary['passed'])
                self.assertEqual(fake.arm_calls, [])
                self.assertEqual(fake.preflight_calls, 0)
                self.assertEqual(fake.writes, [(0, 0)])

    def test_duplicate_nonzero_stops_instead_of_extending(self):
        node, fake = self.make()
        self.ready_and_start(node)
        deadline = node.deadline
        self.step(node)
        node._command(self.command())
        self.assertTrue(node.done)
        self.assertEqual(node.deadline, deadline)
        self.assertEqual(len(fake.arm_calls), 1)
        self.assertFalse(node.summary['passed'])
        self.assertTrue(any('one nonzero' in error for error in node.errors))
        self.assertEqual(fake.writes[-1], (0, 0))

    def test_deadline_finishes_before_any_further_nonzero_write(self):
        node, fake = self.make()
        self.ready_and_start(node)
        self.step(node)
        count = len(fake.writes)
        self.now = node.deadline
        node._tick()
        self.assertTrue(node.summary['passed'])
        self.assertEqual(node.summary['stop_reason'], 'duration_complete')
        self.assertEqual(fake.writes[count:], [(0, 0)])
        node._tick()
        self.assertEqual(fake.stop_calls, 1)

    def test_interval_fault_stops_without_using_stale_feedback(self):
        node, fake = self.make()
        self.ready_and_start(node)
        self.step(node, .2)
        self.assertTrue(node.done)
        self.assertFalse(node.summary['passed'])
        self.assertEqual(node.control_steps, 0)
        self.assertEqual(fake.writes, [(0, 0)])
        self.assertTrue(any('interval' in error.lower() for error in node.errors))

    def test_transport_exception_stops_and_preserves_error(self):
        node, fake = self.make()
        self.ready_and_start(node)
        fake.sample_error = RuntimeError('synthetic CRC failure')
        self.step(node)
        self.assertTrue(node.done)
        self.assertFalse(node.summary['passed'])
        self.assertEqual(fake.writes, [(0, 0)])
        self.assertTrue(any('synthetic CRC failure' in error for error in node.errors))

    def test_m2_negative_raw_change_is_positive_left_feedback_and_output(self):
        node, fake = self.make(left=.2666666667, right=0.)
        self.ready_and_start(node, left=.2666666667, right=0.)
        self.step(node)
        self.assertEqual(fake.arm_calls, [(5., (2,))])
        self.assertEqual(fake.writes[0][0], 0)
        self.assertGreater(fake.writes[0][1], 0)
        fake.next_counts[1] -= 1
        self.step(node)
        count = node.count_pub.publish.call_args.args[0]
        joint = node.joint_pub.publish.call_args.args[0]
        self.assertEqual((count.right_delta, count.left_delta), (0, 1))
        self.assertEqual((count.right_total, count.left_total), (0, 1))
        self.assertEqual(joint.name, ['right_wheel_joint', 'left_wheel_joint'])
        self.assertEqual(joint.velocity[0], 0.)
        self.assertAlmostEqual(joint.velocity[1], math.tau/3688/.05)
        self.assertEqual(fake.writes[-1][0], 0)
        self.assertGreaterEqual(fake.writes[-1][1], 0)
        self.assertGreater(node.last_control['measured_left_right_rad_s'][0], 0.)

    def test_reverse_m1_keeps_negative_output_with_negative_feedback(self):
        node, fake = self.make(right=-.2666666667)
        self.ready_and_start(node, right=-.2666666667)
        self.step(node)
        self.assertLess(fake.writes[0][0], 0)
        self.assertEqual(fake.writes[0][1], 0)
        fake.next_counts[0] -= 1
        self.step(node)
        self.assertLess(node.last_control['measured_left_right_rad_s'][1], 0.)
        self.assertLessEqual(fake.writes[-1][0], 0)

    def test_opposite_direction_and_inactive_wheel_motion_abort(self):
        for counts in ([989, 2000], [1000, 1979]):
            with self.subTest(counts=counts):
                node, fake = self.make()
                self.ready_and_start(node)
                fake.next_counts = counts
                self.step(node)
                self.assertTrue(node.done)
                self.assertFalse(node.summary['passed'])
                self.assertEqual(fake.writes, [(0, 0)])

    def test_failed_stationary_stop_is_not_reported_as_pass(self):
        node, fake = self.make()
        self.ready_and_start(node)
        fake.stop_result['stationary_verified'] = False
        node._command(Twist())
        self.assertFalse(node.summary['passed'])
        saved = json.loads((node.folder/'summary.json').read_text())
        self.assertFalse(saved['passed'])
        self.assertFalse(saved['stop']['stationary_verified'])

    def test_cleanup_ignores_repeat_signals_and_publishes_real_stop_samples(self):
        node, fake = self.make()
        self.ready_and_start(node)
        self.step(node)
        fake.next_counts[0] += 1
        self.step(node)
        self.assertGreater(node.joint_pub.publish.call_args.args[0].velocity[0], 0.)
        before = node.joint_pub.publish.call_count
        handlers = tuple(signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM))
        node._command(Twist())
        self.assertEqual(fake.stop_signal_states, (signal.SIG_IGN, signal.SIG_IGN))
        self.assertEqual(tuple(signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)), handlers)
        self.assertEqual(node.joint_pub.publish.call_count-before, 6)
        self.assertEqual(list(node.joint_pub.publish.call_args.args[0].velocity), [0., 0.])
        self.assertTrue(node.summary['passed'])

    def test_unexpected_cleanup_error_records_failure_and_attempts_zero_close(self):
        node, fake = self.make()
        self.ready_and_start(node)
        self.step(node)
        fake.stop_error = RuntimeError('synthetic cleanup failure')
        node._command(Twist())
        self.assertTrue(node.done)
        self.assertFalse(node.summary['passed'])
        self.assertEqual(fake.writes[-1], (0, 0))
        fake.serial.close.assert_called_once()
        self.assertTrue(fake.tx_disabled)
        self.assertTrue(any('cleanup failure' in error for error in node.errors))


if __name__ == '__main__':
    unittest.main()
