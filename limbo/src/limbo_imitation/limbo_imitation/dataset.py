"""
바퀴 기록 폴더들(bag·meta.json·metrics.csv) → 학습용 .npz. rclpy 노드는 쓰지 않는다(bag 읽기만 rosbag2_py).

표본 하나 = /scan 한 장(10 Hz)이 도착한 시각 t.
- 입력: t 기준 최신 /odom 속도, /tf로 합성한 로봇 자세(map→odom→base_footprint), /patrol/state의
  경유점, 사람 예측 → frame_builder.assemble_frame(정책 노드와 같은 함수) → 최근 3프레임 279칸.
- 정답: t 직전 label_window 안의 운전자 원 명령(/cmd_vel_teleop). 그 시각 /drive_mode의 source가
  teleop일 때만 쓴다. nav(MPPI)는 스승이 아니라서(PM 결정), policy는 정책 자신의 명령이라서 뺀다.
- 수동(manual) 바퀴에서 데드맨을 뗀 구간(source none, reason 'manual without deadman')은 정답 (0, 0).
  중재기가 그때 실제로 0을 내 로봇이 서므로 사람의 "멈춤" 결정이다(손님 앞에서 기다리기, 설계 2-1).
  그 바퀴의 첫 데드맨 누름 ~ 마지막 뗌 사이만 넣는다. 출발 전·도착 후 대기는 운전 결정이 아니다.
  policy·policy_assist에서 데드맨 뗌은 "정책에 맡김"이라 넣지 않는다(PM 2026-11-26).
- 거르기: metrics.bad_intervals(충돌 앞뒤·개인 공간 침범·갇힘·collision_monitor가 깎은 구간) 안의
  표본은 뺀다. 불합격 바퀴도 통째로 버리지 않고 그 구간만 뺀다(PM 결정).
  사람이 정한 제외(바퀴 통째·구간)는 데이터 옆 제외 목록 파일(exclusions.yaml, load_exclusions)에서 읽는다.
- 경유점: /patrol/state가 있는 바퀴(순찰·정책 주행)는 그것을, 없는 바퀴(패드 버튼 수동 바퀴)는
  waypoint_progress로 map 위치에서 순찰 노드와 같은 규칙으로 번호를 계산한다(반경은 실물 Nav2 설정에서 읽음).
- 스캔: 스캔 프레임의 장착 자세(bag /tf_static 또는 tf_static.json)로 base 기준으로 옮긴다. 못 찾으면 no_scan_tf.
- 사람 예측이 input_timeout 넘게 끊긴 표본도 뺀다. person_detector는 처리한 프레임마다 빈 목록이라도
  예측을 내므로 끊김은 "사람 없음"이 아니라 "카메라·인식이 죽음"이다(정책 노드는 그때 MPPI로 넘긴다).
  그래서 기록은 카메라를 켠 채로 해야 표본이 남는다.
- 시각은 모두 bag 수신 시각이다. 기록기의 지표도 수신 시각(노드 시계)으로 쟀고, 정책 노드도
  메시지가 도착한 순간의 최신 값으로 판단하므로 그 상황을 그대로 재현한다.
"""

import argparse
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass, field
import json
import math
import os
import sys

from limbo_imitation import (arbiter_logic, config_file, features, frame_builder, metrics,
                             robot_geometry, run_files, waypoint_progress)
import numpy as np
import yaml

SOURCE_TELEOP = metrics.SOURCE_TELEOP
SOURCE_NAV = metrics.SOURCE_NAV
NS_PER_SEC = 1e9
SECTION = 'build_dataset'
# 데이터 폴더 옆 제외 목록(바퀴 통째·구간, 사람이 정함). load_exclusions 참고
EXCLUSIONS_FILE = 'exclusions.yaml'
DEFAULTS = {
    'label_window': 0.2,
    'intervention_weight': 2.0,
    'val_fraction': 0.2,
    'seed': 0,
    'input_timeout': 0.5,
    'map_frame': 'map',
    'odom_frame': 'odom',
    'base_frame': 'base_footprint',
    'nav2_params_file': '',   # 비면 limbo_navigation의 nav2_real.yaml(발판·도착 허용 오차)
    'patrol_bt_file': '',     # 비면 limbo_navigation의 실물 순찰 BT(경유점 통과 반경)
    'pass_radius': None,      # 비면 patrol_bt_file의 RemovePassedGoals radius
    'stop_tolerance': None,   # 비면 nav2_params_file의 xy_goal_tolerance
    **frame_builder.settings_to_dict(frame_builder.FrameSettings()),
}


class Series:
    """시각 순 표본 목록. latest(t)로 t 이전(같은 시각 포함) 마지막 값을 찾는다."""

    def __init__(self, samples=()):
        self.times = [s[0] for s in samples]
        self.values = [s[1] for s in samples]

    def add(self, t, value):
        self.times.append(t)
        self.values.append(value)

    def sort(self):
        order = sorted(range(len(self.times)), key=self.times.__getitem__)
        self.times = [self.times[i] for i in order]
        self.values = [self.values[i] for i in order]

    def latest(self, t):
        """(시각, 값) 또는 None."""
        index = bisect_right(self.times, t) - 1
        return (self.times[index], self.values[index]) if index >= 0 else None

    def tuples(self):
        """metrics.RunLog 형식 [(t, 값들...)]."""
        return [(t,) + tuple(v) if isinstance(v, tuple) else (t, v)
                for t, v in zip(self.times, self.values)]


@dataclass
class BagStreams:
    """bag 한 개에서 꺼낸 값들. 손으로 만들어 시험할 수 있게 ROS 메시지를 남기지 않는다."""

    start_time: float = 0.0
    end_time: float = 0.0
    # (ranges, angle_min, angle_inc, r_min, r_max, 스캔 프레임)
    scans: Series = field(default_factory=Series)
    odom: Series = field(default_factory=Series)        # (x, y, v, w) odom 좌표
    tf: dict = field(default_factory=dict)              # (부모, 자식) → Series of (x, y, yaw)
    tf_static: dict = field(default_factory=dict)       # (부모, 자식) → (x, y, yaw)
    patrol: Series = field(default_factory=Series)      # (state, waypoint_index)
    # waypoint_index. /patrol/state 없는 바퀴용(derive_waypoints)
    derived_waypoint: Series = field(default_factory=Series)
    predictions: Series = field(default_factory=Series)  # [(x, y, vx, vy)] odom 좌표
    drive_modes: Series = field(default_factory=Series)  # (source, mode, reason)
    teleop: Series = field(default_factory=Series)      # (v, w)
    cmd: Series = field(default_factory=Series)         # (v, w) 중재기 출력
    cmd_out: Series = field(default_factory=Series)     # (v, w) collision_monitor 출력
    monitor_states: Series = field(default_factory=Series)  # action_type


def lookup_pose(streams, parent, child, t):
    """(부모 → 자식 자세, 나이 초) 또는 None. 정적 변환은 나이 0."""
    if (parent, child) in streams.tf_static:
        return streams.tf_static[(parent, child)], 0.0
    series = streams.tf.get((parent, child))
    found = series.latest(t) if series is not None else None
    if found is None:
        return None
    return found[1], t - found[0]


def robot_poses(streams, t, cfg):
    """(map 기준 자세, odom 기준 자세, 둘 중 오래된 쪽 나이) 또는 None.

    tf2 없이 bag의 TransformStamped 두 개(map→odom, odom→base)를 직접 합성한다.
    정책 노드의 tf2 lookup(최신 공통 시각)과 같은 뜻이 되게 더 오래된 쪽 나이를 낸다.
    """
    map_odom = lookup_pose(streams, cfg['map_frame'], cfg['odom_frame'], t)
    odom_base = lookup_pose(streams, cfg['odom_frame'], cfg['base_frame'], t)
    if map_odom is None or odom_base is None:
        return None
    pose_map = frame_builder.compose_poses(map_odom[0], odom_base[0])
    return pose_map, odom_base[0], max(map_odom[1], odom_base[1])


def age_of(series, t):
    found = series.latest(t)
    return None if found is None else t - found[0]


def inputs_at(streams, t, waypoints, cfg):
    """시각 t의 입력 원재료 dict 또는 모자란 이유(문자열, frame_builder.input_problem과 같은 말)."""
    poses = robot_poses(streams, t, cfg)
    if streams.patrol.times:
        patrol = streams.patrol.latest(t)
        index = patrol[1][1] if patrol else None
    else:
        derived = streams.derived_waypoint.latest(t)
        index = derived[1] if derived else None
    goal = frame_builder.waypoint_goal(waypoints, index)
    ages = {'tf': poses[2] if poses else None, 'odom': age_of(streams.odom, t),
            'people': age_of(streams.predictions, t)}
    problem = frame_builder.input_problem(ages, goal, cfg['input_timeout'])
    if problem is not None:
        return problem
    _, _, v, w = streams.odom.latest(t)[1]
    return {'pose_map': poses[0], 'pose_odom': poses[1], 'goal': goal, 'velocity': (v, w),
            'people': streams.predictions.latest(t)[1]}


def teleop_span(drive_modes):
    """(첫, 마지막) source가 teleop인 /drive_mode 시각. 없으면 None. 데드맨 첫 누름 ~ 마지막 뗌의 범위."""
    times = [t for t, value in zip(drive_modes.times, drive_modes.values)
             if value[0] == SOURCE_TELEOP]
    return (times[0], times[-1]) if times else None


def label_at(streams, t, window, span=None):
    """(정답 (v, w) 또는 None, 뺀 이유).

    창 안에서 가장 최근 명령을 쓴다(평균은 운전자가 막 바꾼 명령을 늦게 따라가서).
    후진은 0으로 자른다. 중재기가 후진을 0으로 바꿔 실제로 나간 적이 없고(설계 2-3) 모델도 못 낸다.
    span은 teleop_span(바퀴 전체). 수동 모드 데드맨 뗌이 그 안이면 (0, 0)이다(위 모듈 설명).
    """
    mode = streams.drive_modes.latest(t)
    if mode is None:
        return None, 'no_drive_mode'
    source, drive_mode = mode[1][0], mode[1][1]
    reason = mode[1][2] if len(mode[1]) > 2 else ''
    if source == SOURCE_NAV:
        return None, 'nav'
    if (drive_mode == metrics.MODE_MANUAL and reason == arbiter_logic.REASON_NO_DEADMAN):
        if span is None or t < span[0]:
            return None, 'released_before_first_press'
        if t > span[1]:
            return None, 'released_after_last_press'
        return (0.0, 0.0), None
    if source != SOURCE_TELEOP:
        return None, 'not_teleop'
    command = streams.teleop.latest(t)
    if command is None or t - command[0] > window:
        return None, 'no_command'
    v, w = command[1]
    return (max(v, 0.0), w), None


def in_intervals(t, intervals):
    return any(start <= t <= end for start, end in intervals)


def person_distances(streams):
    """기록기(run_recorder.on_predictions)와 같은 계산: odom 위치와 가장 가까운 사람 거리."""
    result = []
    for t, people in zip(streams.predictions.times, streams.predictions.values):
        odom = streams.odom.latest(t)
        if odom is None:
            continue
        x, y = odom[1][0], odom[1][1]
        result.append((t, min((math.hypot(p[0] - x, p[1] - y) for p in people),
                              default=math.inf)))
    return result


def scan_mount_of(streams, base_frame):
    """Bag 스캔 프레임의 장착 자세(base 기준 x, y, yaw). 스캔이 없거나 못 이으면 None."""
    if not streams.scans.values:
        return None
    return frame_builder.scan_mount(streams.tf_static, base_frame, streams.scans.values[0][5])


def run_log_from_streams(streams, settings, mount):
    """기록(bag) 값 → metrics.RunLog. 학습에서 뺄 구간을 기록기와 같은 함수(metrics)로 다시 계산한다.

    metrics.csv에는 지표 한 줄만 있고 구간은 없어서다. mount가 None이면 라이다 충돌은 셀 수 없다(빈 목록).
    """
    scan_edge = [] if mount is None else [
        (t, metrics.scan_edge_distance(s, mount, settings))
        for t, s in zip(streams.scans.times, streams.scans.values)]
    return metrics.RunLog(
        start_time=streams.start_time, end_time=streams.end_time,
        patrol_states=[(t, s[0]) for t, s in zip(streams.patrol.times, streams.patrol.values)],
        monitor_states=streams.monitor_states.tuples(), scan_edge=scan_edge,
        person_dist=person_distances(streams), odom=streams.odom.tuples(),
        cmd=streams.cmd.tuples(), cmd_out=streams.cmd_out.tuples(),
        drive_modes=streams.drive_modes.tuples())


def derive_waypoints(streams, route, cfg):
    """/patrol/state 없는 바퀴: 스캔 시각마다 map 위치로 경유점 번호를 계산해 derived_waypoint에 넣는다."""
    poses = []
    for t in streams.scans.times:
        found = robot_poses(streams, t, cfg)
        poses.append(found[0] if found else None)
    indices = waypoint_progress.progress(poses, route, cfg['pass_radius'], cfg['stop_tolerance'])
    streams.derived_waypoint = Series([(t, i) for t, i in zip(streams.scans.times, indices)
                                       if i is not None])


def lap_samples(streams, waypoints, cfg, metric_settings, route=None, excluded=(),
                not_collision=()):
    """한 바퀴 → (X 목록, y 목록, weight 목록, stamp 목록, 뺀 이유 Counter, 제외 구간 수).

    route(load_route)를 주면 /patrol/state가 없는 바퀴에 경유점 번호를 계산해 넣는다.
    excluded = 사람이 정한 제외 구간, not_collision = 사람이 충돌이 아니라고 확인한 구간. [(시작, 끝)] bag 시각(초).
    """
    settings = frame_builder.settings_from_dict(
        {key: cfg[key] for key in frame_builder.FrameSettings.__annotations__})
    if route is not None and not streams.patrol.times:
        derive_waypoints(streams, route, cfg)
    mount = scan_mount_of(streams, cfg['base_frame'])
    log = run_log_from_streams(streams, metric_settings, mount)
    # 사람이 충돌이 아니라고 확인한 구간의 라이다 근접 표본은 "없음"(inf)으로 바꿔 충돌 제외에 안 들어가게
    log.scan_edge = [(t, math.inf if in_intervals(t, not_collision) else d)
                     for t, d in log.scan_edge]
    bad = metrics.bad_intervals(log, metric_settings)
    assist = metrics.mode_switch_intervals(streams.drive_modes.tuples(), SOURCE_TELEOP,
                                           (metrics.MODE_POLICY_ASSIST,), streams.end_time)
    span = teleop_span(streams.drive_modes)
    history, xs, ys, weights, stamps, dropped = [], [], [], [], [], Counter()
    for t, scan in zip(streams.scans.times, streams.scans.values):
        if mount is None:
            dropped['no_scan_tf'] += 1
            continue
        inputs = inputs_at(streams, t, waypoints, cfg)
        if isinstance(inputs, str):
            dropped[inputs] += 1
            continue
        frame = frame_builder.assemble_frame(scan[:3], inputs['pose_map'], inputs['pose_odom'],
                                             inputs['goal'], inputs['velocity'],
                                             inputs['people'], settings, mount)
        x = frame_builder.push_and_stack(history, frame)
        label, reason = label_at(streams, t, cfg['label_window'], span)
        if label is None or in_intervals(t, bad):
            dropped[reason or 'bad_interval'] += 1
            continue
        if in_intervals(t, excluded):
            dropped['excluded_by_list'] += 1
            continue
        xs.append(x)
        ys.append(label)
        weights.append(cfg['intervention_weight'] if in_intervals(t, assist) else 1.0)
        stamps.append(t)
    return xs, ys, weights, stamps, dropped, len(bad)


def split_laps(lap_ids, val_fraction, seed):
    """검증 바퀴 id 집합.

    표본 단위로 섞지 않는 이유: 0.1 s 이웃 표본은 거의 같은 장면이라, 섞으면 검증 표본의 쌍둥이가
    학습에 들어가 검증 손실이 실제보다 좋게 나온다. 처음 보는 바퀴에서 얼마나 하는지를 재야 한다.
    바퀴가 둘 이상이면 검증·학습에 적어도 하나씩 둔다.
    """
    laps = sorted(set(lap_ids))
    if len(laps) < 2:
        return set()
    n_val = min(max(1, round(len(laps) * val_fraction)), len(laps) - 1)
    rng = np.random.default_rng(seed)
    return {int(i) for i in rng.choice(laps, size=n_val, replace=False)}


def read_bag(bag_dir, topics=None):
    """기록(bag) 폴더 → BagStreams. 메시지 역직렬화에만 rclpy.serialization을 쓴다(노드는 만들지 않음)."""
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=bag_dir, storage_id=''),
                rosbag2_py.ConverterOptions('', ''))
    types = {meta.name: meta.type for meta in reader.get_all_topics_and_types()}
    handlers = {**TOPIC_HANDLERS, **(topics or {})}
    streams, first, last = BagStreams(), None, None
    while reader.has_next():
        topic, data, stamp_ns = reader.read_next()
        t = stamp_ns / NS_PER_SEC
        first, last = (t if first is None else first), t
        if topic in handlers:
            handlers[topic](streams, t, deserialize_message(data, get_message(types[topic])))
    streams.start_time, streams.end_time = first or 0.0, last or 0.0
    sort_streams(streams)
    return streams


def sort_streams(streams):
    for value in vars(streams).values():
        if isinstance(value, Series):
            value.sort()
    for series in streams.tf.values():
        series.sort()


def clean_frame(name):
    return name.lstrip('/')


def add_scan(streams, t, msg):
    streams.scans.add(t, (np.asarray(msg.ranges, dtype=float), msg.angle_min,
                          msg.angle_increment, msg.range_min, msg.range_max,
                          clean_frame(msg.header.frame_id)))


def add_odom(streams, t, msg):
    p, twist = msg.pose.pose.position, msg.twist.twist
    streams.odom.add(t, (p.x, p.y, twist.linear.x, twist.angular.z))


def transform_pose(transform):
    tr, q = transform.translation, transform.rotation
    return (tr.x, tr.y, frame_builder.yaw_from_quaternion(q.x, q.y, q.z, q.w))


def add_tf(streams, t, msg):
    for stamped in msg.transforms:
        key = (clean_frame(stamped.header.frame_id), clean_frame(stamped.child_frame_id))
        streams.tf.setdefault(key, Series()).add(t, transform_pose(stamped.transform))


def add_tf_static(streams, t, msg):
    for stamped in msg.transforms:
        key = (clean_frame(stamped.header.frame_id), clean_frame(stamped.child_frame_id))
        streams.tf_static[key] = transform_pose(stamped.transform)


def load_tf_static_file(folder, streams):
    """바퀴 폴더의 tf_static.json(기록 노드가 받은 /tf_static)을 streams.tf_static에 넣는다.

    미리 띄운 일시 정지 bag에는 /tf_static이 안 남는다(run_files.TF_STATIC_FILE 참고). 파일이 없으면 그대로.
    """
    path = os.path.join(folder, run_files.TF_STATIC_FILE)
    if not os.path.isfile(path):
        return
    with open(path, encoding='utf-8') as f:
        for t in json.load(f):
            key = (clean_frame(t['parent']), clean_frame(t['child']))
            yaw = frame_builder.yaw_from_quaternion(t['qx'], t['qy'], t['qz'], t['qw'])
            streams.tf_static[key] = (t['x'], t['y'], yaw)


def add_drive_mode(streams, t, msg):
    try:
        data = json.loads(msg.data)
        streams.drive_modes.add(t, (data['source'], data['mode'], data.get('reason', '')))
    except (ValueError, KeyError, TypeError):
        print(f'unreadable /drive_mode at {t:.2f}: {msg.data}', file=sys.stderr)


def add_people(streams, t, msg):
    streams.predictions.add(t, [(p.current_position.x, p.current_position.y,
                                 p.velocity.x, p.velocity.y) for p in msg.predictions])


TOPIC_HANDLERS = {
    '/scan': add_scan,
    '/odom': add_odom,
    '/tf': add_tf,
    '/tf_static': add_tf_static,
    '/patrol/state': lambda s, t, m: s.patrol.add(t, (m.state, m.waypoint_index)),
    '/person_detector/predictions': add_people,
    '/drive_mode': add_drive_mode,
    '/cmd_vel_teleop': lambda s, t, m: s.teleop.add(t, (m.linear.x, m.angular.z)),
    '/cmd_vel_arbiter': lambda s, t, m: s.cmd.add(t, (m.linear.x, m.angular.z)),
    '/cmd_vel': lambda s, t, m: s.cmd_out.add(t, (m.linear.x, m.angular.z)),
    '/collision_monitor_state': lambda s, t, m: s.monitor_states.add(t, m.action_type),
}


def resolve_waypoints(meta, override):
    """경유점 파일 경로. 기록한 보드의 경로가 이 PC에 없을 수 있어 override를 받는다.

    어느 쪽이든 meta.json의 sha256과 다르면 멈춘다. 다른 판의 경유점으로 목표를 계산하면
    정답(운전)과 입력(목표 방향)이 어긋난 표본이 조용히 섞인다.
    """
    path = override or meta.get('waypoints_file')
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(f'waypoints file not found: {path} (use --waypoints)')
    expected = meta.get('waypoints_sha256')
    if expected and run_files.file_sha256(path) != expected:
        raise ValueError(f'waypoints sha256 differs from meta.json: {path}')
    return path


def folder_hashes(folder):
    """폴더 안 파일들의 sha256(상대 경로 → 값). 어느 기록으로 만든 데이터셋인지 남긴다."""
    result = {}
    for root, _, names in os.walk(folder):
        for name in sorted(names):
            path = os.path.join(root, name)
            result[os.path.relpath(path, folder)] = run_files.file_sha256(path)
    return result


def read_meta(folder):
    with open(os.path.join(folder, run_files.META_FILE), encoding='utf-8') as f:
        return json.load(f)


def load_exclusions(path):
    """제외 목록 파일(yaml 목록) → {바퀴 폴더 이름: {'whole': bool, 'excluded': [...], 'not_collision': [...]}}.

    항목(사람·PM이 기록을 보고 정한 것이라 코드에 두지 않는다. reason 필수):
    - {lap, whole_lap: true, reason}: 바퀴 통째로 뺀다
    - {lap, start_s, end_s, reason}: 그 구간 표본을 뺀다
    - {lap, start_s, end_s, not_collision: true, reason}: 그 구간의 라이다 근접은 충돌이 아니다(사람이 확인).
      데이터셋 충돌 제외(앞뒤 collision_margin 포함)에서만 빼고, 지표(metrics)의 collisions는 그대로 센다
    start_s·end_s는 그 바퀴 bag의 첫 메시지부터 초. 파일이 없으면 빈 dict.
    """
    if not path or not os.path.isfile(path):
        return {}
    with open(path, encoding='utf-8') as f:
        entries = yaml.safe_load(f) or []
    result = {}
    for entry in entries:
        if not entry.get('reason'):
            raise ValueError(f'exclusion without reason: {entry}')
        lap = result.setdefault(entry['lap'], {'whole': False, 'excluded': [],
                                               'not_collision': []})
        if entry.get('whole_lap'):
            lap['whole'] = True
            continue
        span = (float(entry['start_s']), float(entry['end_s']), entry['reason'])
        lap['not_collision' if entry.get('not_collision') else 'excluded'].append(span)
    return result


def resolve_geometry(cfg, metric_settings):
    """비어 있는 발판·경유점 반경을 실물 Nav2 설정에서 채운다(값을 코드에 두지 않는다)."""
    cfg, metric_settings = dict(cfg), dict(metric_settings)
    if not metric_settings.get('footprint'):
        metric_settings['footprint'] = robot_geometry.footprint_text(cfg['nav2_params_file'])
    if cfg.get('pass_radius') is None or cfg.get('stop_tolerance') is None:
        cfg['pass_radius'], cfg['stop_tolerance'] = robot_geometry.patrol_radii(
            cfg['nav2_params_file'], cfg['patrol_bt_file'])
    return cfg, metric_settings


def build_laps(folders, cfg, metric_settings, waypoints_override=None, reader=read_bag,
               exclusions=None):
    """폴더마다 표본을 모은다. 결과: 바퀴별 dict 목록(id 순). 제외 목록의 통째 제외 바퀴는 건너뛴다."""
    cfg, metric_settings = resolve_geometry(cfg, metric_settings)
    exclusions = exclusions or {}
    laps = []
    for folder in folders:
        name = os.path.basename(os.path.normpath(folder))
        listed = exclusions.get(name, {'whole': False, 'excluded': [], 'not_collision': []})
        if listed['whole']:
            print(f'skip {name}: excluded by list', file=sys.stderr)
            continue
        lap_id = len(laps)
        meta = read_meta(folder)
        waypoints_file = resolve_waypoints(meta, waypoints_override)
        waypoints = frame_builder.load_waypoints(waypoints_file)
        route = frame_builder.load_route(waypoints_file)
        streams = reader(os.path.join(folder, run_files.BAG_DIR))
        if not streams.tf_static:
            load_tf_static_file(folder, streams)

        def absolute(spans):
            return [(streams.start_time + a, streams.start_time + b) for a, b, _ in spans]
        xs, ys, weights, stamps, dropped, n_bad = lap_samples(
            streams, waypoints, cfg, metric_settings, route, absolute(listed['excluded']),
            absolute(listed['not_collision']))
        laps.append({'id': lap_id, 'folder': os.path.abspath(folder), 'x': xs, 'y': ys,
                     'weight': weights, 'stamp': stamps, 'dropped': dropped, 'n_bad': n_bad,
                     'passed': [row.get('passed') for row in run_files.read_metrics_csv(folder)],
                     'sha256': folder_hashes(folder)})
    return laps


def stack_laps(laps, val_ids):
    """바퀴별 목록 → npz 배열들."""
    used = [lap for lap in laps if lap['x']]
    if not used:
        raise ValueError('no samples in any lap')
    n_rows = [len(lap['x']) for lap in used]
    return {
        'X': np.asarray([x for lap in used for x in lap['x']], dtype=np.float32),
        'y': np.asarray([y for lap in used for y in lap['y']], dtype=np.float32),
        'weight': np.asarray([w for lap in used for w in lap['weight']], dtype=np.float32),
        'lap_id': np.repeat([lap['id'] for lap in used], n_rows).astype(np.int32),
        'stamp': np.asarray([t for lap in used for t in lap['stamp']], dtype=np.float64),
        'is_val': np.repeat([lap['id'] in val_ids for lap in used], n_rows),
    }


def dataset_info(laps, cfg, metric_settings):
    """npz에 json 문자열로 함께 넣는 설명. train.py가 모델 파일로 옮겨 정책 노드까지 간다."""
    frame_keys = frame_builder.FrameSettings.__annotations__
    return {
        'feature_layout': features.__doc__,
        'feature_size': features.FEATURE_SIZE,
        'frame_settings': {key: cfg[key] for key in frame_keys},
        'params': cfg,
        'metric_settings': metric_settings,
        'folders': [lap['folder'] for lap in laps],
        'sha256': {lap['folder']: lap['sha256'] for lap in laps},
    }


def build_dataset(folders, out_path, cfg, metric_settings, waypoints_override=None,
                  reader=read_bag, exclusions=None):
    """폴더들 → out_path(.npz). 바퀴별 요약 목록을 낸다(표 출력용)."""
    cfg, metric_settings = resolve_geometry(cfg, metric_settings)
    laps = build_laps(folders, cfg, metric_settings, waypoints_override, reader, exclusions)
    val_ids = split_laps([lap['id'] for lap in laps if lap['x']], cfg['val_fraction'],
                         cfg['seed'])
    arrays = stack_laps(laps, val_ids)
    info = dataset_info(laps, cfg, metric_settings)
    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    np.savez_compressed(out_path, info=np.array(json.dumps(info, ensure_ascii=False)), **arrays)
    for lap in laps:
        lap['val'] = lap['id'] in val_ids
    return laps


def print_summary(laps, out_path, file=sys.stdout):
    print(f"{'lap':>3}  {'samples':>7}  {'bad':>3}  {'split':<5}  {'passed':<6}  dropped  folder",
          file=file)
    for lap in laps:
        dropped = ','.join(f'{k}={v}' for k, v in sorted(lap['dropped'].items())) or '-'
        split = 'val' if lap.get('val') else ('train' if lap['x'] else '-')
        passed = lap['passed'][0] if lap['passed'] else '-'
        print(f"{lap['id']:>3}  {len(lap['x']):>7}  {lap['n_bad']:>3}  {split:<5}  "
              f'{passed:<6}  {dropped}  {os.path.basename(lap["folder"])}', file=file)
    n_val = sum(1 for lap in laps if lap.get('val'))
    n_train = sum(1 for lap in laps if lap['x'] and not lap.get('val'))
    print(f"total samples {sum(len(lap['x']) for lap in laps)}, laps {len(laps)}, "
          f"excluded intervals {sum(lap['n_bad'] for lap in laps)}, "
          f'train laps {n_train}, val laps {n_val} -> {out_path}', file=file)


def parse_args(argv):
    parser = argparse.ArgumentParser(description='바퀴 기록 폴더들 → 학습용 npz')
    parser.add_argument('folders', nargs='+', help='~/limbo_bags/imitation/<시각>_<번호>_<모드>')
    parser.add_argument('-o', '--output', required=True, help='출력 .npz 경로')
    parser.add_argument('--config', default=config_file.default_config_path(),
                        help='imitation.yaml(build_dataset 절과 run_recorder 지표 기준)')
    parser.add_argument('--waypoints', help='meta.json의 경유점 경로가 이 PC에 없을 때')
    parser.add_argument('--exclusions', help='제외 목록 yaml. 없으면 첫 폴더 옆의 exclusions.yaml(있을 때)')
    parser.add_argument('--label-window', type=float, dest='label_window')
    parser.add_argument('--intervention-weight', type=float, dest='intervention_weight')
    parser.add_argument('--val-fraction', type=float, dest='val_fraction')
    parser.add_argument('--seed', type=int)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    overrides = {key: getattr(args, key)
                 for key in ('label_window', 'intervention_weight', 'val_fraction', 'seed')}
    cfg = config_file.merged(DEFAULTS, args.config, SECTION, overrides)
    metric_settings = config_file.merged(metrics.DEFAULT_SETTINGS, args.config,
                                         'run_recorder', {})
    if len(args.folders) < 2:
        print('warning: one lap only, no validation lap', file=sys.stderr)
    exclusions_file = args.exclusions or os.path.join(
        os.path.dirname(os.path.abspath(os.path.normpath(args.folders[0]))), EXCLUSIONS_FILE)
    exclusions = load_exclusions(exclusions_file)
    if exclusions:
        print(f'exclusions: {exclusions_file} ({len(exclusions)} laps)', file=sys.stderr)
    laps = build_dataset(args.folders, args.output, cfg, metric_settings, args.waypoints,
                         exclusions=exclusions)
    print_summary(laps, args.output)
    return 0


if __name__ == '__main__':
    sys.exit(main())
