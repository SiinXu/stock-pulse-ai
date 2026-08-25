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
    ACTION_DO_NOT_TRAILER,
    ACTION_MANUAL_TRIAGE,
    ACTION_PORT_NOW,
    ACTION_RECORD_TRAILER,
    ACTION_SKIP_DOCS,
    DEFAULT_TRAILER_TRIAGE,
    DriftInventory,
    KIND_DO_NOT_TRAILER,
    KIND_TRAILER_SAFE,
    apply_trailer_triage,
    build_inventory,
    inventory_attention_commit,
    load_trailer_triage,
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
    assert "scripts/upstream_trailer_triage.json" in (
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


def test_trailer_triage_contract_loads_without_overlap() -> None:
    triage = load_trailer_triage(DEFAULT_TRAILER_TRIAGE)
    assert triage.version == 1
    assert triage.upstream_repo == "ZhuLinsen/daily_stock_analysis"
    assert triage.trailer_safe
    assert triage.do_not_trailer
    safe_shas = {entry.sha for entry in triage.trailer_safe}
    deny_shas = {entry.sha for entry in triage.do_not_trailer}
    assert safe_shas.isdisjoint(deny_shas)
    for entry in (*triage.trailer_safe, *triage.do_not_trailer):
        assert len(entry.sha) >= 7
        assert entry.reason
        assert entry.kind in {KIND_TRAILER_SAFE, KIND_DO_NOT_TRAILER}


def test_do_not_trailer_overrides_high_presence_heuristic() -> None:
    """100% path presence must not authorize a trailer for deny-list SHAs."""
    triage = load_trailer_triage(DEFAULT_TRAILER_TRIAGE)
    deny = next(entry for entry in triage.do_not_trailer if entry.sha.startswith("a54f46e1e"))
    action, rationale, _cluster = suggest_action(
        subject=deny.subject or "ci: temporarily disable automatic PR review",
        paths=(
            ".github/workflows/pr-review.yml",
            "docs/CHANGELOG.md",
            "docs/CONTRIBUTING.md",
            "docs/CONTRIBUTING_EN.md",
        ),
        missing_paths=(),
        presence_ratio=1.0,
    )
    assert action == ACTION_RECORD_TRAILER
    action, rationale, _cluster = apply_trailer_triage(
        sha=deny.sha,
        action=action,
        rationale=rationale,
        cluster="likely-absorbed",
        triage=triage,
    )
    assert action == ACTION_DO_NOT_TRAILER
    assert "pull_request_target" in rationale.lower()
    assert "workflow_dispatch" in rationale.lower()

    commit = UpstreamCommit(
        sha=deny.sha,
        short_sha=deny.sha[:9],
        subject=deny.subject,
        author_date="2026-07-22T00:00:00+00:00",
        paths=(".github/workflows/pr-review.yml", "docs/CHANGELOG.md"),
        status=STATUS_ATTENTION,
        shared_paths=(".github/workflows/pr-review.yml", "docs/CHANGELOG.md"),
    )
    row = inventory_attention_commit(commit, repo=ROOT, trailer_triage=triage)
    assert row.suggested_action == ACTION_DO_NOT_TRAILER


def test_sixteen_e342_pr_review_skip_overrides_high_presence() -> None:
    """16e3421c1 stays do_not_trailer after the API-only #1422 slice."""
    triage = load_trailer_triage(DEFAULT_TRAILER_TRIAGE)
    deny = next(entry for entry in triage.do_not_trailer if entry.sha.startswith("16e3421c1"))
    action, rationale, _cluster = apply_trailer_triage(
        sha=deny.sha,
        action=ACTION_RECORD_TRAILER,
        rationale="Most shared paths exist locally",
        cluster="likely-absorbed",
        triage=triage,
    )
    assert action == ACTION_DO_NOT_TRAILER
    assert "pull_request_target" in rationale.lower()


def test_post_child_absorbed_shas_moved_to_trailer_safe() -> None:
    """#1423/#1424/#1425 product ports must not remain on the deny-list."""
    triage = load_trailer_triage(DEFAULT_TRAILER_TRIAGE)
    absorbed = (
        "cfd6b0a5fb9c57685dc2b02ca059fa88d8eff8ec",
        "40b8c6c3cd6829d3fa4146c7aa64e273387df0e3",
        "ae19329d6684c4ec4ad0b51e627c0c5204ccd594",
    )
    for sha in absorbed:
        entry = triage.lookup(sha)
        assert entry is not None, sha
        assert entry.kind == KIND_TRAILER_SAFE, sha
        action, rationale, _cluster = apply_trailer_triage(
            sha=sha,
            action=ACTION_DO_NOT_TRAILER,
            rationale="stale deny-list reason",
            cluster="stale",
            triage=triage,
        )
        assert action == ACTION_RECORD_TRAILER, sha
        assert rationale == entry.reason


def test_trailer_safe_overrides_missing_renamed_path_heuristic() -> None:
    """Fork-native evaluator rename must not stay port_now after spot-check."""
    triage = load_trailer_triage(DEFAULT_TRAILER_TRIAGE)
    safe = next(entry for entry in triage.trailer_safe if entry.sha.startswith("85ded1d70"))
    action, rationale, cluster = suggest_action(
        subject="feat: add skill opinion outcome evaluation core",
        paths=(
            "src/core/skill_opinion_outcome_evaluator.py",
            "src/services/skill_opinion_outcome_service.py",
            "docs/CHANGELOG.md",
        ),
        missing_paths=("src/core/skill_opinion_outcome_evaluator.py",),
        presence_ratio=0.6,
    )
    assert action == ACTION_PORT_NOW
    action, rationale, cluster = apply_trailer_triage(
        sha=safe.sha,
        action=action,
        rationale=rationale,
        cluster=cluster,
        triage=triage,
    )
    assert action == ACTION_RECORD_TRAILER
    assert "skill_opinion_outcome_evaluator.py" in rationale


def test_render_inventory_includes_do_not_trailer_histogram() -> None:
    inventory = DriftInventory(
        generated_at="2026-08-20T00:00:00Z",
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
        action_counts={ACTION_DO_NOT_TRAILER: 1},
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
    assert ACTION_DO_NOT_TRAILER in markdown
    assert "do not trailer" in markdown.lower()
