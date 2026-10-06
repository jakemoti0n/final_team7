#!/usr/bin/env python3
"""Assert the recorded full ROS scenario; emit a small reviewable evidence summary."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import statistics
from receiver import validate


def analyze(report):
    samples = report['samples']
    valid = [s for s in samples if s['latest']]
    for sample in valid:
        validate(sample['latest'])
    unique = {}
    for s in valid:
        unique[(s['latest']['bridge_session_id'], s['latest']['sequence'])] = s
    snapshots = sorted(unique.values(), key=lambda s: s['at_s'])
    def topic(sample, key='odom'):
        return sample['latest']['topics'][key]
    latency = []
    for s in snapshots:
        at = topic(s)['last_received_at']
        if at and s['mode'] == 'ok' and topic(s)['age_ms'] < 1000:
            # Same host UTC only for this local test; production freshness uses monotonic age.
            sent = datetime.fromisoformat(s['latest']['sent_at'].replace('Z','+00:00'))
            received = datetime.fromisoformat(at.replace('Z','+00:00'))
            latency.append((sent-received).total_seconds()*1000)
    all_stopped = [s for s in snapshots if all(t['age_ms'] is not None and t['age_ms'] > 5000
                                              for t in s['latest']['topics'].values())]
    camera_stopped = [s for s in snapshots if topic(s,'camera_raw')['age_ms'] is not None
                      and topic(s,'camera_raw')['age_ms'] > 5000 and topic(s)['age_ms'] < 1000]
    after_outage = next((s for s in snapshots if s['at_s'] > 250 and topic(s)['age_ms'] < 1000), None)
    before_outage = next((s for s in reversed(snapshots) if s['at_s'] < 230), None)
    normal = [s for s in snapshots if s['at_s'] > 280]
    gaps = [b['received_mono']-a['received_mono'] for a,b in zip(normal,normal[1:])]
    clock_headers = [topic(s)['header_stamp']['sec'] for s in snapshots if topic(s)['header_stamp']]
    checks = dict(
        full_10_minutes=report['duration_s'] >= 600 and len(samples) >= 590,
        qos_all_four_matched=report['summary']['all_topics_matched'],
        independent_v1_validation=True,
        bounded_payload=report['summary']['max_payload_bytes'] <= 8192,
        normal_receive_rates=all(v is not None and 18 <= v <= 22 for v in report['summary']['receive_hz_mean'].values()),
        stopped_camera=bool(camera_stopped) and any(topic(s,'camera_raw')['receive_hz'] == 0 for s in camera_stopped),
        stopped_all=bool(all_stopped) and any(all(t['receive_hz'] == 0 for t in s['latest']['topics'].values()) for s in all_stopped),
        zero_speed_rotation=any(s['latest']['motion']['linear_speed_mps'] == 0 and
                                s['latest']['motion']['angular_velocity_radps'] == .75 for s in snapshots),
        invalid_odom=any(topic(s)['received_count'] > 0 and s['latest']['motion']['linear_speed_mps'] is None for s in snapshots),
        clock_pause_and_reversal=100 in clock_headers and 2 in clock_headers and
                                 any(b<a for a,b in zip(clock_headers,clock_headers[1:])),
        latest_after_real_server_restart=bool(after_outage and before_outage and
            topic(after_outage)['received_count']-topic(before_outage)['received_count'] >= 400),
        continued_collection_during_errors=all(any(s['mode'] == mode for s in samples)
            for mode in ('error','delay','disconnect','client_error','offline')) and bool(after_outage),
        normal_heartbeat_within_2s=bool(gaps) and max(gaps) < 2,
        shutdown_bounded=report['shutdown_s'] < 2 and report['bridge_exit_code'] == 0,
        steady_rss_growth_under_16mib=report['summary']['bridge_rss_last']-report['summary']['bridge_rss_first_steady'] < 16*1048576,
    )
    return dict(checks=checks, all_passed=all(checks.values()), measurements=report['summary'],
                shutdown_s=report['shutdown_s'], unique_snapshots=len(snapshots),
                normal_max_heartbeat_gap_s=max(gaps) if gaps else None,
                local_callback_to_snapshot_ms_max=max(latency) if latency else None,
                local_callback_to_snapshot_ms_mean=statistics.mean(latency) if latency else None,
                bytes_accepted=report.get('before_restart_bytes',0)+samples[-1]['bytes_received'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('report', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = analyze(json.loads(args.report.read_text()))
    text = json.dumps(result, indent=2)
    print(text)
    if args.output:
        args.output.write_text(text+'\n')
    raise SystemExit(0 if result['all_passed'] else 1)


if __name__ == '__main__':
    main()
