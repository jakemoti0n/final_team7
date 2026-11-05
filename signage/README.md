# Automaton 로봇 하단 디스플레이 (signage)

로봇 하단 디스플레이(1920×1080 가로)에 세 화면을 차례로 띄우는 Python/PySide6 프로그램이다.

1. **시간·일정** (`clock_schedule`): 날짜, 시각, Excel에 등록한 행사 1건
2. **수거함 적재 현황** (`bin_status`): 일반/재활용 적재율(%)과 채움 막대
3. **환경 피드백** (`eco_feedback`): 검증된 분리수거 성공률에 따라 나무 3상태(초기/긍정/부정)

근거 문서: [docs/PRD_로봇_하단_디스플레이_v0.2.md](docs/PRD_로봇_하단_디스플레이_v0.2.md), 디자인 `docs/하단 디스플레이 디자인 제안.pptx` 3~8페이지, Excel 템플릿 `docs/Automaton_행사일정_Excel_템플릿.xlsx`.

화면 앱은 **읽기 전용**이다. 주행·분류·센서를 건드리지 않으며, 이 앱이 죽거나 멈춰도 로봇 쪽에는 영향이 없다.

> **현재 상태 (2026-11-05)**: PC(Ubuntu 24.04, Python 3.12)에서 세 화면·Excel 일정·Mock/JSON 데이터·자동 재로딩을 확인했다(테스트 75개 통과).
> **Raspberry Pi 실기, 부팅 자동 실행, 2시간 연속 순환은 아직 확인하지 않았다.** 적재율 센서와 성공률 검증 데이터는 아직 공급자가 없어서, 운영 모드에서는 `정보 없음` / 초기 나무로 나온다(의도된 동작).

---

## 1. 설치

저장소 루트의 `venvs/signage/`를 쓴다 (`run.sh`의 기본값. 다른 곳이면 `SIGNAGE_VENV=/경로/venv`).

```bash
sudo apt install libxcb-cursor0              # Qt 6.5+가 X11 창을 띄울 때 필요 (한 번만)
cd ~/limbo                                   # 저장소 루트
python3 -m venv venvs/signage
venvs/signage/bin/pip install -r signage/requirements.txt          # 실행만
venvs/signage/bin/pip install -r signage/requirements-dev.txt      # 테스트까지
```

- 실행 시 `Could not load the Qt platform plugin "xcb"` / `xcb-cursor0 or libxcb-cursor0 is needed`가 나오면 위의 `libxcb-cursor0`이 빠진 것이다. 다른 라이브러리가 빠졌는지는 `ldd venvs/signage/lib/python3*/site-packages/PySide6/Qt/plugins/platforms/libqxcb.so | grep "not found"`로 확인한다.
- 한글 글꼴: 기본으로 시스템의 `Noto Sans CJK KR`을 찾는다. 없으면 `sudo apt install fonts-noto-cjk`, 또는 원하는 글꼴을 [assets/fonts/](assets/fonts/)에 넣는다.
- **Raspberry Pi**: 64비트 Raspberry Pi OS 기준. `PySide6-Essentials` aarch64 휠이 pip로 받아지는지는 실기에서 확인해야 한다. 안 되면 배포판 패키지(`python3-pyside6.*`, `python3-openpyxl`, `python3-yaml` — OS 버전에 따라 PySide6 패키지가 없을 수 있음)를 apt로 설치하고 `python3 -m venv --system-site-packages venvs/signage`로 만든다(이 경로도 미검증).

## 2. 실행

### 어떤 venv로 실행하나

이 앱은 **`~/limbo/venvs/signage/`** (1절에서 만든 venv)로 실행한다. 로봇 쪽 YOLO용 `~/limbo/venvs/limbo_yolo`에는 PySide6가 없으니 쓰지 않는다.

- **`./run.sh`로 실행하면 activate하지 않아도 된다.** `run.sh`가 `../venvs/signage/bin/python`을 경로로 직접 부르므로, 다른 venv가 activate된 터미널에서도 그대로 동작한다. venv를 다른 곳에 두었다면 `SIGNAGE_VENV=/경로/venv ./run.sh`.
- **`python` 명령을 직접 쓸 때**(앱을 `python -m app.main`으로 실행, 테스트, `tools/write_status.py`)는 먼저 activate한다.

```bash
source ~/limbo/venvs/signage/bin/activate     # 프롬프트 앞에 (signage)가 붙는다
cd ~/limbo/signage
python -m app.main --windowed --mock         # ./run.sh --windowed --mock 과 같다
python -m pytest -q
deactivate                                   # 끝나면 빠져나오기
```

activate하지 않고 `../venvs/signage/bin/python ...`처럼 경로를 붙여 실행해도 같다(아래 5.3, 8절의 명령이 이 방식).

### 실행 예

```bash
cd ~/limbo/signage
./run.sh                       # config/app.yaml대로 (기본: 운영 모드, 전체화면)
./run.sh --windowed --mock     # PC 미리보기: 창 모드 + 예시 수치(MOCK/DEMO 표시)
./run.sh --windowed --screen bin_status          # 한 화면만 고정
./run.sh --windowed --at 2026-11-07T13:30        # 이 시각부터 시작한 것처럼 (일정 확인용)
./run.sh --mock --screenshot /tmp/shots          # 세 화면을 1920×1080 PNG로 저장하고 끝
```

| 옵션 | 뜻 |
|---|---|
| `--demo` / `--production` | 이번 실행만 모드 변경 |
| `--mock` | `--demo` + 적재율·환경평가 공급원을 mock으로 |
| `--windowed` / `--fullscreen` | 창 / 전체화면 |
| `--screen ID` | `clock_schedule`, `bin_status`, `eco_feedback` 중 하나만 표시 |
| `--at 시각` | 시작 시각 바꾸기 (시간은 그대로 흐름) |
| `--screenshot DIR` | PNG 저장 후 종료 (모니터 없이 `QT_QPA_PLATFORM=offscreen`으로도 됨) |

점검용 키: `→`/`Space` 다음 화면, `←` 이전, `P` 순환 멈춤/재개, `F11` 전체화면 전환, `Esc`/`Q` 종료.

로그: 화면(stderr)과 `logs/signage.log`(1 MB × 5개 순환). 데이터 출처, 일정 읽기 결과와 제외된 행, 읽기 실패, 적재율 표시/정보 없음 전환, 나무 상태 전환이 남는다. 같은 오류는 바뀔 때만 한 번 기록한다.

## 3. 콘텐츠 바꾸기 (코드 수정 없이)

저장하면 `content.reload_interval_seconds`(기본 3초) 안에 반영된다. 새 파일이 깨졌으면 마지막 정상 내용을 계속 보여 준다.

| 바꿀 것 | 파일 |
|---|---|
| 문구 | [content/text/](content/text/)`*.txt` (UTF-8, 줄바꿈 그대로 표시) |
| 나무 그림 | [assets/images/](assets/images/)`tree_initial.png`, `tree_positive.png`, `tree_negative.png` (PNG/WebP) |
| 글꼴 | [assets/fonts/](assets/fonts/) + `config/app.yaml`의 `theme.font_families` (재시작 필요) |
| 위치·크기·색·날짜 형식 | [config/screens/](config/screens/)`*.yaml` (1920×1080 기준 px) |
| 화면 순서·시간, 테마 색 | [config/app.yaml](config/app.yaml) `rotation`, `theme` |

문구 파일:

| 파일 | 기본 내용 |
|---|---|
| `schedule_empty.txt` | 예정된 행사가 없습니다. |
| `schedule_ongoing_label.txt` / `schedule_upcoming_label.txt` | 지금 진행 중 / 다음 행사 (빈 파일이면 안 보임) |
| `bin_general_label.txt` / `bin_recycle_label.txt` | 일반 / 재활용 |
| `bin_unavailable.txt` | 정보 없음 |
| `eco_initial.txt` / `eco_positive.txt` / `eco_negative.txt` | PPT 6~8페이지 문구 |
| `eco_pending.txt` | 평가 준비 중 |

나무 문구와 그림은 **상태별 묶음**으로 바뀐다. 예를 들어 `eco_positive.txt`와 `tree_positive.png`를 둘 다 정상으로 읽었을 때만 새 묶음으로 바꾼다. 한쪽이 깨졌으면 둘 다 이전 것을 유지한다.

> 나무 그림 3장은 PPT에 들어 있던 이미지를 그대로 꺼낸 것이다. 실제 전시 전에 사용 권리를 확인하고, 문제가 있으면 같은 이름의 파일로 바꾼다(PRD 10절).

## 4. 행사 일정 (Excel)

`data/events.xlsx`의 `Events` 시트를 편집해 저장한다. 앱은 15초마다 수정시각·크기를 보고 바뀌었으면 다시 읽는다. 작성 방법은 같은 파일의 `Guide` 시트에 있다.

- 한 행에 행사 1개. `enabled`가 **`Y`인 행만** 표시 대상이다. 배포본의 예시 행(2026-11-03 국악 공연)은 `N`이다.
- `date`는 `YYYY-MM-DD`, 시각은 24시간제 `HH:MM`. Excel 날짜/시간 셀도 된다. **수식은 쓰지 않는다.**
- 표시 규칙: 진행 중 행사(시작 ≤ 지금 < 종료)가 우선이다. 없으면 가장 가까운 다음 행사를 보여 준다. 지난 행사는 빠지고, `end_time`이 빈 행사는 시작 시각이 지나면 빠진다. 다른 날 행사는 앞에 `내일` / `11월 7일(토)`을 붙인다.
- 잘못된 행(날짜·시각 형식 오류, 종료가 시작보다 이름, 활성 행끼리 `event_id` 중복)은 그 행만 빠지고 로그에 행 번호와 이유가 남는다. 자정을 넘기는 행사는 아직 지원하지 않는다.
- 파일을 못 읽으면(손상, 시트 이름 변경, 저장 중) **마지막으로 정상 읽은 일정**을 계속 보여 주고 다음 주기에 다시 읽는다.

## 5. 적재율·성공률 데이터 연동

화면은 공급원(`adapter`)이 준 dict만 쓴다. 공급원은 `config/app.yaml`에서 고른다.

| adapter | 내용 |
|---|---|
| `json` (기본) | 로컬 파일 `data/bin_status.json`, `data/eco_metrics.json` |
| `http` | `url`에 GET 해서 같은 JSON을 받음 |
| `mock` | 예시 수치. **demo 모드에서만** 허용(운영 모드에서 고르면 거부하고 `정보 없음`) |
| `ros2`, `mqtt` | 아직 없음. 고르면 `정보 없음`으로 동작하고 로그를 남김 |

### 5.1 적재율 `data/bin_status.json`

```json
{
  "schema_version": 1,
  "observed_at": "2026-11-07T14:00:00+09:00",
  "source": "ultrasonic-v1",
  "bins": {
    "general":   {"fill_percent": 60,   "measurement_method": "volume_estimate", "quality": "ok"},
    "recycling": {"fill_percent": null, "measurement_method": "unknown",         "quality": "unavailable"}
  }
}
```

수거함마다 따로 판정하고, 아래를 **모두** 만족할 때만 퍼센트를 표시한다. 하나라도 어긋나면 그 수거함만 `정보 없음`과 점선 빈 칸이 된다. 0%로 대신 표시하지 않는다.

- `schema_version` = 1, `observed_at`이 ISO 8601이고 **120초 이내**(`max_data_age_seconds`)
- 해당 수거함의 `quality` = `ok`
- `measurement_method` ∈ `volume_estimate`, `weight_estimate`, `manual_measured` (`unknown`이면 측정 근거가 없다고 보고 표시하지 않음)
- `fill_percent`가 0~100 숫자. `0`은 실제로 0일 때만 보낸다.

### 5.2 분리수거 성공률 `data/eco_metrics.json`

```json
{
  "schema_version": 1,
  "observed_at": "2026-11-07T14:00:00+09:00",
  "window_start": "2026-11-06T14:00:00+09:00",
  "window_end": "2026-11-07T14:00:00+09:00",
  "source": "eco-evaluator",
  "evaluation_method": "human_audit",
  "verified_correct_count": 18,
  "verified_total_count": 20,
  "quality": "ok"
}
```

성공률 = `100 × verified_correct_count / verified_total_count`. 아래 조건을 모두 통과하면 판정한다.

| 조건 (기본값은 PRD 제안값) | 어긋나면 |
|---|---|
| `quality` = `ok`, `evaluation_method` ∈ `verified_route_log`, `human_audit`, `sensor_verified` | initial + 평가 준비 중 |
| `observed_at`이 600초 이내, `window_start`~`window_end`가 있고 24시간 이하 | initial + 평가 준비 중 |
| 두 건수가 0 이상 정수, `correct ≤ total`, `total > 0` | initial + 평가 준비 중 |
| `total ≥ 20` (`min_verified_samples`) | initial + 평가 준비 중 |
| 성공률 ≥ 80% (`positive_threshold_percent`, **테스트용 초기값**) | 미만이면 negative |

AI 모델의 분류 **예측**만으로는 건수를 채우지 않는다. 실제로 올바른 수거함에 들어갔는지 검증된 건만 센다(PRD 5.4). 적재율로 성공률을 추정하지도 않는다.

### 5.3 값을 쓰는 방법

데이터를 쓰는 프로그램은 **임시 파일에 다 쓴 뒤 `os.replace`로 바꿔 끼운다**. 그래야 화면이 반쯤 쓰인 파일을 읽지 않는다. [app/util.py](app/util.py)의 `atomic_write_json`을 복사해 써도 된다. 손으로 넣거나 연동을 시험할 때는 다음 도구를 쓴다.

```bash
../venvs/signage/bin/python tools/write_status.py bin --general 60 --recycling none --method manual_measured
../venvs/signage/bin/python tools/write_status.py eco --correct 18 --total 20 --method human_audit
../venvs/signage/bin/python tools/write_status.py reset      # 둘 다 '값 없음'으로
```

`observed_at`을 지금 시각으로 넣으므로 120초(적재율)·600초(성공률)가 지나면 다시 `정보 없음`/initial로 돌아간다. 계속 보이게 하려면 생산자가 주기적으로 다시 써야 한다.

### 5.4 새 공급원 추가 (ROS 2, MQTT 등)

1. `app/adapters/`에 `read() -> dict`, `describe() -> str`, `is_mock = False`를 가진 클래스를 만든다. 반환 형식은 5.1/5.2와 같다. 실패하면 `AdapterError`를 던진다. `read()`는 백그라운드 스레드에서 불리므로 블로킹해도 화면은 멈추지 않는다.
2. [app/adapters/__init__.py](app/adapters/__init__.py)의 `_build`에 이름을 등록한다.

화면 코드는 고치지 않는다.

## 6. 운영 모드와 시연 모드

| | `production` (기본) | `demo` |
|---|---|---|
| mock 공급원 | 거부 → `정보 없음` | 허용 |
| 표시 | 실제 값만 | 오른쪽 아래 `DEMO`, mock 값 위에 `MOCK` |

시연에서는 `./run.sh --mock`으로 적재율 60%/10%, 나무 3상태(90% → 70% → 표본 부족)를 36초마다 번갈아 보여 준다. 수치는 `app.yaml`의 `mock_data`에서 바꾼다.

## 7. 부팅 시 자동 실행 (미검증)

```bash
mkdir -p ~/.config/systemd/user
cp ~/limbo/signage/deploy/signage.service ~/.config/systemd/user/   # ExecStart 경로 확인
systemctl --user daemon-reload
systemctl --user enable --now signage.service
journalctl --user -u signage -f      # 로그
```

Raspberry Pi OS에서 데스크톱 자동 로그인이 켜져 있어야 한다. 화면이 안 뜨면 유닛의 `QT_QPA_PLATFORM`을 `xcb`로 바꿔 본다. 앱이 죽으면 3초 뒤 다시 뜬다.

## 8. 테스트

```bash
cd ~/limbo/signage && ../venvs/signage/bin/python -m pytest -q
```

PRD 9절 시나리오 1~13, 15를 자동 테스트로 확인한다(14 오프라인은 네트워크를 쓰지 않는 구조로 충족). 화면 테스트는 `QT_QPA_PLATFORM=offscreen`으로 돌아서 모니터가 없어도 된다.

## 9. 폴더 구조

```text
signage/
├── app/
│   ├── main.py                # 진입점, 명령행 옵션, 스크린샷
│   ├── config.py              # app.yaml 기본값·검증, 프로젝트 밖 경로 차단
│   ├── context.py             # 화면 공용 객체, 설정 자동 재로딩
│   ├── data_manager.py        # 공급원 폴링 스레드, 마지막 정상값, 상태 전환 로그
│   ├── schedule.py            # Excel 행 해석·검증, 표시 일정 선택 (Qt 무관)
│   ├── bin_resolver.py        # 적재율 검증 (Qt 무관)
│   ├── eco_state_resolver.py  # 성공률 → initial/positive/negative (Qt 무관)
│   ├── content_loader.py      # TXT·이미지·글꼴 로드와 자동 재로딩
│   ├── util.py                # 시각 해석·표기, 원자적 JSON 쓰기
│   ├── adapters/              # excel, json, http, mock 공급원
│   ├── renderer/              # Stage(스케일·순환·오류 격리), 그리기 도구
│   └── screens/               # 화면 A/B/C
├── config/app.yaml, config/screens/*.yaml
├── content/text/*.txt, assets/images/*.png, assets/fonts/
├── data/events.xlsx, bin_status.json, eco_metrics.json
├── tools/write_status.py      # 상태 JSON 쓰기 도구
├── deploy/signage.service     # systemd 사용자 유닛
├── tests/
└── docs/                      # PRD, PPT, Excel 템플릿 원본
```

## 10. PRD와 다른 점·추가한 것

- 루트 폴더 이름은 PRD의 `lower-display/` 대신 `signage/`. mock 공급원은 `bin_mock.py`/`eco_mock.py` 대신 `adapters/mock.py` 하나에 있다.
- 일정 화면에 PPT에 없는 요소를 넣었다: 날짜·시각 아래 초록 구분선, `지금 진행 중`/`다음 행사` 문구, 다른 날 행사의 날짜 접두어. 문구는 TXT, 구분선은 YAML `divider.show`로 끌 수 있다.
- 다음은 PRD가 열어 둔 부분을 보수적으로 정한 것이다. 담당자와 합의하면 바꾼다.
  - `measurement_method: unknown`이면 `quality=ok`여도 퍼센트를 표시하지 않는다.
  - 성공률 판정에는 `window_start`/`window_end`가 꼭 있어야 한다.
  - 종료 시각이 시작보다 이르면 잘못된 행으로 본다(자정 넘김 미지원).
- 시계는 초 경계에 맞춰 다시 그려서 분이 바뀌는 순간에 바로 바뀐다.
