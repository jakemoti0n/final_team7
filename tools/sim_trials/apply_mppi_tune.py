"""MPPI(FollowPath) 설정 몇 개를 바꾼다 (실험용, lab). 사용법: apply_mppi_tune.py 키=값 ...
키는 FollowPath 아래 경로: vx_std, CostCritic.cost_weight, PathFollowCritic.cost_weight 등
되돌리기: cd ~/limbo && git checkout limbo/src/limbo_navigation/config/nav2_params.yaml"""
import os, sys
p = os.path.expanduser('~/limbo/limbo/src/limbo_navigation/config/nav2_params.yaml')
lines = open(p).read().split('\n')
start = lines.index('    FollowPath:')
end = next(i for i in range(start + 1, len(lines)) if lines[i] and len(lines[i]) - len(lines[i].lstrip()) <= 4)
for arg in sys.argv[1:]:
    key, value = arg.split('=')
    parts = key.split('.')
    lo, hi, indent = start, end, 6
    for part in parts[:-1]:   # critic 블록 안으로 범위를 좁힌다
        lo = next(i for i in range(lo, hi) if lines[i] == ' ' * indent + part + ':')
        hi = next((i for i in range(lo + 1, hi) if lines[i].strip() and len(lines[i]) - len(lines[i].lstrip()) <= indent), hi)
        indent += 2
    i = next(i for i in range(lo, hi) if lines[i].startswith(' ' * indent + parts[-1] + ':'))
    print(f'{key}: {lines[i].split(":", 1)[1].strip()} → {value}')
    lines[i] = ' ' * indent + parts[-1] + ': ' + value
open(p, 'w').write('\n'.join(lines))
