"""Nav2 파라미터 yaml 조합 유틸.

config/ 아래 축별 yaml(common, costmap, planner, controller, robot)을 골라
하나의 dict로 깊은 병합한다. 뒤 파일이 앞 파일을 덮어쓴다.
- dict 는 재귀 병합
- 리스트/스칼라는 통째로 교체 (plugins: [...] 같은 목록은 병합되지 않음)

launch 파일과 검증 스크립트가 같은 함수를 쓴다.
"""
import copy
import os
import tempfile

import yaml


def deep_merge(base, overlay):
    """overlay 를 base 위에 겹친 새 dict 를 돌려준다 (원본 불변)."""
    if not isinstance(base, dict) or not isinstance(overlay, dict):
        return copy.deepcopy(overlay)
    out = copy.deepcopy(base)
    for k, v in overlay.items():
        out[k] = deep_merge(out[k], v) if k in out else copy.deepcopy(v)
    return out


def load_yaml(path):
    with open(path) as f:
        data = yaml.safe_load(f)
    return data if data is not None else {}


def resolve_files(config_dir, planner, controller, use_perception, robot='sim'):
    """launch 인자 조합에 해당하는 yaml 경로 목록을 로드 순서대로 돌려준다."""
    c = config_dir
    files = sorted(
        os.path.join(c, 'common', f)
        for f in os.listdir(os.path.join(c, 'common'))
        if f.endswith('.yaml') and f != 'self_filter.yaml'   # self_filter 는 Nav2 노드가 아님
    )
    files += [
        os.path.join(c, 'costmap', 'base.yaml'),
        os.path.join(c, 'planner', f'{planner}.yaml'),
        os.path.join(c, 'controller', f'{controller}.yaml'),
    ]
    if use_perception:
        files.append(os.path.join(c, 'costmap', 'with_human.yaml'))
        overlay = os.path.join(c, 'controller', 'overlays', f'{controller}_human.yaml')
        if os.path.exists(overlay):
            files.append(overlay)
    files.append(os.path.join(c, 'robot', f'{robot}.yaml'))
    missing = [f for f in files if not os.path.exists(f)]
    if missing:
        raise FileNotFoundError('파라미터 파일 없음: ' + ', '.join(missing))
    return files


def merge_files(paths):
    merged = {}
    for p in paths:
        merged = deep_merge(merged, load_yaml(p))
    return merged


def write_merged(paths, out_path=None):
    """병합 결과를 yaml 파일로 쓰고 경로를 돌려준다. out_path 없으면 임시 파일."""
    merged = merge_files(paths)
    if out_path is None:
        fd, out_path = tempfile.mkstemp(prefix='limbo_nav2_params_', suffix='.yaml')
        os.close(fd)
    with open(out_path, 'w') as f:
        f.write('# 자동 생성됨 (limbo_navigation/param_merge.py). 직접 수정하지 말 것.\n')
        f.write('# 원본: ' + ', '.join(os.path.relpath(p, os.path.dirname(out_path)) for p in paths) + '\n')
        yaml.safe_dump(merged, f, allow_unicode=True, sort_keys=False)
    return out_path
