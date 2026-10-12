"""ROS-free CLI sender -> real FastAPI HTTP/timer verification."""
import json
import subprocess
import sys
import time
from harness import ROOT, get, server, wait_for


def main():
    report = {}
    with server() as url:
        report['initial'] = get(url + '/api/v1/state')['bridge']['status'] == 'checking'
        subprocess.run([sys.executable, str(ROOT / 'tools/sender.py'), '--url', url,
                        '--scenario', 'partial', '--duration', '4'], check=True)
        state = get(url + '/api/v1/state')
        assert state['bridge']['status'] == 'connected'
        assert state['topics']['lidar_filtered']['status'] == 'delayed'
        assert sum(a['key'] == 'topic:lidar_filtered' for a in state['alerts']) == 1
        report['partial_topic_only'] = True
        wait_for(lambda: get(url + '/api/v1/state')['bridge']['status'] == 'delayed', 4)
        wait_for(lambda: get(url + '/api/v1/state')['bridge']['status'] == 'disconnected', 9)
        report['timer_delay_disconnect'] = True
        subprocess.run([sys.executable, str(ROOT / 'tools/sender.py'), '--url', url,
                        '--scenario', 'empty', '--duration', '1'], check=True)
        state = get(url + '/api/v1/state')
        assert state['bridge']['status'] == 'connected'
        assert all(t['status'] == 'never_received' for t in state['topics'].values())
        assert state['motion']['last_valid'] is None
        report['new_empty_session_clears_previous_values'] = True
    report['all_passed'] = all(report.values())
    (ROOT / 'artifacts/http-validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
