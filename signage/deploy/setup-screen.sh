#!/usr/bin/env bash
# 로봇 하단 화면이 꺼지거나 잠기지 않게 (GNOME, Ubuntu 24.04 기본 데스크톱). 로그인한 사용자로 한 번 실행한다. sudo 필요 없음
#
#   ./setup-screen.sh          화면 끄기·잠금·절전을 끈다
#   ./setup-screen.sh --undo   기본값으로 되돌린다
set -euo pipefail

if ! command -v gsettings >/dev/null 2>&1; then
  echo "gsettings가 없습니다(GNOME이 아님). 데스크톱 설정에서 화면 끄기·잠금을 직접 끈다" >&2
  exit 1
fi

settings=(
  "org.gnome.desktop.session idle-delay uint32 0"                                 # 쓰지 않을 때 화면 끄기: 안 함
  "org.gnome.desktop.screensaver lock-enabled false"                              # 화면 잠금: 안 함
  "org.gnome.desktop.screensaver idle-activation-enabled false"
  "org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing'"     # 전원 연결 중 절전: 안 함
  "org.gnome.settings-daemon.plugins.power idle-dim false"                        # 화면 어둡게: 안 함
  "org.gnome.desktop.notifications show-banners false"                            # 알림 배너가 화면을 가리지 않게
)

for line in "${settings[@]}"; do
  read -r schema key value <<<"$line"
  if ! gsettings list-keys "$schema" 2>/dev/null | grep -qx "$key"; then
    echo "건너뜀 (이 시스템에 없음): $schema $key"
    continue
  fi
  if [ "${1:-}" = "--undo" ]; then
    gsettings reset "$schema" "$key"
    echo "되돌림: $schema $key = $(gsettings get "$schema" "$key")"
  else
    gsettings set "$schema" "$key" "$value"
    echo "설정: $schema $key = $(gsettings get "$schema" "$key")"
  fi
done

# X11 세션이면 X의 화면 보호기·DPMS도 끈다 (Wayland에서는 위 설정으로 충분)
if [ "${XDG_SESSION_TYPE:-}" = "x11" ] && command -v xset >/dev/null 2>&1 && [ "${1:-}" != "--undo" ]; then
  xset s off -dpms && echo "설정: xset s off -dpms (다시 로그인하면 풀린다. 위 GNOME 설정이 그 뒤를 맡는다)"
fi
