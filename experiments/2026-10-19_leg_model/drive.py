import csv, sys
for p in sys.argv[1:]:
    R = list(csv.DictReader(open(p)))
    ok = sum(r['status'] == 'SUCCEEDED' for r in R)
    print(f"{p.split('trial_')[-1][:-4]:22s} 성공 {ok}/{len(R)} 시간 {sum(float(r['duration_s']) for r in R):.0f}s 복구 {sum(int(r['recoveries']) for r in R)} "
          f"사람최소 {min(float(r['min_person_distance_m']) for r in R):.2f} 충돌 {sum(int(r['person_collision']) for r in R)} 사람앞멈춤 {sum(float(r['stopped_near_person_s']) for r in R):.0f}s")
