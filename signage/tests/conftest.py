import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TZ = ZoneInfo("Asia/Seoul")

# 원본 Excel 템플릿 (예시 행 하나, enabled=N). 시험은 data/events.xlsx가 아니라 이것을 쓴다.
# data/events.xlsx는 운영자가 일정을 넣는 파일이라 내용이 바뀔 수 있다.
TEMPLATE_XLSX = ROOT / "docs/Automaton_행사일정_Excel_템플릿.xlsx"


def kst(*args) -> datetime:
    return datetime(*args, tzinfo=TZ)


@pytest.fixture
def project(tmp_path) -> Path:
    """signage/의 설정·콘텐츠·데이터를 임시 디렉터리에 복사한 프로젝트 루트.

    data/events.xlsx만은 원본 템플릿으로 바꿔 넣는다 (활성 행사 없음)."""
    for name in ("config", "content", "assets", "data"):
        shutil.copytree(ROOT / name, tmp_path / name)
    shutil.copyfile(TEMPLATE_XLSX, tmp_path / "data/events.xlsx")  # 운영 일정과 무관하게
    return tmp_path


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])
