# -*- coding: utf-8 -*-
"""Queue/pipeline import-boundary freeze for scheduled-task execution (#1075)."""

from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path

import pytest

from src.config import Config
from src.core.trading_calendar import MarketSessionStatus
from src.repositories.scheduled_task_repo import ScheduledTaskRepository
from src.services.scheduled_task_service import ScheduledTaskService
from src.services.task_queue import AnalysisTaskQueue
from src.storage import DatabaseManager


ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = ROOT / "src" / "services" / "scheduled_task_service.py"
PARTS_DIR = ROOT / "src" / "services" / "scheduled_task_parts"
NOW = datetime(2026, 7, 24, 1, 29)
DUE = datetime(2026, 7, 24, 1, 30)

FORBIDDEN_MODULE_PREFIXES = (
    "src.core.pipeline",
    "src.core.stages",
    "src.core.contracts",
    "src.core.readiness",
    "src.services.analysis_service",
    "src.data_provider",
    "src.llm",
    "src.analyzer",
)
FORBIDDEN_IMPORTED_NAMES = frozenset(
    {
        "StockAnalysisPipeline",
        "AnalysisService",
        "analyze_stock",
    }
)
ALLOWED_MODULE_PREFIXES = (
    "src.core.trading_calendar",
    "src.services.task_queue",
    "src.task_execution",
    "src.services.analysis_submission_service",
    "src.agent.runtime_assembly",
)
QUEUE_EXECUTION_PORT = (
    "submit_tasks_batch",
    "retry",
    "retry_nowait",
    "get",
    "get_task",
)


def _scheduler_source_paths() -> tuple[Path, ...]:
    facade = FACADE_PATH
    parts = tuple(sorted(PARTS_DIR.glob("*.py")))
    assert facade.is_file()
    assert parts, "scheduled_task_parts must contain Python modules"
    return (facade, *parts)


def _is_forbidden_module(name: str) -> bool:
    return any(
        name == prefix or name.startswith(prefix + ".")
        for prefix in FORBIDDEN_MODULE_PREFIXES
    )


def _imported_module_names(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module:
                names.append(module)
            for alias in node.names:
                if alias.name == "*":
                    continue
                names.append(f"{module}.{alias.name}" if module else alias.name)
    return names


def _imported_symbol_names(tree: ast.AST) -> list[tuple[str, str]]:
    symbols: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                symbols.append((alias.name, alias.name.rsplit(".", 1)[-1]))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                if alias.name == "*":
                    continue
                full = f"{module}.{alias.name}" if module else alias.name
                symbols.append((full, alias.name))
    return symbols


def forbidden_imports_in_source(source: str, *, filename: str) -> list[str]:
    tree = ast.parse(source, filename=filename)
    hits: list[str] = []
    for module_name in _imported_module_names(tree):
        if _is_forbidden_module(module_name):
            hits.append(module_name)
    for full_name, imported_name in _imported_symbol_names(tree):
        if imported_name in FORBIDDEN_IMPORTED_NAMES:
            hits.append(full_name)
    return hits


def assert_no_forbidden_scheduler_imports(source: str, *, origin: str) -> None:
    hits = forbidden_imports_in_source(source, filename=origin)
    if hits:
        raise AssertionError(
            f"{origin} must not import forbidden analysis internals: {hits[0]}"
        )


def _top_level_imported_modules(source: str) -> list[str]:
    tree = ast.parse(source)
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


class _SilentSecurityAudit:
    def record_attempt(self, **_fields):
        return None

    def record_completion(self, **_fields):
        return None


class _PipelineStandIn:
    """Pipeline-shaped object that is not an analysis queue."""

    def __init__(self) -> None:
        self.analyze_stock_calls: list[tuple[tuple, dict]] = []

    def analyze_stock(self, *args, **kwargs):
        self.analyze_stock_calls.append((args, kwargs))
        return {"ok": True}


def _task_contract() -> dict:
    return {
        "schema_version": 1,
        "name": "Morning analysis",
        "task_type": "stock_analysis",
        "schedule": {
            "kind": "daily",
            "time": "09:30",
            "timezone": "Asia/Shanghai",
            "calendar_market": "cn",
            "non_trading_day_policy": "skip",
        },
        "payload": {
            "stock_code": "600519",
            "report_type": "detailed",
            "notify": False,
        },
        "enabled": True,
        "max_attempts": 1,
    }


@pytest.fixture
def database(tmp_path):
    DatabaseManager.reset_instance()
    Config.reset_instance()
    manager = DatabaseManager(db_url=f"sqlite:///{tmp_path / 'scheduled.sqlite'}")
    try:
        yield manager
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


def test_scheduler_modules_do_not_import_pipeline_or_analysis_internals() -> None:
    for path in _scheduler_source_paths():
        assert_no_forbidden_scheduler_imports(
            path.read_text(encoding="utf-8"),
            origin=str(path.relative_to(ROOT)),
        )


def test_copied_source_pipeline_import_fails_helper_with_module_name() -> None:
    original = FACADE_PATH.read_text(encoding="utf-8")
    injected = original + "\nfrom src.core.pipeline import StockAnalysisPipeline\n"
    with pytest.raises(AssertionError, match=r"src\.core\.pipeline") as caught:
        assert_no_forbidden_scheduler_imports(
            injected,
            origin="copied-scheduled_task_service.py",
        )
    assert "src.core.pipeline" in str(caught.value)


def test_allowed_queue_calendar_and_lazy_agent_imports_are_not_forbidden() -> None:
    snippet = (
        "from src.core.trading_calendar import classify_market_session\n"
        "from src.services.task_queue import DuplicateTaskError\n"
        "from src.task_execution import TaskSnapshot, TaskStatus\n"
        "from src.services.analysis_submission_service import AnalysisSubmissionService\n"
        "from src.agent.runtime_assembly import get_skill_manager\n"
    )
    assert_no_forbidden_scheduler_imports(snippet, origin="allowed-scheduler-imports")
    for prefix in ALLOWED_MODULE_PREFIXES:
        assert not _is_forbidden_module(prefix), prefix


def test_scheduler_keeps_allowed_imports_and_lazy_runtime_assembly() -> None:
    facade = FACADE_PATH.read_text(encoding="utf-8")
    admission_audit = (
        PARTS_DIR / "analysis_admission_audit.py"
    ).read_text(encoding="utf-8")
    assert "from src.core.trading_calendar import" in facade
    assert "from src.services.task_queue import" in facade
    assert "from src.task_execution import" in facade
    assert "from src.agent.runtime_assembly import get_skill_manager" in facade
    assert "from src.services.analysis_submission_service import" in admission_audit
    top_level = _top_level_imported_modules(facade)
    assert all(
        not (
            name == "src.agent.runtime_assembly"
            or name.startswith("src.agent.runtime_assembly.")
        )
        for name in top_level
    )


def test_queue_execution_port_remains_submit_retry_get() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in _scheduler_source_paths()
    )
    assert "queue.submit_tasks_batch(" in combined
    assert "queue.retry(" in combined
    assert 'getattr(queue, "retry_nowait"' in combined
    assert "queue.get(" in combined
    assert 'getattr(queue, "get_task"' in combined
    for name in QUEUE_EXECUTION_PORT:
        assert callable(getattr(AnalysisTaskQueue, name)), name


def test_pipeline_object_cannot_replace_missing_submit_tasks_batch(database) -> None:
    pipeline = _PipelineStandIn()
    assert not hasattr(pipeline, "submit_tasks_batch")
    service = ScheduledTaskService(
        repository=ScheduledTaskRepository(database),
        task_queue=pipeline,
        clock=lambda: NOW,
        market_session_provider=lambda _market, _date: MarketSessionStatus.OPEN,
        agent_skill_ids_provider=lambda: {"persona_tail_risk"},
        security_audit_factory=lambda: _SilentSecurityAudit(),
    )
    created = service.create_task(_task_contract(), now=NOW)

    claimed = service.tick(now=DUE)

    assert claimed == {"reconciled": 0, "claimed": 1, "skipped": 0}
    assert pipeline.analyze_stock_calls == []
    run = service.get_status(created["id"])["latest_run"]
    assert run["status"] == "retry_wait"
    assert run["attempt_count"] == 0
    assert run["dispatch_failure_count"] == 1
    assert run["execution_task_ids"] == []
    assert run["error_code"] == "scheduled_task_dispatch_failed"
