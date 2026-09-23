#!/usr/bin/env python3
"""조합별 Nav2 파라미터를 출력하거나 두 조합/파일을 비교한다.

  # 병합 결과 출력 (실험 스냅샷용)
  ros2 run limbo_navigation nav2_params_tool.py show --controller rpp --planner smac_hybrid > experiments/.../params.yaml

  # 두 조합 비교 (무엇이 달라지는지 확인)
  ros2 run limbo_navigation nav2_params_tool.py diff --controller mppi  --vs-controller mppi --vs-use-perception

  # 조합 vs 임의 yaml 파일 비교 (예: ros2 param dump 결과, 옛 nav2_params.yaml)
  ros2 run limbo_navigation nav2_params_tool.py diff --controller mppi --use-perception --file old_nav2_params.yaml
"""
import argparse
import os
import sys

import yaml
from ament_index_python.packages import get_package_share_directory

from limbo_navigation.param_merge import merge_files, resolve_files


def flat(d, pre=''):
    out = {}
    for k, v in d.items():
        key = f'{pre}/{k}'
        if isinstance(v, dict):
            out.update(flat(v, key))
        else:
            out[key] = v
    return out


def combo(cfg, ns, prefix=''):
    g = lambda n: getattr(ns, prefix + n)
    return merge_files(resolve_files(cfg, g('planner'), g('controller'), g('use_perception'), g('robot')))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=['show', 'diff'])
    for p in ('', 'vs_'):
        ap.add_argument(f'--{p.replace("_", "-")}planner', default='navfn')
        ap.add_argument(f'--{p.replace("_", "-")}controller', default='mppi')
        ap.add_argument(f'--{p.replace("_", "-")}robot', default='sim')
        ap.add_argument(f'--{p.replace("_", "-")}use-perception', action='store_true')
    ap.add_argument('--file', help='diff 대상 yaml 파일 (있으면 --vs-* 대신 이 파일과 비교)')
    ap.add_argument('--config-dir', help='기본: 설치된 limbo_navigation/share/config')
    ns = ap.parse_args()
    if ns.config_dir is None:
        ns.config_dir = os.path.join(get_package_share_directory('limbo_navigation'), 'config')

    a = combo(ns.config_dir, ns)
    if ns.cmd == 'show':
        yaml.safe_dump(a, sys.stdout, allow_unicode=True, sort_keys=False)
        return 0

    if ns.file:
        b = yaml.safe_load(open(ns.file)) or {}
        label_b = ns.file
    else:
        b = combo(ns.config_dir, ns, 'vs_')
        label_b = f'planner={ns.vs_planner} controller={ns.vs_controller} perception={ns.vs_use_perception} robot={ns.vs_robot}'
    fa, fb = flat(a), flat(b)
    diffs = [(k, fa.get(k, '<없음>'), fb.get(k, '<없음>')) for k in sorted(set(fa) | set(fb)) if fa.get(k, '<없음>') != fb.get(k, '<없음>')]
    print(f'A: planner={ns.planner} controller={ns.controller} perception={ns.use_perception} robot={ns.robot}  ({len(fa)} 키)')
    print(f'B: {label_b}  ({len(fb)} 키)')
    print(f'차이 {len(diffs)}개')
    for k, va, vb in diffs:
        print(f'  {k}\n      A={va}\n      B={vb}')
    return 1 if diffs else 0


if __name__ == '__main__':
    sys.exit(main())
