"""One bounded ROS wheel-speed trial. This is not a continuous drive bridge."""
from dataclasses import asdict, replace
import json
import math
from pathlib import Path
import signal
import time
import uuid

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from rclpy.signals import SignalHandlerOptions
from rcl_interfaces.msg import ParameterDescriptor, SetParametersResult
from geometry_msgs.msg import Twist
from sensor_msgs.msg import JointState
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from limbo_interfaces.msg import WheelEncoderCounts

from .drive_preview_core import calculate_drive_targets
from .roboclaw_readonly import CounterTracker
from .roboclaw_bench import BenchTransport, GuardError, DUTY_ENVELOPE, observation_duration_limit, observation_count_limit
from .speed_pi import CONTROLLER_MODEL, PIConfig, WheelSpeedPI
from .speed_estimator import VELOCITY_ESTIMATOR, CountWindowEstimator


# v3 describes per-wheel gain selection; the underlying PI mathematics is unchanged.
PER_WHEEL_CONTROLLER_MODEL = 'partial_headroom_feedforward_per_wheel_v3'


def _resolve_wheel_pi_configs(common_config, left_gain, right_gain):
    """Return L,R configs; only numeric -1 inherits the already validated common gain."""
    configs=[]
    for gain in (left_gain,right_gain):
        inherit=(not isinstance(gain,bool) and isinstance(gain,(int,float)) and gain==-1)
        # PIConfig.__post_init__ validates explicit type, finiteness, and 0..0.375 bounds.
        configs.append(common_config if inherit else replace(common_config,feedforward_gain=gain))
    return tuple(configs)


class SpeedBenchNode(Node):
    def __init__(self, *, parameter_overrides=None, transport_factory=BenchTransport,
                 monotonic=time.monotonic):
        super().__init__('wheel_speed_bench', parameter_overrides=parameter_overrides)
        self.mono=monotonic
        defaults={
            'enable_output': False, 'duration_seconds': 5.0, 'record_dir': '',
            'extended_observation': False,
            'extended_distance_observation': False, 'record_voltage': False,
            'left_wheel_radius': 0.0, 'right_wheel_radius': 0.0, 'wheel_separation': 0.0,
            'left_counts_per_revolution': 0.0, 'right_counts_per_revolution': 0.0,
            'left_target_rad_s': 0.0, 'right_target_rad_s': 0.0,
            'kp': .10, 'ki': .20, 'max_duty_raw': 3276, 'velocity_window_s': .20,
            'feedforward_gain': 0.0,
            'left_feedforward_gain': -1.0, 'right_feedforward_gain': -1.0,
        }
        descriptor=ParameterDescriptor(read_only=True)
        self.s={k:self.declare_parameter(k,v,descriptor).value for k,v in defaults.items()}
        if self.s['enable_output'] is not True:
            raise ValueError('Explicit enable_output=true is required for a bounded physical trial')
        if self.get_parameter('use_sim_time').value:
            raise ValueError('Physical control requires use_sim_time=false')
        self.add_on_set_parameters_callback(lambda ps:SetParametersResult(
            successful=not any(p.name=='use_sim_time' for p in ps),reason='Physical clock immutable'))
        self.max_duration_s=observation_duration_limit(self.s['extended_observation'])
        self.absolute_count_limit=observation_count_limit(
            self.s['extended_distance_observation'],self.s['extended_observation'])
        if type(self.s['record_voltage']) is not bool:
            raise ValueError('record_voltage must be bool')
        self.distance_envelope=('finite_distance_3000_counts_v1' if self.s['extended_distance_observation']
                                else 'finite_distance_1500_counts_v1')
        self.duration_envelope=('finite_observation_10s_v1' if self.s['extended_observation']
                                else 'finite_trial_5s_v1')
        duration=self.s['duration_seconds']
        if type(duration) not in (int,float) or not math.isfinite(duration) or not 0<duration<=self.max_duration_s:
            raise ValueError(f'Trial duration must be within (0,{self.max_duration_s:g}] seconds')
        self.expected=(self.s['left_target_rad_s'],self.s['right_target_rad_s'])
        if (not all(math.isfinite(v) and abs(v)<=.4 for v in self.expected)
                or not any(self.expected)):
            raise ValueError('At least one requested wheel speed within +/-0.4 rad/s required')
        self._targets(Twist())  # Validate the shared geometry and provisional CPR.
        if (self.s['left_counts_per_revolution'],self.s['right_counts_per_revolution'])!=(3674.,3687.):
            raise ValueError('Review fixed bench guards before changing provisional CPR')
        if self.s['extended_distance_observation']:
            geometry=(self.s['left_wheel_radius'],self.s['right_wheel_radius'],self.s['wheel_separation'])
            if duration!=10. or self.expected!=(.4,.4) or geometry!=(.075,.075,.53):
                raise ValueError('Extended distance observation requires 10s, both +0.4 rad/s, and geometry .075/.075/.53')
        # 벤치의 15 % 상한은 벤치가 직접 지킨다 (PIConfig는 물리 최대까지 허용하고, 주행 브리지는 자기 천장을 따로 둔다)
        if type(self.s['max_duty_raw']) is not int or not 1<=self.s['max_duty_raw']<=4915:
            raise ValueError('max_duty_raw must be an integer in 1..4915 for the bench')
        config=PIConfig(kp=self.s['kp'],ki=self.s['ki'],max_duty_raw=self.s['max_duty_raw'],
                        feedforward_gain=self.s['feedforward_gain'])
        configs=_resolve_wheel_pi_configs(config,self.s['left_feedforward_gain'],
                                          self.s['right_feedforward_gain'])
        self.effective_feedforward_gains=tuple(c.feedforward_gain for c in configs)
        self.controller_model=(CONTROLLER_MODEL if all(c is config for c in configs)
                               else PER_WHEEL_CONTROLLER_MODEL)
        self.controllers=[WheelSpeedPI(c) for c in configs]
        self.velocity_estimator=CountWindowEstimator(
            self.s['left_counts_per_revolution'],self.s['right_counts_per_revolution'],
            self.s['velocity_window_s'])
        if not self.s['record_dir']:
            raise ValueError('A fresh record_dir is required')
        self.folder=Path(self.s['record_dir'])
        self.folder.mkdir(parents=True,exist_ok=False)
        log_names=('wire','samples','control','events')+(('voltage',) if self.s['record_voltage'] else ())
        self.files={name:(self.folder/(name+'.jsonl')).open('w',buffering=1) for name in log_names}
        self.transport=transport_factory(max_duty_raw=self.s['max_duty_raw'],
                                         extended_distance_observation=self.s['extended_distance_observation'],
                                         extended_observation=self.s['extended_observation'],wire_sink=lambda r:self._record('wire',r),
                                         sample_sink=self._transport_sample)
        self.state='opening'
        self.done=False
        self.opened=False
        self.started=self.mono()
        self.deadline=None
        self.previous=None
        self.tracker=CounterTracker(signs=(1,-1))
        self.session=str(uuid.uuid4())
        self.sequence=0
        self.control_steps=0
        self.last_control=None
        self.errors=[]
        self.summary={'settings':self.s,'session_id':self.session,'passed':False,
                      'mode':'one_bounded_ros_speed_trial','configuration_writes':False,
                      'controller_model':self.controller_model,'velocity_estimator':VELOCITY_ESTIMATOR,
                      'envelope':DUTY_ENVELOPE,'duration_envelope':self.duration_envelope}
        self.summary['effective_left_right_feedforward_gain']=list(self.effective_feedforward_gains)
        self.summary['distance_envelope']=self.distance_envelope
        self.summary['voltage_telemetry']={'enabled':self.s['record_voltage'],
            'every_guard_passed_control_samples':5 if self.s['record_voltage'] else 0,
            'range_volts':[5.9,12.8]}
        self.summary['limits']={
            'duration_ceiling_s':self.max_duration_s,'duration_requested_s':duration,
            'max_duty_raw':self.s['max_duty_raw'],'absolute_max_duty_raw':4915,
            'reported_current_a':3.0,'speed_rev_s':0.3,'speed_extra_counts':2,
            'absolute_counts_per_motor':self.absolute_count_limit,'feedback_max_age_s':0.15,
            'control_interval_min_s':0.02,'control_interval_max_s':0.15,
            'target_max_rad_s':0.4,'target_slew_rad_s2':0.4,'output_slew_per_s':0.15,
            'inactive_wheel_counts':20,'opposite_direction_counts':10,
            'required_board_timeout_raw':5,'serial_timeout_s':0.09,
            'stationary_observation_max_s':1.2}
        self.count_pub=self.create_publisher(WheelEncoderCounts,'/wheel/encoder_counts',5)
        self.joint_pub=self.create_publisher(JointState,'/wheel/joint_states',5)
        self.target_pub=self.create_publisher(JointState,'/limbo/drive_bench/target_joint_states',5)
        self.status_pub=self.create_publisher(DiagnosticArray,'/limbo/drive_bench/status',5)
        self.command_sub=self.create_subscription(Twist,'/limbo/drive_bench/cmd_vel',self._command,1)
        self.timer=self.create_timer(.05,self._tick)
        self.status_timer=self.create_timer(.25,self._status)

    def _record(self,name,row):
        self.files[name].write(json.dumps(row,allow_nan=False)+'\n')

    def _record_voltage(self,row):
        # Index is the upcoming guarded control sample, even if this query aborts its write.
        voltage={'control_index':self.control_steps+1,'sample_monotonic_s':row['monotonic_s'],
                 'query_started_monotonic_s':self.mono(),'query_finished_monotonic_s':None,
                 'raw_decivolts':None,'battery_volts':None,'query_succeeded':False,'within_range':None}
        try:
            payload=self.transport.query(24,deadline=min(row['monotonic_s']+.15,self.deadline-.05))
            if len(payload)!=2:raise GuardError('Battery voltage response must contain two bytes')
            raw=int.from_bytes(payload,'big')
            voltage.update(raw_decivolts=raw,battery_volts=raw/10.,query_succeeded=True)
            voltage['within_range']=5.9<=voltage['battery_volts']<=12.8
            if not voltage['within_range']:
                raise GuardError('Battery voltage outside existing preflight range 5.9..12.8 V')
        except BaseException as error:
            voltage['error']=repr(error)
            raise
        finally:
            voltage['query_finished_monotonic_s']=self.mono()
            self._record('voltage',voltage)

    def _transport_sample(self,row):
        self._record('samples',row)
        # Publish actual deceleration and stable zero velocity during cleanup.
        if row['phase']=='final_stop' and self.previous is not None:
            dt=row['monotonic_s']-self.previous['monotonic_s']
            if dt>0:
                self._publish_feedback(row,dt)
                self.previous=row

    def _targets(self,msg):
        values=(msg.linear.x,msg.linear.y,msg.linear.z,msg.angular.x,msg.angular.y,msg.angular.z)
        if not all(math.isfinite(v) for v in values) or any(values[i]!=0 for i in (1,2,3,4)):
            raise ValueError('Invalid differential-drive Twist')
        return calculate_drive_targets(msg.linear.x,msg.angular.z,
            left_radius_m=self.s['left_wheel_radius'],right_radius_m=self.s['right_wheel_radius'],
            wheel_separation_m=self.s['wheel_separation'],
            left_counts_per_revolution=self.s['left_counts_per_revolution'],
            right_counts_per_revolution=self.s['right_counts_per_revolution'])

    def _command(self,msg):
        if self.done:return
        try:
            values=self._targets(msg)
            requested=(values.left.angular_rad_s,values.right.angular_rad_s)
            if not any(requested):
                self._finish('explicit_zero')
                return
            if self.state!='ready':
                raise GuardError('Only one nonzero ROS command is accepted per trial')
            if any(abs(a-b)>1e-8 for a,b in zip(requested,self.expected)):
                raise GuardError('ROS target differs from the explicitly configured trial target')
            self._record('events',{'event':'command_received','monotonic_s':self.mono(),
                                  'linear_m_s':msg.linear.x,'angular_rad_s':msg.angular.z,
                                  'left_right_rad_s':list(requested)})
            self.summary['preflight']=self.transport.preflight()
            self.previous=self.transport.last_sample
            self._publish_feedback(self.previous,None)
            self.velocity_estimator.update(self.previous['monotonic_s'],0,0)
            channels=tuple(ch for ch,value in ((1,self.expected[1]),(2,self.expected[0])) if value)
            self.deadline=self.transport.arm(self.s['duration_seconds'],active_channels=channels)
            self.next_tick=self.mono()+.05
            self.state='running'
            self.summary['armed_monotonic_s']=self.mono()
            self.summary['deadline_monotonic_s']=self.deadline
            self._status()
        except Exception as error:
            self.errors.append(type(error).__name__+': '+str(error))
            self._finish('command_error')

    def _publish_feedback(self,row,dt):
        reading=self.tracker.update(tuple(row['counts']))
        stamp=self.get_clock().now().to_msg()
        count=WheelEncoderCounts()
        count.header.stamp=stamp
        count.session_id=self.session
        count.sequence=self.sequence
        count.baseline=reading.baseline
        count.m1_raw,count.m2_raw=reading.raw
        count.right_delta,count.left_delta=reading.signed_forward_delta
        count.right_total,count.left_total=reading.signed_forward_total
        self.count_pub.publish(count)
        joint=JointState()
        joint.header.stamp=stamp
        joint.name=['right_wheel_joint','left_wheel_joint']
        cpr=(self.s['right_counts_per_revolution'],self.s['left_counts_per_revolution'])
        joint.position=[n*math.tau/c for n,c in zip(reading.signed_forward_total,cpr)]
        if dt is not None:
            joint.velocity=[n*math.tau/c/dt for n,c in zip(reading.signed_forward_delta,cpr)]
        self.joint_pub.publish(joint)
        self.sequence+=1
        return count,joint

    def _tick(self):
        if self.done:return
        try:
            if self.state=='opening':
                self.summary['firmware']=self.transport.open()
                self.opened=True
                self.state='ready'
                self._status()
                return
            if self.state=='ready':
                if self.mono()-self.started>30:self._finish('no_command')
                return
            if self.state!='running':return
            now=self.mono()
            if now>=self.deadline-.05:
                self._finish('duration_complete')
                return
            if now<self.next_tick:return
            row=self.transport.sample('control')
            dt=row['monotonic_s']-self.previous['monotonic_s']
            if not .02<=dt<=.15:raise GuardError('Control sample interval outside .02..0.15 s')
            count,joint=self._publish_feedback(row,dt)
            self.previous=row
            estimate=self.velocity_estimator.update(row['monotonic_s'],count.left_total,count.right_total)
            if estimate is None:raise GuardError('Missing velocity estimator baseline')
            span=estimate.span_s
            measured=(estimate.left_rad_s,estimate.right_rad_s)
            for expected,total in zip(self.expected,(count.left_total,count.right_total)):
                if expected and total*(1 if expected>0 else -1)<-10:
                    raise GuardError('Encoder moved opposite the configured wheel direction')
                if not expected and abs(total)>20:
                    raise GuardError('Inactive wheel moved more than 20 counts')
            if self.s['record_voltage'] and (self.control_steps+1)%5==0:
                self._record_voltage(row)
                after_query=self.mono()
                if after_query>=self.deadline-.05:
                    self._finish('duration_complete')
                    return
                if not 0<=after_query-row['monotonic_s']<=.15:
                    raise GuardError('Voltage query left verified feedback too old for output')
            outputs=[pi.step(target,actual,dt) for pi,target,actual in zip(self.controllers,self.expected,measured)]
            # Both motor-positive duty directions are physical forward. Encoder M2
            # sign normalization has already happened before the PI calculation.
            duties=(outputs[1].duty_raw,outputs[0].duty_raw)
            self.transport.write_duty(*duties)
            target=JointState()
            target.header.stamp=joint.header.stamp
            target.header.frame_id='base_footprint'
            target.name=['left_wheel_joint','right_wheel_joint']
            target.velocity=[r.ramped_rad_s for r in outputs]
            self.target_pub.publish(target)
            self.last_control={'monotonic_s':row['monotonic_s'],'dt':dt,
                'counts_raw_m1_m2':row['counts'],'left_total':count.left_total,'right_total':count.right_total,
                'requested_left_right_rad_s':list(self.expected),'measured_left_right_rad_s':list(measured),
                'instantaneous_right_left_rad_s':list(joint.velocity),'filter_span_s':span,
                'filter_start_s':estimate.window_start_s,'velocity_window_s':self.s['velocity_window_s'],
                'pi_left_right':[asdict(v) for v in outputs],'duty_m1_m2':list(duties),
                'pwms_before_write':row['pwms'],'current_a':row['currents_a'],'status':row['status']}
            self._record('control',self.last_control)
            self.control_steps+=1
            self.next_tick=row['monotonic_s']+.04
        except Exception as error:
            self.errors.append(type(error).__name__+': '+str(error))
            self._finish('control_error')

    def _status(self):
        if not self.context.ok():return
        msg=DiagnosticArray()
        msg.header.stamp=self.get_clock().now().to_msg()
        status=DiagnosticStatus(name='limbo/wheel_speed_bench',hardware_id='roboclaw_2x15A')
        status.level=DiagnosticStatus.ERROR if self.errors else DiagnosticStatus.OK
        status.message=self.state
        values={'state':self.state,'mode':'finite_speed_trial','control_steps':self.control_steps,
                'expected_left_rad_s':self.expected[0],'expected_right_rad_s':self.expected[1],
                'max_duty_raw':self.s['max_duty_raw'],'duration_max_s':self.s['duration_seconds'],
                'velocity_window_s':self.s['velocity_window_s'],
                'distance_envelope':self.distance_envelope,'absolute_counts_per_motor':self.absolute_count_limit,
                'record_voltage':self.s['record_voltage'],
                'feedforward_gain':self.s['feedforward_gain'],
                'effective_left_feedforward_gain':self.effective_feedforward_gains[0],
                'effective_right_feedforward_gain':self.effective_feedforward_gains[1],
                'controller_model':self.controller_model,'velocity_estimator':VELOCITY_ESTIMATOR,
                      'envelope':DUTY_ENVELOPE,'duration_envelope':self.duration_envelope}
        if self.last_control:
            for index,side in enumerate(('left','right')):
                values[side+'_measured_rad_s']=self.last_control['measured_left_right_rad_s'][index]
                values[side+'_target_rad_s']=(self.last_control['pi_left_right'][index]['ramped_rad_s']
                                             if self.state=='running' else 0.)
        status.values=[KeyValue(key=k,value=str(v)) for k,v in values.items()]
        msg.status=[status]
        self.status_pub.publish(msg)

    def _finish(self,reason):
        if self.done:return
        self.done=True
        self.state='stopping'
        self.summary['stop_reason']=reason
        self.summary['cleanup_started_monotonic_s']=self.mono()
        saved={}
        try:
            for sig in (signal.SIGINT,signal.SIGTERM):
                saved[sig]=signal.signal(sig,signal.SIG_IGN)
            try:
                result=self.transport.stop_and_close()
            except BaseException as error:
                self.errors.append('Unexpected cleanup failure: '+repr(error))
                result={'zero_acked':False,'stationary_verified':False,'closed':False,
                        'error':'Cleanup failed; physical stop must be checked'}
                try:
                    self.transport.armed=False
                    self.transport.write_duty(0,0)
                    result['zero_acked']=True
                except BaseException:
                    pass
                finally:
                    self.transport.tx_disabled=True
                    try:
                        if self.transport.serial is not None:self.transport.serial.close()
                        result['closed']=True
                    except BaseException:
                        pass
        finally:
            for sig,handler in saved.items():signal.signal(sig,handler)
        self.summary['stop']=result
        self.summary['errors']=list(self.errors)
        self.summary['control_steps']=self.control_steps
        self.summary['passed']=bool(reason in ('duration_complete','explicit_zero') and not self.errors
                                     and self.control_steps>0 and result.get('stationary_verified')
                                     and result.get('closed'))
        self.state='complete' if self.summary['passed'] else 'failed'
        zero_target=JointState()
        zero_target.header.stamp=self.get_clock().now().to_msg()
        zero_target.header.frame_id='base_footprint'
        zero_target.name=['left_wheel_joint','right_wheel_joint']
        zero_target.velocity=[0.,0.]
        if self.context.ok():self.target_pub.publish(zero_target)
        self.summary['finished_monotonic_s']=self.mono()
        self._record('events',{'event':'finished',**self.summary})
        (self.folder/'summary.json').write_text(json.dumps(self.summary,indent=2,allow_nan=False))
        self._status()
        for stream in self.files.values():stream.flush()

    def close_logs(self):
        for stream in self.files.values():stream.close()


def main(args=None):
    # Keep ROS context alive while the main-thread signal path stops hardware.
    rclpy.init(args=args,signal_handler_options=SignalHandlerOptions.NO)
    node=None
    def interrupt(signum,frame):raise KeyboardInterrupt
    signal.signal(signal.SIGINT,interrupt)
    signal.signal(signal.SIGTERM,interrupt)
    try:
        node=SpeedBenchNode()
        while rclpy.ok() and not node.done:rclpy.spin_once(node,timeout_sec=.05)
    except (KeyboardInterrupt,ExternalShutdownException):
        if node:node.errors.append('Interrupted by signal or ROS shutdown')
    finally:
        signal.signal(signal.SIGINT,signal.SIG_IGN)
        signal.signal(signal.SIGTERM,signal.SIG_IGN)
        if node:
            if not node.done:node._finish('interrupted')
            passed=node.summary['passed']
            node.close_logs()
            node.destroy_node()
        else:passed=False
        if rclpy.ok():rclpy.shutdown()
    return 0 if passed else 1
