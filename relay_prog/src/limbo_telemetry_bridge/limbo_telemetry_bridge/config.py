from pathlib import Path
from urllib.parse import urlsplit
import math
import os
import tempfile
import yaml
from .state import TOPICS


def load_config(path):
    with open(path, encoding='utf-8') as stream:
        config = yaml.safe_load(stream)
    expected = {'robot_id', 'server_url', 'send_interval_s', 'request_timeout_s', 'source_clock', 'topics',
                'control', 'patrol_launch', 'token_file'}
    if not isinstance(config, dict) or set(config) != expected:
        raise ValueError('configuration fields must be: ' + ', '.join(sorted(expected)))
    if not isinstance(config['robot_id'], str) or not 1 <= len(config['robot_id'].encode()) <= 256:
        raise ValueError('robot_id must be a nonempty string, at most 256 UTF-8 bytes')
    url = urlsplit(config['server_url'])
    if (url.scheme not in ('http', 'https') or not url.hostname or url.username or
            url.password or url.query or url.fragment or url.path not in ('', '/')):
        raise ValueError('server_url must be an HTTP(S) origin without credentials or path')
    _ = url.port  # Reject malformed ports at startup.
    for key in ('send_interval_s', 'request_timeout_s'):
        value = config[key]
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(key + ' must be a positive finite number')
    if config['request_timeout_s'] > 1:
        raise ValueError('v1 request_timeout_s must not exceed 1 second')
    if config['source_clock'] not in ('ros_sim', 'ros_system'):
        raise ValueError('source_clock must be ros_sim or ros_system')
    if not isinstance(config['topics'], dict) or set(config['topics']) != set(TOPICS):
        raise ValueError('all four topic keys are required')
    for topic in config['topics'].values():
        if not isinstance(topic, dict) or set(topic) != {'name', 'reliability', 'durability', 'depth'}:
            raise ValueError('invalid topic configuration fields')
        if not isinstance(topic['name'], str) or not topic['name'].startswith('/'):
            raise ValueError('topic name must be absolute')
        if topic['reliability'] not in ('best_effort', 'reliable'):
            raise ValueError('invalid reliability')
        if topic['durability'] not in ('volatile', 'transient_local'):
            raise ValueError('invalid durability')
        if type(topic['depth']) is not int or not 1 <= topic['depth'] <= 100:
            raise ValueError('depth must be an integer in 1..100')
    control = config['control']
    names = ('patrol_state_topic', 'pose_topic', 'pause_service', 'resume_service')
    frames = ('map_frame', 'base_frame')
    if not isinstance(control, dict) or set(control) != {*names, *frames, 'command_wait_s', 'service_timeout_s'}:
        raise ValueError('invalid control configuration fields')
    for key in names:
        if not isinstance(control[key], str) or not control[key].startswith('/'):
            raise ValueError(key + ' must be an absolute ROS name')
    for key in frames:
        if not isinstance(control[key], str) or not control[key] or control[key].startswith('/'):
            raise ValueError(key + ' must be a TF frame name without a leading slash')
    for key, upper in (('command_wait_s', 30), ('service_timeout_s', 10)):
        value = control[key]
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= upper:
            raise ValueError(f'{key} must be a finite number in (0, {upper}]')
    launch = config['patrol_launch']
    keys = ('ros_setup', 'workspace', 'waypoint_dir', 'use_sim_time')
    if not isinstance(launch, dict) or set(launch) != set(keys):
        raise ValueError('patrol_launch fields must be: ' + ', '.join(keys))
    for key in keys[:3]:
        if not isinstance(launch[key], str) or not launch[key].strip():
            raise ValueError(f'patrol_launch.{key} must be a nonempty path')
    if type(launch['use_sim_time']) is not bool:
        raise ValueError('patrol_launch.use_sim_time must be true or false')
    if config['token_file'] is not None and (not isinstance(config['token_file'], str) or not config['token_file'].strip()):
        raise ValueError('token_file must be a path or null')
    return config


MIN_TOKEN_LENGTH = 16


def resolve_token(config, environ=os.environ, base=None):
    """서버 로봇용 경로의 공유 토큰. 환경 변수 LIMBO_ROBOT_TOKEN → token_file 순서. 없으면 None(헤더 안 보냄).

    파일은 git에 올리지 않는다. 상대 경로는 Bridge 실행 디렉터리 기준. 문제가 있으면 시작할 때 알린다."""
    token = environ.get('LIMBO_ROBOT_TOKEN', '').strip()
    if not token and config['token_file']:
        path = Path(base or os.getcwd()) / Path(config['token_file']).expanduser()
        try:
            token = path.read_text(encoding='utf-8').strip()
        except OSError as exc:
            raise ValueError(f'token_file cannot be read: {path} ({exc})') from exc
        if not token:
            raise ValueError(f'token_file is empty: {path}')
    if token and (len(token) < MIN_TOKEN_LENGTH or any(c.isspace() for c in token)):
        raise ValueError(f'robot token must be at least {MIN_TOKEN_LENGTH} characters without spaces')
    return token or None


def resolve_patrol_launch(config, base=None):
    """patrol_launch 경로를 절대 경로로 바꾸고 실제로 쓸 수 있는지 시작할 때 확인한다.

    상대 경로는 Bridge를 실행한 디렉터리(README·런치 기준 저장소 루트) 기준. 문제가 있으면
    어떤 설정의 어떤 경로가 왜 안 되는지 ValueError로 알린다 (명령을 받은 뒤에야 알게 되지 않게)."""
    base = Path(base or os.getcwd())
    launch = config['patrol_launch']
    paths = {key: (base / Path(launch[key]).expanduser()).resolve() for key in ('ros_setup', 'workspace', 'waypoint_dir')}
    hint = f' (relative paths are resolved from {base}; run the Bridge from the repository root or use an absolute path)'
    if not paths['ros_setup'].is_file():
        raise ValueError(f"patrol_launch.ros_setup not found: {paths['ros_setup']}" + hint)
    for name in ('install/setup.bash', 'install/limbo_patrol/lib/limbo_patrol/patrol_node'):
        if not (paths['workspace'] / name).is_file():
            raise ValueError(f"patrol_launch.workspace has no {name}: {paths['workspace']} — build limbo/ first" + hint)
    try:
        paths['waypoint_dir'].mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=paths['waypoint_dir']):
            pass
    except OSError as exc:
        raise ValueError(f"patrol_launch.waypoint_dir is not writable: {paths['waypoint_dir']} ({exc})") from exc
    return {**{k: str(v) for k, v in paths.items()}, 'use_sim_time': launch['use_sim_time']}
