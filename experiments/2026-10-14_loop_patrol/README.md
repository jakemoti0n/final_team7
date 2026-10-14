# 학원 2층 반복 순찰과 원격 일시정지·재개 (2026-10-14, 서브 PC)

## 왜 했나
사용자가 따로 명령하지 않으면 waypoint를 끝없이 반복하는 순찰(A → … → G → A → …)을 원했다. 순찰 노드에 `loop` 파라미터(기본값 false)를 넣고, 학원 2층에서 바퀴가 넘어가는지, 반복 중에도 관제 서버로 보낸 일시정지·재개가 되는지 본다. 끝으로 휴대폰에서 ngrok과 basic auth를 거쳐 원격 제어를 시험한다.

## 조건
- 커밋 `c6fc8cd` + 순찰 노드 `loop` 수정(커밋 전), 서브 PC (RTX 3070), `ROS_DOMAIN_ID=98`, `GZ_PARTITION=demo`, v14
- 월드 `aischool_2f`(사람 10명이 돌아다님), 지도 `aischool_2f_map`, `aischool_waypoints.yaml`(A·B·C·D 정지 5초·E·F·G 정지)
- 시연 스택: 서버(학원 지도 설정) + 시뮬레이션 + Bridge + `patrol_node -p loop:=true`
- 일시정지·재개는 서버 API `POST /api/v1/commands`로 보냄(화면 버튼과 같은 경로)

## 결과

| 시각 | 일 | 결과 |
|---|---|---|
| 09:23:47 | 순찰 시작 | patrolling, 다음 A |
| 09:26:22 | 1바퀴 끝(G 도착) | 바로 `Lap 2 started`, 다음 A (약 155 s) |
| 09:26:38 | 2바퀴째 G → A 중 일시정지 | confirmed, paused, 다음 A |
| 09:26:45 | 재개 | confirmed, patrolling, 다음 A |
| 09:29:39 ~ 09:31:49 | A 약 1.8 m 앞 (-6.74, 1.54)에서 `Failed to make progress` 반복 | Nav2가 목표 포기 → 순찰 `failed` (Navigation failed)로 끝남 |

## 결론
- **바퀴 넘김은 된다.** G 다음에 A부터 다시 돌고, 상태 사유에 `lap 2 started`가 남는다
- **반복 중 일시정지·재개도 된다** (각각 confirmed)
- **이동 실패 한 번에 반복 순찰이 끝난다.** `KNOWN_ISSUES` "Nav2가 목표를 한 번 실패하면 순찰 노드가 순찰 전체를 끝냄" 행과 같은 동작이다. 사람 10명이 다니는 월드에서는 몇 바퀴 못 가서 걸릴 수 있다. 막힌 원인(사람인지 costmap 잔상인지)은 bag을 녹화하지 않아 이번에는 모른다

## 다음
- 순찰 노드가 이동 실패에 순찰을 끝내지 않게 하기(`KNOWN_ISSUES` 순찰 노드 행). 사람 때문에 막힌 경우는 R4(BT 사람이면 기다리기)로 줄어들 수 있으니 R4 뒤에 다시 돌려 본다
- 휴대폰(ngrok + basic auth) 원격 일시정지·재개는 R4 뒤에 반복 순찰과 함께
