# -*- coding: utf-8 -*-
"""Facade identity, patch, reload, and agent-event characterization for #1086."""

from __future__ import annotations

import ast
import importlib
import inspect
import subprocess
import sys
from datetime import timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import src.services.run_flow as run_flow
import src.services.run_flow_parts.agent_events as agent_events
from src.services.run_flow import build_history_run_flow_snapshot
from tests.services.test_run_flow import _diagnostics, _history_record, _overview


ROOT = Path(__file__).resolve().parents[2]
OWNER_PATH = ROOT / "src" / "services" / "run_flow_parts" / "agent_events.py"
PACKAGE_INIT_PATH = ROOT / "src" / "services" / "run_flow_parts" / "__init__.py"
PUBLIC_BUILDER_NAMES = (
    "build_task_run_flow_snapshot",
    "build_history_run_flow_snapshot",
)
SNAPSHOT_KEYS = {
    "schema_version",
    "task_id",
    "trace_id",
    "stock_code",
    "stock_name",
    "status",
    "summary",
    "lanes",
    "nodes",
    "edges",
    "events",
    "generated_at",
}


def _seed_graph() -> tuple[dict[str, dict], list[dict], list[dict]]:
    nodes = {
        "llm": {
            "id": "llm",
            "lane": "analysis",
            "kind": "model",
            "label": "LLM 生成",
            "status": "success",
        }
    }
    return nodes, [], []


def _agent_event(
    event_type: str,
    *,
    name: str,
    span_id: str,
    sequence: int,
    timestamp: str,
    status: str = "success",
    duration_ms: int | None = None,
    step: int | None = None,
    parent_span_id: str | None = None,
    attrs: dict | None = None,
    payload: dict | None = None,
) -> dict:
    event = {
        "schema_version": 1,
        "event_type": event_type,
        "trace_id": "trace-agent",
        "span_id": span_id,
        "sequence": sequence,
        "timestamp": timestamp,
        "name": name,
        "status": status,
    }
    if duration_ms is not None:
        event["duration_ms"] = duration_ms
    if step is not None:
        event["step"] = step
    if parent_span_id is not None:
        event["parent_span_id"] = parent_span_id
    if attrs is not None:
        event["attrs"] = attrs
    if payload is not None:
        event["payload"] = payload
    return event


def test_public_builders_remain_on_run_flow_facade() -> None:
    for name in PUBLIC_BUILDER_NAMES:
        function = getattr(run_flow, name)
        assert callable(function), name
        assert function.__module__ == "src.services.run_flow", name


def test_agent_event_helpers_are_facade_bound_not_a_second_public_api() -> None:
    assert OWNER_PATH.is_file()
    assert PACKAGE_INIT_PATH.is_file()
    package = importlib.import_module("src.services.run_flow_parts")
    assert getattr(package, "__all__", ()) in ((), None)
    assert not hasattr(package, "_append_agent_events")
    assert not hasattr(package, "_agent_event_status")
    source = PACKAGE_INIT_PATH.read_text(encoding="utf-8")
    assert "from .agent_events import" not in source
    assert "bind_agent_events_facade" not in source


def test_agent_events_owner_does_not_import_run_flow_facade() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    assert all(name != "src.services.run_flow" for name in imported)
    assert all(not name.startswith("src.services.run_flow.") for name in imported)
    assert "src.services.run_flow_parts.graph" in imported


def test_agent_event_helpers_share_code_not_identity_with_owner() -> None:
    source_names = []
    for name in agent_events.EXPECTED_AGENT_EVENT_NAMES:
        source_function = getattr(agent_events, name)
        facade_function = getattr(run_flow, name)
        assert inspect.isfunction(source_function), name
        assert inspect.isfunction(facade_function), name
        assert facade_function is not source_function, name
        assert facade_function.__code__ is source_function.__code__, name
        assert facade_function.__module__ == "src.services.run_flow", name
        assert facade_function.__qualname__ == name, name
        assert facade_function.__globals__ is vars(run_flow), name
        assert source_function.__module__ == agent_events.__name__, name
        source_names.append(name)
    assert tuple(source_names) == agent_events.EXPECTED_AGENT_EVENT_NAMES


def test_empty_agent_events_is_a_no_op() -> None:
    nodes, edges, events = _seed_graph()
    original_nodes = dict(nodes)
    result = run_flow._append_agent_events(
        nodes,
        edges,
        events,
        [],
        anchor_node_id="llm",
        capture={"original_count": 0, "returned_count": 0, "dropped_count": 0, "truncated": False},
    )
    assert result is None
    assert nodes == original_nodes
    assert edges == []
    assert events == []


def test_span_merge_updates_the_same_tool_node() -> None:
    nodes, edges, events = _seed_graph()
    last_id = run_flow._append_agent_events(
        nodes,
        edges,
        events,
        [
            _agent_event(
                "agent.tool_start",
                name="get_realtime_quote",
                span_id="tool1",
                sequence=1,
                timestamp="2026-06-08T10:00:03",
                status="running",
                step=1,
            ),
            _agent_event(
                "agent.tool_end",
                name="get_realtime_quote",
                span_id="tool1",
                sequence=2,
                timestamp="2026-06-08T10:00:04",
                status="success",
                duration_ms=8,
                step=1,
            ),
        ],
        anchor_node_id="llm",
    )
    tool_nodes = [node for node_id, node in nodes.items() if node_id.startswith("agent_tool_")]
    assert last_id == "agent_tool_tool1"
    assert len(tool_nodes) == 1
    assert tool_nodes[0]["status"] == "success"
    assert tool_nodes[0]["duration_ms"] == 8
    assert tool_nodes[0]["ended_at"] == "2026-06-08T10:00:04"
    assert tool_nodes[0]["started_at"] == "2026-06-08T10:00:03"
    assert [event["metadata"]["sequence"] for event in events] == [1, 2]


def test_redaction_and_non_finite_integrity_stay_on_facade() -> None:
    nodes, edges, events = _seed_graph()
    run_flow._append_agent_events(
        nodes,
        edges,
        events,
        [
            _agent_event(
                "agent.tool_end",
                name="get_realtime_quote",
                span_id="tool-secret",
                sequence=1,
                timestamp="2026-06-08T10:00:04",
                status="success",
                duration_ms=8,
                attrs={"stock_code": "600519", "api_key": "sk-secret"},
            ),
            _agent_event(
                "agent.decision",
                name="final_answer",
                span_id="decision-1",
                sequence=2,
                timestamp="2026-06-08T10:00:05",
                status="success",
                attrs={"confidence": float("inf"), "signal": "hold"},
            ),
        ],
        anchor_node_id="llm",
        capture={"original_count": 2, "returned_count": 2, "dropped_count": 0, "truncated": False},
    )
    redacted = next(event for event in events if event["metadata"]["sequence"] == 1)
    non_finite = next(event for event in events if event["metadata"]["sequence"] == 2)
    assert redacted["metadata"]["attrs"] == {
        "stock_code": "600519",
        "api_key": "<redacted>",
    }
    assert redacted["metadata"]["detail_integrity"] == "valid"
    assert non_finite["metadata"]["attrs"] == {"signal": "hold"}
    assert non_finite["metadata"]["detail_integrity"] == "invalid_non_finite"


def test_chinese_labels_and_status_mapping() -> None:
    nodes, edges, events = _seed_graph()
    run_flow._append_agent_events(
        nodes,
        edges,
        events,
        [
            _agent_event(
                "agent.phase_start",
                name="agent_loop",
                span_id="phase1",
                sequence=1,
                timestamp="2026-06-08T10:00:02",
                status="started",
            ),
            _agent_event(
                "agent.tool_end",
                name="get_realtime_quote",
                span_id="tool1",
                sequence=2,
                timestamp="2026-06-08T10:00:03",
                status="ok",
                duration_ms=8,
            ),
            _agent_event(
                "agent.model_end",
                name="demo-model",
                span_id="model1",
                sequence=3,
                timestamp="2026-06-08T10:00:04",
                status="error",
                duration_ms=12,
            ),
            _agent_event(
                "agent.phase_end",
                name="agent_loop",
                span_id="phase1",
                sequence=4,
                timestamp="2026-06-08T10:00:05",
                status="done",
                duration_ms=30,
            ),
        ],
        anchor_node_id="llm",
    )
    labels = {node["label"] for node in nodes.values()}
    assert "阶段 · agent_loop" in labels
    assert "工具 · get_realtime_quote" in labels
    assert "模型 · demo-model" in labels
    assert nodes["agent_phase_phase1"]["status"] == "success"
    assert nodes["agent_tool_tool1"]["status"] == "success"
    assert nodes["agent_model_model1"]["status"] == "failed"
    assert run_flow._agent_event_status("running", event_type="agent_tool_end") == "running"
    assert run_flow._agent_event_status("completed", event_type="agent_tool_end") == "success"
    assert run_flow._agent_event_status("fail", event_type="agent_tool_end") == "failed"
    assert run_flow._agent_event_status("timeout", event_type="agent_tool_end") == "timeout"
    assert run_flow._agent_event_status("weird", event_type="agent_tool_end") == "degraded"
    assert run_flow._agent_event_status("", event_type="agent_tool_end") == "unknown"
    assert run_flow._agent_event_status("ok", event_type="agent_tool_start") == "running"


def test_tool_sequence_is_capped_at_forty() -> None:
    nodes, edges, events = _seed_graph()
    raw_events = [
        _agent_event(
            "agent.phase_start",
            name="agent_loop",
            span_id="phase-cap",
            sequence=1,
            timestamp="2026-06-08T10:00:02",
            status="running",
        )
    ]
    for index in range(41):
        raw_events.append(
            _agent_event(
                "agent.tool_end",
                name=f"tool_{index}",
                span_id=f"tool-{index}",
                sequence=index + 2,
                timestamp="2026-06-08T10:00:03",
                status="success",
                duration_ms=1,
                parent_span_id="phase-cap",
            )
        )
    raw_events.append(
        _agent_event(
            "agent.phase_end",
            name="agent_loop",
            span_id="phase-cap",
            sequence=43,
            timestamp="2026-06-08T10:00:05",
            status="success",
            duration_ms=30,
        )
    )
    run_flow._append_agent_events(nodes, edges, events, raw_events, anchor_node_id="llm")
    metadata = nodes["agent_phase_phase_cap"]["metadata"]
    assert metadata["tool_count"] == 41
    assert len(metadata["tool_sequence"]) == 40


def test_history_snapshot_keys_ordering_and_timezone_patch_seam() -> None:
    diagnostics = _diagnostics()
    diagnostics["agent_events"] = [
        _agent_event(
            "agent.phase_start",
            name="agent_loop",
            span_id="phase1",
            sequence=1,
            timestamp="2026-06-08T10:00:02",
            status="running",
        ),
        _agent_event(
            "agent.tool_start",
            name="get_realtime_quote",
            span_id="tool1",
            sequence=2,
            timestamp="2026-06-08T10:00:03",
            status="running",
            step=1,
            parent_span_id="phase1",
            attrs={"stock_code": "600519", "api_key": "secret"},
        ),
        _agent_event(
            "agent.tool_end",
            name="get_realtime_quote",
            span_id="tool1",
            sequence=3,
            timestamp="2026-06-08T10:00:04",
            status="success",
            duration_ms=8,
            step=1,
            parent_span_id="phase1",
        ),
        _agent_event(
            "agent.phase_end",
            name="agent_loop",
            span_id="phase1",
            sequence=4,
            timestamp="2026-06-08T10:00:05",
            status="success",
            duration_ms=30,
        ),
    ]
    diagnostics["agent_events_capture"] = {
        "original_count": 4,
        "returned_count": 4,
        "dropped_count": 0,
        "truncated": False,
    }
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
            "diagnostics": diagnostics,
            "analysis_context_pack_overview": overview,
        }
    )
    with patch(
        "src.services.run_flow._local_timezone",
        return_value=timezone(timedelta(hours=8)),
    ):
        snapshot = build_history_run_flow_snapshot(record)
    payload = snapshot.model_dump(mode="json", by_alias=True)
    assert set(payload) == SNAPSHOT_KEYS
    replay_events = [event for event in snapshot.events if event.type.startswith("agent_")]
    assert [event.metadata["sequence"] for event in replay_events] == [1, 2, 3, 4]
    assert snapshot.summary.elapsed_ms == 5000
    phase_nodes = [node for node in snapshot.nodes if node.id.startswith("agent_phase_")]
    tool_sequence = (phase_nodes[0].metadata or {}).get("tool_sequence") or []
    assert tool_sequence[0]["label"] == "get_realtime_quote"
    assert replay_events[1].metadata["attrs"] == {
        "stock_code": "600519",
        "api_key": "<redacted>",
    }


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.services.run_flow as run_flow",
                    "import src.services.run_flow_parts.agent_events as agent_events",
                    "",
                    "names = agent_events.EXPECTED_AGENT_EVENT_NAMES",
                    "",
                    "def bindings():",
                    "    source = {}",
                    "    facade = {}",
                    "    for name in names:",
                    "        source[name] = getattr(agent_events, name)",
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
agent_events = importlib.reload(agent_events)
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
agent_events = importlib.reload(agent_events)
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
