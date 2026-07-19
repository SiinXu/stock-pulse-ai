# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Guards for retired cross-runtime evidence and its documented limits."""

import json
from pathlib import Path


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
_RETIRED_EVIDENCE_PATHS = (
    "tests/agent/runtime/test_conformance.py",
    "tests/agent/runtime/test_conformance_replay.py",
    "tests/agent/runtime/test_conformance_leak_scan.py",
)


def test_historical_conformance_evidence_names_exact_fixture_ids():
    decision = _ADOPTION_DECISION.read_text(encoding="utf-8")
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    cases_by_id = {case["id"]: case for case in manifest["cases"]}

    for fixture_id in (
        *_HISTORICAL_FULL_EQUIVALENCE_IDS,
        *_HISTORICAL_TERMINAL_ONLY_IDS,
    ):
        assert fixture_id in cases_by_id
        assert cases_by_id[fixture_id]["mode"] == "single_run"
        assert f"`{fixture_id}`" in decision

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

    assert (
        _REPOSITORY_ROOT / "tests" / "agent" / "runtime" / "test_native_adapter.py"
    ).is_file()
