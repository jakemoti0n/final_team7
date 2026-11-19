"""화면에서 고친 파일(waypoint·약도)을 저장하는 공통 규칙."""
import os
from pathlib import Path
import tempfile


def atomic_write(path, data, default_mode=0o644):
    """같은 폴더의 임시 파일에 다 쓴 뒤 바꿔치기. 중간에 끊겨도 원본이 반쯤 쓰인 채로 남지 않는다.
    기존 파일이 있으면 권한을 그대로 물려받고, 없으면 default_mode."""
    path = Path(path)
    mode = path.stat().st_mode & 0o777 if path.exists() else default_mode
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.stem}-", suffix=path.suffix, delete=False) as output:
            temp = Path(output.name)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
        temp = None
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
