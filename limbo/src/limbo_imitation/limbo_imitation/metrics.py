"""
한 바퀴의 결과 지표와 학습에서 뺄 구간을 계산한다. rclpy를 쓰지 않는다.

입력은 RunLog 하나다. 기록기(run_recorder)가 기록 중 구독한 값을 시각과 함께 리스트에 쌓는다.
시각은 모두 초(float). 값은 다음 샘플이 올 때까지 그대로라고 본다(마지막 샘플은 end_time까지).

개인 공간 침범은 로봇이 움직이는 중(odom 속도 > stop_speed)일 때만 센다(설계 2-1).
멈춰 있는 로봇에 사람이 걸어 들어온 것은 손님 응대이지 로봇 잘못이 아니다.
limbo_evaluation의 사람 탓/로봇 탓 구분(최소 거리 순간의 로봇 속도)과 같은 기준이다.
min_person_dist는 참고용 전체 최소 거리, 합격 판정은 min_person_dist_moving으로 한다.

한 시계열의 각 샘플마다 다른 시계열의 "그때 값"을 찾을 때는 시각 목록을 한 번만 만들고
이분 탐색한다. 찾을 때마다 목록을 새로 만들면 바퀴 길이의 제곱으로 느려져, 4~5분 바퀴에서
종료 때 지표 계산이 수 초~수십 초 걸렸다(2026-11-25, 기록기 종료가 늦어진 원인 중 하나).
"""

import bisect
from dataclasses import dataclass, field
import math

# nav2_msgs/CollisionMonitorState.STOP. 메시지를 import하면 rclpy 없이 시험할 수 없어 값을 옮겨 둔다
COLLISION_MONITOR_STOP = 1

PATROL_COMPLETED = 'completed'
# 기록기가 /patrol/state 없이 노드 시작 즉시 기록을 시작한 바퀴(run_recorder의 start_reason)
START_MANUAL = 'manual_start'
# 그런 바퀴의 completed 값. 끝을 아는 것은 운전자뿐이라 True/False 대신 이 글자를 남긴다
COMPLETED_MANUAL = 'manual'
# 패드 기록 버튼으로 시작한 바퀴(run_recorder의 start_reason이자 버튼으로 끝낸 end_reason).
# 사람이 HOME에서 시작해 HOME에서 끊으므로 manual_start와 같이 완주를 운전자에게 맡긴다
START_BUTTON = 'button'
DRIVER_ENDED_STARTS = (START_MANUAL, START_BUTTON)
SOURCE_TELEOP = 'teleop'
SOURCE_NAV = 'nav'
MODE_MANUAL = 'manual'
MODE_POLICY = 'policy'
MODE_POLICY_ASSIST = 'policy_assist'

DEFAULT_SETTINGS = {
    'collision_distance': 0.25,
    'personal_space': 0.5,
    'stop_speed': 0.05,
    'jerk_w': 0.5,
    'collision_margin': 5.0,
    'stuck_min_duration': 1.0,
    'clip_tolerance': 0.01,
}

METRIC_COLUMNS = [
    'collisions', 'collision_monitor_stops', 'scan_collisions',
    'min_person_dist', 'min_person_dist_moving', 'personal_space_time',
    'completed', 'duration', 'distance',
    'stuck_time', 'wobble_ratio',
    'intervention_count', 'intervention_time', 'nav_fallback_count',
]
ROW_COLUMNS = METRIC_COLUMNS + ['passed', 'fail_reasons']


@dataclass
class RunLog:
    """한 바퀴 동안 쌓은 시계열. 튜플의 첫 값은 늘 시각(초)."""

    start_time: float = 0.0
    end_time: float = 0.0
    start_reason: str = ''                              # DRIVER_ENDED_STARTS면 완주 판정을 운전자에게 맡김
    patrol_states: list = field(default_factory=list)   # (t, state 문자열)
    monitor_states: list = field(default_factory=list)  # (t, action_type)
    scan_min: list = field(default_factory=list)        # (t, 라이다 최근접 거리 m)
    person_dist: list = field(default_factory=list)     # (t, 가장 가까운 사람 거리 m, 없으면 inf)
    odom: list = field(default_factory=list)            # (t, x, y, v, w)
    cmd: list = field(default_factory=list)             # (t, v, w) 중재기 출력 = collision_monitor 입력
    cmd_out: list = field(default_factory=list)         # (t, v, w) collision_monitor 출력(/cmd_vel)
    drive_modes: list = field(default_factory=list)     # (t, source, mode)


def scan_min_range(ranges, range_min, range_max):
    """라이다 한 장에서 유효한 점 중 가장 가까운 거리. 유효한 점이 없으면 inf."""
    valid = [r for r in ranges if math.isfinite(r) and range_min <= r <= range_max]
    return min(valid) if valid else math.inf


def runs(samples, is_on, end_time):
    """조건이 참인 연속 구간 [(시작, 끝)]. 샘플 값은 다음 샘플(마지막은 end_time)까지 유지된다."""
    intervals = []
    start = None
    for sample in samples:
        on = is_on(sample)
        if on and start is None:
            start = sample[0]
        if not on and start is not None:
            intervals.append((start, sample[0]))
            start = None
    if start is not None:
        intervals.append((start, max(end_time, start)))
    return intervals


def total_time(intervals):
    return sum(end - start for start, end in intervals)


def sample_times(samples):
    return [s[0] for s in samples]


def latest_before(samples, times, t):
    """시각 t 이전(같은 시각 포함)의 마지막 샘플. 없으면 None.

    samples는 시각 순, times는 sample_times(samples)로 한 번 만들어 넘긴다.
    """
    index = bisect.bisect_right(times, t) - 1
    return samples[index] if index >= 0 else None


def person_dist_while_moving(log, settings):
    """사람 거리 샘플 중 로봇이 서 있던 때는 inf로 바꾼다(그 순간은 로봇 탓 침범이 아님).

    샘플을 지우지 않고 inf로 두는 이유: runs가 다음 샘플까지 값을 유지하므로,
    지우면 앞의 '가까움'이 로봇이 멈춘 뒤까지 이어진 것으로 계산된다.
    """
    stop_speed = settings['stop_speed']
    odom_times = sample_times(log.odom)
    result = []
    for t, dist in log.person_dist:
        odom = latest_before(log.odom, odom_times, t)
        moving = odom is not None and abs(odom[3]) > stop_speed
        result.append((t, dist if moving else math.inf))
    return result


def personal_space_intervals(log, settings):
    """로봇이 움직이는 중에 사람이 personal_space 안에 있던 구간."""
    moving = person_dist_while_moving(log, settings)
    return runs(moving, lambda s: s[1] < settings['personal_space'], log.end_time)


def collision_intervals(log, settings):
    """collision_monitor 정지 구간과 라이다 최근접점이 collision_distance 안인 구간."""
    stops = runs(log.monitor_states, lambda s: s[1] == COLLISION_MONITOR_STOP, log.end_time)
    close = runs(log.scan_min, lambda s: s[1] < settings['collision_distance'], log.end_time)
    return stops, close


def stuck_intervals(log, settings):
    """명령은 가라는데(v > stop_speed) 로봇이 안 움직이는(odom v < stop_speed) 구간.

    stuck_min_duration보다 짧은 구간은 뺀다. 출발할 때마다 모터 응답·odom 지연만큼은
    명령과 실제가 어긋나는데, 그건 갇힘이 아니다.
    """
    stop_speed = settings['stop_speed']
    cmd_times = sample_times(log.cmd)
    flags = []
    for t, _, _, v, _ in log.odom:
        command = latest_before(log.cmd, cmd_times, t)
        flags.append((t, command is not None and command[1] > stop_speed
                      and abs(v) < stop_speed))
    intervals = runs(flags, lambda s: s[1], log.end_time)
    return [(a, b) for a, b in intervals if b - a >= settings['stuck_min_duration']]


def clipped_intervals(log, settings):
    """collision_monitor가 명령을 깎은 구간: 출력 명령이 바로 앞 입력 명령과 다른 때."""
    tolerance = settings['clip_tolerance']
    cmd_times = sample_times(log.cmd)
    flags = []
    for t, v_out, w_out in log.cmd_out:
        command = latest_before(log.cmd, cmd_times, t)
        differs = command is not None and (abs(command[1] - v_out) > tolerance
                                           or abs(command[2] - w_out) > tolerance)
        flags.append((t, differs))
    return runs(flags, lambda s: s[1], log.end_time)


def odom_distance(odom):
    return sum(math.hypot(b[1] - a[1], b[2] - a[2]) for a, b in zip(odom, odom[1:]))


def wobble_ratio(cmd, jerk_w):
    """이웃한 명령 샘플 사이 각속도 변화가 jerk_w를 넘는 비율(비틀거림)."""
    if len(cmd) < 2:
        return 0.0
    jumps = sum(1 for a, b in zip(cmd, cmd[1:]) if abs(b[2] - a[2]) > jerk_w)
    return jumps / (len(cmd) - 1)


def mode_switch_intervals(drive_modes, source, modes, end_time):
    """주행 모드가 modes 중 하나일 때 명령 출처가 source였던 구간(끼어들기·MPPI 전환)."""
    return runs(drive_modes, lambda s: s[1] == source and s[2] in modes, end_time)


def run_completed(log):
    """완주 여부. 수동 시작·버튼 시작 바퀴는 COMPLETED_MANUAL.

    수동 시작·버튼 시작 바퀴에는 /patrol/state가 없어 완주를 기계가 알 수 없다. 운전자가 기록을 끝낸 것을
    완주로 본다. False로 두면 멀쩡한 수동 바퀴가 전부 불합격이 되고, True로 두면 CSV만 보고
    순찰 노드가 완주를 확인한 바퀴와 구별할 수 없다.
    """
    if log.start_reason in DRIVER_ENDED_STARTS:
        return COMPLETED_MANUAL
    return any(state == PATROL_COMPLETED for _, state in log.patrol_states)


def compute_metrics(log, settings=None):
    """한 바퀴 지표를 METRIC_COLUMNS 순서의 dict 한 줄로 낸다."""
    settings = {**DEFAULT_SETTINGS, **(settings or {})}
    stops, close = collision_intervals(log, settings)
    person = [s[1] for s in log.person_dist]
    person_moving = [s[1] for s in person_dist_while_moving(log, settings)]
    personal = personal_space_intervals(log, settings)
    assist = (MODE_POLICY_ASSIST,)
    interventions = mode_switch_intervals(log.drive_modes, SOURCE_TELEOP, assist, log.end_time)
    fallbacks = mode_switch_intervals(log.drive_modes, SOURCE_NAV,
                                      (MODE_POLICY, MODE_POLICY_ASSIST), log.end_time)
    return {
        'collisions': len(stops) + len(close),
        'collision_monitor_stops': len(stops),
        'scan_collisions': len(close),
        'min_person_dist': min(person) if person else math.inf,
        'min_person_dist_moving': min(person_moving) if person_moving else math.inf,
        'personal_space_time': total_time(personal),
        'completed': run_completed(log),
        'duration': log.end_time - log.start_time,
        'distance': odom_distance(log.odom),
        'stuck_time': total_time(stuck_intervals(log, settings)),
        'wobble_ratio': wobble_ratio(log.cmd, settings['jerk_w']),
        'intervention_count': len(interventions),
        'intervention_time': total_time(interventions),
        'nav_fallback_count': len(fallbacks),
    }


def passed(metrics, rules):
    """합격 판정. rules = {'personal_space': m}. (합격 여부, [불합격 이유]) 를 낸다."""
    reasons = []
    if metrics['collisions'] > 0:
        reasons.append(f"collisions {metrics['collisions']}")
    if metrics['min_person_dist_moving'] < rules['personal_space']:
        reasons.append(f"min_person_dist_moving {metrics['min_person_dist_moving']:.2f} < "
                       f"{rules['personal_space']}")
    if metrics['completed'] is False:  # COMPLETED_MANUAL은 운전자가 끝낸 것이라 통과
        reasons.append('not completed')
    if metrics['stuck_time'] > 0:
        reasons.append(f"stuck {metrics['stuck_time']:.1f} s")
    return len(reasons) == 0, reasons


def merge_intervals(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def bad_intervals(log, settings=None):
    """학습에서 뺄 구간 [(시작, 끝)], 겹치면 합친다.

    충돌은 앞뒤 collision_margin까지 뺀다. 충돌 직전 몇 초의 운전이 충돌을 만든 운전이라
    그것을 따라 배우면 안 되고, 직후는 놀란 사람이 평소와 다르게 움직이기 때문이다.
    """
    settings = {**DEFAULT_SETTINGS, **(settings or {})}
    margin = settings['collision_margin']
    stops, close = collision_intervals(log, settings)
    collisions = [(a - margin, b + margin) for a, b in stops + close]
    personal = personal_space_intervals(log, settings)
    return merge_intervals(collisions + personal + stuck_intervals(log, settings)
                           + clipped_intervals(log, settings))


def metrics_row(metrics, rules):
    """CSV 한 줄: 지표 + 합격 여부 + 불합격 이유(';'로 이음)."""
    ok, reasons = passed(metrics, rules)
    return {**metrics, 'passed': ok, 'fail_reasons': '; '.join(reasons)}
