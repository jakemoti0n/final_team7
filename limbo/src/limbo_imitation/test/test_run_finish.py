"""한 바퀴 닫는 단계(run_files.finish_run) 테스트. 노드 없이 bag 자리에 가짜·진짜 자식 프로세스를 쓴다."""

import json
import signal
import subprocess
import sys
import time

from limbo_imitation import metrics, run_files


class StuckBag:
    """SIGINT를 받아도 안 끝나는 bag 흉내."""

    pid = 12345

    def __init__(self, exit_code=None):
        self.exit_code = exit_code
        self.signals = []

    def poll(self):
        return self.exit_code

    def send_signal(self, signum):
        self.signals.append(signum)

    def wait(self, timeout=None):
        if self.exit_code is None:
            raise subprocess.TimeoutExpired('ros2 bag record', timeout)
        return self.exit_code


def finished_meta():
    meta = run_files.build_meta('manual', 'kim', '', '', '', '', '2026-11-25T19:45:33')
    meta.update(end_time='2026-11-25T19:50:05', end_reason='node shutdown')
    return meta


def manual_log():
    return metrics.RunLog(start_time=0.0, end_time=272.0, start_reason=metrics.START_MANUAL)


def read_outputs(folder):
    with open(folder / run_files.META_FILE, encoding='utf-8') as f:
        meta = json.load(f)
    return meta, run_files.read_metrics_csv(str(folder))


def test_finish_run_reaps_bag_child_and_writes_results(tmp_path):
    bag = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    row, closed = run_files.finish_run(str(tmp_path), finished_meta(), manual_log(),
                                       metrics.DEFAULT_SETTINGS, bag, 5.0)
    assert closed and bag.returncode == -signal.SIGINT  # 거둬서 좀비로 남지 않음
    meta, rows = read_outputs(tmp_path)
    assert (meta['end_time'], meta['end_reason']) == ('2026-11-25T19:50:05', 'node shutdown')
    assert rows[0]['completed'] == 'manual' and rows[0]['passed'] == 'True'
    assert row['passed'] is True


def test_results_are_written_even_if_bag_does_not_close(tmp_path):
    bag = StuckBag()
    start = time.monotonic()
    _, closed = run_files.finish_run(str(tmp_path), finished_meta(), manual_log(),
                                     metrics.DEFAULT_SETTINGS, bag, 0.2)
    assert not closed and bag.signals == [signal.SIGINT]
    assert time.monotonic() - start < 1.0
    meta, rows = read_outputs(tmp_path)
    assert meta['end_reason'] == 'node shutdown' and len(rows) == 1


def test_bag_already_stopped_by_terminal_is_not_signalled_again(tmp_path):
    bag = StuckBag(exit_code=0)
    _, closed = run_files.finish_run(str(tmp_path), finished_meta(), manual_log(),
                                     metrics.DEFAULT_SETTINGS, bag, 0.2)
    assert closed and bag.signals == []
