"""rec.py 녹화에서 겹침 비율과 위치 오차를 거리(1.5 m 안/밖)·방향(카메라 앞뒤/옆)으로 나눔. 사용법: err.py <json> ...
앞뒤 오차가 음수면 예측이 정답(사람 중심)보다 카메라 쪽에 있다는 뜻."""
import json, math, bisect, statistics as st, sys
for p in sys.argv[1:]:
    D = json.load(open(p)); gt = sorted(D['gt']); gts = [g[0] for g in gt]; K = len(gt[0][1])
    det = dup = 0; E = {'n': [], 'f': []}; rad = {'n': [], 'f': []}; lat = {'n': [], 'f': []}
    for f in D['frames']:
        i = min(bisect.bisect_left(gts, f['t']), len(gt) - 1); P = gt[i][1]; cx, cy, _ = f['cam']
        per = {k: [] for k in range(K)}
        for pid, x, y in f['p']:
            k = min(range(K), key=lambda k: math.dist((x, y), P[k]))
            if math.dist((x, y), P[k]) < 1.0: per[k].append((x, y))
        for k in range(K):
            if not per[k]: continue
            det += 1; dup += len(per[k]) > 1
            x, y = min(per[k], key=lambda q: math.dist(q, P[k])); d = math.dist((cx, cy), P[k]); b = 'n' if d < 1.5 else 'f'
            ux, uy = (P[k][0] - cx) / d, (P[k][1] - cy) / d; ex, ey = x - P[k][0], y - P[k][1]
            E[b].append(math.hypot(ex, ey)); rad[b].append(ex * ux + ey * uy); lat[b].append(abs(-ex * uy + ey * ux))
    m = lambda v: f"{st.median(v):.2f}" if v else '-'
    print(p.split('/')[-1][:-5], f"겹침 {100*dup/det:.0f}% | 1.5m안 오차 {m(E['n'])} (앞뒤 {m(rad['n'])}, 옆 {m(lat['n'])}, n={len(E['n'])}) | 밖 {m(E['f'])} (앞뒤 {m(rad['f'])}, 옆 {m(lat['f'])})")
