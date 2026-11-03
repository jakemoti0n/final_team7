"""Assess a completed Limbo bench record. Reads files only; never controls a motor.

Legacy summary.passed describes execution/cleanup, not wheel movement or speed
tracking. This tool keeps that result separate and rejects unverified wire data.
"""
import argparse
import binascii
import json
import math
from pathlib import Path
import struct


def signed_delta(a, b):
    return ((b - a + 2**31) % 2**32) - 2**31


def assess(folder):
    folder = Path(folder)
    if (folder / 'node/summary.json').is_file():
        folder = folder / 'node'
    summary = json.loads((folder / 'summary.json').read_text(encoding='utf-8'))
    wire = [json.loads(s) for s in (folder / 'wire.jsonl').read_text(encoding='utf-8').splitlines()]
    writes, counts, pwms = [], [], []
    previous_time = -math.inf
    for row in wire:
        tx, rx = bytes.fromhex(row['tx_hex']), bytes.fromhex(row['rx_hex'])
        stamp = row['monotonic_s']
        if not math.isfinite(stamp) or stamp < previous_time:
            raise ValueError('Non-monotonic wire record')
        previous_time = stamp
        if not row.get('success') or row.get('written') != len(tx):
            raise ValueError('Failed wire transaction; movement acceptance unavailable')
        command = row['command']
        if tx[:2] != bytes((128, command)):
            raise ValueError('Address/command mismatch')
        if command == 34:
            if len(tx) != 8 or rx != b'\xff' or binascii.crc_hqx(tx[:-2], 0) != int.from_bytes(tx[-2:], 'big'):
                raise ValueError('Invalid duty packet/ACK/CRC')
            writes.append((stamp, struct.unpack('>hh', tx[2:6])))
        else:
            if len(tx) != 2 or len(rx) < 3 or binascii.crc_hqx(tx + rx[:-2], 0) != int.from_bytes(rx[-2:], 'big'):
                raise ValueError('Invalid read packet/CRC')
            if command == 78:
                if len(rx) != 10:
                    raise ValueError('Invalid paired counter length')
                counts.append((stamp, struct.unpack('>II', rx[:-2])))
            if command == 48:
                if len(rx) != 6:
                    raise ValueError('Invalid PWM length')
                pwms.append((stamp, struct.unpack('>hh', rx[:-2])))
    nonzero = [w for w in writes if any(w[1])]
    if not nonzero:
        return {'schema':'limbo_motion_outcome_v1','assessment':'not_commanded',
                'legacy_execution_passed':summary.get('passed'),
                'motion_requirement_met':False,'speed_tracking_assessed':False}
    first, last = nonzero[0][0], nonzero[-1][0]
    zeros = [w for w in writes if not any(w[1]) and w[0] > last]
    if not zeros or not any(t < first for t,_ in counts):
        raise ValueError('Missing baseline or final zero')
    zero_time = zeros[0][0]
    baseline = [r for r in counts if r[0] < first][-1][1]
    active_counts = [r for r in counts if first <= r[0] < zero_time]
    if not active_counts:
        raise ValueError('No count observations during commanded interval')
    wheels = {}
    for index,(name,encoder_sign) in enumerate((('right',1),('left',-1))):
        directions = {1 if w[1][index] > 0 else -1 for w in nonzero if w[1][index]}
        if not directions:
            wheels[name] = {'commanded':False,'motion_detected':None}
            continue
        if len(directions) != 1:
            raise ValueError('Direction-changing record requires separate segments')
        sign = next(iter(directions)) * encoder_sign
        progress = [0] + [sign * signed_delta(baseline[index], r[1][index]) for r in active_counts]
        positive = sum(b > a for a,b in zip(progress,progress[1:]))
        negative = sum(b < a for a,b in zip(progress,progress[1:]))
        motion = max(progress) >= 5 and positive >= 3
        wheels[name] = {'commanded':True,'motion_detected':motion,
                        'command_direction':next(iter(directions)),
                        'maximum_directional_progress_counts':max(progress),
                        'net_directional_progress_counts':progress[-1],
                        'positive_sample_increments':positive,'negative_sample_increments':negative}
    active = [w for w in wheels.values() if w['commanded']]
    detected = sum(w['motion_detected'] for w in active)
    category = 'all_commanded_wheels_moved' if detected == len(active) else 'no_motion_detected' if detected == 0 else 'partial_motion_detected'
    stop = summary.get('stop', {})
    stop_verified = all(stop.get(k) is True for k in ('zero_acked','stationary_verified','closed')) and bool(pwms) and pwms[-1][0] > zero_time and pwms[-1][1] == (0,0)
    cap = summary.get('settings',{}).get('max_duty_raw')
    cap_times = {name:sum(b[0]-a[0] for a,b in zip(writes,writes[1:]) if cap and abs(a[1][i]) == cap)
                 for i,name in enumerate(('right','left'))}
    return {'schema':'limbo_motion_outcome_v1','assessment':category,
            'legacy_execution_passed':summary.get('passed'),
            'reported_stop_reason':summary.get('stop_reason'),
            'reported_errors':summary.get('errors',[]),
            'motion_requirement_met':detected == len(active),
            'motion_and_stop_confirmed':detected == len(active) and stop_verified,
            'stop_verified':stop_verified,'wheels':wheels,'duty_cap_exposure_seconds':cap_times,
            'nonzero_write_count':len(nonzero),'wire_transactions_verified':len(wire),
            'criterion':'Each commanded wheel: >=5 directional encoder counts and >=3 positive sample increments during nonzero-command interval. This is a movement check, not speed/odometry acceptance.',
            'speed_tracking_assessed':False,
            'limitations':['Cannot distinguish electrical, mechanical or encoder causes of no observed motion.',
                           'Encoder motion does not independently prove body translation or absence of slip.',
                           'Legacy execution outcome and guard errors are preserved.']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('trial_dir',type=Path)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():
        raise FileExistsError('Refusing to overwrite an existing assessment')
    result=assess(args.trial_dir)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result.get('motion_and_stop_confirmed') else 2


if __name__=='__main__':
    raise SystemExit(main())
