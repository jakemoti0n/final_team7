# LIMBO Dashboard

FastAPI 수신 서버와 React/TypeScript 운영 UI. 구현 기준은 [Dashboard PRD](docs/PRD.md), 수신 계약의 단일 기준은 [Bridge PRD §3](../relay_prog/docs/PRD.md)다. 기존 `limbo/`, `relay_prog/` 프로그램을 수정하지 않는다.

- `/`: 실제 수신 화면. 세 제어 버튼은 항상 비활성화되며 실제 제어 API는 없다.
- `/demo`: 독립 Mock 공급자. 실제 서버 API/WebSocket에 접속하지 않는다. 가상 데이터·알림·명령 결과는 이 페이지의 메모리에만 존재한다.
- 서버는 ROS2 설치 없이 실행된다. 한 로봇, 단일 프로세스, 메모리 최신 상태 및 최근 알림 100건을 지원한다. 서버 재시작 시 초기화되며 브라우저 새로고침은 서버 이력을 지우지 않는다.

## 명령 실행 디렉터리

이 문서의 명령은 **현재 PC의 실제 저장소 위치**를 기준으로 작성했다.

| 용도 | 명령을 실행할 디렉터리 |
|---|---|
| 저장소 루트 · 기존 Bridge 실행 · 실제 ROS2 통합 검증 | `/home/itkwon/limbo_ros2_workspace/final_team7` |
| Dashboard 서버 설치·실행 · 가상 송신기 · Python 테스트 | `/home/itkwon/limbo_ros2_workspace/final_team7/dashboard` |
| UI 설치·빌드·개발 서버 · UI 단위 테스트 · 브라우저 테스트 | `/home/itkwon/limbo_ros2_workspace/final_team7/dashboard/ui` |

**각 명령 블록의 첫 `cd`부터 실행한다.** 따라서 새 터미널을 어느 디렉터리에서 열었든 같은 순서로 실행할 수 있다. 터미널마다 현재 디렉터리는 독립적이므로, 다른 터미널에서 수행한 `cd`는 적용되지 않는다. 다른 PC에 복제했다면 아래 명령의 `/home/itkwon/limbo_ros2_workspace/final_team7` 부분을 해당 PC의 저장소 절대 경로로 바꾼다.

## 설치

Python 3.12, Node.js 22 또는 24, pnpm 10.17.1을 준비한다. 검증 환경은 Python 3.12.3, Node.js 24.19.0이다. ROS/YOLO 환경과 분리한 가상환경을 사용한다.

서버 의존성 설치 — 실행 디렉터리: `/home/itkwon/limbo_ros2_workspace/final_team7/dashboard`.

```bash
cd /home/itkwon/limbo_ros2_workspace/final_team7/dashboard
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
```

UI 의존성 설치 및 빌드 — 실행 디렉터리: `/home/itkwon/limbo_ros2_workspace/final_team7/dashboard/ui`.

```bash
cd /home/itkwon/limbo_ros2_workspace/final_team7/dashboard/ui
corepack pnpm install --frozen-lockfile
corepack pnpm build
```

`corepack`이 없다면 Node.js 설치 환경에서 `npm install --global pnpm@10.17.1`로 pnpm을 설치하고 아래 `corepack pnpm` 대신 `pnpm`을 사용한다. 이 전역 설치 명령은 실행 디렉터리와 무관하다. Python 직접 의존성은 `dashboard/requirements.txt`, 검증된 전체 버전은 `dashboard/requirements.lock`, UI 버전은 `dashboard/ui/package.json`과 `dashboard/ui/pnpm-lock.yaml`로 고정한다. 패키지 설치에는 네트워크가 필요하며 실행 시 외부 폰트나 CDN에 접속하지 않는다.

## 실행·종료

UI 빌드 완료 후, **서버는 `dashboard/ui`가 아닌 `dashboard` 디렉터리에서 실행한다.** 이 서버 하나가 빌드된 실제 화면과 데모 화면을 모두 제공하므로 일반 실행에는 별도 UI 터미널이 필요 없다.

```bash
cd /home/itkwon/limbo_ros2_workspace/final_team7/dashboard
.venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8000 --workers 1
```

실제 수신: <http://127.0.0.1:8000/> · 가상 제어: <http://127.0.0.1:8000/demo>.
종료는 `Ctrl+C`. 서버는 빌드된 UI를 직접 제공한다. `--workers`는 반드시 1이며, 상태 공유 저장소가 없으므로 다중 worker를 사용하지 않는다. 외부 인터넷 공개·인증·실제 로봇 제어는 범위 밖이다.

개발 시에는 위 일반 실행 서버를 종료하고 다음 두 터미널을 사용한다.

첫 번째 터미널 — FastAPI 개발 서버, 실행 디렉터리: `/home/itkwon/limbo_ros2_workspace/final_team7/dashboard`.

```bash
cd /home/itkwon/limbo_ros2_workspace/final_team7/dashboard
.venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8000 --reload
```

두 번째 터미널 — Vite 개발 UI, 실행 디렉터리: `/home/itkwon/limbo_ros2_workspace/final_team7/dashboard/ui`.

```bash
cd /home/itkwon/limbo_ros2_workspace/final_team7/dashboard/ui
corepack pnpm dev
```

개발 UI는 <http://127.0.0.1:5173/>. Vite가 `/api` HTTP/WebSocket과 `/healthz`를 8000으로 프록시한다. 양쪽 터미널에서 `Ctrl+C`로 종료한다. 서버 포트를 바꾸면 개발 프록시의 대상도 `ui/vite.config.ts`에서 맞춘다.

## 설정과 상태 해석

기본 [config.json](config.json)을 수정하거나 `DASHBOARD_CONFIG`로 다른 JSON 경로를 지정한 후 서버를 다시 실행한다. 실행 디렉터리는 `/home/itkwon/limbo_ros2_workspace/final_team7/dashboard`다. 아래 `/absolute/path/config.json`은 사용할 설정 파일의 실제 절대 경로로 바꾼다.

```bash
cd /home/itkwon/limbo_ros2_workspace/final_team7/dashboard
DASHBOARD_CONFIG=/absolute/path/config.json .venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8000 --workers 1
```

| 설정 | 기본값 |
|---|---|
| `robot_id` | `LIMBO-01` |
| `bridge_delay_s` / `bridge_disconnect_s` | 3초 / 10초, 정확한 경계부터 적용 |
| `topic_delay_s` | odom, lidar_raw, lidar_filtered, camera_raw 각각 3초 |
| `browser_delay_s` | 3초. 1초 갱신 간격보다 커야 함 |
| `linear_threshold_mps` / `angular_threshold_radps` | 0.05 m/s / 절대값 0.05 rad/s |
| `alert_limit` | 100, 1~100 |

적용 설정은 서버 스냅샷으로 UI에 전달된다. 토픽별 기준은 실제 발행 주기를 측정한 뒤 조정한다. motion freshness는 odom 지연 기준을 motion 자체 age에 적용한다. ROS 헤더는 freshness 판정에 사용하지 않는다. 현재 세션의 마지막 유효 속도는 별도로 보존하고 현재 값이 없으면 `마지막 수신 값`으로만 표시한다.

- Bridge 연결: 유효한 새 스냅샷의 서버 수신 이후 **단조 증가 시간**으로 판정한다. 중복·역순·잘못된 요청은 heartbeat를 갱신하지 않는다.
- 토픽 수신: Bridge가 전달한 `age_ms`에 서버 수신 이후 단조 증가 경과 시간을 더한다. heartbeat가 와도 센서 수신으로 간주하지 않는다.
- 브라우저 연결: WebSocket 종료·오류 또는 상태 갱신 지연 시 현재 상태를 확인 불가로 덮어 표시한다. 1·2·4·8·10초 간격으로 재접속하고 전체 스냅샷을 받은 뒤 복구한다. 서버 내부 Bridge 판정은 바꾸지 않는다.
- 시각은 UTC 기록을 Asia/Seoul로 표시하며, 브라우저는 서버 age에 `performance.now()` 경과만 더한다. 탭 복귀 시 현재 표시를 보류하고 HTTP 전체 상태를 다시 조회한다.
- `—`는 미수신/미확인이다. 유효한 0은 `0.00 m/s`다. 수신 중은 데이터 도착 여부이며 센서 성능 판정이 아니다. 속도 0이나 Bridge 재연결은 명령 성공 근거가 아니다.

## 인터페이스와 구조

| 경로 | 역할 |
|---|---|
| `POST /api/v1/telemetry` | 공통 v1 계약 그대로, 최대 UTF-8 8192바이트 |
| `GET /api/v1/state` | 전체 현재 판정, 마지막 값, 설정, 알림 |
| `WS /api/v1/stream` | 연결 즉시, 새 유효 수신 시, 1초 타이머마다 전체 상태 |
| `GET /healthz` | `{"status":"ok"}`, 서버 생존 확인만 의미 |

스냅샷에는 `server_run_id`, `revision`, `server_utc`, `robot_id`, `bridge`, `topics`, `motion`, `alerts`, `settings`가 포함된다. `motion.current`와 `motion.last_valid`, 토픽 `receive_hz`와 `last_receive_hz`를 구분한다. 이전 run의 revision과 새 서버 revision을 비교하지 않는다.

스키마는 누락·추가 필드, 숫자 강제 변환, bool 숫자, NaN/Infinity, 음수 범위, 비UTC 시각, null 관계를 검사한다. 오류 코드는 Bridge PRD를 따른다. 종료된 세션은 최근 100개만 기억한다. 느린 WebSocket에는 대기 스냅샷 한 개만 유지하고 전송이 3초 이상 막히면 연결을 닫는다. UI 빌드가 없으면 `/`와 `/demo`는 안내 JSON과 503을 반환한다.

아래 파일 구조의 기준 디렉터리는 `dashboard/`다.

```text
server/models.py     계약 및 설정 검증
server/state.py      시계·세션·판정·알림
server/app.py        FastAPI, 주기 갱신, HTTP/WebSocket, 정적 UI
ui/src/live.ts       실제 공급자와 브라우저 연결 감시
ui/src/demo.ts       별도 가상 상태·알림 공급자
ui/src/commands.ts   요청 ID 기반 3단계 명령 상태 머신
ui/src/App.tsx       공통 화면·재사용 카드·상태·제어·모달
tools/               개발용 송신기 및 통합 검증 도구
```

## 가상 송신기로 독립 검증

가상 송신기는 개발 도구다. **실제 Bridge와 함께 같은 서버에 보내지 않는다.** v1 계약에는 실제/가상 출처 필드가 없으므로 수신 화면은 전송자의 진위를 판별할 수 없다. 반드시 Bridge가 연결되지 않은 전용 서버를 사용한다. `/demo`와는 별개의 테스트다.

첫 번째 터미널에서 위 「실행·종료」 명령으로 테스트 서버를 8000에 실행한 뒤, **두 번째 터미널**에서 아래 명령을 실행한다. 송신기 실행 디렉터리도 `/home/itkwon/limbo_ros2_workspace/final_team7/dashboard`다. 두 시나리오는 각각 20초씩 순서대로 실행된다.

```bash
cd /home/itkwon/limbo_ros2_workspace/final_team7/dashboard
.venv/bin/python tools/sender.py --scenario normal --duration 20
.venv/bin/python tools/sender.py --scenario partial --duration 20
```

`--url`, `--robot-id`, `--duration`을 지원한다. 시나리오:

| 이름 | 입력 |
|---|---|
| `normal`, `empty` | 정상 수신 / 모든 토픽 미수신 heartbeat |
| `partial`, `all-stopped` | 필터 LiDAR만 / 모든 토픽 중단, heartbeat 유지 |
| `bridge-stopped` | 첫 스냅샷 뒤 전송 중단 |
| `new-session` | 5초 후 새 세션의 미수신 스냅샷 |
| `duplicate`, `out-of-order`, `invalid` | 동일 순번 / 역순 / 추가 필드 오류 |
| `zero`, `rotation`, `invalid-motion` | 속도 0 / 제자리 회전 / motion null |

격리 임시 서버와 CLI 송신기를 자동 실행·종료하는 검증은 **별도 서버를 미리 실행할 필요가 없다.** 실행 디렉터리는 `/home/itkwon/limbo_ros2_workspace/final_team7/dashboard`다.

```bash
cd /home/itkwon/limbo_ros2_workspace/final_team7/dashboard
.venv/bin/python tools/validate_http.py
```

## 가상 제어 검증

`/demo` 상단에서 화면 상태, 가상 순찰 상태, **각 명령별** 결과와 두 제한 시간을 선택한다. 전송 완료는 비동기 0.1초, 로봇 응답은 그 후 0.5초, 확인 이벤트는 응답 후 1초다. 기본 응답/확인 제한 시간은 각각 5초다.

성공, 명시적 거절, 응답 없음, 응답 후 상태 확인 없음 및 제한 시간 후 늦은 결과를 제공한다. `진행 중 연결 끊기`는 요청 결과를 확인 불가로 마감한다. 시나리오 변경/초기화는 진행 요청·타이머·알림을 취소한다. 결과는 다음 요청까지 유지된다. 이전 ID, 종료된 요청의 이벤트는 무시하고 자동 재전송하지 않는다. 순찰 재개 여부는 별도의 가상 순찰 상태로 판단하며 속도와 관계없다.

## 테스트

서버 테스트 및 독립 HTTP 검증 — 실행 디렉터리: `/home/itkwon/limbo_ros2_workspace/final_team7/dashboard`.

```bash
cd /home/itkwon/limbo_ros2_workspace/final_team7/dashboard
.venv/bin/python -m pytest -q
.venv/bin/python tools/validate_http.py
```

UI 단위 테스트·빌드·브라우저 테스트 — 실행 디렉터리: `/home/itkwon/limbo_ros2_workspace/final_team7/dashboard/ui`.

```bash
cd /home/itkwon/limbo_ros2_workspace/final_team7/dashboard/ui
corepack pnpm test
corepack pnpm build
# 최초 브라우저 설치가 필요한 경우
corepack pnpm exec playwright install chromium
corepack pnpm test:e2e
```

기존 Chrome을 사용하려면 위 브라우저 설치와 `test:e2e` 명령 대신 다음을 실행한다. 실행 디렉터리는 동일하게 `dashboard/ui`다.

```bash
cd /home/itkwon/limbo_ros2_workspace/final_team7/dashboard/ui
CHROME_PATH=/opt/google/chrome/chrome corepack pnpm test:e2e
```

E2E는 테스트용 FastAPI를 127.0.0.1:8017에서 자동 실행한다. 기존 8017 서버를 종료하고 실행한다. 저장소 루트 기준으로 1440·1024·768·390px 스크린샷은 `dashboard/artifacts/`에 생성되고, 테스트 실패 자료는 `dashboard/ui/test-results/`에 남는다. 모든 생성물·가상환경·의존성은 git에서 제외한다.

## 기존 Bridge 통합

첫 번째 터미널에서는 위 「실행·종료」 명령으로 `dashboard` 디렉터리에서 Dashboard를 8000에 실행한다. **두 번째 터미널에서는 저장소 루트 `/home/itkwon/limbo_ros2_workspace/final_team7`로 이동한 뒤** 아래 명령으로 기존 Bridge를 실행한다. 기존 로봇과 같은 ROS_DOMAIN_ID/discovery 환경을 사용하며, 기존 Mock receiver와 가상 송신기는 종료한다. 아래 명령은 기존 Bridge가 설치되어 있다는 전제다.

```bash
cd /home/itkwon/limbo_ros2_workspace/final_team7
source /opt/ros/jazzy/setup.bash
source relay_prog/install/setup.bash
ros2 run limbo_telemetry_bridge bridge --config relay_prog/src/limbo_telemetry_bridge/config/bridge.yaml
```

다른 서버 주소를 사용할 경우 기존 설정을 저장소 루트 기준 `dashboard/artifacts/bridge.yaml` 등에 복사하고 그 파일의 `server_url`을 변경하여 `--config`로 전달한다. Bridge 프로그램이나 기존 설정을 변경할 필요가 없다.

실제 ROS2 테스트 발행자 → 기존 Bridge → Dashboard → Chrome 자동 검증은 **저장소 루트 `/home/itkwon/limbo_ros2_workspace/final_team7`에서** 다음으로 실행한다. 도구가 테스트 서버·Bridge·발행자·브라우저를 준비하므로 검증용 프로세스를 다른 터미널에서 따로 실행할 필요가 없다. 기존 Bridge Python/ROS 메시지 및 UI 테스트 의존성과 빌드된 UI를 사용한다. `--domain`은 운영 도메인과 겹치지 않는 값을 직접 선택한다.

```bash
cd /home/itkwon/limbo_ros2_workspace/final_team7
source /opt/ros/jazzy/setup.bash
PYTHONDONTWRITEBYTECODE=1 CHROME_PATH=/opt/google/chrome/chrome \
  relay_prog/venvs/bridge/bin/python dashboard/tools/validate_bridge.py --domain 91
```

Node.js가 PATH에 없으면 `--node /absolute/path/to/node`를 추가한다. 도구는 임시 서버 포트, 임시 Bridge 설정, 별도 ROS 도메인 및 `dashboard/artifacts/` 로그를 사용하고 종료 시 자식 프로세스를 정리한다. 헤더 0·역행, 0 속도·회전·무효 odom·재수신을 확인하고 발행 직후부터 브라우저 표시 확인까지 2초 미만인지 측정한다. 실제 Gazebo 주행이나 실물 로봇 검증을 대신하지 않는다.

검증 결과 및 미검증 항목은 [검증 보고서](docs/VALIDATION.md)에 구분해 기록한다.
