#!/bin/bash
# Orin NX 부팅 자동 기동(사용자 systemd 유닛 5개) 설치 스크립트.
#
# 쓰는 법(젯슨 안에서, sudo 없이):
#   bash tools/nx_boot/install.sh              # 설치(링크 + enable). 유닛 start는 하지 않음
#   bash tools/nx_boot/install.sh --check      # 아무것도 바꾸지 않고 상태만 표로 출력
#   bash tools/nx_boot/install.sh --uninstall  # 링크 제거 + 유닛 disable (bridge-nx.yaml·robot_token은 남김)
#
# 유닛이 %h/.config/limbo/boot/start 를 부르므로 실행 위치는 ~/.config/limbo/boot/ 이다.
# 그 자리에 저장소 파일을 가리키는 심볼릭 링크를 만들어서, 저장소를 pull 하면 바로 반영되게 한다.
# (스크립트 내용은 바로 바뀌지만, 이미 떠 있는 유닛은 재시작해야 새 내용으로 돈다.)
set -euo pipefail

# 이 스크립트가 있는 폴더(tools/nx_boot)를 기준으로 경로를 잡는다. 어디서 실행해도 같다.
SRC_DIR="$(cd "$(dirname "$0")" && pwd -P)"

BOOT_DIR="$HOME/.config/limbo/boot"
UNIT_DIR="$HOME/.config/systemd/user"
BRIDGE_FILE="$HOME/.config/limbo/bridge-nx.yaml"
TOKEN_FILE="$HOME/.config/limbo/robot_token"

BOOT_FILES=(start ready.py corridor_pose.py map_search.py)
UNITS=(limbo-nx-drive.service limbo-nx-sensors.service limbo-nx-pose.service
       limbo-nx-navigation.service limbo-nx-dashboard.service)

# 기존 일반 파일을 옮길 때 붙이는 꼬리표(같은 날 여러 번 돌려도 겹치지 않게 시각까지)
BACKUP_SUFFIX="bak_$(date +%Y%m%d-%H%M%S)"

# 링크 한 개 만들기: $1 = 저장소 파일, $2 = 링크를 만들 자리
link_one() {
    local src="$1" dest="$2"
    if [[ -L "$dest" ]]; then
        if [[ "$(readlink "$dest")" == "$src" ]]; then
            echo "  그대로   $dest"
            return
        fi
        # 다른 곳을 가리키는 링크는 내용이 아니라 가리키는 곳만 바뀌므로 백업 없이 바꾼다
        echo "  링크 교체 $dest (이전: $(readlink "$dest"))"
        ln -sfn "$src" "$dest"
        return
    fi
    if [[ -e "$dest" ]]; then
        if [[ -d "$dest" ]]; then
            echo "오류: $dest 가 폴더다. 직접 확인한 뒤 다시 실행할 것" >&2
            exit 1
        fi
        mv "$dest" "$dest.$BACKUP_SUFFIX"
        echo "  백업     $dest -> $dest.$BACKUP_SUFFIX"
    fi
    ln -s "$src" "$dest"
    echo "  링크     $dest -> $src"
}

# 링크 상태 한 줄: 링크 OK / 다른 곳 링크 / 일반 파일 / 없음
link_state() {
    local src="$1" dest="$2"
    if [[ -L "$dest" ]]; then
        if [[ "$(readlink "$dest")" == "$src" ]]; then
            if [[ -e "$dest" ]]; then echo "링크 OK"; else echo "링크 끊김"; fi
        else
            echo "다른 곳 링크($(readlink "$dest"))"
        fi
    elif [[ -e "$dest" ]]; then
        echo "일반 파일"
    else
        echo "없음"
    fi
}

linger_state() {
    loginctl show-user "$USER" -p Linger --value 2>/dev/null || echo "확인 실패"
}

do_install() {
    echo "[1/4] 스크립트 링크: $BOOT_DIR"
    mkdir -p "$BOOT_DIR"
    for f in "${BOOT_FILES[@]}"; do
        link_one "$SRC_DIR/boot/$f" "$BOOT_DIR/$f"
    done

    echo "[2/4] 유닛 링크: $UNIT_DIR"
    mkdir -p "$UNIT_DIR"
    for u in "${UNITS[@]}"; do
        link_one "$SRC_DIR/systemd/$u" "$UNIT_DIR/$u"
    done

    echo "[3/4] 관제 설정: $BRIDGE_FILE"
    if [[ -e "$BRIDGE_FILE" ]]; then
        echo "  이미 있음. 건드리지 않음"
    else
        # 사람이 고치는 파일이라 링크가 아니라 복사
        cp "$SRC_DIR/bridge-nx.example.yaml" "$BRIDGE_FILE"
        echo "  예시를 복사함. 내용(server_url·token_file 경로 등)을 이 보드에 맞게 확인할 것"
    fi
    if [[ ! -e "$TOKEN_FILE" ]]; then
        echo "  주의: 토큰 파일 $TOKEN_FILE 이 없다. 이 파일을 만들어야 limbo-nx-dashboard 유닛이 동작한다(git에 넣지 않음)"
    fi

    echo "[4/4] systemd 등록"
    if ! systemctl --user daemon-reload; then
        echo "오류: systemctl --user 가 실패했다. 젯슨에 그 사용자로 직접 로그인한 셸(사용자 세션)에서 다시 실행할 것" >&2
        exit 1
    fi
    systemctl --user enable "${UNITS[@]}"
    if [[ "$(linger_state)" == "yes" ]]; then
        echo "  linger 이미 켜져 있음(로그인 없이 부팅 때 뜸)"
    elif loginctl enable-linger "$USER"; then
        echo "  linger 켬(로그인 없이 부팅 때 뜸)"
    else
        echo "  안내: linger를 켜지 못했다(권한 부족). 관리자가 'sudo loginctl enable-linger $USER' 를 실행해야 로그인 없이 부팅 때 뜬다"
    fi

    echo
    echo "설치 끝. 유닛은 시작하지 않았다. 지금 켜려면:"
    echo "  systemctl --user start ${UNITS[*]%.service}"
    echo "이미 떠 있던 유닛은 재시작해야 새 내용이 적용된다:"
    echo "  systemctl --user restart ${UNITS[*]%.service}"
}

do_check() {
    printf '%-48s %s\n' "자리" "상태"
    printf '%-48s %s\n' "----" "----"
    for f in "${BOOT_FILES[@]}"; do
        printf '%-48s %s\n' "$BOOT_DIR/$f" "$(link_state "$SRC_DIR/boot/$f" "$BOOT_DIR/$f")"
    done
    for u in "${UNITS[@]}"; do
        printf '%-48s %s\n' "$UNIT_DIR/$u" "$(link_state "$SRC_DIR/systemd/$u" "$UNIT_DIR/$u")"
    done
    for f in "$BRIDGE_FILE" "$TOKEN_FILE"; do
        if [[ -e "$f" ]]; then s="있음"; else s="없음"; fi
        printf '%-48s %s\n' "$f" "$s"
    done
    echo
    printf '%-30s %-12s %s\n' "유닛" "enabled" "active"
    printf '%-30s %-12s %s\n' "----" "-------" "------"
    for u in "${UNITS[@]}"; do
        e="$(systemctl --user is-enabled "$u" 2>/dev/null || true)"
        a="$(systemctl --user is-active "$u" 2>/dev/null || true)"
        printf '%-30s %-12s %s\n' "$u" "${e:-확인 실패}" "${a:-확인 실패}"
    done
    echo
    echo "linger: $(linger_state)"
}

do_uninstall() {
    echo "[1/3] 유닛 disable(떠 있는 유닛은 내리지 않음)"
    systemctl --user disable "${UNITS[@]}" || echo "  안내: disable 일부 실패. 'systemctl --user status limbo-nx-*' 로 확인할 것"

    echo "[2/3] 링크 제거(저장소를 가리키는 링크만. 일반 파일·백업은 남김)"
    for f in "${BOOT_FILES[@]}"; do
        remove_link "$SRC_DIR/boot/$f" "$BOOT_DIR/$f"
    done
    for u in "${UNITS[@]}"; do
        remove_link "$SRC_DIR/systemd/$u" "$UNIT_DIR/$u"
    done

    echo "[3/3] systemd 다시 읽기"
    systemctl --user daemon-reload || echo "  안내: daemon-reload 실패"
    echo
    echo "제거 끝. $BRIDGE_FILE 와 $TOKEN_FILE 은 남겨 두었다."
    echo "떠 있는 유닛을 내리려면: systemctl --user stop ${UNITS[*]%.service}"
}

remove_link() {
    local src="$1" dest="$2"
    if [[ -L "$dest" && "$(readlink "$dest")" == "$src" ]]; then
        rm "$dest"
        echo "  제거     $dest"
    else
        echo "  건너뜀   $dest ($(link_state "$src" "$dest"))"
    fi
}

case "${1:-}" in
    "")          do_install ;;
    --check)     do_check ;;
    --uninstall) do_uninstall ;;
    *)
        echo "쓰는 법: bash $0 [--check | --uninstall]" >&2
        exit 2
        ;;
esac
