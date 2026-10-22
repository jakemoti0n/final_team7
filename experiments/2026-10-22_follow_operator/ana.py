"""따라가기 1단계 분석: 운용자가 카메라에 보이는 프레임 중 맞게 찾은 비율, 다른 사람을 운용자로 잡은(바꿔치기) 횟수, 놓침.
사용법: ana.py <rec.json> [...]   환경: HFOV(반각, 기본 34°) MATCH(정답 일치 거리, 기본 0.6 m)"""
import json, math, os, sys, bisect
HFOV = math.radians(float(os.environ.get('HFOV', 34))); MATCH = float(os.environ.get('MATCH', 0.6)); FAR = 5.0; NEAR = 0.4
OCCL_ANGLE = math.radians(float(os.environ.get('OCCL_DEG', 8)))   # 더 가까운 사람이 이 각 안에 있으면 가려진 것으로 봄 (0.3 m 몸 반경 ≈ 2 m에서 8.5°)

def gt_at(gt, times, t):
    i = bisect.bisect_left(times, t)
    if i == 0: return gt[0][1]
    if i >= len(gt): return gt[-1][1]
    return gt[i][1] if abs(gt[i][0] - t) < abs(gt[i-1][0] - t) else gt[i-1][1]

def analyze(path):
    d = json.load(open(path)); names = d['names'].split(','); op = names.index('operator')
    gt = d['gt']; times = [g[0] for g in gt]
    fr = [f for f in d['frames'] if f['enrolled']]
    n_vis = ok = wrong = miss = 0; n_hidden_found_other = 0
    wrong_eps = []; lost_eps = []; cur_wrong = None; cur_lost = None; reasons = {}
    t_enroll = fr[0]['t'] if fr else None
    for f in fr:
        people = gt_at(gt, times, f['t']); cx, cy, cyaw = f['cam']
        def rel(p):
            dx, dy = p[0] - cx, p[1] - cy; dist = math.hypot(dx, dy)
            return dist, (math.atan2(dy, dx) - cyaw + math.pi) % (2 * math.pi) - math.pi
        od, oa = rel(people[op])
        visible = NEAR <= od <= FAR and abs(oa) <= HFOV
        if visible:   # 더 가까운 사람이 시선 각 안에 있으면 가려짐
            for i, p in enumerate(people):
                if i == op: continue
                pd, pa = rel(p)
                if pd < od and abs(pa - oa) < OCCL_ANGLE: visible = False; break
        if f['found']:
            reasons[f['reason']] = reasons.get(f['reason'], 0) + 1
            dists = [math.hypot(f['xy'][0] - p[0], f['xy'][1] - p[1]) for p in people]
            j = min(range(len(people)), key=lambda k: dists[k])
            is_wrong = j != op and dists[j] < MATCH and dists[op] > MATCH
        else:
            is_wrong = False
        if visible:
            n_vis += 1
            if f['found'] and not is_wrong and dists[op] < MATCH: ok += 1
            elif is_wrong: wrong += 1
            else: miss += 1
        elif f['found'] and is_wrong:
            n_hidden_found_other += 1; wrong += 1
        # 연속 구간
        if is_wrong:
            cur_wrong = cur_wrong or [f['t'], f['t'], names[j]]; cur_wrong[1] = f['t']
        elif cur_wrong: wrong_eps.append(cur_wrong); cur_wrong = None
        if visible and not f['found']:
            cur_lost = cur_lost or [f['t'], f['t']]; cur_lost[1] = f['t']
        elif cur_lost: lost_eps.append(cur_lost); cur_lost = None
    if cur_wrong: wrong_eps.append(cur_wrong)
    if cur_lost: lost_eps.append(cur_lost)
    dur = fr[-1]['t'] - fr[0]['t'] if fr else 0
    print(f'{os.path.basename(path)}: 등록 뒤 {dur:.0f} s, 프레임 {len(fr)}, 운용자 보임 {n_vis}')
    print(f'  맞게 찾음 {ok} ({100*ok/max(n_vis,1):.0f} %), 놓침 {miss} ({100*miss/max(n_vis,1):.0f} %), 바꿔치기 프레임 {wrong} (그중 운용자 안 보일 때 {n_hidden_found_other})')
    print(f'  바꿔치기 구간 {len(wrong_eps)}: ' + ', '.join(f'{e[2]} {e[1]-e[0]:.1f}s' for e in wrong_eps))
    lens = sorted(e[1] - e[0] for e in lost_eps)
    print(f'  놓침 구간 {len(lost_eps)}: 최대 {lens[-1] if lens else 0:.1f} s, 1 s 넘는 것 {sum(1 for l in lens if l > 1.0)}개')
    print(f'  근거: ' + ', '.join(f'{k} {v}' for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])))

for p in sys.argv[1:]: analyze(p)
