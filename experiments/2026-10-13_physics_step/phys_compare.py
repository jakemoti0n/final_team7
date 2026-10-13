"""phys_record.py CSV 두 개(1 ms, 2 ms)를 같은 기준으로 요약한다. 사용법: phys_compare.py 1ms.csv 2ms.csv"""
import sys, csv, math
def load(p):
    with open(p) as f: return [{k: float(v) for k, v in r.items()} for r in csv.DictReader(f)]
def wrap(a): return (a + math.pi) % (2*math.pi) - math.pi
def summarize(rows):
    g0, o0 = rows[0], rows[0]
    # 출발 자세가 다를 수 있으니 둘 다 출발점 기준 상대 변위로 비교
    def rel(r, px, py, pyaw, x0, y0, yaw0):
        dx, dy = r[px]-x0, r[py]-y0; c, s = math.cos(-yaw0), math.sin(-yaw0)
        return dx*c - dy*s, dx*s + dy*c, wrap(r[pyaw]-yaw0)
    drift, step_err, yaw_step_err, z, roll, pitch, vtrack, maxv = [], [], [], [], [], [], [], 0.0
    length = 0.0; prev = None
    for r in rows:
        gx, gy, gyaw = rel(r, 'gt_x', 'gt_y', 'gt_yaw', g0['gt_x'], g0['gt_y'], g0['gt_yaw'])
        ox, oy, oyaw = rel(r, 'od_x', 'od_y', 'od_yaw', o0['od_x'], o0['od_y'], o0['od_yaw'])
        drift.append(math.hypot(gx-ox, gy-oy))
        moving = abs(r['gt_v']) > 0.05
        if moving:
            z.append(r['gt_z']); roll.append(r['gt_roll']); pitch.append(r['gt_pitch'])
        if abs(r['cmd_v']) > 0.1: vtrack.append(abs(r['od_v'] - r['cmd_v']))
        maxv = max(maxv, r['gt_v'])
        if prev:
            dg = math.hypot(r['gt_x']-prev['gt_x'], r['gt_y']-prev['gt_y']); length += dg
            do = math.hypot(r['od_x']-prev['od_x'], r['od_y']-prev['od_y'])
            if moving:
                step_err.append(abs(dg-do))
                yaw_step_err.append(abs(wrap(r['gt_yaw']-prev['gt_yaw']) - wrap(r['od_yaw']-prev['od_yaw'])))
        prev = r
    sd = lambda a: (sum((x-sum(a)/len(a))**2 for x in a)/len(a))**0.5 if a else float('nan')
    mean = lambda a: sum(a)/len(a) if a else float('nan')
    return {
        '주행 시간 (시뮬 s)': rows[-1]['t']-rows[0]['t'], '정답 경로 길이 (m)': length, '최고 속도 (m/s)': maxv,
        'odom 누적 오차 최종 (m)': drift[-1], 'odom 누적 오차 최대 (m)': max(drift),
        '0.1 s 이동량 오차 평균 (mm)': mean(step_err)*1000, '0.1 s 이동량 오차 최대 (mm)': max(step_err)*1000,
        '0.1 s 회전량 오차 평균 (mrad)': mean(yaw_step_err)*1000,
        '본체 높이 흔들림 표준편차 (mm)': sd(z)*1000, '본체 높이 범위 (mm)': (max(z)-min(z))*1000,
        'roll 흔들림 표준편차 (mrad)': sd(roll)*1000, 'pitch 흔들림 표준편차 (mrad)': sd(pitch)*1000,
        '속도 추종 오차 |odom-cmd| 평균 (m/s)': mean(vtrack),
    }
a, b = summarize(load(sys.argv[1])), summarize(load(sys.argv[2]))
print(f"{'항목':34s} {'1 ms':>10s} {'2 ms':>10s}")
for k in a: print(f"{k:34s} {a[k]:10.3f} {b[k]:10.3f}")
