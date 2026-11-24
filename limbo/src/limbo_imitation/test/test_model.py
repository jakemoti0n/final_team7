"""정책 모델 테스트. torch가 없는 PC에서는 건너뛴다."""

import importlib.util

import numpy as np
import pytest

# 모듈 단위 importorskip은 launch_testing pytest 플러그인과 만나 세션 전체를 건너뛰게 해서 표시로 건너뛴다
HAS_TORCH = importlib.util.find_spec('torch') is not None
pytestmark = pytest.mark.skipif(not HAS_TORCH, reason='torch not installed')
if HAS_TORCH:
    from limbo_imitation import model as policy_model
    import torch

V_MAX, W_MAX = 0.5, 0.8


def make_model(seed, in_dim=279):
    torch.manual_seed(seed)
    m = policy_model.PolicyMLP(in_dim)
    m.set_normalization(np.linspace(-1, 1, in_dim), np.linspace(0.5, 2.0, in_dim))
    return m.eval()


def test_command_range_even_for_huge_raw():
    raw = torch.tensor([[1e4, -1e4], [-1e4, 1e4], [0.0, 0.0]])
    v, w = policy_model.to_command(raw, V_MAX, W_MAX)
    assert torch.all(v >= 0) and torch.all(v <= V_MAX)
    assert torch.all(w.abs() <= W_MAX)
    v_np, w_np = policy_model.to_command(raw.numpy(), V_MAX, W_MAX)
    np.testing.assert_allclose(v_np, v.numpy(), atol=1e-6)
    assert v_np[2] == pytest.approx(V_MAX / 2) and w_np[2] == 0.0


def test_save_load_roundtrip_keeps_normalization(tmp_path):
    models = [make_model(i) for i in range(3)]
    path = tmp_path / 'p.pt'
    policy_model.save_policy(path, models, {
        'in_dim': 279, 'hidden': [256, 128], 'v_max': V_MAX, 'w_max': W_MAX,
        'threshold': 0.1, 'feature_layout': 'x', 'frame_settings': {'v_max': V_MAX},
        'dataset_sha256': 'abc', 'val_loss': [1.0, 1.0, 1.0]})
    ensemble, info = policy_model.load_policy(path)
    assert info['threshold'] == 0.1 and info['trained_at']
    np.testing.assert_allclose(ensemble.models[0].std.numpy(), models[0].std.numpy())
    x = np.random.default_rng(0).normal(size=(5, 279)).astype(np.float32)
    before = policy_model.Ensemble(models, V_MAX, W_MAX).predict(x)
    after = ensemble.predict(x)
    for a, b in zip(before, after):
        np.testing.assert_allclose(a, b, atol=1e-6)


def test_numpy_forward_matches_torch():
    m = make_model(3)
    x = np.random.default_rng(1).normal(size=(16, 279)).astype(np.float32)
    with torch.no_grad():
        expected = m(torch.as_tensor(x)).numpy()
    np.testing.assert_allclose(policy_model.numpy_forward(policy_model.numpy_weights(m), x),
                               expected, atol=1e-5)
    numpy_ens = policy_model.Ensemble([m, make_model(4)], V_MAX, W_MAX, backend='numpy')
    torch_ens = policy_model.Ensemble([m, make_model(4)], V_MAX, W_MAX, backend='torch')
    for a, b in zip(numpy_ens.predict(x[0]), torch_ens.predict(x[0])):
        assert a == pytest.approx(b, abs=1e-5)


def test_identical_models_have_zero_disagreement():
    m = make_model(0)
    ensemble = policy_model.Ensemble([m, m, m], V_MAX, W_MAX)
    _, _, disagreement = ensemble.predict(np.zeros(279, dtype=np.float32))
    assert disagreement == pytest.approx(0.0, abs=1e-9)
    _, _, different = policy_model.Ensemble([make_model(0), make_model(1)], V_MAX,
                                            W_MAX).predict(np.zeros(279, dtype=np.float32))
    assert different > 0


def test_limit_acceleration():
    # 0.1 s에 ax 0.5 → 0.05 m/s까지만, aw 2.0 → 0.2 rad/s까지만
    assert policy_model.limit_acceleration((0.0, 0.0), (0.5, -0.8), 0.1, 0.5, 2.0) == \
        (pytest.approx(0.05), pytest.approx(-0.2))
    assert policy_model.limit_acceleration((0.3, 0.1), (0.31, 0.1), 0.1, 0.5, 2.0) == \
        (pytest.approx(0.31), pytest.approx(0.1))
    assert policy_model.limit_acceleration(None, (0.5, 0.2), 0.1, 0.5, 2.0) == (0.5, 0.2)
    assert policy_model.limit_acceleration((0.1, 0.0), (0.5, 0.2), 0.0, 0.5, 2.0) == (0.1, 0.0)
