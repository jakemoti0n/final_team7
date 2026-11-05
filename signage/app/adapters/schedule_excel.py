"""Excel 행사 일정 읽기 (PRD 4절). 파일이 바뀌었을 때(수정시각·크기)만 다시 파싱한다."""

from __future__ import annotations

import logging
from datetime import tzinfo
from pathlib import Path

from ..schedule import ParseResult, ScheduleFileError, parse_rows
from ..util import file_signature

log = logging.getLogger("signage.schedule")


class ExcelScheduleAdapter:
    def __init__(self, path: Path, sheet: str, tz: tzinfo):
        self.path = path
        self.sheet = sheet
        self.tz = tz
        self._sig: tuple[int, int] | None = None
        self._cached: ParseResult | None = None

    def describe(self) -> str:
        return f"excel:{self.path}#{self.sheet}"

    def read(self) -> tuple[ParseResult, bool]:
        """(결과, 이번에 새로 읽었는지). 실패하면 ScheduleFileError (호출 측이 마지막 정상값 유지)."""
        sig = file_signature(self.path)
        if sig is None:
            raise ScheduleFileError(f"{self.path.name}: 파일 없음/접근 불가")
        if sig == self._sig and self._cached is not None:
            return self._cached, False
        result = self._parse()
        if file_signature(self.path) != sig:
            # 읽는 사이에 저장이 일어났다: 이번 결과는 버리고 다음 주기에 다시 읽는다
            raise ScheduleFileError(f"{self.path.name}: 읽는 중 파일이 바뀜 (다시 시도)")
        self._sig, self._cached = sig, result
        return result, True

    def _parse(self) -> ParseResult:
        import openpyxl  # 앱 시작 시간을 줄이려고 지연 import

        try:
            wb = openpyxl.load_workbook(self.path, read_only=True, data_only=True)
        except Exception as e:  # BadZipFile, InvalidFileException, PermissionError ...
            raise ScheduleFileError(f"{self.path.name}: 열 수 없음 ({type(e).__name__}: {e})") from e
        try:
            if self.sheet not in wb.sheetnames:
                raise ScheduleFileError(f"{self.path.name}: '{self.sheet}' 시트 없음")
            rows = wb[self.sheet].iter_rows(values_only=True)
            header = next(rows, None)
            return parse_rows(header, rows, self.tz)
        except ScheduleFileError:
            raise
        except Exception as e:
            raise ScheduleFileError(f"{self.path.name}: 읽기 오류 ({type(e).__name__}: {e})") from e
        finally:
            wb.close()
