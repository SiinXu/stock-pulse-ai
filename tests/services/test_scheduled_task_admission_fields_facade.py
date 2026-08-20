# -*- coding: utf-8 -*-
"""Facade identity, reload, and admission-field characterization for #1086."""

from __future__ import annotations

import ast
import importlib
import inspect
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.services.scheduled_task_parts.admission_fields as admission_fields
import src.services.scheduled_task_service as scheduled_task_service
from src.schemas.scheduled_task import (
    SCHEDULED_TASK_RETRY_DELAY_SECONDS,
    ScheduledRunStatus,
)
from src.services.scheduled_task_service import (
    ScheduledTaskContractError,
    ScheduledTaskService,
)


ROOT = Path(__file__).resolve().parents[2]
OWNER_PATH = (
    ROOT / "src" / "services" / "scheduled_task_parts" / "admission_fields.py"
)
PACKAGE_INIT_PATH = (
    ROOT / "src" / "services" / "scheduled_task_parts" / "__init__.py"
)
NOW = datetime(2026, 7, 24, 1, 29)


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    return descriptor


def test_admission_fields_remain_on_scheduled_task_service_facade() -> None:
    required = admission_fields.EXPECTED_ADMISSION_FIELD_METHOD_NAMES
    assert required == (
        "_conflict_wait_fields",
        "_interrupted_admission_fields",
        "_dispatch_failure_fields",
        "_running_admission_fields",
    )
    for name in required:
        method = getattr(ScheduledTaskService, name)
        assert callable(method), name
        function = _descriptor_function(vars(ScheduledTaskService)[name])
        assert function.__module__ == "src.services.scheduled_task_service", name
        assert function.__qualname__ == f"ScheduledTaskService.{name}", name
        assert function.__globals__ is vars(scheduled_task_service), name


def test_admission_fields_are_not_a_second_public_api() -> None:
    assert OWNER_PATH.is_file()
    assert PACKAGE_INIT_PATH.is_file()
    package = importlib.import_module("src.services.scheduled_task_parts")
    assert getattr(package, "__all__", ()) in ((), None)
    for name in admission_fields.EXPECTED_ADMISSION_FIELD_METHOD_NAMES:
        assert not hasattr(package, name)
    source = PACKAGE_INIT_PATH.read_text(encoding="utf-8")
    assert "from .admission_fields import" not in source
    assert "bind_admission_fields_facade" not in source
    assert "EXPECTED_ADMISSION_FIELD_METHOD_NAMES" not in source


def test_admission_fields_owner_does_not_import_the_facade() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    assert all(name != "src.services.scheduled_task_service" for name in imported)
    assert all(
        not name.startswith("src.services.scheduled_task_service.")
        for name in imported
    )


def test_admission_field_bind_inventory_is_exact() -> None:
    dummy = type("DummyScheduledTaskService", (), {})
    bound = admission_fields.bind_admission_fields_facade(
        dummy,
        vars(scheduled_task_service),
    )
    assert bound == admission_fields.EXPECTED_ADMISSION_FIELD_METHOD_NAMES


def test_admission_field_assembly_raises_on_mismatch() -> None:
    dummy = type("DummyScheduledTaskService", (), {})
    extra = staticmethod(lambda now: {})
    admission_fields._AdmissionFieldMethods._extra_fields = extra
    try:
        bound = admission_fields.bind_admission_fields_facade(
            dummy,
            vars(scheduled_task_service),
        )
        with pytest.raises(
            ImportError,
            match="Unexpected ScheduledTaskService admission field methods",
        ):
            if bound != admission_fields.EXPECTED_ADMISSION_FIELD_METHOD_NAMES:
                raise ImportError(
                    "Unexpected ScheduledTaskService admission field methods: "
                    f"{bound!r}"
                )
        assert "_extra_fields" in bound
    finally:
        del admission_fields._AdmissionFieldMethods._extra_fields


def test_admission_fields_share_code_not_identity_with_owner() -> None:
    source_names = []
    for name, source_descriptor in vars(
        admission_fields._AdmissionFieldMethods
    ).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(ScheduledTaskService)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == admission_fields.__name__
    assert tuple(source_names) == admission_fields.EXPECTED_ADMISSION_FIELD_METHOD_NAMES


def test_conflict_wait_fields_use_retry_delay() -> None:
    fields = ScheduledTaskService._conflict_wait_fields(NOW)
    assert fields["status"] == ScheduledRunStatus.RETRY_WAIT.value
    assert fields["dispatch_token"] is None
    assert fields["error_code"] == "scheduled_task_execution_conflict"
    assert fields["next_attempt_at"] == NOW + timedelta(
        seconds=SCHEDULED_TASK_RETRY_DELAY_SECONDS
    )
    assert fields["finished_at"] is None
    assert fields["updated_at"] == NOW


def test_interrupted_admission_fields_are_terminal() -> None:
    fields = ScheduledTaskService._interrupted_admission_fields(
        NOW,
        error_code="scheduled_task_run_invalid",
    )
    assert fields["status"] == ScheduledRunStatus.INTERRUPTED.value
    assert fields["dispatch_token"] is None
    assert fields["error_code"] == "scheduled_task_run_invalid"
    assert fields["next_attempt_at"] is None
    assert fields["finished_at"] == NOW
    assert fields["updated_at"] == NOW


def test_dispatch_failure_retries_until_terminal_at_three() -> None:
    first = ScheduledTaskService._dispatch_failure_fields(
        SimpleNamespace(dispatch_failure_count=0),
        NOW,
        error_code="scheduled_task_queue_unavailable",
    )
    assert first["status"] == ScheduledRunStatus.RETRY_WAIT.value
    assert first["dispatch_failure_count"] == 1
    assert first["finished_at"] is None
    assert first["next_attempt_at"] == NOW + timedelta(
        seconds=SCHEDULED_TASK_RETRY_DELAY_SECONDS
    )

    second = ScheduledTaskService._dispatch_failure_fields(
        SimpleNamespace(dispatch_failure_count=1),
        NOW,
        error_code="scheduled_task_queue_unavailable",
    )
    assert second["status"] == ScheduledRunStatus.RETRY_WAIT.value
    assert second["dispatch_failure_count"] == 2
    assert second["finished_at"] is None

    terminal = ScheduledTaskService._dispatch_failure_fields(
        SimpleNamespace(dispatch_failure_count=2),
        NOW,
        error_code="scheduled_task_queue_unavailable",
    )
    assert terminal["status"] == ScheduledRunStatus.FAILED.value
    assert terminal["dispatch_failure_count"] == 3
    assert terminal["dispatch_token"] is None
    assert terminal["next_attempt_at"] is None
    assert terminal["finished_at"] == NOW
    assert terminal["updated_at"] == NOW


def test_running_admission_fields_append_owned_and_unowned_ids() -> None:
    run = SimpleNamespace(
        execution_task_ids_json='["existing"]',
        owned_execution_task_ids_json='["existing"]',
        attempt_count=0,
        started_at=None,
    )
    owned = ScheduledTaskService._running_admission_fields(
        run,
        NOW,
        execution_id="new",
        owned=True,
    )
    assert owned["status"] == ScheduledRunStatus.RUNNING.value
    assert owned["attempt_count"] == 1
    assert json.loads(owned["execution_task_ids_json"]) == ["existing", "new"]
    assert json.loads(owned["owned_execution_task_ids_json"]) == ["existing", "new"]
    assert owned["started_at"] == NOW
    assert owned["finished_at"] is None

    unowned = ScheduledTaskService._running_admission_fields(
        run,
        NOW,
        execution_id="new",
        owned=False,
    )
    assert json.loads(unowned["execution_task_ids_json"]) == ["existing", "new"]
    assert json.loads(unowned["owned_execution_task_ids_json"]) == ["existing"]
    assert unowned["attempt_count"] == 1


def test_running_admission_fields_reject_invalid_execution_json() -> None:
    run = SimpleNamespace(
        execution_task_ids_json="{not-json",
        owned_execution_task_ids_json="[]",
        attempt_count=0,
        started_at=None,
    )
    with pytest.raises(ScheduledTaskContractError, match="execution_task_ids"):
        ScheduledTaskService._running_admission_fields(
            run,
            NOW,
            execution_id="new",
            owned=True,
        )


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.services.scheduled_task_service as scheduled_task_service",
                    "import src.services.scheduled_task_parts.admission_fields as admission_fields",
                    "",
                    "names = admission_fields.EXPECTED_ADMISSION_FIELD_METHOD_NAMES",
                    "",
                    "def descriptor_function(descriptor):",
                    "    if isinstance(descriptor, (staticmethod, classmethod)):",
                    "        return descriptor.__func__",
                    "    return descriptor",
                    "",
                    "def bindings():",
                    "    source = {}",
                    "    facade = {}",
                    "    for name in names:",
                    "        source[name] = descriptor_function(",
                    "            vars(admission_fields._AdmissionFieldMethods)[name]",
                    "        )",
                    "        facade[name] = descriptor_function(",
                    "            vars(scheduled_task_service.ScheduledTaskService)[name]",
                    "        )",
                    "        assert facade[name] is not source[name]",
                    "        assert facade[name].__code__ is source[name].__code__",
                    "        assert facade[name].__globals__ is vars(scheduled_task_service)",
                    "        assert facade[name].__module__ == 'src.services.scheduled_task_service'",
                    "        assert facade[name].__qualname__ == f'ScheduledTaskService.{name}'",
                    "    return source, facade",
                    "",
                    body,
                )
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_owner_reload_rebinds_loaded_facade() -> None:
    _run_reload_contract(
        """
old_class = scheduled_task_service.ScheduledTaskService
before_source, before_facade = bindings()
admission_fields = importlib.reload(admission_fields)
assert scheduled_task_service.ScheduledTaskService is old_class
after_source, after_facade = bindings()
for name in names:
    assert after_source[name] is not before_source[name]
    assert after_facade[name] is not before_facade[name]
    assert after_facade[name].__code__ is after_source[name].__code__
"""
    )


def test_facade_then_owner_reload_keeps_one_current_contract() -> None:
    _run_reload_contract(
        """
old_class = scheduled_task_service.ScheduledTaskService
before_source, before_facade = bindings()
scheduled_task_service = importlib.reload(scheduled_task_service)
assert scheduled_task_service.ScheduledTaskService is not old_class
after_base_source, after_base_facade = bindings()
for name in names:
    assert after_base_source[name] is before_source[name]
    assert after_base_facade[name] is not before_facade[name]
reloaded_class = scheduled_task_service.ScheduledTaskService
admission_fields = importlib.reload(admission_fields)
assert scheduled_task_service.ScheduledTaskService is reloaded_class
after_owner_source, after_owner_facade = bindings()
for name in names:
    assert after_owner_source[name] is not after_base_source[name]
    assert after_owner_facade[name] is not after_base_facade[name]
    assert after_owner_facade[name].__code__ is after_owner_source[name].__code__
"""
    )


def test_production_callers_still_import_the_facade() -> None:
    production_roots = (
        ROOT / "src",
        ROOT / "main.py",
        ROOT / "server.py",
    )
    hits = []
    for root in production_roots:
        paths = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for path in paths:
            relative = path.relative_to(ROOT).as_posix()
            if relative.startswith("src/services/scheduled_task_parts/"):
                continue
            text = path.read_text(encoding="utf-8")
            if (
                "src.services.scheduled_task_parts" in text
                and relative != "src/services/scheduled_task_service.py"
            ):
                hits.append(relative)
    assert hits == []
