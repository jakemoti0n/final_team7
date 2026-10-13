# 충장로 번화가 전체 월드 `chungjang_all` (2026-10-13, 노트북)

## 왜 따로, 왜 10 cm 격자인가

- 200 m 월드(`chungjang`)는 거리 한 줄뿐이라 골목·블록을 도는 경로 계획 비교가 안 됨. 큰길(금남로·중앙로·서석로·천변우로) 안쪽 번화가 전체를 별도 월드로 만들었음
- 실제 크기는 거리 방향 약 470 m × 가로 약 530 m(금남로~천변우로). 처음 추정한 400 × 350 m보다 큼
- 격자 10 cm: 5 cm로 하면 격자 5,700 × 6,100 칸의 4배인 약 1억 4천만 칸(400 × 350 m만 잡아도 5,600만 칸)이라 Nav2 costmap·경로 계획·RViz가 너무 무거움. 10 cm는 약 3,500만 칸. 로봇 폭 0.5 m에 10 cm면 충분함
- 200 m 월드와 원점·방향이 같아서 좌표·waypoint를 그대로 쓸 수 있음

## 만드는 법

```
python3 limbo/src/limbo_simulation/tools/chungjang/gen_street.py --all [--preview 그림.png]
build_limbo
```
띄우기: `world:=chungjang_all map:=chungjang_all_map`

## 생성 결과

| 항목 | 값 |
|---|---|
| 지도 | 5,700 × 6,100 칸 (10 cm), 원점 (-170, -135) |
| 구역(로봇이 갈 수 있는 빈 칸) | 88,974 m² |
| 건물 | 495채 (큰길 너머 건물 242채는 뺌), 메시 16개, 26 MB, 56만 면 |
| 울타리 (큰길 가장자리) | 1,501 m |
| 메운 틈 / 채운 막힌 공간 | 2,353 m² / 1,870 m² |
| 골목 넓힘 | 185개, 최소 3 m |
| 거리 폭(벽 사이) | 최소 3.4 m · 중간 7.4 m |
| 생성 시간·메모리 | 5.7 s, 1.4 GB (건물마다 격자 마스크를 들던 처음 방식은 131 s, 30 GB) |

## 시험 (노트북, person_detector 포함 기본 launch)

- 시작: `WORLD=chungjang_all MAP=chungjang_all_map EXTRA_ARGS="record:=false" tools/sim_trials/sim_ctl.sh start all_check` → 1번에 준비됨. 오류 로그는 시작 직후 TF 대기뿐
- 메모리: 전체 6 GB 사용. planner_server 513 MB, amcl 352 MB
- Gazebo 실시간 배율 0.68~0.95 (200 m 월드 0.92와 비슷)
- NavFn 경로 계산 (`ComputePathToPose`, 원점 출발):

| 목표 | 경로 길이 | planning_time |
|---|---|---|
| (50, 0) | 50 m | 0.21 s |
| (200, 0) | 200 m | 0.21 s |
| (310, -12) 거리 끝 | 311 m | 0.22 s |
| (-103, -57) | 128 m | 0.22 s |
| (71, 402) 천변우로 쪽 | 426 m | 0.25 s |
| (300, 318) 반대쪽 구석 | 527 m | 0.37 s |

→ 3,500만 칸이어도 NavFn은 0.4 s 안. Smac·Theta*는 경로 계획 비교(다음 할 일) 때 같이 잼

## 주의

- 건물 안 좌표를 목표로 주면 status 6(ABORTED)으로 바로 실패함. 목표는 `chungjang_all_map.png`에서 빈 칸인지 확인하고 줄 것 (거리 끝은 (310, -12) 근처. (320, -5)는 건물)
- 실제 주행은 아직 안 해 봄 (경로 계산만)
