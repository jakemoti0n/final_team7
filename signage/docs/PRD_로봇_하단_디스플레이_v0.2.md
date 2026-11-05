# PRD — Automaton 로봇 하단 디스플레이 표시 프로그램

- **문서 버전:** v0.2 (2026-11-05)
- **제품:** Automaton 자율주행 이동형 쓰레기통 / 하단 디스플레이
- **개발 언어:** Python
- **실행 장치:** Raspberry Pi / Raspberry Pi OS
- **UI 기술:** PySide6 (Qt) 우선 제안. 실제 Raspberry Pi OS에서 설치·구동 검증 후 확정.
- **목표 해상도:** 1920 × 1080, 가로형 16:9. 실측·OS 출력 설정은 설치 단계에서 재확인.
- **디자인 원본:** `하단 디스플레이 디자인 제안.pptx` (2~8페이지)
- **행사 일정 원본:** `data/events.xlsx` Excel `.xlsx`
- **상태:** 화면 구조 및 데이터 인터페이스 확정 초안. 센서·성공률 판정의 실데이터 공급자는 미구현.

> **원본과 추가 설계 구분:** PPT는 세 화면의 순환, 날짜·시간·행사 안내, 일반/재활용 적재율 표시, 3가지 나무·문구를 제시한다. 아래의 Excel 데이터 스키마, API, 화면 지속시간, 성공률 계산식과 예외처리 규칙은 **추가 개발 제안**이며 PPT에 명시된 확정 사양은 아니다.

## 1. 제품 목적과 설계 원칙

로봇 하단 디스플레이에 **① 시간·일정 → ② 수거함 적재 현황 → ③ 환경 피드백** 화면을 반복 표시한다. 화면 표시 앱은 읽기 전용 클라이언트이며, 로봇의 실제 분류·센서·주행 제어를 수행하지 않는다.

### 필수 원칙

1. **콘텐츠 교체:** 문구는 개별 UTF-8 `.txt`, 이미지는 개별 `.png`/`.webp`, 글꼴은 별도 파일, 배치는 YAML로 관리한다. 소스코드 수정 없이 교체 가능해야 한다.
2. **데이터 출처 교체:** 화면에서 요구하는 데이터 구조는 고정하고, 공급원은 Mock / JSON 파일 / HTTP API / ROS 2 Topic / MQTT 등으로 교체 가능한 `DataAdapter` 계층을 둔다.
3. **표시 데이터 정직성:** 적재율 미측정 시 `0%`를 표시하지 않는다. 성공률 미검증 시 `긍정적/부정적` 판정을 만들어내지 않는다. Mock은 개발 모드에만 허용한다.
4. **단독 실행:** 네트워크와 외부 로봇 기능이 중단되더라도 시간·일정·콘텐츠 순환이 유지된다.
5. **안전한 통합:** 디스플레이 앱의 오류는 주행·분류 프로세스에 영향을 주지 않는다. 로봇의 실시간 제어 루프에 동기식 요청을 넣지 않는다.

## 2. 범위 및 제외 범위

| 포함 | 제외 |
|---|---|
| PPT 기반 3개 화면과 나무 3개 상태 | 주행 및 로봇 하드웨어 제어 |
| 날짜·시계, Excel 행사 일정 표시 | 행사 일정 원격 편집 웹서비스 |
| 수거함 일반/재활용 적재율 표시 UI | 센서의 실제 장착·보정·측정 알고리즘 |
| 검증된 분리수거 성공률 기반 환경 피드백 | AI 예측을 정답으로 가정해 정확도 산출 |
| 콘텐츠 개별 파일 교체, 자동 갱신 | 검증되지 않은 탄소 절감량·환경효과 산출 |
| 데이터 어댑터 / Mock / JSON 입력 | ROS 2 또는 API 서버 자체의 개발(연동 시점 별도) |

## 3. UX / 화면 상세

### 화면 A — `clock_schedule` (PPT 3페이지)

- 현재 날짜: 예 `2026-11-03`; 시간: 예 `오전 10:09`. OS 시간대 `Asia/Seoul`.
- 행사: **Excel `data/events.xlsx`**의 `Events` 시트에서 읽는다. 정해진 스키마를 충족하는 사용 설정(`enabled=Y`) 일정만 대상으로 한다.
- 기본 선택: **현재 진행 중인 행사 우선**, 없으면 가장 가까운 다음 일정 **1건**. 과거 행사 제외. 정렬은 시작시각 오름차순, 동률 시 `event_id` 오름차순.
- 행사 표시 예(PPT): `오후 2:00 – 국악 공연 (주행사장 > 열린야외 무대)`.
- 예정 일정이 없으면 외부 TXT에서 `예정된 행사가 없습니다.` 로드.
- 날짜·시계는 1초 간격 갱신 가능; 분 단위 화면이라도 시간 경계에서 정확히 갱신해야 한다.
- Excel 변경은 기본 15초 간격 확인 후 유효한 데이터만 반영. 읽기 오류 시 마지막 정상 일정 유지, 장애 상태 로그 기록.

### 화면 B — `bin_status` (PPT 4~5페이지)

- 일반쓰레기/재활용에 대해 별도로 **백분율 숫자 + 채움 그래픽** 출력.
- PPT의 `0/0`, `60/10`은 디자인 예시이며 실제 데이터가 아니다.
- 각 적재율은 **0~100 실수 또는 정수**만 유효. 데이터는 실제로 어떤 물리량을 측정했는지 메타데이터 포함(예 `volume_estimate`, `weight_estimate`, `manual_measured`).
- 데이터가 누락/미측정/만료/측정 오류이면 해당 수거함만 `정보 없음`과 빈 측정 자리 표시. **0% 또는 이전 수치를 현재 측정값으로 속이지 않음.**
- `0%`는 실제 센서 또는 검증된 수동 측정값이 **정확히 0인 경우**에만 출력.
- 적재율 센서가 없다면 운영 모드에서는 `정보 없음`, 개발 미리보기에서는 MOCK 배지를 붙이고 예시값 출력.

### 화면 C — `eco_feedback` (PPT 6~8페이지)

- `initial`: `여러분의 재활용이 이 나무를\n자라게 해요.` + 초기 나무.
- `negative`: `분리수거가 잘 안되고 있어요.\n더욱 노력해 주세요.` + 시든 나무.
- `positive`: `분리수거가 잘 되고 있어요.\n자연이 고마워 해요.` + 열매 나무.
- 평가 결과가 없거나 표본 수 부족/실측 근거 없음/유효기간 초과이면 **`initial` 상태 유지**, 필요 시 `평가 준비 중` 별도 소형 안내(TXT) 출력.
- 적재율이 높거나 낮다는 이유만으로 성공률 또는 상태를 계산하지 않는다.
- 이미지와 문구는 **상태 단위로 원자적으로 함께** 변경한다. 파일 누락 시 마지막 정상 묶음 또는 기본 묶음 표시.
- PPT의 `Green Washing` 표기는 원본의 화면 제목. 실제 기능 명칭은 오해를 피하도록 **환경 피드백(Eco Feedback)** 으로 사용한다.

## 4. Excel 행사 일정 스키마 (변경사항)

**파일 경로:** `data/events.xlsx`  
**시트명:** `Events`  
**첫 행:** 헤더(아래 영문 열 이름을 변경하지 않음)  
**표준 시간대:** `Asia/Seoul`  
**파일 구성:** `Events` (운영 데이터), `Guide` (작성 안내)

| 열 | 헤더 | 필수 | 예시 | 처리 규칙 |
|---|---|---|---|---|
| A | `event_id` | 예 | `event-001` | 활성 일정 내 유일한 ID |
| B | `date` | 예 | `2026-11-07` | `YYYY-MM-DD` 권장; Excel 날짜 셀도 허용 |
| C | `start_time` | 예 | `14:00` | 24시간제 `HH:MM` 권장; Excel 시간 셀도 허용 |
| D | `end_time` | 아니오 | `15:00` | 비어 있으면 진행 중 판정 생략하고 시작시각 이후 다음 일정 선정에서 제외 |
| E | `title` | 예 | `국악 공연` | 표시할 행사명 |
| F | `location` | 아니오 | `주행사장 > 열린야외 무대` | 장소 미입력 시 장소 영역 생략 |
| G | `enabled` | 예 | `Y` | `Y`=표시 대상, `N`=무시; 기본 N 권장 |
| H | `notes` | 아니오 | `운영 메모` | 화면 미표시 |

**읽기 규칙:** `openpyxl.load_workbook(..., read_only=True, data_only=True)`를 사용한다. 수식 셀은 저장된 계산 캐시가 없을 수 있으므로 **행사 입력 필드는 수식 사용 금지**. 문자열과 Excel 고유 날짜·시간 타입 둘 다 수용한다. 행 단위 입력 오류는 행 번호와 이유를 로그에 남기고 해당 행만 제외하되, 파일 전체를 읽을 수 없으면 마지막 정상 스냅샷 유지. `enabled=Y`인 일정의 중복 `event_id`는 잘못된 입력으로 취급한다.

**날짜 변경 시 처리:** 한 날짜의 모든 일정이 종료되면 가장 가까운 미래 일정 표시; 미등록 시 안내 문구. 수정 중 읽기 실패하면 재시도. 파일 변경 감지는 수정시각과 크기를 기준으로 확인하거나 15초마다 재읽기한다. Excel 잠금/부분 저장의 영향을 피하기 위해 마지막 성공한 파싱 결과를 보존한다. 원자적 파일 교체 방식으로 배포하는 것도 허용한다.

**배포 원칙:** 기본 템플릿 파일 `events.xlsx`의 예시 행은 `enabled=N`. 운영자가 실제 행을 등록하고 `Y`로 바꿀 때만 나타나도록 한다.

## 5. 데이터 아키텍처: 현재 값이 없어도 개발 가능한 구조

```text
     [운영자가 편집하는 Excel]     [센서/관리자 입력/로봇 측정]      [검증된 분리수거 이벤트]
                |                         |                          |
         ExcelScheduleAdapter       BinStatusAdapter            EcoMetricsAdapter
                |                   ┌─────┴────────┐             ┌──────┴───────┐
                |                  JSON   HTTP/ROS2/MQTT         JSON   HTTP/ROS2/MQTT
                |                         |                          |
                +-------------------------+--------------------------+
                                          |
                        [Data Manager: 정규화/검증/TTL/캐시]
                                          |
                        [Screen Controller + PySide6 Renderer]
                            |            |               |
                         일정화면      적재율화면      환경피드백화면
                                          |
                              [1920 x 1080 HDMI 표시]
```

### 5.1 공급원 교체 인터페이스

각 adapter가 내놓는 정규화 데이터 형식은 동일해야 한다. 예시 프로토콜:

```python
from typing import Protocol

class BinStatusAdapter(Protocol):
    def read(self) -> dict: ...

class EcoMetricsAdapter(Protocol):
    def read(self) -> dict: ...
```

- `MockBinStatusAdapter`: 개발 모드에서만 정해진 수치를 생성.
- `JsonBinStatusAdapter`: `data/bin_status.json` 읽기.
- `HttpBinStatusAdapter`: 외부 API 폴링(후속 개발).
- `Ros2BinStatusAdapter`: ROS 2 Topic 구독 및 최신값 캐시(후속 개발).
- 동일하게 환경평가용 `Mock/Json/Http/Ros2` Adapter 구현 가능.
- **UI는 `adapter.read()` 결과만 사용**하고 파일·URL·토픽을 직접 참조하지 않는다.
- 로봇 내부에 기존 Bridge/Relay/분류 프로그램이 있다면 **수치 발생 지점**에서 공통 JSON 상태를 저장하거나 ROS 2 메시지를 발행하도록 협의한다. 기존 프로그램 내부 구현은 별도 확인 필요.

### 5.2 권장 1차 통합: 로컬 JSON 스냅샷

서로 다른 프로세스가 같은 라즈베리파이에 있다면 외부 데이터 생산자가 정해진 파일에 최신값을 기록하고, 하단 디스플레이가 읽는 방식이 가장 단순하다.

- `data/bin_status.json`: 실제 적재율(없으면 null).
- `data/eco_metrics.json`: **검증된** 분리수거 건수(없으면 null).
- 기록 프로그램은 임시 파일에 전체 JSON을 쓴 뒤 `os.replace(temp_path, target_path)` 등으로 같은 파일시스템 안에서 원자적 교체.
- 표시 프로그램은 형식 검증 후 마지막 유효 데이터를 메모리에 저장하되 **데이터 만료 시 UI는 정보 없음으로 전환**.
- 값에는 작성시각(`observed_at`), 출처(`source`) 및 품질(`quality`) 필드를 포함한다.
- 파일 없음, 권한 오류, 잘못된 JSON, 오래된 업데이트는 UI 프로세스의 종료로 이어지면 안 된다.

### 5.3 쓰레기통 적재율 JSON 계약

`data/bin_status.json`:

```json
{
  "schema_version": 1,
  "observed_at": null,
  "source": "unavailable",
  "bins": {
    "general": {
      "fill_percent": null,
      "measurement_method": "unknown",
      "quality": "unavailable"
    },
    "recycling": {
      "fill_percent": null,
      "measurement_method": "unknown",
      "quality": "unavailable"
    }
  }
}
```

- `quality`: `ok | unavailable | error` 제안.
- `measurement_method`: `volume_estimate | weight_estimate | manual_measured | unknown` 제안.
- `fill_percent`만 있고 `quality=ok`이며 `observed_at` 유효할 때 퍼센트 표시.
- 유효기간(TTL) 제안: 관측 시각에서 **120초** 초과 시 `정보 없음`. 실제 센서 갱신 주기에 맞춰 설정으로 수정 가능.
- 두 수거함 데이터를 개별 검증. 한쪽 오류가 다른 쪽 표시를 차단하지 않는다.

**적재율 데이터를 확보하는 후보**

| 방법 | 얻을 수 있는 정보 | 주의점 |
|---|---|---|
| 거리센서(초음파/ToF) | 내용물의 높이 기반 채움 추정 | 불규칙한 물체·각도·빈 형상에 따른 보정 필요 |
| 무게센서(load cell) | 수거물의 무게 기반 상대적 적재 | 재료별 밀도가 달라 부피 적재율과 다름 |
| 카메라/비전 | 특정 시점의 내용물 외관 기반 추정 | 가림·조명·정확도 검증 필요 |
| 사람의 측정 후 수동 입력 | 사람이 확인한 적재율 | 자동이 아님; 측정 시각과 수동 출처 표시 |

**센서가 없다면 퍼센트 실측은 불가능**하다. 투입 건수만으로 가득 찬 정도를 추정하는 것은 용량·무게·부피 보정 없이 실제 적재율로 표시하지 않는다.

### 5.4 분리수거 성공률 JSON 계약

`data/eco_metrics.json`:

```json
{
  "schema_version": 1,
  "observed_at": null,
  "window_start": null,
  "window_end": null,
  "source": "unavailable",
  "evaluation_method": "unknown",
  "verified_correct_count": null,
  "verified_total_count": null,
  "quality": "unavailable"
}
```

- `verified_correct_count`: 검증 결과 올바르게 분리·투입된 건수.
- `verified_total_count`: **동일한 검증 기준**으로 결과가 판정된 전체 투입 건수. 0 이상 정수.
- 성공률(%) = `100 × verified_correct_count / verified_total_count` (분모가 0보다 크고 `0 ≤ correct ≤ total`일 때에만 계산).
- **중요:** YOLO/EfficientNet 등의 분류 모델이 어떤 항목이라고 예측했다는 사실만으로 실제로 올바른 수거함에 들어갔다는 *검증*은 아니다. 모델 예측과 성공률의 분자는 서로 다른 개념이다.
- `evaluation_method`: `verified_route_log | human_audit | sensor_verified | unknown` 제안. 시스템이 실제 최종 투입 경로까지 확인하는지 별도 검증 필요.
- 건별 이벤트 로그를 확보한다면 외부 평가 프로그램이 검증 완료 건만 집계한 스냅샷을 발행하도록 한다.
- 최근 **24시간** 또는 최근 **N건**처럼 **평가 창(window)** 을 정하고 분자·분모에 동일하게 적용. 기본 24시간은 제안값.
- 표본 **최소 20건** 미만이면 판정하지 않고 `initial` + `평가 준비 중`. 20건은 제안값이며 담당자와 조정.
- 임시 정책 예시: 20건 이상이고 성공률 ≥ **80%**면 `positive`, 미만이면 `negative`. **80% 기준은 최종 정책이 아니라 테스트용 초기값**.
- 관측 값이 없거나 만료(예: 마지막 집계 이후 10분 이상), 검증 근거가 없거나 신뢰도가 부족하면 `initial`.
- 이벤트 데이터에는 가능하면 `event_id`, `timestamp`, `predicted_class`, `actual_bin`, `verification_result` 등을 표준화해 추후 검증 가능하도록 한다. **실제 정답 라벨 확보 경로가 없다면** 성공률 대신 `판정 불가` 표시.

### 5.5 상태 판단 주체

**권장:** 성공률의 *집계*는 로봇 분류/평가 프로그램 또는 별도 `EcoEvaluator`가 맡고, **표시 상태 변환**은 앱 내부의 독립 `EcoStateResolver` 모듈이 설정된 임계값으로 수행한다. 추후 외부에서 이미 판단한 `state`를 보내는 경우에도 유효성 확인과 근거(`source`, `quality`, `observed_at`)를 요구한다.

```text
  verified_correct_count + verified_total_count
                           │
                           ▼
                   [EcoStateResolver]
                   ├─ 데이터 없음/표본 부족 ──> initial
                   ├─ 성공률 >= 80%        ──> positive  (제안 임계값)
                   └─ 성공률 < 80%         ──> negative  (제안 임계값)
```

## 6. 설정 및 파일 아키텍처

```text
lower-display/
├── app/
│   ├── main.py
│   ├── screens/
│   │   ├── clock_schedule.py
│   │   ├── bin_status.py
│   │   └── eco_feedback.py
│   ├── renderer/
│   ├── content_loader.py
│   ├── data_manager.py
│   ├── eco_state_resolver.py
│   └── adapters/
│       ├── schedule_excel.py
│       ├── bin_mock.py
│       ├── bin_json.py
│       ├── eco_mock.py
│       └── eco_json.py
├── config/
│   ├── app.yaml
│   └── screens/
│       ├── clock_schedule.yaml
│       ├── bin_status.yaml
│       └── eco_feedback.yaml
├── content/text/
│   ├── bin_general_label.txt
│   ├── bin_recycle_label.txt
│   ├── schedule_empty.txt
│   ├── eco_initial.txt
│   ├── eco_positive.txt
│   ├── eco_negative.txt
│   └── eco_pending.txt
├── assets/
│   ├── images/
│   │   ├── tree_initial.png
│   │   ├── tree_positive.png
│   │   └── tree_negative.png
│   └── fonts/
├── data/
│   ├── events.xlsx             # Excel 행사 일정
│   ├── bin_status.json         # 실데이터 미연결 시 null
│   └── eco_metrics.json        # 실데이터 미연결 시 null
├── tests/
├── README.md
└── requirements.txt
```

`config/app.yaml` 예시:

```yaml
app:
  locale: ko-KR
  timezone: Asia/Seoul
  mode: production                 # production | demo

display:
  fullscreen: true
  width: 1920
  height: 1080
  orientation: landscape
  scale_mode: keep_aspect_ratio
  hide_cursor: true

rotation:
  - {id: clock_schedule, duration_seconds: 12}
  - {id: bin_status,     duration_seconds: 12}
  - {id: eco_feedback,  duration_seconds: 12}

content:
  reload_interval_seconds: 3

schedule:
  adapter: excel
  file: data/events.xlsx
  sheet: Events
  reload_interval_seconds: 15
  max_visible_events: 1

bin_status:
  adapter: json                     # mock | json | http | ros2 | mqtt
  file: data/bin_status.json
  refresh_interval_seconds: 2
  max_data_age_seconds: 120

eco_feedback:
  adapter: json                     # mock | json | http | ros2 | mqtt
  file: data/eco_metrics.json
  refresh_interval_seconds: 5
  max_data_age_seconds: 600
  evaluation_window_hours: 24
  min_verified_samples: 20
  positive_threshold_percent: 80
  default_state: initial

mock_data:
  allowed_only_in_demo_mode: true
  visible_demo_badge: true
```

- 수치 `12초`, `15초`, `120초`, `600초`, `20건`, `80%`는 **PRD 제안값**이며 운영 중 조정한다.
- 화면별 YAML에서 폰트/크기/좌표, 텍스트 및 이미지 파일 경로만 변경해 레이아웃과 콘텐츠를 제어한다.
- 상대 경로는 프로젝트 루트 기준. 프로젝트 외부 경로를 임의로 참조하지 않도록 유효성 검사한다.
- 새 이미지가 손상되어도 디스플레이 앱을 종료하지 않으며 마지막 정상 이미지 유지.

## 7. 기능 요구사항 및 수용 기준

| ID | 우선순위 | 요구사항 | 수용 기준 |
|---|---|---|---|
| FR-01 | P0 | 세 화면 자동 순환 | 1 → 2 → 3 순서 및 YAML 표시 시간 준수 |
| FR-02 | P0 | Raspberry Pi OS 실행 | Python 앱으로 실제 기기에서 1920×1080 전체화면 표시 |
| FR-03 | P0 | 외부 문구 교체 | TXT 수정만으로 대상 문구 변경, Python 수정 불필요 |
| FR-04 | P0 | 외부 이미지 교체 | PNG/WebP 변경만으로 대상 그림 변경 |
| FR-05 | P0 | 한글 글꼴 지원 | 폰트 리소스 지정, 글꼴 깨짐/줄 겹침 없음 |
| FR-06 | P0 | 시계 갱신 | Asia/Seoul의 현재 날짜·시각 표시 |
| FR-07 | P0 | **Excel 일정 읽기** | `Events` 시트의 `enabled=Y` 일정 정렬·선택 표시 |
| FR-08 | P0 | Excel 갱신 처리 | 파일만 수정해도 변경 일정 반영. 파일 오류 시 마지막 정상 스냅샷 유지 |
| FR-09 | P0 | 적재율 두 항목 표시 | 유효한 JSON 입력에 따라 각각 0~100% 및 채움 그래픽 정확히 표시 |
| FR-10 | P0 | 미측정 상태 | `null`, 오류, 오래된 데이터에 `정보 없음`; 0%로 강제하지 않음 |
| FR-11 | P0 | **분리수거 성공률 계산** | 검증된 correct/total로만 계산. total 0이면 판정 불가 |
| FR-12 | P0 | 나무 상태 자동 선택 | 유효한 성공률·표본 기준을 만족하면 positive/negative, 아니면 initial |
| FR-13 | P0 | 화면과 데이터 소스 분리 | Mock→JSON 교체 시 화면 렌더링 코드 수정 없음 |
| FR-14 | P0 | 운영/시연 모드 분리 | 운영에서 Mock 수치 미노출, 시연에서 `DEMO` 표시 |
| FR-15 | P0 | 오류 격리 | Excel·JSON 오류 시 앱 계속 실행, 주행/분류 프로그램 영향 없음 |
| FR-16 | P1 | API 연동 확장 | HTTP 및 ROS 2 Adapter 추가 시 기존 화면 수정 불필요 |
| FR-17 | P1 | 콘텐츠 자동 재로딩 | 변경된 TXT/이미지/YAML을 다음 갱신 주기에 반영 |
| FR-18 | P1 | 로그 | 데이터 출처, 갱신 시각, 누락, 파싱 오류, 상태 전환 로깅 |
| FR-19 | P1 | PC 미리보기 | 데스크톱에서도 전체화면/창 모드 테스트 가능 |
| FR-20 | P2 | 부팅 시 자동 실행 | 사용자 세션/그래픽 환경에 맞는 systemd 방식으로 자동 실행 |

## 8. 비기능 요구사항

- **레이아웃:** 1920×1080 기준 픽셀 디자인. 출력 해상도 차이에는 비율 유지 스케일링. 창 테두리·커서 숨김; 화면 외곽 5% 안전 여백 권장.
- **텍스트:** 한국어 UTF-8, 운영자의 한글 폰트 교체 가능, 날짜/시간 로캘 지정, 긴 행사명의 줄바꿈 및 글자 잘림 방지.
- **성능:** Raspberry Pi에서 실제 렌더링 부하 측정. 한 화면 갱신 실패가 전체 순환을 정지시키지 않음.
- **신뢰성:** 네트워크 미연결/Excel 오류/JSON 누락에도 GUI 프로세스 유지. 마지막 정상 데이터 보존은 하되 만료 시 현재값인 것처럼 표시하지 않음.
- **파일 안정성:** 원자적 JSON 쓰기, 읽기 실패 재시도, 마지막 정상 Excel 스냅샷, 로깅.
- **보안:** 로컬 데이터는 읽기 전용으로 처리하고 입력·경로 검증, 외부 API 이용 시 신뢰 가능한 네트워크 및 인증 수단(후속).
- **품질:** 최소 2시간 연속 순환 시험(초기 기준), 설치 후 실제 사용 시간을 반영한 장기 시험 별도.
- **데이터 의미:** `measurement_method`, `evaluation_method`, `source`, `quality`, `observed_at`를 남겨 출처 추적 가능.

## 9. 테스트 시나리오

1. **Excel:** `events.xlsx`에서 `Y`로 설정된 미래 행사 한 건을 수정했을 때 다음 재로딩 주기에 새 행사명·장소 반영.
2. **Excel 예외:** 잘못된 날짜 형식 한 행은 제외하고 다른 유효한 행은 유지. 파일 자체가 손상되면 마지막 정상 스냅샷 유지.
3. **빈 일정:** 활성 일정이 없으면 `예정된 행사가 없습니다.` 표시.
4. **적재율 Mock:** 데모 모드에 일반 60%, 재활용 10%를 넣으면 숫자와 막대가 일치하며 `DEMO` 표시.
5. **적재율 운영:** 실제 파일의 두 값이 null이면 양쪽 모두 `정보 없음`으로 표시.
6. **적재율 부분 장애:** 일반 60%, 재활용 null이면 일반 60%만 정상 표시.
7. **적재율 만료:** `observed_at`이 TTL을 넘으면 `정보 없음`으로 전환.
8. **성공률:** 검증된 18/20이면 90% → `positive`(80% 제안 정책 기준).
9. **성공률:** 검증된 14/20이면 70% → `negative`(80% 제안 정책 기준).
10. **표본 부족:** 검증된 9/10이면 90%라도 `initial + 평가 준비 중`(최소 20건 기준).
11. **검증 불가:** AI 예측 라벨만 있고 검증 건수가 없으면 평가하지 않고 초기 상태 유지.
12. **콘텐츠:** `eco_positive.txt`와 `tree_positive.png`를 개별 교체하여 코드 수정 없이 반영.
13. **1920×1080:** 글꼴/이미지 비율·안전 여백·전체화면 확인.
14. **오프라인:** 인터넷 및 데이터 송신 프로그램 중단에도 시간·일정·화면 순환 유지.
15. **환경 장애:** 파일 읽기 오류, 화면 전환 중 이미지 손상 상황에서도 GUI가 종료되지 않음.

## 10. 단계별 구현 순서

**1단계 — PPT 기반 UI + 콘텐츠 모듈화**
- Python/PySide6로 세 화면 개발, 1920×1080 대응.
- PPT 6~8페이지 나무 이미지는 권리 확인 후 별도 PNG로 추출하거나 자체 제작 이미지로 대체.
- 모든 문구·이미지·글꼴·화면 전환 설정을 외부 파일로 분리.

**2단계 — Excel + Mock/JSON 데이터**
- `events.xlsx` 읽기·유효성 검사·실행 중 갱신.
- `MockBinStatusAdapter`, `MockEcoMetricsAdapter`로 PC 미리보기.
- 운영 모드 기본값은 `정보 없음` / `initial`로 처리.

**3단계 — 로봇 실데이터 통합**
- 적재율 센서·로봇 소프트웨어 담당자와 데이터 생산 포맷 합의.
- 성공률의 **검증 기준과 이벤트 출처**를 정의하고 외부 평가 모듈과 연동.
- JSON → HTTP/ROS 2/MQTT로 전환해야 하는 경우 새로운 Adapter만 추가.

**4단계 — 운영 안정화**
- Raspberry Pi OS 전체화면, 부팅 자동 실행.
- 로그·재시도·실측 데이터 신선도·오프라인 안정성 검증.

## 11. 외부 팀과 합의해야 할 데이터 계약 질문

### 적재율 공급자에게
1. 일반/재활용 적재율을 현재 누가 생산할 수 있는가? 센서가 실제 존재하는가?
2. 측정값은 부피/높이/무게 중 어느 의미인가? 0%·100% 보정 기준은 무엇인가?
3. 갱신 주기와 정확도, 통신 방법(JSON/ROS 2/HTTP)은 무엇인가?
4. 센서 고장·초기화·수거함 비움 이벤트는 어떻게 알리는가?

### 성공률 공급자에게
1. **무엇을 성공으로 볼 것인가?** 최종 투입 위치의 적합성인지, AI 분류 예측 정확도인지, 기구 동작 성공인지?
2. 그 성공 여부를 누가/어떻게 검증하는가? 실제 정답 라벨 또는 최종 투입 확인 신호가 있는가?
3. 판정 불능·사용자 투입 오류·기구 장애는 분모에서 어떻게 처리하는가?
4. 집계 단위(최근 24시간/최근 N건), 최소 표본, 긍정·부정 임계값은 무엇인가?
5. 이벤트 로그에서 화면 표시용 최신 집계를 발행할 책임 컴포넌트는 무엇인가?

### 일정 운영자에게
1. 행사 일정은 사람이 Pi의 `events.xlsx`를 직접 편집하는가, 다른 PC에서 파일을 복사하는가?
2. 진행 중 행사를 표시할 것인가, 다가오는 행사만 표시할 것인가?
3. 한 화면에서 몇 건을 표시할 것인가? (기본 1건)

## 12. v0.1 대비 변경 사항

| 항목 | v0.1 | **v0.2** |
|---|---|---|
| 실행 환경 | Raspberry Pi OS 후보 | **Raspberry Pi OS 확정, Python 사용** |
| 해상도 | 16:9, 미정 | **1920×1080 가로형 설계 목표** |
| 일정 파일 | JSON | **Excel `.xlsx` / `Events` 시트** |
| 적재율 | JSON 계약 초안 | **소스 교체형 어댑터 + 품질/시간/측정방식 + 실데이터 없음 처리** |
| 환경 피드백 | 외부 `state` 수신 | **검증된 correct/total 집계 → 성공률 → 상태 판단** |
| 시연/운영 | 시뮬레이터 제안 | **DEMO 워터마크, Mock 운영 금지** |
| 예외 처리 | 기본 실패 대응 | **TTL/원자적 저장/마지막 정상 스냅샷/표본 부족** |

---

**결론:** 실측 적재율과 검증된 분리수거 성공률이 없는 현재도 전체 UI·Excel 일정·Mock 테스트·데이터 계약까지 개발할 수 있다. 다만 실데이터 공급/검증 경로가 생기기 전에는 운영 디스플레이에서 실제 수치 또는 평가 결과인 것처럼 표시하지 않는다.
