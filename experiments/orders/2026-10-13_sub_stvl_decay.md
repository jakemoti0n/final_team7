# 서브 PC 지시서: 전역 costmap STVL 기억 시간 15 → 3초 시험 (R3, 2026-10-13)

## 배경
`docs/KNOWN_ISSUES.md` 맨 위 "지금 주행을 막는 것" 0번. 전역 costmap STVL이 사람이 지나간 자리를 15초 기억해 전역 경로가 몇 초마다 바뀌고 좁은 복도에서 복구를 반복한다.
10-12에 5초와 15초가 같은 성적이었는데 15초를 택했었다. 3초로 줄여도 (1) 한 명 복도 통과와 (2) 지도에 없는 상자 회피가 유지되는지 본다. `docs/PROJECT.md` 8절 다음 0번.

## 준비
```bash
cd ~/limbo && git pull --rebase origin lab && git rev-parse --short HEAD   # 결과에 적는다
build_limbo          # ktj 병합으로 PatrolState 메시지·순찰 노드가 바뀌어 빌드 필요
export ROS_DOMAIN_ID=98 GZ_PARTITION=desk
```
- 실험 도중에는 pull하지 않는다
- 충장로·레이싱 트랙 월드가 저장소에서 빠졌는데(생성 산출물), 로컬에 있던 파일은 그대로 남으니 이번 실험과는 무관

## 실행 (조건당 1회, 약 15분)
```bash
cd ~/limbo
experiments/orders/stvl_decay_one.sh 3 d3       # 전역 voxel_decay 3초: 한 명 복도 + 상자 구간
experiments/orders/stvl_decay_one.sh 15 d15     # 비교용 지금 설정(15초): 같은 두 경로
```
- 스크립트가 설정을 바꾸고 끝나면 원복한다. 중간에 끊었으면 `git checkout -- limbo/src/limbo_navigation/config/nav2_params.yaml`
- 결과 CSV: `~/limbo_bags/sim_trials/logs/trial_d3_single.csv`, `trial_d3_box.csv`, `trial_d15_single.csv`, `trial_d15_box.csv`
- `nav.log`가 비어 있고 로봇이 출발점에 10분 넘게 있으면 Nav2가 멈춘 것. 그 회차는 `kill <nav_route PID>`로 끊고 라벨 뒤에 `r`을 붙여 다시

## 보는 것
| 경로 | 기대 (3초가 좋으면) | 깨지면 |
|---|---|---|
| 한 명 복도 (`people2`, 2구간) | 복구 횟수 ↓, 구간 시간 ↓ (15초: 31·39 s, 복구 1·1) | — |
| 상자 구간 (`box`, 홀 ↔ 왼쪽 복도 왕복 2번, 홀 서쪽 낮은 상자) | 상자와 최소 거리 0.15 m 이상 유지, 닿은 시간 0 (10-12 15초: 6/6 회피, 0.16~0.23 m) | 상자에 닿으면(`obstacle_contact_time_s` > 0) 3초는 못 씀 → 사람 점만 전역에서 빼는 방식으로 |

## 결과 남기기
```bash
mkdir -p experiments/2026-10-13_stvl_decay_sub
cp ~/limbo_bags/sim_trials/logs/trial_d{3,15}_*.csv experiments/2026-10-13_stvl_decay_sub/
for f in experiments/2026-10-13_stvl_decay_sub/*.csv; do echo "== $f"; cut -d, -f3,4,6,11,12,15,17 $f; done
```
- 위 출력(상태·시간·속도·복구·사람 최소 거리·상자 최소 거리·상자 닿은 시간)과 시작 커밋, 특이사항을 `experiments/2026-10-13_stvl_decay_sub/README.md`에 적고, `docs/lab/reports.md`에 R3 완료와 표를 적는다
- 변경 기록 항목 추가(번호는 pull 받은 뒤 맨 위 + 1), "했음" 체. `git pull --rebase origin lab && git push origin lab`
- **설정 파일(`nav2_params.yaml`)은 바꾼 채로 커밋하지 않는다.** 채택은 노트북이 결과를 보고 정한다
