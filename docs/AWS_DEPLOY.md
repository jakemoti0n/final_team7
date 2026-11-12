# 관제 서버를 AWS에 올리기 (초보자용)

작성: 2026-11-06 · 대상: 관제 서버(`dashboard/`)를 인터넷에서 접속할 수 있게 작은 인스턴스 1대에 올리려는 사람

## 0. 전체 그림

```
[브라우저] ──HTTPS + 로그인 화면(아이디/비밀번호)──┐
                                                    ▼
                             [AWS 인스턴스 1대]
                             Caddy (443, 인증서 자동. HTTPS만 담당)
                               │
                               ▼
                             dashboard 컨테이너 (8000, 밖으로 안 열림)
                               │  화면·브라우저 API: 서버가 로그인 세션 검사 (계정: /data/users.db)
                               │  로봇용 4경로: 서버가 토큰 검사
                               ▲
[로봇: Bridge] ──HTTPS + 토큰(Authorization: Bearer)──┘   (로봇에서 나가는 연결만. 로봇 쪽 포트는 안 연다)
```

- 서버에는 ROS가 없다. 순찰 시작·종료도 서버는 명령만 쌓고 **로봇의 Bridge**가 로봇 컴퓨터에서 실행한다(`dashboard/README.md` 「주행 시작·정지·재개·종료」)
- 화면 로그인은 관제 서버의 **사람별 계정**(모두 관리자 한 등급, 화면의 「회원 관리」에서 추가·삭제), 로봇은 **공유 토큰**. 둘 다 HTTPS 위에서만 쓴다
- 쓰는 파일(모두 `dashboard/`): `Dockerfile`, `docker-compose.yml`, `Caddyfile`, `.env.example`, `deploy/`

준비물: AWS 계정, 내 PC의 터미널(SSH), 30분 정도.

---

## 1. 인스턴스 만들기

### Lightsail (쉬움, 추천)

1. AWS 콘솔 → **Lightsail** → **Create instance**
2. 지역: **Seoul (ap-northeast-2)** (로봇과 가까울수록 응답이 빠르다)
3. 플랫폼 **Linux/Unix**, 블루프린트 **OS Only → Ubuntu 24.04 LTS**
4. 요금제: **1 GB 메모리**면 충분하다(화면 빌드가 약 0.5 GB). 여유를 위해 아래 4절의 스왑을 만들어 두기를 권한다
5. 이름(예: `limbo-dashboard`) → **Create instance**

### EC2 t3.micro (대안)

AMI **Ubuntu Server 24.04 LTS**, 유형 **t3.micro**(메모리 1 GB, 4절 스왑 권장), 키 페어를 새로 만들어 `.pem`을 받아 둔다. 저장 공간 16 GB 이상.

## 2. 고정 IP 붙이기

인스턴스를 다시 시작해도 주소가 바뀌지 않게 한다. 로봇의 `server_url`과 인증서가 이 주소에 묶이기 때문이다.

- Lightsail: **Networking → Create static IP** → 인스턴스에 연결
- EC2: **Elastic IP 할당** → 인스턴스에 연결

이 주소를 적어 둔다. 아래에서는 예로 `13.125.10.20`을 쓴다.

## 3. 방화벽

| 포트 | 열 곳 | 이유 |
|---|---|---|
| 80/TCP | 모두 | 인증서 발급(Let's Encrypt)과 http → https 이동 |
| 443/TCP | 모두 | 화면과 로봇 연결 (HTTPS) |
| 443/UDP | 모두 (선택) | HTTP/3. 없어도 동작 |
| 22/TCP | **내 IP만** | SSH. 모두에게 열면 비밀번호 대입 공격이 바로 들어온다 |
| 8000 | **열지 않음** | 서버는 Caddy 뒤에만 있다 |

- Lightsail: 인스턴스 → **Networking → IPv4 Firewall** → HTTP·HTTPS 추가, SSH 규칙의 **Restrict to IP address**에 내 IP(<https://checkip.amazonaws.com>에서 확인)
- EC2: 보안 그룹 인바운드 규칙에 위 표대로

집·학원 IP가 바뀌면 SSH가 막힌다. 그때 콘솔에서 SSH 규칙의 IP만 고친다.

## 4. 접속과 기본 준비

```bash
# Lightsail: 콘솔의 "Connect using SSH" 버튼, 또는 내 PC에서 (키는 Account → SSH keys에서 받음)
ssh -i ~/Downloads/LightsailDefaultKey-ap-northeast-2.pem ubuntu@13.125.10.20
# EC2: ssh -i ~/Downloads/내키.pem ubuntu@13.125.10.20

sudo apt update && sudo apt -y upgrade
sudo timedatectl set-timezone Asia/Seoul
```

**메모리 1 GB 인스턴스면 스왑 2 GB** (빌드와 서버가 같이 돌 때 여유분. 권장):

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h   # Swap 줄에 2.0Gi가 보이면 됨
```

## 5. Docker 설치

Docker 공식 저장소에서 설치한다(<https://docs.docker.com/engine/install/ubuntu/>와 같은 내용).

```bash
sudo apt -y install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt update
sudo apt -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker ubuntu     # sudo 없이 docker를 쓰게
exit                               # 한 번 나갔다가 다시 ssh 접속해야 적용됨
```

다시 접속해서 `docker compose version`이 나오면 된다.

## 6. 코드 받기

```bash
git clone https://github.com/<조직>/<저장소>.git limbo
cd limbo
git checkout dev        # 배포할 브랜치
```

저장소가 비공개면 GitHub **Deploy key**(읽기 전용)를 쓴다: 인스턴스에서 `ssh-keygen -t ed25519 -f ~/.ssh/deploy -N ''` → `~/.ssh/deploy.pub` 내용을 저장소 **Settings → Deploy keys**에 추가 → `GIT_SSH_COMMAND='ssh -i ~/.ssh/deploy' git clone git@github.com:<조직>/<저장소>.git limbo`.

이미지에는 `dashboard/`와 `limbo/`의 지도·기본 waypoint만 들어간다(`dashboard/Dockerfile.dockerignore`). ROS 코드는 빌드에 쓰지 않는다.

## 7. 설정 파일 `.env` 만들기

```bash
cd ~/limbo/dashboard
cp .env.example .env
chmod 600 .env
nano .env
```

| 값 | 넣을 것 |
|---|---|
| `DOMAIN` | 도메인이 있으면 그 이름(DNS A 레코드를 고정 IP로). **없으면 sslip.io**: IP의 점을 `-`로 바꿔 `13-125-10-20.sslip.io` |
| `ADMIN_USERNAME` | 첫 관리자 아이디 (예: `admin`). 영문·숫자·`_.-` 3~32자 |
| `ADMIN_PASSWORD` | 첫 관리자의 **임시** 비밀번호(5자 이상). 첫 로그인 때 새 비밀번호로 바꾸게 된다. **작은따옴표로 감싸** 넣는다(`$` 같은 글자가 바뀌지 않게) |
| `ROBOT_TOKEN` | 로봇용 토큰. 아래 명령으로 만든다. **로봇 쪽에도 같은 값** |
| `MAP_YAML`, `INITIAL_WAYPOINTS` | 지도와 처음 waypoint 파일. 서로 맞는 짝으로(`.env.example` 주석) |

```bash
# 로봇 토큰
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

`ADMIN_USERNAME`·`ADMIN_PASSWORD`는 **사용자 DB에 계정이 하나도 없을 때(처음 시작)만** 쓰인다. 계정이 생긴 뒤에는 무시되므로, 첫 로그인을 마치면 `.env`에서 `ADMIN_PASSWORD` 줄을 지운다(남겨 두면 서버 로그에 `ADMIN_PASSWORD is ignored` 경고).

`.env` 예:

```bash
DOMAIN=13-125-10-20.sslip.io
ADMIN_USERNAME=admin
ADMIN_PASSWORD='temp-1234'
ROBOT_TOKEN=qH3v...43자쯤...
MAP_YAML=limbo/src/limbo_navigation/maps/aischool_2f_map.yaml
INITIAL_WAYPOINTS=aischool_waypoints.yaml
```

> **sslip.io란**: `13-125-10-20.sslip.io` 같은 이름을 물으면 그 안의 IP(13.125.10.20)를 그대로 돌려주는 공개 DNS다. 도메인을 사지 않아도 이름이 생겨서 Let's Encrypt 인증서를 받을 수 있다. 시험·과제용으로 충분하다. 오래 쓸 서비스면 도메인을 사서 쓴다.

## 8. 실행

```bash
cd ~/limbo/dashboard
docker compose up -d --build     # 처음 빌드는 2~5분 (이미지 내려받기가 대부분)
docker compose ps                # dashboard, caddy 둘 다 running
```

브라우저에서 `https://13-125-10-20.sslip.io/` → 로그인 화면 → 관제 화면. 처음 몇 초는 인증서 발급 중이라 접속이 안 될 수 있다.

### 첫 로그인과 다른 사람 계정

1. `.env`의 `ADMIN_USERNAME`·`ADMIN_PASSWORD`로 로그인한다
2. 「비밀번호 변경」 화면이 먼저 나온다. 임시 비밀번호와 새 비밀번호(5자 이상)를 넣는다. 바꾸기 전에는 관제 화면을 쓸 수 없다
3. 서버의 `.env`에서 `ADMIN_PASSWORD` 줄을 지운다(다시 쓰이지 않음. 서버를 다시 시작할 필요는 없다)
4. 다른 사람 계정은 화면 오른쪽 위 「회원 관리」에서 아이디·이름·임시 비밀번호로 만든다. 임시 비밀번호를 본인에게 따로 전달하면, 본인이 첫 로그인 때 바꾼다

**모든 계정이 관리자**다. 로그인한 사람은 누구나 로봇을 시작·정지·종료하고, 다른 계정을 만들고 지울 수 있다. 믿을 수 있는 사람에게만 계정을 만든다. 그만 쓰는 사람은 「사용 중지」나 「삭제」로 바로 끊는다(그 사람의 열린 화면도 30초 안에 로그인 창으로 돌아간다).

### 비밀번호를 잊었을 때

다른 관리자가 「회원 관리」 → 「비밀번호 초기화」로 임시 비밀번호를 정해 준다. 관리자 모두 잊었으면 인스턴스에서 직접 다시 설정한다(서버가 켜져 있어도 된다. 비밀번호는 화면에 보이지 않게 두 번 묻는다):

```bash
cd ~/limbo/dashboard
docker compose exec dashboard python -m server.users list           # 계정 목록
docker compose exec dashboard python -m server.users passwd admin   # 다시 설정 (그 계정의 로그인은 모두 끊김, 사용 중지였으면 다시 사용)
```

## 9. 로그 보기·멈추기·다시 켜기

```bash
docker compose logs -f dashboard   # 서버 로그 (Ctrl+C로 보기만 끝냄, 서버는 계속 돎)
docker compose logs -f caddy       # 인증서 발급·접속 로그
docker compose restart dashboard   # 서버만 다시 시작 (관제 상태·알림은 초기화, waypoint·계정·로그인은 남음)
docker compose down                # 모두 멈춤 (볼륨=waypoint·계정·인증서는 남음)
docker compose up -d               # 다시 켬
```

`restart: unless-stopped`이므로 인스턴스를 재부팅해도 자동으로 다시 뜬다.

## 10. 업데이트

```bash
cd ~/limbo && git pull
cd dashboard && docker compose up -d --build --force-recreate
docker image prune -f              # 예전 이미지 정리 (디스크 절약)
```

`--force-recreate`를 빼면 안 된다. `Caddyfile`은 파일을 컨테이너에 연결(bind mount)해서 쓰므로, `git pull`로 바뀌어도 `up -d --build`만으로는 Caddy 컨테이너가 다시 만들어지지 않고 **예전 설정으로 계속 돈다**. 인증서는 `caddy_data` 볼륨에 있으므로 다시 만들어도 재발급되지 않는다.

화면에서 편집한 waypoint와 계정(사용자 DB)은 볼륨(`dashboard_waypoints`)에 있어서 업데이트해도 남는다.

### basic auth를 쓰던 서버를 처음 올릴 때 (2026-11-12, 변경 기록 76)

76부터 Caddy의 basic auth(공유 아이디 하나)가 없어지고 관제 서버의 계정 로그인으로 바뀌었다. 예전 `.env`(`BASIC_AUTH_USER`·`BASIC_AUTH_HASH`만 있음) 그대로 올리면 **dashboard 컨테이너가 시작하지 않는다**(계정이 없는데 첫 관리자 값도 없음. 로그에 `RuntimeError: No dashboard users yet`).

```bash
cd ~/limbo && git pull
cd dashboard && nano .env
#   BASIC_AUTH_USER, BASIC_AUTH_HASH 줄을 지우고 아래 두 줄을 넣는다
#   ADMIN_USERNAME=admin
#   ADMIN_PASSWORD='임시비밀번호'
docker compose up -d --build --force-recreate      # Caddyfile이 바뀌었으므로 --force-recreate 꼭
docker compose logs dashboard | grep "first admin created"
```

그다음 8절 「첫 로그인과 다른 사람 계정」대로 한다. waypoint 볼륨은 그대로 쓰므로 편집한 경로는 남는다.

**서버와 로봇 Bridge는 같이 업데이트**한다(텔레메트리 v3 기준. 새 Bridge는 옛 서버에 거절되고, 옛 Bridge에는 주행 시작·순찰 종료가 잠긴다). 서버를 먼저 올린다.

## 11. waypoint·계정 백업·되돌리기·지도 바꾸기

```bash
docker compose cp dashboard:/data/waypoints.yaml ./waypoints-backup-$(date +%F).yaml   # 백업
docker compose cp ./waypoints-backup-2026-11-06.yaml dashboard:/data/waypoints.yaml    # 되돌리기
docker compose restart dashboard
```

계정(사용자 DB)도 같은 볼륨의 `/data/users.db`에 있다. 백업·되돌리기 모두 **서버가 켜진 채로** SQLite의 백업 기능을 쓴다. 파일을 그냥 복사하거나 덮어쓰면 옆의 `users.db-wal`(아직 반영 안 된 변경)과 어긋나 내용이 빠지거나 DB가 깨질 수 있다:

```bash
# 백업 (비밀번호는 해시만 들어 있음)
docker compose exec dashboard python -c "import sqlite3; sqlite3.connect('/data/users.db').backup(sqlite3.connect('/tmp/users-backup.db'))"
docker compose cp dashboard:/tmp/users-backup.db ./users-backup-$(date +%F).db
# 되돌리기 (지금 계정이 백업 시점으로 바뀌고, 로그인도 백업 시점 것만 남는다)
docker compose cp ./users-backup-2026-11-12.db dashboard:/tmp/users-restore.db
docker compose exec dashboard python -c "import sqlite3; sqlite3.connect('/tmp/users-restore.db').backup(sqlite3.connect('/data/users.db'))"
docker compose exec dashboard python -m server.users list
```

`INITIAL_WAYPOINTS`는 **`/data/waypoints.yaml`이 없을 때(처음)만** 복사된다. 지도를 다른 장소로 바꿀 때는 `.env`의 `MAP_YAML`·`INITIAL_WAYPOINTS`를 고치고 **waypoint 파일만** 지운다. 볼륨을 통째로 지우면(`docker volume rm dashboard_waypoints`) **계정도 모두 지워지므로** 그렇게 하지 않는다:

```bash
# 편집한 waypoint가 지워진다. 먼저 위처럼 백업
docker compose exec dashboard rm /data/waypoints.yaml
docker compose up -d --force-recreate    # 다시 시작하며 새 INITIAL_WAYPOINTS를 복사
```

새 지도 파일은 저장소의 `limbo/src/limbo_navigation/maps/`에 커밋된 것만 이미지에 들어간다(새 지도를 추가했으면 `git pull` 후 `--build`).

## 12. 로봇(Bridge) 연결

로봇 컴퓨터(PC 또는 Jetson)에서, 저장소 루트 기준:

```bash
# 1) 토큰 파일 (서버 .env의 ROBOT_TOKEN과 같은 값). relay_prog/state/는 git에서 제외됨
mkdir -p relay_prog/state
nano relay_prog/state/robot_token        # 토큰 한 줄 붙여 넣고 저장
chmod 600 relay_prog/state/robot_token
```

`relay_prog/src/limbo_telemetry_bridge/config/bridge.yaml`:

```yaml
server_url: https://13-125-10-20.sslip.io    # 경로·끝 슬래시 없이
token_file: relay_prog/state/robot_token
source_clock: ros_system                      # 실물 로봇. 시뮬레이션이면 ros_sim
patrol_launch:
  use_sim_time: false                         # 실물 로봇. 시뮬레이션이면 true
```

**시계 두 값은 로봇 종류에 맞춘다.** 서버(AWS)와는 상관없다.

| 로봇 | `source_clock` | `patrol_launch.use_sim_time` |
|---|---|---|
| Gazebo 시뮬레이션 (PC에서 시험) | `ros_sim` | `true` |
| 실물 로봇 | `ros_system` | `false` |

틀리면 Bridge는 연결되지만 **지도에 로봇 위치가 안 뜬다**(화면 "로봇 위치 수신 대기"). Bridge는 위치(TF)가 1초 안 것일 때만 보내는데, 시뮬레이션 시각을 실제 시계로 재면 아주 오래된 것으로 보이기 때문이다. 주행 시작한 순찰 노드도 Nav2와 시계가 달라 제대로 돌지 않는다.

그 뒤 Bridge를 다시 시작한다(`relay_prog/README.md` 「실행과 종료」). 로봇은 서버의 443으로 **나가는** 연결만 쓴다. 로봇 쪽 공유기·방화벽에 포트를 열 필요가 없다.

> 로봇 쪽 `bridge.yaml`은 git으로 관리되는 파일이다. 서버 주소를 커밋하지 않으려면 `bridge.yaml`을 복사한 별도 파일(예: `relay_prog/state/bridge.yaml`)을 만들어 `--config`로 지정한다.

## 13. 정상 동작 확인 체크리스트

인스턴스에서:
- [ ] `docker compose ps`: dashboard·caddy `running`
- [ ] `docker compose logs dashboard`에 `RuntimeError`가 없고 `Uvicorn running on http://0.0.0.0:8000`
- [ ] `docker compose logs caddy`에 `certificate obtained successfully`

내 PC에서:
- [ ] `curl -I http://13-125-10-20.sslip.io/` → `308`(https로 이동)
- [ ] `curl -s -o /dev/null -w "%{http_code}\n" https://13-125-10-20.sslip.io/api/v1/state` → `401`(로그인 필요)
- [ ] `curl -s -o /dev/null -w "%{http_code}\n" https://13-125-10-20.sslip.io/` → `200`(화면 파일. 로그인 창이 뜬다)
- [ ] `curl -s -o /dev/null -w "%{http_code}\n" -X POST -H 'content-type: application/json' -d '{}' https://13-125-10-20.sslip.io/api/v1/telemetry` → `401`(토큰 없음)
- [ ] `curl -s https://13-125-10-20.sslip.io/healthz` → `{"status":"ok"}`
- [ ] `nc -zv 13.125.10.20 8000` → 연결 실패(8000이 밖으로 안 열림)
- [ ] 브라우저 로그인(처음이면 비밀번호 변경) → 관제 화면·지도·waypoint 목록이 보이고, 오른쪽 위에 내 아이디와 「회원 관리」
- [ ] `docker compose logs dashboard | grep audit`에 `login 아이디 from ...`

로봇을 연결한 뒤:
- [ ] Bridge 로그 `transport=connected`, `commands=connected` (`http_401`이면 토큰 불일치)
- [ ] 화면 맨 위 `정상`, 순찰 카드·지도 위 로봇 위치가 보임
- [ ] waypoint 하나 이름 변경 → 주행 시작 → "순찰 시작 확인됨" → 로봇의 `relay_prog/state/waypoints/dashboard_waypoints.yaml`에 바뀐 이름
- [ ] 일시정지 → "정지 상태 확인됨", 재개 → "재개 확인됨", 순찰 종료 → "순찰 종료 확인됨"
- [ ] Bridge 로그에 `TimeoutError`가 자주 보이지 않음 (아래 문제 해결)

## 14. 문제 해결

| 증상 | 확인 |
|---|---|
| 브라우저가 접속을 못 함 / 인증서 오류 | 방화벽 80·443이 열렸나, `DOMAIN`이 고정 IP와 맞나(`dig +short 13-125-10-20.sslip.io`). `docker compose logs caddy` |
| `docker compose up`이 `ROBOT_TOKEN을 .env에 넣으세요` | `.env` 값이 비었음. `dashboard/` 안에서 실행했나 |
| dashboard가 계속 다시 시작, 로그에 `No dashboard users yet` | 계정이 하나도 없는데 `.env`에 `ADMIN_USERNAME`·`ADMIN_PASSWORD`가 없음. 넣고 `docker compose up -d` (10절 「basic auth를 쓰던 서버」) |
| 로그에 `ADMIN_USERNAME/ADMIN_PASSWORD rejected` | 아이디가 영문·숫자·`_.-` 3~32자가 아니거나 비밀번호가 5자 미만 |
| 첫 관리자 비밀번호가 `.env`와 다르게 들어간 듯함 | 값을 작은따옴표로 감쌌나(`$` 뒤가 사라짐). 이미 계정이 생겼으면 `.env`를 고쳐도 소용없다. `docker compose exec dashboard python -m server.users passwd admin` |
| 로그인하면 「아이디 또는 비밀번호가 맞지 않습니다」 | 사용 중지된 계정도 같은 문구다. 다른 관리자가 「회원 관리」에서 확인, 또는 위 `passwd` 명령 |
| 「로그인 실패가 많아 잠시 막혔습니다」 | 같은 IP·아이디로 5분에 10번 틀림. 5분 기다린다(서버를 다시 시작해도 풀림) |
| 쓰던 중 로그인 창으로 돌아감 | 12시간 아무것도 안 했거나 로그인 후 7일, 또는 다른 관리자가 사용 중지·비밀번호 초기화함. 다시 로그인 |
| 화면이 502 | dashboard 컨테이너가 죽음. `docker compose logs dashboard` (토큰 16자 미만, `MAP_YAML` 오타 등은 이유를 출력함) |
| Bridge `http_401` / `server rejected the robot token` | 로봇 `robot_token` 파일과 서버 `ROBOT_TOKEN`이 다름(앞뒤 공백은 무시됨) |
| 일시정지는 되는데 주행 시작만 `응답 없음`, Bridge 로그에 `commands=invalid_command` | 로봇의 Bridge가 2026-11-06 (71) 이전 코드다(앞단이 압축한 start 명령을 못 읽음). 로봇에서 `git pull` 후 Bridge 다시 시작 |
| Bridge는 연결됐는데 지도에 로봇 위치가 안 뜸("로봇 위치 수신 대기") | 시뮬레이션인데 `source_clock: ros_system`이면 위치가 버려진다(12절 표). 실물이면 AMCL이 위치를 잡았는지(RViz 초기 위치, `ros2 topic echo /amcl_pose --once`) |
| Bridge `TimeoutError`가 자주 | 텔레메트리 요청 제한이 1초(`request_timeout_s`)다. 로봇 쪽 인터넷이 느리거나 끊김. 같은 지역(서울) 인스턴스인지, 로봇 네트워크 확인 |
| 빌드가 `JavaScript heap out of memory`(exit code 134)로 실패 | 2026-11-07 (72) 이전 코드다. rollup 4.64가 이 화면 빌드에 메모리 약 3 GB를 썼다. `git pull`로 받은 뒤 다시 `docker compose up -d --build` |
| 빌드 중 멈추거나 `Killed` | 메모리 부족. 4절 스왑을 만들거나 2 GB 요금제로 |
| 디스크 부족 | `docker system df`, `docker image prune -f`, `docker builder prune -f` |

## 15. 보안 메모

- 로그인은 HTTPS 위에서만 안전하다. Caddy가 http를 https로 자동으로 보낸다. 로그인 쿠키는 HttpOnly·Secure·SameSite=Strict
- 비밀번호는 서버 DB에 scrypt 해시로만 저장된다. 비밀번호 기준이 5자로 짧으므로 쉬운 값(`admin1`, `12345`)은 쓰지 않는다. 틀린 로그인은 같은 IP·아이디로 5분에 10번까지만 받는다
- 첫 관리자 임시 비밀번호·토큰은 `.env`와 로봇의 `robot_token` 파일에만 둔다. git·채팅에 올리지 않는다. 첫 로그인 뒤 `.env`의 `ADMIN_PASSWORD`는 지운다
- 토큰이 새었으면: 새 토큰을 만들어 서버 `.env`와 로봇 파일을 바꾸고 `docker compose up -d`(서버) + Bridge 재시작
- 계정은 모두 관리자다. 로그인한 사람은 누구나 로봇을 시작·정지·종료하고 다른 계정을 만들고 지울 수 있다. 사람마다 계정을 따로 만들고, 그만 쓰는 사람은 바로 「사용 중지」·「삭제」한다. 누가 무엇을 했는지는 `docker compose logs dashboard | grep audit`
- 서버는 한 프로세스·메모리 상태다(`--workers 1` 고정). 재시작하면 관제 상태·알림은 초기화되고, waypoint·계정·로그인과 인증서는 볼륨에 남는다

## 16. 내 PC에서 먼저 시험하기 (선택)

Docker가 있는 PC에서 같은 구성을 띄워 볼 수 있다. `DOMAIN=localhost`이면 Caddy가 자체 인증서를 쓴다(브라우저가 경고하고, curl은 `-k`).

```bash
cd dashboard
cp .env.example .env    # DOMAIN=localhost, ADMIN_USERNAME·ADMIN_PASSWORD·토큰을 채움
docker compose up -d --build
curl -k -s -o /dev/null -w "%{http_code}\n" https://localhost/api/v1/state      # 401 (로그인 필요)
# 로그인해서 쿠키를 받고(처음이면 must_change_password: true) 그 쿠키로 다시 묻기
curl -k -s -c /tmp/limbo-cookie -H 'content-type: application/json' -d '{"username":"admin","password":"임시비밀번호"}' https://localhost/api/v1/auth/login
curl -k -s -o /dev/null -w "%{http_code}\n" -b /tmp/limbo-cookie https://localhost/api/v1/state   # 403 (비밀번호부터 바꿔야 함) 또는 200

# 가짜 텔레메트리 한 건을 로봇처럼 보낸다 (로그인 없이 토큰만): "accepted":true가 나오면 로봇 경로 정상
TOKEN=$(grep ^ROBOT_TOKEN= .env | cut -d= -f2)
.venv/bin/python -c "import json; from tools.sender import sample; print(json.dumps(sample()))" \
  | curl -k -s -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' --data @- https://localhost/api/v1/telemetry
docker compose down      # 계정은 볼륨에 남는다. 다 지우고 처음부터 하려면 docker compose down -v (waypoint·인증서도 지워짐)
```

### 시뮬레이션까지 한 PC에서 (실제 Bridge를 HTTPS로)

로봇과 똑같이 실제 Bridge가 `https://localhost`로 토큰을 들고 Caddy를 거쳐 붙게 하는 스크립트가 있다. 컨테이너를 켜고(없으면 빌드), Caddy 로컬 인증서를 Bridge가 믿게 하고(`SSL_CERT_FILE`), `.env`의 `ROBOT_TOKEN`을 `LIMBO_ROBOT_TOKEN`으로 넘겨 Bridge를 실행한다. 만든 설정은 `relay_prog/state/local_https/`(git 제외)에 둔다.

```bash
# 터미널 1: 시뮬레이션 (ROS_DOMAIN_ID=97)
limbo && ros_domain
ros2 launch limbo_bringup start_simulation.launch.py

# 터미널 2: Docker 서버 + Caddy + 실제 Bridge. 다른 도메인이면 ROS_DOMAIN_ID=번호 를 앞에 붙임
~/limbo_ros2_workspace/final_team7/dashboard/deploy/local_https_bridge.sh
```

브라우저는 `https://localhost`(처음이면 `.env`의 `ADMIN_USERNAME`·`ADMIN_PASSWORD`로 로그인 후 비밀번호 변경). `start_dashboard.launch.py`를 같이 켜면 Bridge가 둘이 되므로 스크립트가 거절한다. `Ctrl+C`는 Bridge와 순찰 노드만 끄고 컨테이너는 남긴다(`dashboard/`에서 `docker compose down`).

인스턴스에 올린 뒤에는 `-k` 없이 같은 명령이 되어야 한다. 반복해서 보내 보려면 `.venv/bin/python tools/sender.py --url https://<DOMAIN> --token <토큰>`(실제 인증서일 때만).
