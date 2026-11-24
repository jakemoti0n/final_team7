"""바퀴 폴더 합치기 테스트."""

from datetime import datetime

from limbo_imitation import collect_metrics, run_files


def test_run_folder_name():
    name = run_files.run_folder_name(datetime(2026, 11, 24, 9, 5, 3), 2, 'manual')
    assert name == '20261124_090503_02_manual'


def test_collect_rows_merges_columns_and_skips_unfinished(tmp_path, capsys):
    a, b, c = tmp_path / 'a', tmp_path / 'b', tmp_path / 'c'
    for folder in (a, b, c):
        folder.mkdir()
    run_files.write_metrics_csv(a / run_files.METRICS_FILE, {'x': 1}, ['x'])
    run_files.write_metrics_csv(b / run_files.METRICS_FILE, {'x': 2, 'y': 3}, ['x', 'y'])
    assert collect_metrics.main([str(a), str(b), str(c)]) == 0
    out = capsys.readouterr()
    assert out.out.splitlines() == ['run,x,y', 'a,1,', 'b,2,3']
    assert 'c' in out.err


def test_meta_hashes_existing_files_only(tmp_path):
    waypoints = tmp_path / 'w.yaml'
    waypoints.write_text('a: 1\n')
    meta = run_files.build_meta('manual', 'kim', str(waypoints), '', '', '', '2026-11-24T09:00:00')
    assert len(meta['waypoints_sha256']) == 64
    assert meta['map_sha256'] is None and meta['model_file'] is None
