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

## 3. 토큰 (현재 값)

Stitch 시안(`autonomous_metric_control/DESIGN.md`)의 값을 따른다. 시안 색을 **글자**로 쓸 때 바탕과의 대비가 4.5:1에 못 미치면 같은 계열의 더 진한 값으로 바꿨다(경고 `#D97706` → `#92400E`, 링크 `#16A34A` → `#15803D`).

| 묶음 | 토큰 | 값 | 용도 |
|---|---|---|---|
| 주 색 | `--color-primary` / `-hover` | `#14532d` / `#166534` | 사이드바 선택, 주행 시작·재개, 주 버튼, 진행 막대 |
| 글자 | `--color-ink` / `--color-text` | `#111827` / `#1f2937` | 제목·강조 / 본문 |
| | `--color-text-muted` / `-faint` | `#4b5563` / `#6b7280` | 보조 설명 / 오래된 값 |
| 바탕 | `--color-bg` / `--color-surface` | `#f7f8f3` / `#fff` | 페이지 / 카드 |
| 선 | `--color-border` / `-strong` | `#e2e8f0` / `#cbd5e1` | 카드 / 버튼·입력 |
| 강조 | `--color-accent` | `#15803d` | 링크·포커스 |
| 위험 | `--color-danger` / `-hover` | `#dc2626` / `#b91c1c` | 주행 정지 버튼 |
| 상태 good | `--color-good-fg` / `-bg` / `-border` | `#166534` / `#dcfce7` / `#bbf7d0` | 연결됨·수신 중·확인된 성공 |
| 상태 warn | `--color-warn-fg` / `-bg` / `-border` | `#92400e` / `#fef3c7` / `#fde68a` | 지연·확인 필요·경로 편집 잠김 |
| 상태 bad | `--color-bad-fg` / `-bg` / `-border` | `#b91c1c` / `#fee2e2` / `#fecaca` | 끊김·실패 |
| 상태 neutral | `--color-neutral-fg` / `-bg` / `-border` | `#4b5563` / `#f3f4f6` / `#e5e7eb` | 확인 불가·확인 전·마지막 상태 |
| 지도 | `--color-map-robot` / `-robot-other` / `-next` | `#16a34a` / `#6b7280` / `#0e7490` | 선택 로봇 / 다른 로봇 / 다음 목표 지점 |
| 모서리 | `--radius-sm` / `-lg` / `-full` | 4px / 8px / 9999px | 입력·작은 버튼 / 카드·지도·큰 버튼 / 배지 |
| 그림자 | `--shadow-menu` | `0 4px 12px rgba(17,24,39,.08)` | 떠 있는 메뉴만. 카드에는 그림자 없음 |

전체 목록은 `tokens.css`에 있다.

## 4. 시안에서 가져온 것과 가져오지 않은 것

- **가져옴**: 색, 모서리, 얇은 카드 테두리, 제목 글꼴(Gmarket Sans 500), 작은 카드의 회색 대문자형 라벨, 둥근 배지, 사이드바(아이콘 + 선택 시 초록 바탕), 순찰 진행 막대(순찰 노드가 보낸 `waypoint_index / waypoint_count`), 숫자의 고정폭 글꼴.
- **가져오지 않음**: 적재량·배터리 %·쓰레기 수거 통계(로봇이 만들지 않는 값), E-STOP·"SYSTEM READY"·"4/4 ONLINE" 같은 고정 문구, 1Hz로 깜박이는 상태 점, 어두운 바탕의 지도(운영 지도 그림이 밝은 점유 격자라서).
