"""2단계 분석: 따라가는 동안 로봇↔운용자 거리, 다른 사람 최소 거리(충돌 0.3 m), 상태 시간, 놓침, 기다리기, 도착 여부. 사용법: ana2.py <rec2.json>"""
import json, math, sys, bisect
def nearest(seq, times, t):
    i = bisect.bisect_left(times, t); i = min(max(i, 0), len(seq) - 1)
    if i > 0 and abs(seq[i-1][0] - t) < abs(seq[i][0] - t): i -= 1
    return seq[i]
for path in sys.argv[1:]:
    d = json.load(open(path)); names = d['names'].split(','); op = names.index('operator')
    gt = d['gt']; gtt = [g[0] for g in gt]; rb = d['robot']; rbt = [r[0] for r in rb]
    st = d['states']; active = [s for s in st if s[1] in ('following', 'holding')]
    if not active: print(f'{path}: 따라가기 활성 구간 없음'); continue
    t0, t1 = active[0][0], active[-1][0]
    # 운용자가 걷기 시작·멈춘 시각 (정답 속도)
    walk = [(g[0]) for i, g in enumerate(gt[1:], 1) if math.dist(g[1][op], gt[i-1][1][op]) / max(g[0] - gt[i-1][0], 1e-3) > 0.1]
    tw0, tw1 = (walk[0], walk[-1]) if walk else (None, None)
    dist_op, dist_other, speeds = [], [], []
    for r in rb:
        if not (t0 <= r[0] <= t1): continue
        people = nearest(gt, gtt, r[0])[1]
        dist_op.append(math.hypot(r[1] - people[op][0], r[2] - people[op][1]))
        dist_other.append(min([math.hypot(r[1] - p[0], r[2] - p[1]) for i, p in enumerate(people) if i != op] or [99]))
    for a, b in zip(rb, rb[1:]):
        if t0 <= a[0] <= t1 and b[0] > a[0]: speeds.append(math.dist(a[1:3], b[1:3]) / (b[0] - a[0]))
    # 상태 시간
    dur = {}
    for a, b in zip(st, st[1:]):
        dur[a[1]] = dur.get(a[1], 0.0) + (b[0] - a[0])
    hold_eps = []; cur = None
    for s in st:
        if s[1] == 'holding':
            cur = cur or [s[0], s[0]]; cur[1] = s[0]
        elif cur: hold_eps.append(cur); cur = None
    if cur: hold_eps.append(cur)
    waits = [w for w in d['waits'] if t0 <= w[0] <= t1]; wait_t = sum(1 for w in waits if w[1]) * 0.1
    final_r = rb[-1]; final_op = gt[-1][1][op]; final_d = math.hypot(final_r[1] - final_op[0], final_r[2] - final_op[1])
    last = st[-1]
    print(f'{path.split("/")[-1]}: 활성 {t1 - t0:.0f} s (following {dur.get("following", 0):.0f} s, holding {dur.get("holding", 0):.0f} s), 끝 상태 {last[1]}/{last[2]}')
    if tw0: print(f'  운용자 걷기 {tw1 - tw0:.0f} s, 이동 {sum(math.dist(g[1][op], gt[i-1][1][op]) for i, g in enumerate(gt[1:], 1)):.1f} m')
    if dist_op:
        close = sum(1 for x in dist_op if 0.8 <= x <= 2.5) / len(dist_op)
        print(f'  로봇↔운용자 거리: 평균 {sum(dist_op)/len(dist_op):.2f} m, 최소 {min(dist_op):.2f}, 최대 {max(dist_op):.2f}, 0.8~2.5 m 안 {100*close:.0f} %')
        print(f'  다른 사람 최소 거리 {min(dist_other):.2f} m (0.3 m 미만 = 충돌: {sum(1 for x in dist_other if x < 0.3) * 0.1:.1f} s)')
    if speeds: print(f'  로봇 속도 평균 {sum(speeds)/len(speeds):.2f} m/s, 최고 {max(speeds):.2f}')
    print(f'  놓침(holding) {len(hold_eps)}회' + (f', 최대 {max(e[1]-e[0] for e in hold_eps):.1f} s' if hold_eps else '') + f'; 기다리기(/person_wait wait) {wait_t:.1f} s')
    print(f'  끝: 로봇↔운용자 {final_d:.2f} m, 로봇 ({final_r[1]:.1f}, {final_r[2]:.1f}), 운용자 ({final_op[0]:.1f}, {final_op[1]:.1f})')
