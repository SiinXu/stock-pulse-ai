# -*- coding: utf-8 -*-
"""Facade identity, patch, reload, and graph-helper characterization for #1086."""

from __future__ import annotations

import ast
import importlib
import inspect
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import src.services.run_flow as run_flow
import src.services.run_flow_parts.graph as graph
from src.services.run_flow import (
    build_history_run_flow_snapshot,
    build_task_run_flow_snapshot,
)
from tests.services.test_run_flow import _diagnostics, _history_record, _overview


ROOT = Path(__file__).resolve().parents[2]
OWNER_PATH = ROOT / "src" / "services" / "run_flow_parts" / "graph.py"
PACKAGE_INIT_PATH = ROOT / "src" / "services" / "run_flow_parts" / "__init__.py"
PUBLIC_BUILDER_NAMES = (
    "build_task_run_flow_snapshot",
    "build_history_run_flow_snapshot",
)


def test_public_builders_remain_on_run_flow_facade() -> None:
    for name in PUBLIC_BUILDER_NAMES:
        function = getattr(run_flow, name)
        assert callable(function), name
        assert function.__module__ == "src.services.run_flow", name


def test_graph_helpers_are_facade_bound_not_a_second_public_api() -> None:
    assert OWNER_PATH.is_file()
    assert PACKAGE_INIT_PATH.is_file()
    package = importlib.import_module("src.services.run_flow_parts")
    assert getattr(package, "__all__", ()) in ((), None)
    assert not hasattr(package, "_put_node")
    source = PACKAGE_INIT_PATH.read_text(encoding="utf-8")
    assert "from .graph import" not in source
    assert "bind_graph_helpers_facade" not in source


def test_graph_owner_does_not_import_run_flow_facade() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    assert all(name != "src.services.run_flow" for name in imported)
    assert all(not name.startswith("src.services.run_flow.") for name in imported)


def test_graph_helpers_share_code_not_identity_with_owner() -> None:
    source_names = []
    for name in graph.EXPECTED_GRAPH_HELPER_NAMES:
        source_function = getattr(graph, name)
        facade_function = getattr(run_flow, name)
        assert inspect.isfunction(source_function), name
        assert inspect.isfunction(facade_function), name
        assert facade_function is not source_function, name
        assert facade_function.__code__ is source_function.__code__, name
        assert facade_function.__module__ == "src.services.run_flow", name
        assert facade_function.__globals__ is vars(run_flow), name
        assert source_function.__module__ == graph.__name__, name
        source_names.append(name)
    assert tuple(source_names) == graph.EXPECTED_GRAPH_HELPER_NAMES


def test_put_node_omits_empty_optional_fields() -> None:
    nodes: dict[str, dict] = {}
    run_flow._put_node(
        nodes,
        "request",
        lane="entry",
        kind="entry",
        label="用户请求",
        status="success",
        metadata={},
        message=None,
        provider=None,
    )
    assert nodes["request"]["id"] == "request"
    assert nodes["request"]["label"] == "用户请求"
    assert nodes["request"]["status"] == "success"
    assert "provider" not in nodes["request"]
    assert "message" not in nodes["request"]
    assert "metadata" not in nodes["request"]
    assert "duration_ms" not in nodes["request"]


def test_valid_status_vocabulary_and_unknown_fallback() -> None:
    assert run_flow._valid_status("SUCCESS") == "success"
    assert run_flow._valid_status("fallback") == "fallback"
    assert run_flow._valid_status("not-a-status") == "unknown"
    assert run_flow._valid_status(None) == "unknown"


def test_append_edge_rejects_unknown_kind_and_updates_duplicate_id() -> None:
    edges: list[dict] = []
    run_flow._append_edge(edges, "a", "b", "mystery", "running", label="调度")
    assert edges[0]["kind"] == "data"
    assert edges[0]["label"] == "调度"
    run_flow._append_edge(edges, "a", "b", "mystery", "success", label="完成")
    assert len(edges) == 1
    assert edges[0]["status"] == "success"
    assert edges[0]["label"] == "完成"


def test_sanitize_metadata_redacts_secrets_without_mutating_input() -> None:
    original = {"api_key": "sk-secret", "note": "ok"}
    sanitized = run_flow._sanitize_metadata(original)
    assert original == {"api_key": "sk-secret", "note": "ok"}
    assert sanitized["api_key"] == "<redacted>"
    assert sanitized["note"] == "ok"


def test_task_snapshot_keeps_chinese_product_strings() -> None:
    task = SimpleNamespace(
        task_id="task-1",
        trace_id="task-1",
        stock_code="600519",
        stock_name="贵州茅台",
        status="completed",
        created_at=datetime(2026, 6, 8, 10, 0, 0),
        started_at=datetime(2026, 6, 8, 10, 0, 1),
        completed_at=datetime(2026, 6, 8, 10, 0, 5),
        original_query=None,
        selection_source=None,
        query_source=None,
        report_type=None,
        analysis_phase=None,
        error=None,
        message_code=None,
        message=None,
        flow_events=[],
    )
    snapshot = build_task_run_flow_snapshot(task)
    labels = {node.label for node in snapshot.nodes}
    assert "用户请求" in labels
    assert "任务已完成" in {node.message for node in snapshot.nodes if node.message}
    assert snapshot.status == "success"


def test_facade_local_timezone_patch_seam_still_controls_elapsed_ms() -> None:
    overview = _overview(
        blocks=[
            {
                "key": "news",
                "label": "新闻",
                "status": "missing",
                "source": None,
                "warnings": [],
                "missing_reasons": ["news_context_missing"],
            }
        ]
    )
    overview["created_at"] = "2026-06-08T02:00:05+00:00"
    record = _history_record(
        context_snapshot={
            "diagnostics": _diagnostics(),
            "analysis_context_pack_overview": overview,
        }
    )
    with patch(
        "src.services.run_flow._local_timezone",
        return_value=timezone(timedelta(hours=8)),
    ):
        snapshot = build_history_run_flow_snapshot(record)
    assert snapshot.summary.elapsed_ms == 5000


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.services.run_flow as run_flow",
                    "import src.services.run_flow_parts.graph as graph",
                    "",
                    "names = graph.EXPECTED_GRAPH_HELPER_NAMES",
                    "",
                    "def bindings():",
                    "    source = {}",
                    "    facade = {}",
                    "    for name in names:",
                    "        source[name] = getattr(graph, name)",
                    "        facade[name] = getattr(run_flow, name)",
                    "        assert facade[name] is not source[name]",
                    "        assert facade[name].__code__ is source[name].__code__",
                    "        assert facade[name].__globals__ is vars(run_flow)",
                    "        assert facade[name].__module__ == 'src.services.run_flow'",
                    "        assert facade[name].__qualname__ == name",
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
before_source, before_facade = bindings()
graph = importlib.reload(graph)
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
before_source, before_facade = bindings()
run_flow = importlib.reload(run_flow)
after_base_source, after_base_facade = bindings()
for name in names:
    assert after_base_source[name] is before_source[name]
    assert after_base_facade[name] is not before_facade[name]
graph = importlib.reload(graph)
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
            if relative.startswith("src/services/run_flow_parts/"):
                continue
            text = path.read_text(encoding="utf-8")
            if "src.services.run_flow_parts" in text and relative != "src/services/run_flow.py":
                hits.append(relative)
    assert hits == []
