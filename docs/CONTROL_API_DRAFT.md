# 관제 화면 2단계 계약 초안 (명령·순찰 상태·위치)

작성: 2026-10-12 (ktj) · 상태: **초안, itkwon과 합의 전**

`docs/CONTROL_SCREEN.md` A-2단계(정지·재개 명령)와 B(로봇 위치·지도)에 필요한 Bridge ↔ 서버 ↔ 화면 계약이다.
합의되면 내용을 Bridge PRD(`relay_prog/docs/PRD.md` §3, 계약의 단일 기준)와 Dashboard PRD로 옮기고 이 파일은 지운다.

## 지키는 원칙 (v1 그대로)

- 모든 필드는 필수. 값이 없을 때만 `null`. 정의 안 된 필드는 거부
- 시각은 UTC ISO 8601 밀리초 + `Z`. **로봇 시각과 서버 시각을 빼서 판단하지 않는다** (경과 시간은 각자의 단조 증가 시계로 잼)
- 응답이 없어도 같은 요청을 다시 보내지 않는다. 명령은 특히 자동 재전송 금지 (Dashboard PRD §5.3)
- 텔레메트리 요청은 8 KiB 이하. 영상·지도 원본은 넣지 않음

## 전체 구성

```
[화면] ──POST /api/v1/commands──► [서버] ◄──GET /api/v1/commands/next (long poll)── [Bridge] ──/patrol/pause, /patrol/resume──► [순찰 노드]
                                    ▲     ◄──POST /api/v1/commands/{id}/result────
[화면] ◄──WS /api/v1/stream──────── │     ◄──POST /api/v1/telemetry (v2: 순찰 상태·위치 추가)── [Bridge] ◄── /patrol/state, /amcl_pose
[화면] ◄──GET /api/v1/map(.png)──── [서버] (지도 파일은 서버 설정에서 읽음)
```

| 바뀌는 것 | 방식 | 이유 |
|---|---|---|
| 순찰 상태·로봇 위치 | **텔레메트리 v2**에 `patrol`, `pose` 추가 | 1초 heartbeat·세션·순번·경과 시간 규칙을 그대로 씀. 통로를 더 만들 필요 없음 |
| 명령 | **별도 API** (Bridge가 서버에 먼저 묻는 long poll) | 텔레메트리 응답에 실으면 최대 1초 늦어지고, 전송 실패 중(최대 10초 간격)엔 명령도 막힘. 정지는 빨라야 함 |
| 지도 | 서버가 직접 파일에서 읽음 | 주행 중 바뀌지 않아 로봇에서 보낼 이유 없음 |

---

## 1. 텔레메트리 v2 (`POST /api/v1/telemetry`)

v1 필드는 전부 그대로, `schema_version: 2`와 아래 두 객체만 추가한다.
서버는 전환 기간 동안 v1·v2를 모두 받는다 (v1이면 `patrol`, `pose`를 `null`로 본다).

### `patrol` (원본 `/patrol/state`)

| 필드 | 형식 | 의미 |
|---|---|---|
| `state` | 문자열 또는 `null` | `waiting_localization` · `patrolling` · `pausing` · `paused` · `completed` · `failed` |
| `waypoint_index` / `waypoint_count` | 0 이상 정수 또는 `null` | 다음 목표 번호 / 전체 수 |
| `waypoint_name` | 문자열 또는 `null` | 다음 목표 이름 (끝났으면 빈 문자열) |
| `has_resumable_task` | 불 또는 `null` | 재개 버튼 허용 기준 |
| `reason` | 문자열 또는 `null` | 마지막 변경 이유 (최대 200자) |
| `update_count` | 0 이상 정수 | 이 Bridge 세션에서 받은 `/patrol/state` 수. **명령 이후 상태인지 판정할 때 씀** (아래 3.3) |
| `last_received_at` / `age_ms` | v1 토픽과 같음 | |

- 한 번도 못 받았으면 `update_count: 0`, 나머지 `null`
- `/patrol/state`는 상태가 바뀔 때만 오므로 `age_ms`가 커도 이상이 아니다. 순찰 노드가 살아 있는지는 판단하지 않는다 (화면은 "마지막 상태"로 표시)

### `pose` (원본 `/amcl_pose`)

| 필드 | 형식 | 의미 |
|---|---|---|
| `frame_id` | 문자열 또는 `null` | `map`이어야 함 |
| `x`, `y` | 유한 숫자 또는 `null` | 지도 좌표 (m) |
| `yaw` | 유한 숫자 또는 `null` | 방향 (rad, −π~π) |
| `position_std_m` | 0 이상 유한 숫자 또는 `null` | 위치 불확실성. 공분산 xx·yy 중 큰 값의 제곱근 |
| `last_received_at` / `age_ms` | v1 토픽과 같음 | |

- 미수신·무효(NaN 등)면 위치 필드 전부 `null` (v1 `motion`과 같은 규칙)
- 화면: `age_ms` + 서버 경과 시간이 3초를 넘으면 "위치 확인 불가"로 흐리게

추가 크기는 약 400바이트로 8 KiB 안에 들어간다.

---

## 2. 명령 API

### 2.1 화면 → 서버: 명령 요청 `POST /api/v1/commands`

```json
{"command": "pause"}
```

| 응답 | 경우 |
|---|---|
| 202 `{"request_id": "...", "command": "pause", "issued_at": "...Z", "stage": "queued"}` | 접수 |
| 409 `command_in_progress` | 끝나지 않은 명령이 있음 (화면도 그동안 버튼을 잠금) |
| 409 `bridge_not_connected` | Bridge 상태가 `connected`가 아님 |
| 422 `invalid_command` | `pause`, `resume` 외 |

- `request_id`는 서버가 만든 UUID. 화면은 이 ID로 진행 상황을 본다
- 한 번에 명령 하나만 (진행 중이면 거절). 명령 대기열은 길이 1

### 2.2 Bridge → 서버: 명령 가져오기 `GET /api/v1/commands/next`

쿼리: `robot_id`, `bridge_session_id`, `wait_s` (최대 10)

| 응답 | 경우 |
|---|---|
| 200 `{"request_id": "...", "command": "pause", "ttl_ms": 4870}` | 보낼 명령이 있음. 서버는 이때 `stage`를 `delivered`로 바꿈 |
| 204 | `wait_s` 동안 명령이 없음 → Bridge는 바로 다시 요청 |
| 409 `robot_id_mismatch` / `retired_session` | v1과 같은 의미 |

- **`ttl_ms`**: 이 명령이 아직 유효한 남은 시간 (발급 후 5초 기준). 시각이 아니라 남은 시간으로 주는 이유는 로봇·서버 시계를 비교하지 않기 위해서. Bridge는 받은 순간부터 자기 단조 시계로 재고, 지나면 서비스를 부르지 않고 `expired`로 보고한다
- 같은 명령은 한 번만 내준다. Bridge가 받고 응답이 유실돼도 다시 내주지 않는다 (재전송 금지)
- 텔레메트리 전송과 **별도 연결·별도 작업**으로 돈다. 한쪽이 막혀도 다른 쪽에 영향 없음

### 2.3 Bridge → 서버: 결과 보고 `POST /api/v1/commands/{request_id}/result`

```json
{
  "robot_id": "LIMBO-01",
  "bridge_session_id": "4c829302-...",
  "request_id": "...",
  "outcome": "accepted",
  "message": "pause accepted",
  "service_latency_ms": 12.4,
  "patrol_update_count_at_call": 41
}
```

| `outcome` | 뜻 |
|---|---|
| `accepted` | 서비스 `success: true` |
| `rejected` | 서비스 `success: false` (`message`에 사유: `already paused` 등) |
| `no_response` | 서비스 3초 안에 응답 없음 |
| `service_unavailable` | 서비스가 없음 (순찰 노드 꺼짐) |
| `expired` | `ttl_ms`가 지나 부르지 않음 |

- `patrol_update_count_at_call`: 서비스를 부르기 직전까지 받은 `/patrol/state` 수 (텔레메트리 `patrol.update_count`와 같은 카운터)
- 서버 응답: 200 `{"accepted": true}`. 이미 끝난 명령에 대한 늦은 보고는 200 `{"accepted": false, "reason": "command_closed"}` (결과를 바꾸지 않음, PRD §5.3)

---

## 3. 서버의 명령 판정

### 3.1 단계

```
queued → delivered → accepted → confirmed        (성공)
                   ↘ rejected                    (명시적 실패)
       ↘ (5초 안에 결과 없음) no_response        (확인 불가)
                   accepted ↘ (5초 안에 상태 확인 없음) unconfirmed  (확인 불가)
       ↘ expired                                 (확인 불가)
```

| 단계 | 화면 표시 (Dashboard PRD §5.3 표) |
|---|---|
| `queued`, `delivered` | 정지 요청 중 / 재개 요청 중 |
| `accepted` | 로봇 응답 받음, 상태 확인 중 |
| `confirmed` | 정지 상태 확인됨 / 재개 확인됨 |
| `rejected` | 정지 요청 실패 / 재개 실패 (사유 함께) |
| `no_response`, `unconfirmed`, `expired`, 중간에 Bridge 끊김 | 정지 여부 확인 불가 / 재개 여부 확인 불가 |

제한 시간은 Dashboard PRD 데모 기본값과 같은 **응답 5초, 상태 확인 5초**. 서버 설정으로 바꿀 수 있게 한다.

### 3.2 성공 조건 (Dashboard PRD §5.4)

| 명령 | `confirmed` 조건 |
|---|---|
| pause | `accepted` 이후 텔레메트리에서 `patrol.update_count > patrol_update_count_at_call` **이고** `patrol.state == "paused"` **이고** 그 뒤 `motion`이 최신 값이면서 정지 기준(0.05 m/s, 0.05 rad/s) 미만 |
| resume | `accepted` 이후 `patrol.update_count > patrol_update_count_at_call` **이고** `patrol.state == "patrolling"`. 속도로 판단하지 않음 |

### 3.3 왜 `update_count`로 비교하나

"명령 이후의 상태인지"를 알아야 하는데, 순찰 상태의 `stamp`는 로봇(시뮬레이션이면 시뮬레이션 시간) 시각이라 서버 시각과 비교할 수 없다(v1 원칙). 대신 Bridge가 세는 수신 횟수를 쓴다. 서비스 호출 직전 값보다 커졌으면 그 뒤에 온 상태다.

### 3.4 스냅샷에 추가 (`WS /api/v1/stream`, `GET /api/v1/state`)

```json
"command": {
  "request_id": "...", "command": "pause", "stage": "confirmed",
  "message": "pause accepted", "issued_at": "...Z", "updated_at": "...Z"
},
"patrol": { ...텔레메트리 patrol 그대로 + 서버 경과 시간... },
"pose": { ...텔레메트리 pose 그대로 + 서버 경과 시간... }
```

- `command`는 마지막 명령 하나만 (다음 명령 전까지 유지, PRD 그대로). 알림 목록에도 결과를 한 번 남김

---

## 4. 지도 (`GET /api/v1/map`, `GET /api/v1/map.png`)

- 서버 설정 `map_yaml`(예: `limbo/src/limbo_navigation/maps/aischool_2f_map.yaml`)을 시작할 때 읽어 pgm을 PNG로 바꿔 둔다
- `GET /api/v1/map` → `{"resolution": 0.05, "origin": [-12.842, -7.834, 0.0], "width": 492, "height": 471, "image": "/api/v1/map.png", "waypoints": [...]}`
- `waypoints`(이름·좌표·종류)는 서버 설정 `waypoints_yaml`에서 읽는다 (순찰 노드와 같은 파일)
- 나중에 약도로 바꾸면 `image`와 좌표 변환값만 바뀐다

---

## 5. Bridge 동작

| 작업 | 내용 |
|---|---|
| 텔레메트리 (기존) | v2로 `patrol`, `pose` 추가. 1초 주기·재시도 규칙 그대로 |
| 명령 (새로) | 별도 비동기 작업: `commands/next` long poll → 받으면 서비스 비동기 호출(제한 3초) → 결과 보고. 실패 시 1·2·4·8·10초 재시도는 **가져오기에만** 적용, 결과 보고는 한 번 (유실되면 서버가 `no_response`로 처리) |
| 구독 추가 | `/patrol/state` (reliable + transient_local, 순찰 노드와 맞춤), `/amcl_pose` |
| 서비스 대기 | 호출 전에 서비스가 없으면 기다리지 않고 바로 `service_unavailable` |

---

## 정할 것 (itkwon과)

| 항목 | 질문 | 제안 |
|---|---|---|
| 버전 | 텔레메트리를 v2로 올릴지, v1에 선택 필드로 넣을지 | v2 (v1은 모르는 필드를 거부하므로 선택 필드도 결국 호환 깨짐) |
| 명령 통로 | long poll vs 텔레메트리 응답에 싣기 | long poll (정지 지연·전송 실패 중 막힘) |
| 제한 시간 | 응답 5초 / 확인 5초 / 명령 유효 5초 / 서비스 3초 | 데모 값 그대로 시작, 실물에서 조정 |
| 인증 | 화면 → 서버 명령에 인증이 없으면 같은 네트워크 누구나 로봇을 멈출 수 있음 | 학원망에서만 쓰는 동안은 서버 `127.0.0.1` 또는 관제 PC만 허용, 실배치 전 따로 결정 |
| 재시작 버튼 | PRD의 프로그램 재시작 | 이번 범위에서 뺌 (`CONTROL_SCREEN.md`) |
| 담당 | Bridge·서버·화면 구현을 누가 | 계약 합의 후 나눔 |
