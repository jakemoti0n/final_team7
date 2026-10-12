#!/usr/bin/env python3
"""Fixed-payload before/after measurement plus real process restart and SIGTERM."""
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
from validate_ros import ROOT, stop


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--domain', type=int, default=88)
    parser.add_argument('--output', type=Path, default=ROOT/'docs/load_comparison.json')
    args = parser.parse_args()
    env = dict(os.environ, ROS_DOMAIN_ID=str(args.domain), ROS_LOG_DIR=str(ROOT/'log/compare_ros'),
               PYTHONPATH=str(ROOT/'src/limbo_telemetry_bridge')+os.pathsep+os.environ.get('PYTHONPATH',''))
    server = Receiver(('127.0.0.1',0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    pub = bridge = None
    report = dict(domain=args.domain, payload_bytes=dict(lidar_raw=1048576,lidar_filtered=1048576,camera_raw=921600))
    try:
        with tempfile.TemporaryDirectory(prefix='limbo-load-') as tmp:
            temp = Path(tmp)
            config = yaml.safe_load((ROOT/'src/limbo_telemetry_bridge/config/bridge.yaml').read_text())
            config['server_url'] = f'http://127.0.0.1:{server.server_port}'
            path = temp/'config.yaml'
            path.write_text(yaml.safe_dump(config))
            command = [sys.executable,'-m','limbo_telemetry_bridge.node','--config',str(path)]
            pub = subprocess.Popen([sys.executable,str(ROOT/'tools/publisher.py'),
                '--metrics',str(temp/'pub.json'),'--duration','120','--constant-large'], env=env)
            process = psutil.Process(pub.pid)
            process.cpu_percent()
            # Same 3,018,752 bytes per tick before and after adding Bridge.
            def measure(seconds, bridge_process=None):
                rows = []
                for _ in range(seconds):
                    time.sleep(1)
                    if pub.poll() is not None:
                        raise RuntimeError('publisher exited')
                    row = dict(publisher_cpu=process.cpu_percent(),publisher_rss=process.memory_info().rss)
                    if bridge_process:
                        row.update(bridge_cpu=bridge_process.cpu_percent(),bridge_rss=bridge_process.memory_info().rss)
                    rows.append(row)
                return rows
            measure(5)
            report['before'] = measure(15)
            bridge = subprocess.Popen(command,env=env)
            bp = psutil.Process(bridge.pid)
            bp.cpu_percent()
            measure(5,bp)
            before_bytes = server.bytes_received
            before_count = server.latest['topics']['odom']['received_count']
            started = time.monotonic()
            report['after'] = measure(30,bp)
            elapsed = time.monotonic()-started
            report['telemetry_bytes_per_second'] = (server.bytes_received-before_bytes)/elapsed
            report['odom_received_hz'] = (server.latest['topics']['odom']['received_count']-before_count)/elapsed
            report['latest'] = server.latest
            old_session = server.session
            stop(bridge)
            # No publisher now: restarting Bridge must reset all topic state.
            stop(pub)
            started = time.monotonic()
            bridge = subprocess.Popen(command,env=env)
            while time.monotonic()-started < 3 and server.session == old_session:
                time.sleep(.01)
            report['restart'] = dict(new_session=server.session != old_session,
                sequence=server.sequence, empty_counts=all(t['received_count']==0 for t in server.latest['topics'].values()))
            server.mode = 'delay'
            # SIGTERM during/near a slow request must also cleanly exit.
            time.sleep(1.1)
            started = time.monotonic()
            bridge.send_signal(signal.SIGTERM)
            bridge.wait(timeout=3)
            report['sigterm_shutdown_s'] = time.monotonic()-started
            report['sigterm_exit_code'] = bridge.returncode
    finally:
        stop(bridge)
        stop(pub)
        server.shutdown()
        server.server_close()
        thread.join(2)
    report['summary'] = {phase:{key:statistics.mean(row[key] for row in report[phase])
                               for key in report[phase][0]} for phase in ('before','after')}
    report['all_passed'] = (report['restart']['new_session'] and report['restart']['sequence']==1
        and report['restart']['empty_counts'] and report['sigterm_exit_code']==0
        and report['sigterm_shutdown_s']<2 and 18<=report['odom_received_hz']<=22)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('before','after','latest')},indent=2))
    raise SystemExit(0 if report['all_passed'] else 1)


if __name__=='__main__':
    main()
