# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for upstream drift inventory triage heuristics."""

from __future__ import annotations

from pathlib import Path

from scripts.check_upstream_parity import (
    DEFAULT_WHITELIST,
    STATUS_ATTENTION,
    ParityReport,
    UpstreamCommit,
    load_whitelist,
)
from scripts.inventory_upstream_drift import (
    ACTION_DESIGN_NEEDED,
    ACTION_MANUAL_TRIAGE,
    ACTION_PORT_NOW,
    ACTION_RECORD_TRAILER,
    ACTION_SKIP_DOCS,
    DriftInventory,
    build_inventory,
    inventory_attention_commit,
    main,
    render_inventory_markdown,
    suggest_action,
)


ROOT = Path(__file__).resolve().parents[2]


def test_inventory_script_does_not_expand_upstream_path_whitelist() -> None:
    """Local inventory tooling must not weaken upstream path coverage."""
    whitelist = load_whitelist(DEFAULT_WHITELIST)

    assert "scripts/inventory_upstream_drift.py" not in (
        whitelist.deliberately_diverged_prefixes
    )


def test_skip_docs_for_changelog_only() -> None:
    action, _rationale, _cluster = suggest_action(
        subject="docs: prepare v3.30.0 release",
        paths=("docs/CHANGELOG.md",),
        missing_paths=(),
        presence_ratio=1.0,
    )
    assert action == ACTION_SKIP_DOCS


def test_design_needed_for_codex_prototype() -> None:
    action, rationale, cluster = suggest_action(
        subject="feat: add Codex App Server agent prototype",
        paths=(
            "src/agent/codex_agent_backend.py",
            "api/v1/endpoints/agent.py",
        ),
        missing_paths=("src/agent/codex_agent_backend.py",),
        presence_ratio=0.3,
    )
    assert action == ACTION_DESIGN_NEEDED
    assert "codex" in cluster or "codex" in rationale.lower()


def test_record_trailer_for_high_presence_skill_opinion() -> None:
    action, _rationale, cluster = suggest_action(
        subject="feat: persist skill opinion samples",
        paths=(
            "src/repositories/skill_opinion_sample_repo.py",
            "src/services/skill_opinion_sample_service.py",
            "docs/CHANGELOG.md",
        ),
        missing_paths=("tests/test_skill_opinion_samples.py",),
        presence_ratio=0.9,
    )
    assert action == ACTION_RECORD_TRAILER
    assert cluster == "skill opinion"


def test_port_now_for_small_residual_code_gap() -> None:
    action, _rationale, _cluster = suggest_action(
        subject="fix: small foundation gap",
        paths=("src/core/foo.py", "tests/test_foo.py", "docs/CHANGELOG.md"),
        missing_paths=("src/core/foo.py",),
        presence_ratio=0.66,
    )
    assert action == ACTION_PORT_NOW


def test_manual_triage_for_mixed_presence() -> None:
    action, _rationale, _cluster = suggest_action(
        subject="feat: mixed surface",
        paths=tuple(f"src/services/mod_{i}.py" for i in range(10)),
        missing_paths=tuple(f"src/services/mod_{i}.py" for i in range(5)),
        presence_ratio=0.5,
    )
    assert action in {ACTION_MANUAL_TRIAGE, ACTION_PORT_NOW, ACTION_RECORD_TRAILER}


def test_inventory_attention_commit_docs_row() -> None:
    commit = UpstreamCommit(
        sha="b" * 40,
        short_sha="bbbbbbb",
        subject="docs: add v9.9.9 release changelog",
        author_date="2026-08-01T00:00:00+00:00",
        paths=("docs/CHANGELOG.md",),
        status=STATUS_ATTENTION,
        shared_paths=("docs/CHANGELOG.md",),
    )
    row = inventory_attention_commit(commit, repo=ROOT)
    assert row.suggested_action == ACTION_SKIP_DOCS
    assert row.paths_present == 1
    assert row.paths_total == 1


def test_render_inventory_includes_cadence_and_actions() -> None:
    inventory = DriftInventory(
        generated_at="2026-08-12T00:00:00Z",
        local_ref="origin/main",
        upstream_ref="upstream/main",
        upstream_repo="ZhuLinsen/daily_stock_analysis",
        fork_point="abc123",
        totals={
            "upstream_only_commits": 1,
            "attention": 1,
            "already_ported": 0,
            "informational": 0,
        },
        action_counts={ACTION_SKIP_DOCS: 1},
        attention_rows=[],
        already_ported_count=0,
        informational_count=0,
        cadence={
            "machine_report": "weekly",
            "human_triage": "after refresh",
            "re_run_local": "after ports",
        },
        consumers=["Maintainers triaging #1002"],
        notes=["Path presence is a heuristic."],
    )
    markdown = render_inventory_markdown(inventory)
    assert "Upstream drift inventory" in markdown
    assert "Governance cadence" in markdown
    assert ACTION_SKIP_DOCS in markdown
    assert "#1002" in markdown
    assert "#1061" in markdown


def test_build_inventory_from_empty_attention() -> None:
    report = ParityReport(
        local_ref="HEAD",
        upstream_ref="upstream/main",
        fork_point="0" * 40,
        upstream_repo="ZhuLinsen/daily_stock_analysis",
        generated_at="2026-08-12T00:00:00Z",
        commits=[],
    )
    inventory = build_inventory(report, repo=ROOT)
    assert inventory.totals["attention"] == 0
    assert inventory.attention_rows == []


def test_self_test_cli_exit_zero() -> None:
    assert main(["--self-test"]) == 0
