#!/usr/bin/env bash
# Build the pinned Jazzy-compatible STVL overlay; no sudo or robot launch.
set -eo pipefail
_here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
_ws=${LIMBO_STVL_WS:-$HOME/limbo_stvl_compat}
_src="$_ws/src/stvl"
_base=f37544ef1b2b21623eacb0808c69b4cf912ac30f
mkdir -p "$_ws/src"
if [[ ! -e "$_src/.git" ]]; then
  git clone --branch 2.5.5 --depth 1 https://github.com/SteveMacenski/spatio_temporal_voxel_layer.git "$_src"
fi
[[ $(git -C "$_src" rev-parse HEAD) == "$_base" ]] || {
  echo 'STVL source is not the reviewed 2.5.5 commit; refusing to change it.' >&2; exit 1;
}
if git -C "$_src" apply --reverse --check "$_here/limbo_stvl_jazzy.patch" 2>/dev/null; then
  echo 'Reviewed compatibility patch is already applied.'
else
  git -C "$_src" diff --quiet || { echo 'Unrelated STVL edits found; review before building.' >&2; exit 1; }
  git -C "$_src" apply --check "$_here/limbo_stvl_jazzy.patch"
  git -C "$_src" apply "$_here/limbo_stvl_jazzy.patch"
fi
source /opt/ros/jazzy/setup.bash
cd "$_ws"
export MAKEFLAGS=-j1 CMAKE_BUILD_PARALLEL_LEVEL=1
colcon build --executor sequential --packages-select spatio_temporal_voxel_layer \
  --packages-ignore openvdb_vendor --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  '-DCMAKE_CXX_FLAGS_RELWITHDEBINFO=-O1 -g1 -DNDEBUG' \
  -DBUILD_TESTING=OFF -DSTVL_BUILD_GEOMETRY_TESTS=ON
source install/local_setup.bash
./build/spatio_temporal_voxel_layer/test_limbo_lidar_frustum
readelf -d install/spatio_temporal_voxel_layer/lib/libspatio_temporal_voxel_layer_core.so | grep -q NODELETE
python3 - "$_ws" "$_here/limbo_stvl_jazzy.patch" "$_base" <<'PY'
from pathlib import Path
import hashlib,json,sys
ws=Path(sys.argv[1]);patch=Path(sys.argv[2])
lib=ws/'install/spatio_temporal_voxel_layer/lib/libspatio_temporal_voxel_layer_core.so'
data={'base_commit':sys.argv[3],'offset_upstream_commit':'4407b6ac42fe98a0a357b0ef81e50b8f481cef76',
      'patch_sha256':hashlib.sha256(patch.read_bytes()).hexdigest(),
      'library_sha256':hashlib.sha256(lib.read_bytes()).hexdigest(),
      'vertical_bounds':'offset +/- total_fov/2', 'linux_nodelete':True}
(ws/'install/limbo_stvl_compat.json').write_text(json.dumps(data,indent=2)+'\n')
print(json.dumps(data,indent=2))
PY
