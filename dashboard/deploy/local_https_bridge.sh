#!/bin/bash
# 내 PC에서 AWS와 같은 구성으로 시험하기 (docs/AWS_DEPLOY.md 16절)
#   Docker의 관제 서버 + Caddy(HTTPS·basic auth)를 켜고,
#   실제 Bridge를 https://localhost 로 로봇 토큰을 들고 붙인다.
# 먼저 시뮬레이션을 같은 ROS_DOMAIN_ID(기본 97)로 켜 둔다. 어느 폴더에서 실행해도 된다:
#   dashboard/deploy/local_https_bridge.sh
# Ctrl+C: Bridge와 Bridge가 띄운 순찰 노드가 꺼진다. 컨테이너는 남는다(끄기: dashboard/에서 docker compose down)
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
DASH=$ROOT/dashboard
WORK=$ROOT/relay_prog/state/local_https      # git에 안 올라감(.gitignore의 relay_prog/state/)
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-97}

fail() { echo "오류: $*" >&2; exit 1; }
env_value() { grep -E "^$1=" "$DASH/.env" | tail -1 | cut -d= -f2- | sed -e "s/^'//" -e "s/'$//" -e 's/^"//' -e 's/"$//'; }

# 1. 준비물 확인
[ -f "$DASH/.env" ] || fail "dashboard/.env가 없습니다. dashboard/.env.example을 복사해 DOMAIN=localhost, 해시, 토큰을 채우세요 (AWS_DEPLOY.md 7절)"
DOMAIN=$(env_value DOMAIN); TOKEN=$(env_value ROBOT_TOKEN); USER_NAME=$(env_value BASIC_AUTH_USER)
[ "$DOMAIN" = localhost ] || fail ".env의 DOMAIN이 '$DOMAIN'입니다. 이 스크립트는 로컬 시험용이라 DOMAIN=localhost여야 합니다"
[ -n "$TOKEN" ] || fail ".env의 ROBOT_TOKEN이 비어 있습니다"
docker info >/dev/null 2>&1 || fail "docker를 쓸 수 없습니다. Docker가 켜져 있는지, docker 그룹에 들어간 뒤 다시 로그인했는지 확인하세요"
for f in /opt/ros/jazzy/setup.bash "$ROOT/limbo/install/setup.bash" "$ROOT/relay_prog/install/setup.bash"; do
    [ -f "$f" ] || fail "$f 가 없습니다. 빌드를 먼저 하세요 (build_limbo, relay_prog colcon build)"
done
BRIDGE=$ROOT/relay_prog/install/limbo_telemetry_bridge/lib/limbo_telemetry_bridge/bridge
[ -x "$BRIDGE" ] || fail "Bridge 실행 파일이 없습니다: $BRIDGE"
# 실제 Bridge 프로세스만(python이 bridge 실행 파일을 돌리는 것). 그 문자열이 든 다른 셸 명령은 무시
if pgrep -f "^[^ ]*python[^ ]* [^ ]*/lib/limbo_telemetry_bridge/bridge( |$)" >/dev/null; then
    fail "이미 다른 Bridge가 돌고 있습니다(start_dashboard.launch.py 등). 그쪽을 Ctrl+C로 끄고 다시 실행하세요"
fi

# 2. 컨테이너 켜기 (이미지가 없으면 처음 한 번 빌드, 약 3분)
echo "== Docker 관제 서버 + Caddy 켜기"
(cd "$DASH" && docker compose up -d)
for i in $(seq 1 60); do
    curl -k -s -o /dev/null --fail https://localhost/healthz && break
    [ "$i" = 60 ] && fail "https://localhost/healthz 가 30초 안에 응답하지 않습니다. dashboard/에서 docker compose logs 를 보세요"
    sleep 0.5
done

# 3. Caddy 로컬 인증서를 믿게 하는 CA 묶음 + Bridge 설정(server_url만 https://localhost로)
mkdir -p "$WORK"
(cd "$DASH" && docker compose exec -T caddy cat /data/caddy/pki/authorities/local/root.crt) > "$WORK/caddy_root.crt" \
    || fail "Caddy 루트 인증서를 꺼내지 못했습니다"
cat /etc/ssl/certs/ca-certificates.crt "$WORK/caddy_root.crt" > "$WORK/ca.pem"
python3 - "$ROOT/relay_prog/src/limbo_telemetry_bridge/config/bridge.yaml" "$WORK/bridge.yaml" <<'EOF'
import sys, yaml
config = yaml.safe_load(open(sys.argv[1]))
config['server_url'] = 'https://localhost'
config['token_file'] = None          # 토큰은 환경 변수 LIMBO_ROBOT_TOKEN으로 넘긴다
yaml.safe_dump(config, open(sys.argv[2], 'w'), allow_unicode=True, sort_keys=False)
EOF

echo
echo "== 준비 완료"
echo "   화면:  https://localhost  (아이디 ${USER_NAME:-?}, 비밀번호는 해시를 만들 때 쓴 것. 인증서 경고는 '고급 → 계속')"
echo "   ROS_DOMAIN_ID=$ROS_DOMAIN_ID (시뮬레이션과 같아야 함)"
echo "   Bridge 설정: $WORK/bridge.yaml"
echo "   끄기: Ctrl+C (컨테이너는 남음, 끄려면 dashboard/에서 docker compose down)"
echo "== Bridge 시작"
echo

# 4. 실제 Bridge 실행 (저장소 루트 기준 상대 경로 규칙 때문에 루트에서)
cd "$ROOT"
export SSL_CERT_FILE=$WORK/ca.pem LIMBO_ROBOT_TOKEN=$TOKEN
set +u    # ROS setup 스크립트는 정의 안 된 변수를 읽는다
source /opt/ros/jazzy/setup.bash
source "$ROOT/limbo/install/setup.bash"
source "$ROOT/relay_prog/install/setup.bash"
exec "$BRIDGE" --config "$WORK/bridge.yaml"
