# 위치 추정 비교: AMCL(지금) vs slam_toolbox 위치 추정 모드 (2026-10-14, 메인 PC)

## 왜 했나
PROJECT 다음 3번. 같은 LiDAR 스캔(`/scan`, MID-360 → 2D)으로 AMCL(입자 필터)과 slam_toolbox 위치 추정 모드(스캔 매칭 + 포즈그래프)를 사람 있는 복도·홀에서 비교. 지표는 `nav_recorder`의 정답 대비 위치 오차(TF `map → base_footprint` vs Gazebo 정답)·복구·시간.

## 준비 (이번에 만든 것)
- `start_simulation.launch.py` `localization:=amcl|slam|mapping`. `slam`은 slam_toolbox 위치 추정 노드가 `maps/<map>_posegraph`를 읽고 `/map`·`map→odom`을 냄(map_server·AMCL 안 띄움). `mapping`은 **정적 지도를 `/map`으로 따로 띄우고** slam_toolbox 지도는 `/slam_map`으로 보내 Nav2가 기존 지도로 주행하는 동안 포즈그래프를 쌓음(slam_toolbox 지도만으로는 멀리 있는 목표가 지도 밖이라 Nav2가 0초 만에 포기)
- `limbo_navigation/config/slam_toolbox.yaml`(패키지 기본 + 우리 프레임), `tools/sim_trials/make_posegraph.sh`(지도 작성 주행 → `serialize_map`)
- 포즈그래프 `aischool_2f_map_posegraph.posegraph`(24 MB)·`.data`(1.8 MB)는 저장소에 안 넣음(.gitignore). 설치 폴더(maps는 복사 설치)에도 복사해야 읽힘
- slam 전용 lifecycle manager는 `bond_timeout 0`: 큰 포즈그래프를 처리하는 동안 heartbeat 4 s를 놓쳐 노드가 내려가고 Nav2까지 무너짐(3번 다 실패 → 0으로 두니 바로 성공)

## 조건
- 커밋 `529f877` + 위 launch 변경. 기본 BT. 비켜 주는 사람 복도(`aischool_2f_social` `people2`)·홀 손님(`zz_social_approach` `hall`), 각 1회

## 결과

| 위치 추정 | 복도 2구간 시간 s | 복구 | 위치 오차 평균 / 최대 m | 홀 4구간 시간 s | 복구 | 위치 오차 평균 / 최대 m | 충돌 |
|---|---|---|---|---|---|---|---|
| AMCL | 49.5 | 0 | 0.044 / 0.118 | 71.6 | 1 | 0.055 / 0.101 | 0 |
| slam_toolbox | 54.4 | 0 | **0.160 / 0.183** | 64.5 | 0 | **0.029 / 0.072** | 0 |

구간별 오차(평균/최대): AMCL 복도 0.055/0.092 · 0.040/0.082 · 0.048/0.118, 홀 0.050~0.063 / 0.088~0.101. slam 복도 0.082/0.183 · 0.158/0.178 · 0.162/0.183, 홀 0.021~0.041 / 0.053~0.072.

## 해석
- 홀에서는 slam_toolbox가 AMCL의 절반 오차(0.029 vs 0.055), 복도에서는 세 배(0.16 vs 0.044). 복도의 0.16은 세 구간이 거의 같은 값이라 **잡음이 아니라 치우침**이다. slam_toolbox의 `map` 프레임은 포즈그래프를 만들 때의 궤적이 기준이라, 지도 작성 주행 중 복도 쪽에서 쌓인 오차가 그대로 지도 프레임의 치우침이 된 것으로 보인다(정답은 Gazebo 월드 = 정적 지도 원점 기준). 즉 slam_toolbox가 "자기 지도 안에서" 틀린 게 아니라 우리 정적 지도·정답 프레임과 0.16 m 어긋난 것
- 주행 성적(시간·복구·충돌·사람 거리)은 둘이 같다. 1회라 차이를 말할 수 없다
- 운영 쪽: slam_toolbox는 24 MB 포즈그래프와 bond 끄기가 필요하고, 지도가 바뀌면 다시 만들어야 한다. AMCL은 pgm 하나

## 결론
- **AMCL 유지.** 이 조건에서 바꿀 이유가 없다
- slam_toolbox를 다시 볼 만한 자리는 AMCL의 약점인 **사람이 많아 LiDAR 시야가 가려지는 곳**(KNOWN_ISSUES "사람이 많아 beamskip이 꺼짐"). 네모 화면(사람 10명) 순찰에서 둘의 오차를 재는 것이 다음 시험. 그때는 포즈그래프의 치우침을 빼고 보려면 정답을 slam 지도 프레임에 맞추거나, 포즈그래프를 정적 지도에서 출발해 짧게 만든다

## 2차: 사람 10명 네모 화면 순찰 (19:30~20:06, 메인 PC) — AMCL 유지 확정

`human_test_world`(15×15 m, 시간표 사람 10명) + `test_waypoints.yaml` 순찰(3묶음 A→C·D→G·H→J), `patrol_trial.sh`, 각 1회. slam 포즈그래프는 사람을 뺀 같은 월드(`zz_human_test_nopeople`, 저장소 밖)에서 순찰 경로를 돌아 만듦. 둘 다 MPPI `enforce_path_inversion`(105) 켠 설정.

| 위치 추정 | 결과 | 3묶음 시간 합 s | 복구 | 위치 오차 평균 / 최대 m | 사람 0.3 m 미만 |
|---|---|---|---|---|---|
| AMCL | 3/3 | 145.7 | 4 | **0.035 / 0.084** | 3 |
| slam_toolbox | 3/3 | 137.4 | 3 | 0.050 / 0.086 | 3 |

- 묶음별 오차 평균: AMCL 0.026·0.044·0.034, slam 0.045·0.054·0.051. 사람 10명 사이에서도 AMCL 오차가 더 작다. "사람이 많으면 AMCL이 약하다"는 가설은 이 밀도(15×15 m에 10명)에서는 확인되지 않았다(beam skip 꺼짐 로그 0)
- 주행 성적은 같다(둘 다 완주, 시간 차 8 s는 1회 편차). 사람 0.3 m 미만 3번은 시간표 사람이 멈춘 로봇에 걸어 들어온 것
- 부수 발견: 첫 AMCL 회차(옛 설정)는 A 앞 1.2 m에서 3번 다 ABORTED — 원인은 위치 추정이 아니라 `prune_distance` 2.5 + 통과 지점 되돌이 경로(TROUBLESHOOTING, `enforce_path_inversion`으로 해결, `trial_nemo_amcl_old_prune_stall.csv`)
- 결론: **AMCL 유지 확정.** slam_toolbox가 나을 자리는 더 붐비는 환경(수십 명)이나 지도 밖 변화가 큰 곳이며, 그건 충장로 단계에서 본다
