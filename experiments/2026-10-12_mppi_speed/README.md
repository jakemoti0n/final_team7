# MPPI 속도 튜닝 — 2026-10-12

## 배경
같은 속도 한계(0.6 m/s)에서 사람 없는 구간을 RPP는 평균 0.48 m/s, MPPI는 0.34 m/s로 달렸다 ([MPPI vs RPP](../2026-10-12_controller_mppi_vs_rpp/README.md)). MPPI를 빠르게 만들 수 있는지 본다.

## 1차: 짐작으로 값 바꾸기 → 효과 없음
조건은 MPPI vs RPP와 같음 (`people` 경로, 각 2회, `python3 tools/sim_trials/apply_mppi_tune.py ...`)

| | 기존 (3회) | A: `vx_std` 0.2→0.4 | B: A + `CostCritic.cost_weight` 6.0→3.81 |
|---|---|---|---|
| 상자 구간 시간 / 평균 속도 | 37.3 s / 0.34 m/s | 37.7 s / 0.33 | 37.9 s / 0.34 |
| 위쪽 복도 성공 | 12/12 | 7/8 | 6/8 |
| 복구 동작 (이동당) | 11.7 | 11.2 | 14.0 |

속도는 그대로이고 복도 성공률만 떨어졌다. 원본: `trial_tuneA_*.csv`, `trial_tuneB_*.csv`

## 원인 확인: MPPI가 스스로 0.44 m/s를 넘지 않음
`tools/sim_trials/speed_stages.py`로 속도 명령 3단계를 녹화해 직진 순간 435개를 비교했다.

| 단계 | 평균 | 최대 |
|---|---|---|
| 컨트롤러 `/cmd_vel_nav` | 0.38 | 0.44 |
| 속도 평활 `/cmd_vel_smoothed` | 0.38 | 0.44 |
| 최종 `/cmd_vel` (collision monitor) | 0.38 | 0.44 |
| 실제 속도 | 0.37 | 0.46 |

- 평활기·collision monitor가 깎은 순간은 1% → 원인은 MPPI 안
- MPPI는 4초 앞(`time_steps` 80 × `model_dt` 0.05)을 보는데 따라갈 경로는 로봇 앞 1.7 m만 잘라 쓴다(`prune_distance: 1.7`). 4초에 1.7 m = **0.425 m/s**보다 빠른 후보는 잘린 경로 끝을 넘어가 경로 점수에서 손해를 본다. 측정 최대 0.44 m/s와 맞는다
- Nav2 MPPI 문서 권고: `prune_distance` ≥ 최고 속도 × 예측 시간 = 0.6 × 4.0 = 2.4 m

## 2차: C (`prune_distance` 1.7 → 2.5) → 채택 후보
같은 조건 3회 (`python3 tools/sim_trials/apply_mppi_tune.py prune_distance=2.5`). 원본: `trial_tuneC_*.csv`

| | 기존 MPPI | C | RPP (참고) |
|---|---|---|---|
| 상자 구간 시간 / 평균 속도 | 37.3 s / 0.34 m/s | **27.7 s / 0.45 m/s** | 25.9 s / 0.48 |
| 상자와 최소 거리 | 0.20 m | 0.20 m | 0.11 m |
| 위쪽 복도 성공 | 12/12 | **12/12** | 6/12 |
| 복도 이동 시간 (성공 평균) | 30.6 s | **25.6 s** | — |
| 복구 동작 (이동당) | 11.7 | 11.2 | 19.8 |
| 사람과 거리 중앙값 / 최소 | 0.20 / 0.13 m | 0.18 / 0.13 m | 0.12 / 0.05 m |
| 사람 0.5 m 안 시간 | 1.3 s | 1.4 s | 1.3 s |

직진 속도 측정 (`speed_stages.py`, 직진 순간 291개): MPPI 출력 최대 **0.60 m/s**(기존 0.44), 평균 0.55(기존 0.38). 평활기·collision monitor가 깎은 순간 0%.

## 결론
`prune_distance`를 최고 속도 × 예측 시간(0.6 × 4.0 = 2.4 m)보다 길게 두면 MPPI가 사람 회피를 유지한 채 사람 없는 구간에서 RPP에 가까운 속도를 낸다. dev 반영 후보.
