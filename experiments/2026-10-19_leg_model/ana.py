"""rec.py 녹화 분석. 사용법: ana.py <json> ..."""
import json, math, bisect, statistics as st, sys
MATCH, HFOV = 1.0, math.radians(36)
def ana(path):
    D = json.load(open(path)); names = D['names'].split(','); gt = sorted(D['gt']); gts = [g[0] for g in gt]; fr = sorted(D['frames'], key=lambda f: f['t'])
    def gt_at(t):
        i = min(max(bisect.bisect_left(gts, t), 0), len(gt) - 1); return gt[i][1]
    def speed(t, k):
        a, b = gt_at(t - 0.25)[k], gt_at(t + 0.25)[k]; return math.dist(a, b) / 0.5
    K = len(gt[0][1]); bins = {'0-1.5': [0, 0], '1.5-3': [0, 0], '3-5': [0, 0]}
    errs, dup, false, ids = [], 0, 0, {k: [] for k in range(K)}
    stopv = {k: [] for k in range(K)}  # (t, detected) 멈춘·보이는·3m 안 프레임
    for f in fr:
        P = gt_at(f['t']); cx, cy, cyaw = f['cam']; per = {k: [] for k in range(K)}
        for pid, x, y in f['p']:
            k = min(range(K), key=lambda k: math.dist((x, y), P[k])); e = math.dist((x, y), P[k])
            if e < MATCH: per[k].append((e, pid))
            else: false += 1
        for k in range(K):
            d = math.dist((cx, cy), P[k]); b = abs((math.atan2(P[k][1] - cy, P[k][0] - cx) - cyaw + math.pi) % (2 * math.pi) - math.pi)
            det = bool(per[k])
            if per[k]:
                per[k].sort(); errs.append(per[k][0][0]); ids[k].append(per[k][0][1]); dup += len(per[k]) > 1
            if b > HFOV or d > 5: continue
            key = '0-1.5' if d < 1.5 else '1.5-3' if d < 3 else '3-5'
            bins[key][0] += det; bins[key][1] += 1
            if d < 3 and speed(f['t'], k) < 0.05: stopv[k].append((f['t'], det))
    sw = sum(sum(a != b for a, b in zip(v, v[1:])) for v in ids.values()); nid = sum(len(set(v)) for v in ids.values())
    # 멈춘 사람 끊김: 연속(0.3 s 안) 멈춤 프레임 묶음별로 검출 사이 가장 긴 공백
    gaps, srate = [], [0, 0]
    for v in stopv.values():
        segs, cur = [], []
        for t, d in v:
            if cur and t - cur[-1][0] > 0.3: segs.append(cur); cur = []
            cur.append((t, d))
        if cur: segs.append(cur)
        for s in segs:
            if s[-1][0] - s[0][0] < 1.0: continue
            dt = [t for t, d in s if d]; srate[0] += len(dt); srate[1] += len(s)
            edges = [s[0][0]] + dt + [s[-1][0]]; gaps.append(max(b - a for a, b in zip(edges, edges[1:])))
    wall = fr[-1]['wall'] - fr[0]['wall']; sim = fr[-1]['t'] - fr[0]['t']
    r = lambda b: f"{100*b[0]/b[1]:.0f}% ({b[1]})" if b[1] else '-'
    return (f"{path.split('/')[-1][:-5]:22s} fps {len(fr)/wall:.1f}(sim {len(fr)/sim:.1f}) | 검출 0-1.5 {r(bins['0-1.5'])} 1.5-3 {r(bins['1.5-3'])} 3-5 {r(bins['3-5'])} | "
            f"ID {nid}개 바뀜 {sw} | 겹침 프레임 {dup} 오검출 {false} | 오차 중앙 {st.median(errs):.2f} | 멈춤 {len(gaps)}구간 검출 {r(srate)} 최장끊김 {max(gaps) if gaps else 0:.1f}s")
for p in sys.argv[1:]: print(ana(p))
