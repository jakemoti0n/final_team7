#!/usr/bin/env python3
"""Verify real Limbo RGB-D input processing; YOLO inference is deliberately excluded.

Runs the actual PersonDetector constructor, subscriptions, ApproximateTimeSynchronizer,
CameraInfo callback, image_callback and depth conversion. Only the imported YOLO
model is replaced: track() returns no boxes and records that it received the actual
converted camera image. All detector outputs are remapped below /limbo_input_check.
No synthetic camera/TF/detection message is published. Missing robot/odom TF is an
explicit exclusion; the real lookup uses a zero timeout so it cannot throttle input.
Use the camera's isolated ROS domain and source the Limbo + DepthAI overlays first.
"""
import argparse
from collections import OrderedDict
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import sys
import time
import traceback
import types


def utc():
    return datetime.now(timezone.utc).isoformat()


def stamp(msg):
    return int(msg.header.stamp.sec) * 1000000000 + int(msg.header.stamp.nanosec)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--seconds', type=float, default=30.0)
    parser.add_argument('--params-file', action='append', default=[])
    parser.add_argument('--frame', default='oak_rgb_camera_optical_frame')
    parser.add_argument('--width', type=int, default=640)
    parser.add_argument('--height', type=int, default=400)
    parser.add_argument('--minimum-rate', type=float, default=9.5)
    parser.add_argument('--maximum-rate', type=float, default=10.5)
    parser.add_argument('--maximum-gap', type=float, default=0.25)
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds < 20:
        parser.error('--seconds must be finite and at least 20')
    output = Path(args.out)
    if output.exists():
        parser.error('--out must be a new file')
    output.parent.mkdir(parents=True, exist_ok=True)
    result = {'status': 'failed', 'started_utc': utc(), 'requested_seconds': args.seconds,
              'errors': [], 'error_count': 0, 'stream_stats': {}, 'checks': {},
              'excluded': ['YOLO/BoT-SORT inference and detection accuracy',
                  'physical distance / RGB-depth alignment accuracy',
                  'camera mounting TF and odom/base transforms',
                  'motor, navigation and prediction behaviour with real detections'],
              'method': 'Actual PersonDetector with only ultralytics.YOLO replaced by empty-result model; all output topics remapped to /limbo_input_check; tf_timeout=0.0',
              'thresholds': {'rate_hz': [args.minimum_rate, args.maximum_rate],
                  'maximum_gap_s': args.maximum_gap, 'sync_slop_s': 0.03,
                  'minimum_receive_span_s': args.seconds - 8.0,
                  'minimum_sync_ratio': 0.95, 'maximum_last_age_s': 0.5}}
    node = executor = None
    rclpy = np = geometry = None
    original_depth = None
    previous_ultralytics = sys.modules.get('ultralytics')
    interrupted = None
    started = time.monotonic()
    context = {'rgb': None, 'depth': None, 'start': started,
               'sync_count': 0, 'processed': 0, 'skipped_before_info': 0,
               'depth_conversions': 0, 'model_track_calls': 0,
               'max_sync_delta_s': 0.0, 'tf_missing': 0, 'tf_available': 0,
               'rgb_info_exact_pairs': 0, 'last_info': None, 'graph_checks': 0,
               'depth_valid_fractions': [], 'image_info_maps': {
                   'rgb': OrderedDict(), 'info': OrderedDict()}, 'unmatched': []}
    samples = {key: {'count': 0, 'first': None, 'last': None, 'max_gap_s': 0,
                        'last_stamp': None, 'stamp_regressions': 0, 'duplicate_stamps': 0,
                        'zero_stamps': 0}
               for key in ('rgb', 'depth', 'info', 'synchronized_callback', 'processed_callback')}

    def fail(where, message):
        result['error_count'] += 1
        if len(result['errors']) < 80:
            result['errors'].append({'context': where, 'message': str(message)})

    def require(condition, message):
        if not condition:
            raise AssertionError(message)

    def on_signal(signum, _frame):
        nonlocal interrupted
        interrupted = signum

    def observe(key, msg):
        now = time.monotonic()
        s = samples[key]
        if s['first'] is None:
            s['first'] = now
        if s['last'] is not None:
            s['max_gap_s'] = max(s['max_gap_s'], now - s['last'])
        s['count'] += 1
        s['last'] = now
        timestamp = stamp(msg)
        s['zero_stamps'] += int(timestamp <= 0)
        if s['last_stamp'] is not None:
            s['stamp_regressions'] += int(timestamp < s['last_stamp'])
            s['duplicate_stamps'] += int(timestamp == s['last_stamp'])
        s['last_stamp'] = timestamp
        return now

    def check_dimensions(msg):
        require((msg.width, msg.height) == (args.width, args.height), 'Unexpected image/info dimensions')
        require(msg.header.frame_id == args.frame, 'Unexpected optical frame: ' + msg.header.frame_id)
        require(stamp(msg) > 0, 'Non-positive acquisition timestamp')

    def array(msg, kind, channels=1):
        dt = np.dtype(kind).newbyteorder('>' if msg.is_bigendian else '<')
        require(msg.step >= msg.width * dt.itemsize * channels, 'Invalid row step')
        require(len(msg.data) == msg.height * msg.step, 'Invalid image payload length')
        shape = (msg.height, msg.width) if channels == 1 else (msg.height, msg.width, channels)
        strides = (msg.step, dt.itemsize) if channels == 1 else (msg.step, channels * dt.itemsize, dt.itemsize)
        return np.ndarray(shape, dtype=dt, buffer=msg.data, strides=strides)

    def register_rgb_info(key, msg, now):
        own = context['image_info_maps'][key]
        other = context['image_info_maps']['info' if key == 'rgb' else 'rgb']
        t = stamp(msg)
        meta = {'arrival': now, 'frame': msg.header.frame_id, 'width': msg.width,
                'height': msg.height}
        if t in other:
            paired = other.pop(t)
            require(all(meta[k] == paired[k] for k in ('frame', 'width', 'height')),
                    'RGB/CameraInfo exact-stamp metadata mismatch')
            context['rgb_info_exact_pairs'] += 1
        else:
            own[t] = meta
        while len(own) > 512:
            _, old = own.popitem(last=False)
            context['unmatched'].append({'kind': key, **old})

    try:
        import numpy as np_module
        import cv2
        import rclpy as ros
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import qos_profile_sensor_data, ReliabilityPolicy, DurabilityPolicy
        from rclpy.signals import SignalHandlerOptions
        from sensor_msgs.msg import Image
        np, rclpy = np_module, ros

        class NoInferenceModel:
            names = {0: 'person', 1: 'leg'}

            def __init__(self, model_path):
                result['excluded_model_path'] = str(model_path)

            def track(self, source, **_kwargs):
                raw = context['rgb']
                require(raw is not None, 'Model reached without synchronized real RGB input')
                require(source.dtype == np.uint8 and np.array_equal(source, array(raw, 'u1', 3)),
                        'Actual consumer BGR conversion changed pixels')
                context['model_track_calls'] += 1
                return [types.SimpleNamespace(boxes=None)]

        replacement = types.ModuleType('ultralytics')
        replacement.YOLO = NoInferenceModel
        sys.modules['ultralytics'] = replacement
        from limbo_perception import person_detector as pd
        from limbo_perception import geometry as geo
        geometry = geo
        result['source'] = {}
        for name, module in (('person_detector', pd), ('geometry', geometry)):
            path = Path(module.__file__).resolve()
            result['source'][name] = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        result['environment'] = {'python': sys.executable, 'numpy': np.__version__,
            'opencv': cv2.__version__, 'ROS_DOMAIN_ID': os.getenv('ROS_DOMAIN_ID'),
            'RMW_IMPLEMENTATION': os.getenv('RMW_IMPLEMENTATION'),
            'FASTRTPS_DEFAULT_PROFILES_FILE': os.getenv('FASTRTPS_DEFAULT_PROFILES_FILE')}

        original_depth = geometry.depth_in_meters

        def verified_depth(raw, encoding):
            converted = original_depth(raw, encoding)
            msg = context['depth']
            require(msg is not None, 'Depth conversion outside synchronized callback')
            require(encoding == '16UC1' and raw.dtype == np.uint16, 'Expected millimetre uint16 depth')
            require(np.array_equal(raw, array(msg, 'u2')), 'Actual cv_bridge depth differs from ROS pixels')
            require(converted.dtype == np.float32 and converted.shape == raw.shape, 'Wrong metre array dtype/shape')
            np.testing.assert_allclose(converted, raw.astype(np.float64) / 1000.0, rtol=1e-6, atol=1e-7)
            context['depth_conversions'] += 1
            if len(context['depth_valid_fractions']) < 100:
                valid = np.isfinite(converted) & (converted > node.depth_config.min_depth) & (converted < node.depth_config.max_depth)
                context['depth_valid_fractions'].append(float(valid.mean()))
            return converted

        geometry.depth_in_meters = verified_depth

        class VerifiedDetector(pd.PersonDetector):
            def camera_info_callback(self, msg):
                try:
                    now = observe('info', msg)
                    check_dimensions(msg)
                    k = np.asarray(msg.k, dtype=np.float64)
                    require(k.shape == (9,) and np.isfinite(k).all(), 'Invalid K matrix')
                    require(k[0] > 0 and k[4] > 0 and 0 <= k[2] < msg.width and 0 <= k[5] < msg.height,
                            'Invalid focal lengths/principal point')
                    np.testing.assert_allclose(k[[1, 3, 6, 7, 8]], [0, 0, 0, 0, 1], atol=1e-6, rtol=0)
                    register_rgb_info('info', msg, now)
                    super().camera_info_callback(msg)
                    np.testing.assert_allclose([self.intrinsics.fx, self.intrinsics.fy, self.intrinsics.cx, self.intrinsics.cy],
                                               k[[0, 4, 2, 5]], atol=0, rtol=0)
                    context['last_info'] = {'frame_id': msg.header.frame_id, 'width': msg.width, 'height': msg.height,
                        'k': list(msg.k), 'p': list(msg.p), 'd': list(msg.d), 'distortion_model': msg.distortion_model}
                except Exception as exc:
                    fail('camera_info_callback', exc)

            def image_callback(self, rgb, depth, detections_msg=None):
                try:
                    observe('synchronized_callback', rgb)
                    context['sync_count'] += 1
                    check_dimensions(rgb)
                    check_dimensions(depth)
                    require(rgb.encoding == 'bgr8' and depth.encoding == '16UC1', 'Unexpected input encoding')
                    delta = abs(stamp(rgb) - stamp(depth)) / 1e9
                    context['max_sync_delta_s'] = max(context['max_sync_delta_s'], delta)
                    require(delta <= self.sync_slop, 'Synchronizer delivered frames outside actual slop')
                    require(self.camera_frame == rgb.header.frame_id == depth.header.frame_id,
                            'Consumer camera_frame differs from actual frame')
                    if self.intrinsics is None:
                        context['skipped_before_info'] += 1
                        require(time.monotonic() - context['start'] < 5.0, 'CameraInfo still unavailable after5s')
                    context['rgb'], context['depth'] = rgb, depth
                    before = context['model_track_calls']
                    super().image_callback(rgb, depth, detections_msg)
                    if self.intrinsics is not None:
                        require(context['model_track_calls'] == before + 1, 'Consumer did not complete model boundary')
                        observe('processed_callback', rgb)
                        context['processed'] += 1
                except Exception as exc:
                    fail('image_callback', exc)
                finally:
                    context['rgb'] = context['depth'] = None

            def _robot_position(self, timestamp):
                value = super()._robot_position(timestamp)
                context['tf_available' if value is not None else 'tf_missing'] += 1
                return value

        ros_args = ['--ros-args']
        for file in args.params_file:
            ros_args += ['--params-file', file]
        ros_args += ['-p', 'tf_timeout:=0.0']
        # Absolute production output topic names require explicit remaps.
        output_topics = [value for name, value in vars(pd).items()
                         if name.endswith('_TOPIC') and isinstance(value, str) and value.startswith('/person_detector/')]
        for topic in output_topics:
            ros_args += ['-r', topic + ':=/limbo_input_check/' + topic.rsplit('/', 1)[-1]]
        result['output_remaps'] = output_topics
        rclpy.init(args=ros_args, signal_handler_options=SignalHandlerOptions.NO)
        signal.signal(signal.SIGINT, on_signal)
        signal.signal(signal.SIGTERM, on_signal)
        node = VerifiedDetector()
        require(node.detector_source == 'yolo', 'Camera-only v3 profile requires host-YOLO consumer input mode')
        require(node.rgb_topic == '/rgbd_camera/image' and node.depth_topic == '/rgbd_camera/depth_image'
                and node.camera_info_topic == '/rgbd_camera/camera_info', 'Unexpected configured Limbo input topics')
        require(node.sync_queue_size == 5 and abs(node.sync_slop - .03) < 1e-12, 'Consumer sync configuration changed')
        require(node.get_parameter('use_sim_time').value is False, 'Consumer unexpectedly uses sim time')
        result['consumer_parameters'] = {'rgb_topic': node.rgb_topic, 'depth_topic': node.depth_topic,
            'camera_info_topic': node.camera_info_topic, 'camera_frame': node.camera_frame,
            'sync_queue_size': node.sync_queue_size, 'sync_slop_s': node.sync_slop,
            'depth': asdict(node.depth_config), 'tf_timeout_s': 0.0, 'use_sim_time': False}

        # Numerical controls call production geometry directly; no test messages enter ROS.
        mm = np.array([[0, 1000, 2000, 65535]], dtype=np.uint16)
        metres = original_depth(mm, '16UC1')
        np.testing.assert_allclose(metres, [[0, 1, 2, 65.535]], rtol=1e-6, atol=1e-7)
        controls = {}
        cfg = replace(node.depth_config, roi_margin=0.0)
        for name, value, expected in (('one_metre', 1.0, 1.0), ('zero_invalid', 0.0, None),
                                      ('saturated65535_invalid', float(metres[0, 3]), None),
                                      ('nan_invalid', float('nan'), None), ('inf_invalid', float('inf'), None)):
            observed = geometry.person_depth(np.full((8, 8), value, dtype=np.float32), 0, 0, 8, 8, cfg)
            require(observed == expected, name + ' geometry validity mismatch')
            controls[name] = {'expected': expected, 'observed': observed, 'passed': True}
        result['synthetic_geometry_controls'] = controls

        def raw_callback(key, msg):
            try:
                now = observe(key, msg)
                check_dimensions(msg)
                require(msg.encoding == ('bgr8' if key == 'rgb' else '16UC1'), 'Unexpected raw encoding')
                array(msg, 'u1' if key == 'rgb' else 'u2', 3 if key == 'rgb' else 1)
                if key == 'rgb':
                    register_rgb_info('rgb', msg, now)
            except Exception as exc:
                fail(key + '_raw_subscription', exc)

        references = [node.create_subscription(Image, topic,
                      lambda message, key=key: raw_callback(key, message), qos_profile_sensor_data)
                      for key, topic in (('rgb', node.rgb_topic), ('depth', node.depth_topic))]
        executor = SingleThreadedExecutor()
        executor.add_node(node)
        started = context['start'] = time.monotonic()
        result['observation_started_utc'] = utc()
        next_graph = started + 5.0
        next_progress = started + 15.0

        def graph_check():
            graph = {}
            for topic, message_type in ((node.rgb_topic, 'sensor_msgs/msg/Image'),
                                        (node.depth_topic, 'sensor_msgs/msg/Image'),
                                        (node.camera_info_topic, 'sensor_msgs/msg/CameraInfo')):
                pubs = node.get_publishers_info_by_topic(topic)
                require(len(pubs) == 1, topic + ' must have exactly one publisher; got ' + str(len(pubs)))
                pub = pubs[0]
                require(pub.topic_type == message_type, 'Wrong published message type on ' + topic)
                graph[topic] = {'publisher_node': pub.node_namespace.rstrip('/') + '/' + pub.node_name,
                    'type': pub.topic_type, 'reliability': str(pub.qos_profile.reliability),
                    'durability': str(pub.qos_profile.durability)}
                require(pub.qos_profile.reliability in (ReliabilityPolicy.BEST_EFFORT, ReliabilityPolicy.RELIABLE),
                        'Unknown publisher reliability')
                subs = [sub for sub in node.get_subscriptions_info_by_topic(topic) if sub.node_name == node.get_name()]
                require(subs and all(sub.qos_profile.reliability == ReliabilityPolicy.BEST_EFFORT
                                    and sub.qos_profile.durability == DurabilityPolicy.VOLATILE for sub in subs),
                        'Actual consumer subscription QoS differs from sensor_data')
            result['last_graph'] = graph
            context['graph_checks'] += 1

        while rclpy.ok() and not interrupted and time.monotonic() - started < args.seconds:
            executor.spin_once(timeout_sec=0.05)
            now = time.monotonic()
            if now >= next_graph:
                try:
                    graph_check()
                except Exception as exc:
                    fail('ROS graph', exc)
                next_graph = now + 15.0
            if now >= next_progress:
                print(json.dumps({'elapsed_s': now-started, 'processed': context['processed'],
                                  'errors': result['error_count']}), flush=True)
                next_progress = now + 15.0
        ended = time.monotonic()
        result['elapsed_seconds'] = ended - started
        require(not interrupted and result['elapsed_seconds'] >= args.seconds, 'Observation interrupted/ended early')
        graph_check()
        for key, value in samples.items():
            span = value['last'] - value['first'] if value['count'] > 1 else 0
            rate = (value['count'] - 1) / span if span > 0 else 0
            age = ended - value['last'] if value['last'] is not None else None
            result['stream_stats'][key] = {**value, 'received_span_s': span, 'rate_hz': rate, 'last_age_s': age}
            require(span >= args.seconds - 8.0, key + ': insufficient actual receive span')
            require(args.minimum_rate <= rate <= args.maximum_rate, key + ': rate out of limits ' + str(rate))
            require(value['max_gap_s'] <= args.maximum_gap, key + ': receive gap exceeds limit')
            require(age is not None and age <= .5, key + ': stale final stream')
            require(not any(value[k] for k in ('stamp_regressions', 'duplicate_stamps', 'zero_stamps')),
                    key + ': acquisition timestamp anomalies')
        for key, entries in context['image_info_maps'].items():
            context['unmatched'].extend({'kind': key, **entry} for entry in entries.values())
        interior = [entry for entry in context['unmatched'] if started + 1 <= entry['arrival'] <= ended - 1]
        result['rgb_info_unmatched_interior'] = len(interior)
        result['rgb_info_unmatched_boundary_ignored'] = len(context['unmatched']) - len(interior)
        require(not interior, 'Unmatched interior RGB / shared CameraInfo acquisition stamps')
        denominator = min(samples['rgb']['count'], samples['depth']['count'])
        result['synchronized_fraction_of_smaller_input'] = context['sync_count'] / denominator if denominator else 0
        require(result['synchronized_fraction_of_smaller_input'] >= .95, 'Too few actual consumer synchronized callbacks')
        require(context['processed'] == context['depth_conversions'] == context['model_track_calls'],
                'Actual depth/model/callback completion counts differ')
        require(context['rgb_info_exact_pairs'] >= max(20, denominator * .95), 'Insufficient exact RGB/CameraInfo pairs')
        require(context['graph_checks'] >= 2, 'Too few endpoint consistency checks')
        result['checks'] = {'actual_consumer_constructor_and_callbacks': True,
            'actual_mm_to_m_pixels': True, 'actual_rgb_pixels': True, 'RGB_shared_CameraInfo_contract': True,
            'actual_message_filter_sync': True, 'single_publishers_and_sensor_qos': True,
            'rate_stability_and_timestamp_checks': True}
        result['status'] = 'passed' if result['error_count'] == 0 else 'failed'
    except BaseException as exc:
        fail('fatal_or_final_verdict', type(exc).__name__ + ': ' + str(exc))
        traceback.print_exc()
    finally:
        if executor is not None:
            executor.shutdown(timeout_sec=2.0)
        if node is not None:
            node.destroy_node()
        if rclpy is not None and rclpy.ok():
            rclpy.shutdown()
        if geometry is not None and original_depth is not None:
            geometry.depth_in_meters = original_depth
        if previous_ultralytics is None:
            sys.modules.pop('ultralytics', None)
        else:
            sys.modules['ultralytics'] = previous_ultralytics
        for key in ('rgb', 'depth', 'image_info_maps', 'unmatched'):
            context.pop(key, None)
        result['consumer_observations'] = context
        result['finished_utc'] = utc()
        # Always retain raw counters even when an early failure prevents final stats.
        if not result['stream_stats']:
            result['stream_stats'] = samples
        temporary = output.with_suffix(output.suffix + '.tmp')
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        os.replace(temporary, output)
        print(json.dumps({'status': result['status'], 'error_count': result['error_count'], 'out': str(output)}), flush=True)
    return 0 if result['status'] == 'passed' else 2


if __name__ == '__main__':
    sys.exit(main())
