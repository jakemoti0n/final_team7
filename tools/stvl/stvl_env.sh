#!/usr/bin/env bash
# Source AFTER ROS / Limbo / sensor overlays and BEFORE launching any Nav2 process.
_limbo_stvl_load() {
  local ws=${LIMBO_STVL_WS:-$HOME/limbo_stvl_compat}
  local prefix="$ws/install/spatio_temporal_voxel_layer"
  [[ -r "$ws/install/local_setup.bash" && -r "$ws/install/limbo_stvl_compat.json" ]] || {
    echo 'Verified STVL overlay missing. Run tools/stvl/build_stvl_compat.sh first.' >&2
    return 1
  }
  python3 - "$ws" <<'PY' || return 1
from pathlib import Path
import hashlib,json,sys
ws=Path(sys.argv[1]);m=json.loads((ws/'install/limbo_stvl_compat.json').read_text())
lib=ws/'install/spatio_temporal_voxel_layer/lib/libspatio_temporal_voxel_layer_core.so'
assert m['base_commit']=='f37544ef1b2b21623eacb0808c69b4cf912ac30f'
assert m['linux_nodelete'] and m['library_sha256']==hashlib.sha256(lib.read_bytes()).hexdigest(), 'STVL binary changed; rebuild and revalidate'
PY
  source "$ws/install/local_setup.bash" || return 1
  [[ $(ros2 pkg prefix spatio_temporal_voxel_layer) == "$prefix" ]] || {
    echo 'STVL overlay precedence is incorrect.' >&2; return 1;
  }
  export LIMBO_STVL_COMPAT_PREFIX="$prefix"
}
_limbo_stvl_load || return 1
unset -f _limbo_stvl_load
