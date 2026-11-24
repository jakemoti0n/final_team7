"""
콘솔 스크립트(build_dataset·train_policy)가 imitation.yaml에서 기본값을 읽는다. rclpy를 쓰지 않는다.

노드가 아닌 스크립트도 같은 yaml을 보게 해 값이 두 곳에 갈라지지 않게 한다.
우선순위: 명령줄 > yaml(노드 이름 절의 ros__parameters) > 코드 기본값.
"""

import os

import yaml

PACKAGE = 'limbo_imitation'
CONFIG_NAME = 'imitation.yaml'


def default_config_path():
    """설치된 패키지의 imitation.yaml. 설치 전(소스에서 바로 실행)이면 None."""
    try:
        from ament_index_python.packages import get_package_share_directory
        return os.path.join(get_package_share_directory(PACKAGE), 'config', CONFIG_NAME)
    except (ImportError, LookupError):
        return None


def read_section(path, name):
    """yaml의 <name>.ros__parameters. 파일이나 절이 없으면 빈 dict."""
    if not path or not os.path.isfile(path):
        return {}
    with open(path, encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
    return (data.get(name) or {}).get('ros__parameters') or {}


def merged(defaults, path, name, overrides):
    """코드 기본값의 키만 쓴다. yaml에 오타 난 키가 조용히 새 설정이 되지 않게."""
    section = read_section(path, name)
    result = dict(defaults)
    result.update({key: value for key, value in section.items() if key in defaults})
    result.update({key: value for key, value in overrides.items() if value is not None})
    return result
