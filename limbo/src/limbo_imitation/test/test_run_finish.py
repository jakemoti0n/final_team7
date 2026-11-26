"""한 바퀴 닫는 단계(run_files.finish_run) 테스트. 노드 없이 bag 자리에 가짜·진짜 자식 프로세스를 쓴다."""

from datetime import datetime
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


# ---------------------------------------------------------------- 콘솔 문구


START = datetime(2026, 11, 26, 19, 19, 2)


def test_button_lines_match_approved_wording():
    assert (run_files.start_line(1, metrics.START_BUTTON, START)
            == '[기록] 1번째 바퀴 기록 시작 (19:19:02) — 이제 출발하세요')
    assert (run_files.end_line(1, metrics.START_BUTTON, 148.3, 44.42, True)
            == '[기록] 1번째 바퀴 기록 끝 — 148초, 44.4 m, 저장 완료')
    assert run_files.IDLE_LINE == '[기록] 지금은 기록 중이 아닙니다. 다음 바퀴는 ≡를 누르세요'


def test_end_line_has_no_pass_verdict():
    line = run_files.end_line(2, metrics.START_BUTTON, 60.0, 10.0, True)
    assert 'passed' not in line and '합격' not in line


def test_other_start_reasons_read_naturally():
    assert (run_files.start_line(3, metrics.START_MANUAL, START)
            == '[기록] 3번째 바퀴 기록 시작 (19:19:02, 런치와 함께 시작) — 이제 출발하세요')
    # 순찰은 로봇이 스스로 가므로 출발 안내가 없다
    assert (run_files.start_line(1, 'patrolling', START)
            == '[기록] 1번째 바퀴 기록 시작 (19:19:02, 순찰 시작)')


def test_other_end_reasons_and_unknown_values():
    assert (run_files.end_line(1, 'node shutdown', 272.0, 44.8, True)
            == '[기록] 1번째 바퀴 기록 끝(런치 종료) — 272초, 44.8 m, 저장 완료')
    # 거리를 모르면(odom 없음) 빼고, bag이 안 닫혔으면 저장 완료라고 하지 않는다
    assert (run_files.end_line(1, 'completed', 30.0, None, False)
            == '[기록] 1번째 바퀴 기록 끝(순찰 완주) — 30초, bag이 아직 안 닫힘(아래 경고 참고)')
