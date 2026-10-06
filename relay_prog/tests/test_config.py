from pathlib import Path
import pytest
import yaml
from limbo_telemetry_bridge.config import load_config

DEFAULT = Path(__file__).resolve().parents[1]/'src/limbo_telemetry_bridge/config/bridge.yaml'


def test_default_config():
    config = load_config(DEFAULT)
    assert config['request_timeout_s'] == 1
    assert len(config['topics']) == 4


@pytest.mark.parametrize('key,value', [
    ('request_timeout_s', 2), ('request_timeout_s', 0), ('request_timeout_s', True),
    ('send_interval_s', float('nan')), ('send_interval_s', -1),
    ('source_clock', 'utc'), ('server_url', 'ftp://localhost'),
    ('server_url', 'http://localhost/api'), ('server_url', 'http://user:pass@localhost'),
    ('robot_id', ''), ('robot_id', 'x'*257), ('topics', {}),
])
def test_invalid_configuration(tmp_path, key, value):
    config = yaml.safe_load(DEFAULT.read_text())
    config[key] = value
    path = tmp_path/'bad.yaml'
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError):
        load_config(path)
