"""drive_test 구간별로 정답과 odom의 이동량·회전량을 비교한다. 사용법: drive_compare.py 태그..."""
import sys, csv, math, re
def wrap(a): return (a + math.pi) % (2*math.pi) - math.pi
def analyze(tag):
    S = sys.argv[0].rsplit('/', 1)[0]
    rows = [{k: float(v) for k, v in r.items()} for r in csv.DictReader(open(f'{S}/drive_{tag}.csv'))]
    ph = [(m.group(1), float(m.group(2))) for m in re.finditer(r'(\S+) 시작 t=([\d.]+)', open(f'{S}/drive_{tag}.phases').read())]
    ph.append(('끝', rows[-1]['t'] + 1))
    out = {}
    for (name, t0), (_, t1) in zip(ph, ph[1:]):
        if name == '정지': continue
        seg = [r for r in rows if t0 <= r['t'] < t1]
        if len(seg) < 2: continue
        a, b = seg[0], seg[-1]
        gd = math.hypot(b['gt_x']-a['gt_x'], b['gt_y']-a['gt_y']); od = math.hypot(b['od_x']-a['od_x'], b['od_y']-a['od_y'])
        gr = sum(wrap(q['gt_yaw']-p['gt_yaw']) for p, q in zip(seg, seg[1:])); orr = sum(wrap(q['od_yaw']-p['od_yaw']) for p, q in zip(seg, seg[1:]))
        key = name
        out[key] = (gd, od, math.degrees(gr), math.degrees(orr))
    return out
res = {t: analyze(t) for t in sys.argv[1:]}
print(f"{'구간':6s} {'항목':22s}" + ''.join(f"{t:>12s}" for t in sys.argv[1:]))
for key in ['직진', '회전+', '후진', '회전-']:
    for i, label in enumerate(['정답 이동 (m)', 'odom 이동 (m)', '정답 회전 (deg)', 'odom 회전 (deg)']):
        print(f"{key:6s} {label:22s}" + ''.join(f"{res[t][key][i]:12.3f}" for t in sys.argv[1:]))
    gd, od = [res[t][key][0] for t in sys.argv[1:]], [res[t][key][1] for t in sys.argv[1:]]
    gr, orr = [res[t][key][2] for t in sys.argv[1:]], [res[t][key][3] for t in sys.argv[1:]]
    print(f"{key:6s} {'→ 이동 오차 (mm)':22s}" + ''.join(f"{(o-g)*1000:12.1f}" for g, o in zip(gd, od)))
    print(f"{key:6s} {'→ 회전 오차 (deg)':22s}" + ''.join(f"{o-g:12.2f}" for g, o in zip(gr, orr)))
