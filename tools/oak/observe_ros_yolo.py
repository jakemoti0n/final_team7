#!/usr/bin/env python3
"""Observe actual Limbo YOLO ROS outputs without publishing or replacing inference.

The boxes topic contains TRACKED boxes, not raw YOLO predictions. The 'kept'
array precedes geometry rejection; person_position denotes an accepted optical
result. PNG pairs retain exact input acquisition stamps. A positive box or point
does not establish that a person is actually present: inspect saved raw images.
"""
import argparse
from collections import OrderedDict
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import signal
import sys
import time
import traceback


def utc():
    return datetime.now(timezone.utc).isoformat()


def stamp_ns(msg):
    return int(msg.header.stamp.sec) * 1_000_000_000 + int(msg.header.stamp.nanosec)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--seconds', type=float, default=60.0)
    parser.add_argument('--scene-label', default='unspecified; human presence requires image review')
    parser.add_argument('--rgb', default='/rgbd_camera/image')
    parser.add_argument('--annotated', default='/person_detector/annotated_image')
    parser.add_argument('--boxes', default='/person_detector/boxes')
    parser.add_argument('--position', default='/person_detector/person_position')
    parser.add_argument('--frame', default='oak_rgb_camera_optical_frame')
    parser.add_argument('--sample-interval', type=float, default=5.0)
    parser.add_argument('--raw-cache-frames', type=int, default=32)
    parser.add_argument('--max-samples', type=int, default=40)
    parser.add_argument('--require-detection', action='store_true',
                        help='Require >=3 accepted optical-result frames and an exact-stamp raw/annotated evidence pair; human review still required')
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds < 5:
        parser.error('--seconds must be finite and >= 5')
    if args.sample_interval <= 0 or not math.isfinite(args.sample_interval):
        parser.error('--sample-interval must be finite and positive')
    if not 10 <= args.raw_cache_frames <= 600 or args.max_samples < 1:
        parser.error('raw cache must be 10..600 frames and max-samples positive')
    out = Path(args.out_dir)
    if out.exists() and any(out.iterdir()):
        parser.error('--out-dir must be new or empty')
    out.mkdir(parents=True, exist_ok=True)
    result = {'status': 'failed', 'started_utc': utc(), 'scene_label': args.scene_label,
              'requested_seconds': args.seconds, 'errors': [], 'error_count': 0,
              'samples': [], 'graph_checks': [],
              'method': 'Read-only ROS subscriber; actual published inference outputs only; no mock/model/publisher',
              'interpretation': {
                  'boxes': 'Tracked model.track() boxes after track-ID gate; not raw YOLO predictions',
                  'kept': 'Merged tracked boxes, before surface/depth/edge/physical-width filtering',
                  'surface': 'Tracked candidates rejected by surface filter',
                  'optical_position': 'Nearest accepted result after geometry filters, in camera optical frame',
                  'scene_label': 'Operator context only; observer cannot establish human presence',
                  'human_presence_verdict': 'Manual review of exact-stamp raw/annotated PNG pairs required'},
              'limitations': ['No raw YOLO prediction statistics are available on the existing boxes topic.',
                  'A detection is not ground truth; accuracy requires labeled positive/negative scenes.',
                  'No fixed inference FPS is assumed; measured rates include full node processing.',
                  'Header age includes camera, transport, inference, tracking and scheduling latency.',
                  'Base/odom TF, physical distance accuracy and robot motion are outside this observer.',
                  'Raw input cache is bounded; slow output can expire its matching raw image.'],
              'configuration': vars(args)}
    counters = {'tracked_nonempty_frames': 0, 'tracked_boxes_total': 0,
                'merged_nonempty_frames': 0, 'merged_boxes_total': 0,
                'surface_rejected_boxes_total': 0, 'optical_position_messages': 0,
                'annotated_with_exact_raw': 0, 'annotated_without_cached_raw': 0,
                'annotated_with_boxes': 0, 'annotated_without_boxes': 0,
                'annotated_with_optical_position': 0, 'sample_write_failures': 0,
                'positive_with_raw_and_boxes': 0,
                'metadata_evictions': 0, 'raw_cache_evictions': 0}
    stats = {name: {'count': 0, 'first_mono': None, 'last_mono': None, 'max_gap_s': 0.0,
                   'previous_stamp_ns': None, 'stamp_regressions': 0,
                   'duplicate_stamps': 0, 'zero_stamps': 0, 'frames': set(), 'ages': []}
             for name in ('rgb', 'annotated', 'boxes', 'optical_position', 'base_position', 'odom_position')}
    raw_cache, annotations, boxes, positions = (OrderedDict() for _ in range(4))
    node = executor = ros = None
    np = cv2 = None
    interrupted = None
    started = time.monotonic()
    last_saved = -math.inf
    first_positive_saved = False
    event_log = (out / 'events.jsonl').open('x', encoding='utf-8', buffering=1)

    def fail(where, exc):
        result['error_count'] += 1
        if len(result['errors']) < 100:
            result['errors'].append({'context': where, 'message': str(exc)})

    def require(condition, message):
        if not condition:
            raise ValueError(message)

    def write_event(event):
        event_log.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + '\n')

    def on_signal(signum, _frame):
        nonlocal interrupted
        interrupted = signum

    def observe(name, timestamp=None, frame=None):
        now = time.monotonic()
        s = stats[name]
        if s['first_mono'] is None:
            s['first_mono'] = now
        if s['last_mono'] is not None:
            s['max_gap_s'] = max(s['max_gap_s'], now - s['last_mono'])
        s['last_mono'] = now
        s['count'] += 1
        if frame is not None:
            s['frames'].add(frame)
        if timestamp is not None:
            s['zero_stamps'] += int(timestamp <= 0)
            if s['previous_stamp_ns'] is not None:
                s['stamp_regressions'] += int(timestamp < s['previous_stamp_ns'])
                s['duplicate_stamps'] += int(timestamp == s['previous_stamp_ns'])
            s['previous_stamp_ns'] = timestamp
            if timestamp > 0:
                age = (node.get_clock().now().nanoseconds - timestamp) / 1e9
                s['ages'].append(age)
        return now

    def bound(mapping, limit, counter):
        while len(mapping) > limit:
            mapping.popitem(last=False)
            counters[counter] += 1

    def bgr_array(msg):
        require(msg.encoding in ('bgr8', 'rgb8'), 'Unsupported image encoding ' + msg.encoding)
        require(msg.width > 0 and msg.height > 0 and msg.step >= msg.width * 3,
                'Malformed image dimensions/step')
        require(len(msg.data) == msg.height * msg.step, 'Malformed image payload length')
        image = np.ndarray((msg.height, msg.width, 3), dtype=np.uint8,
                           buffer=msg.data, strides=(msg.step, 3, 1))
        return image if msg.encoding == 'bgr8' else image[:, :, ::-1]

    def image_callback(name, msg):
        try:
            timestamp = stamp_ns(msg)
            now = observe(name, timestamp, msg.header.frame_id)
            require(msg.header.frame_id == args.frame, 'Unexpected optical frame ' + msg.header.frame_id)
            bgr_array(msg)
            target = raw_cache if name == 'rgb' else annotations
            target[timestamp] = {'msg': msg, 'arrival': now}
            target.move_to_end(timestamp)
            if name == 'rgb':
                bound(target, args.raw_cache_frames, 'raw_cache_evictions')
                if stats['rgb']['count'] == 1:
                    require(cv2.imwrite(str(out / 'raw_first.png'), bgr_array(msg)), 'Could not save first raw PNG')
                    result['raw_first'] = {'file': 'raw_first.png', 'stamp_ns': timestamp,
                                           'frame_id': msg.header.frame_id}
            else:
                # normally only a few pending outputs; retain evidence of unexpected backlog.
                require(len(target) < 120, 'Unprocessed annotation backlog exceeds120')
        except Exception as exc:
            fail(name, exc)

    def boxes_callback(msg):
        try:
            payload = json.loads(msg.data)
            require(isinstance(payload, dict), 'Boxes JSON must be object')
            t = payload.get('t')
            require(isinstance(t, (int, float)) and math.isfinite(t) and t > 0, 'Invalid boxes timestamp')
            timestamp = round(t * 1e9)
            now = observe('boxes', timestamp)
            tracked, kept, surfaces = (payload.get(k) for k in ('boxes', 'kept', 'surface'))
            require(all(isinstance(v, list) for v in (tracked, kept, surfaces)), 'Missing boxes/kept/surface arrays')
            for row in tracked:
                require(isinstance(row, list) and len(row) == 6 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in row),
                        'Invalid tracked box row')
                cls, x1, y1, x2, y2, confidence = row
                require(x2 >= x1 and y2 >= y1 and 0 <= confidence <= 1, 'Invalid box geometry/confidence')
            for row in kept:
                require(isinstance(row, list) and len(row) == 5 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in row),
                        'Invalid merged box row')
            counters['tracked_nonempty_frames'] += int(bool(tracked))
            counters['tracked_boxes_total'] += len(tracked)
            counters['merged_nonempty_frames'] += int(bool(kept))
            counters['merged_boxes_total'] += len(kept)
            counters['surface_rejected_boxes_total'] += len(surfaces)
            boxes[timestamp] = {'payload': payload, 'arrival': now}
            bound(boxes, 2048, 'metadata_evictions')
            write_event({'kind': 'tracked_boxes', 'received_utc': utc(), 'stamp_ns_from_float': timestamp,
                         'payload': payload})
        except Exception as exc:
            fail('boxes', exc)

    def point_callback(name, msg):
        try:
            timestamp = stamp_ns(msg)
            now = observe(name, timestamp, msg.header.frame_id)
            xyz = [float(msg.point.x), float(msg.point.y), float(msg.point.z)]
            require(all(math.isfinite(v) for v in xyz), 'Non-finite person position')
            if name == 'optical_position':
                require(msg.header.frame_id == args.frame and xyz[2] > 0, 'Invalid optical frame/depth')
                counters['optical_position_messages'] += 1
                positions[timestamp] = {'frame_id': msg.header.frame_id, 'xyz_m': xyz, 'arrival': now}
                bound(positions, 2048, 'metadata_evictions')
            write_event({'kind': name, 'received_utc': utc(), 'stamp_ns': timestamp,
                         'frame_id': msg.header.frame_id, 'xyz_m': xyz})
        except Exception as exc:
            fail(name, exc)

    def matching_boxes(timestamp):
        # JSON float epoch seconds lose submicrosecond precision, unlike ROS Header.
        candidates = [(abs(other - timestamp), entry) for other, entry in boxes.items()
                      if abs(other - timestamp) <= 2000]
        return min(candidates, key=lambda pair: pair[0]) if candidates else (None, None)

    def process_annotations(final=False):
        nonlocal last_saved, first_positive_saved
        now = time.monotonic()
        for timestamp, entry in list(annotations.items()):
            if not final and now - entry['arrival'] < .4:
                continue
            msg = entry['msg']
            raw = raw_cache.get(timestamp)
            delta, diagnostics = matching_boxes(timestamp)
            point = positions.get(timestamp)
            counters['annotated_with_exact_raw' if raw else 'annotated_without_cached_raw'] += 1
            counters['annotated_with_boxes' if diagnostics else 'annotated_without_boxes'] += 1
            counters['annotated_with_optical_position'] += int(point is not None)
            positive = point is not None
            payload = diagnostics['payload'] if diagnostics else None
            counters['positive_with_raw_and_boxes'] += int(positive and raw is not None and payload is not None and bool(payload['boxes']))
            event = {'kind': 'annotated_frame', 'stamp_ns': timestamp,
                     'frame_id': msg.header.frame_id, 'size': [msg.width, msg.height],
                     'exact_raw_available': raw is not None, 'boxes_timestamp_delta_ns': delta,
                     'tracked_box_count': len(payload['boxes']) if payload else None,
                     'merged_box_count': len(payload['kept']) if payload else None,
                     'surface_rejected_count': len(payload['surface']) if payload else None,
                     'optical_position': point}
            write_event(event)
            save = not result['samples'] or entry['arrival'] - last_saved >= args.sample_interval or (positive and not first_positive_saved)
            if save and len(result['samples']) < args.max_samples:
                try:
                    stem = f"sample_{len(result['samples']) + 1:03d}_{timestamp}"
                    annotated_name = stem + '_annotated.png'
                    require(cv2.imwrite(str(out / annotated_name), bgr_array(msg)), 'Could not save annotated PNG')
                    raw_name = None
                    if raw:
                        require(raw['msg'].header.frame_id == msg.header.frame_id and
                                (raw['msg'].width, raw['msg'].height) == (msg.width, msg.height),
                                'Exact-stamp raw/annotated frame geometry differs')
                        raw_name = stem + '_raw.png'
                        require(cv2.imwrite(str(out / raw_name), bgr_array(raw['msg'])), 'Could not save raw PNG')
                    sample = {**event, 'annotated_png': annotated_name, 'raw_png': raw_name,
                              'diagnostics': payload, 'human_presence_review': 'pending'}
                    result['samples'].append(sample)
                    last_saved = entry['arrival']
                    first_positive_saved |= bool(positive and raw_name and payload and payload['boxes'])
                except Exception as exc:
                    counters['sample_write_failures'] += 1
                    fail('evidence PNG', exc)
            annotations.pop(timestamp)

    try:
        import numpy as numpy_module
        import cv2 as opencv
        import rclpy
        from rclpy.node import Node
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import qos_profile_sensor_data
        from rclpy.signals import SignalHandlerOptions
        from sensor_msgs.msg import Image
        from std_msgs.msg import String
        from geometry_msgs.msg import PointStamped
        np, cv2, ros = numpy_module, opencv, rclpy
        ros.init(args=[], signal_handler_options=SignalHandlerOptions.NO)
        signal.signal(signal.SIGINT, on_signal)
        signal.signal(signal.SIGTERM, on_signal)
        node = Node('limbo_real_yolo_observer_' + str(os.getpid()))
        result['environment'] = {'python': sys.executable, 'numpy': np.__version__, 'opencv': cv2.__version__,
            'ROS_DOMAIN_ID': os.getenv('ROS_DOMAIN_ID'),
            'ROS_AUTOMATIC_DISCOVERY_RANGE': os.getenv('ROS_AUTOMATIC_DISCOVERY_RANGE'),
            'RMW_IMPLEMENTATION': os.getenv('RMW_IMPLEMENTATION'),
            'FASTRTPS_DEFAULT_PROFILES_FILE': os.getenv('FASTRTPS_DEFAULT_PROFILES_FILE')}
        references = [node.create_subscription(Image, args.rgb, lambda msg: image_callback('rgb', msg), qos_profile_sensor_data),
                      node.create_subscription(Image, args.annotated, lambda msg: image_callback('annotated', msg), qos_profile_sensor_data),
                      node.create_subscription(String, args.boxes, boxes_callback, qos_profile_sensor_data)]
        for name, topic in (('optical_position', args.position),
                            ('base_position', '/person_detector/person_position_base'),
                            ('odom_position', '/person_detector/person_position_odom')):
            references.append(node.create_subscription(PointStamped, topic,
                lambda msg, name=name: point_callback(name, msg), qos_profile_sensor_data))
        executor = SingleThreadedExecutor()
        executor.add_node(node)
        started = time.monotonic()
        next_graph = started + 5
        next_progress = started + 15
        while ros.ok() and not interrupted and time.monotonic() - started < args.seconds:
            executor.spin_once(timeout_sec=.05)
            process_annotations()
            now = time.monotonic()
            if now >= next_graph:
                graph = {'elapsed_s': now - started, 'publishers': {}}
                for topic in (args.rgb, args.annotated, args.boxes, args.position):
                    entries = node.get_publishers_info_by_topic(topic)
                    graph['publishers'][topic] = [{'node': info.node_namespace.rstrip('/') + '/' + info.node_name,
                        'type': info.topic_type, 'reliability': str(info.qos_profile.reliability)} for info in entries]
                    if len(entries) > 1:
                        fail('ROS graph', 'Multiple publishers on ' + topic)
                result['graph_checks'].append(graph)
                next_graph = now + 15
            if now >= next_progress:
                print(json.dumps({'elapsed_s': now-started, 'rgb': stats['rgb']['count'],
                    'annotated': stats['annotated']['count'], 'tracked_nonempty': counters['tracked_nonempty_frames'],
                    'optical_points': counters['optical_position_messages'], 'errors': result['error_count']}), flush=True)
                next_progress = now + 15
        ended = time.monotonic()
        process_annotations(final=True)
        result['elapsed_seconds'] = ended - started
        if interrupted:
            fail('observation', 'Interrupted by signal ' + str(interrupted))
        elif result['elapsed_seconds'] < args.seconds:
            fail('observation', 'ROS context ended early')
        for key in ('rgb', 'annotated', 'boxes'):
            if stats[key]['count'] == 0:
                fail('no stream', key + ' received no messages')
        if args.require_detection:
            if counters['annotated_with_optical_position'] < 3 or counters['positive_with_raw_and_boxes'] < 1:
                fail('required positive structure', 'Need >=3 accepted optical-result frames and >=1 exact raw/annotated/tracked-box evidence frame')
            if not any(sample['raw_png'] and sample['optical_position'] and sample['tracked_box_count']
                       for sample in result['samples']):
                fail('required positive evidence', 'No saved exact-stamp positive raw/annotated evidence pair')
        result['positive_structure_observed'] = counters['annotated_with_optical_position'] >= 3 and counters['positive_with_raw_and_boxes'] >= 1
        result['status'] = 'completed' if result['error_count'] == 0 else 'failed'
    except BaseException as exc:
        fail('fatal', type(exc).__name__ + ': ' + str(exc))
        traceback.print_exc()
    finally:
        ended = time.monotonic()
        result['streams'] = {}
        for key, s in stats.items():
            span = s['last_mono'] - s['first_mono'] if s['count'] > 1 else 0
            ages = s.pop('ages')
            age_summary = {'count': len(ages)}
            if ages and np is not None:
                age_summary.update({'p50_s': float(np.percentile(ages, 50)), 'p95_s': float(np.percentile(ages, 95)),
                                    'max_s': max(ages), 'min_s': min(ages)})
            result['streams'][key] = {**s, 'frames': sorted(s['frames']), 'received_span_s': span,
                'rate_hz': (s['count'] - 1) / span if span > 0 else None,
                'last_age_s': ended - s['last_mono'] if s['last_mono'] is not None else None,
                'source_to_observer_age': age_summary}
        result['counters'] = counters
        result['finished_utc'] = utc()
        event_log.close()
        if executor is not None:
            executor.shutdown(timeout_sec=2)
        if node is not None:
            node.destroy_node()
        if ros is not None and ros.ok():
            ros.shutdown()
        tmp = out / 'summary.json.tmp'
        tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        os.replace(tmp, out / 'summary.json')
        print(json.dumps({'status': result['status'], 'errors': result['error_count'], 'out': str(out / 'summary.json'),
                          'human_presence_review': 'required; not automated'}), flush=True)
    return 0 if result['status'] == 'completed' else 2


if __name__ == '__main__':
    sys.exit(main())
