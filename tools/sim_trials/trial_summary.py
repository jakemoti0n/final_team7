"""trial CSV들을 요약한다. 사용법: trial_summary.py <csv> ...  (첫 줄은 출발 구간이라 따로 보여 줌)"""
import csv, statistics as st, sys
for path in sys.argv[1:]:
    rows = list(csv.DictReader(open(path)))
    body = rows[1:]
    ok = sum(r['status'] == 'SUCCEEDED' for r in body)
    rec = [int(r['recoveries']) for r in body]; dur = [float(r['duration_s']) for r in body if r['status'] == 'SUCCEEDED']
    print(f"{path.split('/')[-1]:32s} 첫 이동 {rows[0]['status']}(상자 {rows[0]['min_obstacle_distance_m']}m)  "
          f"위쪽 복도 {ok}/{len(body)} 성공, 복구 {rec}, 성공 평균 {st.mean(dur) if dur else 0:.1f}s")
