"""로컬·전역 costmap의 로봇 외곽(footprint)과 여유(footprint_padding)를 바꾼다 (실험용, lab).
사용법: apply_footprint.py <앞뒤 반> <좌우 반> <여유>   예) apply_footprint.py 0.25 0.295 0.0
되돌리기: cd ~/limbo && git checkout limbo/src/limbo_navigation/config/nav2_params.yaml"""
import os
import re
import sys

p = os.path.expanduser('~/limbo/limbo/src/limbo_navigation/config/nav2_params.yaml')
half_x, half_y, padding = (float(v) for v in sys.argv[1:4])
s = open(p).read()
fp = f'"[[{half_x}, {half_y}], [{half_x}, -{half_y}], [-{half_x}, -{half_y}], [-{half_x}, {half_y}]]"'
s, n = re.subn(r'(\n      footprint: )"[^"]*"', r'\g<1>' + fp, s)
s, m = re.subn(r'(\n      footprint_padding: )[\d.]+', r'\g<1>' + str(padding), s)
if n != 2 or m != 2:
    raise SystemExit(f'footprint {n}곳, padding {m}곳을 찾음 (각 2곳이어야 함)')
open(p, 'w').write(s)
print(f'footprint {fp}, padding {padding} (로컬·전역)')
