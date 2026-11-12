# LIMBO Dashboard

FastAPI 수신·관제 서버와 React/TypeScript 관제 화면(LIMBO 관제). 처음 구현 기준은 [Dashboard PRD](docs/PRD.md)이고, 그 뒤 추가한 관제 기능(일시정지·순찰 재개, 지도, 순찰 상태, 상태 요약)의 설계는 [관제 화면 설계](../docs/CONTROL_SCREEN.md), 텔레메트리 v2와 명령 계약은 [관제 계약 초안](../docs/CONTROL_API_DRAFT.md)이 기준이다. 텔레메트리 v1 계약은 [Bridge PRD §3](../relay_prog/docs/PRD.md)을 따른다. PRD와 달라진 점은 [관제 화면 설계의 「PRD와 달라지는 것」](../docs/CONTROL_SCREEN.md#prd와-달라지는-것)에 정리되어 있고, 변경 이력은 [CHANGELOG](../docs/CHANGELOG.md) (24)~(29), (32)에 있다.


- `/`: 실제 수신 화면. 순찰 상태에 따라 주행 시작·정지·재개가 한 버튼에 나타나며 waypoint 편집을 지원한다.
- `/demo`: 독립 Mock 공급자. 실제 서버 API/WebSocket에 접속하지 않는다. 가상 데이터·알림·명령 결과는 이 페이지의 메모리에만 존재한다.
- 서버 자체는 ROS2를 쓰지 않는다. 주행 시작·순찰 종료도 서버는 명령을 쌓기만 하고, **로봇 컴퓨터의 Bridge**가 그 컴퓨터에서 `patrol_node`를 띄우고 끈다. 그래서 서버를 ROS가 없는 다른 컴퓨터(예: AWS)에 두어도 된다. 로봇 쪽에는 ROS 2 Jazzy, 빌드된 `limbo_patrol`, Bridge가 필요하다. 한 로봇, 단일 프로세스, 메모리 최신 상태 및 최근 알림 100건을 지원한다. 서버 재시작 시 관제 상태가 초기화되며 브라우저 새로고침은 서버 이력을 지우지 않는다.

- `/`: 실제 관제 화면. 맨 위 상태 한 줄 요약(정상 / 확인 필요 / 연결 끊김), 순찰·이동 카드, 지도(로봇 위치·방향, 순찰 경로, 다음 목표, 로봇 따라가기), **일시정지·순찰 재개** 버튼, 접어 둔 「센서 수신 상세」(토픽 4개), 알림으로 구성된다. 두 버튼은 서버 명령 API를 거쳐 Bridge가 순찰 노드의 `/patrol/pause`·`/patrol/resume` 서비스를 부르는 **실제 제어**다. 프로그램 재시작 버튼은 없다.
- `/demo`: 독립 Mock 공급자. 실제 서버 API/WebSocket에 접속하지 않는다. 가상 데이터·순찰·위치·알림·명령 결과는 이 페이지의 메모리에만 존재한다.
- 서버는 ROS2 설치 없이 실행된다. 한 로봇, 단일 프로세스, 메모리 최신 상태, 마지막 명령 하나, 최근 알림 100건을 지원한다. 서버 재시작 시 초기화되며 브라우저 새로고침은 서버 이력을 지우지 않는다.
- 순찰 상태·위치·제어는 텔레메트리 **v2 이상**을 보내는 Bridge(`relay_prog`)와 순찰 노드(`limbo_patrol`)가 있어야 동작한다. 주행 시작·순찰 종료는 **v3**(`launcher` 추가)를 보내는 Bridge가 있어야 열린다. v2를 보내는 이전 Bridge가 연결되면 두 버튼은 「로봇의 Bridge를 업데이트해야 사용할 수 있습니다」로 잠긴다. v1 송신기만 연결하면 순찰 카드·지도 위 로봇은 비어 있고, 순찰 재개는 잠긴다. 일시정지는 눌러서 요청을 만들 수 있지만 v1 송신기는 명령을 가져가지 않으므로 실행되지 않는다(「버튼 잠금」 참고).


## 명령 실행 디렉터리

이 문서의 명령은 **현재 PC의 실제 저장소 위치**를 기준으로 작성했다.

| 용도 | 명령을 실행할 디렉터리 |
|---|---|
| 저장소 루트 · 기존 Bridge 실행 · 실제 ROS2 통합 검증 | `/home/itkwon/limbo_ros2_workspace/final_team7` |
| Dashboard 서버 설치·실행 · 가상 송신기 · Python 테스트 | `/home/itkwon/limbo_ros2_workspace/final_team7/dashboard` |
| UI 설치·빌드·개발 서버 · UI 단위 테스트 · 브라우저 테스트 | `/home/itkwon/limbo_ros2_workspace/final_team7/dashboard/ui` |

**각 명령 블록의 첫 `cd`부터 실행한다.** 따라서 새 터미널을 어느 디렉터리에서 열었든 같은 순서로 실행할 수 있다. 터미널마다 현재 디렉터리는 독립적이므로, 다른 터미널에서 수행한 `cd`는 적용되지 않는다. 다른 PC에 복제했다면 아래 명령의 `/home/itkwon/limbo_ros2_workspace/final_team7` 부분을 해당 PC의 저장소 절대 경로로 바꾼다.

예를 들어 저장소가 `/home/david/limbo`에 있다면 위 경로를 모두 `/home/david/limbo`로 바꾼다. `node --version`이 22 또는 24인지 확인한 다음 UI 명령을 실행한다. 기존 Node 18에서는 이 UI의 설치·빌드를 진행하지 않는다.

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

## Dashboard와 Bridge 한 번에 실행

UI 빌드와 `limbo_bringup`·`limbo_telemetry_bridge` 빌드가 끝난 뒤, 저장소 루트에서 다음처럼 실행한다. `start_dashboard.launch.py`가 FastAPI 서버(127.0.0.1:8000)와 telemetry Bridge를 함께 관리한다. 별도 UI 개발 서버는 필요 없다.

```bash
cd ~/limbo
source /opt/ros/jazzy/setup.bash
source limbo/install/setup.bash
ros2 launch limbo_bringup start_dashboard.launch.py
```

서버가 준비되면 기본 브라우저에서 `http://127.0.0.1:8000/`을 자동으로 연다. 자동 열기를 끄려면 `open_browser:=false`를 붙인다.

종료는 해당 터미널에서 `Ctrl+C`. 한 프로세스가 먼저 끝나도 launch가 다른 프로세스를 정리한다. 기존 Dashboard 서버나 Bridge가 실행 중이면 먼저 종료해야 한다. 기본 경로는 이 저장소의 `dashboard/`와 `relay_prog/`이며, 다른 배치에서는 `repo_root:=/absolute/path/to/repo`를 지정한다. `ros_domain_id` 기본값은 launch 파일에 지정된 `97`이다. 다른 도메인을 사용할 때는 `ros_domain_id:=번호`로 바꾼다. 주행 시작 때 Bridge가 띄우는 순찰 노드도 Bridge 프로세스의 `ROS_DOMAIN_ID`를 그대로 쓴다(Dashboard 서버에는 ROS 설정이 없다).

## 실행·종료

UI 빌드 완료 후, **서버는 `dashboard/ui`가 아닌 `dashboard` 디렉터리에서 실행한다.** 이 서버 하나가 빌드된 실제 화면과 데모 화면을 모두 제공하므로 일반 실행에는 별도 UI 터미널이 필요 없다.

```bash
cd /home/itkwon/limbo_ros2_workspace/final_team7/dashboard
.venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8000 --workers 1
```

실제 수신: <http://127.0.0.1:8000/> · 가상 제어: <http://127.0.0.1:8000/demo>.
종료는 `Ctrl+C`. 서버는 빌드된 UI를 직접 제공한다. `--workers`는 반드시 1이며, 상태 공유 저장소와 명령 대기열이 프로세스 메모리에 있으므로 다중 worker를 사용하지 않는다. 기본 `config.json`은 로컬 개발용이라 로봇 토큰 없이 연다(`allow_no_robot_token: true`). 서버 자체에는 화면 로그인이 없으므로 `127.0.0.1` 밖으로 열 때는 아래 「로봇 토큰과 인터넷 공개」를 따른다.

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

## 로봇 토큰과 인터넷 공개

서버의 경로는 두 종류다.

| 종류 | 경로 | 보호 |
|---|---|---|
| 로봇용 (Bridge가 부름) | `POST /api/v1/telemetry`, `GET /api/v1/commands/next`, `POST /api/v1/commands/{id}/claim`, `POST /api/v1/commands/{id}/result` | 서버가 **공유 토큰**으로 검사: `Authorization: Bearer <토큰>`. 없거나 틀리면 401 `unauthorized` |
| 브라우저용 | 화면(`/`, `/demo`, `/assets`), 나머지 `/api/v1/*`(명령 요청·상태·WebSocket·지도·waypoint), `/healthz` | 서버는 검사하지 않는다. 인터넷에 열 때는 **앞단 Caddy의 basic auth**로 막는다(로봇용 4경로는 basic auth에서 빼고 토큰만). 배포는 `docs/AWS_DEPLOY.md` |

토큰은 서버와 Bridge가 **같은 값**을 쓴다. git에 올리지 않는다. 16자 이상, 공백 없이. 만들기:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

서버가 토큰을 읽는 순서: 환경 변수 `ROBOT_TOKEN` → `config.json`의 `robot_token_file`(파일 내용, 저장소 루트 기준 상대경로 또는 절대경로). 둘 다 없으면 `allow_no_robot_token: true`일 때만 토큰 없이 열고, 아니면 **서버가 시작하지 않는다**(`RuntimeError: Set ROBOT_TOKEN or robot_token_file`). 파일이 없거나 비었거나 짧아도 시작하지 않는다.

Bridge가 토큰을 읽는 순서: 환경 변수 `LIMBO_ROBOT_TOKEN` → `bridge.yaml`의 `token_file`. 둘 다 없으면 헤더를 보내지 않는다. 서버가 401을 돌려주면 Bridge는 10초 간격으로 다시 시도하며 `server rejected the robot token` 경고를 남긴다. 토큰을 `http://`로 다른 컴퓨터에 보내면(평문) 시작할 때 경고한다. 인터넷 너머는 `https://`를 쓴다.

**로컬 개발(127.0.0.1)**: 기본 설정 그대로면 토큰 없이 된다(서버 `allow_no_robot_token: true`, Bridge `token_file: null`). 로컬에서 토큰까지 시험하려면:

```bash
# 저장소 루트에서. relay_prog/state/는 git에서 제외됨
mkdir -p relay_prog/state
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > relay_prog/state/robot_token
chmod 600 relay_prog/state/robot_token

# 서버 (dashboard에서): 토큰을 환경 변수로
cd dashboard
ROBOT_TOKEN=$(cat ../relay_prog/state/robot_token) .venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8000 --workers 1

# Bridge (다른 터미널, 저장소 루트에서): 환경 변수로 주거나 bridge.yaml에 token_file: relay_prog/state/robot_token
LIMBO_ROBOT_TOKEN=$(cat relay_prog/state/robot_token) ros2 run limbo_telemetry_bridge bridge --config relay_prog/src/limbo_telemetry_bridge/config/bridge.yaml

# 확인: 토큰 없으면 401, 있으면 422(본문 검사까지 감)
curl -s -o /dev/null -w "%{http_code}\n" -X POST -H 'content-type: application/json' -d '{}' http://127.0.0.1:8000/api/v1/telemetry
curl -s -o /dev/null -w "%{http_code}\n" -X POST -H 'content-type: application/json' -H "Authorization: Bearer $(cat ../relay_prog/state/robot_token)" -d '{}' http://127.0.0.1:8000/api/v1/telemetry
```

환경 변수 `ROBOT_TOKEN`이 있으면 `allow_no_robot_token: true`여도 토큰을 검사한다. 가상 송신기도 `--token`(기본값은 환경 변수 `ROBOT_TOKEN`)으로 헤더를 붙인다.

## 인터넷(AWS) 배포

컨테이너 두 개(관제 서버 + Caddy)로 올린다. 처음부터 끝까지의 순서는 [docs/AWS_DEPLOY.md](../docs/AWS_DEPLOY.md)를 따른다.

| 파일 | 내용 |
|---|---|
| `Dockerfile` | UI 빌드(node 24, pnpm lockfile 그대로) → Python 3.12 서버. `uvicorn --workers 1` 고정, root 아닌 사용자. 빌드 context는 저장소 루트(지도·기본 waypoint가 `limbo/`에 있음), 넣는 파일은 `Dockerfile.dockerignore`가 고름 |
| `docker-compose.yml` | `dashboard`(8000, 밖으로 안 엶) + `caddy`(80·443). 볼륨: `waypoints`(편집한 waypoint), `caddy_data`(인증서) |
| `Caddyfile` | HTTPS 자동 발급, 화면·브라우저 API는 basic auth, 로봇용 4경로와 `/healthz`는 basic auth 없이 서버로(로봇은 토큰) |
| `.env.example` | `DOMAIN`, `BASIC_AUTH_USER`/`BASIC_AUTH_HASH`, `ROBOT_TOKEN`, `MAP_YAML`, `INITIAL_WAYPOINTS`. 복사해 `.env`로(git 제외) |
| `deploy/config.json`, `deploy/entrypoint.sh` | 컨테이너용 설정(waypoint는 `/data/waypoints.yaml`, `allow_no_robot_token: false`). 처음 시작 때 볼륨이 비었으면 `INITIAL_WAYPOINTS`를 복사하고, `MAP_YAML`을 설정에 끼운 뒤 서버 실행 |

## 주행 시작·정지·재개·종료

실제 화면의 제어 버튼은 Bridge가 보고한 순찰 상태에 따라 **주행 시작 → 주행 정지 → 주행 재개**로 바뀐다. 정지는 기존 `/patrol/pause` 서비스를 이용하는 **일시정지**이며 노드를 종료하지 않는다. 재개는 `/patrol/resume`으로 현재 순찰을 이어 간다. 주행 정지는 일시정지, **순찰 종료**는 노드 종료다.

네 동작 모두 같은 명령 통로를 쓴다: 화면 → `POST /api/v1/commands` → 서버 대기열 → Bridge가 `commands/next`로 가져가 `claim` → 실행 → `result` 보고 → 서버가 텔레메트리로 확인. 서버는 subprocess도 ROS도 쓰지 않는다. 로봇은 서버로 나가는 HTTP(S) 연결만 쓰므로 로봇 쪽에 들어오는 포트를 열 필요가 없다.

- **주행 시작**(`start`): 서버는 명령을 만드는 순간 `waypoints_yaml`을 읽어 검사하고, waypoint 목록·`revision`·지도 범위를 명령에 담는다(서버 YAML이 원본). Bridge는 받은 목록을 서버와 같은 규칙으로 다시 검사한 뒤, 로봇 컴퓨터의 `patrol_launch.waypoint_dir/dashboard_waypoints.yaml`에 원자적으로 저장하고(임시 파일 → `os.replace`) 그 **절대 경로**를 `waypoints` 파라미터로 넘겨 `patrol_node`를 띄운다. 순찰 노드가 `waiting_localization` 또는 `patrolling`을 보고하면 성공이다(기본 60초, `command_start_confirm_timeout_s`). 노드가 그 전에 끝나면 종료 코드와 로봇 쪽 로그 경로를 담아 실패로 끝낸다.
- **순찰 종료**(`stop`): Bridge가 **자기가 띄운** 노드에만 SIGTERM을 보낸다. 순찰 노드는 진행 중인 Nav2 목표를 취소하고 취소 결과를 받은 뒤 끝난다. Bridge가 노드 종료를 보고하거나 순찰 상태가 사라지면 성공이다(기본 30초, `command_stop_confirm_timeout_s`). 다른 터미널에서 띄운 노드는 끌 수 없다(버튼에 「다른 곳에서 띄운 순찰 노드는 여기서 끌 수 없습니다」).
- **중복 실행 거부**: 이미 순찰 노드가 돌고 있으면 시작 버튼이 잠기고, 서버도 409 `patrol_already_running`으로 거절한다. Bridge는 로봇 컴퓨터의 `/proc`를 2초마다 검사해 다른 터미널에서 띄운 `patrol_node`도 `other_patrol_running`으로 보고하고, 실행 직전에도 다시 검사해 있으면 `rejected`(사유 `patrol_already_running`)로 알린다.
- 노드가 끝났는데 Bridge에 오래된 순찰 상태가 남아 있어도(`launcher.state`가 `exited`) 주행 버튼은 **주행 시작**으로 돌아온다.
- **Bridge를 끄면 Bridge가 띄운 순찰 노드도 SIGTERM으로 같이 끈다**(Bridge 없이는 화면에서 일시정지도 할 수 없으므로). 15초 안에 안 끝나면 그때만 SIGKILL.
- Bridge 쪽 설정(ROS setup 경로, 워크스페이스, waypoint 저장 디렉터리, `use_sim_time`)은 [relay_prog README](../relay_prog/README.md) 「설정」의 `patrol_launch`를 본다.

일반 터미널에서 `ros2 run limbo_patrol patrol_node`를 파라미터 없이 실행하면 설치된 패키지의 `test_waypoints.yaml`을 읽는다. 화면에서 편집한 경로는 주행 시작 때 로봇으로 보내지므로 그 수동 실행에는 반영되지 않는다. 수동 실행에서도 편집한 경로를 쓰려면 한 번 화면에서 시작한 뒤 생긴 `-p waypoints:=<저장소>/relay_prog/state/waypoints/dashboard_waypoints.yaml`을 지정한다.

## Waypoint 지도 편집

실제 화면(`/`)에서 주행 제어 버튼과 순찰 종료 버튼 아래의 Waypoint 목록을 조회하고 `새 지점 만들기`, `이름 변경`, `위치 교체`, `삭제`를 사용할 수 있다. 목록의 ⋮⋮ 손잡이를 다른 행으로 끌어 놓으면 순서가 바뀐다. 마지막 지점은 `stop`이어야 하므로 이를 어기는 순서 변경은 저장하지 않는다. 추가하거나 위치를 바꿀 때 지도를 클릭하여 좌표를 고른다. 저장하면 서버 컴퓨터의 `config.json`의 `waypoints_yaml` 파일(원본)에 반영되고 목록과 지도도 갱신된다. 로봇에는 다음 **주행 시작** 때 명령에 실려 전달된다. 기본 설정은 `limbo/src/limbo_patrol/config/test_waypoints.yaml`이다. 다른 월드 또는 순찰 파일을 쓸 때는 `map_yaml`과 `waypoints_yaml`을 실제 실행 설정에 맞추고 Dashboard 서버를 다시 시작해야 한다.

순찰 노드는 시작할 때 waypoint 파일을 한 번 읽어 메모리에 보관한다. 주행 중과 일시정지 중에는 waypoint 추가·이름 변경·위치 교체·삭제·순서 변경을 사용할 수 없고, 버튼에 마우스를 올리면 "주행 완료 후 변경 가능합니다"가 표시된다. 저장 API도 409 `patrol_active`로 거절한다. 판단 근거는 Bridge가 보고한 상태다: Bridge가 띄운 노드가 실행 중이거나, 다른 곳에서 띄운 노드가 있거나, 순찰 상태가 활성(위치 확인 중·순찰 중·멈추는 중·일시정지)인데 Bridge가 띄운 노드가 끝났다고 하지 않은 경우. 주행 시작·순찰 종료 요청을 처리하는 동안에도 잠근다(보낸 경로와 파일이 어긋나지 않게). 순찰이 완료되거나 노드가 종료된 뒤 편집한 경로는 다음 순찰 시작 시 적용된다. 파일은 저장 중 문제가 생겨도 기존 내용을 지키도록 원자적으로 교체한다. 다른 편집자가 먼저 파일을 바꾸면 저장 요청이 거절되고 화면의 목록을 다시 불러온다. 마지막 지점은 `stop`이어야 하므로 마지막 정지 지점을 바로 삭제할 수 없다. 새 `pass` 지점은 마지막 정지 지점 앞에 삽입된다. 새 지점의 `yaw`와 `wait_sec`는 0으로 저장하고, 기존 지점을 이동할 때 기존 값은 유지한다.

API: `GET /api/v1/waypoints`로 목록과 `revision`을 읽고, `PUT /api/v1/waypoints`에 `revision` 및 변경 작업을 보낸다. 작업은 `add`(`waypoint`의 `name/type/x/y`), `move`(`name/x/y`), `delete`(`name`), `rename`(`name/new_name`), `reorder`(`order`에 현재 이름 전체를 원하는 순서로 지정)다. `GET /api/v1/map`도 저장된 목록을 다시 읽는다.

`/demo`에서는 같은 조작을 시연할 수 있다. 데모 변경은 브라우저 메모리에만 유지되며 새로고침하면 초기화된다. 실제 YAML은 수정하지 않는다.

## 설정과 상태 해석

기본 [config.json](config.json)을 수정하거나 `DASHBOARD_CONFIG`로 다른 JSON 경로를 지정한 후 서버를 다시 실행한다. 실행 디렉터리는 `/home/itkwon/limbo_ros2_workspace/final_team7/dashboard`다. 아래 `/absolute/path/config.json`은 사용할 설정 파일의 실제 절대 경로로 바꾼다.

```bash
cd /home/itkwon/limbo_ros2_workspace/final_team7/dashboard
DASHBOARD_CONFIG=/absolute/path/config.json .venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8000 --workers 1
```

| 설정 | 기본값 |
|---|---|
| `robot_id` | `LIMBO-01`. 기본 로봇: 항상 목록에 있고 화면이 처음 여는 로봇 (「여러 로봇」) |
| `robots` | `{}`. 미리 등록할 로봇과 그 로봇의 `map_yaml`·`waypoints_yaml`. 생략한 항목은 공통값 |
| `max_robots` | 16. 자동 등록 상한, 넘으면 텔레메트리가 429 `too_many_robots` |
| `bridge_delay_s` / `bridge_disconnect_s` | 3초 / 10초, 정확한 경계부터 적용 |
| `topic_delay_s` | odom, lidar_raw, lidar_filtered, camera_raw 각각 3초 |
| `browser_delay_s` | 3초. 1초 갱신 간격보다 커야 함 |
| `linear_threshold_mps` / `angular_threshold_radps` | 0.05 m/s / 절대값 0.05 rad/s |
| `alert_limit` | 100, 1~100 |
| `command_ttl_s` | 5초. 이 안에 Bridge가 가져가지 않으면 `expired`(실행 안 함) |
| `command_response_timeout_s` | 5초. 전달(또는 claim) 후 로봇 응답 제한, 넘으면 `no_response` |
| `command_confirm_timeout_s` | 5초. 응답 후 순찰 상태로 확인하는 제한, 넘으면 `unconfirmed` |
| `command_start_response_timeout_s` / `command_start_confirm_timeout_s` | 10초 / 60초. 주행 시작 전용 (노드 기동·위치 확인을 기다림) |
| `command_stop_response_timeout_s` / `command_stop_confirm_timeout_s` | 10초 / 30초. 순찰 종료 전용 (Nav2 목표 취소 후 노드 종료를 기다림) |
| `map_yaml` | `limbo/src/limbo_navigation/maps/human_test_map.yaml`. 생략하면 지도 API가 404 |
| `waypoints_yaml` | `limbo/src/limbo_patrol/config/test_waypoints.yaml`. 순찰 경로의 원본. 주행 시작 명령에 실려 로봇으로 간다 |
| `robot_token_file` | `null`. 로봇용 경로 토큰 파일. 환경 변수 `ROBOT_TOKEN`이 우선 (「로봇 토큰과 인터넷 공개」) |
| `allow_no_robot_token` | 기본 `config.json`은 `true`(로컬 개발), 설정에서 빼면 `false`. 토큰이 없을 때 로봇용 경로를 열어 둘지. **인터넷에 열 때는 `false`** |

예전 `patrol_ros_domain_id`·`patrol_use_sim_time`은 지웠다(서버가 순찰 노드를 띄우지 않으므로). 설정 파일에 남아 있으면 서버가 시작하지 않으니 지운다. 같은 역할은 Bridge 프로세스의 `ROS_DOMAIN_ID`와 `bridge.yaml`의 `patrol_launch.use_sim_time`이 한다.

`map_yaml`·`waypoints_yaml`은 절대경로이거나 **저장소 루트 기준** 상대경로다. 지도는 8비트 P5 PGM만 읽으며 서버 시작 때 한 번만 읽는다. 읽기에 실패하면 서버는 그대로 뜨고 로그에 `map not loaded`를 남기며, 화면에는 「서버에 지도가 설정되지 않았습니다」가 보인다. 지도나 waypoint를 바꾸면 서버를 다시 실행한다.

적용 설정은 서버 스냅샷으로 UI에 전달된다. 토픽별 기준은 실제 발행 주기를 측정한 뒤 조정한다. motion freshness는 odom 지연 기준을 motion 자체 age에 적용한다. ROS 헤더는 freshness 판정에 사용하지 않는다. 현재 세션의 마지막 유효 속도는 별도로 보존하고 현재 값이 없으면 `마지막 수신 값`으로만 표시한다.

- Bridge 연결: 유효한 새 스냅샷의 서버 수신 이후 **단조 증가 시간**으로 판정한다. 중복·역순·잘못된 요청은 heartbeat를 갱신하지 않는다.
- 토픽 수신: Bridge가 전달한 `age_ms`에 서버 수신 이후 단조 증가 경과 시간을 더한다. heartbeat가 와도 센서 수신으로 간주하지 않는다.
- 브라우저 연결: WebSocket 종료·오류 또는 상태 갱신 지연 시 현재 상태를 확인 불가로 덮어 표시한다. 1·2·4·8·10초 간격으로 재접속하고 전체 스냅샷을 받은 뒤 복구한다. 서버 내부 Bridge 판정은 바꾸지 않는다.
- 시각은 UTC 기록을 Asia/Seoul로 표시하며, 브라우저는 서버 age에 `performance.now()` 경과만 더한다. 탭 복귀 시 현재 표시를 보류하고 HTTP 전체 상태를 다시 조회한다.
- `—`는 미수신/미확인이다. 유효한 0은 `0.00 m/s`다. 수신 중은 데이터 도착 여부이며 센서 성능 판정이 아니다. 속도 0이나 Bridge 재연결은 명령 성공 근거가 아니다.
- 상태 한 줄 요약: 서버 문제·로봇 연결 끊김이면 `연결 끊김`, 연결 확인 중·수신 지연이나 수신 중이 아닌 토픽이 있으면 `확인 필요`(해당 토픽 이름 표시), 그 외는 `정상`.
- 순찰 카드: v2 `patrol.state`(위치 확인 중·순찰 중·멈추는 중·일시정지·순찰 완료·순찰 실패)와 다음 목표를 보인다. 연결이 원활하지 않으면 회색 `(마지막 상태)`로 표시한다. 받은 적은 있는데 상태가 비면 `순찰 상태 확인 불가`(순찰 노드 꺼짐)다. 순찰 노드가 사유로 이동 실패를 알리면 `순찰 중 · 이동 다시 시도 (n/m)` 또는 `이동 실패 · 확인 후 재개`로 바꾸고, 서버가 알림도 남긴다(순찰이 다시 진행되면 닫힘).
- 지도: 로봇 위치는 v2 `pose`(지도 좌표)로 그리며, 원은 위치 표준편차의 2배다. pose age가 odom 지연 기준 이상이거나 연결이 불확실하면 `위치 확인 불가 · 마지막 위치`로 흐리게 표시한다. 「로봇 따라가기」는 로봇 중심 10 m 범위를 보인다.
- 버튼 잠금: 서버 문제나 로봇 연결이 `연결됨`이 아니면 모두 잠긴다. 주행 시작·순찰 종료는 Bridge가 v3 `launcher`를 보고해야 열리고, 순찰 종료는 Bridge가 띄운 노드가 실행 중일 때만 열린다. 처리 중인 요청이 있어도 잠긴다. 일시정지는 순찰 노드가 이미 `paused`·`pausing`이라고 알린 경우만 잠그며, **순찰 상태를 모를 때(v1 연결, 순찰 노드 꺼짐)는 열어 둔다**(멈추는 쪽은 막지 않음). 순찰 재개는 순찰 노드의 `has_resumable_task`가 참일 때만 열린다(속도로 추정하지 않음).
- 명령 결과: 서버 단계 `queued → delivered → accepted → confirmed`를 화면의 3단계(서버 접수·로봇 응답·상태 확인)로 보인다. **성공은 서버가 `confirmed`라고 판정한 것만**이다. 서버는 명령 이후 Bridge가 센 순찰 상태 수신 횟수가 늘고, 재개는 `patrolling`, 일시정지는 `paused`이면서 odom 기준 정지 속도, 주행 시작은 `waiting_localization`·`patrolling`일 때 확인한다. 순찰 종료는 Bridge의 노드 종료 보고나 순찰 상태가 사라진 것으로 확인한다. 그 밖의 결과는 `rejected`·`service_unavailable`·`expired`(실패), `no_response`·`unconfirmed`·`connection_lost`(확인 불가)다. 자동 재전송하지 않으며 결과는 1분 뒤 한 줄로 접힌다.

## 여러 로봇

서버 하나가 여러 로봇의 상태를 받는다. 로봇마다 relay_prog `bridge.yaml`의 `robot_id`만 다르게 주면 된다(토큰은 같아도 됨, Bridge 코드 변경 없음).

- **자동 등록**: 토큰이 맞는 텔레메트리가 처음 보는 `robot_id`로 오면 그 로봇을 목록에 넣는다. `robot_id`는 1~64자 영문·숫자·`.`·`_`·`-`만(그 밖은 422). `max_robots`를 넘으면 429. 자동 등록한 로봇은 서버를 다시 시작하면 목록에서 사라진다(설정의 `robot_id`·`robots`는 연결 전에도 `연결 확인 중`으로 보임)
- **로봇마다 따로**: 연결 판정·순찰 상태·명령(한 로봇에 하나)·알림·세션. 한 로봇에 낸 명령은 그 로봇의 Bridge만 가져간다
- **지도·waypoint**: `robots`에 적은 로봇은 그 파일, 나머지는 공통 `map_yaml`·`waypoints_yaml`. 같은 waypoint 파일을 쓰는 로봇 중 하나라도 순찰 중(또는 시작·종료 처리 중)이면 그 파일 편집이 잠긴다

```json
"robot_id": "LIMBO-01",
"robots": { "LIMBO-02": { "waypoints_yaml": "limbo/src/limbo_patrol/config/limbo02_waypoints.yaml" } }
```

화면: 헤더의 로봇 이름(`LIMBO-01 ▾`)을 누르면 로봇 목록과 각 연결 상태가 열린다. 고르면 화면 전체(순찰·이동·지도·제어·알림·센서)가 그 로봇으로 바뀌고, 주소에 `?robot=LIMBO-02`가 붙는다(이 브라우저에 기억함). 서버가 모르는 로봇이 주소에 있으면 기본 로봇으로 돌아간다. 진행 중이던 요청은 원래 로봇에서 계속 처리된다. 데모(`/demo`)는 로봇 하나만 보인다.

지도에는 **같은 지도 파일을 쓰는 다른 로봇**도 회색 화살표와 이름으로 그린다(선택한 로봇은 빨간 화살표). 연결이 늦거나 위치가 오래되면 흐리게 그린다. 회색 화살표를 누르면(키보드는 Tab 후 Enter) 그 로봇으로 전환한다. 지점 편집 중에는 지도 클릭이 위치 선택이라 누를 수 없다. 다른 로봇의 위치는 1초마다 갱신된다(서버 주기 갱신). 지도가 다른 로봇은 좌표가 맞지 않아 그리지 않는다.

## 인터페이스와 구조

| 경로 | 역할 |
|---|---|
| `POST /api/v1/telemetry` | 텔레메트리 v1, v2(`patrol`·`pose` 추가) 또는 v3(`launcher` 추가), 최대 UTF-8 8192바이트 |
| `GET /api/v1/robots` | `{"default": "LIMBO-01", "robots": [{"robot_id", "status", "last_received_at"}]}`. 헤더 로봇 목록용 |
| `GET /api/v1/state` | `?robot_id=`(생략하면 기본 로봇, 모르면 404 `unknown_robot`). 전체 현재 판정, 마지막 값, 순찰·위치, 마지막 명령, 설정, 알림 |
| `POST /api/v1/stream-ticket` | WebSocket 일회용 입장표 `{"ticket"}` (30초 유효). basic auth 뒤에 있음 |
| `WS /api/v1/stream` | `?ticket=`(필수, 없거나 틀리면 거절) `&robot_id=`(모르면 4404로 닫음). 연결 즉시, 새 유효 수신·명령 변화 시, 1초 타이머마다 전체 상태. Safari(iPhone)는 WebSocket에 basic auth를 싣지 않으므로 Caddy는 이 경로만 basic auth 없이 넘기고 입장표로 검사한다 |
| `POST /api/v1/commands` | 화면 → 서버. `{"command":"pause"\|"resume"\|"start"\|"stop", "robot_id"?: "LIMBO-02"}`(생략하면 기본 로봇, 모르면 404 `unknown_robot`). 202와 요청 정보, 처리 중이면 409 `command_in_progress`, 로봇 연결이 `connected`가 아니면 409 `bridge_not_connected`. start·stop은 추가로 409 `bridge_unsupported`(이전 Bridge)·`patrol_already_running`·`patrol_not_running`·`invalid_route`, 503 `waypoints_unavailable` |
| `GET /api/v1/commands/next` | Bridge → 서버. `robot_id`, `bridge_session_id`, `wait_s`(최대 10초 long poll). 명령이 있으면 `request_id`·`command`·`ttl_ms`(start는 `route`도: `revision`·`bounds`·`waypoints`), 없으면 204(아직 텔레메트리를 보내지 않은 로봇도 204). 현재 세션에 한 번만 내준다 |
| `POST /api/v1/commands/{request_id}/claim` | Bridge가 서비스를 부르기 직전 아직 유효한지 확인. 허락되면 응답 제한을 이 시각부터 다시 센다. 끝난 명령이거나 다른 로봇의 명령이면 409 `command_closed`·`unknown_robot` |
| `POST /api/v1/commands/{request_id}/result` | Bridge의 결과 보고(`accepted`·`rejected`·`no_response`·`service_unavailable`·`expired`). 끝난 명령의 늦은 보고는 결과를 바꾸지 않는다 |
| `GET /api/v1/map` | `?robot_id=`. 그 로봇의 지도 메타데이터(`image`에 `?robot_id=`가 붙음)(해상도·원점·크기·waypoint). 지도 미설정 시 404 `map_not_configured` |
| `GET /api/v1/map.png` | `?robot_id=`. SLAM PGM을 변환한 회색조 PNG |
| `GET /healthz` | `{"status":"ok"}`, 서버 생존 확인만 의미 |

명령 API 본문도 텔레메트리와 같이 `application/json`, 8192바이트 이하만 받는다. 명령은 한 번에 하나만 처리하며 마지막 명령은 다음 명령 전까지 스냅샷에 남는다.

스냅샷에는 `server_run_id`, `revision`, `server_utc`, `robot_id`, `bridge`, `topics`, `motion`, `alerts`, `settings`, `patrol`, `pose`, `command`, `map_available`, `launcher`, `patrol_running`, `robots`(서버가 아는 로봇 전체와 연결 상태, 같은 지도를 쓰는 다른 로봇은 `pose`: x·y·yaw·`age_s`·`stale`)가 포함된다. v1 Bridge면 `patrol`·`pose`, v1·v2 Bridge면 `launcher`가 null이다. `patrol_running`은 서버가 판단한 "순찰 노드가 돌고 있음"(시작 거절·편집 잠금 기준)이다. `motion.current`와 `motion.last_valid`, 토픽 `receive_hz`와 `last_receive_hz`를 구분한다. `patrol`·`pose`·`command`의 `age_s`는 서버가 잰 값이며 브라우저 시계와 비교하지 않는다. 이전 run의 revision과 새 서버 revision을 비교하지 않는다.

스키마는 누락·추가 필드, 숫자 강제 변환, bool 숫자, NaN/Infinity, 음수 범위, 비UTC 시각, null 관계를 검사한다. v2는 `patrol`·`pose`가 모두 있어야 하고 v1은 둘 다 없어야 한다. motion은 최신 odom과 같은 시각·age여야 한다. 오류 코드는 Bridge PRD를 따른다. 종료된 세션은 최근 100개만 기억한다. 느린 WebSocket에는 대기 스냅샷 한 개만 유지하고 전송이 3초 이상 막히면 연결을 닫는다. UI 빌드가 없으면 `/`와 `/demo`는 안내 JSON과 503을 반환한다.

아래 파일 구조의 기준 디렉터리는 `dashboard/`다.

```text
server/models.py     텔레메트리 v1·v2, 명령, 설정 검증
server/state.py      시계·세션·판정·알림, 명령 단계·확인 판정, 순찰 이동 실패 알림
server/mapdata.py    지도 PGM → PNG 변환, waypoint 읽기
server/app.py        FastAPI, 주기 갱신, HTTP/WebSocket, 명령·지도 API, 정적 UI
ui/src/live.ts       실제 공급자와 브라우저 연결 감시
ui/src/control.ts    실제 제어: 명령 전송, 서버 단계 → 화면 3단계, 버튼 잠금 사유
ui/src/map.ts        지도 좌표 → 그림 좌표 변환
ui/src/demo.ts       별도 가상 상태·순찰·위치·알림 공급자, 데모 지도
ui/src/commands.ts   명령 이름·결과 문구, 데모용 요청 ID 기반 3단계 상태 머신
ui/src/App.tsx       공통 화면·상태 요약·순찰·지도·제어·모달
tests/               서버 시험 (test_server.py 수신, test_control.py 명령·v2·지도, test_robots.py 여러 로봇)
tools/               개발용 송신기 및 통합 검증 도구
```

## 가상 송신기로 독립 검증

가상 송신기는 개발 도구다. **텔레메트리 v1만 보내므로** 순찰 카드·지도 위 로봇·실제 제어는 검증하지 않는다. 순찰 상태가 없으므로 순찰 재개는 잠기지만 일시정지는 눌러서 서버에 요청을 만들 수 있다. 그러나 송신기는 `commands/next`로 명령을 가져가거나 실행하지 않으므로, 그 요청은 `command_ttl_s`(5초) 뒤 `expired`(「정지 요청 실패: 로봇에 제때 전달되지 않아 실행 안 함」)로 끝난다. 이 부분은 서버 시험 `tests/test_control.py`, UI 단위 시험, `/demo`, 실제 Bridge 통합으로 확인한다. **실제 Bridge와 함께 같은 서버에 보내지 않는다.** v1 계약에는 실제/가상 출처 필드가 없으므로 수신 화면은 전송자의 진위를 판별할 수 없다. 반드시 Bridge가 연결되지 않은 전용 서버를 사용한다. `/demo`와는 별개의 테스트다.

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

`/demo` 상단에서 화면 상태(정상 수신·일부 토픽 지연·로봇 상태 수신 지연·로봇 연결 끊김·최초 접속·서버 연결 문제), 가상 순찰 상태, **일시정지·순찰 재개 각각의** 결과와 두 제한 시간을 선택한다. 데모 지도는 그림 없이 `test_waypoints.yaml`과 같은 배치의 순찰 지점만 그리며, 가상 로봇은 순찰 중일 때 1초에 0.5 m씩 다음 지점으로 움직인다. 일시정지에 성공하면 가상 순찰이 `일시정지`로 바뀐다. 전송 완료는 비동기 0.1초, 로봇 응답은 그 후 0.5초, 확인 이벤트는 응답 후 1초다. 기본 응답/확인 제한 시간은 각각 5초다.

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

첫 번째 터미널에서는 위 「실행·종료」 명령으로 `dashboard` 디렉터리에서 Dashboard를 8000에 실행한다. **두 번째 터미널에서는 저장소 루트 `/home/itkwon/limbo_ros2_workspace/final_team7`로 이동한 뒤** 아래 명령으로 Bridge를 실행한다. 기존 로봇과 같은 ROS_DOMAIN_ID/discovery 환경을 사용하며, 기존 Mock receiver와 가상 송신기는 종료한다. 아래 명령은 `limbo/`와 `relay_prog/`가 빌드되어 있다는 전제다. Bridge는 순찰 상태 메시지 `limbo_interfaces/msg/PatrolState`를 쓰므로 **Jazzy → `limbo/` 설치본 → `relay_prog/` 설치본** 순서로 source한다(빠뜨리면 `ModuleNotFoundError: No module named 'limbo_interfaces'`). 자세한 빌드·문제 해결은 [relay_prog README](../relay_prog/README.md)를 따른다.

```bash
cd /home/itkwon/limbo_ros2_workspace/final_team7
source /opt/ros/jazzy/setup.bash
source limbo/install/setup.bash
source relay_prog/install/setup.bash
ros2 run limbo_telemetry_bridge bridge --config relay_prog/src/limbo_telemetry_bridge/config/bridge.yaml
```

Bridge는 텔레메트리 v2(센서 4개 + `/patrol/state` 순찰 상태 + TF `map → base_footprint` 위치, `/amcl_pose` 불확실성)를 보내고, `commands/next`를 long poll로 기다렸다가 `/patrol/pause`·`/patrol/resume`(`std_srvs/srv/Trigger`)을 부른다. 따라서 순찰 카드·지도 위치·버튼까지 보려면 시뮬레이션(또는 실물)에서 navigation과 순찰 노드가 함께 실행 중이어야 한다. 순찰 노드가 꺼져 있으면 순찰 카드는 `순찰 상태 확인 불가`, 명령은 `service_unavailable`로 끝난다. 토픽·서비스 이름과 제한 시간은 `bridge.yaml`의 `control:` 항목에서 바꾼다.

다른 서버 주소를 사용할 경우 기존 설정을 저장소 루트 기준 `dashboard/artifacts/bridge.yaml` 등에 복사하고 그 파일의 `server_url`을 변경하여 `--config`로 전달한다. Bridge 프로그램이나 기존 설정을 변경할 필요가 없다.

실제 ROS2 테스트 발행자 → 기존 Bridge → Dashboard → Chrome 자동 검증은 **저장소 루트 `/home/itkwon/limbo_ros2_workspace/final_team7`에서** 다음으로 실행한다. 도구가 테스트 서버·Bridge·발행자·브라우저를 준비하므로 검증용 프로세스를 다른 터미널에서 따로 실행할 필요가 없다. 기존 Bridge Python/ROS 메시지 및 UI 테스트 의존성과 빌드된 UI를 사용한다. `--domain`은 운영 도메인과 겹치지 않는 값을 직접 선택한다.

```bash
cd /home/itkwon/limbo_ros2_workspace/final_team7
source /opt/ros/jazzy/setup.bash
source limbo/install/setup.bash
PYTHONDONTWRITEBYTECODE=1 CHROME_PATH=/opt/google/chrome/chrome \
  relay_prog/venvs/bridge/bin/python dashboard/tools/validate_bridge.py --domain 91
```

Node.js가 PATH에 없으면 `--node /absolute/path/to/node`를 추가한다. 도구는 임시 서버 포트, 임시 Bridge 설정, 별도 ROS 도메인 및 `dashboard/artifacts/` 로그를 사용하고 종료 시 자식 프로세스를 정리한다. 헤더 0·역행, 0 속도·회전·무효 odom·재수신을 확인하고 발행 직후부터 브라우저 표시 확인까지 2초 미만인지 측정한다. 실제 Gazebo 주행이나 실물 로봇 검증을 대신하지 않는다. 이 도구는 v1 시절에 만든 것으로 센서 수신·속도 표시만 확인하며, 순찰 상태·위치·일시정지/재개는 검증하지 않는다. 제어 기능의 시뮬레이션 시험 절차와 결과는 [관제 화면 설계 A](../docs/CONTROL_SCREEN.md#a-일시정지순찰-재개)에 있다.

검증 결과 및 미검증 항목은 [검증 보고서](docs/VALIDATION.md)에 구분해 기록한다. 이 보고서는 v1 기준이며, 관제 기능 추가 뒤의 시험 기록은 [CHANGELOG](../docs/CHANGELOG.md)와 [관제 화면 설계](../docs/CONTROL_SCREEN.md)에 있다.

## 서버 운영 시: 실물 지도·경로 적용 (2026-11-11)

이 절은 **AWS 서버(Docker)로 실물 로봇을 운영할 때만** 해당한다. 저장소의 기본값(`config.json`, `deploy/config.json`, `docker-compose.yml`, `deploy/entrypoint.sh`)은 로컬 개발·시험용 시뮬레이션 지도·경로(`human_test_map.yaml` + `test_waypoints.yaml`)로 두고, 운영 값은 **서버의 `.env`에만** 넣는다. 서버는 저장소를 받기만 하고 파일을 직접 고치지 않는다(고치면 다음 `git pull`이 막힌다).

- 운영 지도는 `real_open_space_20261111.yaml`/`.pgm`(W1 코너 장애물 A·B를 지운 판), 경로는 `real_loop_waypoints.yaml`의 W1 → W2 → MID → W3 → W4 → HOME이다
- 서버 `dashboard/.env`:
  ```bash
  MAP_YAML=limbo/src/limbo_navigation/maps/real_open_space_20261111.yaml
  INITIAL_WAYPOINTS=real_loop_waypoints.yaml
  ```
- `INITIAL_WAYPOINTS`는 볼륨이 비었을 때(처음)만 복사된다. 이미 쓰던 볼륨의 경로를 바꾸려면 기존 `/data/waypoints.yaml`을 따로 백업한 뒤 교체한다
- 로봇의 AMCL·Nav2도 같은 지도 YAML을 써야 화면의 로봇 위치가 맞는다
- 받은 뒤 반영: `git pull` → `cd dashboard && docker compose up -d --build` (지도와 기본 waypoint는 이미지에 들어가므로 다시 빌드)
