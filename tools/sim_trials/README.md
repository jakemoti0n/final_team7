# 시뮬레이션 반복 시험 도구 (실험용, lab)

시나리오 월드를 띄우고 정해진 경로를 Nav2로 돌린 뒤, 측정 도구(`record:=true`) CSV를 모아 비교한다.
결과는 저장소 밖 `~/limbo_bags/sim_trials/logs/`에 쌓인다.

## 자주 쓰는 것

```bash
cd ~/limbo/tools/sim_trials
./sim_ctl.sh start <이름>          # 창 없이(gui:=false) 띄우고 Nav2·위치 추정이 준비될 때까지 기다림. 시작 실패면 최대 3번 다시 띄움
./sim_ctl.sh stop                  # 이 스크립트가 띄운 프로세스만 끔
./trial.sh <이름> <box|people>     # 띄우기 → 경로 주행 → 끄기 → logs/trial_<이름>.csv
python3 trial_summary.py ~/limbo_bags/sim_trials/logs/trial_*.csv
```

- 월드·지도 바꾸기: `WORLD=human_test_world MAP=human_test_map ./trial.sh ...` (경로는 `nav_route.py`의 `room`)
- launch 인자 추가: `EXTRA_ARGS="person_model:=..." ./sim_ctl.sh start ...`
- 설정 실험: `python3 apply_controller.py rpp`, `python3 apply_global_stvl.py <초>` (되돌리기: `git checkout limbo/src/limbo_navigation/config/nav2_params.yaml`)
- 다른 컴퓨터와 같은 네트워크라면 `ROS_DOMAIN_ID`를 서로 다르게 하고 `GZ_PARTITION`도 나눈다

## 경로 (`nav_route.py`)

| 이름 | 내용 |
|---|---|
| `box` | 홀 ↔ 왼쪽 복도 위쪽 끝 왕복 2번 (홀 서쪽 낮은 상자) |
| `people` | 왼쪽 복도 위쪽 끝 → 위쪽 복도 왕복 2번 (나란히 걷는 두 사람) |
| `room` | human_test_world 네 모서리와 가운데 |

## 분석

| 스크립트 | 내용 |
|---|---|
| `record_drive.sh` + `slip_replay.py` | 헛돎 판단 재현 (스캔·odom·정답 위치 녹화 후 정답과 비교) |
| `record_frames.py` + `compare_models.py`, `false_person.py` | 사람 인식 모델 비교 (YOLO만) |
| `pred_record.py` + `pred_compare.py`, `stop_pos_err.py` | 사람 인식 전체 비교 (멈춘 사람 끊김·ID·위치 오차) |
