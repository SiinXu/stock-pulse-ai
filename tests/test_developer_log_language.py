# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Guard English developer logs at the remediated API, Agent, Bot, and storage boundaries."""

from __future__ import annotations

import ast
from pathlib import Path
import re
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
SCOPED_DIRECTORIES = (
    REPO_ROOT / "api" / "middlewares",
    REPO_ROOT / "api" / "v1" / "endpoints",
    REPO_ROOT / "src" / "agent",
    REPO_ROOT / "bot",
)
SCOPED_FILES = (
    REPO_ROOT / "main.py",
    REPO_ROOT / "api" / "app.py",
    REPO_ROOT / "src" / "core" / "pipeline.py",
    REPO_ROOT / "src" / "logging_config.py",
    REPO_ROOT / "src" / "services" / "alphasift_service.py",
    REPO_ROOT / "src" / "services" / "image_stock_extractor.py",
    REPO_ROOT / "src" / "storage.py",
)
LOG_METHODS = {
    "debug",
    "info",
    "warning",
    "warn",
    "error",
    "exception",
    "critical",
}
CJK_TEXT = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def _is_logger_call(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute) or node.func.attr not in LOG_METHODS:
        return False
    owner = node.func.value
    if isinstance(owner, ast.Name):
        return "logger" in owner.id.lower() or owner.id == "logging"
    if isinstance(owner, ast.Attribute):
        return "logger" in owner.attr.lower()
    return False


def _literal_segments(node: ast.AST) -> Iterable[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node.value
    elif isinstance(node, ast.JoinedStr):
        for value in node.values:
            yield from _literal_segments(value)


def find_non_english_developer_logs(source: str) -> list[tuple[int, str]]:
    tree = ast.parse(source)
    failures: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_logger_call(node):
            continue
        text = " ".join(
            segment
            for argument in (*node.args, *(keyword.value for keyword in node.keywords))
            for segment in _literal_segments(argument)
        )
        if CJK_TEXT.search(text):
            failures.append((node.lineno, text))
    return sorted(failures)


def _remediated_log_boundaries() -> list[Path]:
    files = {
        path
        for directory in SCOPED_DIRECTORIES
        for path in directory.rglob("*.py")
        if "__pycache__" not in path.parts
    }
    files.update(SCOPED_FILES)
    return sorted(files)


def test_log_language_guard_detects_logger_text_but_ignores_user_messages() -> None:
    fixture = '''
logger.warning("重试失败")
raise HTTPException(status_code=400, detail="用户可见中文")
'''

    assert find_non_english_developer_logs(fixture) == [(2, "重试失败")]


def test_remediated_boundaries_use_english_developer_logs() -> None:
    failures = {
        str(path.relative_to(REPO_ROOT)): find_non_english_developer_logs(
            path.read_text(encoding="utf-8")
        )
        for path in _remediated_log_boundaries()
    }

    assert {path: entries for path, entries in failures.items() if entries} == {}
