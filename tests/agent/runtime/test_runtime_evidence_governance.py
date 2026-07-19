# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Guards for retired cross-runtime evidence and its documented limits."""

import json
import re
from pathlib import Path

import pytest

from src.agent.runtime.contract import ExecutionContext, ExecutionMode, ExecutionState
from src.agent.runtime.native_adapter import NativeRuntimeAdapter


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_ADOPTION_DECISION = (
    _REPOSITORY_ROOT
    / "docs"
    / "architecture"
    / "pydanticai-runtime-adoption-decision.md"
)
_WORK_TRACKER = _REPOSITORY_ROOT / "docs" / "stockpulse-work-tracker.md"
_MANIFEST = _REPOSITORY_ROOT / "tests" / "fixtures" / "agent_runtime" / "manifest.json"

_HISTORICAL_FULL_EQUIVALENCE_IDS = (
    "a-single-run-normal",
    "hk-single-run-normal",
    "us-single-run-normal",
    "a-single-run-partial",
    "contract-modelref-single-mismatch",
    "contract-fallback-provider-error",
    "contract-toolscope-unknown-tool",
    "contract-malformed-dashboard-repaired",
)
_HISTORICAL_TERMINAL_ONLY_IDS = (
    "contract-timeout-agent-wallclock",
    "contract-cancelrace-single-slow-tool",
    "contract-cancelrace-parallel-late-tool",
)
_HISTORICAL_CONFORMANCE_TABLE = {
    "等价通过（8）": _HISTORICAL_FULL_EQUIVALENCE_IDS,
    "仅终态分类等价（3）": _HISTORICAL_TERMINAL_ONLY_IDS,
    "明确不支持（2 个直接调用）": (
        "ExecutionMode.CHAT",
        "ExecutionMode.RESEARCH",
    ),
}
_RETIRED_EVIDENCE_PATHS = (
    "tests/agent/runtime/test_conformance.py",
    "tests/agent/runtime/test_conformance_replay.py",
    "tests/agent/runtime/test_conformance_leak_scan.py",
)


def _parse_conformance_table(decision):
    section = decision.split("### 3.1 ", 1)[1].split("### 3.2 ", 1)[0]
    entries_by_category = {}

    for line in section.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        columns = tuple(column.strip() for column in stripped.strip("|").split("|"))
        assert len(columns) == 3, f"malformed conformance table row: {line}"
        category, fixtures, _conclusion = columns
        if category in {"类别", "---"}:
            continue
        assert category not in entries_by_category, (
            f"duplicate conformance category: {category}"
        )
        parsed_fixtures = []
        for fixture in fixtures.split("、"):
            match = re.fullmatch(r"`([^`]+)`", fixture.strip())
            assert match is not None, (
                f"malformed conformance fixture entry in {category}: {fixture}"
            )
            parsed_fixtures.append(match.group(1))
        entries_by_category[category] = tuple(parsed_fixtures)

    return entries_by_category


class _RaisingExecutor:
    def __init__(self, error):
        self.error = error

    def run(self, _task, context=None):
        raise self.error


def test_historical_conformance_table_names_exact_fixture_ids_by_category():
    decision = _ADOPTION_DECISION.read_text(encoding="utf-8")
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    cases_by_id = {case["id"]: case for case in manifest["cases"]}
    table = _parse_conformance_table(decision)

    assert table == _HISTORICAL_CONFORMANCE_TABLE
    documented_fixture_ids = (
        *table["等价通过（8）"],
        *table["仅终态分类等价（3）"],
    )
    assert len(documented_fixture_ids) == len(set(documented_fixture_ids))
    assert documented_fixture_ids == (
        *_HISTORICAL_FULL_EQUIVALENCE_IDS,
        *_HISTORICAL_TERMINAL_ONLY_IDS,
    )

    for fixture_id in documented_fixture_ids:
        assert fixture_id in cases_by_id
        assert cases_by_id[fixture_id]["mode"] == "single_run"

    assert "contract-timeout、contract-cancelrace ×2" not in decision
    assert "不得按 `profile` 自动扩展" in decision
    assert "所有非 RUN 模式" not in decision
    assert "`ExecutionMode.CHAT`" in decision
    assert "`ExecutionMode.RESEARCH`" in decision


def test_tracker_keeps_incomplete_runtime_evidence_partial():
    tracker = _WORK_TRACKER.read_text(encoding="utf-8")

    assert (
        "| AR-PY-05 | Conformance / benchmark / 决策门禁 | "
        "**Historical / Partial** |"
    ) in tracker
    assert "AR-PY-05 -> Done" not in tracker
    assert "ADR-001 D5" not in tracker


def test_dependency_footprint_does_not_claim_unreproducible_counts():
    decision = _ADOPTION_DECISION.read_text(encoding="utf-8")

    assert "传递闭包约 22 个包" not in decision
    assert "净新增约 10 个" not in decision
    assert "未保存可复现的双环境依赖快照" in decision


def test_retired_evidence_paths_match_the_native_only_codebase():
    for relative_path in _RETIRED_EVIDENCE_PATHS:
        assert not (_REPOSITORY_ROOT / relative_path).exists()


def test_native_exception_evidence_is_executable_and_fail_closed():
    leaked_api_key = "sk-LEAKED0000key1111secret2222deadbeef"
    leaked_url = "https://user:pw@internal.provider.local/v1/chat"
    leaked_bearer = "Bearer abcdef0123456789abcdef0123456789"
    raw_error = (
        f"request to {leaked_url} failed: authorization={leaked_bearer} "
        f"apikey={leaked_api_key} raw_provider_body="
    ) * 20
    exception = RuntimeError(raw_error)
    adapter = NativeRuntimeAdapter(executor=_RaisingExecutor(exception))
    context = ExecutionContext(mode=ExecutionMode.RUN, prompt="task")

    handle = adapter.start(context)
    try:
        assert handle.wait(timeout=5)
        assert handle.state is ExecutionState.FAILED
        assert handle.result is None
        assert handle.worker_exception is exception
        diagnostic = handle.error or ""
        assert diagnostic
        assert len(diagnostic) <= 300
        for secret in (
            leaked_api_key,
            "internal.provider.local",
            "abcdef0123456789abcdef0123456789",
        ):
            assert secret not in diagnostic
        assert "[REDACTED" in diagnostic
    finally:
        handle.close()

    with pytest.raises(RuntimeError) as excinfo:
        adapter.execute(context)
    assert excinfo.value is exception
