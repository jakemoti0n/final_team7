"""
학습용 npz(build_dataset 결과) → 정책 모델 파일(.pt). rclpy를 쓰지 않는다.

같은 데이터로 seed만 바꿔 모델 n_models개를 학습해 앙상블로 저장한다(model.Ensemble).
결과는 저장소 밖(~/limbo_bags/imitation/models/)에 쓴다. 어느 모델을 저장소에 올릴지는 PM이 매번 정한다.
사용: ros2 run limbo_imitation train_policy data.npz [-o policy.pt]
"""

import argparse
from datetime import datetime
import json
import os
import sys
import time

from limbo_imitation import config_file, model as policy_model, run_files
import numpy as np
import torch
from torch.nn import functional

SECTION = 'train_policy'
DEFAULTS = {
    'n_models': 3,
    'hidden': [256, 128],
    'lr': 1e-3,
    'batch': 256,
    'max_epochs': 200,
    'patience': 10,
    'w_weight': 2.0,
    'threshold_quantile': 0.95,
    'seed': 0,
}
DEFAULT_OUTPUT_DIR = '~/limbo_bags/imitation/models'
MIN_STD = 1e-6  # 늘 같은 값인 열(예: 사람 없는 바퀴의 사람 칸)을 0으로 나누지 않게
HUBER_DELTA = 1.0  # m/s·rad/s. 명령 범위(0.5·0.8)보다 커서 사실상 제곱 오차, 튀는 표본만 덜 민다


def load_dataset(path):
    with np.load(path) as data:
        arrays = {key: data[key] for key in data.files if key != 'info'}
        info = json.loads(str(data['info']))
    return arrays, info


def normalization(x_train):
    """학습 표본만으로 평균·표준편차. 검증 표본을 섞으면 검증이 미리 본 시험이 된다."""
    std = x_train.std(axis=0)
    return x_train.mean(axis=0), np.where(std < MIN_STD, 1.0, std)


def weighted_loss(model, x, y, weight, limits, w_weight):
    """Huber(v) + w_weight·Huber(w)의 표본 가중 평균.

    회전을 더 무겁게 보는 이유: v는 대부분 최고 속도 근처라 쉽고, 사람·벽을 피하는 판단은 w에 담긴다.
    """
    v, w = policy_model.to_command(model(x), *limits)
    loss_v = functional.huber_loss(v, y[:, 0], reduction='none', delta=HUBER_DELTA)
    loss_w = functional.huber_loss(w, y[:, 1], reduction='none', delta=HUBER_DELTA)
    return ((loss_v + w_weight * loss_w) * weight).sum() / weight.sum()


def run_epoch(model, optimizer, train, cfg, limits, generator):
    model.train()
    order = torch.randperm(len(train['y']), generator=generator)
    for start in range(0, len(order), cfg['batch']):
        index = order[start:start + cfg['batch']].to(train['y'].device)
        optimizer.zero_grad()
        loss = weighted_loss(model, train['X'][index], train['y'][index],
                             train['weight'][index], limits, cfg['w_weight'])
        loss.backward()
        optimizer.step()


def evaluate(model, part, cfg, limits):
    model.eval()
    with torch.no_grad():
        return float(weighted_loss(model, part['X'], part['y'], part['weight'], limits,
                                   cfg['w_weight']))


def train_one(seed, train, val, norm, cfg, limits):
    """모델 하나. early stopping: 검증 손실이 patience epoch 동안 나아지지 않으면 멈추고 최선 가중치로.

    반환: (모델, 검증 손실 기록[0 = 학습 전]).
    """
    torch.manual_seed(seed)
    model = policy_model.PolicyMLP(train['X'].shape[1], tuple(cfg['hidden']))
    model.set_normalization(*norm)
    model.to(train['X'].device)
    optimizer = torch.optim.Adam(model.parameters(), lr=cfg['lr'])
    generator = torch.Generator().manual_seed(seed)
    history = [evaluate(model, val, cfg, limits)]
    best, best_state, since_best = history[0], clone_state(model), 0
    for _ in range(cfg['max_epochs']):
        run_epoch(model, optimizer, train, cfg, limits, generator)
        history.append(evaluate(model, val, cfg, limits))
        if history[-1] < best:
            best, best_state, since_best = history[-1], clone_state(model), 0
        else:
            since_best += 1
        if since_best >= cfg['patience']:
            break
    model.load_state_dict(best_state)
    return model.eval(), history


def clone_state(model):
    return {key: value.detach().clone() for key, value in model.state_dict().items()}


def to_tensors(arrays, mask, device):
    return {key: torch.as_tensor(arrays[key][mask], device=device)
            for key in ('X', 'y', 'weight')}


def mean_abs_error(model, part, limits):
    """원 단위(m/s, rad/s) 평균 절대 오차."""
    with torch.no_grad():
        v, w = policy_model.to_command(model(part['X']), *limits)
    return (float((v - part['y'][:, 0]).abs().mean()), float((w - part['y'][:, 1]).abs().mean()))


def disagreement_threshold(ensemble, x_val, quantile):
    """검증 표본 불일치의 quantile 분위수.

    손으로 정하지 않는 이유: 불일치의 크기는 모델 크기·데이터 양·seed마다 달라 절대 눈금이 없다.
    "처음 보는 바퀴에서도 95 %는 이 안"이라는 뜻의 값이라야 모델을 다시 학습해도 같은 뜻이 유지된다.
    """
    _, _, disagreement = ensemble.predict(x_val)
    return float(np.quantile(disagreement, quantile))


def train_policy(npz_path, out_path, cfg, device=None):
    """학습하고 저장한다. 결과 표에 쓸 dict를 낸다."""
    device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
    arrays, info = load_dataset(npz_path)
    if not arrays['is_val'].any() or arrays['is_val'].all():
        raise ValueError('dataset needs both train and val laps (record at least 2 laps)')
    settings = info['frame_settings']
    limits = (settings['v_max'], settings['w_max'])
    train = to_tensors(arrays, ~arrays['is_val'], device)
    val = to_tensors(arrays, arrays['is_val'], device)
    norm = normalization(arrays['X'][~arrays['is_val']])
    started = time.monotonic()
    models, rows = [], []
    for i in range(cfg['n_models']):
        model, history = train_one(cfg['seed'] + i, train, val, norm, cfg, limits)
        models.append(model)
        rows.append({'seed': cfg['seed'] + i, 'epochs': len(history) - 1,
                     'initial_val_loss': history[0], 'val_loss': min(history),
                     'mae': mean_abs_error(model, val, limits)})
    ensemble = policy_model.Ensemble(models, *limits)
    threshold = disagreement_threshold(ensemble, arrays['X'][arrays['is_val']],
                                       cfg['threshold_quantile'])
    policy_model.save_policy(out_path, models, {
        'in_dim': int(arrays['X'].shape[1]), 'hidden': list(cfg['hidden']),
        'v_max': limits[0], 'w_max': limits[1], 'threshold': threshold,
        'feature_layout': info['feature_layout'], 'frame_settings': settings,
        'dataset_sha256': run_files.file_sha256(npz_path),
        'val_loss': [row['val_loss'] for row in rows]})
    return {'rows': rows, 'threshold': threshold, 'seconds': time.monotonic() - started,
            'device': device, 'out_path': out_path}


def print_table(result, file=sys.stdout):
    print(f"{'model':>5}  {'seed':>4}  {'epochs':>6}  {'val_loss':>9}  {'MAE v m/s':>9}  "
          f"{'MAE w rad/s':>11}", file=file)
    for i, row in enumerate(result['rows']):
        print(f"{i:>5}  {row['seed']:>4}  {row['epochs']:>6}  {row['val_loss']:>9.5f}  "
              f"{row['mae'][0]:>9.4f}  {row['mae'][1]:>11.4f}", file=file)
    print(f"threshold {result['threshold']:.4f}, time {result['seconds']:.1f} s "
          f"({result['device']}) -> {result['out_path']}", file=file)


def default_output():
    folder = os.path.expanduser(DEFAULT_OUTPUT_DIR)
    return os.path.join(folder, f"policy_{datetime.now().strftime('%Y%m%d_%H%M')}.pt")


def parse_args(argv):
    parser = argparse.ArgumentParser(description='학습용 npz → 정책 앙상블 .pt')
    parser.add_argument('dataset', help='build_dataset 결과 .npz')
    parser.add_argument('-o', '--output', help=f'기본 {DEFAULT_OUTPUT_DIR}/policy_<시각>.pt')
    parser.add_argument('--config', default=config_file.default_config_path())
    parser.add_argument('--device', choices=('cuda', 'cpu'))
    for key in ('n_models', 'batch', 'max_epochs', 'patience', 'seed'):
        parser.add_argument('--' + key.replace('_', '-'), dest=key, type=int)
    for key in ('lr', 'w_weight', 'threshold_quantile'):
        parser.add_argument('--' + key.replace('_', '-'), dest=key, type=float)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    overrides = {key: getattr(args, key) for key in DEFAULTS if hasattr(args, key)}
    cfg = config_file.merged(DEFAULTS, args.config, SECTION, overrides)
    out_path = args.output or default_output()
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    print_table(train_policy(args.dataset, out_path, cfg, args.device))
    return 0


if __name__ == '__main__':
    sys.exit(main())
