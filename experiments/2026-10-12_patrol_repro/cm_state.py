"""멈춘 구간마다 collision monitor 상태를 '구간 시작 직전 마지막 메시지 + 구간 안 메시지'로 계산.
patrol_analyze.py는 구간 안 메시지만 봐서, 상태가 바뀔 때만 오는 토픽을 놓친다."""
import sys, importlib.util, bisect
spec = importlib.util.spec_from_file_location('pa', '/home/automaton/limbo/tools/sim_trials/patrol_analyze.py')
pa = importlib.util.module_from_spec(spec); spec.loader.exec_module(pa)
data = pa.read(sys.argv[1])
cm = data.get('/collision_monitor_state', [])
ts = [t for t, _ in cm]
gt = data['/ground_truth/odom']; t0 = gt[0][0]
print('전체 상태 변화:', ', '.join(f'{t - t0:.1f}s {pa.ACTIONS.get(m.action_type, m.action_type)}({m.polygon_name})' for t, m in cm) or '없음')
for s, e in [tuple(map(float, w.split('-'))) for w in sys.argv[2:]]:
    s += t0; e += t0
    i = bisect.bisect_right(ts, s) - 1
    states = ([cm[i][1]] if i >= 0 else []) + [m for t, m in cm if s < t <= e]
    print(f'  {s - t0:.1f}~{e - t0:.1f}s:', ', '.join(f'{pa.ACTIONS.get(m.action_type, m.action_type)}({m.polygon_name})' for m in states) or '개입 없음 (메시지 없음)')
