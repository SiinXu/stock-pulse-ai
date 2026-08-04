from __future__ import annotations

from datetime import datetime

import pytest

from src.config import Config
from src.storage import DatabaseManager


@pytest.fixture()
def fixed_now() -> datetime:
    return datetime(2026, 8, 4, 12, 0, 0)


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "DATABASE_PATH",
        str(tmp_path / "skill-opinion-outcomes.db"),
    )
    Config.reset_instance()
    DatabaseManager.reset_instance()
    db = DatabaseManager.get_instance()
    try:
        yield db
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()
