"""3단계(관제) 검증 도우미: 대시보드 서버 API로 명령을 보내고 끝날 때까지 본다. ROS 없이 표준 라이브러리만.
사용법: api3.py wait_bridge [초] | api3.py cmd <follow_enroll|follow_start|follow_stop|pause|resume> [초] | api3.py follow | api3.py alerts [n]"""
import json, sys, time, urllib.request
URL = 'http://127.0.0.1:8000'
FINAL = {'confirmed', 'rejected', 'service_unavailable', 'no_response', 'expired', 'unconfirmed', 'connection_lost'}

def get(path):
    with urllib.request.urlopen(URL + path, timeout=3) as r:
        return json.loads(r.read())

def post(path, body):
    req = urllib.request.Request(URL + path, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

what = sys.argv[1]
if what == 'wait_bridge':
    deadline = time.time() + (float(sys.argv[2]) if len(sys.argv) > 2 else 60)
    while time.time() < deadline:
        try:
            s = get('/api/v1/state')
            if s['bridge']['status'] == 'connected' and s.get('follow') and s['follow']['state']:
                print(f"bridge connected, follow={s['follow']['state']} enrolled={s['follow']['enrolled']}"); sys.exit(0)
        except Exception:
            pass
        time.sleep(1)
    print('bridge not connected'); sys.exit(1)
elif what == 'cmd':
    name = sys.argv[2]; limit = float(sys.argv[3]) if len(sys.argv) > 3 else 20
    code, body = post('/api/v1/commands', {'command': name})
    if code != 202:
        print(f'{name}: HTTP {code} {body}'); sys.exit(1)
    rid = body['request_id']; t0 = time.time()
    while time.time() - t0 < limit:
        c = get('/api/v1/state')['command']
        if c and c['request_id'] == rid and c['stage'] in FINAL:
            print(f"{name}: {c['stage']} ({c['message'] or '-'}) {time.time()-t0:.1f}s"); sys.exit(0 if c['stage'] == 'confirmed' else 1)
        time.sleep(0.2)
    print(f'{name}: timeout'); sys.exit(1)
elif what == 'follow':
    f = get('/api/v1/state')['follow']; print(json.dumps(f, ensure_ascii=False))
elif what == 'alerts':
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    for a in get('/api/v1/state')['alerts'][:n]:
        print(f"{a['at'][11:19]} [{a['severity']}] {a['kind']:9} {a['message']}{' (지속 중)' if a['active'] else ''}")
