"""people 경로 trial CSV 묶음을 조건별로 합쳐 요약한다. 사용법: people_summary.py 이름=csv,csv,... ..."""
import csv, statistics as st, sys
def f(x): return float(x) if x not in ('', 'inf') else float('inf')
print(f"{'조건':10s} {'첫구간 s':>9s} {'첫구간 m/s':>10s} {'상자 최소 m':>10s} {'복도 성공':>9s} {'복도 평균 s':>10s} {'복구/이동':>9s} {'사람 최소 m':>10s} {'사람 중앙 m':>10s} {'0.5m안 s':>8s}")
for arg in sys.argv[1:]:
    name, paths = arg.split('='); first, body = [], []
    for p in paths.split(','):
        rows = list(csv.DictReader(open(p))); first.append(rows[0]); body += rows[1:]
    ok = [r for r in body if r['status'] == 'SUCCEEDED']
    pmin = [f(r['min_person_distance_m']) for r in body]; ps = [f(r['personal_space_time_s']) for r in body]
    print(f"{name:10s} {st.mean(f(r['duration_s']) for r in first):9.1f} {st.mean(f(r['mean_speed_mps']) for r in first):10.2f} "
          f"{min(f(r['min_obstacle_distance_m']) for r in first):10.2f} {len(ok):>4d}/{len(body):<4d} "
          f"{st.mean(f(r['duration_s']) for r in ok) if ok else 0:10.1f} {st.mean(int(r['recoveries']) for r in body):9.1f} "
          f"{min(pmin):10.2f} {st.median(pmin):10.2f} {st.mean(ps):8.1f}")
