# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Contract tests for structured readiness / self-check (Issue #1071)."""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from src.core.readiness import (
    SCHEMA_VERSION,
    ReadinessCheck,
    aggregate_readiness_status,
    build_readiness_report,
    check_data_providers,
    check_llm_runtime,
    check_task_queue,
    parse_readiness_check_timeout_seconds,
    project_setup_check_to_readiness,
    readiness_report_to_diagnostic_components,
)


def test_schema_version_and_status_enum_stable() -> None:
    check = ReadinessCheck(
        key="demo", status="ok", reason_code="ready", reason="ok", suggestion="none"
    )
    payload = check.to_dict()
    assert payload["status"] == "ok"
    assert payload["reason_code"] == "ready"
    with pytest.raises(ValueError):
        ReadinessCheck(key="x", status="ready", reason_code="x", reason="x")


def test_aggregate_empty_is_failed_not_ok() -> None:
    assert aggregate_readiness_status([]) == "failed"


def test_aggregate_required_failed_dominates() -> None:
    checks = [
        ReadinessCheck(key="a", status="ok", reason_code="ok", reason="ok", required=True),
        ReadinessCheck(key="b", status="failed", reason_code="down", reason="down", required=True),
    ]
    assert aggregate_readiness_status(checks) == "failed"


def test_aggregate_optional_failed_is_degraded() -> None:
    checks = [
        ReadinessCheck(key="a", status="ok", reason_code="ok", reason="ok", required=True),
        ReadinessCheck(key="b", status="failed", reason_code="x", reason="x", required=False),
    ]
    assert aggregate_readiness_status(checks) == "degraded"


def test_timeout_parser_clamps_and_rejects_nan() -> None:
    assert parse_readiness_check_timeout_seconds("1.5") == 1.5
    assert parse_readiness_check_timeout_seconds(0.01) == 0.1
    assert parse_readiness_check_timeout_seconds(99) == 5.0
    assert parse_readiness_check_timeout_seconds("nope") == 1.0
    assert parse_readiness_check_timeout_seconds(float("nan")) == 1.0


def test_data_providers_not_initialized_is_failed_not_ok() -> None:
    check = check_data_providers(
        status_payload={
            "source_state": "not_initialized",
            "error_code": "data_runtime_not_initialized",
            "error_message": "not live",
            "providers": [],
            "markets": [],
            "partial": True,
        }
    )
    assert check.status == "failed"
    assert check.reason_code == "data_runtime_not_initialized"


def test_data_providers_error_source_is_failed() -> None:
    check = check_data_providers(
        status_payload={
            "source_state": "error",
            "error_code": "data_provider_status_resolve_failed",
            "error_message": "boom",
            "providers": [],
            "markets": [],
            "partial": True,
        }
    )
    assert check.status == "failed"
    assert "boom" in check.reason


def test_data_providers_factory_exception_is_failed() -> None:
    def _raise() -> Dict[str, Any]:
        raise RuntimeError("manager missing")

    check = check_data_providers(status_factory=_raise)
    assert check.status == "failed"
    assert check.reason_code == "data_provider_probe_failed"


def test_data_providers_all_unavailable_is_failed() -> None:
    check = check_data_providers(
        status_payload={
            "source_state": "ok",
            "error_code": None,
            "providers": [
                {"provider_id": "akshare", "available": False, "health_status": "unavailable"},
                {"provider_id": "efinance", "available": False, "health_status": "circuit_open"},
            ],
            "markets": [
                {"market": "cn", "quality": "unavailable"},
                {"market": "hk", "quality": "unavailable"},
                {"market": "us", "quality": "unavailable"},
            ],
            "partial": False,
        }
    )
    assert check.status == "failed"
    assert check.reason_code in {"all_markets_unavailable", "all_providers_unavailable"}


def test_data_providers_partial_degradation() -> None:
    check = check_data_providers(
        status_payload={
            "source_state": "ok",
            "providers": [
                {"provider_id": "akshare", "available": True, "health_status": "ok"},
                {"provider_id": "tushare", "available": False, "health_status": "unavailable"},
            ],
            "markets": [
                {"market": "cn", "quality": "ok"},
                {"market": "hk", "quality": "degraded"},
                {"market": "us", "quality": "unavailable"},
            ],
            "partial": False,
        }
    )
    assert check.status == "degraded"
    assert check.reason_code == "partial_provider_degradation"


def test_data_providers_ok_when_registered() -> None:
    check = check_data_providers(
        status_payload={
            "source_state": "ok",
            "providers": [
                {"provider_id": "akshare", "available": True, "health_status": "unknown"},
            ],
            "markets": [{"market": "cn", "quality": "unknown"}],
            "partial": False,
        }
    )
    assert check.status == "ok"
    assert check.reason_code == "providers_ready"


def test_llm_missing_primary_is_degraded_not_ok() -> None:
    check = check_llm_runtime(
        setup_status={
            "ready_for_smoke": False,
            "checks": [
                {
                    "key": "llm_primary",
                    "status": "needs_action",
                    "required": True,
                    "message": "No primary model",
                    "next_step": "Configure a model",
                }
            ],
        },
        generation_status={
            "primary": {"backend_id": "litellm", "available": False, "health_status": "not_tested"}
        },
    )
    assert check.status == "degraded"
    assert check.reason_code == "primary_model_missing"


def test_llm_configured_but_backend_unavailable_is_failed() -> None:
    check = check_llm_runtime(
        setup_status={
            "ready_for_smoke": True,
            "checks": [
                {"key": "llm_primary", "status": "configured", "required": True, "message": "model set"}
            ],
        },
        generation_status={
            "primary": {"backend_id": "codex_cli", "available": False, "health_status": "failed"}
        },
    )
    assert check.status == "failed"
    assert check.reason_code == "primary_backend_unavailable"


def test_llm_setup_probe_exception_is_failed() -> None:
    def _raise() -> Dict[str, Any]:
        raise RuntimeError("config unreadable")

    check = check_llm_runtime(setup_status_factory=_raise)
    assert check.status == "failed"
    assert check.reason_code == "llm_setup_probe_failed"


def test_task_queue_missing_is_failed() -> None:
    check = check_task_queue(queue_factory=lambda: None)
    assert check.status == "failed"
    assert check.reason_code == "task_queue_missing"


def test_task_queue_shutdown_is_failed() -> None:
    queue = SimpleNamespace(_shutdown=True, max_workers=3, get_task_stats=lambda: {})
    check = check_task_queue(queue=queue)
    assert check.status == "failed"
    assert check.reason_code == "task_queue_shutdown"


def test_task_queue_stats_exception_is_failed() -> None:
    class _Broken:
        _shutdown = False
        max_workers = 2

        def get_task_stats(self) -> Dict[str, int]:
            raise RuntimeError("lock broken")

    check = check_task_queue(queue=_Broken())
    assert check.status == "failed"
    assert check.reason_code == "task_queue_stats_failed"


def test_task_queue_zero_workers_is_failed() -> None:
    queue = SimpleNamespace(
        _shutdown=False,
        max_workers=0,
        get_task_stats=lambda: {"pending": 0, "processing": 0},
    )
    check = check_task_queue(queue=queue)
    assert check.status == "failed"
    assert check.reason_code == "task_queue_no_workers"


def test_task_queue_busy_is_degraded() -> None:
    queue = SimpleNamespace(
        _shutdown=False,
        max_workers=1,
        get_task_stats=lambda: {"pending": 3, "processing": 1, "completed": 0, "failed": 0},
    )
    check = check_task_queue(queue=queue)
    assert check.status == "degraded"
    assert check.reason_code == "task_queue_busy"


def test_task_queue_ready_is_ok() -> None:
    queue = SimpleNamespace(
        _shutdown=False,
        max_workers=3,
        get_task_stats=lambda: {
            "total": 1, "pending": 0, "processing": 1, "completed": 0, "failed": 0
        },
    )
    check = check_task_queue(queue=queue)
    assert check.status == "ok"
    assert check.reason_code == "task_queue_ready"


def test_setup_projection_unknown_status_fail_closed() -> None:
    check = project_setup_check_to_readiness(
        {"key": "storage", "status": "mystery", "required": True, "message": "???"}
    )
    assert check.status == "failed"
    assert check.reason_code == "setup_status_unknown"


def test_build_report_timeout_never_ok() -> None:
    def _slow() -> Dict[str, Any]:
        time.sleep(0.5)
        return {
            "source_state": "ok",
            "providers": [{"provider_id": "akshare", "available": True}],
            "markets": [],
        }

    report = build_readiness_report(
        timeout_seconds=0.1,
        include_dependency_checks=False,
        data_provider_status_factory=_slow,
        setup_status={
            "checks": [
                {"key": "llm_primary", "status": "configured", "required": True, "message": "ok"}
            ]
        },
        generation_status={"primary": {"backend_id": "litellm", "available": True}},
        task_queue=SimpleNamespace(
            _shutdown=False,
            max_workers=2,
            get_task_stats=lambda: {"pending": 0, "processing": 0},
        ),
    )
    assert report.schema_version == SCHEMA_VERSION
    assert report.status in {"failed", "degraded"}
    data_check = next(c for c in report.checks if c.key == "data_providers")
    assert data_check.timed_out is True
    assert data_check.status == "failed"


def test_build_report_all_ready() -> None:
    report = build_readiness_report(
        timeout_seconds=1.0,
        include_dependency_checks=True,
        data_provider_status={
            "source_state": "ok",
            "providers": [{"provider_id": "akshare", "available": True, "health_status": "ok"}],
            "markets": [{"market": "cn", "quality": "ok"}],
        },
        setup_status={
            "ready_for_smoke": True,
            "checks": [
                {"key": "llm_primary", "status": "configured", "required": True, "message": "model ready"},
                {"key": "storage", "status": "configured", "required": True, "message": "db ok"},
                {"key": "notification", "status": "optional", "required": False, "message": "no channel"},
                {"key": "llm_agent", "status": "optional", "required": False, "message": "agent optional"},
                {"key": "stock_list", "status": "configured", "required": True, "message": "stocks set"},
            ],
        },
        generation_status={"primary": {"backend_id": "litellm", "available": True}},
        task_queue=SimpleNamespace(
            _shutdown=False,
            max_workers=3,
            get_task_stats=lambda: {"pending": 0, "processing": 0},
        ),
    )
    assert report.status == "ok"
    assert report.partial is False
    keys = {c.key for c in report.checks}
    assert {"data_providers", "llm", "task_queue", "storage"}.issubset(keys)
    assert all(c.status == "ok" for c in report.checks)


def test_build_report_unavailable_deps_do_not_report_ready() -> None:
    report = build_readiness_report(
        timeout_seconds=1.0,
        include_dependency_checks=False,
        data_provider_status={
            "source_state": "not_initialized",
            "error_code": "data_runtime_not_initialized",
            "error_message": "no manager",
            "providers": [],
            "markets": [],
        },
        setup_status={
            "checks": [
                {"key": "llm_primary", "status": "needs_action", "required": True, "message": "no model"}
            ]
        },
        generation_status={"primary": {"backend_id": "litellm", "available": False}},
        task_queue_factory=lambda: (_ for _ in ()).throw(RuntimeError("queue down")),
    )
    assert report.status == "failed"
    by_key = {c.key: c for c in report.checks}
    assert by_key["data_providers"].status == "failed"
    assert by_key["llm"].status == "degraded"
    assert by_key["task_queue"].status == "failed"
    assert all(c.status != "ok" for c in report.checks)


def test_diagnostic_component_projection() -> None:
    report = build_readiness_report(
        timeout_seconds=1.0,
        include_dependency_checks=False,
        data_provider_status={
            "source_state": "ok",
            "providers": [{"provider_id": "akshare", "available": True}],
            "markets": [],
        },
        setup_status={
            "checks": [
                {"key": "llm_primary", "status": "configured", "required": True, "message": "ok"}
            ]
        },
        generation_status={"primary": {"backend_id": "litellm", "available": True}},
        task_queue=SimpleNamespace(
            _shutdown=False,
            max_workers=1,
            get_task_stats=lambda: {"pending": 0, "processing": 0},
        ),
    )
    components = readiness_report_to_diagnostic_components(report)
    assert "data_providers" in components
    assert components["data_providers"]["status"] in {"ok", "degraded", "failed"}


def test_checks_do_not_mutate_injected_queue() -> None:
    stats_calls = {"n": 0}

    class _Queue:
        _shutdown = False
        max_workers = 2
        mutated = False

        def get_task_stats(self) -> Dict[str, int]:
            stats_calls["n"] += 1
            return {"pending": 0, "processing": 0, "completed": 0, "failed": 0}

    queue = _Queue()
    check_task_queue(queue=queue)
    assert stats_calls["n"] == 1
    assert queue.mutated is False
    assert queue._shutdown is False
