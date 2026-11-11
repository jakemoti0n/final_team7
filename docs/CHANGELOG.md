# 변경 기록

2026-10-02 리팩터링을 기준으로 나눈다.
- **리팩터링 이후**: ktj 작업. dev에 push할 때마다 맨 위에 추가한다. pull 받은 뒤 해야 할 일은 "할 일"에 적는다.
- **리팩터링 이전**: 원작자 작업. git 히스토리로 정리해 둔 기록이며 더 이상 추가하지 않는다.

---

# 리팩터링 이후 (2026-10-02 ~, ktj 작업)

## 2026-11-11 (74) 운영 지도 `real_open_space_20261111.pgm`을 서버 판(W1 코너 장애물 A·B 제거)으로, 서버는 받기 전용(운영 값은 `.env`에만)

**할 일**
- 서버: 직접 고친 파일을 되돌린 뒤 받는다. `git restore dashboard/README.md dashboard/config.json dashboard/deploy dashboard/docker-compose.yml dashboard/.env.example limbo/src/limbo_navigation/maps/real_open_space_20261111.pgm` → `git pull` → `docker compose up -d --build`. `.env`의 `MAP_YAML`·`INITIAL_WAYPOINTS`는 그대로 둔다
- Jetson: 받으면 AMCL·Nav2 지도도 A·B가 없는 판이 된다. 실제로 A·B가 치워졌는지 확인

**변경**
- `limbo/src/limbo_navigation/maps/real_open_space_20261111.pgm`: x 12.1~13.3 m, y −0.1~1.35 m(그림 픽셀 x 442~465, y 333~361) 장애물 247칸을 빈 공간으로. `.yaml`은 그대로
- `dashboard/README.md` 「서버 운영 시: 실물 지도·경로 적용」: 저장소 기본값은 시뮬레이션용으로 두고 운영 값은 서버 `.env`에만, 서버는 파일을 고치지 않음

**원인과 근거**
- 서버에서 지도·설정 5개·README를 직접 고쳐 둔 탓에 `git pull`이 막혔다. 설정 5개의 변경은 `.env`가 이미 같은 값을 주고 있어 동작에 영향이 없었고, 실제로 차이를 만드는 것은 지도 pgm뿐이었다

## 2026-11-11 (73) 관제 서버 하나로 여러 로봇: 처음 보는 `robot_id`는 자동 등록, 로봇마다 상태·명령·알림·지도·waypoint 따로, 헤더의 로봇 이름을 눌러 볼 로봇 선택

**할 일**
- 두 번째 로봇은 relay_prog `bridge.yaml`의 `robot_id`만 다르게(예: `LIMBO-02`). 토큰·서버 주소는 그대로. Bridge 코드 변경 없음
- 로봇마다 다른 경로를 쓰려면 Dashboard 설정에 `"robots": {"LIMBO-02": {"waypoints_yaml": "..."}}` (`dashboard/README.md` 「여러 로봇」). 적지 않으면 공통 `waypoints_yaml`을 같이 쓴다
- `robot_id`는 이제 1~64자 영문·숫자·`.`·`_`·`-`만 받는다(그 밖은 텔레메트리 422). 지금 쓰는 `LIMBO-01`은 해당 없음
- 화면 다시 빌드: `dashboard/ui`에서 `corepack pnpm build`

**변경**
- 서버 `app.py`: 로봇별 묶음(`Store`·WebSocket 구독자·명령 신호·지도·waypoint 파일). telemetry는 `robot_id`로 찾고 없으면 등록(`max_robots` 기본 16, 넘으면 429 `too_many_robots`). commands/next·claim·result도 `robot_id`로 찾는다(이전의 409 `robot_id_mismatch` 없앰. 모르는 로봇의 commands/next는 `wait_s` 뒤 204). 화면용 `state`·`stream`·`map`·`map.png`·`waypoints`에 `?robot_id=`, `POST /api/v1/commands` 본문에 `robot_id`(모두 생략하면 기본 로봇). 새 `GET /api/v1/robots`. 스냅샷에 `robots`(각 로봇 연결 상태)
- 같은 지도·waypoint 파일은 한 번만 읽고 공유. waypoint 편집 잠금은 **그 파일을 쓰는 모든 로봇** 기준
- `models.py`: `Settings.robots`(로봇별 `map_yaml`·`waypoints_yaml`)·`max_robots`, `robot_id` 형식 검사. `state.py`: `Store`가 자기 `robot_id`를 가짐
- 지도에 같은 지도 파일을 쓰는 다른 로봇도 회색 화살표와 이름으로 표시, 누르면(또는 Tab·Enter) 그 로봇으로 전환. 서버는 스냅샷 `robots` 항목에 `pose`를 넣는다(`Store.pose_view`: 위치만 계산, 알림·revision은 그대로). 지도가 다른 로봇은 좌표가 맞지 않아 넣지 않음
- 화면: 헤더의 로봇 이름이 버튼(`LIMBO-01 ▾`) → 로봇 목록과 연결 배지, 키보드(↑↓·Enter·Esc) 지원. 고르면 화면 전체를 그 로봇으로 새로 만든다(이전 로봇 상태가 섞이지 않게). 주소 `?robot=`와 브라우저 저장으로 새로 고쳐도 유지, 서버가 모르는 로봇이면 기본 로봇으로. 데모는 로봇 하나
- 문서: `dashboard/README.md` 「여러 로봇」·API 표, `docs/CONTROL_API_DRAFT.md` §2.1·§2.2·§3.4·§4

**원인과 근거**
- 이전 서버는 설정의 `robot_id` 하나만 받고 다른 로봇은 모두 409로 거절했다. Bridge는 이미 모든 요청에 `robot_id`를 싣고 있어서 서버·화면만 바꿨다
- 등록 방식은 설정 목록 대신 자동 등록을 골랐다(로봇 추가 때 서버 설정을 안 바꿔도 됨). 대신 `bridge.yaml` 오타로 유령 로봇이 생길 수 있어 상한과 글자 제한을 뒀다

**확인**(이 PC, 2026-11-11)
- 서버 pytest 113 통과(새 `tests/test_robots.py` 11건: 같은 지도 로봇 위치·오래됨·다른 지도 제외, 로봇별 상태·세션, 자동 등록·상한, 명령이 고른 로봇에만 감, 다른 로봇 이름의 claim 거절, 로봇별 start 경로, 로봇별 지도·waypoint, 같은 파일 공유 시 편집 잠금, 로봇별 stream)
- UI 단위 시험 32 통과, `pnpm build` 성공
- Playwright 27 통과(`CHROME_PATH=/usr/bin/google-chrome`): 다른 로봇 표시를 눌러 전환하는 시험 추가. 새 시험은 두 로봇 텔레메트리 → 헤더 목록 열기 → 다른 로봇 선택 시 순찰 카드·주소·footer가 바뀜, 새로 고침 유지, Esc 닫힘, 모르는 로봇 주소는 기본 로봇으로

## 2026-11-07 (72) AWS에서 화면 빌드가 메모리 부족으로 실패하던 문제: rollup을 4.40.2로 고정 (빌드 3분·2.9 GB → 1초·0.3 GB)

**할 일**
- `dashboard/ui`에서 `corepack pnpm install --frozen-lockfile` (rollup 버전이 바뀜). Docker는 `docker compose up -d --build`만 하면 됨

**변경**
- `dashboard/ui/package.json`에 `"pnpm": {"overrides": {"rollup": "4.40.2"}}`, `pnpm-lock.yaml` 갱신(rollup과 플랫폼별 바이너리만 바뀜)
- `docs/AWS_DEPLOY.md`: 1 GB 인스턴스로 충분, 빌드 시간 2~5분, 문제 해결 표에 `JavaScript heap out of memory`

**원인과 근거**
- AWS 인스턴스에서 `docker compose up -d --build`가 `[ui 7/7] RUN corepack pnpm build`에서 `FATAL ERROR: Ineffective mark-compacts near heap limit … JavaScript heap out of memory`(exit 134)로 멈췄다. Node는 기계의 물리 메모리로 힙 한도를 정하므로 스왑을 만들어도 한도가 커지지 않는다
- 소스는 1,100줄·모듈 35개인데 이 PC에서도 `vite build`가 3분·최대 2.9 GB였다. React 플러그인을 빼도, 압축(minify)을 꺼도 같았다. CPU 프로파일 결과 시간의 대부분이 rollup 트리 셰이킹(`includeCallArgumentsWhenCalledAtPath`, `trackEntityAtPathAndGetIfTracked` 등)이었다
- vite 6.3.5는 rollup을 `^4.34.9`로만 요구해서 잠금 파일에 최신 4.64.0이 들어가 있었다. 4.40.2로 고정하자 같은 결과물(`index-B8uD1lsY.js` 해시 동일)이 0.8초·0.3 GB로 나왔다

**확인**(이 PC, 2026-11-07)
- `corepack pnpm build`(tsc 포함) 3.4초·최대 0.42 GB, UI 단위 시험 30 통과
- `docker compose build` 10초. `node:24-slim` 컨테이너를 메모리 1 GB로 묶고(`-m 1g --memory-swap 1g`) `pnpm install --frozen-lockfile && pnpm build` 성공
- 고치기 전 같은 빌드를 힙 512 MB로 묶으면 9초 만에 같은 `heap out of memory`로 재현

## 2026-11-06 (71) AWS 배포 파일과 가이드: Dockerfile·docker-compose(관제 서버 + Caddy HTTPS·basic auth)·`docs/AWS_DEPLOY.md`, Caddy 뒤에서 start 명령이 깨지던 압축 문제 수정 (인터넷 공개 준비 3단계)

**할 일**
- 없음 (로컬 실행 방법은 그대로). 배포할 때 `docs/AWS_DEPLOY.md`

**변경**
- `dashboard/Dockerfile`(+ `Dockerfile.dockerignore`): node 24에서 UI 빌드 → python 3.12-slim, `requirements.lock` 설치, `uvicorn --workers 1`, uid 10001. context는 저장소 루트이고 `limbo/`의 지도(yaml·pgm)와 `limbo_patrol/config`만 넣는다
- `dashboard/docker-compose.yml`: `dashboard`(8000은 밖으로 안 엶) + `caddy:2.10`(80·443). 볼륨 `waypoints`(화면에서 편집한 waypoint, 컨테이너를 다시 만들어도 남음)·`caddy_data`(인증서)
- `dashboard/Caddyfile`: `{$DOMAIN}` 자동 HTTPS. 로봇용 4경로(정규식)와 `/healthz`는 basic auth 없이, 나머지는 basic auth
- `dashboard/deploy/config.json`·`entrypoint.sh`: waypoint는 `/data/waypoints.yaml`, 볼륨이 비었을 때만 `INITIAL_WAYPOINTS`를 복사, `MAP_YAML`을 설정에 끼움, 잘못된 이름이면 고를 수 있는 목록을 출력하고 끝냄. `allow_no_robot_token: false`라 `ROBOT_TOKEN`이 없으면 서버가 시작하지 않음
- `dashboard/.env.example`(sslip.io 예, 해시는 작은따옴표), `.gitignore`에 `dashboard/.env`
- `docs/AWS_DEPLOY.md`: Lightsail(또는 EC2 t3.micro)·고정 IP·방화벽(80·443, 22는 내 IP만)·스왑·Docker 설치·배포·로그·업데이트·waypoint 백업·지도 바꾸기·sslip.io·로봇 `bridge.yaml`(server_url, token_file, use_sim_time)·확인 체크리스트·문제 해결
- `dashboard/README.md` 「인터넷(AWS) 배포」
- Bridge `transport.py`: 모든 요청에 `Accept-Encoding: identity`(압축하지 말라). `Caddyfile`의 `encode`는 브라우저 경로에만
- `relay_prog/tools/receiver.py`(시험 서버): Caddy처럼 gzip을 받겠다는 요청엔 512 B 이상 응답을 압축
- `dashboard/deploy/local_https_bridge.sh`: 내 PC에서 Docker 서버 + Caddy + 실제 Bridge(HTTPS·토큰)를 한 번에. 시뮬레이션만 따로 켜면 AWS와 같은 구성으로 시험(`AWS_DEPLOY.md` 16절). 이미지에는 안 넣음

**원인과 근거**
- 지도·waypoint 경로는 "저장소 루트 기준 상대경로" 규칙이라 이미지 안에서도 `/srv`를 저장소 루트로 두고 `limbo/...` 경로를 그대로 살렸다(서버 코드 변경 없음)
- 이 PC에서 화면 빌드에 메모리를 많이 써서(vite 약 2.8 GB) 1 GB 인스턴스는 스왑을 필수로 적었다
- Caddy 뒤에서 **주행 시작이 `no_response`로 실패**했다: Bridge는 응답 크기를 세며 읽으려고 자동 압축 풀기를 꺼 두었는데(`auto_decompress=False`) aiohttp가 기본으로 `Accept-Encoding: gzip, deflate`를 보내서, Caddy가 512 B가 넘는 start 명령(waypoint 목록)을 gzip으로 보냈고 Bridge는 `invalid_command`로 버렸다. 텔레메트리 응답과 pause/resume은 작아서 압축되지 않아 드러나지 않았다. 다른 앞단(nginx 등)에서도 같은 일이 생기지 않게 Bridge 쪽을 고쳤다

**확인**(PC 한 대, Docker 29.9 + Compose 5.7, `DOMAIN=localhost`, 2026-11-06)
- `docker compose build` 성공(약 3분 20초, 이미지 215 MB), `up -d`로 두 컨테이너 실행, 서버는 uid 10001로 돎, 첫 시작 때 `test_waypoints.yaml`을 볼륨에 복사
- basic auth: `/`·`/api/v1/state`·`POST /api/v1/commands`·WebSocket `/api/v1/stream` 로그인 없음·틀린 비밀번호 401, 맞으면 200(WS는 101), JS·CSS 200, `/healthz` 200, http→https 308
- 로봇 경로: telemetry·commands/next·claim·result 토큰 없음·틀림 401, basic auth만 있어도 401, 맞는 토큰이면 서버까지 감. `tools.sender.sample()` 한 건 `"accepted":true`
- 지도 302×302·`map.png`, waypoint 이름 변경 → `docker compose down`·`up`(새 컨테이너) 후에도 남음
- **실제 Bridge → Caddy(HTTPS, Caddy 내부 루트 인증서를 `SSL_CERT_FILE`로 신뢰) → 컨테이너**: 연결·launcher v3, 주행 시작 `confirmed`(로봇 쪽 YAML에 화면에서 바꾼 이름, `waypoints:=<절대경로>`), 실행 중 편집 409 `patrol_active`, 순찰 종료 `confirmed`(exit 0). 고치기 전엔 start가 `no_response`(위 원인), Bridge만 고친 상태(Caddy는 전 경로 압축)와 둘 다 고친 상태 모두 통과
- `local_https_bridge.sh`: 컨테이너가 꺼진 상태에서 실행 → 컨테이너 켜고 Bridge 연결, 주행 시작·순찰 종료 `confirmed`, 두 번째 실행은 Bridge 중복으로 거절, Ctrl+C로 Bridge·순찰 노드 모두 정리(종료 코드 0)
- `test_start_command_reaches_launcher_with_route`가 고치기 전 코드에서 실패·고친 뒤 통과, relay pytest 93 통과
- 빌드 경고 `Ignored build scripts: esbuild`(pnpm 10)는 무해: `@esbuild/linux-x64` 바이너리가 따로 설치돼 vite 빌드가 됨

## 2026-11-06 (70) 로봇용 경로에 공유 토큰 인증 (`Authorization: Bearer`): 인터넷 공개 준비 2단계

**할 일**
- 로컬 개발은 할 일 없음 (기본 `config.json`의 `allow_no_robot_token: true`, `bridge.yaml`의 `token_file: null`)
- 자기 `config.json`을 따로 쓰면: 토큰을 설정하거나 `"allow_no_robot_token": true`를 넣는다. 둘 다 없으면 서버가 시작하지 않는다
- 자기 `bridge.yaml`을 따로 쓰면 `token_file: null` 줄을 추가 (없으면 Bridge가 시작하지 않음)

**변경**
- 서버: telemetry, commands/next·claim·result 4경로가 본문을 읽기 전에 토큰 검사(`hmac.compare_digest`). 없거나 틀리면 401 `unauthorized` + `WWW-Authenticate: Bearer`. 토큰은 환경 변수 `ROBOT_TOKEN` → `robot_token_file`. 없으면 `allow_no_robot_token`일 때만 열고 아니면 시작 거부. 16자 미만·공백·빈 파일도 시작 거부. 브라우저용 경로는 그대로(앞단 Caddy basic auth 전제, 3단계)
- Bridge: 환경 변수 `LIMBO_ROBOT_TOKEN` → `bridge.yaml`의 `token_file`. 모든 요청에 헤더. 401이면 10초 간격 재시도 + 토큰 확인 경고. 토큰을 평문 `http://`로 다른 컴퓨터에 보내면 시작할 때 경고
- Mock 서버(`relay_prog/tools/receiver.py`)·가상 송신기(`dashboard/tools/sender.py --token`)도 토큰 지원
- 문서: `dashboard/README.md` 「로봇 토큰과 인터넷 공개」(로컬에서 토큰 시험하는 법), `relay_prog/README.md` 설정 표, `docs/CONTROL_API_DRAFT.md` 원칙·인증 결정

**원인과 근거**
- 서버를 인터넷에 열면 누구나 가짜 텔레메트리를 보내거나 명령을 가로챌 수 있다. 로봇은 브라우저가 아니라 basic auth 대신 공유 토큰을 쓴다. 화면 쪽 로그인은 서버에 넣지 않고 앞단 Caddy가 맡는다(서버는 한 프로세스·메모리 상태라 단순하게 유지)

**확인**(PC 한 대, 2026-11-06)
- `dashboard` pytest 102, `relay_prog` pytest 93 통과
- 실제 서버(`ROBOT_TOKEN`, `allow_no_robot_token: false`) + 실제 Bridge: 토큰 없이 서버 시작 → 거부. curl 토큰 없음/틀림 → 401, `/api/v1/state` → 200. 맞는 토큰 Bridge → 연결됨, start·stop confirmed. 틀린 토큰 Bridge → `http_401` + 토큰 확인 경고

## 2026-11-06 (69) 주행 시작·순찰 종료를 Bridge 경유 명령으로: 서버는 명령만 쌓고 로봇 컴퓨터의 Bridge가 `patrol_node`를 띄우고 끈다. waypoint 목록은 시작 명령에 실어 보낸다 (AWS 배포 준비 1단계)

**할 일**
- pull 뒤 `relay_prog`를 다시 빌드(새 파일 `launcher.py`). Bridge는 **저장소 루트에서** 실행(`patrol_launch`의 상대 경로 기준)
- 실물 로봇이면 `bridge.yaml`의 `patrol_launch.use_sim_time: false`
- 자기 `config.json`에 `patrol_ros_domain_id`·`patrol_use_sim_time`이 있으면 지운다(남아 있으면 서버가 시작하지 않음)
- 서버와 Bridge를 같이 올린다. 새 Bridge(v3)는 옛 서버에 거절되고, 옛 Bridge(v2)에는 새 서버가 시작·종료 버튼을 잠근다

**변경**
- 서버: `server/patrol_launch.py`(서버에서 subprocess 실행·`/proc` 검사) 삭제. `/api/v1/patrol/start`·`stop`·`launch` 삭제 → `POST /api/v1/commands`에 `start`·`stop`. start는 그 순간의 서버 YAML 목록·`revision`·지도 범위를 명령 `route`에 고정. 확인: start는 `waiting_localization`·`patrolling`(60초), stop은 노드 종료 보고나 순찰 상태 사라짐(30초). 새 설정 `command_start_*`·`command_stop_*`. waypoint 편집 잠금·중복 시작 거절은 텔레메트리 순찰 상태 + Bridge 보고(`patrol_running`)로. `config.json`에서 `patrol_ros_domain_id`·`patrol_use_sim_time` 삭제
- 텔레메트리 **v3**: v2 + `launcher`(지원 명령, idle/running/exited, pid, exit code, 경로 revision, 로그 경로, 다른 곳에서 띄운 노드 여부)
- Bridge: `launcher.py` 새로(예전 서버의 `_other_patrol_running` 옮김). 받은 경로를 서버와 같은 규칙으로 검사 → `patrol_launch.waypoint_dir/dashboard_waypoints.yaml`에 원자적 저장 → 절대 경로로 `patrol_node` 실행. 종료는 자기가 띄운 노드에만 SIGTERM. Bridge가 끝나면 띄운 노드도 끔. `bridge.yaml`에 `patrol_launch:`(ros_setup, workspace, waypoint_dir, use_sim_time). 시작할 때 경로를 확인해 틀리면 바로 알림. 명령 응답 한도 8 → 64 KiB
- 화면: 주행 시작·순찰 종료도 일시정지와 같은 3단계 결과 상자. `/api/v1/patrol/*` 폴링 제거. 이전 Bridge면 「로봇의 Bridge를 업데이트해야 사용할 수 있습니다」. `/demo`도 같은 흐름 + 「Bridge 버전」 선택
- 검증 규칙 사례표 `relay_prog/tests/data/route_cases.json`을 서버·Bridge 시험이 함께 읽음 (한쪽만 바꾸면 시험이 깨짐)
- 문서: `dashboard/README.md`, `docs/CONTROL_API_DRAFT.md`(§1.3·§2.5), `docs/CONTROL_SCREEN.md`(A 5단계), `relay_prog/README.md`, `relay_prog/docs/PRD.md`

**원인과 근거**
- 서버를 AWS에 올리면 서버 컴퓨터에 ROS가 없고 DDS는 인터넷을 못 넘는다. 서버가 직접 `patrol_node`를 띄우는 방식은 서버와 로봇이 같은 컴퓨터일 때만 됐다. 로봇은 서버로 나가는 HTTP(S)만 쓰고, 들어오는 포트를 열지 않는다
- 명령 통로(`next → claim → result`, TTL, 응답·확인 제한)를 새로 만들지 않고 그대로 써서 재전송 금지·늦은 실행 방지 규칙을 그대로 받는다

**확인**(PC 한 대, 2026-11-06)
- `dashboard` pytest 77, `relay_prog` pytest 91(ROS 환경 source), UI 단위 30, Playwright e2e 25(`CHROME_PATH=/opt/google/chrome/chrome`) 모두 통과, UI 빌드 성공
- 실제 서버 + 실제 Bridge + 실제 `patrol_node`(Gazebo·Nav2 없이, ROS_DOMAIN_ID 93): waypoint 이동 → 주행 시작 confirmed(`waiting_localization`) → 로봇 쪽 YAML에 이동한 좌표, `patrol_node` 인자 `waypoints:=<절대 경로>` → 실행 중 편집 409 `patrol_active`·재시작 409 → 순찰 종료 confirmed(exit 0) → 다른 터미널에서 띄운 노드가 있으면 시작 409·종료 409 → Bridge Ctrl+C 때 띄운 노드도 종료
- 하지 못함: 시뮬레이션에서 주행 중 일시정지·재개. 이 경로(서비스 호출)는 바꾸지 않았고 e2e로만 확인
- 남은 것: 순찰 종료 때 순찰 노드가 `failed` · `stopped by operator`를 내서 「순찰 실패」 알림이 하나 생긴다(전에도 같음)

## 2026-11-11 (68) 다익스트라 시험(순찰 8) 실패 분석 → 원인은 계획기가 아니라 **지도 잡티(복도 한가운데 5칸)와 지역 비용 지도의 정적 층 부재**, 지도 `real_open_space_20261111`(고립 잡티 224개 제거), 실물 절차 순서 수정(초기 위치 → Nav2), 노트북 감시 화면 4개

**했음**
- **순찰 8**(다익스트라 `use_astar: false`, 되꺾임 처리 켬, 팽창 0.35, 카메라 제외, 지도 1110): **실패(900 s 타임아웃)**. 1구간 →MID 236 s(W1 코너 174 s: 정지 64·회전 86 s, 누적 2078°), 2구간은 MID→W3→왼쪽 복도 (0.49, 2.31)까지 39 s에 내려온 뒤 **W4까지 2.1 m를 전역 계획기가 85 s 동안 "경로 없음"(재시도 3회) → Goal failed**. 되꺾임 지표(1구간 경로 67장 중 로봇 1 m 안 되꺾임 45장, 67 %)는 A*의 88 %보다 조금 낮지만 W1은 더 오래 섰고, 다익스트라에서만 나는 NavFn 오류 `Failed to create a plan from potential when a legal potential was found` 4회. **다익스트라는 해답이 아님 → A*로 복귀**
- **왼쪽 복도 실패 원인 = 지도 잡티**: 지도 1110의 복도 한가운데 5칸 점유 (0.45~0.70, 2.15~2.25)(11-09 SLAM 잡음)가 전역 비용 지도에서 팽창 안쪽(99)까지 지름 0.5 m 덩어리가 되고, NavFn은 99 칸도 못 지난다. 로봇이 그 위에 올라선 순간 모든 목표에 경로 없음(지금 자리에서 `compute_path_to_pose` 시험 → HOME·1 m 남쪽 모두 ABORTED 208, 로봇 칸 값 100). 지역 비용 지도에는 정적 층이 없어 그 자리가 빈칸이라 MPPI가 거기로 몰고 들어갔다. 카메라 영상도 빈 바닥. 지도 전체에 ≤8칸 고립 잡티 441개, 순찰 경로 위에는 왼쪽 복도 2개·오른쪽 복도 (13.65, 5.35)·HOME 옆 (0.0, −0.2)
- **W1 틈 실측(전역 비용 지도 줄 단위)**: 정수기·쓰레기통 A(지도 x 12.10~13.30)와 탁자 B(13.80~14.30) 사이 지나갈 수 있는 폭이 **y 0.18~0.53에서 0.30~0.35 m(6~7칸)**, y 0.6부터 넓어져 y 1.0에서 1.0 m. 이 좁은 띠에서 NavFn이 떤다. A·B 모양은 라이다 관측 그대로라 더 좁게 그릴 근거 없음(쓰레기통은 148 s 카메라에 실물 확인; 지역 비용 지도에 안 보인 건 로봇에 너무 가까워 걸러진 것)
- `limbo_navigation/maps/real_open_space_20261111.{pgm,yaml}`(새): 1110에서 **≤8칸이고 큰 구조물에서 0.5 m 넘게 떨어진 고립 점유 덩어리 224개(397칸)** 를 주변 다수값(자유/미지)으로 메움. 벽·A·B는 그대로. 순찰 구역 안 40개 중 36개는 섬 내부 미지 영역, 복도 위 4개는 위 목록. 규칙·스크립트는 스크래치패드 `mapclean.py`(지도 만들기 표준 절차에 넣을 후보)
- `docs/REAL_PATROL_RUN.md`: 새로 부팅하면 Nav2가 안 올라오던 순서 오류 수정 — ② 센서+AMCL → **③ 위치 탐색·`/initialpose`(`/tmp/setpose.sh`)** → ④ 설정 → ⑤ Nav2. 설정 생성에서 `enforce_path_inversion=False` 제거. 막히면 항목 추가. TROUBLESHOOTING 11-11 1건(AMCL `set_initial_pose: false` + 비용 지도 TF 60 s 대기 → 생명주기 관리자 기동 중단)
- 노트북 감시 화면 4개(PM 요청, 스크래치패드 `watch_rviz.sh`·`watch_cam.sh`·`watch_nav2.sh`·`watch_patrol.sh`·`real_watch.rviz`): 노트북에서 `ROS_STATIC_PEERS=192.168.20.210`만 주면 젯슨 런치(LOCALHOST 탐색)를 안 바꿔도 토픽 37개가 보임. RViz = 정적 지도 + 전역/지역 비용 지도(costmap 색) + 발판 + /plan + /local_plan + /scan + AMCL + 카메라 패널. 저장소 반영 여부는 PM 결정 대기
- 측정용 Nav2 설정(젯슨 `/tmp/nav2_real_measure.yaml`, `/tmp/mkmeasure.py`): 카메라 제외 + 팽창 0.35 + **지역 비용 지도에 `static_layer` 추가** + A*(저장소 기본) + 되꺾임 처리 켬

**할 일**
- 순찰 9(지도 1111 + 위 측정 설정) 한 바퀴 → W1·왼쪽 복도 시간, 되꺾임 지표 비교. 지역 정적 층·지도 1111의 저장소 기본값 채택은 PM 결정
- W1 0.30 m 띠: NavFn 대안(Smac 2D + 다듬기) 별도 실험, 또는 실물 통로(0.85 m) 쪽 결정
- 변경 기록 67 할 일 나머지(카메라 역할 분리·절벽 감지·HOME 도착 회전·지도 만들기 표준 절차·문 구역·배터리·ToF)

## 2026-11-10 (67) 라이다 비용 지도 점군이 높이 0.84~1.0 m 띠만 보던 버그(pcl_ros 복셀 기본 z 자르기) 수정, 센서 장착 실측(라이다 높이 0.857), 원점 바닥 테이프 자리 (0.74, −0.04) +x, 카메라 가짜 점 원인 확정(흰 벽·유리 앞 스테레오 짝 오류 → 세로 9칸 규칙으로 W3 벽 가짜 칸 0), 지나가기 순찰 `real_loop_waypoints.yaml`(MID·HOME 2곳만 정지), 지도 `real_open_space_20261110`(W1 코너 정수기·쓰레기통·탁자 추가) → 한 바퀴 362 → 264(카메라 켬) → **170 s(카메라를 비용 지도에서 뺀 측정, 주행 157 s)**, 이후 바퀴마다 W1 코너 87~182 s 정지의 원인 = **NavFn(A*) 전역 경로 떨림(되꺾임 수백 개) + MPPI `enforce_path_inversion`**. 실행 절차 `docs/REAL_PATROL_RUN.md`. TROUBLESHOOTING 4건

**할 일**
- **코너·빈 복도에서 1~3분 서는 것의 진짜 원인(순찰 4~7)**: 전역 경로(NavFn, `use_astar: true`)가 로봇 바로 앞에서 2 cm 간격으로 되꺾이는 떨림 경로를 냄(순찰 5 46 s: 되꺾임 299개, 순찰 6 150 s: 374개; W1 구간 경로 40개 중 35개가 로봇 1 m 안에 되꺾임). MPPI `enforce_path_inversion: true`(10-14 시뮬 되돌이용)가 첫 되꺾임(3 cm 앞)에서 경로를 자르고 방향(±23°, 경로 yaw는 전부 0)이 맞을 때까지 속도 0 → "진행 없음" 10 s마다 → 복구 회전 반복. 깨끗한 경로가 오면 출발(순찰 3 29 s / 4 110 / 5 87 / 6 182 s의 차이). **되꺾임 끄기만 한 순찰 7: W1 11 s로 풀렸지만 W3 코너 224 s(진짜 머리핀 경로를 끄지 않고 따라가다 제자리 회전) → 취소.** 즉 되꺾임 처리는 머리핀(pass 경유점을 옆으로 스쳐 지날 때)에 필요하고, W1의 문제는 그 처리가 떨림 경로에 오작동한 것. 다음: ① **되꺾임 처리는 다시 켜고**, ② 떨림 자체를 줄이기 — `use_astar: false`(다익스트라, 원작자 기본값; 10-15에 시뮬 계산 시간만 보고 A*로 바꾼 것) 또는 경로 다듬기 단계가 있는 Smac 계획기, ③ 머리핀이 안 생기게 pass 통과 반경(`RemovePassedGoals radius 0.7`, 실물 BT xml) 1.0~1.5로 올리거나 W3를 로봇이 실제로 지나는 자리로(순찰 3~6 궤적 기준). 판단 기준은 **되꺾임 수·1 m 안 되꺾임 경로 비율**(`/tmp/plancusp.py` 방식)로 통일하고, 다시 A*로 돌리지 않음
- **고정 물건 판정 기준 수정**: "로봇이 근처를 지난 모든 기록에서 보임"만으로는 **라이다 높이 상한(1.0 m) 경계에 걸린 물건(높은 탁자 상판)**이 2/7 기록에만 보여 사람으로 오판됨(11-10). 영상·로봇 카메라로 실물을 확인하는 단계를 둘 것. 탁자는 1110 지도에 추가함
- **팽창 반경 0.35(측정용)**: W1 통로(A↔탁자 0.85 m) 통과용으로 0.45에서 내림. 안전 띠라 PM 결정으로 저장소 반영 여부 정할 것
- **카메라를 다시 켜는 조건 = 가짜 점 규칙이 들어간 뒤**: 순찰 2·3(카메라를 비용 지도·충돌 감시에서 뺌)에서 네 복도가 전부 0.5 m/s(저속·정지 0 s)였고, 순찰 1(카메라 켬)의 오른쪽 복도 40·W3 51·왼쪽 복도 48 s 흔들림은 **카메라였음이 확정**(제어기 아님). 지금 그대로 켜면 그 흔들림이 돌아온다. 카메라 없이 도는 동안은 **0.75 m 아래 낮은 물체가 사각**이라 복도에 새 물건을 두지 말고 관찰자 2 m 밖. 젯슨의 측정용 설정은 `/tmp/nav2_real_nocam.yaml`(저장소에 없음, 재부팅하면 사라짐; `run_nav2_real.sh params_file:=`로 지정)
- **HOME 도착 25 s(순찰 3의 마지막 낭비)**: 목표 7~13 cm 앞에서 방향 0°를 맞추느라 회전 누적 669°, 앞 치명 칸 0. 어제 원점 복귀 36 s와 같은 "목표 바로 앞 방향 맞추기" 문제 → RotationShim(45° 문턱)·`yaw_goal_tolerance 0.25`·GoalAngleCritic을 볼 것. 이것만 고치면 주행 약 132 s
- **코너를 "서다→돌다→가다"로 도는 것**(PM 지적): RotationShim `angular_dist_threshold 0.785`(45°)라 90° 코너마다 제자리 회전. 100°쯤으로 올리고 전역 경로 꺾임을 둥글게(smoother) 하면 달리면서 돈다. 지도에 물건이 들어간 뒤 한 바퀴로 시험(좁은 코너 안쪽 벽 접근 주의)
- **지도 만들기 표준 절차(새 장소용, 도구화·설계 승인 필요)**: bag 한 바퀴 → 벽 지도(오프라인 SLAM) → **같은 bag의 라이다 0.1~1.0 m 점 중 지도상 빈 바닥에, 로봇이 근처를 지난 모든 기록에서(순찰 3 기준 73~98 %) 보인 자리를 고정 물건으로 지도에 넣기** → PM 그림 승인 → 경유점이 벽·물건 팽창 띠(0.45 m)+여유 밖인지 자동 검사 → 출발 전 점검에 "전역 경로가 지도 물건 0.5 m 안을 지나는지" 추가. 11-09 지도는 /scan 높이 띠(0.69~1.04 m)로만 만들어 낮은 고정 물건(쓰레기통 0.7 m·탁자 다리)이 빠져 있었고, 그 옆에 W1을 둬서 코너 113 s 갇힘(순찰 2)이 났다. "2개 기록에서 보임" 기준은 서 있던 사람을 통과시킨다(11-10 확인: 유리벽 쪽·아래 복도 덩어리는 사람)
- **순찰 노드 출발 대기 13 s**(`patrol_node`가 AMCL·Nav2 준비를 기다림) → 기록 시작을 노드 준비 뒤로 옮기거나 노드를 미리 띄워 둘 것
- **카메라 가짜 점 규칙(팀원 상의)**: `near_depth_filter.py`에 "깊이 화소가 세로로 9행 이상 이어진 것만 남김"(9 = 1 m 앞 2 cm = 비용 지도 `min_obstacle_height`, fy 477 px) + 역할 나누기(비용 지도의 카메라 `max_obstacle_height` 1.0 → 0.75, 그 위는 라이다가 봄). 근거는 아래 "원인과 근거". 시간 규칙(같은 자리 2장 연속)은 W1 벽 앞에서 절반밖에 못 줄임(7구간 합 11,002 → 9칸 2,074 → +2장 1,061)
- **카메라 각도**: 사용자가 0°로 맞춰 둠. 각도 도구가 준비되면 숙일 각도를 정할 것 — 0°에서는 0.5 m 앞 0.47 m 아래, 1 m 앞 0.27 m 아래가 화면 밖(11-10 상자 시험에서 상자가 안 잡힘). 라이다도 −7°라 0.3 m 물체는 4.4 m 밖에서만 봄 → **낮고 무늬 없는 물체는 지금 두 센서 모두 사각**
- **팀원에게 넘길 실측(11-10 줄자·사진)**: 라이다 꼭대기 0.87 ± 0.01 m → 측정 원점 약 0.857(파일 `MID360s_mount.json` 0.837, +2 cm), 좌우 로봇 오른쪽 2 mm, 앞뒤 0. 카메라 렌즈 높이 약 0.67(파일 0.68), 좌우 가운데. 시뮬 URDF의 카메라 왼쪽 0.1575 m는 실물과 다름(실물 런치는 URDF를 안 씀). 카메라 숙임은 bag 벽면 기울기로 0.6~3° 사이(확정 못 함, 0°로 재세팅)
- 이전 항목 그대로: 문 두 곳, 오른쪽 복도 축척 줄자, 원점 복귀 시간, 무한 순찰 + 4시간, bag→지도 도구화, 배터리(오늘 전압 측정 안 함)

**결과 (11-10, 새 지도, 1번 수정 적용. 사람이 간간이 지나다님)**

| 시험 | 조건 | 결과 |
|---|---|---|
| 루프 15 | 경유점마다 정지, +x 출발, W1 (13.1, 0.1) | 362 s, 실패 35. W1 구간 129 s(마지막 3.4 m를 108 s, 회전 방향 19번) |
| W1 기록 주행 | 원점 → W1 (13.1, 0.1) 하나 | 72 s, 실패 4 |
| 3왕복 | 원점 ↔ W1 (13.1, 0.1), 7구간 | 구간 67~124 s(평균 100), 실패 6~20. 느린 시간의 80 %. 7구간 내내 같은 자리 (13.8~13.9, 0.2~0.5) 흰 벽 앞 가짜 칸 |
| 2왕복 | 원점 ↔ **W1 (12.0, 0.1)**, 4구간 | 구간 47~83 s(평균 62), 3구간 이상 반복 가짜 자리 225 → 8곳. 멈칫하는 자리가 목표와 함께 1 m 이동 → 목표 근처 감속·회전이 원인 |
| 순찰 1 | 지나가기(W1·W2 pass → MID stop, W3·W4 pass → HOME stop) | **264 s, 실패 53**. 아래 복도 20 s(0.5 m/s), W1 코너 26, 오른쪽 복도 40, W2 16, 위 복도 38, W3 코너 51, 왼쪽 복도 48, HOME 27(출발 대기 13 포함) |
| 순찰 2 | 순찰 1 + **카메라를 비용 지도·충돌 감시에서 뺌**(젯슨 /tmp 설정) | 주행 239 s(Nav2 시각; 기록은 마지막 40 s 누락). 오른쪽 복도 **12**, 위 복도 **21**, W3+왼쪽 복도+HOME **64** → 복도 흔들림 소멸. 대신 **W1 코너 113 s**(회전 누적 1182°): 지도에 없던 정수기·쓰레기통·탁자 옆 0.45~0.6 m에 갇힘 |
| 순찰 3 | 순찰 2 + 지도 1110(그 물건 추가) + W1 (11.0, 0.3) | **170 s, 실패 4**(주행 157). 아래 19, W1 29, 오른쪽 12, W2 15, 위 21, W3 16, 왼쪽 14, HOME 44(출발 대기 13 + **도착 방향 맞추기 25**) |
| 순찰 4 | 순찰 3과 같음 | 263 s. W1 코너 **110**(정지 50·회전 35), 왼쪽 복도 34, 나머지 순찰 3과 같음 |
| 순찰 5 | 순찰 3과 같음(영상 촬영) | 218 s. W1 코너 **87**, 나머지 같음. 46~111 s 경로 길이 17 ↔ 24.6 m 뒤집힘 = 떨림 |
| 순찰 6 | + 지도에 탁자 추가 + 팽창 0.35 | 329 s. W1 코너 **182**(정지 106). 49~69 s: 경로 정면·발판 비용 0인데 제어기 속도 0 |
| 순찰 7 | + `enforce_path_inversion: false` | 취소(420 s). **W1 코너 11 s**(정지·회전 0 → W1 정지는 되꺾임 처리가 원인이었음이 확정). 대신 W2 41(회전 605°), 위 복도 95(왔다 갔다), **W3 코너 224 s(회전 3766°)** → 취소. W3에서는 경로가 떨린 게 아니라(되꺾임 1개) 로봇이 W3를 1.2 m 남기고 먼저 남쪽으로 꺾어 통과 반경 0.7 m 밖 → 경로가 W3까지 올라갔다 내려오는 **진짜 머리핀**. 되꺾임 처리를 끄니 MPPI가 머리핀을 그대로 따라가려다 제자리 회전 |

**변경**
- `limbo_bringup/launch/start_mid360.launch.py`: `mid360_costmap_voxel`에 `filter_field_name: ''`(TROUBLESHOOTING 11-10). 테스트 `test_costmap_lidar_voxel_keeps_every_height`(수정본 통과, 원본 실패 확인)
- `limbo_navigation/maps/real_open_space_20261110.{pgm,yaml}`(새): 1109 지도 + W1 코너 섬 쪽(Class Room 4 문 옆) 정수기·쓰레기통 257칸(0.64 m², x 12.1~13.3·y −0.1~1.7) + 유리벽 쪽 높은 탁자 101칸(0.25 m², x 13.8~14.3·y −0.6~0.7; 상판이 라이다 높이 상한에 걸려 깜빡이던 것). 두 덩어리 사이 통로 폭 0.85 m(y≈0.4). 오늘 기록 7개 모두에서 라이다(높이 0.1~1.0 m)가 73~98 % 관측한 자리만 넣음. **기본값은 아직 11-05**, 젯슨에는 `load_map`으로 올려 씀
- `docs/REAL_PATROL_RUN.md`(새, PM 요청): 젯슨에서 런치 3개 → 측정용 Nav2 설정 생성 → 위치 확인·초기 위치·점검·기록·순찰을 한 번에 도는 절차와 끝내기·막히면. 11-11: 설정 생성 스니펫에서 `enforce_path_inversion=False` 줄을 뺌(순찰 7 결론대로 되꺾임 처리는 켠 채 둠)
- `limbo_patrol/config/real_loop_waypoints.yaml`(새): 실물 지나가기 순찰. HOME (0.74, −0.04, 0°) = 바닥 테이프 자리(정밀 탐색 5회, x 0.72~0.745), W1 (11.0, 0.3)(코너 앞 자유 공간; (12.0, 0.1)은 위 물건의 팽창 띠 안), W2 (13.4, 9.6), MID (6.5, 9.5, 180°) stop, W3 (0.4, 9.8), W4 (0.6, 0.2). 실행: `ros2 run limbo_patrol patrol_node --ros-args -p use_sim_time:=false -p waypoints:=real_loop_waypoints.yaml -p loop:=false`(젯슨은 install이 build로 링크돼 있어 새 파일은 링크 1회 필요)
- 젯슨에만(커밋 안 함): `/tmp/nav2_real_nocam.yaml`(카메라 소스 제거) → `_inf35.yaml`(+팽창 0.35) → `_inf35_noinv.yaml`(+되꺾임 멈춤 끔). 재부팅하면 사라짐, 만드는 법은 `docs/REAL_PATROL_RUN.md` 2절. `real_robot_mount.yaml`·`MID360s_mount.json`은 팀원 파일이라 손대지 않음

**원인과 근거**
- **카메라 가짜 점 = 스테레오 짝 오류**: OAK-D Lite는 적외선 투사기가 없어 좌우 흑백 영상의 무늬로만 짝을 찾는다(시차 96 px → 최소 0.38 m). W3 흰 벽(0.88 m) 앞 30 s 기록: 깊이 영상 61 %가 못 잼(0), 0.5 m 안 가짜 화소 장당 약 1만. 팀원 필터가 99.3 % 지워도 장당 ~70화소가 남고 비용 지도는 점 하나도 치명 칸(+팽창 0.45)으로 치므로, 10 Hz×기억 1 s 때문에 벽을 보는 동안 95 %의 시간에 가짜 장애물이 있다. 가짜 화소는 가로줄을 따라 짝을 찾는 탓에 **두께 1~8행(88 %가 2~3행)의 가로 띠**. 세로 9칸 열림 연산으로 W3 벽 가짜 칸 77장 → 0장, 0.5 m 앞 사람(청바지) 화소 87 %·비용 지도 칸 89 % 유지. W1 끝 벽(점무늬 시트 유리문·파란 띠)에서는 가짜 칸 −81 %로 0이 아님 → 규칙 하나로는 부족
- **W1 쪽은 목표 근처 동작이 증폭**: 영상(순찰 전 2왕복)에서 목표 2 m 안 감속 뒤 정수기·쓰레기통·배너·흰 벽을 번갈아 보며 치명 칸이 1초마다 0 ↔ 57로 널뛰고 회전 방향 20번 바뀜. 원점 쪽은 목표 7~13 cm 앞에서 방향 맞추기 20 s. → 지나가기 순찰로 바꾼 근거
- 실물 런치는 URDF를 쓰지 않고 `real_robot_mount.yaml`·`MID360s_mount.json`으로 고정 TF를 낸다. 1번 수정 효과·사각 계산은 이 장착값 기준
- 영상 IMG_1173(사용자 촬영, 로봇 경로 한 바퀴 172 s)과 지도 대조: 아래 복도 바깥 전부 유리벽, W1 코너 정수기·쓰레기통·높은 탁자, 위 복도 회색 쓰레기통·상자 = 지도 (7.0, 10.3), W3 코너 정수기·검은 쓰레기통·무늬 없는 흰 벽(가짜 점 최다 17 %), 왼쪽 복도 사물함. 바닥 소화기·우산꽂이·상자 등 0.3~0.5 m 물체가 경로 옆에 많음(사각 대상)

## 2026-11-09 (66) 저녁 시험: 오른쪽 위 코너(W2→W3) 위치 추정 실패(4바퀴 중 3번 중단)의 원인 = 11-05 지도의 복도 길이 오차(오른쪽·위 복도가 바퀴 odom보다 12~16 % 짧음) + 18시 이후 복도 쪽으로 직각으로 열린 문 2곳. 수동 한 바퀴 bag으로 오프라인 SLAM 재지도 `real_open_space_20261109` 추가 → 독립 bag 스캔 일치 평균 95 %(기존 지도 72 %), 새 지도로 한 바퀴 완주 ×2(문 열림 324 s·문 닫힘 313 s)

**할 일**
- **문 두 곳 처리(다음 차례)**: 새 지도는 19:46 문이 열린 상태로 만들어 W2→W3 문짝이 벽 선(x≈9.2, 섬 벽 y≈8.3에서 복도 쪽으로 약 1.3 m)으로 들어가 있다. 문이 닫힌 날에도 경로 계획이 없는 문짝을 피한다. 문틀·문짝이 쓸고 지나가는 범위를 지도에서 "모름"으로 비운다(그림으로 PM 승인 뒤). **기본 지도(`map:=`) 교체는 그 뒤** — 지금 실물 런치 인자는 11-05 지도 그대로
- **위 복도 `Optimizer fail` 뭉침(문과 무관)**: 루프 13(문 열림) 23건, 루프 14(문 닫힘) 27건으로 같은 자리(x 2~9, y 9.6~10). 실패 순간 로봇 1 m 안에 점이 있던 건 99건 중 15건뿐: 라이다 몸체 점 3순간(중심에서 8~38 cm·높이 0.84~0.91 m → 발판 안이라 후보 전부 충돌), 열린 문짝 1(지도 (9.35, 9.35), 높이 0.85~1.7 m), 카메라 4(앞 0.6~0.9 m·높이 0.5~0.9 m, 정체 미확인). **나머지 84건은 1 m 안에 점이 없는데 실패** → 실패 순간 로봇 발판과 로컬 비용 지도 칸을 맞대 어느 칸이 충돌을 냈는지 볼 것. 뒤쪽 1.5~2 m·높이 1 m 이상 점 589개는 따라오던 관찰자(앞으로 가는 후보와 무관)
- **라이다 몸체 점**: `lidar_cloud_guard.py`(팀원 코드)가 통과시킨 8~38 cm 점의 자리·높이를 정리해 상의
- **오른쪽 복도 축척**: 새 지도도 독립 bag 추적 이동량이 odom보다 5.5~5.8 % 짧다(아래 −0.8~−1.5 %, 위 −1.8 %). 지그재그 주행으로 odom이 더 쟀는지 지도가 짧은지 데이터로는 못 가른다 → 오른쪽 복도 한 구간 줄자 1회
- **원점 복귀 36 s**(새 지도 루프 13, 이전 6 s) 원인
- **무한 순찰 + 위치 자동 재설정 → 4시간 내구 시험**: 지도가 맞은 뒤의 안전장치로. 일치율이 기준 아래로 일정 시간 → 정지 → 주변 탐색 → `/initialpose` → 다음 경유점부터. 바퀴 수·시간·전압 기록. 설계 PM 승인 뒤
- **bag → 지도 만들기 도구화**: 오늘 절차(TROUBLESHOOTING 11-09 "오프라인 SLAM")를 스크립트로 저장소에 둘지 PM 결정
- **배터리**: 밤새 충전해도 아침 12.3 V(납축 완충이면 12.7 V 근처), 보드 전류 판독이 주행 중 0~0.9 A로 믿기 어려움 → 4시간 가능 여부는 완충 후 내구 시험(전압·시간 기록) + 집게형 전류계 1회 실측으로 판단

**결과 (11-09 저녁, 경유점 W1→W2→W3→W4→원점, s / 최적화 실패 건수)**

| 바퀴 | 조건 | W1 | W2 | W3 | W4 | 원점 | 합 |
|---|---|---|---|---|---|---|---|
| 8 (17:40쯤) | 기존 지도, 문 닫힘, 촬영자 옆 0.5~1 m 동행 | 61/10 | 71/5 | 95/43 | 41/7 | 7/0 | 275 s/65 |
| 9 (18:25) | 기존 지도, 문 열림 | 100/3 | 97/12 | **중단** 40 s | | | |
| 10 | 기존 지도, 문 열림 | 72/2 | 79/5 | **중단** 58 s | | | |
| 11 | 기존 지도, 문 열림, 사람 없음 | 68/4 | 49/2 | 97/14 | 35/14 | 6/0 | 255 s/34 |
| 12 | 기존 지도, 문 열림 | 62/7 | 45/5 | **중단** 43 s | | | |
| 13 | **새 지도**, 문 열림 | 82/4 | 57/1 | 118/25 | 31/0 | 36/0 | 324 s/30 |
| 14 | **새 지도**, 문 닫힘 | 70/5 | 59/10 | 131/43 | 35/11 | 18/0 | 313 s/69 |

- 오른쪽 위 코너 스캔 일치율: 루프 8 77~89 % → 루프 9~12 38~53 %(중단 3번은 AMCL이 로봇을 (11.0~11.4, 9.3~9.85), 지도상 위 복도 벽 너머로 끌어올려 경로 계획이 출발점부터 실패) → 새 지도 루프 13 86~93 %
- 루프 8 영상(IMG_1169~1172)과 bag: 촬영자가 로봇 옆 0.5~1 m로 따라 걸었고 W3 실패 43건이 그 구간에 몰림 → 사람 영향. 사람 없는 루프 11은 W3 14건
- 수동 한 바퀴(키보드, 원점 출발·복귀, 최고 0.51 m/s, 45 m·219 s) → 새 지도의 재료
- 배터리: 20:50 휴지 11.9 V

**변경**
- `limbo_navigation/maps/real_open_space_20261109.{pgm,yaml}`(새): 수동 한 바퀴 bag(`~/limbo_bags/manual_loop2_1109`, 원점 출발·복귀)으로 오프라인 slam_toolbox(`slam_real.yaml`) → 원점 주변(x −1.6~6, y −1.2~3) 벽 ICP로 기존 좌표에 맞춤(원점, +x = 복도 방향 유지). 680×560, origin (−10, −10). 쓰는 법: 실물 런치 `map:=…/real_open_space_20261109.yaml`, 떠 있는 상태면 `ros2 service call /map_server/load_map nav2_msgs/srv/LoadMap "{map_url: <yaml 경로>}"`(AMCL·전역 비용 지도가 바로 받음, 11-09 확인). **기본값은 아직 11-05**
- 새 지도 경유점(로봇이 실제로 지나간 복도 중심 기준): W1 (13.1, 0.1, 0°), W2 (13.4, 9.6, 90°), W3 (0.4, 9.8, 180°), W4 (0.6, 0.2, −90°), 원점 (1.0, 0.2, 180°). 기존 (12.0, 0.4)/(12.3, 8.0)/(0.7, 7.9)/(1.0, 0.3)에서 오른쪽 복도 +1.1 m, 위 복도 +1.8 m
- `tools/drive/pose_search.py` 도움말: 출발 전 확인은 `--radius 0.3 --step 0.1 --deg-step 2`. 기본 5° 간격은 실제 176°를 놓쳐 81 %로 나왔다(2° 간격 99 %)
- 출발 순서(대화 합의): 로봇을 세웠다고 하면 위치 탐색(≥ 85 %) → `/initialpose` → `nav_preflight.py` 위치 항목 → bag → 출발을 한 번에, 기준 미달이면 출발하지 않고 보고. 관찰자는 로봇에서 2 m 밖

**원인과 근거**
- 기존 지도 복도 길이(AMCL 위치로 잰 이동량 대 같은 구간 바퀴 odom): 오른쪽 복도 y 1.5→6.5 지도 5.00 m 대 odom 5.59~5.68 m(루프 10·11·12 모두), 위 복도 x 9→3 지도 6.00 m 대 odom 7.00 m. 바퀴 odom은 줄자와 1~1.5 % 일치(11-09 낮). 벽이 밋밋한 복도에서 AMCL은 앞뒤를 odom에 기대므로 실제 코너에 닿을 때 지도상 이미 코너를 약 1 m 지나 있다 → 코너 벽 모양을 보고 0.6~1 m 되돌려야 하는데, 루프 8·11은 성공, 9·10·12는 실패. **주의**: 아래 복도는 같은 방법으로 1~2 %가 나왔지만 일자 복도에선 AMCL이 odom을 따라가므로 그 값은 지도 정확도의 근거가 못 된다
- 문: 사용자 확인 — W2→W3, W3→W4(유리문) 두 곳이 복도 쪽으로 직각, 18시 이후 실험 때만 열림. 라이다가 문틀 자리로 교실 안 약 1 m 뒤 벽을 봐(루프 8과 10의 같은 자리 스캔 겹침) 되돌림을 더 어렵게 함. 주원인은 지도 길이, 문은 악화 요인. 위 복도 실패는 문을 닫아도 그대로라 문과 무관
- 수동 주행 bag을 AMCL과 독립으로 재추적(odom 예측 + 스캔-지도 국소 맞춤)해도 기존 지도로는 같은 코너에서 일치 37~43 %로 떨어지고 위로 끌려감 → AMCL 설정 문제가 아니라 지도 문제
- 새 지도 검증(지도 만들 때 안 쓴 bag을 같은 재추적으로): 루프 11 평균 95 %·최저 82 %·코너 96 %(기존 지도 72 %·21 %·41 %), 루프 12 평균 95 %·최저 86 %. 70 % 미만 0 %, 스캔당 보정 평균 1~2 cm

## 2026-11-09 (65) 복도 한 바퀴(37 m) 자율주행 완주 ×5(최고 265 s @0.5 m/s). 바퀴 수리 후 직진·회전 척도 재검증. 실물 비용 지도용 라이다 점군 5 cm 복셀 분리(18.6k → 1.0k점). 실물 로컬 비용 지도에서 정적 층 제거(좁은 복도 MPPI 전부 충돌 원인). 속도 상한 0.25 → 0.5 m/s(회전 0.8 유지). 실물 Nav2 `composition` 옵션. `spin_run.py`·`pose_search.py` 추가

**할 일**
- **MPPI "전부 충돌"(Optimizer fail) 뭉침의 최종 원인 특정** — 오른쪽 복도 y≈5.5~6.5·왼쪽 복도 y≈4·W1 진입에서 바퀴마다 반복(3~5차 6/11/10회). bag(`~/limbo_bags/glass_1109`, W1→W2)에서 확인된 것: 로봇이 비튼 두 순간 **카메라 점 139~250개가 정면 0.95~1.22 m·폭 0.6~0.9 m·높이 0.3~1.05 m에 0.5 s 나타났다 사라짐, 라이다는 그 자리에 없음** → 유리문에 비친 로봇 거울상(유리 거리의 2배)으로 판단. 카메라 표시 거리 1 m 적용 뒤 W1→W2 재주행에서도 실패 9/11회 남음 → **카메라만이 아님**. 1초 안 6~7회 뭉침 + `follow_path Aborting handle` 패턴은 새 경로 수신 때 MPPI 리셋 쪽도 의심. **내일부터 모든 주행에 bag 기본 기록**(점군·비용 지도·TF·`/plan`·`/cmd_vel_nav`) 후 실패 한 건씩 센서/경로로 특정. 현장 사진·영상(유리문)과 시각 맞춰 볼 것
- **Nav2 노드의 대기 CPU**: 로봇이 서 있어도 controller 13·planner 11·bt_navigator 10·lifecycle_manager 16 %씩, 합계 코어 0.85개. 점군을 솎아도(90 → 85 %) 컴포지션으로 묶어도(→ 80 %) 거의 안 줄었으므로 점군이 아니라 노드 자체 소모다. 원인(타이머·executor·bond) 조사 필요. lifecycle_manager 16 %가 가장 비정상
- **파이썬 필터 2개**(`lidar_cloud_guard.py` 8~10 %, `near_depth_filter.py` 21~24 %): 라이다 몸체 제거는 `pcl_ros filter_crop_box_node`(C++)로 교체 검토, 카메라 필터는 변환/연산 시간 분리 측정 후 C++·주기·장치 내 처리 중 결정. 팀원 코드라 상의 먼저. FAST-LIO2(코어 ~1개 예상) 전에 끝내 둘 것
- **도착 후 방향 맞추기**: 목표 방향이 진행 방향과 다르면 MPPI가 제자리에서 좌우 왕복(W1 30 s, W3 20 s, W2는 계획기 응답 지연과 겹쳐 중단). 경유점 도착 방향을 진행 방향으로 주면 회피됨. 근본 해결(도착 회전을 별도 동작으로) 설계 필요
- **위치 추정**: 두 번째 바퀴 끝에서 AMCL이 180° 뒤집힌 가설(일치 66 %)에 눌러앉음. 복도 앞뒤가 비슷하고 유리 투과 선이 많은 지도 탓 → 재지도(키보드, 양방향) + 초기화 뒤 일치율 검사 자동화. 지도 벽이 실제보다 20~30 cm 안쪽인 곳(원점 뒤 벽)도 재지도에서 잡기
- **복귀 목표는 x ≥ 1.0**: (0.3, 0.3)은 원점 뒤 벽(지도상 −0.3)에서 0.6 m라 몸체 0.32 + 팽창 0.45 안 → 도착 직전 "Optimizer fail" 반복. 목표는 벽에서 0.77 m 이상
- `nav_preflight.py` 5번(정적 지도)은 직선으로 재서 좁은 복도에서 벽 팽창(비용 53)에 걸린다 → 계획기 경로(`ComputePathToPose`)를 받아 그 위 비용을 보도록 바꿀 것. 11-09 왼쪽 복도에서 계획기 경로 비용 0인데 직선 53으로 막힘
- 오른쪽 복도 y≈5.5~6.5, 왼쪽 복도 y≈3.3~3.7에서 두 바퀴 모두 3~15 s 멈춤·후진 — 그 자리에 뭐가 있는지(유리·문·낮은 물건) 현장 확인
- 좌표 용어: 지도 **+x = 복도 쪽(6 m 직진 방향, 초록)**, **−x = 원점 뒤 벽 쪽**. 11-09 대화에서 라벨이 반대로 쓰여 한 번 혼선

**결과 (11-09, 보드 12.2~12.3 V)**
- 바퀴 수리(허브 어댑터 교체) 후 척도: `straight_run` 2 m@0.1 m/s → 줄자 2.03(1.1 %), 6 m@0.25 m/s → 6.0±0.1(1.5 %). `spin_run` 720° 좌 odom/AMCL 0.9905, 우 1.0034, 제자리 이탈 4 mm → 반지름 0.0738·간격 0.53 **유지**
- 자율주행: +x 6 m 3회(25~30 s, ±3~6°), 복귀 (1.0, 0.3, 180°) 33 s 흔들림 없음, 복도 한 바퀴 W1→W2→W3→W4 1차 완주(W2는 위치 도달 후 방향 회전 중 ABORTED: 계획기 응답 timeout), 2차 완주(93/129/136/55 s + HOME 29 s), 3차(복셀 적용, 아래 표)
- 복셀 전후(주행 중 5 s 표본): load1 최대 6.5 → 3.9, controller 평균 41 → 25 %(구간 길이 달라 평균은 참고만), 최적화 실패 1 → 0
- 한 바퀴 시간(W1/W2/W3/W4/HOME, s): 2차 0.25 m/s 93/129/136/55/29=442 · 3차 복셀 75/84/185/50/13=407 · 4차 0.4+정적층 제거 50/65/61/51/60=287 · 5차 0.5 75/55/76/37/22=**265**. 최적화 실패(구간당): 3차 1/6/6/4/0, 4차 2/11/12/11/14, 5차 3/10/18/6/0 — 시간은 줄었으나 실패는 안 줄어 원인이 남아 있음
- 배터리: 아침 12.3 V → 15:25 11.8 V(주행 약 2시간)

**변경**
- `drive.yaml`: `max_linear_m_s` 0.25 → 0.4(한 바퀴 검증) → **0.5**(PM 결정). 회전은 1.0으로 한 바퀴 돌아 본 뒤 **0.8로 되돌림**: 0.5 전진 + 1.0 회전 동시면 바깥 바퀴 0.765 m/s = QPPS 최고의 96 %로 포화, 0.8이면 0.71(89 %). 가속 0.5 m/s²로 1 s 도달. MPPI `vx_max/wz_max`·Shim 회전 속도·복구 회전·평활기 상한은 생성기가 따라감. `straight_run.py`·`spin_run.py` 상한도 맞춤
- `build_real_configs.py`: 실물 **로컬 비용 지도에서 `static_layer` 제거**(글로벌은 유지). 테스트 `test_real_local_costmap_has_no_static_layer`
- `build_real_configs.py`: 실물 STVL `rgbd_mark.obstacle_range` 4.5 → **1.0 m**(PM "일단 진행"). 카메라 역할 = 라이다 사각(1 m 앞 높이 0.7 m 아래)의 가까운 낮은 장애물, 유리 거울상은 ≥1 m. 지우기·충돌 감시·YOLO 입력은 그대로. 테스트 `test_real_camera_marks_only_near_obstacles`. **효과 미확인**(적용 후 1회 주행에서 실패 여전)
- `start_mid360.launch.py`(mounted): `pcl_ros filter_voxel_grid_node` `mid360_costmap_voxel`(leaf 0.05) 추가 → `/mid360/points_costmap`. 원본 `/mid360/points`·몸체 제거 `/mid360/points_filtered`(→ `/scan`, AMCL)는 그대로(FAST-LIO2 등 전밀도용)
- `build_real_configs.py`: 실물 프로필의 STVL `mid360_mark/clear`(로컬·글로벌)와 collision_monitor 라이다 소스 토픽을 `/mid360/points_costmap`로. 시뮬 원본 무변경. 테스트 `test_real_costmaps_use_the_downsampled_lidar_cloud`(젯슨 14 통과)
- `start_nav2_real.launch.py`: `composition:=true`면 노드 8개 + lifecycle_manager를 `component_container_isolated` 하나에 싣는다(플러그인 이름 명시, 컨테이너에도 params 파일을 줘야 함 — 안 주면 costmap이 기본 레이어로 떠 MPPI 세그폴트). 기본 `false`: 정지 측정에서 90 → 80 %뿐이라 기본값은 유지하고 옵션만 남김
- `tools/drive/pose_search.py`(새): 위치 추정이 틀렸을 때 가정 위치 주변·전 방향 스캔 일치 전수 비교로 실제 자세 찾기(11-09: 27 % → +175° 80 %)
- `tools/drive/spin_run.py`(새): 제자리 회전 시험. odom yaw 누적이 목표에 닿으면 정지, AMCL yaw 누적과 비율(= 바퀴 간격 보정 배율) 출력
- `tools/drive/near_obstacles.py`(새, 11-08 작성분 포함): 로봇 주변 점을 센서별·비용 지도별로 base_footprint 기준 나열
- `nav_preflight.py`: odom 주기는 수신 구간으로, 로컬 비용 지도는 자기 좌표계(odom), `--goal`이면 목표 쪽 검사

**원인과 근거**
- 라이다 점군: `/mid360/points_filtered` 18,536점·10 Hz·5.6 MB/s를 6곳(로컬 mark/clear, 글로벌 mark/clear, 충돌 감시, 스캔 변환)이 각자 받아 풀고, 비용 지도 2개가 전밀도로 복셀·광선 처리. 5 cm 복셀(비용 지도 해상도와 같음) 뒤 1,014점·270 KB/s, 비용 지도 쪽 구독 5곳이 이걸 받음
- 컴포지션 측정(정지 20 s): 따로 90 % → 컨테이너 80 %. 복사 비용은 10 %. 나머지는 노드 자체 대기 소모
- 위 복도(폭 1.5~1.7 m) 185 s의 정체: 멈춘 구간에서 controller CPU가 13~30 %로 **낮았다** → 계산 부족이 아니라 MPPI 후보 2,000개가 전부 충돌 판정(`Optimizer fail` 13회). 로컬 비용 지도에 정적 층이 있어 지도 벽(실제보다 20~30 cm 안쪽인 곳 있음: 원점 뒤 벽 라이다 0.95 m 대 비용 지도 0.62 m)이 로컬 회피에 들어왔고, 좁은 복도에서 로봇 반폭 0.3 + 팽창 0.45를 빼면 여유 0 → 제거. 아래 복도(폭 3 m)에서 문제없던 것과 일치
- 11-09 1차 주행 "줄자 7.39 m 대 odom 5.3 m"는 로봇 쪽 수치로 재현 불가(카운트 L 5.35/R 5.39 m, 속도 상한 0.25 × 25 s ≤ 6.2 m, 같은 속도 6 m 재시험 1.5 % 일치). 기준점 문제로 판단하고 종결
- AMCL이 복도 앞뒤 위치를 못 잡는 이유: 벽이 진행 방향과 나란해 라이다는 옆·방향만 구속하고 앞뒤는 odom을 따른다. 일치율 99 %가 x 위치와 무관하게 나올 수 있음 → 일치율만으로 "위치 맞음"을 단정하지 말 것

## 2026-11-08 (64) 실물 자율주행 첫 성공(6 m 왕복). 제자리 회전 29 s → 6 s: `RotationShimController`(MPPI 앞단) + `PoseProgressChecker`(회전도 진행으로). 점검 도구 3건 수정. 바퀴 파손으로 시험 중단

**할 일**
- **바퀴 수리 먼저.** 마지막 복귀 주행 중 바퀴가 부러짐(기계 파손). 주행 기록 `~/limbo_bags/nav_1108_1/control.jsonl`의 7개 주행 구간 모두 실측/목표 바퀴 속도 0.99~1.01, 최대 PWM 18,892/32,767 — 엔코더(모터축)는 끝까지 정상이라 허브·축·바퀴 쪽 파손은 기록에 안 잡힌다. 수리 후 바퀴 반지름(60)·좌우 균형(60의 좌우 차 4~7 mm)을 다시 재야 한다
- **뚜껑(또는 윗판 위 물건) 확인 후 재측정**: 마지막 복귀 주행에서 라이다 `/mid360/points_filtered`가 로봇 중심 0.23~0.7 m, 높이 0.80~1.37 m에 1,330점을 봄 → 로컬 비용 지도에 로봇 발밑 막힌 칸(반경 0.45 m 안 비용 99~100이 켜졌다 꺼졌다) → MPPI가 제자리에서 ±90° 흔들며 "Failed to make progress". 몸체 필터는 45×45 cm·높이 0.79 m까지만 지움(`MID360s_mount.json`, 11-04 팀원 메모 "lid must remain closed"). 뚜껑이 열려 있었는지 확인하고, 닫은 상태에서 `tools/drive/near_obstacles.py`로 0.7 m 안 라이다 점이 0인지 확인. 열림이 원인이면 뚜껑 고정 또는 몸체 필터 높이 조정(설계 결정)
- 시작 절차는 (63)과 같고 `nav_preflight.py --goal X Y`가 목표 쪽을 본다. 복귀 주행은 `(0.3, 0.3, 180°)`
- 지도 검증(복도 모서리 너머) 시작은 바퀴 수리 후

**결과 (11-08, 보드 12.2 V, 목표 (5.65, 0.30) ↔ (0.3, 0.3))**
| 주행 | 결과 | 시간 | 진행 없음 | 방향 흔들림 |
|---|---|---|---|---|
| 1 +x 6 m (경로 앞) | 도달 | 27 s | 0 | ±4° |
| 2 복귀 180° + 5 m (MPPI만) | 도달 | 회전 30 s + 주행 | 3 (전부 회전 중) | ±18° |
| 3 제자리 180°만 | 도달 | 7 s, 0.57 rad/s | 0 | — |
| 4 +x 재현 (PoseProgress) | 도달 | 25 s | 0 | ±4° |
| 5 복귀 (PoseProgress) | 도달 | 회전 29 s + 주행 | 0 | ±18° |
| 6 +x, 경로 등 뒤 (RotationShim) | 도달 | 회전 6 s + 주행, 29 s | 0 | ±7° |
| 7 복귀 (RotationShim) | 중단 | 회전 6 s, 주행 15 s 뒤 제자리 흔들림 | 1 | 발밑 막힌 칸(위 할 일) |

**변경**
- `nav2_params.yaml`(시뮬 원본) → `nav2_real.yaml` 생성: `FollowPath`를 `nav2_rotation_shim_controller::RotationShimController`로, `primary_controller` MPPI(기존 MPPI 설정은 그대로 같은 이름 아래). 경로 방향과 45°(`angular_dist_threshold` 0.785, Nav2 기본) 이상 차이 나면 제자리 회전 후 MPPI에 인계. `rotate_to_heading_angular_vel`은 시뮬 1.8(= wz_max), 실물은 `build_real_configs.py`가 주행 노드 상한 0.8로; `max_angular_accel`은 시뮬 4.0(= az_max), 실물은 drive.yaml 도출값 1.894. 나머지(`forward_sampling_distance` 0.5, `simulate_ahead_time` 1.0)는 Nav2 기본값
- 진행 감시기 `SimpleProgressChecker` → `PoseProgressChecker`(`required_movement_angle` 0.5 rad 추가, 반지름 0.5 m·10 s는 그대로)
- `test_real_integration.py`: 생성된 실물 프로필의 RotationShim 플러그인·회전 속도(= `max_angular_rad_s`)·회전 가속(= 도출값) 단언. 젯슨 13 통과
- `tools/drive/nav_preflight.py`: ① odom 주기를 첫 수신~마지막 수신 구간으로(구독 붙는 시간이 섞여 20 Hz가 10.8 Hz로 나옴) ② 로컬 비용 지도는 자기 좌표계(odom)로 자세를 구해 읽음(map 자세로 읽어 엉뚱한 칸을 봄) ③ `--goal`이 있으면 로컬 비용 검사를 로봇 정면이 아니라 목표 쪽으로(목표가 등 뒤면 정면 벽은 상관없음)
- `tools/drive/near_obstacles.py`(새): 로봇 2 m 안에 잡힌 것을 센서별(`/scan`·카메라·라이다 점군)과 로컬 비용 지도 막힌 칸으로 base_footprint 기준 나열. 오늘 뚜껑 추정에 쓴 스크래치 스크립트를 도구로 올린 것
- `docs/TROUBLESHOOTING.md`: 경로가 등 뒤일 때 MPPI 회전 지연 + 가짜 진행 실패 1건, 로봇 윗부분이 라이다에 잡혀 발밑 장애물 1건. 11-07 카메라 항목의 확인란을 11-08 결과로

**원인과 근거**
- 회전 지연은 MPPI 구조: 경로가 정반대(180°)면 좌·우 회전 비용이 같아 2,000개 샘플의 가중 평균이 0 근처에서 상쇄된다. 실측 명령 0.04~0.10 rad/s(0°→80°, 22 s), 80° 아래부터 0.37 rad/s로 가속, 145°부터 전진. 같은 180°라도 목표 자체가 회전(GoalAngle)이면 0.57 rad/s(주행 3)라 바퀴·평활기 문제는 아님(명령=실측, 지연 없음)
- 진행 감시기는 이동 거리만 봐서 느린 회전이 10 s를 넘길 때마다 실패→복구가 끼어듦(주행 2의 3회 전부 회전 구간). PoseProgressChecker로 0회(주행 5), 회전 속도는 그대로 느림 → 둘 다 필요
- RotationShim은 Nav2 표준 패키지(`ros-jazzy-nav2-rotation-shim-controller 1.3.13`, MPPI와 같은 버전, 젯슨에 이미 설치). 가중치 조정(PathAngleCritic 2 → ?) 대신 고른 이유: 근거 없는 숫자 맞추기가 되고 다른 상황의 균형을 깨기 때문
- 복귀 방향 ±18° 흔들림(주행 2·5)은 AMCL−odom yaw 차가 주행 중 3~11°, 빠른 회전 중 최대 21°까지 벌어진 것과 같이 감(돌아오는 방향 스캔 일치 80~85 %, 갈 때 97 %). 주행 7은 거기에 발밑 막힌 칸이 겹침
- 이번 "54 cm 오차"는 오차가 아님: 출발선 x 0.07, 복귀 목표 x 0.30, 허용 0.25 → x 0.56 정지. 테이프 54 cm 대 추정 49 cm

## 2026-11-07 (63) 자율주행 출발 전 점검 도구 `tools/drive/nav_preflight.py` + 실물 런치 `filter_near_depth` 기본값 `true`(카메라 가짜 근거리 점 → 가상 벽). TROUBLESHOOTING 2건

**할 일 (11-08 시작 절차)**
- Jetson: `git pull`(런치·도구만이라 빌드 불필요. `limbo_bringup` 테스트 `test_real_integration.py` 한 번)
- 순서: `run_teleop.sh record_dir:=~/limbo_bags/nav_1108_1` → `run_real.sh encoder_source:=external localization:=amcl map:=<real_open_space_20261105.yaml> yolo:=false` → 로봇을 지도 원점(ㅁ자 복도 아래 왼쪽 모서리)에 **+x(초록 점)** 를 보게 놓고 `/initialpose` (0, 0.3, 0°) → `run_nav2_real.sh cmd_vel_out:=/cmd_vel` → `python3 tools/drive/nav_preflight.py --goal 5.65 0.30` **전부 통과해야** 목표 (5.65, 0.30) 전송
- 통과 기준: 목표 도달, "Failed to make progress" 0회, 방향 흔들림 ±5° 안. 되면 (62)의 가속 통일·(60)·(61)까지 실물 확인 완료
- 안 되면 그 층의 숫자(점검 도구 출력·`navwatch` 3 s 간격 MPPI 출력)를 들고 판단. 추측으로 바꾸지 말 것
- 센서 입력 확인 전에 Nav2 목표를 보내지 말 것 — 11-07 오후 3시간이 이 순서를 건너뛴 대가

**변경**
- `tools/drive/nav_preflight.py`(새): 6항목 점검(odom 주기, 위치 추정 스캔 일치율, 카메라 근거리 점, 로컬 비용 지도 정면, `--goal` 쪽 정적 지도, Nav2 노드). 실패가 있으면 종료 코드 1
- `start_real.launch.py`·`start_rgbd_points.launch.py`: `filter_near_depth` 기본값 `true`
- `docs/TROUBLESHOOTING.md`: 가짜 근거리 점 가상 벽, AMCL 가짜 수렴

**원인과 근거**
- 11-07 오후 Nav2 시도 7회의 실패 원인 분해: ① 로봇을 지도 반대 방향으로 놓음(1회) ② MPPI 가속 가정 7배 불일치(수정, (62)) ③ 지도에 없는 −x 쪽 목표(2회, 계획 실패) ④ AMCL 가짜 수렴(2회) ⑤ 카메라 가짜 근거리 점의 가상 벽(모든 회차에 존재, 11-06 팀원 로그의 "첫 0.75 m 비용 92"도 같은 것). 바퀴는 어느 회차에서도 명령을 정확히 따랐음(명령 누적 회전과 odom 1~3° 일치)
- 필터 켠 뒤 깊이 영상 통계: 유효 81 %, 1 m 안 0 %, 1~3 m 42 %, 3 m 이상 58 %. 끄면 정면 0.5~1.25 m에 점 150개(앞을 비워도 그대로)
- 팀원 11-06 1차 목표 주행 마지막 1.1 s: Nav2 명령 바퀴 이동 L 0.184 / R 0.078 m(꺾는 명령, 가상 벽 회피로 추정), 실측 L 0.189 / R 0.037(오른쪽 바퀴 정지) → "왼쪽으로 치우침"은 카메라(명령)와 바퀴(실행) 둘 다
- 필터·런치 기본값은 팀원 커밋 `2485d9c`(jetson 브랜치에만 있음)

## 2026-11-07 (62) 가속 한계를 한 값으로: 주행 노드 `target_slew_rad_s2` 2.0 → 6.8(전진 0.5 m/s², 회전 1.9 rad/s²), MPPI `ax_max/az_max`·속도 평활기 `max_accel`은 `build_real_configs.py`가 그 값에서 도출. 테스트 240+1

**할 일**
- Jetson: `git pull` 뒤 `limbo_bringup` 테스트(`test_real_integration.py`)로 설치본과 소스 일치 확인. 주행 노드·Nav2 다시 띄워 6 m 목표
- 통과 기준: 목표 (5.65, 0.30) 도달, 방향 흔들림 ±5° 안, "Failed to make progress" 0회

**변경**
- `drive.yaml` `target_slew_rad_s2: 6.8`(주석에 근거). `tools/drive/build_real_configs.py` `nav2_profile(data, drive, geometry)`: `ax_max = slew × 반지름`, `az_max = 2 × ax_max / 간격`, 평활기 `max_accel/max_decel` 같은 값. `wheel_geometry()`는 `wheel_odometry.yaml`에서. `nav2_real.yaml` 재생성(가속 세 값만 바뀜)
- `test_real_integration.py`: 생성기 호출에 geometry, 가속 한계 일치 테스트 1개 추가

**원인과 근거**
- Nav2 자율주행(11-07, 1 m·6 m 목표 5회) 전부 지그재그 뒤 "Failed to make progress": MPPI는 회전 가속 4.0 rad/s²·전진 1.0 m/s²를 가정하는데 주행 노드가 보드에 거는 가속은 0.56 rad/s²·0.15 m/s²(7배 느림). t=1 s 좌회전 0.36 명령 → 바퀴 목표 ±1.3 rad/s인데 실측 −1.06/+0.82로 0.6 s 늦게 도달 → MPPI가 더 밀고 넘친 뒤 반대로 −0.4 → 반복. 명령 누적 회전과 odom 방향은 1~3° 안에서 일치(바퀴는 늦게나마 정확). /odom 속도값도 명령과 일치(0.3 → 0.299, 0.1 → 0.100). YOLO를 꺼 부하를 내려도(load 3.7) 같고, `wz_std`만 0.1로 줄여도 같음 → 샘플 떨림·부하가 아니라 지연
- 11-06 팀원이 본 ±15° 흔들림도 같은 원인(굼뜬 바퀴가 진폭을 줄였을 뿐)
- 카메라를 끄면(`camera:=false`) 충돌 감시가 rgbd 입력 없음으로 모든 명령을 0으로 막는다. 부하를 빼려면 `yolo:=false`만
- 로컬 비용 지도의 막힌 칸 2,500~3,000개는 0.3~1.0 m 높이의 실제 물체(점군 높이 분포로 확인). 유령 아님
- Nav2 프로세스를 끌 때 `nav2_` 패턴으로 모으면 AMCL·map_server(같은 접두사)까지 죽는다. 런치 PID에 INT

## 2026-11-07 (61) `control_mode` 기본값 `board_speed`로 + TROUBLESHOOTING 3건(저속 정지·출발 지연 원인, 최대 전압 자동 감지, 보호 장치 오판)

**할 일**
- Jetson: `git pull`. 이제 `run_teleop.sh`·`run_real.sh`를 인자 없이 띄워도 보드 속도 제어로 돈다. 예전 방식은 `control_mode:=host_duty`
- 보정 확인: 반지름 0.0738로 6 m 직진 → odom 6.001 m, 줄자 6.025 m(0.4 %). 확정
- Nav2 자율주행은 바퀴와 무관하게 MPPI가 전진 명령을 안 내는 문제가 남아 있음(비용 지도가 센서 메시지를 TF 시각 불일치로 버림, load 5~6). 다음 시험은 센서+AMCL+Nav2를 띄우고 정면 1 m 목표부터, MPPI 출력·TF·부하를 같이 본다

**변경**
- `drive.yaml` `control_mode: board_speed`(주석에 통과 근거). `docs/TROUBLESHOOTING.md` 실물 절에 3건

**원인과 근거**
- PM 결정(11-07): 바퀴 쪽 검증(계단 응답·키보드·자동 직진 3회) 통과로 기본값 전환. 다른 보드에 꽂으면 속도 제어 값이 없어 노드가 시작을 거부하므로 조용히 잘못 돌 일은 없음

## 2026-11-07 (60) 바퀴 유효 반지름 0.075 → 0.0738 (6 m 직진 실측 보정). 자동 직진 6 m 2회 통과: 좌우 차이 4 mm, 방향 +0.5°, 출발 0.4 s

**할 일**
- Jetson: `git pull`(설정 파일만이라 빌드는 symlink로 반영). 주행 노드 다시 띄운 뒤 `straight_run.py --distance 6` 한 번 더: odom이 줄자와 ±5 cm 안이면 보정 확정

**변경**
- `wheel_odometry.yaml`: 좌우 반지름 0.0738. 주행 노드·odom·`drive_report.py`·`board_setup.py`가 같은 파일을 읽는다

**원인과 근거**
- 자동 직진(`straight_run.py`, board_speed, 0.1 m/s, 기록 `~/limbo_bags/straight_1107_1`) 2회: 바퀴 odom 왼쪽 6.050/6.051 m, 오른쪽 6.046/6.046 m(차이 4 mm), /odom 방향 변화 +0.5°, 옆으로 왼쪽 9 cm, 출발 지연 왼쪽 0.45 s·오른쪽 0.35~0.40 s, 실측 속도 0.100/0.100, 보드 출력 평균 18~20 %(최대 30 %), 전류 바퀴당 1.65~1.7 A, 배터리 11.9 V. 11-06(젯슨 PI, Nav2)의 4.4 m에 좌우 차 0.14 m·방향 ±15°·출발 1.5~2.0 s와 비교
- 줄자 실측 5.95 m(바퀴 접지점 기준, ±5 cm) → 바퀴 odom이 1.6 % 많이 읽음 → 반지름 0.075 × 5.95/6.048 = 0.0738. 좌우 균형은 손대지 않음(비율 그대로)

## 2026-11-07 (59) 자동 직진 시험 도구 `tools/drive/straight_run.py` + "반대로 달림" 판정에 속도 추정 지연 틱 반영(복구 회전 중 또 꺼진 것). 테스트 240

**할 일**
- Jetson: `git pull` 뒤 `limbo_hardware` 빌드. 주행 노드 `control_mode:=board_speed record_dir:=...`로 띄운 뒤 `python3 tools/drive/straight_run.py --distance 6 --speed 0.1`. 끝나면 `drive_report.py <record_dir>`로 좌우 이동량·출발 지연 확인
- 통과 기준(PM 11-07): 6 m를 똑바로. odom 방향 변화 ±3° 안, 좌우 이동량 차이 11-06(4.4 m에 0.14 m)보다 작게. 바닥 끝점에서 옆으로 샌 거리는 줄자로

**변경**
- `tools/drive/straight_run.py`(새): /cmd_vel로 10 Hz 직진 명령, /odom 거리로 목표에서 정지. 결과: 거리·시간·평균 속도·방향 변화·옆으로 샌 거리
- `drive_node.py` `_runs_wrong_way`: 연속 틱 요구를 `ceil(velocity_window_s / control_period_s) + MAX_CONSECUTIVE_ERRORS`(= 2 + 3)로. 테스트 1개 추가

**원인과 근거**
- 2차 자율주행(17:46~48)도 Nav2 복구 회전만 반복(MPPI 출력 v 최대 0.026 m/s — 충돌 감시·주행 노드 이전 단계에서 이미 0). 그 사이 17:47:00 주행 노드가 또 "왼쪽 바퀴 반대 방향으로 빨라짐(목표 −40 카운트/초, 실측 0.27 rad/s)"으로 종료: 회전 중 목표가 뒤집히면 0.1 s 창 추정이 2~3틱 더 옛 방향으로 빨라져 보이는데 (58)의 3틱 기준이 그 안에 있었다
- 로컬 비용 지도의 검은 덩어리는 유령이 아니라 0.3~1.0 m 높이의 실제 물체(점군을 base_footprint로 바꿔 세면 0.3 m 아래 점 0개). 2D /scan은 그 높이를 안 보여 달라 보였을 뿐
- PM 지시(11-07): 직진 6 m를 자동으로 똑바로 가는 것이 제1 과제. Nav2·AMCL·비용 지도는 그 뒤

## 2026-11-07 (58) 보드 설정 완료(엔코더 방향·QPPS·속도 PID·전압 한도 저장) + `board_speed`의 "반대로 달림" 판정이 Nav2의 작은 회전 명령 뒤집힘을 오판해 노드를 끝내던 것 수정. 테스트 239

**할 일**
- Jetson: `git pull` 뒤 `limbo_hardware` 빌드. 보드에는 이미 값이 저장돼 있어 `control_mode:=board_speed`로 바로 띄울 수 있다
- 자율주행 재시험: 로봇을 지도 원점에 **지도 만들 때 향한 방향**으로 놓고(1차는 반대로 놓아 Nav2가 진행 못 함) `/initialpose` (0, 0, 0°) → 목표 (5.65, 0.30)

**변경**
- `drive_node.py` `_runs_wrong_way`: "목표와 반대 방향 + 빨라짐"에 **목표 크기보다 빠름** 조건과 속도 추정 해상도(창 안 한 카운트) 이상 늘어난 것만 "빨라짐"으로 세는 조건 추가. 테스트 1개 추가(11-07 재현), 치명 사례 테스트는 목표보다 빠른 값으로
- `board_setup.py`: voltage 단계에 `--auto-offset`(기본 0), 명령 110 선택 읽기

**원인과 근거**
- 보드 설정(11-07, 바퀴 띄우고, 기록 `~/limbo_bags/board_setup/`): 엔코더 모드 M2 0x40(두 바퀴 전진 +, 20 % 확인 회전 +1091/+792), QPPS 100 %에서 M1 6264·M2 6351(0.80/0.82 m/s, 12.0 V). 중간 출력에서는 오른쪽이 왼쪽의 65 %(50 %: 0.24 vs 0.39 m/s) — 같은 출력에서 오른쪽이 느린 것이 숫자로 확인됨. 속도 PID 매뉴얼 기본값 1.0/0.5/0.25로 계단 응답 0.07·0.13 m/s 오차 ±1 %, 도달 0.2~0.5 s(0.13은 가속 제한 0.15 m/s²에 걸림). P 2.0/I 0.25는 도달 0.5 s·오차 −10 %로 더 나빠 기본값 유지. 0.03 m/s의 넘침 ~100 %는 걸린 바퀴가 풀리는 튐 + 20 Hz 측정 해상도(한 표본 12카운트)로 공중에서는 더 못 가림
- 전압 한도: 최대 전압 "자동 감지"가 켜져 있어 켤 때마다 최대 = 그때 전압 + 2 V가 됨(11.9 V에서 켜 13.9, 충전기 29.1 V에서 켜 31.1). 11-03 "충전 뒤 전압 높음으로 안 움직임"은 낮은 전압에서 켠 뒤 충전해 한도를 넘은 것. 명령 57의 오프셋 바이트를 0으로 쓰면 꺼진다(저장·재시작 뒤 16.0 유지 확인). 최소는 10.0을 쓰면 9.9로 읽힘(보드 특성)
- 바닥 키보드 확인(board_speed, `~/limbo_bags/floor_board_1107_1`): 0.1 m/s 전진에서 두 바퀴 0.25 s 안에 구르기 시작, 0.5 s에 목표 도달(11-06 1.5~2.0 s), 정상 오차 ±0.1 rad/s, 보드 출력 13~28 %로 알아서 변함, 전류 바퀴당 1.6~1.7 A, 상태 비트 0
- 1차 자율주행 실패: 로봇을 지도 반대 방향으로 놓은 상태에서 초기 위치를 0°로 줌 → Nav2 전진 명령 거의 없음(83 s 동안 v 최대 0.05, 전진 0.27 m), "Failed to make progress" 10 s마다, 복구 회전 7번(odom +225°, AMCL도 같은 만큼 → 위치 추정 자체는 일관). 그 도중 Nav2가 100 ms 사이에 회전 방향을 뒤집었고 왼쪽 바퀴가 옛 방향으로 막 구르기 시작(−0.017 → −0.034 → −0.049 → −0.085 rad/s, 목표 +0.11)한 3틱을 "반대로 달림"으로 판정해 노드가 꺼짐 → odom TF 끊김 → AMCL 스캔 버림
- 29.2 V 건: 충전기를 꽂은 채 보드가 충전기 출력을 읽는다. 뽑으면 12.2 V. 최대 16 V 한도로 충전기 꽂은 채 출력이 막히게 됨
- Jetson에서 `setsid -f`로 띄운 런치는 Ctrl+C 신호(INT)를 받는다. 비대화식 셸의 `&` 백그라운드는 INT를 무시하도록 상속돼 PID로 끝내야 했음(11-07 오전). `run_nav2_real.sh`는 실행 비트가 없어 `bash`로 띄움

## 2026-11-07 (57) 보드 설정 도구 `tools/drive/board_setup.py`: 모션스튜디오 없이 Jetson에서 왼쪽 엔코더 방향·QPPS·속도 PID·전압 한도를 넣고 저장·확인. 계단 응답 시험 포함. 테스트 238

**할 일**
- Jetson: `git pull` 뒤 `limbo_hardware` 빌드. 바퀴를 띄운 채 `source limbo/install/setup.bash; python3 tools/drive/board_setup.py <단계>`를 backup → encoder → qpps → pid → voltage → save → step 순서로, 단계마다 출력(JSON 요약)을 보고 다음으로. 기록은 `~/limbo_bags/board_setup/`
- step 결과(90 % 도달 시간, 넘침, 정상 오차, 멈춤)를 보고 P·I를 바꿔 `pid` → `step`을 반복. 통과하면 `save`로 저장하고 주행 노드를 `control_mode:=board_speed`로 띄워 (55)의 실물 확인 순서로
- 되돌리기: `board_setup.py restore --from ~/limbo_bags/board_setup/backup_<시각>.json` 뒤 `save`
- 충전기를 꽂은 채로는 주행하지 않는다: 보드가 충전기 출력을 읽어 29.2 V가 나온다(11-07 실측, 뽑으면 12.2 V). voltage 단계에서 최대 16 V로 두면 그 상태에서는 보드가 "전압 높음"으로 출력을 막는다

**변경**
- `tools/drive/board_setup.py`(새): 단계 backup·encoder·qpps·pid·voltage·save·step·restore. 모든 모터 동작은 20 Hz로 명령을 다시 보내며(보드 timeout 0.5 s) 카운트·PWM·전류·상태를 jsonl로 남기고, 끝은 반드시 duty 0. 보드 상태에 정지 비트가 켜지면 바로 멈추고 끝낸다
- `roboclaw_drive.py`: 읽기 명령 59(전압 한도, 펌웨어 4.4.9의 5바이트)·110(속도 오차 한계) 허용, `write_setting(command, payload)`(ACK 설정 명령. 주행 노드는 쓰지 않음)
- 테스트 `test_board_setup.py`(새 15개: 패킷 바이트 순서 D·P·I·QPPS, 단계 흐름, 모터 반전 비트 거부, 가짜 보드로 QPPS 측정·계단 지표), `test_roboclaw_drive.py` +2. 전체 238

**원인과 근거**
- 11-07 PM 지적: 모션스튜디오는 사람이 손으로 같은 값을 넣는 도구일 뿐이라 Jetson에서 시리얼로 쓰면 USB를 옮길 필요가 없다. (55)에서 모션스튜디오를 고른 건 보드 설정 쓰기를 피하려던 것이었고 꼭 그래야 할 이유는 없었다
- 명령 28·29의 페이로드 순서는 매뉴얼 rev 6.0대로 D, P, I, QPPS (읽기 55·56은 P, I, D, QPPS). 명령 57은 최소·최대(0.1 V)·자동 최대 오프셋 1바이트로, 펌웨어 4.4.9의 59 응답 5바이트와 맞는다
- 상태 비트 0x01000000·0x02000000은 "Idle Motor 1·2" 경고다(매뉴얼 상태 표). (56)에서 속도 오차 경고로 적은 것은 틀렸음. 속도 오차는 0x0100·0x0200(리셋까지 유지되는 오류)
- PID 시작값 1.0 / 0.5 / 0.25는 매뉴얼 명령 28의 기본값. 출발점일 뿐이고 step 결과로 바꾼다
- 11-07 보드 읽기(충전기 뽑은 뒤): 속도 PID·QPPS·위치 PID 전부 0, 엔코더 모드 0/0, 배터리 12.2 V(하룻밤 충전 뒤 쉬는 전압. 용량이 많이 준 배터리)
- 11-06 팀원 기록 `tools/motors/tracking_trials_20261106.txt`를 다시 읽음: 목표점은 스크립트가 보낸 NavigateToPose (5.65, 0.30)(지도 좌표, 거의 직진 5.65 m), AMCL 초기 위치는 따로 안 잡고 지도 원점 근처에서 출발(매칭 92~97 %). 두 번 다 4.2~4.4 m에서 좌우 이동량 불균형으로 스크립트가 취소, 방향 오차 ±15°, 출발 지연 1.5~2.0 s, 배터리 최저 11.3 V

## 2026-11-06 (56) 벤치 도구도 엔코더 전진 부호를 보드에서 읽음 + 주행 기록 요약 도구 `tools/drive/drive_report.py`. (55)를 Jetson에 올려 실물 보드에서 읽기·주기 확인

**할 일**
- Jetson: `git pull` 뒤 `limbo_hardware` 빌드. 이제 벤치 도구(`speed_bench_node`)도 보드 엔코더 방향 설정을 따라가므로 (55)의 "쓰지 말 것"은 해제
- 주행 시험 뒤 `tools/drive/drive_report.py <record_dir>`로 요약을 뽑아 (54)의 11-06 기록과 비교한다. 기준값: 11-03 키보드 주행(기존 방식, 상한 25 %)은 출발 지연 중앙값 왼쪽 1.05 s·오른쪽 1.30 s, 목표 0.25 m/s에서 실측 0.16~0.17 m/s, 목표 0.03 m/s 이상인데 안 돈 시간 왼쪽 18.6 s·오른쪽 24.3 s(1153 s 기록, 지금 치수로 환산)
- 보드의 주전원 전압 한도는 지금 최소 5.9 V·최대 31.1 V다(읽기만 함). 충전 직후 "전압 높음 경고"로 안 움직이던 문제(11-03)는 이 값에서는 안 생긴다. 다만 최소 5.9 V로는 보드가 납축전지를 지켜 주지 못하므로(노드의 10.0 V 정지에만 의존) 모션스튜디오에서 Min 10 V로 올릴 것

**변경**
- `roboclaw_bench.py`: 읽기 명령 91 허용, `read_encoder_modes()`. `speed_bench_node.py`: 열 때 `forward_signs()`로 부호를 정하고 요약에 `forward_signs_m1_m2` 기록. 테스트 1개 추가(218)
- `tools/drive/drive_report.py`(새): `record_dir`의 `control.jsonl`에서 출발 지연(목표가 생긴 뒤 5 mm 구를 때까지), 목표가 일정한 구간의 목표·실측 속도, 목표가 있는데 바퀴가 선 시간, 좌우 이동량과 방향 변화, 모터 전류·보드 출력, 배터리 최저, 멈춘 이유를 낸다. 바퀴 치수·1회전 카운트는 설정 파일에서 읽는다. 이전 형식 기록(전류 없음)도 읽는다

**원인과 근거**
- (55) 배포 확인(Jetson, 모터 출력 0으로 19 s, 기록 `~/limbo_bags/deploy_check_1106_1738`): 시작 로그 `encoder_modes [0, 0]`·`forward_signs_m1_m2 [1, -1]`(지금 보드 설정과 일치), 384틱 주기 중앙 50.0 ms·최대 60.7 ms, 직렬 실패 0, 틱당 왕복 합 1.5 ms(읽기 4 + 쓰기 1, 명령당 중앙 0.26~0.37 ms). 읽기 2개를 늘린 것이 20 Hz 주기에 부담이 아니다. Jetson에서도 테스트 217 통과
- 같은 날 보드 읽기: 속도 제어 값 M1·M2 모두 P 0·I 0·D 0·QPPS 0(튜닝 전), 엔코더 모드 0/0, 명령 timeout 0.5 s, 배터리 10.6 V → 충전 중 10.8 V. 이 펌웨어(4.4.9)의 명령 59 응답은 매뉴얼의 4바이트가 아니라 5바이트다(최소 59, 최대 311, 끝 1바이트 20)

## 2026-11-06 (55) 주행 브리지에 보드 속도 제어 모드(`control_mode: board_speed`) 추가 + 엔코더 전진 부호를 보드 설정에서 읽음. 기본은 기존 방식(`host_duty`) 그대로

**할 일**
- **순서 주의**: 이 코드가 Jetson에 올라가 빌드되기 **전에** 보드의 엔코더 방향을 바꾸지 말 것. 이전 코드는 왼쪽 부호가 −1로 고정이라, 방향만 먼저 바꾸면 왼쪽 바퀴가 뒤로 간다고 읽어 출력을 상한까지 밀고 odom이 제자리에서 돈다
- Jetson: `limbo_hardware` 빌드. 그 뒤 기존 방식 그대로 한 번 띄워 `opened` 로그의 `encoder_modes`·`forward_signs_m1_m2`가 `[0, 0]`·`[1, -1]`로 나오는지 본다(읽기 2개가 늘었다: 시작 때 명령 91, 틱마다 명령 49 전류. 실물 보드에서는 아직 안 돌려 봤다)
- 보드 준비(모션스튜디오, 바퀴를 띄우고): ① General Settings → Encoders → **Encoder 2 Mode**에서 방향 반전(Motor Reverse는 건드리지 않는다. 켜면 노드가 시작을 거부한다) ② PWM Settings에서 M1·M2 슬라이더를 올릴 때 두 엔코더 값이 모두 **증가**하는지 확인 ③ 슬라이더를 100 %로 올려 M1 Speed·M2 Speed를 읽고 Velocity Settings의 QPPS에 모터별로 넣는다 ④ Tune M1, Tune M2 ⑤ Battery에서 Autodetect Max Main Battery를 끄고 Max 16 V·Min 10 V ⑥ File → Save Settings 뒤 보드 전원을 껐다 켠다
- 실물 확인(단계마다 PM 승인): 바퀴 든 채 0.03·0.07·0.13 m/s 전후진 → 바닥 직선 2 m → 키보드(제자리 회전·완만한 곡선) → 11-06과 같은 5.65 m 목표점 2회. 띄우기 `tools/drive/run_teleop.sh control_mode:=board_speed record_dir:=...`. 판정: 목표 0.03 m/s 이상인 바퀴가 서 있지 않을 것, 목표점 2/2 도착, 평소 주행 전류가 모터 정격 안. 통과하면 `drive.yaml` 기본값을 바꾸고 문제 해결 문서에 남긴다
- 벤치 도구(`speed_bench_node`)는 부호가 아직 `(1, -1)` 고정이다. 엔코더 방향을 바꾼 뒤에는 고치기 전까지 쓰지 말 것

**변경**
- `roboclaw_readonly.py`: 읽기 명령 91(엔코더 모드) 허용, `read_encoder_modes()`, `forward_signs(modes)`. 배선 기본 부호 `(M1 +1, M2 −1)`에 보드의 엔코더 방향 반전 비트(6번)를 반영해 전진 부호를 돌려준다. 모터 방향 반전 비트(5번)가 켜져 있으면 거부
- `encoder_node.py`·`drive_node.py`: 고정값 `signs=(1, -1)` 대신 연결할 때마다 보드에서 읽어 정한다. 진단에 실제 부호 표시
- `roboclaw_drive.py`: `speed_packet`·`write_speed`(명령 40: 가속도 + 양쪽 부호 있는 속도, 카운트/초), `read_velocity_settings()`(명령 55·56: P·I·D·QPPS), `read_encoder_modes()`, `sample()`에 모터 전류(A). 속도 명령은 보드의 QPPS를 읽어 둘 다 양수일 때만 열리고 QPPS를 넘는 값은 직렬로 나가지 않는다
- `drive_node.py` `control_mode`(기본 `host_duty`): `board_speed`면 바퀴별 목표를 카운트/초로 바꿔 보드에 보낸다. 가속도는 `target_slew_rad_s2`를 카운트/초²로 바꾼 값(새 숫자 없음). 멈출 이유(명령 끊김·배터리·보드 비트·사람 기다리기·잠김)가 있으면 속도 0이 아니라 duty 0. 시작 거부: 보드에 속도 제어 값이 없음, 엔코더 전진 부호가 `(1, 1)`이 아님. 잠김: 목표가 있는데 엔코더가 `stall_seconds` 동안 0(속도 창 안에 한 카운트도 안 되는 작은 목표는 제외). 반대로 달림: 목표 반대 방향으로 빨라지는 틱이 3번 이어지면 노드 종료. 기록·진단에 `control_mode`, 보드 PWM 읽은 값, 전류, 보낸 속도
- `drive.yaml` `control_mode: host_duty`, `teleop_drive.launch.py`·`run_teleop.sh`에 `control_mode` 인자
- 테스트 22개 추가(217). 가짜 보드에 엔코더 모드·속도 제어 값·속도 명령을 넣었고 기존 검사 내용은 그대로

**원인과 근거**
- 11-06 목표점 주행(변경 기록 54)의 문제는 odom이 아니라 바퀴가 저속·출발에서 목표를 못 따라가는 것이었다. 지금 방식은 20 Hz로 엔코더를 읽어 계산하고 USB로 duty를 보내며, 속도 추정 창 0.1 s까지 더하면 측정에서 출력까지 0.1 s 넘게 늦다. 이득을 낮게 둘 수밖에 없어(kp 0.02·ki 0.10) 멈춘 바퀴를 밀어 올리지 못한다
- 출발 지연은 구조에서 나온다: 바퀴는 출력 20 % 근처부터 구르는데(11-06 오른쪽 21 %에서 0 m/s) `output_slew_per_s` 0.15는 출력을 초당 15 %만 올린다 → 1.3 s는 제자리. 기록에서도 출발 2 s 동안 명령 0.13 m에 실제 0.03·0.006 m였다
- RoboClaw는 엔코더를 직접 물고 속도를 맞추는 제어기를 갖고 있다(명령 35~40, 매뉴얼 rev 6.0). 보드의 속도 제어 값은 지금까지 전부 0이었다(10-30~11-03 점검 기록의 "PID/QPPS 0"). 팀원 기록에도 "내부 PID 전환은 기계 정렬 전 보류, 미실행"
- 왼쪽 엔코더는 전진에서 숫자가 내려간다(좌우 모터가 마주 보게 달림). 보드 속도 제어는 "양수 명령 = 카운트 증가"를 전제로 해서, 그대로 켜면 왼쪽이 최대 출력까지 폭주한다. 매뉴얼 rev 6.0의 엔코더 모드 6번 비트(엔코더 방향)로 선을 바꾸지 않고 맞출 수 있다. 그래서 부호를 코드 고정값에서 보드 읽기로 옮겼다
- PM 결정(11-06): `board_speed`에서는 출력(PWM) 상한을 걸지 않는다(상한에 붙어 제어가 풀리는 것이 문제의 절반: 11-03 직진 표본의 93 %가 25 % 상한 포화). 기본값은 실물 시험 통과 전까지 `host_duty`

## 2026-11-06 (54) 팀원의 실물 작업(11-04~06, Jetson 보드에만 있던 커밋 2485d9c)을 그대로 올림: 실물 Nav2·AMCL·지도, 바퀴 치수 재측정, 목표점 주행 시험 기록

**할 일**
- 이 항목은 보드에 있던 커밋을 **내용 변경 없이** 원격에 올린 것이다. 노트북에서는 `limbo_hardware` 테스트 195개 통과만 확인했고, 나머지 패키지(실물 런치·Nav2 설정·STVL)는 노트북에서 빌드·실행하지 않았다
- 보드 작업 트리에는 커밋되지 않은 변경(`tools/motors/README_*.md` 9개 삭제, `tools/oak/README_ROS_*.md` 수정, `tools/motors/README.md`·`tools/navigation/` 새 파일)이 남아 있다. 이번에 올리지 않았다
- 실물 스택을 쓰려면 STVL 오버레이가 필요하다: `tools/stvl/build_stvl_compat.sh`(작업공간 `~/limbo_stvl_compat`, spatio_temporal_voxel_layer 2.5.5에 `limbo_stvl_jazzy.patch`)

**변경 (커밋에 들어 있는 것)**
- 실물 런치: `start_real.launch.py`(센서·odom·TF, 모터 출력 없음), `start_real_frames.launch.py`(base 별칭·카메라 장착 TF 한 곳), `start_rgbd_points.launch.py` + `scripts/near_depth_filter.py`(가까운 깊이의 작은 조각 제거 뒤 5 cm 복셀), `start_nav2_real.launch.py`(실물 Nav2, 속도 출력은 기본으로 분리). 스크립트 `tools/drive/run_real.sh`·`run_nav2_real.sh`·`build_real_configs.py`(시뮬 설정에서 실물용 설정을 만들어 냄)
- 설정: `limbo_navigation/config/nav2_real.yaml`·`amcl_real.yaml`·`slam_real.yaml`, 실물용 BT xml 2개, 지도 `maps/real_open_space_20261105`, `limbo_perception/config/person_wait_real.yaml`
- 바퀴 치수(11-05 재측정, 손으로 3바퀴 연속): 1회전 카운트 왼쪽 3688 → 3674·오른쪽 3607 → 3687, 바퀴 중심 간격 0.54 → 0.53 m(바퀴를 양쪽 5 mm씩 안으로 옮김)
- 센서 장착: 라이다 yaw +90°(`MID360s_mount.json`, 정면 사람 점으로 확인), 카메라 앞 0.22 m·높이 0.68 m(`real_robot_mount.yaml`, 실측)
- 주행 브리지: 출력 상한·천장 30 %(9830, 11-04), 오른쪽 전진 피드포워드 곡선(`use_right_forward_curve`, 기본 끔), 직진 출발 때 왼쪽 출력 상승 제한(`balance_straight_start`, 기본 끔). 테스트 추가(195)
- 기록: `tools/motors/tracking_trials_20261106.txt`(오른쪽 바퀴 PWM 시험 10회 + 목표점 주행 2회의 콘솔 출력), `tools/motors/drive_telemetry_20261103.tar.gz`

**원인과 근거**
- 보드는 https 원격에 쓸 자격이 없어 11-06 15:11 커밋이 보드에만 있었다. 번들로 받아 노트북에서 올렸다(변경 기록 50과 같은 방법)
- 11-06 목표점 주행 2회(5.65 m 직선, MPPI 0.13 m/s)는 4.4 m·4.2 m에서 시험 도구가 "좌우 바퀴 이동량 불균형"으로 취소했다. 같은 기록에서 odom 방향 변화는 AMCL과 0.4°·3.8° 차이, 거리는 +3.7 %·+3.6 %였다. 출발 2 s 동안 명령 0.13 m에 실제 0.03·0.006 m, 저속 목표에서 한쪽 바퀴가 섰다(오른쪽 출력 21 %에서 0 m/s). 대응은 다음 항목에서

## 2026-11-03 (53) 실물 사람 앞 기다리기 시험 준비: 브리지에 `/person_wait` 정지 게이트 + 임시 카메라 장착 TF + person_wait 실물 런치

**할 일**
- Jetson 빌드 `limbo_hardware limbo_bringup`. 시험 순서: 카메라·검출기 → `run_teleop.sh`(새로 띄워야 게이트가 듦) → 라이다+SLAM → `tools/drive/run_person_wait.sh`. 로그가 `NOT_READY → DRIVING`이 되면 사람이 앞에 서 있는 쪽으로 키보드 전진. 설 때 범퍼~사람 발 거리를 줄자로 잰다
- `limbo_bringup/config/real_robot_mount.yaml`의 카메라 x 0.20 m·pitch 0은 **임시값**. 줄자 결과와 person_wait가 본 거리 차이만큼 x를 고친다(실물 URDF가 생기면 그쪽으로 옮김)

**변경**
- `drive_node.py`: `/person_wait`(limbo_interfaces/PersonWait) 구독, `wait`가 참인 동안 출력 0(reason `person_wait`). 시뮬 BT의 IsWaitingForPerson과 같은 필드. 파라미터 `wait_topic`(비우면 끔). 테스트 1개 추가(188)
- `start_person_wait_real.launch.py`(새): `base_footprint→oak_device_frame` 고정 TF(mount yaml) + person_wait(실물 override: base_frame base_footprint, bumper_frame 없음→bumper_x, odom `/odom`). ToF 없음·EKF 없음이 시뮬과 다른 점
- `tools/drive/run_person_wait.sh`(새)

**원인과 근거**
- PM: "전진하다 사람 앞 몇 cm 남기고 서는지"를 Nav2 전에 보고 싶음. person_wait는 사람 위치를 odom 좌표로 받아 범퍼 앞 1.5 m 구역·진로 접근으로 판단하므로 카메라 TF와 map 프레임(SLAM)만 있으면 키보드 주행에서도 동작한다

## 2026-11-03 (52) 주행 브리지 손질: 출력 천장 50 %·기본 25 %·지도 작성 35 %, 직렬 오류 연속 3회까지 허용, 지도 런치에 slam_toolbox lifecycle manager. 첫 실물 키보드 주행·풀 세트 부하 측정 결과

**할 일**
- Jetson에서 `limbo_hardware limbo_bringup` 다시 빌드. 키보드 주행은 `run_teleop.sh`(기본 25 %), 지도 작성은 `run_mapping.sh`(35 %). 더 올릴 땐 `max_duty_raw:=<raw>`(천장 16383)
- Motion Studio에서 RoboClaw 최대 전압 자동 감지 끄고 16 V 고정(TROUBLESHOOTING 실물 절). 배터리(Volten 12 V 25 Ah 납축) 15 h 충전 뒤 12.0 V, 주행 후 11.3 V → 멀티미터로 단자 전압 확인, 12.2 V 이하면 교체 검토

**변경**
- `roboclaw_drive.py`: `DUTY_CEILING` 9830 → 16383(50 %, PM 결정). 잠겨도 약 12 A로 보드 15 A 안. `recover()`(실패한 교환 뒤 입력 버퍼 비움)
- `drive_node.py`: 직렬 오류를 연속 3틱(0.15 s, 보드 timeout 0.5 s 안)까지 넘기고 그 틱은 0 출력 시도. 11-03 19분 주행이 USB 쓰기 timeout 한 번으로 끝난 것. 진단에 `transient_serial_errors`
- `config/drive.yaml`: 기본 상한 8191(25 %). 15 %는 축 수리 뒤 왼쪽이 못 굴렀고 25 %로 19분 주행 확인
- `start_mapping.launch.py`: 상한 기본 11468(35 %), slam_toolbox용 `nav2_lifecycle_manager`(autostart, bond_timeout 0). Jazzy slam_toolbox는 lifecycle 노드라 activate 전엔 `/scan`을 구독하지 않았다
- `odometry_node.py`: 시작 로그에 TF on/off 표시(옛 문구 "no TF"가 오해를 불렀음)
- 테스트: 일시 오류 2회 허용·3회 종료·시작 실패 즉시 종료 추가(전체 187)
- TROUBLESHOOTING "실물" 절 신설: GPU 부트스트랩 실패(재부팅), slam_toolbox lifecycle, RoboClaw 자동 최대 전압, 전원 재투입 뒤 timeout 0

**원인과 근거 (11-03 실물 기록)**
- 수리 후 1회차(15 %): 왼쪽 1.4 cm/오른쪽 27.4 cm, 왼쪽 상한에서 8 s 0카운트 → 들면 돌아 체결 저항으로 확정, 나사 조정
- 키보드 주행 19분(25 %, `~/limbo_bags/drive_1103_1537`): 전진 33 m, 목표 0.25 m/s에 실제 0.15 m/s(양쪽 상한 포화 90 %), 좌/우 거리비 0.96. duty≈속도 비율이라 상한을 올려야 속도가 나고 PI 여유가 생겨 쏠림도 잡힌다
- 풀 세트 부하 2분(카메라+YOLO+라이다+SLAM+브리지+bag, `~/limbo_bags/load_1103_1709`): CPU 48 %(최대 66), GPU 8 %, RAM 3.2/7.5 GB, 55 °C, /scan 10 Hz·/odom 20 Hz·YOLO 10.4 Hz 유지, SLAM 드롭 2건. 기준(카메라+YOLO만) CPU 21 %. CPU 1위 YOLO 81 %, Livox 19 %

## 2026-11-03 (51) 실물 주행 명령 브리지 `/cmd_vel`→RoboClaw(`roboclaw_drive`) + 바퀴 odom TF + 키보드 주행·지도 작성 런치. 브랜치 `jetson`

**할 일**
- Jetson에서 빌드: `limbo_hardware limbo_bringup`. 키보드 주행은 터미널 둘: `tools/drive/run_teleop.sh`(브리지+odom) / `tools/drive/teleop_keyboard.sh`(키). 지도 작성은 `run_teleop.sh` 대신 `tools/drive/run_mapping.sh`(라이다·slam_toolbox·bag 포함), 저장은 `tools/drive/save_map.sh <이름>`
- 첫 시험은 바퀴를 띄우고: 전진·후진·제자리 회전·키 떼면 0.5 s 안에 정지. 그 다음 바닥 저속
- 출력 상한은 `drive.yaml` 15 %(4915) 그대로. 11-03 축 수리 뒤 왼쪽이 15 %로 안 굴러 25 %(8191)로 올릴지는 PM 결정 → `run_teleop.sh max_duty_raw:=8191`

**변경**
- `limbo_hardware/roboclaw_drive.py`(새): 연속 주행용 직렬 계층. 쓰기는 duty(34)와 명령 timeout(14, 런타임) 둘뿐. 출력 천장 30 %(`DUTY_CEILING` 9830, 모터 잠겨도 약 7 A로 보드 15 A 안). 펌웨어 4.x 상태 비트 표(`STOP_STATUS_BITS`: E-stop·드라이버 고장·과전압/저전압 오류·경고)
- `limbo_hardware/drive_node.py`(새, 실행파일 `roboclaw_drive`): `/cmd_vel` 구독 → 좌우 바퀴 목표(기존 `calculate_drive_targets`) → 바퀴별 PI(기존 `WheelSpeedPI`)+좌우 FF → duty 20 Hz. 엔코더 카운트·관절 상태는 벤치와 같은 토픽. 출력을 0으로 두는 신호: 명령 끊김(보드 timeout과 같은 시간, 보드에서 읽음), 배터리 10.0 V 아래(10.3에서 복귀), 보드 정지 비트, 잠김(상한 출력인데 1 s 동안 엔코더 0 → 양쪽 목표 0이 올 때 풀림). 시작 때 보드 timeout이 0이면 0.5 s로 켠다(전원 재투입마다 0으로 돌아오던 것). 방향 전환은 PI를 0으로 거쳐서. 선속도 0.25 m/s·각속도 0.8 rad/s 상한(둘 다 같은 비율로 줄여 회전 반경 유지)
- `limbo_hardware/config/drive.yaml`(새): 위 값과 근거. PI 이득은 11-03 마지막으로 움직인 설정(kp 0.02, ki 0.10, FF 0.2375/0.2625)
- `limbo_hardware/odometry_node.py`: `publish_tf` 파라미터(기본 false). true면 `odom→base_footprint` TF 발행(SLAM·AMCL 요구). EKF를 붙이면 끈다
- `limbo_hardware/speed_pi.py`: `max_duty_raw` 검사 상한 4915 → 물리 최대 32767 (벤치 15 %는 벤치 노드가, 주행 30 % 천장은 `roboclaw_drive`가 각자 검사)
- `limbo_hardware/launch/teleop_drive.launch.py`(새), `limbo_bringup/launch/start_mapping.launch.py`(새: teleop_drive + `start_mid360 profile:=mounted` + slam_toolbox(`limbo_navigation/config/slam.yaml`, mapping, 실물 시계) + bag 녹화 `~/limbo_bags/mapping_<label>`)
- `tools/drive/`(새): `run_teleop.sh`, `teleop_keyboard.sh`(repeat_rate 10·key_timeout 0.6: 기본 "키 누를 때 한 번 발행"은 0.5 s 끊김 정지에 걸림), `run_mapping.sh`, `save_map.sh`. 도메인 97·탐색 SUBNET(노트북 rviz가 Wi-Fi로 보게)
- 테스트: `test_roboclaw_drive.py`(패킷·상한·상태 비트·timeout·CRC), `test_drive_node.py`(끊김·제한·전환·잠김·저전압·정지 비트·오류 종료·gap), odom TF 1개. 전체 186 통과(노트북)
- `limbo_bringup/package.xml`: `limbo_hardware`, `slam_toolbox` 의존. `limbo_hardware/package.xml`: `tf2_ros`, `teleop_twist_keyboard`

**원인과 근거**
- 지금까지 실물 모터는 벤치 노드(고정 목표 한 개, 최대 10 s)로만 움직였고 `/cmd_vel` 경로가 없어 키보드 주행도 Nav2 주행도 불가능했다. PM 결정 순서: 브리지로 키보드 주행 → 지도 작성 → 목표점 주행 → 자율 주행
- 11-03 수리 후 1회차(0.03 m/s 10 s): 오른쪽 27.4 cm, 왼쪽 1.4 cm. 왼쪽은 15 % 상한에서 8 s 동안 카운트 0 → 잠김 가드의 근거. 11-03 아침 충전 후 무동작은 보드 과전압 경고(자동 상한 = 켤 때 전압+2 V)가 모터를 제동한 것과 맞아 정지 비트 가드의 근거

## 2026-11-03 (50) Jetson 실물 작업 스냅샷(10-27~11-03, 팀원이 Codex 에이전트로 진행): OAK 카메라 ROS 입력·호스트 YOLO, RoboClaw 엔코더·바퀴 odom·저속 구동 벤치(`limbo_hardware`), MID-360S 입력·`/scan` 연결. 브랜치 `jetson`에만 올림

**할 일**
- 이 항목은 Jetson `~/limbo` 작업 트리(커밋 d1da95a 기준)를 그대로 커밋한 것. dev·ktj에 합치기 전에 아래 "주의"의 설계 결정이 먼저
- Jetson에서 빌드: `limbo_interfaces limbo_hardware limbo_bringup limbo_perception`. 카메라는 `~/limbo_oak_ros_compat`의 DepthAI SDK 3.6.1·ROS v3 3.2.1 overlay(`tools/oak/ros_input_env.sh`), 라이다는 `~/livox_ws`(SDK2 spdlog 패치본)가 Jetson에 따로 있어야 돈다. 자세한 경위는 팀원 문서 `LIMBO_OAK_CONNECTION_LOG.md`(저장소 밖)

**변경**
- 새 패키지 `limbo_hardware`: RoboClaw USB 읽기 전용 엔코더 노드(`/wheel/encoder_counts`, `/wheel/joint_states`), 바퀴 odom(`/odom`, TF는 안 냄), 모터 출력 없는 목표 속도 미리보기, 저속 속도 벤치(`/limbo/drive_bench/cmd_vel`, Jetson PI → RoboClaw duty, 최대 10 s·출력 상한 15 %). `/cmd_vel`→모터 브리지가 아니고 명령 끊김 watchdog도 없음
- `limbo_interfaces/msg/WheelEncoderCounts.msg`
- `limbo_bringup`: `start_oak_camera.launch.py`(DepthAI v3 드라이버 → `/rgbd_camera/*` remap), `start_mid360.launch.py`(profile preview/mounted, 몸체 상자 필터 → `/mid360/points_filtered` → `/scan`, 고정 TF base_footprint→mid360_link (0, 0, 0.837)), `scripts/lidar_cloud_guard.py`, config 4개(`oak_usb2_rgbd.yaml`, `fastdds_camera.xml`, `MID360s_limbo.json`, `MID360s_mount.json`)
- `limbo_perception`: `person_detector.py`에 yolo.device 전달·최신 프레임만 처리하는 `latest_frame_worker.py`(`processing.latest_only`)·종료 순서 보완, `config/person_detector_oak_ros.yaml`
- `tools/oak`(ROS 입력·YOLO 실행·검증 스크립트, requirements 버전 고정), `tools/encoders`, `tools/motors`
- `.gitignore`에 `.pytest_cache/`

**확인된 것 / 안 된 것**
- 통과: 카메라 USB 2, 640×400, 10 fps. 호스트 YOLO(leg_640) 약 10 Hz, 지연 p95 609→138 ms. 엔코더 M1=오른쪽·M2=왼쪽, 1회전 카운트 임시 R 3607·L 3688, 반지름 0.075 m·중심 간격 0.54 m, odom 전후진 0.5 m·좌우 90° 확인. MID-360S(192.168.1.113 ↔ Jetson 192.168.1.50) 점군 10 Hz·IMU 200 Hz, 정지 장애물 costmap 표시·제거 확인
- 미해결: 저속 속도 추종 기준 미달(끊김·좌우 교대), 11-02~03 15 % 상한에서 무동작했다가 재동작한 원인 미확정(차체 약 25 kg), 축·바퀴 기울어짐(가수리 상태), Nav2 costmap 종료 SIGSEGV(센서 없이도 재현), 카메라 장착 TF·EKF·AMCL·Nav2 통합·센서 동시 부하 미수행

**주의(합치기 전에 정할 것)**
- `start_mid360.launch.py`는 자체 몸체 상자 필터와 자체 TF를 내는데, `start_simulation.launch.py role:=robot`는 robot_self_filter로 같은 `/mid360/points_filtered`를 만들고 URDF가 TF를 낸다. 같이 띄우면 중복 발행이라 한쪽으로 정해야 함
- `person_detector.py` 수정은 lab(밴드 재식별)·dev(camera:=oak 카메라 내 NN)와 세 갈래로 갈림
- `tools/motors`의 README 9개는 하나로 합칠 대상

## 2026-10-27 (49) README에 두 대로 나눠 돌리기·카메라 점군 토픽 추가, `limbo_bringup`에 pcl_ros 의존 선언 (48의 문서·선언 마무리)

**할 일**
- 없음 (`ros-jazzy-pcl-ros`는 README 설치 목록에 원래 있음)

**변경**
- `README.md`: "자주 쓰는 변형"에 PC `role:=sim` / Jetson `role:=robot nav2_composition:=True` 명령과 소켓 버퍼·순서는 split-sim 스킬을 보라는 줄, "주요 토픽"에 `/rgbd_camera/points_raw → /rgbd_camera/points`, "시뮬레이션 참고"의 런치 순서에 `rgbd_voxel`
- `limbo_bringup/package.xml`: `<exec_depend>pcl_ros</exec_depend>` (48에서 런치가 pcl_ros 노드를 띄우게 됐는데 선언이 빠져 있었음)

**원인과 근거**
- 48은 코드·스킬만 올리고 README를 안 고쳐 팀원이 README만 보면 두 대 구성과 새 토픽을 모른다. 의존 선언은 `rosdep`으로 설치하는 환경을 위해 맞춘다

## 2026-10-26 (48) 두 대 분리 시뮬에서 Jetson이 서던 원인(UDP 수신 버퍼 넘침) 해결: PC에서 카메라 점군을 5 cm 복셀로 줄이는 `rgbd_voxel` + 양쪽 소켓 버퍼 — 유선 263 → 49 Mbit/s, Jetson CPU 72 → 59 %, 1 m 목표 주행 성공

**할 일**
- pull 뒤 `build_limbo`(bridge.yaml·런치가 바뀜). 두 대 모두 split-sim 0절의 **UDP 소켓 버퍼**(sysctl + FastDDS 프로필)를 한 번 적용
- PC 런치를 다시 띄우면 Jetson 런치도 다시 띄운다(스킬 2절)

**변경**
- `bridge.yaml`: Gazebo 카메라 점군을 ROS `/rgbd_camera/points_raw`로 받는다(gz 토픽은 그대로)
- `start_simulation.launch.py`: `rgbd_voxel`(pcl_ros `filter_voxel_grid_node`, leaf 5 cm, role sim/all) 추가. `points_raw` → `/rgbd_camera/points`. Nav2 설정·Jetson 쪽은 손대지 않음
- `split-sim/SKILL.md`: 대역 표를 실측값으로(rgbd 2 Mbit/s, 라이다 39, 유선 전체 약 50), 0절에 소켓 버퍼 적용 명령, 2절에 "PC 재시작이면 Jetson도", 3절 기대값, 막히면 5(서 있을 때: 목표 유무 → RcvbufErrors)

**원인과 근거**
- 유선 직결 1 Gbps인데 Jetson collision_monitor가 `Robot to stop due to invalid source`, 점군 4.7 s 묵음. `/proc/net/snmp` Udp RcvbufErrors 초당 45개: 카메라 점군 320×240 전 화소 76,800점(미반환 NaN 포함) 27 MB/s(219 Mbit/s) + 라이다 9 MB/s가 수백 개 UDP 조각으로 몰려 오는데 커널 수신 버퍼 상한이 기본 208 KB. 조각 하나만 잃어도 한 장이 사라짐
- 소켓 버퍼(커널 64 MB, FastDDS 32 MB)만으로 드롭 0, /imu 63 → 191 Hz, 주행 성공. 다만 Jetson CPU 72 %·TF 지연 최대 388 ms가 남아 PM 결정으로 점군 자체를 줄임(1번: PC 쪽 복셀). 코스트맵 해상도가 5 cm라 코스트맵 결과는 같음
- 복셀 뒤: 유선 49 Mbit/s, rgbd 1,482점 0.26 MB/s, Jetson CPU 59 %(주행 중), nav2_container 171 → 139 %, 주행 중 TF odom→base_footprint 지연 중앙 6 ms·최대 116 ms, 1 m 목표 7.0 s 성공(/cmd_vel 20 Hz), 경고 0
- "서 있다"의 나머지 절반은 목표를 아무도 안 보낸 것이었다. 스킬 막히면 5에 적음

**확인**(노트북 role:=sim camera:=oak ↔ Jetson role:=robot nav2_composition:=True, 유선 직결, 2026-10-26)
- 위 숫자. 복도 7.5 m(스폰 → 순찰 경로점 A) 주행: 23.9 s 성공, 평균 0.44 m/s·최대 0.60, /cmd_vel 20 Hz, 경고 0, 주행 중 TF odom→base_footprint 28 Hz·지연 중앙 6 ms·최대 48 ms(버퍼 전 388 ms), UDP 드롭 0, Jetson CPU 평균 73 %(person_detector가 주행 중 99 %로 올라감 — 인식 쪽 별도 주제)
- 노트북 한 대(role:=all) 구성은 아직 안 돌려 봄 — rgbd_voxel이 role all에서도 뜨므로 다음 순찰 시뮬에서 코스트맵이 같은지 한 번 본다

## 2026-10-25 (47) dev 병합에서 빠진 Nav2 컨테이너와 `camera:=oak` 되살림 — dev의 `nav2_composition`·벽 오인식 수정은 유지, Jetson 검증 전

(dev를 itkwon에 합칠 때 충돌을 dev 쪽으로 정리하면서 itkwon의 45·46 내용과 Nav2 컨테이너가 빠졌다. 45·46 항목도 아래에 되살림)

**할 일**
- pull 뒤 `build_limbo` (person_detector.py가 바뀜)
- Jetson 시험은 `.claude/skills/split-sim/SKILL.md`대로. Jetson은 `nav2_composition:=True`, OAK로 잴 때는 두 대 모두 `camera:=oak`(4-2절)

**변경**
- `start_simulation.launch.py`: `nav2_composition:=True`이면 `nav2_container`(component_container_isolated)를 직접 띄우고 params 파일을 컨테이너에도 준다.
  `navigation_launch.py`는 컨테이너에 노드를 싣기만 하고 컨테이너는 띄우지 않으므로, 43의 인자만으로는 `/nav2_container/_container/load_node`를 끝없이 기다려 Nav2가 하나도 안 떴다.
  params 파일을 안 주면 local_costmap 같은 하위 노드가 설정을 못 받아 기본 레이어로 뜨고 죽는다(2026-10-22). `use_composition`은 True/False로 맞춰 넘긴다(`true`도 받음)
- `start_simulation.launch.py`: `camera:=sim|oak` 인자, oak_camera 노드, person_detector에 `person_detector_oak.yaml` 덧씌우기를 46대로 되살림
- `person_detector.py`: `detector.source: oak`(YOLO 없이 /oak/detections에 BoT-SORT, 16UC1 깊이는 m로)를 44의 면 판정(surface_check)·폭 하한 위에 다시 합침.
  두 방식 모두 `_detect`가 (검출, 진단 dict)를 돌려주고 면 판정·폭 하한을 똑같이 거친다
- `split-sim/SKILL.md`: 4-2절(camera:=oak), 역할 표, 끝내기 ps, 보고 형식의 OAK 줄을 되살림. Jetson 명령에 `nav2_composition:=True`, depthai는 `pip install "depthai<3" "numpy==1.26.4"`로(requirements 전체 설치는 Jetson용 torch를 CPU판으로 바꿈)

**확인**(이 노트북, 도메인 45, 카메라 없음)
- 단위 테스트 76개(test_logic·test_oak·test_tof·test_person_wait), flake8·pep257 통과
- role:=sim camera:=sim + role:=robot camera:=sim nav2_composition:=True: 컨테이너 안에서 Nav2 `Managed nodes are active`, local_costmap에 stvl·human_layer, bt_navigator active, 컨테이너 밖 Nav2 프로세스 0, person_detector `source yolo`
- 같은 구성에서 dev 판(컨테이너 없음)은 30초 동안 Nav2 노드를 하나도 못 실음(`Abandoning wait for the '/nav2_container/_container/load_node' service`)
- camera:=oak 두 대: PC에 `parameter_bridge_camera` 없음, person_detector `source oak`, oak_camera는 장치 없음으로 1→2초 다시 연결, /rgbd_camera/image 발행자 oak_camera 1, Nav2 active
- 가짜 OAK 토픽(640x352 bgr8, 16UC1 2 m, 사람 박스 1개) 8초: /person_detector/boxes 34건 모두 kept 1개, surface 판정 통과(무늬 있음), 오류 0

**아직 안 본 것**
- Jetson 두 대 구성. 10-24 Jetson+무선에서는 컨테이너 Nav2가 bt_navigator 활성화에서 멈췄다(gdb: bt_navigator가 Fast DDS `MessageReceiver::associateEndpoint`, 코스트맵이 `SendBuffersManager::get_buffer`에서 대기). 송신 버퍼 dynamic XML(코드 밖)로 시험 중

## 2026-10-23 (46) person_detector가 실물 OAK-D Lite 영상과 카메라 안 모델 결과를 쓰는 `camera:=oak` — 실기·Jetson 검증 전

**할 일**
- `sudo apt install ros-jazzy-vision-msgs` (검출 결과 메시지). 대부분 이미 깔려 있다
- YOLO venv에 depthai: `pip install -r requirements.txt` (`depthai<3`이 추가됨). 그 뒤 `build_limbo`
- OAK를 맡은 사람: 카메라를 꽂고 `ros2 launch limbo_bringup start_simulation.launch.py camera:=oak`. 로그에 `oak_camera: OAK-D-LITE 연결`, 10초마다 `발행 … Hz`가 찍히고 RViz `/person_detector/annotated_image`에 카메라 앞 사람 박스·거리가 보이면 정상. 거리를 줄자와 대 보고 결과를 알려 주면 다음 기록에 적는다
- Jetson에 꽂아 두 대로 잴 때는 split-sim 스킬 4-2 (두 대 모두 `camera:=oak`)

**변경**
- 런치 인자 `camera:=sim|oak`(기본 sim). `role`(어느 컴퓨터)과 따로 고른다. oak면 Gazebo 카메라 영상 브리지를 끄고 robot 쪽에 `oak_camera`를 띄우며, person_detector에 `person_detector_oak.yaml`을 덧씌운다
- `limbo_perception/oak_camera.py`(새 노드): 장치를 열어 `/rgbd_camera/image`(bgr8 640x352)·`depth_image`(16UC1 mm, 컬러에 정렬, preview와 같은 영역으로 자름)·`camera_info`(장치 보정값)와 `/oak/detections`(vision_msgs/Detection2DArray)를 같은 stamp로 낸다. stamp = 노드 시계 − 장치 지연. 장치를 못 찾거나 링크가 끊기면(X_LINK_ERROR, 케이블 빠짐, 다른 프로세스가 사용 중) 노드는 살아 있고 장치만 다시 연다. 기다림 1→2→4…최대 10초, 영상을 받으면 1초로. 연결돼 있는데 NN 결과가 3초 넘게 안 오면 멈춘 것으로 보고 다시 연다(`reconnect.*`, `stall_timeout`. `reconnect.enabled: false`면 exit code 1)
- `limbo_perception/oak.py`: 파이프라인·decode·프레임 짝짓기(NN 결과↔입력 프레임은 sequence 번호, 깊이는 가장 가까운 장치 시각). `tools/oak/oak_common.py`는 이것을 가져다 쓴다(카메라 구성은 한 곳에만)
- person_detector `detector.source: yolo|oak`. oak면 YOLO를 올리지 않고, 받은 박스를 `yolo.classes`·`yolo.confidence`로 거른 뒤 `model.track()`과 같은 BoT-SORT(`yolo.tracker`)에 넣는다. 깊이 encoding이 16UC1이면 m로 바꾼다. 그 뒤(leg 합치기·깊이·칼만·의도·예측)는 그대로
- `person_detector_oak.yaml`: source oak, `edge_min_width_px` 40→80(640 폭이라 같은 12 %). `oak_camera.yaml`: blob, `usb_speed: high`, NN 문턱
- blob을 `tools/oak/models/`에서 `limbo_perception/models/`로 옮겨 설치본에 넣음
- Gazebo 브리지 설정을 `bridge.yaml`(나머지)과 `bridge_camera.yaml`(컬러·깊이·CameraInfo)로 나눔. /rgbd_camera/points는 Nav2가 시뮬 월드를 보도록 camera:=oak여도 Gazebo 것을 씀

**배경**
- 실물에서 추론은 카메라 칩에서 하고 Jetson은 YOLO를 돌리지 않는다(변경 기록 45). 부하 시험도 그 구성으로 재야 해서 카메라 출처를 role과 따로 바꿀 수 있게 했다
- 카메라는 시뮬 로봇과 같이 안 움직인다. camera:=oak는 로봇을 세워 두고 인식·부하를 잴 때만 쓴다. 시뮬에서는 stamp를 TF에 맞추려고 oak_camera가 /clock을 받는다(실물에는 없는 부하)

**확인**(이 노트북, 카메라 없음)
- 단위 테스트 69개 통과(새 `test_oak.py`: decode·NMS·깊이 자르기·짝짓기·mm→m·클래스/문턱 거르기), flake8 통과
- 가짜 oak_camera 토픽(2 m 앞 사람 박스, 16UC1)으로 person_detector source oak: BoT-SORT ID 1 → base_link x 2.1 m → 예측 발행
- `camera:=oak gui:=false` 런치: 카메라 브리지 없음, /rgbd_camera/image 발행자 0, /rgbd_camera/points 1, person_detector `source oak`. 기본 런치는 `parameter_bridge_camera`가 뜨고 YOLO로 추적(이전과 같음)
- 다시 연결: 가짜 depthai로 못 찾음 2번 → 연결 → X_LINK_ERROR → 다시 연결 → 결과 멈춤 3초 → 다시 연결 → 정상 15 Hz 순서를 확인. 실물로는 다른 프로세스가 장치를 잡고 있는 동안 `X_LINK_DEVICE_ALREADY_IN_USE`로 1·2·4초 기다리다 풀리자 연결됨
- 실물 oak_camera 단독(노트북 USB 2.0, 시뮬 없이): 14.8~15.3 Hz, 지연 중앙값 232~233 ms, 깊이 짝 없음 0. 칩 온도 62~63°C(변경 기록 45의 37~46°C보다 높음, 계속 보기)
- 시뮬과 같이 돌린 첫 시험(19:37)에서는 40초쯤 13.4 → 2.7 Hz로 떨어진 뒤 X_LINK_ERROR로 끊겼고, 커널 로그에 USB error -71·-110이 나왔다. 케이블·포트·전원 쪽으로 보고 작업자가 원인을 잡음(무엇을 바꿨는지 여기 적을 것)
- 아직 실기에서 안 본 것: 깊이 4 px 자르기·CameraInfo cy 보정이 맞는지(줄자 대조), 케이블을 실제로 뽑았다 꽂을 때의 다시 연결

## 2026-10-23 (45) OAK-D Lite 점검 도구 + 하반신 모델(leg_640)을 카메라 안에서 돌리는 blob — `tools/oak/`, Jetson 검증 전

(번호 43·44는 ktj에 있음: split-sim 대역폭·컴포지션, 벽 오인식 수정. 이 항목은 그 뒤 번호)

**할 일**(OAK-D Lite를 맡은 사람)
- venv 만들기: `python3 -m venv ~/limbo/venvs/limbo_oak && ~/limbo/venvs/limbo_oak/bin/pip install -r tools/oak/requirements.txt`
- 처음 한 번 udev 규칙(sudo, `tools/oak/check_camera.py` 맨 위 설명). 넣은 뒤 카메라를 뽑았다 다시 꽂는다
- `~/limbo/venvs/limbo_oak/bin/python tools/oak/check_camera.py` → 이름 OAK-D-LITE, rgb·depth 19.5 Hz 안팎이면 정상
- `~/limbo/venvs/limbo_oak/bin/python tools/oak/run_leg_model.py` → 사람이 1.5~3 m 앞에 서면 person·leg 검출이 찍힘. 끝나면 `oak_last.png`에 박스 그림
- **USB 케이블이 2.0이면 기본값(`--usb high`) 그대로. 3.0 케이블이면 `--usb super`.** 2.0 케이블에 super를 주면 장치가 8초 뒤 워치독 크래시로 꺼진다(아래 배경)
- Jetson에서 돌린 결과(세 줄의 Hz·지연·온도)를 보고하면 다음 기록에 적는다. 문서에 적힌 구성(16:9·3 shave·USB 속도)은 바꾸지 않는다

**변경**
- `tools/oak/oak_common.py`: 실물 배치와 같은 파이프라인(컬러 640x352 16:9, 깊이 640x360 컬러 정렬, NN), 모델 출력 풀기(decode, NMS), 공통 인자
- `tools/oak/check_camera.py`: 연결·USB 속도·센서·프레임률·깊이 확인. `tools/oak/run_leg_model.py`: blob을 카메라에 올려 검출·프레임률·지연 측정
- `tools/oak/export_blob.py`: .pt → ONNX(640x352) → blob 변환 절차. 모델을 다시 학습했을 때만
- `tools/oak/models/leg_640_352_3shave.blob`: leg_640.pt를 변환한 것(FP16, 3 shave, BGR→RGB·/255 정규화 내장). `tools/oak/requirements.txt`: depthai<3 등
- 저장소의 ROS 노드는 아직 안 건드림. person_detector에 OAK 입력 모드를 넣는 설계는 ktj에서 승인 뒤 진행

**배경**
- 실물 카메라는 OAK-D Lite(IMX214 컬러 + OV7251 모노 640x480 ×2, 플래시 없음). IMU는 Mid-360 내장을 쓴다. 플래시가 없어 모델은 호스트(Jetson)가 켤 때마다 올리고, 추론은 카메라 칩(MyriadX)에서 한다. Jetson은 YOLO를 돌리지 않는다
- 16:9(640x352)로 정한 이유: 카메라 높이 0.6 m 수평에서 1.5 m 앞 사람은 바닥~1.17 m까지 보여 하반신(발~골반)이 다 들어온다. 4:3(13 MP 모드)이 더 보는 건 배·가슴과 1.2 m 안 바닥뿐인데, 깊이 유효 비율은 4:3이 띠별 43~73 %로 16:9(52~80 %)보다 비고 지연도 20 ms 길다. 시뮬 카메라(320x240 4:3)는 아직 그대로라 뒤에 맞춘다
- USB 2.0 링크에서 depthai 기본값(super)으로 열면 펌웨어는 부팅되지만 호스트 RPC 스트림이 안 열려 8초 뒤 워치독이 재부팅한다(`Device already closed or disconnected`). `dai.Device(pipeline, dai.UsbSpeed.HIGH)`로 링크를 2.0에 고정하면 붙는다. 노트북 USB 3 포트에 꽂아도 2.0으로 잡힌 것은 케이블이 2.0용이기 때문
- shave: 스테레오를 같이 돌리면 NN에 shave 7개만 남아 6 shave 블롭은 9.8 Hz·지연 600 ms로 막혔다. 3 shave × 2 thread가 14.8 Hz·231 ms, 7 shave × 1 thread 10.4 Hz

**확인**(이 노트북, USB 2.0)
- blob과 PC ONNX 대조: 시뮬 녹화 56장에서 박스 92개 중 90개 일치(IoU 0.5, 같은 클래스), 점수 차 평균 −0.013·최대 0.065
- check_camera: rgb·depth 19.5 Hz, 깊이 지연 79 ms, 유효 0.99, 온도 37°C. run_leg_model: NN 14.5 Hz·233 ms(깊이 포함), 17.2 Hz·200 ms(--no-depth)
- Jetson(arm64)에서는 아직 안 돌려 봄. depthai는 aarch64 휠이 있어 같은 requirements로 깔린다

## 2026-10-22 (44) 벽·검은 면을 사람으로 보는 오인식 수정: 큰 박스 평면·무늬 판정 + person 박스 실제 폭 하한 — 회귀 통과

**할 일**
- pull 뒤 `build_limbo`(limbo_perception 코드·yaml). 모델·문턱은 그대로(leg_640, 0.3)
- 벽 오인식이 또 보이면 `/person_detector/boxes`의 `surface` 항목과 주석 영상의 회색 박스를 확인 (TROUBLESHOOTING 2026-10-22)

**변경**
- `geometry.py`: `SurfaceConfig`·`surface_check`(화면 15 % 이상 박스의 가운데 깊이가 역깊이 평면에 3 cm 안 95 % 이상 + 명암 라플라시안 편차 6 미만 → 면), `physical_width_m`·`too_narrow_for_person`(person 박스 실제 폭 < 0.15 m → 사람 아님, 박스 끝 ±2 px 여유, leg 제외)
- `person_detector.py`: 박스마다 면 판정을 먼저 해 버린 것은 추적에 안 넣음. 진단 토픽 `/person_detector/boxes`를 `_detect`가 아니라 프레임 처리 끝에 발행하고 `surface` 목록 추가. 깊이 계산 뒤 폭 하한. `surface.*`·`min_person_width_m` 파라미터
- `visualization.draw_surface`: 버린 박스를 회색으로
- `person_detector.yaml`: `surface:` 절(min_box_area_ratio 0.15, inner_margin 0.30, plane_tol_m 0.03, min_planar_ratio 0.95, max_texture 6.0, min_valid_pixels 50), `min_person_width_m 0.15`
- `test_logic.py`: 면 판정 7개(평평한 검은 벽, 비스듬한 벽, 가장자리 단차 있는 판, 벽 앞 두 다리, 둥근 몸통+옷 무늬, 벽에 기댄 사람, 작은 박스·깊이 없음), 폭 하한 1개

**원인과 근거**(TROUBLESHOOTING 2026-10-22에 상세)
- 하반신 모델이 크고 어두운 균일한 사각형을 person으로 봄. 보고된 장면을 모델에 넣으면 leg_640 0.34(문턱 넘음)·leg_512 0.25, 뒤집으면 둘 다 넘음 → 공통 약점. 문턱을 0.4로 올리면 가까운 손님 박스의 11~15 %를 잃어 택하지 않음
- 10-19 비교 녹화에는 사람 검출률만 있고 사람 없는 곳의 박스(오탐)는 재지 않았음

**확인**(ktj 이 커밋, 시뮬)
- 같은 녹화 프레임에 오프라인 적용: 노드가 사람으로 봤던 검은 판 박스(신뢰도 0.85) 평면 1.00·무늬 0.0 → 버림. 사람 장면(aischool_2f_scenarios 90 s) person 박스 469개 중 잘못 버린 것 0, 큰 박스 151개 평면 최대 0.84·무늬 최소 3.0
- 회귀 세트(41과 같음): 손님 홀 왕복 4/4 × 3(복구 0, 구간 12 s), 상자 4/4 × 2(상자 최소 0.29·0.32 m, 복구 5·7), 순찰 3/3(180·185·186 s). 상자 1회차는 서 있는 사람 앞에서 기다리기 상태가 안 풀린 것(41에 적힌 ktj 기다리기 상태 기계 문제, 그때 사람은 정상 추적 중) → 재시험 2회 통과
- 패키지 시험 67개 통과(flake8·pep257 포함)

## 2026-10-22 (43) split-sim 수정: 네트워크 실측 반영(포인트클라우드 850 Mbit/s), Nav2 컴포지션 인자 `nav2_composition`, 유선 필수

**할 일**
- pull 뒤 `build_limbo`. 한 대 구성(기본 `nav2_composition:=False`)은 바뀌지 않음
- Jetson 시험은 `.claude/skills/split-sim/SKILL.md` 수정본대로 (유선 1 GbE, Jetson은 `nav2_composition:=True`)

**변경**
- `start_simulation.launch.py`: `nav2_composition` 인자(기본 False) → nav2 `navigation_launch.py`의 `use_composition`으로 전달
- `split-sim/SKILL.md`: 네트워크 표를 실측으로 교체(42의 "약 50 Mbit/s"는 카메라 영상만 센 값이었음), 브랜치 전제, 유선 필수, 2절 명령에 `nav2_composition:=True`, 3절에 대역폭 확인, 에이전트 규칙에 "문서에 적힌 것은 묻지 않는다"

**배경**(팀원 실측, PC에서 role:=sim만 띄우고 `ros2 topic bw`, aischool_2f)
- /rgbd_camera/points 213 Mbit/s, /mid360/points_filtered 50, 카메라 컬러+깊이 65, 나머지 합계 1 미만. Nav2를 기본대로 프로세스 3개로 띄우면 코스트맵·collision_monitor가 포인트클라우드를 3벌 받아 약 850 Mbit/s → 컴포지션으로 1벌(약 330)로 줄이고 유선으로. 실물에서는 센서와 Nav2가 같은 본체라 생기지 않는 부담

## 2026-10-22 (42) 시뮬을 두 대로 나눠 돌리는 `role` 런치 인자 + 안내 스킬 `split-sim` — Jetson 부하 시험용, Jetson 검증 전

**할 일**
- pull 뒤 `build_limbo`(런치 파일은 심링크 설치라 빌드 없이도 되지만, 다른 브랜치를 쓰던 컴퓨터는 전체 빌드가 필요)
- Jetson 부하 시험을 맡은 사람은 `.claude/skills/split-sim/SKILL.md`를 처음부터 따라 한다. Claude Code를 쓰면 `/split-sim`으로 같은 안내가 뜬다
- 기본값 `role:=all`은 지금까지와 같아 다른 사람의 사용법은 바뀌지 않음

**변경**
- `start_simulation.launch.py`: `role` 인자 추가. `sim`은 Gazebo·robot_state_publisher·브리지·self_filter·pointcloud_to_laserscan·rviz만, `robot`은 EKF·wheel_slip_monitor·AMCL·Nav2·person_detector·tof_node·person_wait(·nav_recorder)만. 나누는 기준은 "실물에서 Jetson이 돌릴 것"
- `.claude/skills/split-sim/`: 안내(SKILL.md), 붙었는지 확인 `scripts/check_split.sh`, 양쪽 부하 측정 `scripts/load_watch.sh`, 멀티캐스트가 막힌 공유기용 `assets/fastdds_peers.xml`. 에이전트 규칙: 자잘한 결정은 작업자, 중대한 결정은 작업자를 거쳐 PM

**배경**
- Jetson Orin Nano 한 대에 시뮬 전체를 올리면 real-time factor 0.56, /scan 1~2 Hz, load average 20, 메모리 부족, AMCL TF 시각 불일치(2026-10-22 팀원 보고). 원인은 Gazebo 센서 렌더링(라이다 43,200 광선 10 Hz)이 6코어·8 GB를 다 쓰는 것. Jetson은 실물에서 로봇 스택만 돌리므로 Gazebo는 PC에 두고 재는 것이 맞다

**확인**(이 노트북 한 대에서 role:=sim과 role:=robot을 따로 띄움, aischool_2f_scenarios)
- 역할별로 뜬 프로세스가 위 표와 같음. robot 쪽 /scan 7.3~7.8 Hz 수신, bt_navigator active, map→base_footprint TF 나옴, AMCL TF 경고 0건(90 s), 정리 후 남은 프로세스 없음
- Jetson + PC 두 대 구성은 아직 안 돌려 봄. 결과는 스킬의 "보고 형식"대로 받아 다음 기록에 적는다

## 2026-10-21 (41) 기본 하반신 모델을 leg_640(입력 640)으로 — 회귀 세트 통과(손님 4/4×3, 상자 4/4, 순찰 3/3)

**할 일**
- pull만 하면 됨(yaml은 심링크 설치라 빌드 불필요. (40)의 `build_limbo`를 아직 안 했으면 그것은 필요). 사람 인식 노드 시작 로그가 "모델 … leg_640.pt … 입력 크기 640"인지 확인
- 이전 모델로 돌리려면 `person_detector.yaml`에서 `model: models/leg_512.pt`, `imgsz: 512`

**변경**
- `person_detector.yaml`: `yolo.model` leg_512 → **leg_640**, `yolo.imgsz` 512 → **640**. 클래스·합치기·깊이 보정은 그대로(두 모델 모두 0 person·1 leg)

**확인**(이 커밋의 ktj 빌드를 별도 폴더에 처음부터 만들어 돌림, 시뮬레이션)
- 회귀 세트: 손님(approach_stop) 4/4 × 3회(50~52 s, 복구 0), 낮은 상자+서 있는 사람 4/4(29~39 s, 상자 최소 0.25~0.29 m, 복구 3), 순찰 3/3(200·234·210 s, Goal failed 0). 충돌 0. 10-20 (39) 회귀와 같은 수준
- 두 사람 나란히(people): leg_512 3/5·5/5, leg_640 2/5·3/5·0/5. 폭 1.8 m 복도를 두 사람이 나란히 막는 장면이라 원래 못 지나가며(틈 0.25~0.35 m), 성공은 사람을 뚫고 간 것(사람 최소 0.01~0.11 m, 접촉 2~4). 두 모델 같은 양상. 0/5 회차는 출발 뒤 서 있는 사람(정답 1.54 m) 옆 (-6.4, 4.3)에서 "다가옴" 대기에 들어가 406 s 동안 못 나온 것 — 서 있는 사람을 다가옴으로 오판한 뒤 출구가 없는 **기다리기 상태 기계 문제**(KNOWN_ISSUES 서로 양보 교착과 같은 계열)로 모델과 무관. lab에는 이미 고친 것(서 있는 사람은 실제로 막혔을 때만 기다림, 막힘 타이머 재시작)이 있어 다음 ktj 반영 후보
- 손님 회차 3번 모두 사람 최소 1.4~1.6 m로 실제 마주침은 없었음(이 월드의 손님 actor는 25.9 s 시간표로 출발점 동쪽 1.9 m까지만 옴). 손님 앞 정지·출발은 lab 비교(zz_social 손님 4/4 × 2, 사람 최소 0.64~0.67 m, 접촉 0, 검출 코드 ktj와 동일)로 확인된 것을 근거로 함
- 자원(RTX 4060 Laptop, 노드): CPU 평균 100~109 %(leg_512 105~107 %), RSS 1.65 GB 같음, GPU 메모리 276~296 MB(280 MB), 처리 속도 14.5 Hz 같음
- 두 모델 비교 근거(손님·복도·충장로 군중 각 2회): (40) 확인 항목

## 2026-10-21 (40) 하반신 모델 leg_640(입력 640) 추가 — 시뮬 비교에서 leg_512와 같거나 우세, 기본값은 아직 leg_512

**할 일**
- `build_limbo`(limbo_perception `setup.py` 설치 목록에 `models/leg_640.pt` 추가). 기본 모델은 그대로 leg_512·512라 동작은 바뀌지 않음

**변경**
- `limbo_perception/models/leg_640.pt` 추가(팀원 sgh 재학습: yolo11n에서 coco_lower 100 epoch, 입력 640, classes 0 person·1 leg). `person_detector.yaml` 주석에 바꿔 쓰는 법(`model: models/leg_640.pt`, `imgsz: 640`). dev의 "leg_640 (#20)" 커밋은 빈 커밋이라 모델 파일이 들어오지 않았음 → 여기서 넣음

**확인**(시뮬레이션, 손님·복도·충장로 군중 50명 각 2회, 자원 포함)
- 손님 0~1.5 / 1.5~3 m 검출: leg_512 52·42 / 52·75 %, leg_640 67·89 / 58·77 %. 복도 3~5 m: 97·95 % vs 88·92 %. 군중은 0~3 m 회차 편차 안, 3~5 m 75·75 % vs 72·65 %. 겹침 0·오검출 0·주행 성공·충돌 0은 같음
- 자원(RTX 4060 Laptop): 노드 CPU 평균 +5~10 %p, GPU 메모리 +16 MB, RSS 같음, 처리 속도 14.5 Hz 같음. 영상이 320×240이라 입력 크기 차이가 거의 안 드러나며 Jetson에서 재측정 필요
- 화면 가장자리(30~36°)에 반쯤 잘린 사람: leg_512는 YOLO가 50~75 %만 잡고 leg_640은 90 %+ 잡지만, 최종 예측은 둘 다 40~60 %. 빠지는 몫 대부분이 "화면 끝에 닿은 40 px 미만 박스 제외" 필터라 모델이 아니라 필터를 손봐야 함(설계 뒤)
- 기본값 전환은 실물 카메라 bag 비교 뒤 결정. 바꾸면 기다리기 회귀 세트 1회

## 2026-10-20 (39) 사람 앞에서 기다리기를 상태 기계 하나로 재설계(2-7), 하반신 검출 모델을 기본으로, 안전 정지 분리

**할 일**
- `build_limbo` 전체 재빌드(새 메시지 `PersonWait`, 새 노드 `person_wait`, BT 플러그인 교체, 모델 파일). pull 뒤 `git log -1`이 이 항목과 맞는지 확인
- 기존 COCO 모델로 돌리려면 `person_detector.yaml` 주석대로(`model: yolo11n.pt`, `classes: [0]`, `imgsz: 640`)

**변경**
- **기다리기 재설계**(PROJECT.md 2-7): 래치 두 개(`/person_blocking`·`/person_approaching`)와 BT 조건 두 개를 상태 기계 `person_wait`(`limbo_perception/person_wait.py`, ROS 없는 순수 모듈 + `person_wait_node.py`)와 토픽 `/person_wait`(`limbo_interfaces/PersonWait`), BT 조건 `IsWaitingForPerson` 하나로. 근거는 사람 트랙뿐: ① 진로 위로 다가오는 사람(최근접점 0.6 m 안, 3 m 안) → 멈춤 ② 구역(범퍼 앞 1.5 m × 로봇 반폭+사람 반경) 안에 서 있는 사람은 로봇이 실제로 막혔을 때(속도 0.05 m/s 미만 2 s)만 → 멈춤. 사람이 구역을 벗어나면 0.5 s 뒤 출발. 서 있는 채 15 s(서비스 시간)가 지나면 비켜서기(예정), 자리 없으면 계속 기다리며 30 s마다 경보(WARN). **타이머로 기다림을 끝내는 전이는 없다**. 코앞에서 카메라가 사람을 놓치면(화면 밖) 직전 3 s 안 트랙 + ToF 막힘으로 이어 기다리고 ToF가 비면 즉시 출발. 전이마다 INFO 한 줄("WAITING ← DRIVING: approaching, tracks 1 …")로 "왜 멈췄나/갔나"가 설명됨
- BT: 계획 중 대기·추종 중 정지·복구 전 조건 세 자리를 `IsWaitingForPerson`으로. `FollowPathOrWait` 반복 상한 60 → 사실상 무한(타이머는 출구가 아님)
- `tof_node`: 점군 처리만(`/tof/obstacle_ahead`·`/tof/nearest`·`/tof/points`). 래치·`/scan`·`/map` 구독 삭제. `tof.yaml`에서 래치 파라미터 삭제
- 안전 정지: `collision_monitor` approach 모델(명령 속도로 1.2 s 앞 footprint를 밀어 보고 충돌 임박 시 정지) 관측원에 ToF 점군 추가. 사람 여부와 무관. 고정 구역 정지는 쓰지 않음(벽 옆 제자리 회전과 겹쳐 갇힘)
- **하반신 모델**(`limbo_perception/models/leg_512.pt`, 팀원 학습, classes 0 person·1 leg, 입력 512)을 기본으로. `person_detector.py`: 클래스·입력 크기 파라미터, 같은 사람의 person·leg 박스 합치기(`geometry.merge_leg_boxes`), 두 다리 따로 잡힌 박스 합치기, leg 박스 깊이 샘플링(가로 여백 5 %·percentile 10), 몸 중심 보정(leg 0.25 m·몸 전체 0.12 m), 화면 가장자리에 잘린 박스는 거리 계산 제외, 거리 급변(1 m) 거르기. 진단 토픽 `/person_detector/boxes`
- `geometry.py`: 지도 벽 걸러내기·사람 몸통 폭 덩어리·최근접점 함수 보존(라이다 다리 검출 전처리용). 단위 시험 `test_person_wait.py`(18개)·`test_logic.py` 갱신, `test_tof.py` 정리. 총 59개 통과
- 문서: PROJECT.md 2-7·결정 이력·6절 피팅 금지, KNOWN_ISSUES(60 s 정지 해결 표시, 서로 양보 교착), TROUBLESHOOTING(래치 교훈)

**확인**(시뮬레이션, 카메라 0.60 m·0°)
- 하반신 모델: 1.5 m 안 검출 0~49 % → 71~95 %, 멈춘 손님 0 → 62~93 %, 한 사람에 박스 2개 0~5 %, ID 바뀜 기존 수준, 위치 오차 중앙값 0.07~0.21 m, 추론 3.7 → 4.0 ms
- 기다리기: 손님 4/4(정지 7 s 뒤 떠나면 출발), 상자+벽 옆 사람 4/4(벽 옆 사람 옆을 멈춤 없이 지나감, 상자 최소 0.25 m), 옆에서 와서 앞에 서는 사람 3/3(막힌 뒤 대기 → ToF 비면 출발). 복구·충돌 0, 60 s 정지 0
- 남은 것: 사람이 옆에 서고 로봇도 막혀 둘 다 기다리는 교착(KNOWN_ISSUES), 출구는 비켜서기(예정)

## 2026-10-19 (38) dashboard README: v1 연결에서도 일시정지는 열린다고 버튼 잠금 설명 고침

**변경**
- 코드 변경 없음. (37)에서 "v1 송신기만 연결하면 버튼은 잠긴다"고 적었으나, 실제로는 순찰 재개만 잠긴다. `ui/src/control.ts`의 `pauseReason`은 순찰 상태를 모를 때도 일시정지를 열어 둔다(멈추는 쪽은 막지 않음, `control.test.ts` "모르면 누를 수 있음"). PR 리뷰(Copilot) 지적
- `dashboard/README.md` 세 곳: 소개, 「버튼 잠금」(순찰 상태를 모르면 일시정지는 열림), 「가상 송신기로 독립 검증」. 가상 송신기에서 일시정지를 누르면 요청은 만들어지지만 송신기가 `commands/next`로 가져가지 않으므로 `command_ttl_s`(5초) 뒤 `expired`(「정지 요청 실패: 로봇에 제때 전달되지 않아 실행 안 함」)로 끝나며, 실제 제어는 검증할 수 없음을 구분해 적음

**확인**
- 문서 내용을 `ui/src/control.ts`·`control.test.ts`·`server/state.py`(명령 `expired` 마감과 알림 문구)와 대조. 실제 화면에서 눌러 보지는 않음

## 2026-10-19 (37) dashboard·relay_prog README를 관제 기능(텔레메트리 v2·정지/재개·지도)에 맞게 갱신

**할 일**
- Bridge를 실행하거나 시험할 때 source 순서는 **Jazzy → `limbo/install/setup.bash` → `relay_prog/install/setup.bash`**. `limbo/`를 빠뜨리면 `ModuleNotFoundError: No module named 'limbo_interfaces'`
- UI 시험·빌드는 Node.js 22 또는 24. Node 18에서는 `pnpm test`가 `crypto is not defined`로 실패

**변경**
- 코드 변경 없음. `dashboard/README.md`는 처음 추가(2026-10-06) 뒤 한 번도 고치지 않아 (24)~(29)·(32)의 관제 기능이 빠져 있었음
- `dashboard/README.md`: 버튼 3개 항상 비활성 → 일시정지·순찰 재개 2개를 실제 제어로. 화면 구성(상태 한 줄 요약·순찰·지도·센서 수신 상세), 설정 `command_ttl_s`·`command_response_timeout_s`·`command_confirm_timeout_s`·`map_yaml`·`waypoints_yaml`, 상태 해석(순찰 카드·지도·버튼 잠금·명령 결과 단계), 명령 API 4개·지도 API 2개·스냅샷 새 필드. Bridge 실행·`validate_bridge.py` 명령에 `source limbo/install/setup.bash` 추가(없으면 Bridge가 안 뜸). 가상 송신기·`validate_bridge.py`는 v1 기준이라 순찰·위치·제어를 검증하지 않음을 적음
- `relay_prog/README.md`: v2·명령 구현과 `limbo_interfaces` 의존을 소개에. "0. 먼저: `limbo/` 빌드", source 순서, 추가 ROS 패키지(`geometry_msgs`·`std_srvs`·`tf2_ros`), `control` 설정 표, Mock 서버로 명령 넣기, 자주 나는 오류 표

**확인**
- 문서 내용을 코드(`dashboard/server`, `dashboard/ui/src`, `bridge.yaml`)와 대조
- 서버 시험 `dashboard/.venv/bin/python -m pytest -q` 58개 통과. UI 단위 시험 `pnpm test`는 Node 24.22.0에서 25개 통과

## 2026-10-19 (36) README: pull 뒤 재빌드·다른 브랜치 빌드 흔적 지우기 안내

**할 일**
- `git pull` 뒤 `build_limbo`. `package '…' not found`가 나면 README "2. 빌드"의 지우기 명령

**변경**
- README "2. 빌드"에 pull 뒤 매번 재빌드해야 하는 이유와, 다른 브랜치 빌드 흔적(없는 패키지) 지우는 명령 추가. "막히면"에 내 코드가 최신인지 확인하는 방법 추가
- 코드 변경 없음. dev에 (33)~(35)가 들어 있는데도 "안 고쳐졌다"는 보고가 있어, 옛 설치본으로 돌았을 가능성이 커서 적음

**확인**
- 이 PC에서 같은 증상 재현: 다른 브랜치에서 빌드한 패키지 흔적이 남아 `package 'limbo_drive' not found`로 launch가 멈췄고, 흔적을 지우고 재빌드하니 정상. 네모 월드 순찰·학원 2층 순찰 2회 완주, 사람·로봇 위치 급변 없음

## 2026-10-16 (35) 라이다로 "앞에 선 사람"을 잡고, 벽을 사람으로 오해해 60 s 서 있던 문제를 고침

**할 일**
- `colcon build --symlink-install --packages-select limbo_perception`
- 단위 시험: `colcon test --packages-select limbo_perception && colcon test-result --verbose` (test_tof.py 25개)

**변경**
- `tof.py`·`tof_node.py`: 라이다 `/scan` 점에서 **정적 지도의 벽**(`/map` 점유 칸에서 해상도 2칸 안)을 걸러 내고, 남은 점을 이웃 간격 0.15 m로 묶어 **사람 몸통 폭(0.15~0.6 m)** 덩어리만 "앞에 선 사람"으로 본다(`person_blob_ahead`). 전에는 띠 안에 점 2개만 있으면 사람으로 봐서 복도 벽 모서리에 60 s까지 섰다. 띠 반폭은 하드코딩 0.55 대신 `robot_half_width`(0.30, 바퀴 바깥면) + `person_radius`(0.25)
- `/person_blocking`(코앞 막힘) 확장: ToF 막힘 + (직전 5 s 다가옴 이력 **또는** 앞 사람 덩어리) → 참. 옆·뒤에서 와서 앞에 선 사람, 느린 사람, 카메라 밖에서 멈춘 사람도 잡는다. 덩어리만 근거이고 카메라가 그 자리(1 m 안) 사람을 못 봤으면 **5 s**(`blob_only_hold_sec`)만 기다리고 풀어 상자 앞 무한 대기를 막는다
- `/person_approaching`(다가옴) 풀기: 정지 뒤 유지 근거가 라이다 덩어리뿐이면 **15 s**(`approach_blob_only_hold_sec`), 카메라·ToF가 다시 보면 60 s. 유지 근거(seen/tof/blob)와 풀린 이유를 INFO 로그 한 줄로 남긴다
- `tof.yaml`: 새 파라미터와 근거 주석. `front_sector_*`는 `blob_*`·`robot_half_width`·`person_radius`로 대체. map TF가 없으면(위치 추정 전) 걸러내기 없이 종전처럼 동작
- `package.xml`: nav_msgs 의존 추가

**확인**
- 옆에서 와서 앞에 서는 사람(새 시나리오) 3회 모두 3/3: 다가옴 래치는 안 켜지고 덩어리로 코앞 막힘을 잡아 회전·후진 없이 기다렸다가 사람이 비키면 출발, 충돌 0, 사람 최소 0.43~0.53 m
- 손님 4/4(사람 앞 정지 27.5 s, 전과 같음), 낮은 상자 4/4(덩어리 래치 안 걸림), 사람 두 명 복도 2회 3/3·3/3(다가옴 최대 유지 4.8·5.5 s, 60 s 정지 없음)
- 복도 2회는 1/3: 시험 사람의 왕복 반환점이 로봇 출발 자리 0.61 m 앞이라 사람이 ToF 0.32 m에 60 s 내내 서 있던 경우. 설계대로 기다린 것이며 시험 시나리오 쪽 문제. "앞에서 계속 서 있는 사람"은 비켜서기(다음 작업)의 몫
- 남은 관찰: 시뮬이 뜨는 동안(TF 준비 전) ToF 0.04 m·로봇 앞면 크기 덩어리로 래치가 몇 번 켜졌다 꺼짐. 주행 영향 없음, KNOWN_ISSUES에 기록

## 2026-10-16 (34) 복구 전에 사람 여부를 먼저 물어 사람 앞에서는 회전·후진하지 않음

**할 일**
- `colcon build --symlink-install --packages-select limbo_navigation` (BT xml)

**변경**
- `limbo_navigate_to_pose_w_replanning_and_recovery.xml`: 복구 묶음(costmap 지우기 → 회전 1.57 rad → 5 s 대기 → 0.3 m 후진) 앞에 가지 하나 추가. `/person_approaching`(진로 위로 다가오는 사람)이나 `/person_blocking`(사람 때문에 코앞 막힘)이 참이면 복구 대신 1 s 기다리고 본 가지로 돌아가 "사람이면 기다리기"로 다시 들어간다. 복구 도중 사람이 다가오거나 코앞이 막히면 회전·후진을 멈추기 위한 것. 두 조건이 거짓이면 전과 똑같이 복구한다
- 이 가지는 기다리기 래치(`tof_node`)가 알아본 사람에만 듣는다. 래치가 못 알아본 사람(옆에서 와서 앞에 선 사람 등) 앞에서는 여전히 복구가 돈다. 그 부분은 다음 작업(라이다로 "앞에 선 사람" 잡기)에서 다룬다

**확인**
- 사람 두 명이 왕복하는 복도 3회 3/3·3/3·3/3(사람 최소 0.62~0.67 m, 충돌 0), 낮은 상자 4/4(최소 0.14 m, 접촉 0). 사람이 없을 때의 진전 실패 4회(복도 1회차, 사람 2.45 m 밖)는 새 조건이 거짓으로 찍히고 기존 복구(costmap 지우기 → 회전)로 넘어가 78.8 s에 도착
- 복도 1회차 출발 직후 정체는 알려진 문제(옆으로 스치는 코너의 30 cm 상자)의 재발이며 이 변경과 무관(KNOWN_ISSUES에 추가 기록)

## 2026-10-15 (33) 하드웨어 최종 치수(라이다 0.70 m·카메라 0.60 m), default_server_timeout 100, 충장로 맛보기

**할 일**
- `colcon build --symlink-install --packages-select limbo_description limbo_bringup limbo_navigation` (URDF·launch·nav2 설정), 또는 `build_limbo`
- 실물 카메라 마운트를 바닥 0.60 m·수평으로, MID-360을 바닥 0.70 m로 맞춘다 (URDF와 같아야 인식 좌표가 맞음)

**변경**
- **로봇 치수** (`limbo.urdf.xacro`): 몸체 윗면 `body_top` 0.835 → 0.609로 뚜껑 위 MID-360이 바닥 0.70 m(0.609 + 0.09094, 전 0.926 m). 카메라 `camera_z` 기본값 0.70 → 0.60(수평 0° 그대로). 몸체 시각 메시는 높이 0.835 m로 그려져 있어 z 배율 `body_top / 0.835`로 줄임 — 메시가 높은 채면 Gazebo 라이다가 자기 몸체를 봐 출발 자리에서 못 움직임(`docs/TROUBLESHOOTING.md` "몸체를 낮추자…"). 전체 높이 약 0.72 m
- `start_simulation.launch.py`·`gazebo.launch.py`: `camera_z` 기본값 0.60
- `nav2_params.yaml`: `bt_navigator`의 `default_server_timeout` 20 → 100 ms. 시작 직후 부하에서 계획·추종 서버 응답을 놓쳐 목표를 바로 포기하던 것(손님 장면 0/4). 주행 동작은 그대로, 서버 응답 대기만 여유
- **충장로 맛보기**: `limbo_simulation/tools/chungjang/gen_street.py`와 입력 자료 `osm_chungjang.json`(© OpenStreetMap contributors, ODbL 1.0). 충장로 보행자 거리 200 m 구간 월드 `chungjang`·지도 `chungjang_map`을 만든다. 산출물은 커서 저장소에 넣지 않음(`.gitignore`)
- 순찰 노드의 TF 출발(`/amcl_pose` 없이 `map → base_footprint` TF로 판단)은 (32)에 이미 들어 있어 그대로
- README "충장로 맛보기" 절 추가. `docs/PROJECT.md` 센서 표(크기 약 0.72 m, MID-360 0.70 m·사각 0.3 m 높이 3.3 m 안·바닥 5.7 m 안, 카메라 0.60 m)·결정 표(최종 치수, NavFn A* 유지)
- `docs/KNOWN_ISSUES.md`: 기다리기 BT "다가옴 정지"가 60 s 상한까지 안 풀리는 경우 간헐(0/3 → 2/2 → 1/3). 기다리기 BT는 켠 채 둠

**확인** (시뮬레이션)
- xacro 전개 base_footprint 기준 높이: MID-360 0.700, 카메라 0.60, ToF 0.10, 뚜껑 0.609. 출발 자리 scan 1.0 m 안 점 0개(자기 몸체 안 봄)
- 최종 치수에서 복도 3/3(25~89 s, 사람 충돌 0, 사람 최소 0.70 m), 상자 4/4(31~36 s, 장애물 최소 0.18 m, 충돌 0)
- `default_server_timeout` 100에서 손님 4/4(17~28 s, 사람 최소 0.56 m), 순찰 3/3(320·258·211 s)
- 계획기: NavFn A* 1.0~2.4 ms vs 다익스트라 1.8~5.8 ms(10회×4목표, 성공 80/80) → A* 유지

## 2026-10-14 (32) 저녁 채택분 반영: 사람이면 기다리기 BT, ToF costmap, 카메라 0°, MPPI 되돌이 처리, 순찰 반복·TF 출발, 관제 일시정지

**할 일**
- pull 후 `colcon build --packages-select limbo_navigation limbo_perception limbo_description limbo_patrol limbo_evaluation` (BT 조건 플러그인·ToF 노드·URDF·순찰)
- 학원 2층 순찰을 한 번 돌려 A 지점 맴돎이 사라졌는지 확인

**변경**
- **사람이면 기다리기 BT 켬** (`nav2_params.yaml`의 `limbo_navigate_*_w_replanning_and_recovery.xml`): 진로 폭 띠(범퍼 앞 0~1.5 m, 좌우 0.55 m)에 다가오는 사람이면 정지·기다림, 코앞을 막은 사람(ToF 0.5 m)은 카메라 기억 래치로 유지, 떠나거나 1 s 비면 재개(상한 60 s). 경로 계획 실패도 사람 때문이면 기다림. 조건 노드 `IsPersonBlocking`(`limbo_navigation`), 판단 노드 `tof_node`(`limbo_perception`, `/tof/points` → `/tof/obstacle_ahead`·`/person_blocking`·`/person_approaching`)
- **ToF 근접 센서**: URDF `tof_link`(범퍼 앞 0.25 m, 높이 0.10 m, 수평), 시뮬레이션 8×8 63° 4 m(`limbo.gazebo.xacro`, `bridge.yaml`). 점군을 local costmap STVL `tof_mark` 관측원으로도 넣음(0° 카메라가 0.78 m 안에서 놓치는 30 cm 상자, 상자 벤치 12/12·접촉 0)
- **카메라 0.7 m·0°**(전 15°): 기울이면 비스듬히 다가오는 손님의 상체가 잘려 검출 19 % → 3 %. launch 인자 `camera_z`·`camera_pitch_deg`
- **MPPI `enforce_path_inversion: true`**: 순찰 통과 지점에서 경로가 되돌아 꺾일 때 `prune_distance` 2.5가 그 앞 1.2 m 정체를 만들던 문제(A 지점 맴돎) 해결
- 순찰 노드: `loop` 파라미터(끝없이 반복, `aischool_loop_waypoints.yaml`), 이동 실패 시 2번 재시도 뒤 paused로 사람의 재개 대기, `/amcl_pose` 없이 TF만으로 출발. 관제 화면 일시정지·재개(`dashboard`, `docs/CONTROL_SCREEN.md`)
- `nav_recorder`: 순찰(`navigate_through_poses`) 지원, 벽 거리·사람 접근 속도·위치 추정 오차 열
- `start_simulation.launch.py`: `localization:=amcl|slam|mapping` 인자(slam_toolbox 비교용, 기본 amcl), ToF 노드

**확인**
- 비켜 주는 사람 복도 3회 9/9(사람 앞 기다림 4~5 s, 60 s 정지 0), 손님 4/4, 상자 4/4. 사람 10명 네모 순찰 AMCL 3묶음 완주 145.7 s(위치 오차 0.035 m)
- 열린 문제: ToF 시야 밖 코너의 30 cm 상자 정체 13회 중 1회, 복도 목표 코앞 정체 5회 중 1회 (`docs/KNOWN_ISSUES.md`)

## 2026-10-14 (31) 시뮬레이션에서 채택된 설정·코드 반영: 전역 STVL 3초, HumanLayer 치명 비용, prune_distance 2.5, 카메라 0.7 m 15°, nav_recorder 지표

**할 일**
- pull 후 `build_limbo` (HumanLayer C++). 실물 카메라 마운트를 0.70 m·아래 15°로 맞추고 피치를 실측해 URDF와 같게

**변경**
- `nav2_params.yaml`: 전역 costmap STVL `voxel_decay` 15 → 3초(3초·15초 성적 같음, 작은 값), MPPI `prune_distance` 1.7 → 2.5(1.7이면 4 s 예측 × 0.425 m/s가 사실상 속도 상한. 충장로 직선 0.42 → 0.58 m/s, 사람 있는 복도·홀에서 충돌 0·사람 거리 동일에 시간 −22~31 %), `human_layer` 파라미터 9개
- `human_layer.cpp/.hpp` 다시 씀: 사람 현재 위치와 0.5 s 안 예측점은 몸 반경 0.25 m 안을 치명(254)으로. 전에는 현재 위치를 안 칠하고 최고 비용 220이라 MPPI 충돌 판정에 안 걸려 사람을 뚫는 궤적을 골랐음. 상수는 yaml로, 2초마다 찍던 INFO 로그는 DEBUG로
- `limbo.urdf.xacro`·`gazebo.launch.py`·`start_simulation.launch.py`: 카메라 0.50 m 수평 → 0.70 m 아래 15°(짧은 치마 밑단보다 높게 두어 올려다보지 않음, 근거리 바닥 0.78 m부터. 12·15·18° 비교에서 사람 검출·상자 costmap 전과 같음). `camera_z`·`camera_pitch_deg` 인자
- `nav_recorder`: 순찰(`navigate_through_poses`)도 기록(`action` 열), 사람 충돌(0.3 m 미만)·사람 앞/그 외 멈춤·전역 경로 변경·최소 거리 순간의 사람 접근 속도와 로봇 속도 열. 테스트 23개
- `tools/demo_patrol.sh`: Nav2 준비 검사 `grep -q active`가 `inactive`에도 맞던 것을 `^active`로
- `README.md`(따라 하면 무엇이 뜨는지 흐름으로 다시 씀, CSV 열 표), `docs/PROJECT.md`(에이전트용 안내서: 설계 전제·기록 규칙·결정 이력·지금 상태), `docs/KNOWN_ISSUES.md`(맨 위 "지금 주행을 막는 것"), `docs/TROUBLESHOOTING.md`(10-13·14 항목 추가)

**확인**
- ktj에서 `colcon build` 10개 패키지, `limbo_evaluation` pytest 23개 통과, xacro 카메라 joint (0.235, 0.1575, 0.70) pitch 0.262 rad
- 학원 2층 순찰 1회 완주 (`tools/demo_patrol.sh`)

## 2026-10-13 (30) lab에서 실제 로봇 v14 모델·학원 2층 지도·waypoint 선택 가져옴 (실험 기록은 뺌)

**할 일**
- **`build_limbo`** (새 메시·월드·모델·waypoint 파일이 들어옴)
- 이제 시뮬레이션 로봇이 **v14(실제 로봇)가 기본**. 예전 모델로 비교하려면 `robot:=legacy`
- 학원 2층으로 순찰하려면 `-p waypoints:=aischool_waypoints.yaml` (기본은 그대로 `test_waypoints.yaml`)

**변경** (lab 커밋 880bc1e, 4f45201, 0222337, 12301be, 1438bb3, 815bab9, 26f790e에서 파일 단위로 가져옴. lab 전체를 merge하지 않음)
- **로봇 모델 v14**: `limbo_description/` (v14 메시, URDF, 예전 모델은 `urdf/legacy/`). `start_simulation.launch.py`·`gazebo.launch.py`에 `robot:=v14|legacy`, 시뮬레이션 브리지에 뚜껑 각도(`lid_angle`)
- **Nav2**: `nav2_params.yaml` 로봇 외곽을 v14 실제 크기로 (0.9 m 문·1.3 m 책상 통로를 지나가게), `self_filter.yaml` v14 몸체, `self_filter_legacy.yaml` 예전 모델용
- **학원 2층**: 월드·지도를 문 0.9 m 기준으로 다시 만듦 (`aischool_2f`, `aischool_2f_scenarios`), 가구 월드 `aischool_2f_furnished`와 지도·waypoint, 가구 모델 6종(출처 `models/CREDITS.md`), 생성 도구 `tools/aischool_2f/`
- **순찰 노드**: waypoint 파일을 `waypoints` 파라미터로 고름 (일시정지·재개 코드와 손으로 합침)
- **월드 물리 스텝 1 ms → 2 ms** (`human_test_world`, 학원 2층 월드): 실시간 비율 0.6 → 0.95, odom 정확도 차이 없음 (lab 실험)
- **`tools/demo_patrol.sh`**: 시뮬레이션이 준비되면 순찰을 자동 시작하는 시연용 한 줄 실행
- README(월드 표·순찰·로봇 모델), TROUBLESHOOTING(가구 월드 통로 끝 "Failed to make progress")
- **가져오지 않은 것**: `experiments/`, `tools/sim_trials/`, `docs/LAB_BOARD.md`·`docs/lab/`, lab 전용 `CLAUDE.md`, 충장로·레이싱 트랙 월드와 지형·OSM 자료, 움직이는 장애물 스크립트(`gazebo.launch.py`에서도 그 부분을 뺌)

**시험**
- `build_limbo` 성공, 시뮬레이션에서 로봇 모델이 v14인 것 확인 (`robot_description`에 `v14/body.stl`, `lid_link`)
- **v14로 관제 화면 일시정지·재개 다시 확인**: 일시정지 1.39초, 재개 0.86초 만에 "확인됨", 재개 4초 뒤 0.42 m/s
- Bridge·대시보드 설정은 바꾸지 않음 (v14도 프레임 `base_footprint`, `rgbd_camera_optical_link`와 센서 토픽 이름이 같음)

---

## 2026-10-13 (29) 관제 화면 UI/UX 다듬기

**할 일**
- 화면 다시 빌드(5분 넘게 걸림), 서버 다시 실행 (알림 문구·명령 경과 시간이 바뀜)

**변경** (설계: `docs/CONTROL_SCREEN.md` "UI/UX 다듬기")
- **이미 일시정지면 일시정지 버튼을 잠금**: 순찰 노드가 `paused`·`pausing`이라고 알려 준 경우만. "이미 일시정지 상태입니다". 순찰 상태를 모르면 누를 수 있게 둠 (멈추는 쪽은 막지 않음). 전에는 눌리고 "요청 실패: already paused"가 떴음
- **결과 상자에 경과 시간**("요청 시각 15:34:51 · 4초 전"), 끝난 지 1분이 지나면 한 줄("재개 확인됨 · 1분 19초 전 · 자세히")로 접음. 경과 시간은 서버가 잰 값(`command.age_s`, 새 필드)을 써서 브라우저 시계와 비교하지 않음
- **좁은 화면(999px 이하)에서는 로봇 제어를 맨 위로**: 휴대폰 첫 화면에 일시정지 버튼이 보임 (전에는 지도 아래)
- **"추정 이동 속도"와 "이동 상태" 카드를 "이동" 하나로** 합치고, 순찰 카드를 앞에 둠
- **"상태 전달 프로그램" → "로봇"**: 머리글("로봇 연결됨"), 안내 띠, 서버 알림("로봇 연결 끊김", "로봇 상태 수신 지연", "로봇 연결 복구", "로봇 연결됨")
- **"전달 안 됨"(`expired`)을 실패로 표시**: (28)의 claim 덕분에 `expired`는 "실행 안 함"이 확실함. "정지 요청 실패 · 로봇에 제때 전달되지 않아 실행하지 않았습니다. 필요하면 다시 눌러 주세요" (전에는 "확인 불가")
- **순찰 카드**: 로봇 연결이 지연·끊김이면 회색 "순찰 중 (마지막 상태)" + "지금 상태는 알 수 없습니다" (전에는 초록 "순찰 중" 그대로)
- **지도**: 로봇 아이콘을 키우고 "로봇 따라가기"(로봇 중심 10 m) / "전체 지도 보기" 버튼
- `/demo`의 가상 순찰 시작 상태를 "순찰 중"으로 (일시정지 잠금 때문에)
- `tools/observe_ui.mjs`(Bridge 통합 검증용)를 새 머리글·카드에 맞춤

**시험**
- 화면 단위 시험 24개(새 1: 일시정지 잠금), 서버 55개, 브라우저 e2e 17개 통과
- 실제 화면 + 시뮬레이션: 휴대폰 폭(390px) 첫 화면에 일시정지 버튼 보임, 일시정지 후 버튼 잠김·사유 표시, 로봇 따라가기, 1분 뒤 결과 접힘 확인
- 시험 중 고친 것: 합친 "이동" 카드에서 연결이 끊긴 화면일 때 "마지막 수신 값" 표시가 768·390px에서 화면 밖으로 넘침 → 줄바꿈되게 함

---

## 2026-10-13 (28) 일시정지 문제 1·2 수정: 늦게 읽은 명령은 실행 안 함, 순찰 노드 꺼짐 표시

**할 일**
- **서버·Bridge·화면을 함께 올릴 것**. 새 Bridge는 서버에 "아직 유효한가"를 묻는데, 예전 서버는 이 주소가 없어서 **모든 명령을 실행하지 않음**
- Bridge 다시 빌드, 화면 다시 빌드(5분 넘게 걸림), 서버 다시 실행

**변경** (설계: `docs/CONTROL_API_DRAFT.md` §2.4, `docs/CONTROL_SCREEN.md` 실패 시험 표)
- **문제 1**: Bridge가 서비스를 부르기 직전에 `POST /api/v1/commands/{id}/claim`으로 서버에 묻고, **왕복 시간을 Bridge가 직접 잼**. 서버가 거절하거나(이미 "응답 없음"으로 끝남 등) 1초 안에 답이 없으면 부르지 않고 `expired`로 보고. 서버는 허락한 시각부터 응답 제한(5초)을 다시 셈
- **문제 2**: Bridge가 0.5초마다 `/patrol/state` 발행자(순찰 노드)가 있는지 봄. 없으면 순찰 상태를 "받았지만 알 수 없음"(필드 null, 계약 그대로)으로 보냄. 화면 순찰 카드 "순찰 상태 확인 불가 · 순찰 프로그램이 꺼져 있거나 상태를 알 수 없습니다", 재개 버튼 사유도 같이

**시험**
- 서버 55개(새 1), Bridge 66개(새 4), 화면 단위 23개, 브라우저 e2e 17개 통과
- 실제 화면 + 시뮬레이션에서 다시 돌림
  - Bridge를 얼린 뒤 일시정지: 화면 "정지 여부 확인 불가" → Bridge를 풀어도 **로봇이 실행하지 않음** (Bridge 로그 `claim refused`). 고치기 전에는 6초 늦게 멈췄음
  - 순찰 노드 끔: 순찰 카드 "순찰 상태 확인 불가", 재개 사유 "순찰 프로그램 상태를 확인할 수 없습니다", 일시정지 → **바로** "정지 요청 실패: 순찰 프로그램이 꺼져 있어 요청을 실행하지 않았습니다" (고치기 전: "순찰 중"으로 남고 3초 뒤 "응답 없음")
  - 정상 경로: 일시정지 1.38초, 재개 0.86초 만에 확인됨

**참고**
- **새로 본 것**: 순찰 노드가 꺼져도 Nav2가 하던 목표를 계속 가는 경우가 있음 (이번엔 속도 0.4 m/s로 계속 이동). 이때 일시정지 버튼은 "실패"를 사실대로 보여 주지만 **로봇을 멈추지는 못함**. Bridge가 이 경우 Nav2 목표를 직접 취소할지 정해야 함
- 문제 3(재개 직후 내비게이션 실패로 순찰 종료)은 그대로. 시험 중 두 번 더 일어남

---

## 2026-10-13 (27) 일시정지 버튼 실패·경계 상황 시험 (코드 변경 없음)

**할 일**
- 없음 (시험만 함). 아래 문제 1~3은 고칠 방법을 정한 뒤 따로 작업

**시험** (실제 화면 + 시뮬레이션, Chromium으로 버튼 클릭, 자세한 표는 `docs/CONTROL_SCREEN.md` "일시정지 실패·경계 상황 시험")
- 정상: 브라우저 두 개 동시 클릭(명령 하나만), 정지 지점 대기 중 정지(0.87초, 대기가 끝나도 계속 정지), 상태 보고 전에 Bridge가 멈춤("확인 불가", 늦은 보고로 성공으로 안 바뀜), Bridge 끔(4초 뒤 버튼 잠김, 11초 뒤 "연결 끊김", 다시 켜면 풀림)
- **문제 1**: Bridge가 명령을 늦게 읽으면 화면은 "정지 여부 확인 불가"로 끝났는데 **약 6초 뒤 로봇이 실제로 실행**함. 유효 시간을 Bridge가 읽은 순간부터 세기 때문. 재개 명령이면 예고 없이 출발할 수 있음
- **문제 2**: 순찰 노드가 꺼져도 화면은 계속 "순찰 중", 재개 버튼 사유 "이미 순찰 중입니다", 일시정지 결과는 "로봇 응답 없음"
- **문제 3**: 재개 직후 Nav2 컨트롤러가 TF 시각 10 ms 차이로 목표를 포기해 순찰 전체가 "순찰 실패"로 끝남 (내비게이션 쪽)
- 개선할 점: 이미 일시정지일 때 버튼이 눌려 "요청 실패"가 뜸, 연결이 지연·끊김이어도 순찰 카드가 초록 "순찰 중"으로 남음

**참고**
- 시험 도구: `~/limbo_bags/pause_fail/` (`scenarios.cjs`: 시나리오, `proc.sh`: 순찰 노드·Bridge만 끄기·얼리기·다시 켜기, 프로세스 그룹 단위)
- 시뮬레이션 중 `collision_monitor`가 카메라 점군이 15초 늦다고 계속 경고함 (시뮬레이션 부하). 이번 시험 결과와는 관계없음

---

## 2026-10-13 (26) Bridge: 로봇 위치를 TF로 읽음 (멈춰 있어도 위치 표시)

**할 일**
- **Bridge 다시 빌드**: `cd ~/limbo/relay_prog && venvs/bridge/bin/python -m colcon build --symlink-install --base-paths src` (의존성 `tf2_ros` 추가, ROS Jazzy에 이미 있음)
- 직접 만든 `bridge.yaml`을 쓰면 `control:`에 `map_frame: map`, `base_frame: base_footprint` 두 줄을 넣을 것. 없으면 설정 오류로 시작하지 않음

**변경** (설계: `docs/CONTROL_SCREEN.md` B)
- 위치·방향을 `/amcl_pose` 대신 **TF `map → base_footprint`에서 0.5초마다** 읽음. `/amcl_pose`는 로봇이 움직일 때만 나와서, 일시정지·순찰 완료 뒤 화면에 "위치 확인 불가"가 떴음
- `/amcl_pose`는 위치 불확실성(오차 원)에만 씀. 한 번도 못 받았으면(AMCL이 위치를 잡기 전) 위치를 보내지 않음
- 최신 TF가 1초보다 오래됐으면(오도메트리 끊김) 위치를 갱신하지 않음 → 3초 뒤 화면이 "위치 확인 불가"
- `/amcl_pose` 구독을 AMCL과 같은 **transient_local**로 바꿈. volatile이면 Bridge를 나중에 켰을 때 로봇이 움직이기 전까지 마지막 값을 못 받았음
- 텔레메트리 형식(v2)은 그대로. 서버·화면 변경 없음

**시험**
- Bridge 시험 62개 통과 (기존 58 + 새 4: 프레임 이름 검사 3, TF 위치 읽기 1 — AMCL 전·오래된 TF·TF 없음이면 안 보냄)
- 실제 연결(시뮬레이션): **일시정지 중에도 위치가 0.4~1.4초 전 값으로 계속 갱신**되고 화면 로봇이 흐려지지 않음. 재개하면 이동하는 위치를 따라감(2초마다 약 0.5 m), 정지·재개 확인도 그대로 `confirmed`

**참고**
- 처음 고친 뒤 실제 연결에서 위치가 안 나왔음. 원인은 위 transient_local 문제였고, 단위 시험으로는 안 잡혀서 실제 연결에서 찾음

---

## 2026-10-13 (25) 관제 화면: 일시정지·재개 버튼, 지도, 순찰 상태, 상태 한 줄 요약

**할 일**
- **화면 다시 빌드**: `cd ~/limbo/dashboard/ui && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm build` (5분 넘게 걸릴 수 있음, 아래 참고). 서버는 그대로 두고 브라우저만 새로고침하면 됨
- 버튼이 실제 로봇에 명령을 보냄. 시뮬레이션이 아닌 로봇에 붙일 때 조심할 것 (인증은 아직 없음)

**변경** (설계: `docs/CONTROL_SCREEN.md` A-3단계·B·D)
- **실제 화면 버튼 연결**: 일시정지·순찰 재개가 `POST /api/v1/commands`를 부름. 결과 상자(요청 전송 → 로봇 응답 → 상태 확인)는 서버의 명령 단계로 표시

  | 서버 단계 | 화면 |
  |---|---|
  | `queued` / `delivered` / `accepted` | 정지(재개) 요청 중. 진행 중인 칸만 바뀜 |
  | `confirmed` | 정지 상태 확인됨 / 재개 확인됨 (**이때만 성공**) |
  | `rejected`, `service_unavailable` | 정지 요청 실패 / 재개 실패 (사유 표시) |
  | `no_response`, `expired`, `unconfirmed`, `connection_lost` | 정지(재개) 여부 확인 불가 |

  - 연결이 `connected`가 아니거나 요청 처리 중이면 버튼을 잠금. 서버가 거절(409)하거나 서버에 못 보내면 "요청 실패"로 보여 주고 **자동으로 다시 보내지 않음**
  - 재개 버튼은 순찰 노드의 `has_resumable_task`로만 허용 ("이미 순찰 중입니다", "재개할 작업이 없습니다", "순찰 상태를 확인할 수 없습니다")
- **"프로그램 재시작" 버튼 삭제** (실제 화면, `/demo` 모두). 로봇 쪽 기능이 없고 설계에서 범위 밖으로 뺐음. 버튼 이름 "원격 정지" → **"일시정지"**
- **지도 카드** 추가 (`src/map.ts`, App의 `MapCard`): SLAM 지도 위에 순찰 경로(점선), 지점(○ 통과, □ 정지), 지난 지점 흐리게, 다음 목표 강조, 로봇 위치·방향·불확실성 원(표준편차 2배). 위치가 오래되면 로봇을 흐리게 하고 "위치 확인 불가"
- **순찰 카드** 추가: 순찰 중 / 멈추는 중 / 일시정지 / 순찰 완료 / 순찰 실패(사유), 다음 목표(몇 번째/전체)
- **상태 한 줄 요약**(머리글): 정상 / 확인 필요(이유: "카메라 원본 수신 지연" 등) / 연결 끊김. 토픽 4개 표는 맨 아래 "센서 수신 상세"로 접어 둠
- `/demo`도 같은 화면: 그림 없는 지도에 가상 로봇이 순찰 지점을 따라 움직임. 서버는 계속 부르지 않음
- "실제 수신 · 제어 미연동" 표시 삭제

**시험**
- 단위 시험 23개 통과 (기존 17 + 새 6, `src/control.test.ts`): 서버 단계 10종 → 화면 결과(`confirmed`만 성공), 잠금 이유, 재개 허용 기준(속도 무관), 보내기·거절·네트워크 실패 시 한 번만 보냄, 지도 좌표 변환, 한 줄 요약
- 실제 연결(시뮬레이션 → 순찰 노드 → Bridge → 서버 → 화면, 헤드리스 Firefox 화면 캡처): 순찰 중 지도에 로봇·다음 목표 B 표시, 일시정지 요청 → "정지 상태 확인됨" 세 칸 모두 완료, 순찰 카드 "일시정지", 재개 버튼 활성
- 브라우저 시험(e2e, Playwright Chromium) **17개 통과**: 실제 화면에서 일시정지 버튼을 누르면 서버에 명령이 생기고, 로봇이 안 가져가면 5초 뒤 "정지 여부 확인 불가"(성공으로 안 바뀜). `/demo`는 서버를 부르지 않음, 재개 사유, 센서 표 접기, 화면 폭 1440·1024·768·390px에서 가로 넘침 없음, 데모 결과 8가지
- **실제 화면에서 버튼 클릭**(시뮬레이션 연결, Chromium): "순찰 재개" 클릭 → 0.89초 만에 "재개 확인됨", 4초 뒤 속도 0.30 m/s·순찰 카드 "순찰 중". "일시정지" 클릭 → 1.87초 만에 "정지 상태 확인됨", 속도 0.00, 멈춘 동안에도 위치 표시 정상
  - 처음 돌릴 때: `node_modules/.bin/playwright install chromium` (사용자 폴더에 약 100 MB). 실행은 ROS를 source하지 않은 터미널이나 `env -u PYTHONPATH -u AMENT_PREFIX_PATH`로

**참고**
- **빌드가 5분 넘게 걸림**: rollup 4.64.0의 tree-shaking이 오래 걸림 (예전 코드로 빌드해도 같음, 코드 문제 아님). 멈춘 게 아니니 기다릴 것
- 멈춰 있으면 "위치 확인 불가"가 뜨던 문제는 (26)에서 고침

---

## 2026-10-13 (24) 대시보드 서버: 텔레메트리 v2·관제 명령·지도 API

**할 일**
- **서버 의존성 다시 설치** (PyYAML이 늘었음): `cd ~/limbo/dashboard && .venv/bin/python -m pip install -r requirements.lock`
- 서버를 다시 실행하면 적용됨. 화면(UI)은 아직 그대로라 버튼·지도는 다음 단계에서 보임
- 다른 월드로 시험할 때는 `dashboard/config.json`의 `map_yaml`, `waypoints_yaml`을 그 월드 것으로 바꿀 것 (기본은 `human_test_world`)

**변경** (설계: `docs/CONTROL_API_DRAFT.md`)
- 텔레메트리 v1·v2를 모두 받음. v2의 `patrol`(순찰 상태)·`pose`(위치)를 검사해 화면 스냅샷에 넣음. 위치가 3초 넘게 안 오면 `pose.stale: true`
- **관제 명령 API** 추가
  - `POST /api/v1/commands` `{"command": "pause"|"resume"}`: 화면이 부름. Bridge가 연결돼 있고 진행 중인 명령이 없을 때만 접수(아니면 409)
  - `GET /api/v1/commands/next`: Bridge가 부름. 최대 10초 기다렸다 명령을 한 번만 내줌 (남은 유효 시간 `ttl_ms` 포함)
  - `POST /api/v1/commands/{id}/result`: Bridge의 결과 보고. 끝난 명령에 늦게 온 보고는 결과를 바꾸지 않음
- **명령 판정**: `queued → delivered → accepted → confirmed`. 정지는 "명령 뒤에 온 순찰 상태가 `paused` + 실제 속도 정지 기준 미만"일 때만 확인됨, 재개는 "명령 뒤 `patrolling`"(속도로 판단 안 함). 안 되면 `rejected` / `service_unavailable` / `no_response` / `expired` / `unconfirmed` / `connection_lost`. 결과는 알림에 한 번 남김
  - "명령 뒤에 온 상태"는 시각이 아니라 Bridge가 센 순찰 상태 수신 횟수로 판단 (로봇·서버 시계를 비교하지 않는 v1 원칙)
  - 제한 시간: 유효 5초, 응답 5초, 상태 확인 5초 (`config.json`에서 바꿀 수 있음)
- **지도 API**: `GET /api/v1/map`(해상도·원점·크기·waypoint), `GET /api/v1/map.png`. 서버 시작 때 `map_yaml`의 pgm을 PNG로 한 번 바꿔 둠
- 실패하던 서버 시험 4개를 고침 (10-12 motion·odom 일치 검사가 들어온 뒤 시험 데이터를 안 맞춰서 422가 났음)

**시험**
- 서버 시험 54개 통과 (기존 38 + 새 16, `tests/test_control.py`), HTTP 통합 검증 `tools/validate_http.py` 통과
- 실제 연결(시뮬레이션 → 순찰 노드 → Bridge → 서버): 정지 요청 후 **1.13초 만에 `confirmed`**(로봇이 실제로 멈춘 것까지 확인), 두 번째 정지는 `rejected: already paused`, 재개 0.88초 만에 `confirmed`. 지도 302 × 302, waypoint 10개

**참고**
- 서버 시험은 ROS를 source한 터미널에서 돌리면 ROS의 pytest 플러그인 때문에 바로 멈춤. `env -u PYTHONPATH .venv/bin/python -m pytest -q`로 돌릴 것
- 손으로 확인: 서버·Bridge를 띄우고 `curl -X POST -H 'Content-Type: application/json' -d '{"command":"pause"}' http://127.0.0.1:8000/api/v1/commands`, 결과는 `curl http://127.0.0.1:8000/api/v1/state`의 `command`

---

## 2026-10-13 (23) Bridge: 텔레메트리 v2(순찰 상태·위치)와 관제 명령 처리

**할 일**
- **Bridge 다시 빌드** (`relay_prog`에서, YOLO venv 끈 터미널): `venvs/bridge/bin/python -m colcon build --symlink-install --base-paths src`
- **Bridge 실행 전에 limbo 워크스페이스도 source**: `source ~/limbo/limbo/install/setup.bash` (순찰 상태 메시지 `PatrolState`를 읽어야 함). 안 하면 Bridge가 시작하자마자 죽음
- 지금 대시보드 서버는 아직 v1만 받아서 **이 Bridge를 붙이면 422로 거절됨**. 서버 v2 작업이 끝날 때까지는 이전 Bridge를 쓰거나 Mock 서버(`tools/receiver.py`)로 시험

**변경** (설계: `docs/CONTROL_API_DRAFT.md`)
- 텔레메트리를 **v2**로 올림 (`schema_version: 2`). v1 필드는 그대로, 두 객체를 추가
  - `patrol`: 순찰 상태(`/patrol/state`) — 상태, 다음 waypoint, 재개 가능 여부, 이유, **받은 횟수(`update_count`)**
  - `pose`: 로봇 위치(`/amcl_pose`) — x, y, 방향, 위치 불확실성(m)
  - 못 받았거나 값이 이상하면(NaN 등) 전부 `null` (v1 `motion`과 같은 규칙)
- **관제 명령 작업**을 추가함. 텔레메트리와 연결을 따로 씀
  - 서버에 `GET /api/v1/commands/next`로 명령을 묻고(최대 10초 기다림), 받으면 `/patrol/pause` 또는 `/patrol/resume`을 한 번 부름(3초 제한)
  - 결과(`accepted` / `rejected` / `no_response` / `service_unavailable` / `expired`)를 `POST /api/v1/commands/{id}/result`로 **한 번만** 보냄. 다시 부르거나 다시 보내지 않음
  - 서버가 준 유효 시간(`ttl_ms`)이 지난 명령은 부르지 않음 (끊겼다 붙었을 때 오래된 정지가 뒤늦게 실행되지 않게)
- 설정 `bridge.yaml`에 `control:` 블록 추가 (토픽·서비스 이름, 기다리는 시간)
- Mock 서버(`tools/receiver.py`)가 v1·v2를 모두 받고, 명령 API를 흉내 냄 (`POST /api/v1/commands`로 명령을 넣을 수 있음)

**시험**
- 단위 시험 58개 통과 (기존 40 + 새 18, `tests/test_control.py`)
- 실제 ROS 연결(시뮬레이션 → 순찰 노드 → Bridge → Mock 서버): 정지 명령이 서비스 12 ms 만에 접수되고 2.5초 뒤 상태 `paused`·속도 0. 재개도 정상

**참고**
- 시험 방법
  ```bash
  cd ~/limbo/relay_prog
  source /opt/ros/jazzy/setup.bash; source ~/limbo/limbo/install/setup.bash
  venvs/bridge/bin/python -m pytest tests -q
  ```
- 손으로 확인: Mock 서버를 띄우고 Bridge를 붙인 뒤 `curl -X POST -H 'Content-Type: application/json' -d '{"command":"pause"}' http://127.0.0.1:8000/api/v1/commands`, 결과는 `curl http://127.0.0.1:8000/status`

---

## 2026-10-12 (22) 순찰 일시정지·재개 서비스와 순찰 상태 토픽

**할 일**
- **빌드 필요** (메시지가 새로 생김): `build_limbo`. `limbo_interfaces`를 빌드하지 않으면 순찰 노드가 `PatrolState`를 못 찾아 바로 죽음

**변경**
- 순찰 노드에 서비스 두 개를 추가했음. 관제 화면의 일시정지·순찰 재개 버튼이 쓸 것 (설계: `docs/CONTROL_SCREEN.md` A)
  - `/patrol/pause`: 순찰 중이면 Nav2 주행을 취소하고 멈춤
  - `/patrol/resume`: 멈춘 곳부터 이어서 순찰. 이미 지난 waypoint로 되돌아가지 않음
  - 둘 다 `std_srvs/srv/Trigger`. 안 되는 경우는 사유와 함께 거절함 (`already paused`, `not patrolling`, `already patrolling`, `nothing to resume` 등)
- 순찰 상태를 `/patrol/state`(`limbo_interfaces/msg/PatrolState`, 새 메시지)로 냄: 상태(`patrolling`·`paused`·`completed`·`failed` 등), 다음 waypoint, 재개 가능 여부, 바뀐 시각·이유. 늦게 붙은 구독자도 마지막 상태를 바로 받음
- 명령을 안 보내면 동작은 전과 같음 (Nav2가 실패·취소하면 순찰 실패로 끝나는 것도 같음)
- `Ctrl+C`로 끌 때 나던 오류 메시지를 없앴음
- 위치 추정이 30초 안에 준비되지 않으면 상태를 `failed`(이유 `localization not ready (30 s)`)로 내고 끝냄. 전에는 `waiting_localization`에 멈춘 채 오류로 종료돼 관제 화면이 이유를 알 수 없었음 (종료 코드 1은 그대로)

**시험** (시뮬레이션 `human_test_world`)
- 주행 중 정지 7번 모두 성공. **정지 요청부터 실제로 멈출 때까지 평균 0.55초, 최대 0.66초**
- 정지·재개 5개 동시, 0.1~0.5초 간격 섞어 40번: 접수는 매번 1개만, 응답 없음 0번, 응답 평균 4 ms. 마지막 명령대로 상태가 정리되고 노드가 멈추지 않음
- 15초마다 정지·재개하며 순찰 5번 모두 완주 (정지 없음 5번과 시간 차이는 멈춘 시간만큼). stop 지점 대기 중 정지 후 재개도 다음 구간으로 정상 진행

**참고**
- 서비스를 직접 시험해 보려면
  ```bash
  ros2 topic echo /patrol/state
  ros2 service call /patrol/pause std_srvs/srv/Trigger
  ros2 service call /patrol/resume std_srvs/srv/Trigger
  ```
- (21) 전에는 정지 지점 0.2~0.4 m 앞 갇힘이 정지·재개 회차에서 더 자주 났음(5번 중 3번 5~7분). (21)을 합친 뒤에는 0번
- 아직 확인 못 한 것: 구간 사이(대기 끝 → 다음 구간 출발 직전)에 정지가 들어오는 순간. 코드로는 막아 둠
- 관제 화면 버튼과는 아직 연결 안 됨 (Bridge·서버 작업이 다음 단계)

---

## 2026-10-12 (21) 순찰 정지 지점 방향 수정 정리 (원작자 PR #9)

**할 일**
- 없음 (waypoint yaml만 바뀜. 순찰 노드만 다시 실행하면 됨. 설치 폴더가 symlink가 아니면 `build_limbo`)

**변경 (원작자 PR #9)**
- 순찰 중 정지 waypoint 0.3 m 앞에서 멈춘 뒤 실패하던 문제를 원작자가 해결했음. `test_waypoints.yaml`의 정지 지점 C·G·J의 방향(yaw)을 들어가는 방향으로 바꿨음 (C −124°, G −89°, J −179°)
  - 원인: 목표가 로봇 옆·뒤에 남았는데 목표 방향은 이미 맞아 있어서, 후진이 꺼진 MPPI가 돌아서 다가가는 것보다 멈추는 쪽을 골랐음
  - 확인: 원래 월드 순찰 10/10 완주

**정리 (ktj)**
- `docs/TROUBLESHOOTING.md`에 위 문제를 "증상 → 원인 → 해결 → 확인"으로 추가하고 원작자 문서 두 개(`NAV2_NEAR_GOAL_FAILURE_2026-10-12.md`, `NAV2_YAW_10_RUN_VALIDATION_2026-10-12.md`)를 링크했음
- `docs/KNOWN_ISSUES.md`에서 해결된 안내 단락을 빼고, 원작자가 남긴 남은 문제 두 개를 표로 정리했음 (사람이 아주 가까울 때 MPPI 경고, launch 고정 시간 때문에 가끔 시작 실패)

**참고**
- **새 waypoint 파일을 만들 때 정지 지점의 yaw는 들어가는 방향으로** 둘 것. yaml의 yaw는 도 단위

---

## 2026-10-12 (20) 헛돎 감시 오탐 방어 수정

**할 일**
- 없음 (Python·yaml만 바뀜. 시뮬레이션만 다시 띄우면 적용됨)

**변경**
- 헛돎 확정에 필요한 연속 의심을 1초(0.5초 × 2) → **2초(0.5초 × 4)**로 늘렸음. 사람이 지나가며 생기는 순간적인 오판을 거름 (`slip.consecutive_windows: 4`)
- 두 스캔의 점이 잘 안 맞으면(사람이 가리는 등) 그 구간은 판단을 보류함 (`slip.min_inlier_ratio: 0.8`)
- 녹화 데이터로 확인: 상자에 막힌 진짜 헛돎은 1초 늦게 잡을 뿐 모두 감지, 사람 경로·사람 10명 방에서 오탐 0

**참고**
- 팀원 환경의 오탐 원인은 아직 확정 못 했음. 이번 수정 후에도 오탐이 나면 터미널의 `[wheel_slip_monitor]: SUSPECT/SLIP: wheel ... m, scan ... m` 줄을 보내 주세요
- 주행 취소는 계속 꺼져 있음 (진짜로 막혀도 로봇이 계속 밈). 오탐이 사라진 게 확인되면 다시 켤 예정

---

## 2026-10-12 (18) launch에 사람 인식 모델 선택 인자 추가

**할 일**
- 없음 (launch 파일만 바뀜)

**변경**
- `start_simulation.launch.py`에 `person_model` 인자를 추가했음. 경로를 주면 yaml을 고치지 않고 그 모델로 사람 인식을 돌림. 비우면(기본) 지금처럼 `person_detector.yaml`의 yolo11n
  ```bash
  ros2 launch limbo_bringup start_simulation.launch.py world:=aischool_2f_scenarios map:=aischool_2f_map \
    person_model:=$HOME/limbo/human-leg/runs/person_leg_stage1/weights/best.pt
  ```
- 하반신 모델은 아직 학습 중이라 기본으로 바꾸지 않았음. 새 모델이 나오면 경로만 바꿔 같은 시험을 반복하면 됨

---

## 2026-10-12 (17) 사람 거리 계산 수정 (다리만 보일 때), 하반신 모델 평가

**할 일**
- 없음 (Python·yaml만 바뀜. 시뮬레이션만 다시 띄우면 적용됨)

**변경**
- 사람까지 거리를 박스 가운데 영역 depth의 **중앙값** 대신 **가까운 순 25% 위치 값**으로 재게 했음 (`person_detector.yaml`의 `depth.percentile: 25.0`, 50이면 예전과 같음). 다리만 보이는 박스는 가운데가 다리 사이로 보이는 벽이라 중앙값이 벽까지 거리가 됐음
- 팀원의 하반신 모델(`human-leg/.../best.pt`)을 시뮬레이션에서 평가했음. 1.4m 앞에 멈춘 사람(다리만 보임)을 기존 모델은 65%, 하반신 모델은 100% 검출. 이번 거리 수정과 같이 쓰면 4초 동안 끊김 없이 추적함 (자세한 표는 `docs/TROUBLESHOOTING.md`)
- **기본 모델은 그대로 yolo11n**임. 실제 사람으로 확인한 뒤 바꾸기로 했음

**참고**
- 하반신 모델을 시험해 보려면: `ros2 launch ... ` 후 사람 인식 노드의 `yolo.model`을 `~/limbo/human-leg/runs/person_leg_stage1/weights/best.pt`로 지정 (yaml 또는 `-p yolo.model:=...`)
- 사람 몸이 박스 가운데의 25%보다 적으면 다시 배경을 잼 → `docs/KNOWN_ISSUES.md`

---

## 2026-10-12 (16) 전역 costmap에 장애물 층(STVL) 추가

**할 일**
- 없음 (설정 파일만 바뀜. 시뮬레이션만 다시 띄우면 적용됨)

**변경**
- 전역 costmap(경로 계획기가 보는 지도)에 로컬과 같은 STVL 층을 추가했음 (기억 15초). 전에는 지도의 벽만 알아서, 지도에 없는 낮은 상자를 관통하는 경로를 그렸고 로봇이 상자 앞에서 머뭇거리다 부딪혔음
- 시험: 상자 6/6 회피 (전에는 2/2 부딪힘), 위쪽 복도 사람 왕복 24/24 성공

**참고**
- 좁은 복도를 사람이 막으면 경로 계획이 실패하고 재시도함. 이동당 복구 동작이 0~1번에서 약 12번으로 늘고 2~3초 더 걸림. 순찰 시험에서 복구 횟수나 실패가 늘면 알려 주세요
- 로봇 바로 앞(약 1m 안쪽)에 처음부터 있던 낮은 물체는 여전히 못 봄 → `docs/KNOWN_ISSUES.md`
- dev에 합쳐진 PR #7·#8(대시보드, 중계 프로그램, 학습 결과)도 ktj에 받았음

---

## 2026-10-12 (15) 헛돎 감시 시각 어긋남 수정, 오탐 조사 결과

**할 일**
- 없음 (`limbo_monitor`에 Python 파일이 하나 늘었지만 symlink 빌드라 시뮬레이션만 다시 띄우면 됨. 안 되면 `build_limbo`)

**변경**
- 헛돎 감시가 스캔을 **도착한 순간의 최신 바퀴 odom**과 비교하고 있었음. 스캔은 포인트클라우드 변환을 거쳐 늦게 도착하므로, 멈췄다 출발하는 순간에는 스캔은 아직 정지인데 바퀴는 출발한 상태라 헛돎으로 보일 수 있었음. 최근 2초 odom을 보관해 **스캔을 찍은 시각의 odom**과 비교하도록 고쳤음
- 상자에 막혀 바퀴만 도는 진짜 헛돎은 수정 후에도 그대로 감지됨

**참고 (팀원이 겪은 오탐 조사)**
- 시뮬레이션에서 사람 경로, `human_test_world`(사람 10명), 스캔 지연 0.5초 재현까지 해 봤지만 오탐을 재현하지 못했음. 원인 확정에는 오탐이 날 때의 로그가 필요함
  - 터미널의 `[wheel_slip_monitor]: SUSPECT: wheel ... m, scan ... m` / `SLIP: ...` 줄
  - 가능하면 그 상황 녹화: `ros2 bag record /scan /odom /ground_truth/odom /wheel_slip -o slip_case`
- **주의**: 주행 취소를 꺼 둔 지금은 로봇이 진짜로 막혀도 멈추지 않음 (시험에서 상자를 2분 동안 계속 밀었음). Nav2의 "진전 없음" 판단도 바퀴 odom을 봐서 막지 못함 → `docs/KNOWN_ISSUES.md` "바퀴 헛돎 감시"

---

## 2026-10-12 (14) 헛돎 감시 주행 취소 임시로 끔, 낮은 장애물 시험 월드

**할 일**
- **빌드 한 번 필요** (`limbo_evaluation`에 새 파일): `build_limbo`

**변경**
- `wheel_slip_monitor.yaml`의 `cancel_navigation_on_slip`을 `false`로 바꿨음. 사람이 로봇 가까이 지나가면 스캔 비교가 속아 헛돎으로 잘못 판단하고 주행을 취소하던 문제 때문임 (팀원 주행 시험과 시뮬레이션에서 확인). 감지, `/wheel_slip` 발행, 로그는 그대로임
- 시나리오 월드 홀 서쪽에 지도에 없는 낮은 상자 2개(0.1m, 0.3m)를 두었음. 측정 도구 CSV에 상자까지 최소 거리(`min_obstacle_distance_m`)와 닿은 시간(`obstacle_contact_time_s`)이 추가됐음
- dev에 병합된 순찰 노드 개선(PR #6)을 ktj에도 받았음

**참고**
- 지금 설정(로컬 costmap에만 장애물 층)으로는 로봇이 0.1m 상자에 부딪힘. 전역 costmap에 장애물 층을 넣으면 피하지만 좁은 복도에서 사람 때문에 경로 계획이 자주 실패해서, 반복 시험 후 정할 예정
- 헛돎 오탐 수정과 "진짜로 막혔을 때 취소할지"는 `docs/KNOWN_ISSUES.md` "바퀴 헛돎 감시"

---

## 2026-10-07 (13) 멈춘 사람 예측 개선, 센서 사각지대 기록

**할 일**
- 없음 (Python·yaml만 바뀜. 시뮬레이션만 다시 띄우면 적용됨)

**변경**
- `person_detector`가 멈춘 사람을 빨리 알아채게 했음. 최근 0.6초 동안 측정 위치가 0.15m 미만으로 움직였으면 속도를 0으로 하고 위치를 최근 측정 평균으로 맞춤 (`person_detector.yaml`의 `tracking.stop_window`, `tracking.stop_max_displacement`)
  - 멈춘 뒤 1~2초 추정 속도 0.37 → 0.03m/s. 걷는 사람 출력은 수정 전과 같음
- 검출이 잠깐 끊겼다 다시 잡힐 때 "그 자리에 멈췄을 경우"도 고려해 같은 사람으로 재연결하게 했음 (전에는 새 ID가 붙었음)
- 시나리오 분석에서 찾은 센서 사각지대를 `docs/KNOWN_ISSUES.md` "센서 배치"에 수치와 함께 기록했음
  - 카메라가 낮아(0.5m, 수평) 2m 안의 사람은 다리만 보여 YOLO 검출이 끊김
  - MID-360 아래쪽 시야가 −7°라 0.1m 방지턱은 5.1m, 0.3m 상자는 3.5m보다 가까우면 안 보임
- URDF 카메라 주석이 실제 값(0.50m, 수평)과 달라서 고쳤음

**참고**
- 센서 높이·기울기는 하드웨어 담당과 정해야 함. 결정에 필요한 표가 KNOWN_ISSUES에 있음
- 실제 카메라는 위치가 시뮬레이션보다 많이 흔들리므로, 서 있는 사람이 걷는 것으로 나오면 `stop_max_displacement`를 키울 것

---

## 2026-10-07 (12) 주행 평가 기록 도구 `limbo_evaluation`

**할 일**
- **빌드 한 번 필요** (새 패키지, 로봇 모델에 정답 위치 플러그인 추가): `build_limbo`

**변경**
- Nav2 Goal이 끝날 때마다 주행 지표를 CSV 한 줄로 남기는 `nav_recorder`를 추가했음. launch에 `record:=true`를 붙이면 켜지고, 결과는 `~/limbo_results/nav_<월드>_<날짜_시각>.csv`에 쌓임
  - 결과, 시간, 주행 거리, 사람과의 최소 거리와 개인 공간(0.5m) 침범 시간, 위치 추정 오차, 복구 횟수, 컨트롤러 주기 경고, 헛돎 감지
  - 위치 추정 오차는 TF(`map → base_footprint`)로 재서 AMCL을 다른 방식으로 바꿔도 같은 기준으로 비교됨
  - 열 설명은 README "주행 평가 기록"
- 로봇 모델에 Gazebo 정답 위치 플러그인을 달고 `/ground_truth/odom`으로 브리지했음. 평가 전용이고 주행 노드는 쓰지 않음
- 확인: `aischool_2f_scenarios`에서 왕복 4번 → CSV 4줄, 위치 오차 최대 0.11~0.12m, 서 있는 사람 옆 0.70m. 나란히 걷는 두 사람이 로봇에 0.33m까지 붙은 순간과 그때의 복구 1번도 기록됐음

**참고**
- 시뮬레이션 전용이고, 지도 원점과 Gazebo 월드 원점이 같다고 가정함 (`human_test_world`, `aischool_2f*`는 같음)
- 이전에 임시 스크립트로 잰 AMCL 오차(0.24~0.28m)는 정답을 느리게 받아 시각이 다른 위치끼리 비교해서 부풀려진 값이었음

---

## 2026-10-07 (11) MPPI 주기 저하 해결 확인, LiDAR 5Hz 원인 정정

**할 일**
- 없음 (문서만 바뀜)

**변경**
- 어제 기록한 MPPI 컨트롤러 주기 저하(20Hz → 6.5Hz, 주행 실패)를 다시 시험했음. Gazebo 창을 켠 기본 상태에서 홀 ↔ 왼쪽 복도 왕복 4/4 성공, 주기 경고는 1번(12.5Hz)뿐이었음. 오늘 줄인 CPU(헛돎 감시, 사람 인식) 덕분이라 KNOWN_ISSUES에서 TROUBLESHOOTING으로 옮겼음
- LiDAR가 10Hz 설정인데 5Hz로 나오는 문제는 Gazebo 창을 꺼도 같고 GPU도 남아서 부하 때문이 아니었음. 원인 추정을 Gazebo 센서 스케줄링으로 고쳤음

**참고**
- 주기 경고 확인 방법: `~/.ros/log/controller_server_*.log`에서 `Control loop missed` 줄 수 세기

---

## 2026-10-07 (10) 시나리오 월드 추가, Gazebo 창 끄기 옵션

**할 일**
- **빌드 한 번 필요** (새 월드 파일 설치): `build_limbo`

**변경**
- 시험용 월드 `aischool_2f_scenarios`를 추가했음. 같은 학원 2층 건물·지도에 사람 6명이 장소마다 상황 하나씩을 반복함
  - 로봇 시작 위치 1.6m 앞에 와서 4초 멈춤 / 홀에서 오른쪽 복도로 90° 꺾음 / 왼쪽 복도 벽에 붙어 서 있음 / 위쪽 복도에 둘이 0.6m 간격으로 천천히 / 왼쪽 아래 복도를 빨리(1.6m/s)
  - 모두 정해진 시간표대로만 움직이고 로봇에 반응하지 않음 (매번 같은 상황을 재현하려고)
  - 실행: `ros2 launch limbo_bringup start_simulation.launch.py world:=aischool_2f_scenarios map:=aischool_2f_map`
  - 기존 `aischool_2f` 월드는 그대로임. 경로는 `tools/aischool_2f/gen_world.py`의 `SCENARIO_PATHS`
- launch에 `gui` 옵션을 추가했음. `gui:=false`면 Gazebo 3D 창 없이 서버만 뜸. 센서·사람·주행은 그대로이고 Gazebo CPU가 285% → 110%로 줄었음. 기본은 켬이라 지금처럼 쓰면 됨

**참고**
- 창을 끄면 Gazebo가 가벼워져 depth 카메라가 원래 설정대로 15Hz로 나오고(전에는 약 10Hz), 그만큼 person_detector가 프레임을 더 처리해 CPU가 늘어 보일 수 있음
- 멈추거나 꺾는 사람은 예상 위치와의 차이가 평균 0.4m로, 직진하는 사람(0.15m)보다 큼. 이걸 시험하려고 만든 시나리오이고 분석은 다음 작업

---

## 2026-10-06 (9) person_detector CPU 감소 (sim time 해제)

**할 일**
- 없음 (Python·launch 파일만 바뀜. symlink 빌드라 시뮬레이션만 다시 띄우면 적용됨)

**변경**
- `person_detector`가 예측 메시지(`/person_detector/predictions`) 시각을 노드 시계 대신 **그 카메라 이미지를 찍은 시각**으로 찍게 했음. 노드 시계를 안 쓰게 돼서 launch에서 `use_sim_time: False`로 실행함. Gazebo `/clock`(초당 약 740번)을 받지 않아 CPU가 약 30%p 줄었음 (나란히 띄운 비교 139% → 109%)
- 녹화 bag 재생 비교에서 출력 870프레임이 기존과 같았음. human_layer가 예측의 나이를 잴 때도 카메라 시각이 더 정확함

**참고**
- 실행기(`MultiThreadedExecutor`)의 남는 스레드가 헛도는 문제(약 20%p)도 찾았지만, 고치는 방법마다 처리량이나 TF 실패 횟수가 바뀌어 적용하지 않았음. 시도한 내용은 `docs/KNOWN_ISSUES.md`

---

## 2026-10-06 (8) 헛돎 감시 CPU 감소, 안 쓰는 LiDAR 브리지 삭제

**할 일**
- 없음 (launch·설정 파일만 바뀜. 시뮬레이션만 다시 띄우면 적용됨)

**변경**
- `wheel_slip_monitor`를 `use_sim_time: False`로 실행하게 했음. sim time을 켜면 Gazebo `/clock`(초당 약 740번)을 Python이 전부 처리해 CPU를 50% 썼음 → 5%. 판단 로직은 스캔 메시지 시각만 써서 동작은 같음
- 아무도 구독하지 않던 MID-360 LaserScan 브리지(`mid360`)를 삭제했음. 포인트클라우드(`mid360/points`)와 `/scan`은 그대로. CPU 효과는 측정 오차 수준

**참고**
- 같은 `/clock` 부담이 sim time이 꼭 필요한 `person_detector`에도 있음. Gazebo 물리 스텝을 늘리는 방법을 검토 중 (`docs/KNOWN_ISSUES.md`)
- CPU를 잴 때는 Gazebo가 일시정지 상태가 아닌지 먼저 확인할 것 (`docs/TROUBLESHOOTING.md`)

---

## 2026-10-06 (7) AMCL beamskip, 왼쪽 복도 멈춤 해결

**할 일**
- 없음 (설정 파일만 바뀜. 시뮬레이션만 다시 띄우면 적용됨)

**변경**
- `amcl.yaml`에 beamskip을 적용했음 (`laser_model_type: likelihood_field_prob`, `do_beamskip: true`). 사람처럼 지도에 없는 장애물에 맞은 빔을 위치 계산에서만 뺌. 장애물 회피는 모든 빔을 그대로 씀
- 원인: 좁은 복도에서 걷는 사람과 마주치면 AMCL 파티클이 앞뒤로 퍼졌다가, 복도 끝 교차로에서 위치가 크게 튀었음 (방향 51~68° 오차)
- 확인: 같은 마주침 시험에서 방향 오차 1.5° 이내, `aischool_2f` 왼쪽 복도 Nav2 왕복 4/4 성공
- 조사 과정과 배제한 원인은 `docs/TROUBLESHOOTING.md`에 있음

**참고**
- 좁은 복도(1.54m)에서 제자리 회전 실패, CPU가 몰릴 때 MPPI 주기 저하(20Hz → 6.5Hz)를 새로 찾아 `docs/KNOWN_ISSUES.md`에 기록했음
- `Ctrl+C` 후 Gazebo 서버가 남는 경우가 있음. 다시 띄우기 전에 `ps aux | grep "gz sim"`으로 확인

---

## 2026-10-06 (6) 왼쪽 복도 멈춤 조사 기록

**할 일**
- 없음 (문서만 바뀜)

**변경**
- `aischool_2f` 왼쪽 복도 멈춤 문제를 조사해 `docs/KNOWN_ISSUES.md`에 기록했음. 원인은 AMCL 내부로 좁혀졌고(odom·EKF·지도·스캔은 정상), 다음 실험 계획을 적어 두었음
- `wheel_slip_monitor` CPU 사용량(약 54%)과 LiDAR 실제 주기(약 5Hz) 문제를 추가했음

**참고**
- `aischool_2f`에서 왼쪽 복도 위쪽(y 5~7.5)을 지나는 Goal은 아직 실패할 수 있음

---

## 2026-10-06 (5) README 새로 작성, requirements.txt 복원

**할 일**
- 기존 팀원은 없음
- 새로 설치하는 사람은 README "설치"를 위에서부터 따라 하면 됨

**변경**
- README를 설치 → 실행 → 구성 순서로 새로 썼음. 문서 안내, 월드 선택표, 패키지·토픽·튜닝 파일 위치를 넣었고, 원작자의 하드웨어 조정 메모는 그대로 살렸음
- PR #5에서 지워졌던 `requirements.txt`를 되살렸음 (`setuptools<80` 고정 추가). 지워진 상태에서는 README대로 YOLO 환경을 만들 수 없었음
- 설치 단계에 `ros-dev-tools`(colcon), `rosdep`, HTTPS clone, GPU용 torch 설치 명령을 넣었음
- 새 셸·새 venv에서 README 명령 그대로 clone → venv → 빌드 → 테스트까지 통과하는 것을 확인했음 (apt 단계와 새 설치본의 시뮬레이션 실행은 미확인)

---

## 2026-10-06 (4) 바퀴 헛돎 감시, 문제 해결 기록

**할 일**
```bash
build_limbo
```

**변경**
- 바퀴 헛돎 감시 노드 `limbo_monitor/wheel_slip_monitor`를 추가했음. 0.5초마다 바퀴 이동량과 LiDAR 스캔(ICP) 이동량을 비교해, 바퀴만 돌고 로봇이 안 움직이면 `/wheel_slip`을 True로 내고 Nav2 Goal을 취소함. 시뮬레이션 실행 시 자동으로 같이 뜸
- 시험 결과: 벽에 밀어붙였을 때 1.0초 만에 감지, Goal 취소 0.017초. `aischool_2f` 복도 4분 주행(22m 왕복 포함) 오경보 0건
- 긴 복도처럼 스캔으로 앞뒤 이동을 알 수 없는 구간에서는 판단을 보류함
- 튜닝값은 `limbo_monitor/config/wheel_slip_monitor.yaml`
- 겪은 문제의 원인·해결 과정을 모은 `docs/TROUBLESHOOTING.md`를 추가했음

**참고**
- `aischool_2f` 왼쪽 복도 (−5.8, 4.4) 부근에서 Nav2가 Goal을 포기하고 멈추는 문제가 있음. 원인 조사 중 (`docs/KNOWN_ISSUES.md`)

---

## 2026-10-02 (3) IMU 추가, 바퀴 odom + IMU 융합(EKF)

**할 일**
```bash
sudo apt install ros-jazzy-robot-localization   # 처음 한 번만
build_limbo
```

**변경**
- 시뮬레이션 로봇에 MID-360 내장 IMU를 추가했음 (`/imu`, 200Hz, 노이즈·바이어스 포함)
- 바퀴 odom(전진 속도)과 IMU(회전 속도)를 EKF로 합쳤음. 회전 오차가 360° 회전 기준 31°에서 0.4°로 줄었음
- `odom → base_footprint` TF는 이제 EKF(`ekf_filter_node`)가 발행함. Gazebo diff-drive TF는 브리지하지 않음

**참고**
- 로봇이 걸려서 바퀴만 헛도는 문제는 IMU로도 못 잡아서 남아 있음 (`docs/KNOWN_ISSUES.md`)
- 바퀴 마찰 계수(0.5)가 낮아 회전 시 미끄러짐. 회전 오차의 원인으로 추정

---

## 2026-10-02 (2) 학원 2층 월드, 월드·지도 선택 인자

**할 일**
```bash
build_limbo
```

**변경**
- 피난안내도 사진으로 학원 2층 월드 `aischool_2f`를 만들었음 (교실 7개, 홀, 복도, 걷는 사람 3명). 같은 도면으로 만든 지도도 있어서 SLAM 없이 바로 주행 가능함
  ```bash
  ros2 launch limbo_bringup start_simulation.launch.py world:=aischool_2f map:=aischool_2f_map
  ```
- launch에 `world`, `map` 인자를 추가했음. 인자 없이 실행하면 기존 `human_test` 그대로임
- 월드 생성 스크립트를 `limbo_simulation/tools/aischool_2f/`에 넣었음. 축척은 교실 깊이 실측(약 6.1m)과 복도 폭(약 1.5m)으로 맞췄음
- 미해결 문제 목록 `docs/KNOWN_ISSUES.md`를 만들었음

**참고**
- 새 월드 주행 중 로봇이 걸려 바퀴만 헛돌면 AMCL이 위치를 놓치는 문제를 확인했음

---

## 2026-10-02 (1) person_detector 리팩터링, 버그 수정

**할 일**
```bash
build_limbo
```

**변경**
- person_detector를 기능별 파일로 나눴음 (`tracking`, `kalman`, `motion`, `intent`, `geometry`, `visualization`, `messages`). 같은 rosbag으로 전후 출력이 같은 것을 확인했음
- 튜닝값을 `limbo_perception/config/person_detector.yaml`로 뺐음. 빌드 없이 바꿀 수 있음
- 시뮬레이션을 켜면 2D Pose Estimate 없이 바로 주행 가능함 (AMCL 초기 위치 = 스폰 위치)
- Gazebo가 일시정지 없이 바로 재생됨
- person_detector CPU 사용량을 줄였음 (시뮬레이션 중 약 775% → 116%). torch·numpy 스레드 풀이 서로 헛돌던 문제였음
- 새로 clone하면 `limbo_description` 빌드가 실패하던 문제를 고쳤음
- `.gitignore`에 `__pycache__`, `*.pyc`를 추가했음

**참고**
- 리팩터링 전 원본은 `kkh` 브랜치에 있음

---

# 리팩터링 이전 (2026-08-18 ~ 2026-09-30, 원작자 작업)

더 이상 추가하지 않는 기록이다. 이 문서를 만들기 전 커밋을 보고 2026-10-02에 정리했음. 커밋 메시지가 짧은 경우("수정본", "지금 안됨" 등)는 바뀐 파일로 내용을 추정했음. 틀린 부분은 작성자가 고쳐 주면 됨.

## 2026-09-30 PR #5 (kkh → dev)

- 폴더 구조를 다시 평평하게 되돌렸음 (`src/common`, `src/navigation`, `src/perception` → `src/limbo_*`)
- Nav2 파라미터를 축별 yaml 조합에서 `limbo_navigation/config/nav2_params.yaml` 한 파일로 되돌렸음
- `human_layer`를 `limbo_human_costmap`에서 `limbo_navigation`으로 옮기고, 오래된 예측을 버리는 `max_prediction_age` 검사를 넣었음
- person_detector가 RGB와 depth를 `ApproximateTimeSynchronizer`로 같은 시점끼리 묶고, TF를 이미지 시각으로 조회하게 바꿨음. 실행기를 `MultiThreadedExecutor`(2스레드)로 바꿨음
- patrol_node를 stuck 재시도 로직이 없는 단순 버전(232줄)으로 바꿨음. stuck 로직이 있던 이전 버전은 `.codex-backups/`에 백업으로 남아 있음
- `limbo_patrol/config/test_waypoints.yaml` 추가
- `limbo/requirements.txt`, `limbo/README.md`를 지우고 루트 `README.md`를 정리했음

## 2026-09-23 PR #4, 구조 개편, ktj 트랙

- 폴더를 담당별로 나눴음 (`src/common`, `src/navigation`, `src/perception`). Nav2 파라미터를 축별 yaml로 쪼개 launch에서 조합하게 했음 (`config/common`, `costmap`, `planner`, `controller`, `localization`, `robot`)
- `human_layer`를 별도 패키지 `limbo_human_costmap`으로 분리했음
- YOLO용 `requirements.txt`, 상세 `limbo/README.md`(주행·인지 투트랙 가이드) 추가
- (ktj) Gazebo diff-drive 각속도·각가속도 한계를 Nav2 값(1.8 / 3.0)에 맞췄음. MPPI 사람 회피 오버레이를 `mppi.yaml`로 흡수했음
- (ktj) `docs/PROJECT.md`(프로젝트 개요와 할 일) 추가
- (kkh) patrol_node에 stuck 감지 후 재시도 로직 추가(9/30 PR #5에서 단순 버전으로 다시 바뀜), `human_test_world` 걷는 사람을 1명에서 10명으로 늘림, MPPI 값 조정

## 2026-09-22 1차 테스트

- MPPI 회전 한계를 올렸음 (`wz_max` 1.0 → 1.8, `az_max` 1.5 → 4.0), `visualize` 끔
- 기본 월드를 `bookstore_world`로 바꿔 시험했음
- README에 alias 사용법 추가

## 2026-09-21 사람 회피 주행

- `human_layer`가 예측 시점별로 cost를 다르게 주게 확장했음 (가까운 미래일수록 높게)
- 사람 회피 시험용 `human_test_world`와 `human_test_map` 추가

## 2026-09-18 사람 이동 경로에 cost 부여

- 사람 예측 메시지 `limbo_interfaces/PersonPrediction(Array)` 추가
- local costmap 플러그인 `human_layer` 첫 버전 추가 (예측 위치에 cost 부여)
- person_detector가 사람별 예측 경로를 발행하게 했음

## 2026-09-17 순찰, 장애물 레이어 변경

- `limbo_patrol` 패키지 추가 (waypoint 순찰, `config/waypoints.yaml`)
- local costmap 장애물 레이어를 STVL(3D 복셀)로 바꿨음. 이전 설정은 `nav2_params_before_stvl.yaml`로 남겼음

## 2026-09-14 사람 인식

- `limbo_perception` 패키지와 `person_detector` 첫 버전 추가 (YOLO + RGB-D depth로 사람 3D 위치 추정)

## 2026-09-11 RGB-D 카메라, self filter

- 로봇에 RGB-D 카메라 추가, 카메라 포인트클라우드를 local costmap에 반영했음
- `robot_self_filter` 서브모듈 추가 (LiDAR가 로봇 몸체를 장애물로 보지 않게 함)
- `nav2_params.yaml`, 통합 실행 `start_simulation.launch.py` 정비

## 2026-09-10 README

- 루트 `README.md` 추가

## 2026-09-08 Gazebo 환경, SLAM

- 패키지 4개 추가: `limbo_description`(로봇 URDF), `limbo_simulation`(bookstore 월드, ros_gz 브리지), `limbo_navigation`, `limbo_bringup`
- SLAM으로 `bookstore_map`을 만들고 AMCL 위치 추정(`amcl.yaml`, `localization.launch.py`) 추가
- 처음 커밋에 `build/`, `install/`이 들어갔다가 같은 날 `.gitignore`로 뺐음

## 2026-08-18 저장소 생성

- 저장소와 `CODEOWNERS.txt` 생성
