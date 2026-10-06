from urllib.parse import urlsplit
import math
import yaml
from .state import TOPICS


def load_config(path):
    with open(path, encoding='utf-8') as stream:
        config = yaml.safe_load(stream)
    expected = {'robot_id', 'server_url', 'send_interval_s', 'request_timeout_s', 'source_clock', 'topics'}
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
    return config
