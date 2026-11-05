"""HTTP GET으로 같은 JSON 계약을 받아 오는 공급원 (PRD FR-16). 폴링 스레드에서 호출되므로 UI를 막지 않는다."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .base import AdapterError

MAX_BYTES = 1_000_000


class HttpJsonAdapter:
    is_mock = False

    def __init__(self, url: str, timeout: float = 2.0):
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            raise ValueError(f"url은 http:// 또는 https://로 시작해야 합니다: {url!r}")
        self.url = url
        self.timeout = timeout

    def describe(self) -> str:
        return f"http:{self.url}"

    def read(self) -> dict:
        req = urllib.request.Request(self.url, headers={"Accept": "application/json",
                                                        "User-Agent": "automaton-signage"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read(MAX_BYTES + 1)
        except (urllib.error.URLError, OSError) as e:
            raise AdapterError(f"{self.url}: 요청 실패 ({e})") from e
        if len(body) > MAX_BYTES:
            raise AdapterError(f"{self.url}: 응답이 너무 큼")
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise AdapterError(f"{self.url}: JSON 형식 오류 ({e})") from e
        if not isinstance(data, dict):
            raise AdapterError(f"{self.url}: 최상위가 JSON 객체가 아님")
        return data
