# limbo 프로젝트 개요 (ktj 트랙)

최종 갱신: 2026-09-23

## 무엇을 만드는가

서점 순찰 로봇 **limbo**. ROS 2 Jazzy + Gazebo 시뮬레이션으로 개발하고, 최종적으로 실물 로봇에 투입한다.

- 차동구동(differential drive), footprint 0.45 × 0.45 m
- 센서: mid360 3D LiDAR (지붕, 지면 0.72 m, 수평 360°, 수직 -7°~+52°) + RGB-D 카메라 (전방, FOV 72°, 5 m)
- Nav2 스택 (AMCL 위치추정 · NavFn 경로계획 · MPPI 경로추종 · STVL costmap)
- 저장소: `jakemoti0n/final_team7`

## 두 트랙으로 나눠 개발한다

| | `dev` (팀원 david) | `ktj` (준태) |
| --- | --- | --- |
| 방향 | 보수적 — 항상 동작하는 상태 유지 | 도전적 — 알고리즘 교체 실험 |
| 담당 | 인지 (YOLO 사람 인식, human_layer costmap) | 주행 (planner / controller / localization) |
| 역할 | 베이스 코드 | 실험장. 깨져도 됨 |

코드는 `dev → ktj` **단방향**으로 흐른다. ktj에서 dev로 자동으로 가지 않으며, 실험 결과가 좋으면 그때 팀원과 상의해 선택적으로 반영한다.

```
팀원 → origin/dev ──fetch──→ 로컬 ktj-dev ──merge──→ 로컬 ktj ──push──→ origin/ktj
                                                          ↑
                                                       준태 개발
```

`ktj-dev`는 dev 사본 전용이라 원격 추적을 끊어 두었다. 실수로 `origin/dev`에 push되는 것을 막기 위함이다.

## ktj 트랙의 목표

**실물 투입 전에 시뮬레이션에서 더 나은 알고리즘 조합을 찾는 것.**

planner / controller / localization을 갈아끼우며 성능을 비교하고, 그 결과와 튜닝값을 기록으로 남겨 실물 로봇 설정의 근거로 삼는다.

## 확정된 설계 방침

- **사람이 1 m 이내로 접근하면 정지한다.** 다만 혼잡 구역에서는 이 정지 기능을 끄고 웨이포인트를 따라 밀고 간다. 계속 멈추면 순찰 자체가 불가능하기 때문이다.
- **후진은 금지한다.** mid360은 수직 하향각이 -7°뿐이라 낮은 물체를 가까이서 보지 못한다(바닥 기준 5.9 m 이내 사각). 전방은 RGB-D가 덮지만 후방은 덮을 센서가 없다. 따라서 막혔을 때 탈출 수단은 제자리 회전(spin)뿐이며, 그만큼 회전 성능이 중요하다.
- **mid360을 아래로 기울일 예정이다.** 각도는 미정. 기울이면 근거리 사각이 줄지만 아래 "결정 필요" 항목의 부작용을 함께 처리해야 한다.
- **평가는 항상 사람이 움직이는 환경에서 한다.** 동적 장애물 없이 주행 알고리즘을 비교하는 것은 의미가 없다. 그래서 `use_perception` 기본값이 `true`다.
- **변경 사항은 커밋과 함께 이 `docs/`에도 문서로 남긴다.** git log를 뒤지지 않고 훑어볼 수 있게 하기 위함이다.

## 파라미터 구조

`limbo_navigation/config/` 아래를 축별로 나누고, launch 인자 조합에 맞는 파일들을 순서대로 깊은 병합해 Nav2에 넘긴다.

```
config/
├── common/        bt_navigator, behaviors, velocity_smoother, collision_monitor, docking, self_filter
├── costmap/       base.yaml  |  with_human.yaml (use_perception 일 때만)
├── planner/       navfn.yaml ...          ← planner:=<이름>
├── controller/    mppi.yaml ...           ← controller:=<이름>
├── localization/  amcl.yaml, slam.yaml    ← localization:=<이름>
└── robot/         sim.yaml, real.yaml     ← 마지막에 겹쳐짐
```

로드 순서는 `common/* → costmap/base → planner → controller → [use_perception 이면 costmap/with_human] → robot`. 뒤 파일이 앞 값을 덮는다. **단 리스트(`plugins: [...]`)는 병합이 아니라 통째로 교체**되므로 오버레이에서 목록을 바꿀 때는 전체를 다시 적어야 한다.

실제로 Nav2가 받는 값은 하나로 합쳐진 `/tmp/limbo_nav2_params_*.yaml`이며, 경로가 launch 로그에 찍힌다. 조합을 확인하거나 비교하려면:

```bash
ros2 run limbo_navigation nav2_params_tool.py show
ros2 run limbo_navigation nav2_params_tool.py diff --controller mppi --vs-controller rpp
```

파일명이 런타임에 조립되는 부분이 있어 `grep`으로는 추적되지 않는다. 무엇이 로드되는지는 위 도구나 launch 로그로 확인한다.

## 지금까지 한 일

- 패키지를 담당별 폴더(`common` / `navigation` / `perception`)로 재배치 — 팀원이 dev에 반영
- `nav2_params.yaml` 한 덩어리를 축별 파일로 분해하고 launch 인자로 조합
- `human_layer` 플러그인을 `limbo_navigation`에서 `limbo_human_costmap`으로 분리
- **Gazebo 각속도 제한 정합** — DiffDrive가 0.8 rad/s로 남아 Nav2 쪽 1.8 설정이 전부 잘리고 있었다. 1.8 / 3.0으로 맞춰 최소 회전 반경이 0.75 m → 0.33 m가 되었다
- **컨트롤러 오버레이 폴더 제거** — `use_perception` 기본값이 true라 항상 적용되고 있었고, 다른 컨트롤러에는 대응 파일이 없어 알고리즘 비교 시 조건이 불공정해지기 때문이다. 값은 `mppi.yaml`로 흡수했고 병합 결과가 이전과 동일함을 확인했다

## 앞으로 할 일

### 우선순위 높음

1. **대안 알고리즘 yaml 추가** — RPP, DWB, Smac 2D 등. Nav2 내장 플러그인이 이미 설치되어 있으므로 yaml만 작성하면 `controller:=rpp`로 바로 비교할 수 있다.
2. **측정 도구 `limbo_evaluation`** — 주행 시간, 경로 길이, 사람과의 최소 거리, 정지·recovery 횟수, 추종 오차, CPU 사용률을 CSV로 저장한다. 이것이 없으면 수십 번 돌려도 눈대중 비교가 된다.
3. **`experiments/` 폴더** — 조합별 결과와 그 시점의 파라미터 스냅샷을 누적해 실물 설정의 근거로 삼는다.

### 결정이 필요한 것

4. **mid360 기울기 각도** — 정하면 두 곳을 함께 고쳐야 한다. `pointcloud_to_laserscan`의 `target_frame`이 `mid360_link`라 센서를 기울이면 2D 스캔 슬라이스도 같이 기울어져 AMCL이 망가진다(중력 정렬 프레임으로 변경 필요). STVL `mid360_clear`의 `vertical_fov_offset`(현재 0.393 rad = 22.5°, FOV 중심각)도 기울인 만큼 내려야 한다.
5. **global costmap에 STVL을 넣을지** — 현재 전역 지도는 static + inflation뿐이라 플래너가 사람이나 맵에 없는 장애물을 전혀 모른다. 서 있는 사람이 통로를 막으면 플래너는 계속 그 통로로 경로를 그리고, 1 m 정지 정책과 겹치면 영원히 지나가지 못한다. 반면 넣으면 경로가 자주 바뀌어 진동할 수 있다.
6. **실물 모터 스펙 확인** — 각속도 1.8 rad/s가 실제로 가능한 값인지. 시뮬에서만 올려두면 실물에서 다시 튜닝해야 한다.
7. **`backup` recovery 제거** — 후진이 금지되어 명령이 0으로 잘리므로 실질적으로 동작하지 않는다. recovery 순서에 남아 있어 시간만 소모한다.
8. **`__pycache__` 추적 해제** — `.pyc` 파일이 저장소에 추적되고 있어 실행할 때마다 변경으로 뜨고 merge 시 바이너리 충돌이 난다.

### 팀원 작업이 필요한 것

9. **1 m 정지 기능** — Nav2 `collision_monitor`가 `circle` 폴리곤과 `stop` 액션을 지원하므로 설정만으로 구현할 수 있고, 폴리곤의 `enabled`가 파라미터라 혼잡 구역 전환도 런타임에 가능하다. 다만 현재 관측 소스가 원본 포인트클라우드라 서가와 벽에 계속 걸린다. **사람 위치만 담은 PointCloud2**를 `person_detector`가 발행해 주어야 한다.
10. **`human_layer` 파라미터화** — 사람 반경(0.35 m), 가우시안 폭, 예측 시간 범위, peak cost 등이 C++ 상수로 박혀 있어 튜닝하려면 재컴파일해야 한다. 컨트롤러를 바꿔가며 실험하려면 yaml로 빠져야 한다.

## 알려진 제약

- **예측 대상은 전방의 사람뿐이다.** RGB-D 시야(72°) 밖에서 접근하는 사람은 mid360이 장애물로는 잡지만 경로 예측 대상이 되지 않아 반응적으로만 회피한다.
- **낮은 물체는 가까울수록 보이지 않는다.** 0.3 m 높이 물체는 3.5 m 이내, 바닥은 5.9 m 이내가 mid360 사각이다. 전방은 RGB-D가 보완한다.
- **빌드는 메모리 8 GB에서 병렬로 하면 시스템이 멈춘다.** `MAKEFLAGS="-j2" python -m colcon build --symlink-install --executor sequential` 로 빌드한다.
