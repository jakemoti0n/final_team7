# 학원 2층 순찰 반복 — 목표 앞 정지 재현 (R1)

- 지시: [`orders/2026-10-12_home_patrol_repro.md`](../orders/2026-10-12_home_patrol_repro.md)
- 실행: 서브 PC (`automaton-desk`, RTX 3070), 2026-10-12 14:15~15:00, `ROS_DOMAIN_ID=98 GZ_PARTITION=desk`
- 조건: 월드 `aischool_2f`(걷는 사람 3명), 지도 `aischool_2f_map`, `aischool_waypoints.yaml`(A→G 7개), 설정 변경 없음
- 커밋: home1 `6372d97`, home2~10 `6808ade` (녹화 수정 후 도구). 도중 pull한 `2e5f852`, `962558c`는 문서만 바뀜

## 결론

- **팀원이 본 "목표 34cm 앞 정지 후 실패"는 재현되지 않았다. 10/10 OK.** 실패가 없어 2단계(사람 없음 10회)는 지시대로 하지 않았다
- 대신 **위쪽 복도 (x −3.5~−4.8, y 8.5)에서 3~5초 머뭇거림이 9회 중 4회** 나왔다 (home2, 4, 7, 10). 매번 스스로 빠져나왔다
  - 원인 후보로 보면 **2번(MPPI)**: MPPI 명령(`/cmd_vel_nav`)부터 0.01~0.02 m/s. collision monitor는 멈춘 동안 개입 없음, 위치 추정 오차 0.02~0.05 m
  - 매 회차 녹화 약 123~126초에 collision monitor `APPROACH`(감속)가 잠깐 켜졌다 꺼진 직후(약 1~3초 뒤)에 머뭇거림이 시작된다. 사람이 시간표대로 움직여서 같은 시각에 같은 사람과 만나는 것으로 보인다. 머뭇거리지 않은 회차에서는 같은 시각 `APPROACH`가 home3·9에만 있었고(124~127s), home5는 133.0s·home8은 127.2s에 한 번, home6은 없음. 즉 그 시각 근접이 있다고 늘 머뭇거리는 것은 아니다
  - `KNOWN_ISSUES`의 "위쪽 복도에서 30초간 붙잡힘 (−4.14, 8.38)"과 같은 구간이다. 이번에는 짧게 끝났지만 같은 원인일 수 있다
- **시뮬레이션 시작 실패 2/10** (home1, home7). 둘 다 `Failed to activate global_costmap because transform from base_link to map did not become available before timeout` → `sim_ctl.sh`가 다시 띄워 회복. 그 두 회차만 430초대로 길다

## 회차별 결과

| 회차 | 결과 | 시간 | 3초 넘게 멈춘 구간 (출발 직후 제자리 회전 제외) |
|---|---|---|---|
| home1 | OK | 431s* | D 지점(−11.73, 0.65) 5.5초 = waypoint D `wait_sec: 5` (정상). 녹화 수정 전 bag이라 근사 분석 |
| home2 | OK | 200s | 128.0~133.0s (−4.82, 8.56) 5.0초, MPPI 0.02 → 최종 0.02 m/s, 회전 0.05 |
| home3 | OK | 193s | 없음 |
| home4 | OK | 202s | 127.5~131.4s (−4.80, 8.47) 3.9초, MPPI 0.00, 회전 0.83 (제자리 회전) |
| home5 | OK | 212s | 없음 |
| home6 | OK | 201s | 없음 |
| home7 | OK | 435s* | 127.6~131.9s (−3.52, 8.53) 4.3초, MPPI 0.02 → 최종 0.02 m/s, 회전 0.03 |
| home8 | OK | 198s | 없음 |
| home9 | OK | 214s | 없음 |
| home10 | OK | 203s | 127.2~130.3s (−4.34, 8.48) 3.1초, MPPI 0.01 → 최종 0.01 m/s, 회전 0.23 |

\* 시뮬레이션 시작 1회 실패 후 재시작 포함

- 모든 회차에 출발 직후 3~4초 정지가 있다: (0, 0)에서 첫 목표 쪽으로 제자리 회전(0.5~0.7 rad/s). 정상 동작이라 표에서 뺐다
- 원본: [`patrol_results.txt`](patrol_results.txt). bag·로그는 서브 PC `~/limbo_bags/sim_trials/logs/patrol_home*`

## collision monitor 상태 보정

`patrol_analyze.py`는 멈춘 구간 **안에** 들어온 `/collision_monitor_state`만 본다. 이 토픽은 상태가 **바뀔 때만** 나와서(회차당 10~20개) 대부분 "기록 없음"으로 나온다.
[`cm_state.py`](cm_state.py)로 구간 시작 직전 마지막 상태까지 포함해 다시 봤다.

| 회차 | 머뭇거림 구간 | 그 동안 collision monitor | 직전 변화 |
|---|---|---|---|
| home2 | 128.0~133.0s | 개입 없음 | 123.9~125.0s APPROACH 3번 깜빡임 |
| home4 | 127.5~131.4s | 개입 없음 | 124.9~126.6s APPROACH 3번 |
| home7 | 127.6~131.9s | 개입 없음 | 123.1~124.2s APPROACH |
| home10 | 127.2~130.3s | 개입 없음 | 123.7~125.0s APPROACH |

```bash
python3 cm_state.py ~/limbo_bags/sim_trials/logs/patrol_home2_bag 128.0-133.0   # 구간은 녹화 시작 기준 초
```

## 다음에 볼 것 (제안)

- 머뭇거림 구간에 사람 위치가 녹화되지 않아 "사람 때문"은 추정이다. 녹화에 사람 예측 토픽(human_layer가 받는 것)이나 actor 정답 위치를 넣으면 확정할 수 있다
- 사람 없는 월드로 같은 10회를 돌리면 이 머뭇거림이 사라지는지로 사람 원인 여부를 가릴 수 있다 (2단계와 같은 방법)
- 팀원 실패(34cm 앞 정지)는 다른 조건(사람 시작 시각, CPU 부하, 팀원 PC 사양)일 수 있다. 팀원 실패 회차의 bag이나 로그가 있으면 같은 분석을 돌려 볼 수 있다
