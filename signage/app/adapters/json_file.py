"""로컬 JSON 스냅샷 파일 읽기 (PRD 5.2). bin_json / eco_json이 같이 쓴다."""

from __future__ import annotations

import json
import time
from pathlib import Path

from .base import AdapterError

MAX_BYTES = 1_000_000


class JsonFileAdapter:
    is_mock = False

    def __init__(self, path: Path, retries: int = 1, retry_delay: float = 0.05):
        self.path = path
        self.retries = retries
        self.retry_delay = retry_delay

    def describe(self) -> str:
        return f"json:{self.path}"

    def read(self) -> dict:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                if self.path.stat().st_size > MAX_BYTES:
                    raise AdapterError(f"{self.path.name}: 파일이 너무 큼 (> {MAX_BYTES} bytes)")
                with open(self.path, encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    raise AdapterError(f"{self.path.name}: 최상위가 JSON 객체가 아님")
                return data
            except FileNotFoundError as e:
                raise AdapterError(f"{self.path.name}: 파일 없음") from e
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                # 원자적 교체를 안 쓰는 생산자가 쓰는 도중일 수 있으니 한 번 더 읽어 본다
                last_error = e
                if attempt < self.retries:
                    time.sleep(self.retry_delay)
            except OSError as e:
                raise AdapterError(f"{self.path.name}: 읽기 실패 ({e})") from e
        raise AdapterError(f"{self.path.name}: JSON 형식 오류 ({last_error})")
