"""학습 스크립트 테스트: 작은 합성 데이터로 검증 손실이 주는지, 문턱이 저장되는지. CPU로 수 초."""

import importlib.util
import json

from limbo_imitation import features, frame_builder
import numpy as np
import pytest

# test_model.py와 같은 이유로 importorskip 대신 표시로 건너뛴다
HAS_TORCH = importlib.util.find_spec('torch') is not None
pytestmark = pytest.mark.skipif(not HAS_TORCH, reason='torch not installed')
if HAS_TORCH:
    from limbo_imitation import model as policy_model, train

FRONT = features.FRAME_SIZE * 2  # 최신 프레임의 정면 스캔 칸
GOAL_SIN = features.FRAME_SIZE * 2 + features.SCAN_BINS + 1  # 최신 프레임의 목표 sin 칸


def write_synthetic(path, n_laps=5, per_lap=200):
    """정답: v = 0.5·(1 − 정면 거리 특징), w = 0.6·경유점 sin."""
    rng = np.random.default_rng(0)
    n = n_laps * per_lap
    x = rng.uniform(0, 1, size=(n, features.FEATURE_SIZE)).astype(np.float32)
    x[:, GOAL_SIN] = rng.uniform(-1, 1, size=n)
    y = np.stack([0.5 * (1 - x[:, FRONT]), 0.6 * x[:, GOAL_SIN]], axis=1).astype(np.float32)
    lap_id = np.repeat(np.arange(n_laps), per_lap).astype(np.int32)
    info = {'feature_layout': features.__doc__,
            'frame_settings': frame_builder.settings_to_dict(frame_builder.FrameSettings())}
    np.savez(path, X=x, y=y, weight=np.ones(n, dtype=np.float32), lap_id=lap_id,
             stamp=np.zeros(n), is_val=lap_id == 0, info=np.array(json.dumps(info)))


def test_training_reduces_val_loss_and_saves_threshold(tmp_path):
    data, out = tmp_path / 'd.npz', tmp_path / 'p.pt'
    write_synthetic(data)
    cfg = {**train.DEFAULTS, 'max_epochs': 20, 'patience': 20, 'n_models': 2}
    result = train.train_policy(str(data), str(out), cfg, device='cpu')
    for row in result['rows']:
        assert row['val_loss'] < row['initial_val_loss'] * 0.5
    ensemble, info = policy_model.load_policy(out)
    assert info['threshold'] == pytest.approx(result['threshold'])
    assert info['threshold'] > 0
    assert len(info['dataset_sha256']) == 64
    assert info['frame_settings']['w_max'] == 0.8
    assert result['seconds'] < 10.0
    with open(train.curves_path(str(out)), encoding='utf-8') as f:
        curves = json.load(f)
    assert [len(m['train']) for m in curves['models']] == [len(m['val']) for m in curves['models']]
    assert curves['models'][0]['train'][-1] < curves['models'][0]['train'][0]


def test_normalization_ignores_constant_columns():
    x = np.array([[1.0, 5.0], [3.0, 5.0]])
    mean, std = train.normalization(x)
    np.testing.assert_allclose(mean, [2.0, 5.0])
    np.testing.assert_allclose(std, [1.0, 1.0])


def test_needs_both_train_and_val(tmp_path):
    data = tmp_path / 'd.npz'
    write_synthetic(data, n_laps=1)
    with pytest.raises(ValueError):
        train.train_policy(str(data), str(tmp_path / 'p.pt'), train.DEFAULTS, device='cpu')
