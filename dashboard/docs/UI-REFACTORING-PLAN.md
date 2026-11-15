# 관제 화면 UI 리팩터링 계획 (초안)

- 작성일: 2026-11-13
- 대상: `dashboard/ui` (React 19 · TypeScript 5.8 · Vite 6 · pnpm 10)
- 문서 상태: **초안 · 분석 결과와 제안**. 이 문서를 쓰는 동안 소스코드와 의존성은 바꾸지 않았다.
- 함께 보는 문서: [COMPONENT-INVENTORY.md](COMPONENT-INVENTORY.md) (컴포넌트 목록), [UX-REQUIREMENTS.md](UX-REQUIREMENTS.md) (화면이 지켜야 할 동작), [PRD.md](PRD.md), [../../docs/CONTROL_SCREEN.md](../../docs/CONTROL_SCREEN.md)

## 0. 요약

- 화면 코드는 약 1,500줄로 작지만 **관제 화면 전체가 [App.tsx](../ui/src/App.tsx) 한 파일(464줄, 한 줄이 매우 긴 형식)** 에 들어 있다. 스타일도 **[style.css](../ui/src/style.css) 한 파일**이며 색은 모두 hex 값을 직접 쓴다.
- 반면 **상태 판단 로직은 이미 잘 나뉘어 있다**: 실시간 수신(`live.ts`), 명령 단계(`control.ts`·`commands.ts`), 인증(`auth.ts`), 좌표 변환(`map.ts`), 가상 데이터(`demo.ts`). 이 파일들은 단위 테스트가 있고 리팩터링 대상이 아니다.
- `/demo`에 **Mock 데이터 공급자(`MockProvider`)와 시나리오 도구가 이미 있다.** 지도·waypoint가 Provider를 거치지 않는 점만 보완하면 "로봇 없이 UI 시험" 요구를 채울 수 있다.
- 가장 큰 UX 공백은 **브라우저↔서버 구간에서 "연결 끊김"과 "수신 지연"을 구분하지 못하는 것**이다. 지금은 둘 다 `serverProblem: true` 하나로 합쳐진다 (§2.3).
- 권장 순서: **디자인 토큰(CSS 변수) → 컴포넌트 파일 분리 → 연결 상태 모델 → Mock 확장 → Lucide 아이콘 → Storybook → (선택) Tailwind·shadcn/ui**. Tailwind·shadcn/ui는 현재 CSS·e2e 셀렉터와 충돌 지점이 있어 마지막에 판단한다.

---

## 1. 현재 프런트엔드 구조

### 1.1 파일 구성

| 파일 | 줄 | 역할 | 테스트 |
|---|---:|---|---|
| [main.tsx](../ui/src/main.tsx) | 4 | 진입점, `style.css` 로드 | — |
| [App.tsx](../ui/src/App.tsx) | 464 | 인증 게이트, 관제 화면 전체(헤더·카드·지도·제어·waypoint·알림·센서 표·데모 도구) | e2e |
| [types.ts](../ui/src/types.ts) | 35 | 서버 스냅샷 타입(`Snapshot`, `View`, `Provider`) | — |
| [live.ts](../ui/src/live.ts) | 92 | `LiveProvider`: WebSocket 수신, 재연결, 지연 감시, 탭 복귀 재조회 | `live.test.ts` |
| [control.ts](../ui/src/control.ts) | 135 | `LiveControl`: 명령 전송·서버 단계→화면 3단계, 버튼 잠금 사유 | `control.test.ts` |
| [commands.ts](../ui/src/commands.ts) | 77 | 명령 이름·결과 문구, 데모용 `CommandMachine` | `commands.test.ts` |
| [demo.ts](../ui/src/demo.ts) | 133 | `MockProvider`: 가상 로봇(시나리오·순찰 이동·명령 결과) | e2e |
| [map.ts](../ui/src/map.ts) | 21 | ROS 지도 좌표 ↔ 그림 픽셀 변환 | — |
| [auth.ts](../ui/src/auth.ts) | 83 | 세션 로그인 API, `api()` fetch 래퍼(401·403 감지), 회원 API | `auth.test.ts` |
| [Login.tsx](../ui/src/Login.tsx) · [ChangePassword.tsx](../ui/src/ChangePassword.tsx) · [Users.tsx](../ui/src/Users.tsx) | 155 | 로그인, 비밀번호 변경, 회원 관리 | e2e (`login.spec.ts`) |
| [style.css](../ui/src/style.css) | 55 | 전체 스타일 (1행이 압축된 기본 스타일, 이후 패치가 덧붙음) | — |

의존성은 `react`·`react-dom` 둘뿐이다. 라우터·상태 관리 라이브러리·UI 키트·아이콘 라이브러리가 없다.

### 1.2 React 컴포넌트 구조

```text
App                                   pathname === '/demo' 이면 인증 생략
├─ AuthGate                           checking / unreachable / 로그인 / 비번 강제 변경 / 관제
│  ├─ Login
│  ├─ ChangePassword (forced)
│  └─ RobotApp                        로봇 선택(?robot= · localStorage) → key={robotId}로 통째 재생성
│     └─ RobotDashboard               Provider·LiveControl·지도·waypoint 문서 상태를 모두 소유
│        ├─ (데모 배너)
│        ├─ header
│        │  ├─ RobotPicker            로봇 목록 드롭다운
│        │  ├─ 연결 요약 (overall + Badge + 마지막 수신)
│        │  └─ AccountBar → Users · ChangePassword (오버레이)
│        ├─ banner                    연결 상태 경고 띠
│        ├─ DemoTools                 /demo 전용 시나리오 도구
│        └─ main
│           ├─ summary: PatrolCard · 이동 카드(인라인 JSX)
│           ├─ body-grid: MapCard · Controls → ResultBox · WaypointPanel
│           ├─ 최근 알림 카드 → AlertRow
│           ├─ Reception (센서 수신 상세, <details>)
│           └─ footer
```

특징과 문제:

- **공용 컴포넌트가 `Badge`·`Card` 둘뿐이고 export되지 않는다.** 버튼·입력·표·오버레이는 매번 JSX와 CSS 클래스로 직접 만든다.
- **props 전달이 깊다.** `Controls`는 12개 props를 받아 그중 8개를 `WaypointPanel`에 그대로 넘긴다. waypoint 목록이 "로봇 제어" 카드 안에 들어 있어서다.
- **화면과 데이터 처리가 섞여 있다.** waypoint 저장 API 호출·409 충돌 재조회는 `RobotDashboard`에, 데모 waypoint 변경 로직은 `WaypointPanel` 안에 있다.
- **"지금 시각" 타이머(200 ms)가 `RobotDashboard` 전체를 초당 5회 다시 그린다.** "N초 전" 표시 때문이다. 지금 규모에서는 문제없지만 컴포넌트가 늘면 비용이 커진다.
- 라우팅은 `location.pathname` 비교 두 곳(`/`, `/demo`)뿐이다. 서버도 이 두 경로만 `index.html`로 응답한다 ([server/app.py:721](../server/app.py#L721)).

### 1.3 CSS 및 스타일링

- 전역 CSS 한 파일. 1행에 기본 스타일 전체가 압축돼 있고, 2~55행은 waypoint·로그인 기능을 붙이며 덧댄 규칙이다. 같은 셀렉터가 여러 번 재정의된다 (예: `.waypoint-list li`가 9·29·38행, `.waypoint-drag`가 27·36행).
- 색은 hex 직접 사용, 약 25종. 의미별로 묶으면 아래와 같다 (토큰 후보, §3.1).

| 의미 | 값 | 쓰는 곳 |
|---|---|---|
| 기본 잉크(남색) | `#17264a` | 제목·카드 윗선·헤더 밑선·버튼 글자·지도 경로 |
| 본문 | `#2b3445` | `:root` color |
| 보조 글자 | `#5b6576` | `.muted`, `small`, 표 머리 |
| 강조(청록) | `#0b7a80` | 링크·포커스 링·다음 목표·재개 버튼 |
| 위험(빨강) | `#c42b2b` / `#a32323` | 정지 버튼·로봇 표시·끊김 배너 |
| 상태 good/warn/bad/neutral | `#1d7a43`·`#a65300`·`#c42b2b`·`#5f6878` (+배경·테두리) | `.badge.*` |
| 배경·테두리 | `#eef0f3`·`#fff`·`#d7dbe2`·`#e3e6eb`·`#8c95a4` | 페이지·카드·구분선 |

- 디자인 언어: **모서리 0(각진 카드), 2px 남색 윗선, 그림자 거의 없음, 숫자 tabular-nums.** 정보 밀도가 높은 산업용 관제 화면 스타일이다.
- 글꼴: `Archivo, "Noto Sans KR", system-ui`로 지정했지만 **글꼴 파일을 불러오지 않는다**. 실제로는 사용자 PC에 설치된 글꼴로 보인다.
- 반응형: 1200 / 999 / 699 px 세 구간. 999 px 이하에서 `display: contents`와 `order`로 제어 카드를 위로 올린다. 699 px 이하에서 표를 카드형으로 바꾼다 (`td::before { content: attr(data-label) }`).
- 다크 모드 없음. `prefers-reduced-motion` 대응 있음. 아이콘은 유니코드 문자(●, !, ○, ■, ▷, ⋮⋮, ▾, ▸).

### 1.4 UI 상태 관리

외부 라이브러리 없이 세 가지 방식이 섞여 있다.

| 상태 | 위치 | 방식 |
|---|---|---|
| 로그인 상태 | `AuthGate` | `useState` + `onAuthLost` 구독(전역 Set) |
| 선택한 로봇 | `RobotApp` | `useState` + URL `?robot=` + `localStorage['limbo.robot']` |
| 실시간 스냅샷 | `LiveProvider`/`MockProvider` (클래스) → `RobotDashboard` | `subscribe(setView)` — 외부 저장소 패턴 |
| 진행 중 명령 | `LiveControl` (클래스) | 내부 필드 + `useReducer` 강제 리렌더(`redraw`) |
| 지도·waypoint 문서 | `RobotDashboard` | `useState` + `useEffect` fetch |
| waypoint 편집 모드·선택 좌표 | `RobotDashboard` → `Controls` → `WaypointPanel`, `MapCard` | props 전달 |
| 패널 내부(이름 입력, 드래그 등) | 각 컴포넌트 | `useState` |

평가: 클래스 기반 Provider·Control은 **React와 무관하게 테스트할 수 있다는 장점**이 있어 유지할 가치가 있다. 다만 React 쪽 연결은 `useSyncExternalStore` 훅(`useView`, `useCommand`)으로 감싸는 편이 명확하다. 전역 상태 라이브러리(Redux·Zustand 등)는 필요하지 않다.

### 1.5 Backend API 통신

모든 요청은 같은 출처(`/api/v1/...`)로 가며, 개발 시에는 Vite가 `127.0.0.1:8000`으로 프록시한다 ([vite.config.ts](../ui/vite.config.ts)). 브라우저 API는 **세션 쿠키(HttpOnly)** 로 인증한다. 화면은 토큰을 다루지 않는다.

| 기능 | 메서드·경로 | 호출 위치 | 비고 |
|---|---|---|---|
| 로그인 상태 | `GET /api/v1/auth/me` | `auth.me()` | 401이면 로그인 필요 |
| 로그인·로그아웃 | `POST /api/v1/auth/login` · `/logout` | `auth.ts` | |
| 비밀번호 변경 | `PUT /api/v1/auth/password` | `auth.ts` | 403(wrong_password)을 로그아웃으로 보지 않게 `fetch` 직접 사용 |
| 회원 관리 | `GET·POST /api/v1/users`, `PATCH·DELETE /api/v1/users/{id}` | `auth.users` | |
| 스냅샷 1회 조회 | `GET /api/v1/state?robot_id=` | `LiveProvider.refresh` | 탭 복귀 시, 3초 제한 |
| 실시간 입장표 | `POST /api/v1/stream-ticket` | `LiveProvider.connect` | 30초·1회용 (iPhone Safari 대응) |
| 실시간 스트림 | `WS /api/v1/stream?robot_id=&ticket=` | `LiveProvider` | |
| 로봇 목록 | `GET /api/v1/robots` | `RobotApp` | 저장된 로봇이 사라졌는지만 확인 |
| 명령 | `POST /api/v1/commands` | `LiveControl.send` | 202 + `request_id`, 5초 제한, **자동 재전송 없음** |
| 지도 | `GET /api/v1/map?robot_id=` → `GET /api/v1/map.png` | `RobotDashboard` | 스냅샷의 `map_available`이 참일 때 1회 |
| Waypoint | `GET·PUT /api/v1/waypoints?robot_id=` | `RobotDashboard` | `revision` 낙관적 동시성, 409 시 재조회 |

`api()` 래퍼([auth.ts:13](../ui/src/auth.ts#L13))는 401·403을 받으면 `onAuthLost` 구독자를 깨워 로그인 화면으로 돌려보낸다. **이 래퍼는 리팩터링 뒤에도 모든 인증 API 호출의 유일한 통로여야 한다.**

로봇(Bridge)용 경로(`/api/v1/telemetry`, `/commands/next`, `/claim`, `/result`)는 화면이 쓰지 않는다.

### 1.6 WebSocket과 실시간 데이터 처리

[live.ts](../ui/src/live.ts)의 `LiveProvider` 동작:

1. `POST /stream-ticket`으로 입장표를 받고 `WS /stream`에 연결한다. 서버는 연결 즉시 현재 스냅샷을 보내고, 이후 로봇 텔레메트리를 받을 때마다 **전체 스냅샷**을 보낸다. 서버 대기열은 1개라 느린 브라우저는 최신 것만 받는다.
2. 받은 스냅샷 검증: 필수 필드, 다른 `robot_id` 버림, 같은 `server_run_id`에서 `revision`이 줄면 버림.
3. **지연 감시(200 ms 간격):** 마지막 수신 후 `settings.browser_delay_s`(기본 3초)가 지나면 `serverProblem = true`로 바꾸고 소켓을 닫는다.
4. **재연결:** 소켓이 닫히면 `serverProblem = true`, 1·2·4·8·10초 백오프로 재시도. 스냅샷을 받으면 시도 횟수 초기화.
5. **탭 복귀:** `visibilitychange`에서 먼저 `serverProblem = true`(예전 값을 지금 값으로 보이지 않게), 그 뒤 `GET /state`로 다시 받는다.
6. 화면 쪽 `delta`(`performance.now()` - 수신 시각)를 서버가 준 `age_s`에 더해 "N초 전"을 계속 늘린다.

관찰한 한계:

- 3번(데이터가 늦음)과 4번(연결이 끊김)이 **같은 `serverProblem` 하나**로 표현되어 화면이 구분하지 못한다. 재연결 시도 횟수·다음 시도 시각도 화면에 나오지 않는다.
- 서버가 보내는 종료 코드 `4401`(세션 끝남)·`4404`(모르는 로봇)를 읽지 않는다. 4401은 다음 입장표 요청의 401로 간접 처리되지만, 4404는 끝없이 재연결한다.
- `navigator.onLine`(브라우저 자체 오프라인)을 보지 않는다.

서버↔로봇 구간과 토픽 구간은 **서버가 판정해서 스냅샷에 넣어 준다** (`bridge.status`: checking/connected/delayed(3초)/disconnected(10초), `topics[*].status`: receiving/delayed/never_received/unknown). 화면은 이 값을 해석만 한다.

### 1.7 지도 렌더링 ("LiDAR 지도")

- 지도는 **SLAM으로 미리 만든 점유 격자(PGM)** 다. 서버가 시작할 때 한 번 읽어 PNG로 바꾸고 메타데이터(`resolution`, `origin`, `width`, `height`)와 함께 준다 ([server/mapdata.py](../server/mapdata.py)). **실시간 LiDAR 스캔 점은 그리지 않는다** (PRD 제외 범위).
- [MapCard](../ui/src/App.tsx#L189)는 SVG 한 장에 PNG(`<image>`, `image-rendering: pixelated`)를 깔고 그 위에 경로(점선 polyline), waypoint(정지=사각, 통과=원, 다음 목표 링, 지난 지점 흐림), 내 로봇(화살표 + 위치 오차 원 2σ), 같은 지도를 쓰는 다른 로봇(누르면 그 로봇으로 전환)을 그린다.
- 좌표 변환은 [map.ts](../ui/src/map.ts)의 `toPixel`·`fromPixel`·`headingDeg`·`uncertaintyPx`가 맡는다 (ROS y축 위 ↔ SVG y축 아래).
- 확대: "로봇 따라가기"(로봇 중심 10 m 사각형으로 viewBox 변경)만 있다. 마우스 휠·핀치 확대, 이동은 없다. 표시 크기 단위(`unit`)를 보이는 범위에 맞춰 확대해도 글자 크기가 일정하다.
- waypoint 편집 중에는 지도 클릭이 좌표 선택이 된다 (`getScreenCTM().inverse()`로 픽셀 → m 변환). 이때 다른 로봇 클릭은 막는다.
- 데모 지도는 그림 없이(`image: null`) 회색 바탕에 waypoint만 그린다.

### 1.8 Waypoint 관리

- 목록·추가·위치 교체·이름 변경·삭제·드래그 순서 변경 ([WaypointPanel](../ui/src/App.tsx#L56)).
- 저장은 `PUT /api/v1/waypoints`에 `{ revision, action, ... }`. 서버가 YAML 파일에 쓴다. **다음 순찰 시작 때 적용**된다.
- 규칙(화면 검사): 이름 1~32자·대소문자 무시 중복 금지, 마지막 지점은 정지 지점, 마지막 정지 지점 삭제 불가(실제 모드).
- 잠금: 순찰 노드가 돌고 있으면(`patrol_running`, 없으면 순찰 상태로 판단) 또는 시작·종료 명령 처리 중이면 편집 전체를 잠근다 ([control.ts:130](../ui/src/control.ts#L130)).
- 오류 처리: 409 `revision_conflict` → 최신 목록 재조회 후 안내, `patrol_active` → 잠금 안내.
- 순서 변경은 **HTML5 드래그 앤 드롭만** 지원한다. 휴대폰 터치에서는 동작이 불안정하고 키보드로는 할 수 없다 (UX 공백).

### 1.9 이벤트 로그(알림) 표시

- 서버가 로봇별로 최근 알림 최대 100건(`alert_limit`)을 최신순으로 보관하고 스냅샷마다 전체 목록을 보낸다. 각 항목: `id, key, at, severity(info/warning/error), message, kind(problem/control 등), active`.
- 화면은 "최근 알림" 카드에 **전부 그대로** 나열한다 (시각 · 심각도 배지 · 문구 · "지속 중"). 필터·검색·페이지·건수 표시·접기가 없다.
- 명령 결과는 알림과 별도로 제어 카드의 `ResultBox`(3단계 진행 표시)에 나온다. 60초가 지나면 한 줄로 접힌다.
- 데모 알림은 `MockProvider`가 직접 만든다.

### 1.10 테스트

- 단위(Vitest): `auth`·`commands`·`control`·`live` — 로직만 시험하고 화면은 시험하지 않는다.
- E2E(Playwright): `dashboard.spec.ts` 17건(주로 `/demo`), `login.spec.ts` 2건(로그인 켠 서버). 실제 FastAPI 서버를 8017·8018 포트로 띄운다.
- **E2E가 CSS 클래스에 의존한다** (`.result`, `.connection`, `.overall`, `.patrol-state`, `.controls .command`, `.map-card svg`, `.map-card .waypoint`, `.alert-row`, `.speed strong`, `.waypoint-add`, `.waypoint-name`, `.account`, `.account-name`, `.last-received`, `.banner`, `.auth-notice`, `.user-list li`, `details.reception table` 등). 클래스 이름을 바꾸면 E2E가 깨진다 → Phase 0에서 먼저 정리한다.

---

## 2. 리팩터링 전에 고칠 구조 문제

| # | 문제 | 영향 | 해결 단계 |
|---|---|---|---|
| 2.1 | `App.tsx` 한 파일에 화면 전체, 컴포넌트 비공개 | 부분 교체·Storybook·AI 생성 코드 적용이 어려움 | Phase 2 |
| 2.2 | 색·간격·글꼴 크기가 CSS 곳곳에 직접 값 | 디자인 변경 시 전수 수정, DESIGN.md와 연결 불가 | Phase 1 |
| 2.3 | 브라우저↔서버 "끊김"과 "지연"이 `serverProblem` 하나 | 운영자가 재연결 중인지, 잠깐 늦은 건지 모름 | Phase 3 |
| 2.4 | 지도·waypoint가 Provider 밖에서 직접 fetch | Mock 모드에서 지도 그림·waypoint 저장 흐름 시험 불가, 데모 로직이 UI에 섞임 | Phase 4 |
| 2.5 | E2E가 CSS 클래스에 의존 | 스타일 정리만 해도 시험이 깨짐 | Phase 0 |
| 2.6 | 오버레이(회원 관리·비밀번호)에 포커스 가두기 없음, 드롭다운 직접 구현 | 키보드·스크린리더 사용성 | Phase 6 |
| 2.7 | waypoint 순서 변경이 마우스 드래그 전용 | 휴대폰·키보드에서 순서 변경 불가 | Phase 5 |

---

## 3. 디자인 시스템 도입 검토

### 3.1 한눈에 보기

| 기술 | 적합성 | 충돌 위험 | 권고 | 시점 |
|---|---|---|---|---|
| CSS Design Tokens (CSS 변수) | 높음 | 거의 없음 | **도입** | Phase 1 |
| Lucide React | 높음 | 낮음 | **도입** | Phase 5 |
| Storybook | 중~높음 | 중간 (의존성 다수, 컴포넌트 분리 선행 필요) | **도입** (개발 전용) | Phase 6 |
| Tailwind CSS v4 | 중간 | 중간~높음 (`preflight`, `.container`, 기존 전역 규칙) | 보류 후 판단 | Phase 7 (선택) |
| shadcn/ui | 중간 | 높음 (Tailwind 필수, 둥근 기본 스타일, 경로 별칭) | 일부 부품만 선택적으로 | Phase 7 (선택) |

### 3.2 CSS Design Tokens

- **적합 이유:** 의존성 추가 없이 `:root`의 CSS 변수로 색·간격·글꼴·모서리·그림자를 이름 붙여 정의한다. SVG 지도의 `fill`·`stroke`도 CSS에서 지정하므로 토큰을 그대로 쓸 수 있다. DESIGN.md·Stitch·Tailwind·shadcn/ui가 모두 이 변수를 공통 기준으로 쓸 수 있어 **이후 어떤 선택을 하든 먼저 해 두면 이득**이다.
- **구성안:** 원시 토큰(`--color-navy-900`) → 의미 토큰(`--color-ink`, `--color-accent`, `--color-status-good-fg/bg/border`, `--color-map-route`) → 컴포넌트는 의미 토큰만 사용. 상태 4톤(good/warn/bad/neutral)과 연결 상태(§UX 3장)를 토큰으로 고정한다.
- **파일:** `ui/src/styles/tokens.css`(변수만), 기존 `style.css`는 값을 변수로 바꾸기만 한다. 다크 모드는 토큰 값만 바꾸면 되도록 구조를 잡되, 도입 여부는 열린 결정(§8).
- **충돌:** 없음. 화면 결과가 픽셀 단위로 같아야 한다 (Playwright 스크린샷 비교로 확인).

### 3.3 Tailwind CSS (v4)

- **장점:** AI 도구(Google Stitch 포함)가 내보내는 코드가 대개 Tailwind HTML이라 옮겨 붙이기 쉽다. `@theme`에 위 토큰을 연결하면 유틸리티 클래스가 같은 값을 쓴다.
- **충돌 지점:**
  - `preflight`(기본 스타일 초기화)가 기존 전역 규칙(`button{border:1px solid …}`, `h1,h2,p{margin:0}`, `small{display:block}`)과 겹친다. 순서·우선순위에 따라 지금 화면이 바뀐다.
  - 기존 클래스 `.container`가 Tailwind의 `container` 유틸리티와 이름이 같다.
  - E2E가 의미 있는 클래스 이름(`.result` 등)에 의존하는데, Tailwind 방식은 클래스가 유틸리티 나열로 바뀐다.
  - 새 의존성 `tailwindcss`, `@tailwindcss/vite`. Docker 빌드(node 24, `pnpm install --frozen-lockfile`)에는 문제없으나 lockfile 갱신이 필요하다.
- **판단:** 토큰·컴포넌트 분리가 끝난 뒤, 새로 만드는 컴포넌트부터 Tailwind를 쓰고 **`preflight`를 끈 상태로** 공존시키는 방식만 고려한다. 기존 CSS를 한 번에 옮기지 않는다. Stitch 결과를 쓰지 않는다면 도입하지 않아도 된다.

### 3.4 shadcn/ui

- **성격:** 라이브러리가 아니라 Radix UI 기반 컴포넌트 소스를 프로젝트에 복사해 넣는 방식이다. Tailwind가 전제다.
- **얻는 것:** `Dialog`(포커스 가두기·Esc·스크롤 잠금 — 회원 관리·비밀번호 변경 오버레이), `DropdownMenu`/`Select`(로봇 선택), `Tooltip`(잠긴 버튼 사유 — 지금은 `title` 속성), `Collapsible`(센서 수신 상세), `Sonner`(토스트) 등 접근성이 검증된 부품.
- **충돌 지점:**
  - Tailwind 필수 (§3.3의 충돌을 모두 안고 들어옴).
  - `@/` 경로 별칭, `components.json`, `class-variance-authority`·`clsx`·`tailwind-merge`·`@radix-ui/*` 다수 추가.
  - 기본 디자인(둥근 모서리, 옅은 그림자)이 현재 각진 관제 스타일과 다르다. `--radius: 0`과 토큰 덮어쓰기로 맞춰야 한다.
  - Radix가 만드는 DOM 구조·role이 지금과 달라 E2E의 role 기반 셀렉터(`getByRole('dialog')`, `getByRole('button', { name: /로봇 선택/ })`)를 다시 확인해야 한다.
- **판단:** Tailwind를 도입하기로 한 경우에만, **Dialog·DropdownMenu·Tooltip 같은 상호작용 부품만** 골라 쓴다. 상태 배지·카드·지도처럼 도메인 의미가 큰 부품은 직접 만든다. Tailwind 없이 같은 효과를 원하면 `@radix-ui/react-dialog` 등 Radix 단품을 직접 쓰는 대안이 있다.

### 3.5 Lucide React

- **적합 이유:** 아이콘만 개별 import(tree-shaking)하므로 번들 증가가 작다. 유니코드 기호(●, !, ■, ▷, ⋮⋮, ▾)를 일관된 선 아이콘으로 바꾸고, 연결 상태 아이콘(Wifi/WifiOff/Clock/RefreshCw 계열)으로 끊김과 지연을 모양으로도 구분할 수 있다(색만으로 구분하지 않기).
- **충돌:** 거의 없음. 주의점 두 가지.
  - 아이콘은 `aria-hidden`으로 두고 **버튼 접근성 이름(텍스트)을 바꾸지 않는다.** E2E가 `getByRole('button', { name: '주행 정지', exact: true })`처럼 정확한 이름을 찾는다.
  - 상태 배지의 기호는 색맹 대응용 보조 표시이므로, 아이콘으로 바꿔도 톤별로 모양이 달라야 한다.

### 3.6 Storybook

- **적합 이유:** 로봇·서버 없이 컴포넌트를 상태별로 보는 작업대. `demo.ts`의 시나리오를 스토리 고정 데이터(fixture)로 재사용할 수 있다. Stitch/DESIGN.md로 만든 디자인을 컴포넌트 단위로 대조하는 데 유용하다.
- **선행 조건:** 컴포넌트가 파일로 나뉘고 **props만으로 그려지는(표현용) 형태**여야 한다. 지금의 `Controls`처럼 `LiveControl` 인스턴스를 받는 컴포넌트는 그대로는 스토리로 만들기 어렵다.
- **충돌 지점:** devDependency가 많이 늘고(Storybook 본체·애드온) lockfile이 커진다. Vite 6·React 19와는 호환되는 버전을 고른다. Vitest 3과 Storybook의 Vitest 애드온 버전 조합을 맞춰야 한다. Docker 이미지에는 들어가지 않는다(`build` 스크립트와 분리, Dockerfile은 `pnpm build`만 실행).
- **대안:** 의존성을 늘리기 싫다면 `/demo`에 "컴포넌트 갤러리" 화면을 만드는 방법도 있으나, 상태 조합을 관리하기엔 Storybook이 낫다.

### 3.7 Google Stitch와 DESIGN.md 작업 흐름

목적은 "AI 도구가 이 프로젝트의 디자인 규칙을 읽고 따르게 하는 것"이다.

```text
DESIGN.md (사람·AI가 읽는 규칙)  ──┐
   ↑ 동기화                        │ 프롬프트에 첨부
tokens.css (코드의 단일 기준)       │
   ↓                               ▼
React 컴포넌트 ← 사람이 옮김 ← Google Stitch 시안 (참고용 HTML/이미지)
   ↓
Storybook 스토리 (상태별 확인) → E2E·스크린샷 비교
```

- **DESIGN.md 위치(제안):** `dashboard/ui/DESIGN.md`. 내용: 디자인 원칙(관제 화면, 각진 카드, 정보 밀도), 토큰 표(이름·값·용도), 상태 표현 규칙(UX-REQUIREMENTS 3장 요약), 컴포넌트 목록과 금지 사항(예: "성공은 서버 확인 뒤에만 초록").
- **토큰 값의 기준은 `tokens.css` 하나**로 둔다. DESIGN.md는 그 표를 옮겨 적은 사본이며, 바꿀 때 둘을 함께 바꾼다(PR 체크 항목).
- **Stitch 결과물은 참고용이다.** 생성된 HTML을 그대로 붙이지 않고, 기존 컴포넌트·토큰으로 다시 구현한다. 특히 상태 문구·잠금 규칙·접근성 이름은 Stitch가 모르므로 바꾸지 않는다.
- Stitch에 넘길 때 실제 운영 화면 캡처 대신 `/demo` 화면(가상 데이터)을 쓴다. 로봇 ID·서버 주소 등 운영 정보가 외부 서비스로 나가지 않게 한다.

---

## 4. 리팩터링 중 지킬 불변 조건

아래 항목은 어느 단계에서도 바뀌면 안 된다. 각 단계의 PR은 이 목록으로 검토한다.

1. **Backend API 유지:** 경로·메서드·요청/응답 형식을 바꾸지 않는다. 화면 변경을 위해 서버를 고쳐야 한다면 별도 계획으로 분리한다.
2. **인증 유지:** 모든 인증 API 호출은 `api()` 래퍼를 거친다. `AuthGate`의 상태 전이(checking → unreachable/login/forced change/app), 입장표 → WebSocket 순서, `/demo` 무로그인 동작을 유지한다.
3. **로봇 제어 로직 유지:** `control.ts`·`commands.ts`의 판단 함수(`driveControl`, `lockReason`, `stopReason`, `waypointLocked`, `fromServer`, `stageShapes`)는 화면 리팩터링에서 고치지 않는다. 성공 표시는 서버 `confirmed`일 때만, 자동 재전송 없음.
4. **실시간 처리 유지:** `LiveProvider`의 검증·revision 순서·재연결 백오프·지연 감시·탭 복귀 규칙을 유지한다. Phase 3은 **정보를 더 내보내는 것만** 하고 판단 규칙은 바꾸지 않는다.
5. **지도 유지:** 좌표 변환(`map.ts`), 2σ 오차 원, 따라가기, 다른 로봇 전환, 편집 중 클릭 좌표 선택을 유지한다.
6. **Waypoint 유지:** revision 동시성, 409 재조회, 잠금 규칙, 이름·마지막 정지 지점 규칙을 유지한다.
7. **문구:** 상태 문구(“확인 불가”, “마지막 수신 값”, “멈춰 있다고 일시정지가 확인된 것은 아닙니다” 등)는 의미가 정해진 것이다. 바꾸려면 UX-REQUIREMENTS 용어집을 먼저 고친다.
8. **기존 테스트 통과:** `pnpm test`, `pnpm test:e2e`, `pytest`가 각 단계 끝에서 모두 통과해야 한다.

---

## 5. 단계별 계획

각 단계는 독립된 PR로 낸다. 단계가 끝날 때마다 화면이 동작하는 상태여야 하며, 문제가 생기면 그 PR만 되돌린다. 저장소 관례대로 단계마다 CHANGELOG 항목을 남긴다.

### Phase 0 — 안전망 (시각 변화 없음)

- E2E 셀렉터를 CSS 클래스에서 **role·label 또는 `data-testid`** 로 옮긴다. 우선 위 1.10의 클래스 의존 셀렉터부터.
- Playwright 스크린샷 기준 이미지 생성: `/demo`의 시나리오 6종(정상·일부 지연·수신 지연·연결 끊김·최초 접속·서버 문제) × 화면 폭 3종(1440·900·390 px).
- 화면 표시용 순수 함수(`ageText`, `timeText`, `overall`, `patrolLabel`)를 `format.ts`·`status.ts`로 옮기고 단위 테스트 추가.
- 완료 기준: 테스트 전부 통과, 스크린샷 기준 저장.

### Phase 1 — 디자인 토큰 (시각 변화 없음)

- `styles/tokens.css` 추가, `style.css`의 hex·px 값을 변수로 치환. 압축된 1행을 읽을 수 있게 풀고 중복 규칙을 합친다.
- 글꼴: 실제로 쓸 글꼴을 정한다 (Pretendard 또는 Noto Sans KR 자체 호스팅 권장 — 외부 CDN 의존 없이 `dist`에 포함).
- `ui/DESIGN.md` 초안 작성 (토큰 표 포함).
- 완료 기준: 스크린샷 차이 0 (글꼴을 바꾸면 그 변화만 승인).

### Phase 2 — 컴포넌트 파일 분리 (시각 변화 없음)

- [COMPONENT-INVENTORY.md](COMPONENT-INVENTORY.md) 6장의 디렉터리 구조로 `App.tsx`를 나눈다. 로직은 옮기기만 하고 고치지 않는다.
- React 연결 훅 추가: `useView(provider)`, `useCommand(live, view)` (`useSyncExternalStore`), `useNow(intervalMs)`(시계를 쓰는 컴포넌트만 다시 그리게).
- `Controls`에서 `WaypointPanel`을 꺼내 형제 카드로 둔다 (배치는 CSS로 지금과 같게 유지).
- waypoint 저장 로직을 `useWaypoints()` 훅으로 옮겨 `RobotDashboard`와 `WaypointPanel`에서 데이터 처리를 뺀다.
- 완료 기준: 스크린샷 차이 0, 테스트 통과, `App.tsx` 100줄 이하.

### Phase 3 — 연결 상태 모델 (끊김과 지연 구분)

- `View`에 브라우저↔서버 링크 상태를 **추가**한다 (기존 `serverProblem`은 호환을 위해 유지하고 새 값에서 계산).

  ```ts
  type Link =
    | { state: 'connecting' }                                  // 처음 연결 중
    | { state: 'live' }                                        // 정상 수신
    | { state: 'stale'; sinceMono: number }                    // 소켓은 열렸으나 browser_delay_s 넘게 새 스냅샷 없음
    | { state: 'reconnecting'; attempt: number; retryAtMono: number }  // 소켓 닫힘, 재시도 대기
    | { state: 'offline' }                                     // navigator.onLine === false
  ```

  `LiveProvider`의 판단 규칙(3초 감시 후 소켓 닫기, 백오프)은 그대로 두고 **어느 경로로 `fail()`이 불렸는지를 기록**만 한다. 4404 종료 코드는 "선택한 로봇을 서버가 모름" 안내로 구분한다.
- 화면: 헤더 연결 표시를 세 구간(브라우저↔서버 / 서버↔로봇 / 센서)으로 나눠 보여 준다. 표시 규칙은 [UX-REQUIREMENTS.md](UX-REQUIREMENTS.md) 3장.
- `MockProvider`에 같은 상태를 만드는 시나리오 추가 (Phase 4와 함께).
- 완료 기준: 새 단위 테스트(소켓 닫힘 → reconnecting, 감시 시간 초과 → stale, 재수신 → live), 기존 `live.test.ts` 통과.

### Phase 4 — Mock 데이터 확장 (로봇·서버 없이 전체 UI 시험)

- `Provider` 옆에 **데이터 소스 인터페이스**를 둔다. 실제 구현은 기존 함수를 감싸기만 한다.

  ```ts
  interface DashboardSource {
    provider: Provider                                   // 기존 그대로
    commands: { current(view: View): RequestResult | null; send(view: View, c: Command): void }
    map: { load(): Promise<MapInfo | null> }
    waypoints: { load(): Promise<WaypointDocument>; change(c: WaypointChange): Promise<WaypointDocument> }
  }
  ```

  - `liveSource(robotId)`: `LiveProvider` + `LiveControl` + 기존 fetch 코드.
  - `mockSource(options)`: `MockProvider` + `CommandMachine` + 메모리 waypoint(revision 증가, 409·잠금 흉내) + 번들 지도 그림.
- 데모 waypoint 변경 로직을 `WaypointPanel`에서 `mockSource`로 옮긴다.
- 시나리오 추가: `stale`(스냅샷 멈춤), `reconnecting`(소켓 끊김·재시도), `offline`, `waypoint 충돌`, `bridge legacy`. 시나리오 목록은 UX-REQUIREMENTS 8장.
- 고정 데이터 `fixtures/snapshots.ts`: 시나리오별 `Snapshot`을 내보내 Storybook·단위 테스트·E2E가 함께 쓴다.
- 개발 진입: 기존 `/demo` 유지 + 개발 서버에서 `?source=mock` 또는 `VITE_DATA_SOURCE=mock`이면 서버 없이 실행(빌드 결과물에서는 `/demo`만 허용).
- 데모 지도 그림: 운영 지도와 다른, 저장소에 이미 있는 시뮬레이션 지도(`human_test_map`)를 작게 줄여 포함하는 안을 검토.
- 완료 기준: `pnpm dev` + `?source=mock`으로 서버 없이 모든 카드가 데이터를 가진 상태로 열림. 기존 `/demo` E2E 통과.

### Phase 5 — 시각 개선 1차 (아이콘·상태 표시·waypoint 사용성)

- Lucide React 도입: 상태 배지·연결 표시·제어 버튼·waypoint 행 아이콘 교체 (접근성 이름 유지).
- 연결 3구간 표시, 데이터 신선도(“N초 전”) 표시 통일, 오래된 값의 흐림·“마지막 값” 표시 통일.
- Waypoint: 순서 변경에 ↑/↓ 버튼(키보드·터치) 추가, 행 단위 "더보기" 메뉴로 버튼 정리.
- 이벤트 로그: 심각도 필터, "지속 중만 보기", 건수, 처음 N건 + 더보기.
- 완료 기준: 바뀐 화면만 스크린샷 승인, 접근성 검사(axe) 위반 0.

### Phase 6 — Storybook과 접근성 부품

- Storybook 설치(개발 전용), 공용 부품(`StatusBadge`, `Card`, `ConnectionIndicator`, `CommandResult`)과 도메인 카드의 스토리를 fixtures로 작성.
- 오버레이를 접근성 있는 Dialog로 교체(포커스 가두기·복귀), 로봇 선택을 표준 listbox/menu 패턴으로 정리. Tailwind를 쓰지 않으면 Radix 단품, 쓰면 shadcn/ui.
- 완료 기준: 모든 공용 부품에 상태별 스토리, Storybook 정적 빌드 성공(CI용).

### Phase 7 — (선택) Tailwind·shadcn/ui 및 Stitch 시안 반영

- Phase 1~6 결과로 Stitch 시안을 받아 비교한 뒤, 레이아웃 재구성이 필요하다고 판단될 때만 진행한다.
- Tailwind는 `preflight` 끈 상태로 새 컴포넌트부터, 기존 CSS는 컴포넌트 단위로 하나씩 옮긴다. `.container` 이름 충돌 먼저 해결.
- 완료 기준: 옮긴 컴포넌트마다 스크린샷 승인, 번들 크기 증가 기록.

---

## 6. 단계별 검증

| 확인 | 방법 | 단계 |
|---|---|---|
| 기능이 그대로인가 | `pnpm test`, `pnpm test:e2e`, `cd dashboard && pytest` | 모든 단계 |
| 보이는 모습 | Playwright 스크린샷 비교 (6 시나리오 × 3 폭) | 0~2는 차이 0, 이후 승인 |
| 실제 서버·Bridge | `tools/sender.py`(가상 송신기)로 서버에 텔레메트리 보내며 확인 | 3, 5 |
| 연결 끊김·지연 | 서버 중지/재시작, 송신기 중지(Bridge 지연·끊김), 브라우저 오프라인 | 3 |
| 휴대폰 | iPhone Safari 실기 (입장표·로그인 반복 문제 재발 여부) | 3, 5, 6 |
| 접근성 | axe(Playwright), 키보드만으로 모든 조작 | 5, 6 |
| 빌드·배포 | `pnpm build`, `docker compose build` | 1, 5, 6, 7 |

---

## 7. 위험과 대응

| 위험 | 대응 |
|---|---|
| 컴포넌트 분리 중 실수로 판단 로직 변경 | 로직 파일(`control.ts` 등)은 diff 없음을 PR 조건으로, 옮기는 PR과 고치는 PR 분리 |
| 클래스 정리로 E2E 대량 실패 | Phase 0에서 셀렉터 먼저 이전 |
| 새 의존성으로 Docker 빌드 실패 | 버전 고정, `pnpm install --frozen-lockfile` 로컬 확인 후 PR |
| AI 생성 코드가 상태 의미를 바꿈 (예: 응답만 받고 "성공" 표시) | DESIGN.md·UX-REQUIREMENTS에 금지 규칙 명시, PR 체크리스트 |
| iPhone에서 실시간 연결 회귀 | Phase 3 이후 실기 확인 필수 (TROUBLESHOOTING 관제 서버 절 참고) |

---

## 8. 열린 결정 사항

1. Tailwind·shadcn/ui 도입 여부 (Phase 6 끝난 뒤 Stitch 시안을 보고 결정).
2. 다크 모드 필요 여부 (야간 현장 운영이 있으면 필요).
3. 글꼴 (Pretendard / Noto Sans KR) 과 번들 포함 방식.
4. 이벤트 로그를 서버 100건 이상 보관·조회할지 — 필요하면 서버 API 추가라 이 계획 범위 밖.
5. 지도 확대·이동(휠·핀치) 추가 여부.
6. Mock 지도 그림으로 어떤 지도를 번들할지.
