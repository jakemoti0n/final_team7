#!/usr/bin/env python3
"""Real DDS subscriptions + reproducible baseline and 10-minute process measurements."""
import argparse
import json
import os
from pathlib import Path
import signal
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import psutil
import yaml
from receiver import Receiver

ROOT = Path(__file__).resolve().parents[1]


def stop(process):
    if process is not None and process.poll() is None:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise RuntimeError('process did not stop within four seconds')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration', type=float, default=600)
    parser.add_argument('--baseline', type=float, default=15)
    parser.add_argument('--domain', type=int, default=87,
                        help='isolated test domain; never used by production bridge config')
    parser.add_argument('--output', type=Path, default=ROOT/'docs/ros_validation.json')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, ROS_DOMAIN_ID=str(args.domain), ROS_LOG_DIR=str(ROOT/'log/ros_validation'),
               PYTHONPATH=str(ROOT/'src/limbo_telemetry_bridge')+os.pathsep+os.environ.get('PYTHONPATH',''))
    samples, baseline, received = [], [], []
    publisher = bridge = None
    receiver = Receiver(('127.0.0.1', 0))
    thread = threading.Thread(target=receiver.serve_forever, daemon=True)
    thread.start()
    port = receiver.server_port
    report = dict(duration_s=args.duration, baseline_s=args.baseline, domain=args.domain,
                  python=sys.version, scenarios=[], samples=samples)
    with tempfile.TemporaryDirectory(prefix='limbo-telemetry-') as tmp:
        temp = Path(tmp)
        metrics = temp/'publisher.json'
        config = yaml.safe_load((ROOT/'src/limbo_telemetry_bridge/config/bridge.yaml').read_text())
        config['server_url'] = f'http://127.0.0.1:{port}'
        config_path = temp/'bridge.yaml'
        config_path.write_text(yaml.safe_dump(config))
        try:
            with (ROOT/'log/publisher_validation.log').open('w') as pub_log, (ROOT/'log/bridge_validation.log').open('w') as bridge_log:
                publisher = subprocess.Popen([sys.executable, str(ROOT/'tools/publisher.py'),
                    '--metrics', str(metrics), '--duration', str(args.baseline+args.duration+10)],
                    env=env, stdout=pub_log, stderr=subprocess.STDOUT)
                pub_process = psutil.Process(publisher.pid)
                pub_process.cpu_percent()
                start = time.monotonic()
                while time.monotonic()-start < args.baseline:
                    time.sleep(1)
                    if publisher.poll() is not None:
                        raise RuntimeError('publisher exited; inspect log')
                    baseline.append(dict(cpu=pub_process.cpu_percent(), rss=pub_process.memory_info().rss))
                bridge = subprocess.Popen([sys.executable, '-m', 'limbo_telemetry_bridge.node',
                    '--config', str(config_path)], env=env, stdout=bridge_log, stderr=subprocess.STDOUT)
                bridge_process = psutil.Process(bridge.pid)
                bridge_process.cpu_percent()
                start = time.monotonic()
                last_mode = None
                while time.monotonic()-start < args.duration:
                    elapsed = time.monotonic()-start
                    mode = ('error' if 120 <= elapsed < 140 else 'delay' if 150 <= elapsed < 170
                            else 'disconnect' if 180 <= elapsed < 195 else 'client_error' if 200 <= elapsed < 215
                            else 'offline' if 230 <= elapsed < 250 else 'ok')
                    if mode != last_mode:
                        if mode == 'offline':
                            receiver.shutdown()
                            receiver.server_close()
                            thread.join(2)
                        elif last_mode == 'offline':
                            report['before_restart_bytes'] = receiver.bytes_received
                            receiver = Receiver(('127.0.0.1', port))
                            thread = threading.Thread(target=receiver.serve_forever, daemon=True)
                            thread.start()
                        receiver.mode = mode
                        report['scenarios'].append(dict(at_s=elapsed, mode=mode))
                        last_mode = mode
                    if bridge.poll() is not None or publisher.poll() is not None:
                        raise RuntimeError('ROS process exited; inspect validation logs')
                    time.sleep(1)
                    try:
                        pub = json.loads(metrics.read_text())
                    except (ValueError, FileNotFoundError):
                        pub = {}
                    with receiver.lock:
                        latest = receiver.latest
                        arrival = receiver.received_mono
                    sample = dict(at_s=elapsed, bridge_cpu=bridge_process.cpu_percent(),
                        bridge_rss=bridge_process.memory_info().rss, publisher_cpu=pub_process.cpu_percent(),
                        publisher_rss=pub_process.memory_info().rss, mode=mode, publisher=pub,
                        accepted=receiver.accepted, bytes_received=receiver.bytes_received,
                        latest=latest, received_mono=arrival)
                    samples.append(sample)
                    if len(samples) % 30 == 0:
                        print(f'{elapsed:.0f}s mode={mode} bridge_rss={sample["bridge_rss"]/1048576:.1f}MiB accepted={receiver.accepted}', flush=True)
                stop_started = time.monotonic()
                stop(bridge)
                report['shutdown_s'] = time.monotonic()-stop_started
                report['bridge_exit_code'] = bridge.returncode
        finally:
            stop(bridge)
            stop(publisher)
            receiver.shutdown()
            receiver.server_close()
            thread.join(2)
            report['baseline'] = baseline
            report['summary'] = summarize(samples, baseline)
            args.output.write_text(json.dumps(report, indent=2, allow_nan=False))
            print(json.dumps(report['summary'], indent=2), flush=True)


def summarize(samples, baseline):
    if not samples:
        return {'error': 'no samples'}
    valid = [s for s in samples if s['latest']]
    steady = [s for s in valid if s['at_s'] >= 280] or valid
    rates = {k: [s['latest']['topics'][k]['receive_hz'] for s in steady
                 if s['latest']['topics'][k]['receive_hz'] is not None]
             for k in ('odom','lidar_raw','lidar_filtered','camera_raw')}
    return dict(
        samples=len(samples), baseline_publisher_cpu_mean=statistics.mean(s['cpu'] for s in baseline),
        baseline_publisher_rss_mean=statistics.mean(s['rss'] for s in baseline),
        publisher_cpu_mean=statistics.mean(s['publisher_cpu'] for s in samples),
        bridge_cpu_mean=statistics.mean(s['bridge_cpu'] for s in samples),
        bridge_rss_min=min(s['bridge_rss'] for s in steady),
        bridge_rss_max=max(s['bridge_rss'] for s in steady),
        bridge_rss_first_steady=steady[0]['bridge_rss'], bridge_rss_last=steady[-1]['bridge_rss'],
        receive_hz_mean={k:statistics.mean(v) if v else None for k,v in rates.items()},
        max_payload_bytes=max(len(json.dumps(s['latest'], separators=(',',':')).encode()) for s in valid),
        all_topics_matched=any(all(v > 0 for v in s['publisher'].get('matched', {}).values())
                               and len(s['publisher'].get('matched', {})) == 4 for s in samples),
    )


if __name__ == '__main__':
    main()
