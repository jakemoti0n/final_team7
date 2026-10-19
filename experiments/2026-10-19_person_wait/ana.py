"""회차 로그 집계. 사용법: ana.py <라벨>...  (~/limbo_bags/sim_trials/logs/{sim,trial}_<라벨>.*)
목표(구간)마다: 결과·시간(nav.log), 사람 최소·충돌·장애물 최소(CSV), 그 구간의 /person_wait 전이(WAITING 진입 사유별 수·
대기 최대 s), 경보·abort 수, spin/backup 수와 그때 상태 기계 상태, FrontStop 정지 시간, 대기 중에 끝난 목표(타이머 종료 의심)."""
import csv, os, re, sys
from collections import Counter

LOGS = os.path.expanduser('~/limbo_bags/sim_trials/logs')
TS = re.compile(r'\[(\d{10}\.\d+)\]')


def stamp(line):
    m = TS.search(line)
    return float(m.group(1)) if m else None


def goals(lines):
    """bt_navigator 목표 구간 [(시작, 끝, 결과)]."""
    out, start = [], None
    for line in lines:
        if '[bt_navigator]' not in line:
            continue
        t = stamp(line)
        if 'Begin navigating' in line:
            if start is not None:
                out.append((start, t, 'PREEMPTED'))
            start = t
        elif start is not None and ('Goal succeeded' in line or 'Aborting handle' in line or 'canceled' in line):
            out.append((start, t, 'SUCCEEDED' if 'succeeded' in line else 'ABORTED' if 'Abort' in line else 'CANCELED'))
            start = None
    return out


def segment(lines, t0, t1, state_at_start):
    s = {'enter': Counter(), 'wait_max': 0.0, 'alarm': 0, 'abort': 0, 'spin': 0, 'backup': 0,
         'recovery_states': Counter(), 'frontstop': 0.0, 'end_state': state_at_start}
    state, wait_since, stop_since = state_at_start, (t0 if state_at_start == 'WAITING' else None), None
    for line in lines:
        t = stamp(line)
        if t is None or t < t0 or t > t1:
            continue
        m = re.search(r'\[person_wait\]: (\w+) ← (\w+): (\w+)', line)
        if m:
            state = m.group(1)
            if state == 'WAITING':
                s['enter'][m.group(3)] += 1
                wait_since = t
            elif wait_since is not None:
                s['wait_max'] = max(s['wait_max'], t - wait_since)
                wait_since = None
        if '[person_wait]' in line and 'alarm' in line:
            s['alarm'] += 1
        if 'abort_pull_over' in line or '← PULL_OVER: person_moved' in line:
            s['abort'] += 1
        if '[behavior_server]' in line and re.search(r'Running (spin|backup)', line):
            kind = 'spin' if 'spin' in line else 'backup'
            s[kind] += 1
            s['recovery_states'][state] += 1
        if 'FrontStop polygon' in line and ('Robot to stop' in line or 'Robot to limit' in line):
            stop_since = stop_since or t
        elif stop_since is not None and '[collision_monitor]' in line and 'Robot to' in line and 'FrontStop' not in line:
            s['frontstop'] += t - stop_since
            stop_since = None
    if wait_since is not None:
        s['wait_max'] = max(s['wait_max'], t1 - wait_since)
    if stop_since is not None:
        s['frontstop'] += t1 - stop_since
    s['end_state'] = state
    return s


def main():
    print('라벨|구간|결과|시간 s|사람 최소 m|충돌|장애물 최소 m|WAITING 진입|대기 최대 s|경보|spin/backup(상태)|FrontStop s|대기 중 종료')
    for label in sys.argv[1:]:
        lines = open(f'{LOGS}/sim_{label}.log', errors='replace').read().splitlines()
        nav = [line.split('→') for line in open(f'{LOGS}/trial_{label}.nav.log') if '→' in line]
        rows = list(csv.DictReader(open(f'{LOGS}/trial_{label}.csv'))) if os.path.exists(f'{LOGS}/trial_{label}.csv') else []
        state = 'DRIVING'
        for i, (t0, t1, result) in enumerate(goals(lines)):
            s = segment(lines, t0, t1, state)
            state = s['end_state']
            name = nav[i][0].strip() if i < len(nav) else '?'
            row = rows[i] if i < len(rows) else {}
            enter = ' '.join(f'{k}{v}' for k, v in s['enter'].items()) or '0'
            rec = f"{s['spin']}/{s['backup']}" + (f" ({' '.join(f'{k}{v}' for k, v in s['recovery_states'].items())})" if s['recovery_states'] else '')
            timer_end = 'yes' if result != 'SUCCEEDED' and state == 'WAITING' else ''
            print(f"{label}|{name}|{result}|{t1 - t0:.1f}|{row.get('min_person_distance_m', '')}|{row.get('person_collision', '')}|"
                  f"{row.get('min_obstacle_distance_m', '')}|{enter}|{s['wait_max']:.1f}|{s['alarm']}|{rec}|{s['frontstop']:.1f}|{timer_end}")


main()
