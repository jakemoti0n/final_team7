# 서브 PC 지시서: 사람 있는 복도에서 속도 설정 A·B·C 각 1회 (R2, 2026-10-13)

## 배경
사람 없는 충장로에서는 `prune_distance` 2.5(B)·상한 0.75(C)가 빨라지는 것을 확인했다([chungjang_speed](../2026-10-13_chungjang_speed/README.md)).
사람이 걷는 학원 시나리오에서는 원래 목표 지점이 사람 동선 위라 지금 설정부터 끼여서 비교를 못 했다([people_speed](../2026-10-13_people_speed/README.md)).
목표를 벽 쪽으로 옮긴 `people_side` 경로로 노트북이 A·B·C를 2회씩 돌리는 중이고, 서브 PC가 **3회차를 맡아** 조건당 3회를 채운다.

## 준비
```bash
cd ~/limbo && git pull --rebase origin lab && git rev-parse --short HEAD   # 이 해시를 결과에 적는다
build_limbo          # 월드 물리 스텝이 2 ms로 바뀌어 install에 다시 복사해야 함 (변경 기록 (39))
export ROS_DOMAIN_ID=98 GZ_PARTITION=desk
```
- 실험 도중에는 pull하지 않는다
- 실시간 비율을 한 번 잰다 (서브 PC가 노트북보다 빠르거나 느리면 결과 해석에 필요):
  `./tools/sim_trials/sim_ctl.sh start rtf` → `python3 experiments/2026-10-13_physics_step/speed_probe.py 10` → `./tools/sim_trials/sim_ctl.sh stop`. RTF 열의 값 5개를 보고에 적는다

## 실행 (조건당 1회, 순서대로)
```bash
cd ~/limbo
experiments/orders/people_side_one.sh A sideA3
experiments/orders/people_side_one.sh B sideB3
experiments/orders/people_side_one.sh C sideC3
```
- 한 회 8~12분. 경로는 홀 → 왼쪽 복도 위쪽 끝(벽 쪽) → 위쪽 복도 동쪽(벽 쪽) 왕복 2번
- 결과 CSV는 `~/limbo_bags/sim_trials/logs/trial_side{A,B,C}3.csv`
- 어떤 회차의 `nav.log`(같은 폴더)가 첫 줄만 찍고 멈추면 경로 스크립트가 Nav2 결과를 놓친 것이다(노트북에서 1번 있었음). 그 회차는 버리고 같은 라벨 뒤에 `r`을 붙여 다시 돌린다 (예: `sideB3r`)

## 결과 남기기
```bash
mkdir -p experiments/2026-10-13_people_speed_sub
cp ~/limbo_bags/sim_trials/logs/trial_side?3*.csv experiments/2026-10-13_people_speed_sub/
python3 experiments/2026-10-13_people_speed/people_summary.py \
  A=experiments/2026-10-13_people_speed_sub/trial_sideA3.csv \
  B=experiments/2026-10-13_people_speed_sub/trial_sideB3.csv \
  C=experiments/2026-10-13_people_speed_sub/trial_sideC3.csv
```
- 요약 표 출력, 시작 커밋, RTF 5개 값, 회차별 특이사항(갇힘·복구 반복·시작 실패)을 `experiments/2026-10-13_people_speed_sub/README.md`에 적고, `docs/lab/reports.md`에 R2 완료와 표를 적는다
- 커밋 메시지는 "했음" 체, `docs/CHANGELOG.md`에 항목 추가 (번호는 pull 받은 뒤 마지막 번호 + 1)
- `git pull --rebase origin lab && git push origin lab`

## 여유가 있으면 (R2-b)
충장로 거리 200 m 왕복을 조건당 1회 더 (노트북 1회 결과의 재현 확인). 아래를 조건별로:
```bash
# A
WORLD=chungjang MAP=chungjang_map GOAL_TIMEOUT=450 ./tools/sim_trials/trial.sh streetA2 street
# B: python3 tools/sim_trials/apply_mppi_tune.py prune_distance=2.5 후 위 명령(라벨 streetB2), 끝나면 git checkout -- limbo/src/limbo_navigation/config/nav2_params.yaml
# C: people_side_one.sh의 C 설정 세 줄을 적용한 뒤 라벨 streetC2, 끝나면 nav2_params.yaml·limbo.gazebo.xacro 둘 다 checkout
```
결과 CSV 3개의 `duration_s`, `mean_speed_mps`, `recoveries`를 보고에 적는다.
