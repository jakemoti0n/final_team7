"""
정책 신경망(작은 MLP)과 앙상블, 저장·로드, torch 없는 numpy 추론. rclpy를 쓰지 않는다.

- PolicyMLP: 279칸 → 256 → 128 → 2(raw). 입력 정규화(평균·표준편차)를 버퍼로 품어 모델 파일과 함께
  다닌다. 정규화 상수를 따로 두면 실행 때 다른 판을 쓰는 실수가 생긴다.
- to_command: raw → (v, w). Ensemble: 같은 데이터로 seed만 바꿔 학습한 모델 N개의 평균과 불일치.
  불일치가 크다 = 모델들이 이 장면을 배운 적이 없다 → /policy/status ok=false → 중재기가 nav로.
"""

from datetime import datetime

import numpy as np
import torch
from torch import nn

DEFAULT_HIDDEN = (256, 128)
OUTPUT_SIZE = 2
FILE_KEYS = ('models', 'in_dim', 'hidden', 'v_max', 'w_max', 'threshold', 'feature_layout',
             'frame_settings', 'dataset_sha256', 'trained_at', 'val_loss')


class PolicyMLP(nn.Module):

    def __init__(self, in_dim=279, hidden=DEFAULT_HIDDEN, out=OUTPUT_SIZE):
        super().__init__()
        layers, size = [], in_dim
        for width in hidden:
            layers += [nn.Linear(size, width), nn.ReLU()]
            size = width
        layers.append(nn.Linear(size, out))
        self.net = nn.Sequential(*layers)
        self.register_buffer('mean', torch.zeros(in_dim))
        self.register_buffer('std', torch.ones(in_dim))

    def set_normalization(self, mean, std):
        self.mean.copy_(torch.as_tensor(mean, dtype=torch.float32))
        self.std.copy_(torch.as_tensor(std, dtype=torch.float32))

    def forward(self, x):
        return self.net((x - self.mean) / self.std)


def to_command(raw, v_max, w_max):
    """출력(raw) → (v, w). torch 텐서와 numpy 배열 모두 받는다(마지막 축이 2칸).

    v = v_max·sigmoid: 0~v_max. 뒤를 보는 센서가 없어 후진하지 않는다(설계 2-3).
    w = w_max·tanh: ±w_max. 상한은 nav2_real.yaml(vx_max 0.5, wz_max 0.8)·보드가 받는 범위.
    모델이 아무리 큰 값을 내도 출력이 이 범위를 못 넘게 구조로 막는다.
    """
    if isinstance(raw, np.ndarray):
        v = v_max * 0.5 * (1.0 + np.tanh(0.5 * raw[..., 0]))  # = sigmoid, 큰 값에서 exp가 넘치지 않는 꼴
        return v, w_max * np.tanh(raw[..., 1])
    return v_max * torch.sigmoid(raw[..., 0]), w_max * torch.tanh(raw[..., 1])


def limit_acceleration(previous, target, dt, ax_max, aw_max):
    """직전 명령에서 dt 동안 ax_max·aw_max 넘게 바뀌지 않게 자른다.

    previous가 None이면 target 그대로, dt <= 0이면 previous 그대로(시간이 안 흘렀으면 못 바뀐다).
    """
    if previous is None:
        return target
    if dt <= 0.0:
        return (float(previous[0]), float(previous[1]))
    dv = np.clip(target[0] - previous[0], -ax_max * dt, ax_max * dt)
    dw = np.clip(target[1] - previous[1], -aw_max * dt, aw_max * dt)
    return (float(previous[0] + dv), float(previous[1] + dw))


def numpy_weights(model):
    """모델(PolicyMLP) → numpy 배열 dict(numpy_forward용). 키는 state_dict와 같다."""
    return {key: value.detach().cpu().numpy().astype(np.float32)
            for key, value in model.state_dict().items()}


def numpy_forward(weights, x):
    """같은 계산을 torch 없이(Jetson에서 torch가 없을 때의 선택지). x: (279,) 또는 (N, 279)."""
    h = (np.asarray(x, dtype=np.float32) - weights['mean']) / weights['std']
    layer_ids = sorted({int(key.split('.')[1]) for key in weights if key.startswith('net.')})
    for i, layer in enumerate(layer_ids):
        h = h @ weights[f'net.{layer}.weight'].T + weights[f'net.{layer}.bias']
        if i < len(layer_ids) - 1:
            h = np.maximum(h, 0.0)
    return h


class Ensemble:
    """모델 N개 묶음. backend 'torch'면 torch로, 'numpy'면 numpy_forward로 추론한다."""

    def __init__(self, models, v_max, w_max, backend='torch'):
        if backend not in ('torch', 'numpy'):
            raise ValueError(f'backend must be torch or numpy, got {backend}')
        self.models = [m.eval() for m in models]
        self.weights = [numpy_weights(m) for m in models] if backend == 'numpy' else None
        self.v_max, self.w_max, self.backend = v_max, w_max, backend

    def raw_outputs(self, x):
        """(모델 수, ..., 2) numpy 배열."""
        if self.backend == 'numpy':
            return np.stack([numpy_forward(w, x) for w in self.weights])
        with torch.no_grad():
            tensor = torch.as_tensor(np.asarray(x, dtype=np.float32))
            device = next(self.models[0].parameters()).device
            return np.stack([m(tensor.to(device)).cpu().numpy() for m in self.models])

    def predict(self, x):
        """(평균 v, 평균 w, 불일치). x가 여러 줄이면 각각 배열.

        불일치 = 정규화 출력(v/v_max, w/w_max)의 모델 간 표준편차를 두 칸 더한 것.
        단위가 다른 v·w를 같은 눈금으로 보려고 상한으로 나눈다.
        """
        v, w = to_command(self.raw_outputs(x), self.v_max, self.w_max)
        disagreement = np.std(v / self.v_max, axis=0) + np.std(w / self.w_max, axis=0)
        return v.mean(axis=0), w.mean(axis=0), disagreement


def save_policy(path, models, info):
    """.pt 저장. info에는 FILE_KEYS 중 models·trained_at 말고 나머지가 있어야 한다."""
    data = {key: info[key] for key in FILE_KEYS if key not in ('models', 'trained_at')}
    data['models'] = [{k: v.detach().cpu() for k, v in m.state_dict().items()} for m in models]
    data['trained_at'] = datetime.now().isoformat(timespec='seconds')
    torch.save(data, path)
    return data


def load_policy(path, backend='torch', device='cpu'):
    """.pt → (Ensemble, 파일 내용 dict). weights_only로 읽어 파일 속 임의 코드는 실행하지 않는다."""
    data = torch.load(path, map_location=device, weights_only=True)
    missing = [key for key in FILE_KEYS if key not in data]
    if missing:
        raise ValueError(f'model file missing keys: {missing}')
    models = []
    for state in data['models']:
        model = PolicyMLP(data['in_dim'], tuple(data['hidden']))
        model.load_state_dict(state)
        models.append(model.to(device))
    return Ensemble(models, data['v_max'], data['w_max'], backend), data
