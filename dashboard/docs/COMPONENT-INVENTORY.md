# 관제 화면 컴포넌트 목록 (초안)

- 작성일: 2026-11-13
- 기준 코드: `dashboard/ui/src` (커밋 `9302659`)
- 문서 상태: **초안 · 현재 코드 분석**. 리팩터링 계획은 [UI-REFACTORING-PLAN.md](UI-REFACTORING-PLAN.md), 화면 동작 요구는 [UX-REQUIREMENTS.md](UX-REQUIREMENTS.md).

## 0. 읽는 법

- **재사용 가능 여부**: 지금 코드 그대로 다른 화면·Storybook에서 쓸 수 있는가.
  - 가능: props만 받고 다른 부품에 의존하지 않음
  - 분리 후 가능: 파일로 꺼내고 props를 정리하면 됨
  - 어려움: 데이터 처리·클래스 인스턴스·여러 상태가 얽혀 있음
- **리팩터링 난이도**: 하(옮기기만), 중(props·상태 정리 필요), 상(데이터 흐름 변경 필요).
- 줄 번호는 [App.tsx](../ui/src/App.tsx) 기준이다.

## 1. 요약 표

| 요청 분류 | 현재 컴포넌트 | 파일:줄 | Backend 의존 | 재사용 | 난이도 |
|---|---|---|---|---|---|
| Header | `RobotDashboard` 안 `<header>` JSX, `RobotPicker`, `AccountBar` | App.tsx:450, 292, 351 | `/robots`, `/auth/*`, `/users` | 분리 후 가능 | 중 |
| Connection Status | `overall()`, 헤더 `.connection`, 경고 `banner` | App.tsx:254, 450–451 | 스냅샷 `bridge`·`topics` + `serverProblem` | 분리 후 가능 | 중 (모델 확장 필요) |
| Robot Status | `PatrolCard`, 이동 카드(인라인) | App.tsx:177, 455–457 | 스냅샷 `patrol`·`motion` | 분리 후 가능 | 하~중 |
| Navigation Map | `MapCard` | App.tsx:189–238 | `/map`, `/map.png`, 스냅샷 `pose`·`patrol`·`robots` | 분리 후 가능 | 중 |
| Robot Controls | `Controls`, `ResultBox` | App.tsx:144–167, 39–51 | `/commands` (via `LiveControl`), 스냅샷 `command`·`launcher`·`patrol` | 어려움 | 상 |
| Waypoint List | `WaypointPanel` | App.tsx:56–143 | `/waypoints` GET·PUT (상위에서) | 어려움 | 상 |
| Event Logs | 최근 알림 카드(인라인), `AlertRow` | App.tsx:459, 281 | 스냅샷 `alerts` | 가능 (`AlertRow`) | 하 |
| Sensor Status | `Reception` | App.tsx:265–280 | 스냅샷 `topics`·`settings` | 분리 후 가능 | 하 |

공용 부품: `Badge`(App.tsx:27), `Card`(App.tsx:31) — 재사용 가능, 난이도 하. 단 export되지 않음.

---

## 2. 요청한 8개 컴포넌트 상세

### 2.1 Header

- **현재 구현**
  - `<header>` JSX: [App.tsx:450](../ui/src/App.tsx#L450) (`RobotDashboard` 반환값 안 한 줄)
  - [`RobotPicker`](../ui/src/App.tsx#L292) — 로봇 이름 버튼 + 목록(listbox), 화살표·Enter·Esc 키 처리, 바깥 클릭 닫기. **export됨.**
  - [`AccountBar`](../ui/src/App.tsx#L351) — 계정 이름, 회원 관리·비밀번호 변경·로그아웃 버튼, [`Users`](../ui/src/Users.tsx)·[`ChangePassword`](../ui/src/ChangePassword.tsx) 오버레이 열기
  - 데모일 때 `mode-tag`(데모 데이터)와 페이지 위 `demo-banner`
- **담당 기능**: 제품명, 현재 로봇 표시·전환, 전체 상태 요약(→ 2.2), 계정 메뉴.
- **Backend 의존성**
  - 로봇 목록은 스냅샷 `robots[]`(WebSocket)에서 받는다. `RobotApp`이 별도로 `GET /api/v1/robots`를 불러 저장된 로봇이 사라졌는지만 확인.
  - 로봇 전환 시 `?robot=`·`localStorage['limbo.robot']` 갱신 → `RobotDashboard`를 `key`로 통째 재생성(WebSocket 재연결).
  - 계정: `POST /auth/logout`, `PUT /auth/password`, `/users` CRUD.
- **재사용**: `RobotPicker`는 props만 받아 재사용 가능. 헤더 전체는 인라인 JSX라 분리 필요.
- **리팩터링 난이도**: 중. 헤더 줄 하나에 연결 요약·로봇 선택·계정이 모두 들어 있다. 999 px·699 px에서 줄바꿈 규칙이 CSS에 흩어져 있다.
- **분리안**: `AppHeader({ robot, robots, summary, account, demo })` → 자식 `RobotPicker`, `ConnectionIndicator`, `AccountMenu`.
- **E2E 의존**: `getByRole('button', { name: /로봇 선택/ })`, `.account`, `.account-name`, `getByRole('button', { name: '회원 관리' | '로그아웃' })`.

### 2.2 Connection Status

- **현재 구현**
  - [`overall(view)`](../ui/src/App.tsx#L254) — 정상 / 확인 필요 / 연결 끊김 한 줄 요약 + 사유 문구. **export됨.**
  - 헤더 `.connection`: 요약 배지 + "로봇 {연결됨|수신 지연|…} · 마지막 수신 HH:MM:SS · N초 전" ([App.tsx:450](../ui/src/App.tsx#L450))
  - 경고 띠 `banner` ([App.tsx:447–451](../ui/src/App.tsx#L447)): 서버 문제 / 로봇 끊김 / 로봇 지연 / 확인 중 문구
  - `AuthGate`의 "관제 서버에 연결할 수 없습니다. 5초마다 다시 시도" 화면 ([App.tsx:345](../ui/src/App.tsx#L345)) — 로그인 확인 단계 전용
- **담당 기능**: 3개 구간의 상태를 운영자에게 알림.
  - 브라우저↔서버: `view.serverProblem` (LiveProvider 판단)
  - 서버↔로봇(Bridge): `snapshot.bridge.status` = checking / connected / delayed / disconnected (서버 판단: 3초·10초)
  - 데이터(토픽): `snapshot.topics[*].status` (서버 판단)
- **Backend 의존성**: WebSocket `/api/v1/stream` 스냅샷, `settings.browser_delay_s`·`bridge_delay_s`·`bridge_disconnect_s`·`topic_delay_s`.
- **재사용**: `overall()`은 순수 함수라 재사용 가능. 표시 JSX는 분리 필요.
- **리팩터링 난이도**: 중. 표시 자체는 쉬우나, **브라우저↔서버 구간의 "끊김"(소켓 닫힘·재연결 중)과 "지연"(소켓은 열렸으나 3초 넘게 새 데이터 없음)을 구분하려면 `LiveProvider`가 내보내는 정보가 늘어야 한다** (계획 Phase 3). 현재는 둘 다 헤더에 "연결 끊김"으로 나온다.
- **분리안**: `ConnectionIndicator({ link, bridge, topicsSummary })` + `ConnectionBanner`. 상태 → 톤·문구 변환은 `status.ts` 순수 함수로.
- **E2E 의존**: `.connection`, `.overall`, `.last-received`, `.banner`, `getByRole('alert')`.

### 2.3 Robot Status

- **현재 구현**
  - [`PatrolCard`](../ui/src/App.tsx#L177) — 순찰 상태 배지(위치 확인 중·순찰 중·멈추는 중·일시정지·완료·실패, 이동 재시도), 다음 목표 `이름 (n/N)`, 보조 문구. 로봇 연결이 끊기면 "(마지막 상태)"로 회색 처리.
  - [`patrolLabel()`](../ui/src/App.tsx#L171) — 상태·사유 → 문구·톤. **export됨.**
  - 이동 카드 (인라인 JSX, [App.tsx:455–457](../ui/src/App.tsx#L455)) — 이동 중/정지 상태/확인 불가 배지, 회전 중, 선속도 m/s 큰 숫자, "마지막 수신 값" 표시, "멈춰 있다고 일시정지가 확인된 것은 아닙니다" 안내.
- **담당 기능**: 순찰 진행과 이동 여부를 한눈에.
- **Backend 의존성**: 스냅샷 `patrol`(v2 이상 Bridge), `motion.status/current/last_valid/rotating`, `bridge.status`.
- **재사용**: `PatrolCard`는 `view`만 받아 분리하면 재사용 가능. 이동 카드는 인라인이라 꺼내야 함.
- **리팩터링 난이도**: 하~중. 로직은 단순하나 "현재 값 / 마지막 값 / 모름" 세 갈래 표시 규칙을 지켜야 한다.
- **분리안**: `PatrolStatusCard({ patrol, bridgeStatus, serverProblem })`, `MotionCard({ motion, serverProblem })`. 공통으로 `FreshValue`(현재 값/마지막 값 표시) 부품.
- **E2E 의존**: `.patrol-state`, `.speed strong`.

### 2.4 Navigation Map

- **현재 구현**: [`MapCard`](../ui/src/App.tsx#L189) — SVG 하나. 좌표 함수는 [map.ts](../ui/src/map.ts).
  - 지도 그림(SLAM PGM → 서버가 PNG로 변환) 또는 빈 사각형(데모)
  - 경로 점선, waypoint(정지=□, 통과=○, 다음 목표 링, 지난 지점 흐림, 이름)
  - 내 로봇: 방향 화살표 + 위치 오차 원(2σ), 위치가 오래되면 흐림
  - 다른 로봇: 같은 지도일 때만, 누르면 그 로봇으로 전환(키보드 Enter·Space 지원)
  - "로봇 따라가기"(10 m 범위) / "전체 지도 보기" 토글
  - waypoint 편집 중: 클릭 좌표 → m 변환해 상위로 전달, 테두리 강조·안내 문구
  - 범례(다른 로봇·다음 목표·정지·통과), 위치 수신 상태 문구
- **담당 기능**: 로봇 위치·경로·목표를 지도 위에 표시, waypoint 위치 선택.
- **Backend 의존성**
  - `GET /api/v1/map?robot_id=` (메타 + waypoint + `image: "/api/v1/map.png"`) — 스냅샷 `map_available`이 참일 때 **한 번만** 부름 (`RobotDashboard`).
  - 스냅샷 `pose`(x, y, yaw, position_std_m, stale), `patrol.waypoint_index`, `robots[].pose`.
- **재사용**: `map`·`view`·콜백 props만 받으므로 파일 분리하면 재사용 가능. 다만 `view` 전체를 받는다 — 필요한 값만 받도록 줄이면 Storybook에 쓰기 쉽다.
- **리팩터링 난이도**: 중. 레이어 순서·`unit` 크기 계산·좌표 변환·클릭 이벤트 전파(`stopPropagation`)가 한 함수에 모여 있다. **실시간 LiDAR 스캔은 그리지 않는다**(지도는 고정 그림).
- **분리안**: `MapView`(SVG 틀·viewBox·클릭 변환) + 레이어 컴포넌트 `MapImageLayer`, `RouteLayer`, `WaypointLayer`, `RobotMarker`, `OtherRobotsLayer` + `MapLegend`, `MapToolbar`. 지도 데이터 로딩은 `useMapInfo()` 훅으로.
- **E2E 의존**: `.map-card svg`, `.map-card .waypoint`.

### 2.5 Robot Controls

- **현재 구현**
  - [`Controls`](../ui/src/App.tsx#L144) — 주 버튼 하나(상황에 따라 주행 시작 / 주행 정지 / 주행 재개), 순찰 종료 버튼, 잠금 사유 문구, 순찰 노드 비정상 종료 안내, 결과 상자, **그리고 waypoint 패널까지 포함**.
  - [`ResultBox`](../ui/src/App.tsx#L39) — 요청 결과 배지, 설명, 3단계(요청 전송·로봇 응답·상태 확인), 요청 시각·ID. 60초 지나면 접힘.
  - 판단 로직: [control.ts](../ui/src/control.ts) (`driveControl`, `lockReason`, `stopReason`, `waypointLocked`, `LiveControl`), [commands.ts](../ui/src/commands.ts) (문구, 데모 `CommandMachine`).
- **담당 기능**: 순찰 시작·일시정지·재개·종료 명령, 처리 단계 표시, 버튼 잠금.
- **Backend 의존성**
  - `POST /api/v1/commands { command, robot_id }` → 202 `request_id`. 이후 진행은 스냅샷 `command.stage`(queued → delivered → accepted → confirmed / rejected / expired / …)로 따라간다.
  - 스냅샷 `launcher`(v3 Bridge: 지원 명령·노드 상태·종료 코드), `patrol_running`, `patrol`.
  - 오류 코드별 문구(`command_in_progress`, `bridge_not_connected`, `bridge_unsupported` 등).
- **재사용**: 어려움. `demo: MockProvider | null`과 `live: LiveControl | null` 인스턴스를 직접 받고, waypoint 관련 props 8개를 그냥 통과시킨다.
- **리팩터링 난이도**: 상. 판단 로직은 이미 분리돼 있어 건드리지 않아도 되지만, 컴포넌트가 실제/데모 두 경로를 `if (demo)`로 나누고 있어 데이터 소스 추상화(계획 Phase 4)가 먼저다.
- **분리안**: `CommandPanel({ action, reason, stopReason, pending, onSend })` (표시 전용) + `useCommand(source, view)` 훅. `CommandResult`(=ResultBox) 독립. `WaypointPanel`은 형제 카드로 이동.
- **E2E 의존**: `.controls .command`, `.result`, `getByRole('button', { name: '주행 정지' | '주행 시작' | '순찰 종료' })`.
- **주의**: 성공(초록)은 서버 `confirmed`일 때만. 클릭·202 응답만으로 성공 표시 금지. 자동 재전송 금지.

### 2.6 Waypoint List

- **현재 구현**: [`WaypointPanel`](../ui/src/App.tsx#L56) (88줄, 상태 9개)
  - 목록(이름·종류·좌표), 이름 변경(인라인 입력, Enter·Esc), 위치 교체(지도 클릭), 삭제, 드래그 순서 변경(⋮⋮ 손잡이), 새 지점 만들기(이름·종류 + 지도 클릭)
  - 잠금 시 모든 버튼 비활성화 + `title`로 "주행 완료 후 변경 가능합니다"
  - **데모일 때 waypoint 변경 계산을 이 컴포넌트가 직접 한다** (77–82행)
  - 실제 저장은 상위 `RobotDashboard.changeWaypoint`([App.tsx:418](../ui/src/App.tsx#L418))가 `PUT`·409 처리
- **담당 기능**: 순찰 경로 편집.
- **Backend 의존성**: `GET /api/v1/waypoints` (`{ revision, waypoints, file, applies }`), `PUT /api/v1/waypoints` (`{ revision, action: add|move|delete|rename|reorder, ... }`), 오류 `revision_conflict`(409), `patrol_active`. 잠금 판단에 스냅샷 `patrol_running`.
- **재사용**: 어려움. 편집 모드·선택 좌표를 상위(지도와 공유)에서 props로 받고, 데모·실제 분기가 안에 있다.
- **리팩터링 난이도**: 상. 지도 카드와 편집 상태를 공유해야 하므로 `WaypointEditorContext`(모드·선택 좌표) 또는 상위 훅이 필요하다. 드래그 외 순서 변경 수단(↑/↓)도 추가 대상.
- **분리안**: `useWaypoints(source)`(문서·저장·충돌) + `useWaypointEditor()`(모드·선택 좌표, 지도와 공유) + 표시 부품 `WaypointList`, `WaypointRow`, `WaypointEditor`, `WaypointRenameForm`.
- **E2E 의존**: `getByRole('region', { name: 'Waypoint 목록' })`, `.waypoint-add`, `.waypoint-name`, 버튼 이름(`이름 변경`, `위치 교체`, `저장`, `새 지점 만들기`, `A 순서 끌어서 변경`), `getByLabel('이름')`.

### 2.7 Event Logs

- **현재 구현**: "최근 알림" 카드(인라인, [App.tsx:459](../ui/src/App.tsx#L459)) + [`AlertRow`](../ui/src/App.tsx#L281) (시각 · 심각도 배지 정보/주의/오류 · 문구 · "지속 중").
- **담당 기능**: 서버가 만든 문제·제어 이벤트 표시.
- **Backend 의존성**: 스냅샷 `alerts[]` (서버가 로봇별 최대 `alert_limit`=100건, 최신순, 매 스냅샷 전체 전송). 데모는 `MockProvider`가 생성.
- **재사용**: `AlertRow`는 props 하나라 바로 재사용 가능.
- **리팩터링 난이도**: 하. 필터(심각도·지속 중), 건수, 접기를 넣어도 화면 안에서 끝난다. 100건보다 오래된 기록 조회는 서버 API가 필요해 범위 밖.
- **분리안**: `EventLog({ alerts, filter })`, `EventLogItem`, `EventLogFilter`.
- **E2E 의존**: `.alert-row`.

### 2.8 Sensor Status

- **현재 구현**: [`Reception`](../ui/src/App.tsx#L265) — 접히는 `<details>` 카드 "센서 수신 상세(개발자용)". 표: 항목(주행 정보·LiDAR 원본·LiDAR 필터 결과·카메라 원본) × 수신 상태·마지막 수신·수신 빈도(Hz). 699 px 이하에서 카드형. 지연 기준 초 표시.
- **담당 기능**: 토픽 4종이 들어오는지 확인 (센서 정상 여부 판단은 아님 — 화면에 명시).
- **Backend 의존성**: 스냅샷 `topics[odom|lidar_raw|lidar_filtered|camera_raw]` (`status`, `age_s`, `last_received_at`, `receive_hz`, `last_receive_hz`, `received_count`), `settings.topic_delay_s`.
- **재사용**: `state`·`serverProblem`·`delta`만 받아 분리하면 재사용 가능.
- **리팩터링 난이도**: 하. 표의 반응형 CSS(`td::before` 라벨)만 함께 옮기면 된다.
- **분리안**: `SensorStatusTable({ topics, settings, linkOk })`, 행 `SensorRow`. 헤더 요약용 `SensorSummary`(n/4 수신 중) 추가 가능.
- **E2E 의존**: `details.reception table`, `tbody`.

---

## 3. 그 밖의 컴포넌트

| 컴포넌트 | 파일:줄 | 역할 | Backend | 재사용 | 난이도 |
|---|---|---|---|---|---|
| `Badge` | App.tsx:27 | 상태 → 톤(good/warn/bad/neutral)·기호·문구 | — | 가능 | 하 |
| `Card` | App.tsx:31 | 제목 있는 `section` | — | 가능 | 하 |
| `DemoTools` | App.tsx:239 | 데모 시나리오·Bridge 버전·순찰 상태·명령 결과·제한 시간 조절 | — (MockProvider) | 분리 후 가능 | 하 |
| `AuthGate` | App.tsx:327 | 로그인 상태 확인·전이 | `/auth/me` | 화면 고유 | 중 (규칙 유지 필수) |
| `RobotApp` | App.tsx:364 | 로봇 선택 저장·복원, 대시보드 재생성 | `/robots` | 화면 고유 | 하 |
| `RobotDashboard` | App.tsx:385 | Provider·지도·waypoint·명령 상태 소유, 레이아웃 | `/map`, `/waypoints`, WS | 어려움 | 상 (분해 대상) |
| `Login` | Login.tsx | 로그인 폼 | `/auth/login` | 가능 | 하 |
| `ChangePassword` | ChangePassword.tsx | 강제/일반 비밀번호 변경, 일반은 오버레이 | `/auth/password` | 가능 | 하 (Dialog 교체 시 중) |
| `Users` | Users.tsx | 회원 목록·추가·초기화·중지·삭제 (오버레이) | `/users` | 가능 | 중 (Dialog 교체) |
| page-meta · footer | App.tsx:453, 461 | 화면 설명, 데모/실제 전환 링크, 시간대 표시 | — | 분리 후 가능 | 하 |

---

## 4. 로직 모듈 (리팩터링 대상 아님)

| 모듈 | 내용 | 비고 |
|---|---|---|
| [live.ts](../ui/src/live.ts) | `LiveProvider`, `robotQuery`, `backoff` | Phase 3에서 링크 상태 **추가 출력**만 |
| [control.ts](../ui/src/control.ts) | 명령 단계 변환, 잠금 사유, `LiveControl` | 변경 금지 |
| [commands.ts](../ui/src/commands.ts) | 명령 문구, 데모 `CommandMachine` | 변경 금지 |
| [demo.ts](../ui/src/demo.ts) | `MockProvider`, `demoMap`, 시나리오 | Phase 4에서 확장 |
| [map.ts](../ui/src/map.ts) | 좌표 변환 | 변경 금지 |
| [auth.ts](../ui/src/auth.ts) | `api()` 래퍼, 인증·회원 API | 변경 금지 |
| [types.ts](../ui/src/types.ts) | 서버 스냅샷 타입 | 서버 계약과 같아야 함, 필드 추가만 |

---

## 5. 공용 부품 후보 (디자인 시스템 1차 목록)

DESIGN.md·Storybook의 첫 대상. 모두 표현 전용(props만)으로 만든다.

| 부품 | 대체할 현재 코드 | 변형(variant) |
|---|---|---|
| `StatusBadge` | `Badge` | tone: good·warn·bad·neutral · size: sm·md·lg(순찰/이동 카드의 큰 배지) |
| `Card` / `CardHeader` | `Card`, `.summary .card` | default · summary(작은 제목) · collapsible(`details`) |
| `Button` | 전역 `button`, `.command.pause/.resume`, `.patrol-stop`, `.primary`, `.danger`, `.link` | primary · danger · outline-accent · ghost · link, size, busy |
| `DisabledReason` | `span[title]`으로 감싼 비활성 버튼 | 툴팁 + 화면에 사유 문구(터치 대응) |
| `FreshValue` | 이동 카드·위치 문구의 "N초 전 / 마지막 값" | live · stale · unknown |
| `ConnectionIndicator` | 헤더 `.connection` | 구간 3개(브라우저↔서버·서버↔로봇·센서) |
| `Banner` | `.banner`, `.demo-banner` | info · warn · danger · demo |
| `StepProgress` | `ResultBox`의 `.steps` | 단계별 waiting·running·done·failed·unknown |
| `Field` (Label + Input/Select) | 로그인·waypoint·회원 관리 폼 | invalid, hint |
| `Dialog` | `.overlay` (Users, ChangePassword) | 포커스 가두기·복귀·Esc |
| `Icon` | 유니코드 기호 | Lucide 래퍼, `aria-hidden` 기본 |

---

## 6. 목표 디렉터리 구조 (제안)

```text
ui/src/
├─ main.tsx
├─ App.tsx                     라우팅(/, /demo)과 AuthGate만
├─ styles/
│  ├─ tokens.css               디자인 토큰 (단일 기준)
│  └─ base.css                 기존 style.css를 정리해 옮김
├─ lib/                        ← 지금의 로직 파일 (이동만, 내용 변경 없음)
│  ├─ live.ts  control.ts  commands.ts  demo.ts  map.ts  auth.ts  types.ts
│  ├─ format.ts                ageText, timeText
│  └─ status.ts                overall, patrolLabel, 연결 상태 → 톤·문구
├─ data/
│  ├─ source.ts                DashboardSource 인터페이스
│  ├─ liveSource.ts  mockSource.ts
│  ├─ fixtures/                시나리오별 Snapshot (Storybook·테스트 공용)
│  └─ hooks.ts                 useView, useCommand, useNow, useMapInfo, useWaypoints
├─ components/                 공용 부품 (5장)
│  └─ StatusBadge.tsx  Card.tsx  Button.tsx  Dialog.tsx  …
├─ features/
│  ├─ header/        AppHeader, RobotPicker, AccountMenu, ConnectionIndicator
│  ├─ status/        PatrolStatusCard, MotionCard
│  ├─ map/           MapView, layers/*, MapLegend
│  ├─ control/       CommandPanel, CommandResult
│  ├─ waypoints/     WaypointPanel, WaypointRow, WaypointEditor
│  ├─ events/        EventLog, EventLogItem
│  ├─ sensors/       SensorStatusTable
│  ├─ demo/          DemoTools
│  └─ auth/          Login, ChangePassword, Users
└─ pages/
   └─ Dashboard.tsx            지금의 RobotDashboard (레이아웃 + 데이터 연결)
```

`lib/`로 옮길 때 import 경로만 바뀌고 내용은 그대로여야 한다 (git `--find-renames`로 확인).
