# 작업 지시: 학원 2층 순찰 반복 — 목표 앞 정지 재현

- **상태**: 진행 (서브 PC, 2026-10-12 시작)
- **담당**: 집 컴퓨터
- **지시**: 메인(학원 컴퓨터) 2026-10-12
- **브랜치**: `lab`

## 배경
팀원이 학원 2층 순찰을 10번 돌렸더니 1번, 로봇이 waypoint **34cm 앞에서 멈춘 뒤** 주행이 실패했다 (도착 판정 범위는 25cm).
원인 후보는 세 가지다.
1. **collision monitor**: MPPI는 속도를 내는데 최종 `/cmd_vel`만 0 (목표 근처에 사람·벽)
2. **MPPI**: 목표 근처 cost 때문에 MPPI 자체가 0 근처에서 머묾
3. **위치 추정**: 위치가 틀어져 목표가 벽 팽창 구역 안으로 들어감

이 실험은 **설정을 바꾸지 않고** 지금 상태(lab = dev + 순찰 waypoint 파라미터)에서 같은 현상이 나는지 보고, 나면 위 셋 중 무엇인지 가린다.

## 규칙
- `lab` 브랜치에서만 작업한다. **`dev`, `ktj`에 push하지 않는다**
- `limbo/src/` 아래 코드와 설정(`nav2_params.yaml` 등)을 **고치지 않는다**. 관찰 실험이다
- 프로세스는 스크립트(`sim_ctl.sh stop`)나 PID로만 끈다. `pkill -f`처럼 이름 패턴으로 끄지 않는다 (자기 셸까지 꺼질 수 있음)
- rosbag(`*_bag/`)은 크니까 커밋하지 않는다. 요약 텍스트와 분석 결과만 커밋한다
- 막히면(빌드 실패, 시뮬레이션이 안 뜸 등) 더 진행하지 말고 아래 "결과"에 증상과 로그를 적고 상태를 `막힘`으로 바꿔 push한다

## 준비 (한 번)
노트북과 같은 네트워크일 수 있으므로 서브 PC는 ROS·Gazebo 통신을 분리한다 (LAB_BOARD Q1).
```bash
export ROS_DOMAIN_ID=98 GZ_PARTITION=desk     # 시험하는 터미널마다
cd ~/limbo && git fetch && git switch lab && git pull
build_limbo
cd tools/sim_trials && ./sim_ctl.sh start check && ./sim_ctl.sh stop
```
- `ready`와 `남은 gz: 0  남은 launch: 0`이 나오면 된다
- 화면 오류(GLX 등)로 안 뜨면 NVIDIA 그래픽만 있는 데스크톱일 수 있다: `export __NV_PRIME_RENDER_OFFLOAD=0` 후 다시
- `nvidia-smi`가 `Driver/library version mismatch`면 드라이버가 자동 업데이트된 것이다. 재부팅이 필요하니 `막힘`으로 기록한다

## 1단계: 걷는 사람 3명 있는 상태로 10번
```bash
cd ~/limbo/tools/sim_trials
for k in $(seq 1 10); do ./patrol_trial.sh home$k; done
cat ~/limbo_bags/sim_trials/logs/patrol_results.txt
```
- 한 번에 약 5~10분. 결과는 `OK` / `FAIL (...)` / `TIMEOUT` / `START_FAIL`
- **OK가 아닌 회차마다** 분석한다
  ```bash
  python3 patrol_analyze.py ~/limbo_bags/sim_trials/logs/patrol_home<k>_bag
  grep -vE "^\[" ~/limbo_bags/sim_trials/logs/patrol_home<k>.log | tail -20
  ```
  분석 결과의 마지막 화살표(→)가 원인 후보다. OK 회차도 `주행 중 3초 넘게 멈춘 구간`이 있으면 같이 적는다

## 2단계: 1단계에서 실패가 있었을 때만 — 사람 없이 10번
사람이 원인인지 가린다. 사람만 뺀 월드를 **로컬에서만** 만든다 (커밋하지 않는다).
```bash
cd ~/limbo/limbo/src/limbo_simulation/worlds
python3 -c "import re; s=open('aischool_2f.sdf').read(); open('aischool_2f_noactors.sdf','w').write(re.sub(r'\n    <actor .*?</actor>', '', s, flags=re.S))"
cd ~/limbo/limbo && python -m colcon build --symlink-install --packages-select limbo_simulation
cd ~/limbo/tools/sim_trials
for k in $(seq 1 10); do WORLD=aischool_2f_noactors ./patrol_trial.sh home_noactor$k; done
```
끝나면 `aischool_2f_noactors.sdf`를 지운다 (`git status`에 남지 않게).

## 결과 남기기
1. `experiments/2026-10-12_patrol_repro/README.md`를 만든다
   - 조건 (월드, 횟수, 커밋 해시 `git rev-parse --short HEAD`)
   - 회차별 결과 표 (`patrol_results.txt` 내용)
   - 실패·멈춤 회차의 `patrol_analyze.py` 출력과 순찰 로그 마지막 부분
   - 결론: 재현됐는지, 됐다면 원인 후보 셋 중 무엇인지, 사람 유무에 따라 달라지는지
2. 이 지시서의 **상태**를 `완료`(또는 `막힘`)로 바꾼다
3. `experiments/README.md` 표에 한 줄 추가한다
4. `docs/lab/reports.md`의 R1 진행 상태를 바꾸고 결론 한두 줄을 "결과"에 적는다 (예전 `LAB_BOARD.md`는 쓰지 않음)
5. 커밋하고 `lab`에 push한다 (`git push origin lab`)
