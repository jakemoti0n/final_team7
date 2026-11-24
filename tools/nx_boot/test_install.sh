#!/bin/bash
# install.sh 검사. 진짜 홈·진짜 systemd는 건드리지 않는다.
#  - HOME을 임시 폴더로 바꾼다
#  - PATH 맨 앞에 가짜 systemctl·loginctl(받은 인자를 로그에 적기만 함)을 둔다
# 실행: bash tools/nx_boot/test_install.sh
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd -P)"
INSTALL="$SRC_DIR/install.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
export HOME="$WORK/home"
export USER="tester"
mkdir -p "$HOME" "$WORK/bin"
LOG="$WORK/calls.log"
: > "$LOG"
export FAKE_LOG="$LOG"

# 가짜 systemctl: 인자 기록. is-enabled/is-active에는 그럴듯한 답
cat > "$WORK/bin/systemctl" <<'EOF'
#!/bin/bash
echo "systemctl $*" >> "$FAKE_LOG"
case "$2" in
    is-enabled) echo enabled ;;
    is-active)  echo inactive ;;
esac
exit 0
EOF
# 가짜 loginctl: linger는 꺼져 있고, sudo 없이 켜기는 실패하는 상황을 흉내
cat > "$WORK/bin/loginctl" <<'EOF'
#!/bin/bash
echo "loginctl $*" >> "$FAKE_LOG"
case "$1" in
    show-user)    echo no ;;
    enable-linger) exit 1 ;;
esac
exit 0
EOF
chmod +x "$WORK/bin/systemctl" "$WORK/bin/loginctl"
export PATH="$WORK/bin:$PATH"

BOOT_DIR="$HOME/.config/limbo/boot"
UNIT_DIR="$HOME/.config/systemd/user"
BOOT_FILES=(start ready.py corridor_pose.py map_search.py)
UNITS=(limbo-nx-drive.service limbo-nx-sensors.service limbo-nx-pose.service
       limbo-nx-navigation.service limbo-nx-dashboard.service)

PASS=0
ok()   { PASS=$((PASS + 1)); echo "  통과: $1"; }
fail() { echo "  실패: $1" >&2; exit 1; }
check() { local msg="$1"; shift; if "$@"; then ok "$msg"; else fail "$msg"; fi; }

# 링크 9개가 모두 저장소 파일을 가리키는지
links_ok() {
    local f u
    for f in "${BOOT_FILES[@]}"; do
        [[ -L "$BOOT_DIR/$f" && "$(readlink "$BOOT_DIR/$f")" == "$SRC_DIR/boot/$f" ]] || return 1
    done
    for u in "${UNITS[@]}"; do
        [[ -L "$UNIT_DIR/$u" && "$(readlink "$UNIT_DIR/$u")" == "$SRC_DIR/systemd/$u" ]] || return 1
    done
}
count_links() { find "$HOME/.config" -type l | wc -l; }
log_has() { grep -qxF -- "$1" "$LOG"; }

echo "[준비] 기존 일반 파일 하나(start)를 미리 둔다"
mkdir -p "$BOOT_DIR"
echo "old start" > "$BOOT_DIR/start"

echo "[1] 설치"
bash "$INSTALL" > "$WORK/install1.out"
check "링크 9개가 저장소를 가리킴" links_ok
check "링크 개수가 정확히 9" test "$(count_links)" -eq 9
check "start 실행 권한(링크 대상)" test -x "$BOOT_DIR/start"
backup="$(ls "$BOOT_DIR"/start.bak_* 2>/dev/null | head -n 1)"
check "기존 start가 start.bak_<날짜>로 옮겨짐" test -n "$backup"
check "백업 내용이 원래 내용" grep -qx "old start" "$backup"
check "bridge-nx.yaml이 일반 파일로 복사됨" test -f "$HOME/.config/limbo/bridge-nx.yaml" -a ! -L "$HOME/.config/limbo/bridge-nx.yaml"
check "bridge-nx.yaml 내용이 예시와 같음" cmp -s "$HOME/.config/limbo/bridge-nx.yaml" "$SRC_DIR/bridge-nx.example.yaml"
check "토큰 파일 안내가 출력됨" grep -q "robot_token" "$WORK/install1.out"
check "daemon-reload 호출" log_has "systemctl --user daemon-reload"
check "유닛 5개 enable 호출" log_has "systemctl --user enable ${UNITS[*]}"
check "start는 호출하지 않음" bash -c '! grep -qE "^systemctl --user (re)?start" "$1"' _ "$LOG"
check "enable-linger를 사용자 이름으로 호출" log_has "loginctl enable-linger tester"
check "linger 실패 시 sudo 안내 출력" grep -q "sudo loginctl enable-linger tester" "$WORK/install1.out"

echo "[2] 다시 설치(이미 있는 bridge-nx.yaml은 그대로, 새 백업 없음)"
echo "# 사람이 고친 줄" >> "$HOME/.config/limbo/bridge-nx.yaml"
cp "$HOME/.config/limbo/bridge-nx.yaml" "$WORK/bridge.before"
bash "$INSTALL" > "$WORK/install2.out"
check "링크 9개 유지" links_ok
check "bridge-nx.yaml을 덮어쓰지 않음" cmp -s "$HOME/.config/limbo/bridge-nx.yaml" "$WORK/bridge.before"
check "백업이 하나뿐(링크는 백업하지 않음)" test "$(find "$HOME/.config" -name '*.bak_*' | wc -l)" -eq 1

echo "[3] --check (아무것도 바꾸지 않음)"
find "$HOME" -printf '%p %y %l\n' | sort > "$WORK/tree.before"
: > "$LOG"
bash "$INSTALL" --check > "$WORK/check.out"
find "$HOME" -printf '%p %y %l\n' | sort > "$WORK/tree.after"
check "--check 뒤 파일 변화 없음" cmp -s "$WORK/tree.before" "$WORK/tree.after"
check "--check 출력에 링크 OK 9줄" test "$(grep -c '링크 OK' "$WORK/check.out")" -eq 9
check "--check 출력에 유닛 5개 enabled" test "$(grep -cE '^limbo-nx-.*\.service +enabled' "$WORK/check.out")" -eq 5
check "--check 출력에 linger 상태" grep -qx "linger: no" "$WORK/check.out"
check "--check 출력에 토큰 없음 표시" grep -qE "robot_token +없음" "$WORK/check.out"
check "--check가 enable·daemon-reload를 부르지 않음" bash -c '! grep -qE "^systemctl --user (enable|disable|daemon-reload)( |$)|^loginctl enable-linger" "$1"' _ "$LOG"

echo "[4] --uninstall"
touch "$HOME/.config/limbo/robot_token"
: > "$LOG"
bash "$INSTALL" --uninstall > "$WORK/uninstall.out"
check "링크 0개" test "$(count_links)" -eq 0
check "유닛 5개 disable 호출" log_has "systemctl --user disable ${UNITS[*]}"
check "bridge-nx.yaml 남아 있음" test -f "$HOME/.config/limbo/bridge-nx.yaml"
check "robot_token 남아 있음" test -f "$HOME/.config/limbo/robot_token"
check "백업 파일 남아 있음" test -f "$backup"
bash "$INSTALL" --check > "$WORK/check2.out"
check "제거 뒤 --check에 링크 OK 없음" bash -c '! grep -q "링크 OK" "$1"' _ "$WORK/check2.out"

echo "[5] 잘못된 옵션은 종료 코드 2"
set +e
bash "$INSTALL" --nope > /dev/null 2>&1
rc=$?
set -e
check "잘못된 옵션 종료 코드 2" test "$rc" -eq 2

echo "통과: 검사 ${PASS}개 모두 성공"
