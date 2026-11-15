# 관제 화면 디자인 규칙 (DESIGN.md)

사람과 AI 도구(Google Stitch 등)가 함께 읽는 관제 화면(`dashboard/ui`)의 디자인 기준이다.

- **값의 원본은 [`src/styles/tokens.css`](src/styles/tokens.css) 하나다.** 이 문서의 표는 그 사본이다. 토큰을 바꾸면 이 표도 같은 PR에서 바꾼다.
- 컴포넌트 CSS는 색·글꼴·그림자를 직접 쓰지 않고 `var(--…)`만 쓴다.
- 시안(`dashboard/docs/stitch_autonomous_robot_fleet_control_dashboard/`)은 참고용이다. 생성된 HTML을 붙여 넣지 않고 기존 컴포넌트와 토큰으로 다시 만든다.
- 함께 지킬 동작 규칙: [UX-REQUIREMENTS.md](../docs/UX-REQUIREMENTS.md)

## 1. 원칙

1. **모르는 것은 모른다고 표시한다.** 받지 못한 값은 "—"·"확인 불가"(neutral)로, 마지막 값은 흐리게 + "마지막 수신 값" + 받은 시각.
2. **성공(초록)은 서버가 `confirmed`일 때만.** 클릭·전송·응답만으로 초록을 쓰지 않는다.
3. **색만으로 구분하지 않는다.** 상태마다 기호(● ! ○)와 문구가 다르다.
4. **버튼이 잠긴 이유를 글로 보인다.** `title`(마우스 오버)에만 맡기지 않는다.
5. **로봇이 만들지 않는 숫자를 그리지 않는다.** 시안에 있어도 적재량·배터리 %·E-STOP·"SYSTEM READY" 같은 고정 문구는 쓰지 않는다(분석: 1단계 범위 밖 C·D 항목).

## 2. 글꼴

| 토큰 | 값 | 용도 |
|---|---|---|
| `--font-body` | Pretendard Variable → 시스템 글꼴 | 본문·라벨·버튼·표 |
| `--font-heading` | Gmarket Sans(700·500) → 본문 글꼴 | 화면 제목·카드 제목 |
| `--font-mono` | JetBrains Mono(600·700) | 속도·좌표·시각·요청 ID 같은 숫자 |

모두 빌드에 포함한다(외부 CDN 없음). Pretendard는 글자 묶음별 파일이라 화면에 쓰인 묶음만 받는다. Gmarket Sans는 한글 2,350자로 줄인 파일이다([src/assets/fonts/README.md](src/assets/fonts/README.md)).

## 3. 색 토큰 (현재 값)

| 묶음 | 토큰 | 값 | 용도 |
|---|---|---|---|
| 글자 | `--color-ink` | `#17264a` | 제목·강조 글자, 카드 윗선 |
| | `--color-text` | `#2b3445` | 본문 |
| | `--color-text-muted` | `#5b6576` | 보조 설명 |
| | `--color-text-faint` | `#7b8391` | 오래된 값 |
| 바탕 | `--color-bg` | `#eef0f3` | 페이지 바탕 |
| | `--color-surface` | `#fff` | 카드 |
| | `--color-surface-sunken` | `#f5f6f8` | 표 머리·빈 지도 |
| 선 | `--color-border` / `-subtle` / `-strong` | `#d7dbe2` / `#e3e6eb` / `#8c95a4` | 카드 / 행 구분 / 버튼·입력 |
| 강조 | `--color-accent` | `#0b7a80` | 링크·포커스·다음 목표 |
| 상태 good | `--color-good-fg` / `-bg` / `-border` | `#1d7a43` / `#e6f3eb` / `#c4dfce` | 연결됨·수신 중·확인된 성공 |
| 상태 warn | `--color-warn-fg` / `-bg` / `-border` | `#a65300` / `#fdf0e1` / `#efd1b0` | 지연·확인 필요 |
| 상태 bad | `--color-bad-fg` / `-bg` / `-border` | `#c42b2b` / `#fbe9e9` / `#efbebe` | 끊김·실패·정지 버튼 |
| 상태 neutral | `--color-neutral-fg` / `-bg` / `-border` | `#5f6878` / `#eceef2` / `#d3d7de` | 확인 불가·확인 전 |
| 지도 | `--color-map-robot` / `-robot-other` / `-bg` | `#c42b2b` / `#5f6878` / `#cdcdcd` | 선택 로봇 / 다른 로봇 / 지도 밖 |

전체 목록은 `tokens.css`에 있다.

## 4. 시안에서 가져올 값 (1단계 1-5에서 적용 예정)

`autonomous_metric_control/DESIGN.md` 기준. 적용하면 위 3장 표를 이 값으로 바꾼다.

| 역할 | 시안 값 |
|---|---|
| 주 색(헤더·사이드바·주 버튼) | `#14532D`, hover `#16A34A` |
| 페이지 바탕 | `#F7F8F3` |
| 글자 | `#111827` |
| 카드 | `#FFFFFF` + 1px `#E2E8F0`, 모서리 8px |
| 상태 good | 바탕 `#DCFCE7`, 글자 `#14532D` |
| 상태 warn | 바탕 `#FEF3C7`, 글자 `#D97706` |
| 상태 bad | 바탕 `#FEE2E2`, 글자 `#DC2626` |
| 모서리 | 입력·버튼 4px, 카드·지도 8px, 배지 9999px |
| 그림자 | 떠 있는 것만 `0 4px 12px rgba(17,24,39,.05)` |

시안의 1Hz로 깜박이는 상태 점은 쓰지 않는다(`prefers-reduced-motion`과 주의 분산).
