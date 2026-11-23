#!/usr/bin/env bash
# 로봇 하단 디스플레이(/display)를 브라우저 키오스크로 띄운다. PRD v0.3 (signage/docs/PRD_로봇_하단_디스플레이_v0.3.md)
#
#   ./display-kiosk.sh            서버에 접속될 때까지 기다렸다가 전체 화면으로 띄운다 (systemd가 부른다)
#   ./display-kiosk.sh --print    띄울 명령만 보여 준다 (기다리지 않음)
#
# 설정은 같은 폴더의 display-kiosk.env (다른 파일이면 DISPLAY_KIOSK_ENV=/경로). 설치는 signage/README.md 「로봇 하단 화면 키오스크」
set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
env_file=${DISPLAY_KIOSK_ENV:-$here/display-kiosk.env}
if [ -f "$env_file" ]; then
  # shellcheck disable=SC1090
  . "$env_file"
fi
: "${DISPLAY_URL:?DISPLAY_URL이 없습니다 ($env_file)}"
BROWSER=${BROWSER:-}
EXTRA_FLAGS=${EXTRA_FLAGS:-}

if [ -z "$BROWSER" ]; then
  for name in chromium chromium-browser google-chrome google-chrome-stable; do
    if command -v "$name" >/dev/null 2>&1; then BROWSER=$(command -v "$name"); break; fi
  done
fi
if [ -z "$BROWSER" ]; then
  echo "브라우저가 없습니다. Jetson(Ubuntu 24.04)은 'sudo snap install chromium'" >&2
  exit 1
fi

# 이 화면 전용 브라우저 프로필 (평소 쓰는 브라우저와 섞이지 않게). snap 브라우저는 홈의 숨김 폴더에 쓰지 못한다
# (/snap/bin/chromium은 /usr/bin/snap을 가리키는 링크, apt의 chromium-browser는 snap을 부르는 껍데기)
is_snap() {
  case "$BROWSER" in /snap/*) return 0 ;; esac
  # /usr/bin/snap 자체도 snapd로 가는 링크일 수 있어 양쪽을 끝까지 따라가 비교한다
  [ -e /usr/bin/snap ] && [ "$(readlink -f "$BROWSER")" = "$(readlink -f /usr/bin/snap)" ] && return 0
  [ "$(basename "$BROWSER")" = chromium-browser ] && command -v snap >/dev/null 2>&1 && snap list chromium >/dev/null 2>&1 && return 0
  return 1
}
if is_snap; then
  profile=$HOME/snap/chromium/common/limbo-display
else
  profile=${XDG_DATA_HOME:-$HOME/.local/share}/limbo-display-browser
fi

flags=(
  --kiosk                                   # 전체 화면, 주소창·탭 없음, 나갈 방법 없음
  --user-data-dir="$profile"
  --autoplay-policy=no-user-gesture-required   # 「지나갑니다」 소리를 화면을 누르지 않아도 튼다
  --no-first-run --no-default-browser-check
  --noerrdialogs --disable-session-crashed-bubble --disable-infobars
  --disable-features=Translate,TranslateUI
  --disable-pinch --overscroll-history-navigation=0   # 손가락으로 확대·뒤로 가기가 되지 않게
  --password-store=basic                    # 키링 잠금 해제 창이 뜨지 않게
  --check-for-update-interval=31536000
  --ozone-platform-hint=auto                # Wayland(Ubuntu 24.04 기본)·X11 둘 다
)
# shellcheck disable=SC2206
[ -n "$EXTRA_FLAGS" ] && flags+=($EXTRA_FLAGS)

if [ "${1:-}" = "--print" ]; then
  printf '%q ' "$BROWSER" "${flags[@]}" "$DISPLAY_URL"
  echo
  exit 0
fi

# 부팅 직후 네트워크가 붙기 전에 띄우면 브라우저가 오류 페이지에 멈춘다. 서버가 화면을 내줄 때까지 기다린다.
# (한 번 뜬 뒤에 끊기는 것은 화면이 3초마다 다시 시도하므로 괜찮다)
waited=0
until curl -fs -o /dev/null --max-time 5 "$DISPLAY_URL"; do   # 실패 이유는 30초마다 아래 한 줄로만
  if [ $((waited % 30)) -eq 0 ]; then
    echo "서버를 기다리는 중 (${waited}s): $DISPLAY_URL — 네트워크, 서버의 VISITOR_ENABLED=true를 확인" >&2
  fi
  sleep 5
  waited=$((waited + 5))
done

# 전원이 그냥 꺼졌다 켜졌을 때 「Chrome이 제대로 종료되지 않았습니다」 복원 창이 뜨지 않게
prefs=$profile/Default/Preferences
if [ -f "$prefs" ]; then
  sed -i 's/"exited_cleanly":false/"exited_cleanly":true/; s/"exit_type":"[^"]*"/"exit_type":"Normal"/' "$prefs"
fi

echo "띄움: $DISPLAY_URL ($BROWSER)" >&2
exec "$BROWSER" "${flags[@]}" "$DISPLAY_URL"
