import sys, csv, math
def wrap(a): return (a + math.pi) % (2*math.pi) - math.pi
rows = [{k: float(v) for k, v in r.items()} for r in csv.DictReader(open(sys.argv[1]))]
g0 = rows[0]
print(" t   정답(x,y)      yaw오차(deg) 위치오차(m) ekf오차(m) 누적회전(deg) 구간|회전오차|(deg)")
tot_rot = 0.0; prev = None; seg_rot_err = 0.0; next_t = rows[0]['t'] + 10
for r in rows:
    if prev:
        tot_rot += abs(wrap(r['gt_yaw']-prev['gt_yaw']))
        seg_rot_err += abs(wrap(r['gt_yaw']-prev['gt_yaw']) - wrap(r['od_yaw']-prev['od_yaw']))
    # 출발점 기준 상대 변위 (odom 프레임 원점 = 출발점)
    yaw_err = wrap((r['gt_yaw']-g0['gt_yaw']) - (r['od_yaw']-rows[0]['od_yaw']))
    c, s = math.cos(-g0['gt_yaw']), math.sin(-g0['gt_yaw'])
    gx, gy = (r['gt_x']-g0['gt_x'])*c - (r['gt_y']-g0['gt_y'])*s, (r['gt_x']-g0['gt_x'])*s + (r['gt_y']-g0['gt_y'])*c
    pe = math.hypot(gx-(r['od_x']-rows[0]['od_x']), gy-(r['od_y']-rows[0]['od_y']))
    ee = math.hypot(gx-(r['ek_x']-rows[0]['ek_x']), gy-(r['ek_y']-rows[0]['ek_y']))
    if r['t'] >= next_t:
        print(f"{r['t']-rows[0]['t']:5.0f} ({r['gt_x']:6.2f},{r['gt_y']:6.2f}) {math.degrees(yaw_err):8.1f} {pe:9.2f} {ee:9.2f} {math.degrees(tot_rot):10.0f} {math.degrees(seg_rot_err):10.2f}")
        next_t += 10; seg_rot_err = 0.0
    prev = r
