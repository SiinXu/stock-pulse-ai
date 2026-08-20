# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for upstream parity path classification and Ported-from matching."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_upstream_parity import (
    STATUS_ATTENTION,
    STATUS_INFORMATIONAL,
    STATUS_PORTED,
    build_ported_index,
    classify_paths,
    list_local_commit_messages,
    load_whitelist,
    main,
    match_ported_by,
    parse_ported_from_trailers,
    path_is_deliberately_diverged,
    render_issue_summary,
    render_markdown_report,
    ParityReport,
    UpstreamCommit,
    WhitelistConfig,
)
from scripts.inventory_upstream_drift import (
    DEFAULT_TRAILER_TRIAGE,
    load_trailer_triage,
)


ROOT = Path(__file__).resolve().parents[2]
WHITELIST_PATH = ROOT / "scripts" / "upstream_parity_whitelist.json"


def test_repository_whitelist_loads() -> None:
    config = load_whitelist(WHITELIST_PATH)
    assert config.version == 1
    assert config.upstream_repo == "ZhuLinsen/daily_stock_analysis"
    assert config.deliberately_diverged_prefixes
    assert any(
        prefix.startswith("apps/dsa-desktop")
        for prefix in config.deliberately_diverged_prefixes
    )


def test_path_prefix_matching_directory_and_file() -> None:
    prefixes = ("apps/dsa-desktop/", "AGENTS.md", "examples/")
    assert path_is_deliberately_diverged("apps/dsa-desktop/package.json", prefixes)
    assert path_is_deliberately_diverged("apps/dsa-desktop", prefixes)
    assert path_is_deliberately_diverged("AGENTS.md", prefixes)
    assert path_is_deliberately_diverged("examples/foo.py", prefixes)
    assert not path_is_deliberately_diverged("AGENTS.md.bak", prefixes)
    assert not path_is_deliberately_diverged("src/core/pipeline.py", prefixes)
    assert not path_is_deliberately_diverged("apps/dsa-web/src/App.tsx", prefixes)


def test_classify_paths_shared_vs_informational() -> None:
    prefixes = ("apps/dsa-desktop/", "examples/")
    status, shared, diverged = classify_paths(
        ["apps/dsa-desktop/main.ts", "examples/x.py"], prefixes
    )
    assert status == STATUS_INFORMATIONAL
    assert shared == ()
    assert set(diverged) == {"apps/dsa-desktop/main.ts", "examples/x.py"}

    status, shared, diverged = classify_paths(
        ["src/services/foo.py", "examples/x.py"], prefixes
    )
    assert status == STATUS_ATTENTION
    assert shared == ("src/services/foo.py",)
    assert diverged == ("examples/x.py",)

    status, shared, diverged = classify_paths([], prefixes)
    assert status == STATUS_INFORMATIONAL
    assert shared == () and diverged == ()


def test_parse_ported_from_trailers_filters_repo_and_length() -> None:
    message = "\n".join(
        [
            "fix: port provider health",
            "",
            "Ported-from: ZhuLinsen/daily_stock_analysis@91988da1",
            "Ported-from: ZhuLinsen/daily_stock_analysis@ee3d3da1deadbeef",
            "Ported-from: other/repo@abcdef012345",
            "Ported-from: ZhuLinsen/daily_stock_analysis@abc",
            "Not-a-trailer: ZhuLinsen/daily_stock_analysis@ffffffff",
        ]
    )
    found = parse_ported_from_trailers(
        message, upstream_repo="ZhuLinsen/daily_stock_analysis"
    )
    assert found == ["91988da1", "ee3d3da1deadbeef"]


def test_malformed_ported_from_without_repo_does_not_match() -> None:
    """Missing repo@ trailers must not mark upstream SHAs already ported."""
    message = "\n".join(
        [
            "refactor: split the chat page and persist session skill selection",
            "",
            "Ported-from: ed848da6",
            "Ported-from: ae19329d",
            "Ported-from: e430fcfe48016a33399c37efcd2ffb20d79b9a43",
            "Ported-from: 4dda5d71",
        ]
    )
    found = parse_ported_from_trailers(
        message, upstream_repo="ZhuLinsen/daily_stock_analysis"
    )
    assert found == []
    index = build_ported_index(
        [message], upstream_repo="ZhuLinsen/daily_stock_analysis"
    )
    assert match_ported_by("ed848da6f0fc1080e1a61a1799b9c7d510a3eaca", index) == []
    assert match_ported_by("ae19329d6684c4ec4ad0b51e627c0c5204ccd594", index) == []
    assert match_ported_by("e430fcfe48016a33399c37efcd2ffb20d79b9a43", index) == []


def test_match_ported_by_prefix() -> None:
    index = build_ported_index(
        [
            "fix: a\n\nPorted-from: ZhuLinsen/daily_stock_analysis@91988da1\n",
            "fix: b\n\nPorted-from: ZhuLinsen/daily_stock_analysis@ee3d3da\n",
        ],
        upstream_repo="ZhuLinsen/daily_stock_analysis",
    )
    matched = match_ported_by("91988da1be2ad4e1ac122d35067b8c63648b8025", index)
    assert matched == ["fix: a"]
    assert match_ported_by("ffffffffffffffffffffffffffffffffffffffff", index) == []


def test_render_markdown_sections() -> None:
    whitelist = WhitelistConfig(
        version=1,
        upstream_repo="ZhuLinsen/daily_stock_analysis",
        deliberately_diverged_prefixes=("examples/",),
    )
    report = ParityReport(
        local_ref="HEAD",
        upstream_ref="upstream/main",
        fork_point="abc1234",
        upstream_repo=whitelist.upstream_repo,
        generated_at="2026-08-05T00:00:00Z",
        commits=[
            UpstreamCommit(
                sha="1" * 40,
                short_sha="1111111",
                subject="shared fix",
                author_date="2026-08-01T00:00:00+00:00",
                paths=("src/core/x.py",),
                status=STATUS_ATTENTION,
                shared_paths=("src/core/x.py",),
            ),
            UpstreamCommit(
                sha="2" * 40,
                short_sha="2222222",
                subject="examples only",
                author_date="2026-08-02T00:00:00+00:00",
                paths=("examples/demo.py",),
                status=STATUS_INFORMATIONAL,
                diverged_paths=("examples/demo.py",),
            ),
            UpstreamCommit(
                sha="3" * 40,
                short_sha="3333333",
                subject="already taken",
                author_date="2026-08-03T00:00:00+00:00",
                paths=("src/core/y.py",),
                status=STATUS_PORTED,
                shared_paths=("src/core/y.py",),
                ported_by=("fix: port y",),
            ),
        ],
    )
    markdown = render_markdown_report(report, whitelist=whitelist)
    assert "Attention (shared paths)" in markdown
    assert "`1111111`" in markdown
    assert "Already ported" in markdown
    assert "`3333333`" in markdown
    assert "Informational" in markdown
    assert "`2222222`" in markdown
    summary = render_issue_summary(report)
    assert "<!-- upstream-parity-tracking-issue -->" in summary
    assert "Attention: **1**" in summary


def test_load_whitelist_rejects_invalid(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"version": 2}), encoding="utf-8")
    with pytest.raises(Exception, match="unsupported whitelist version"):
        load_whitelist(path)


def test_self_test_exit_zero() -> None:
    assert main(["--self-test"]) == 0


def test_trailer_safe_shas_have_well_formed_trailers_on_head() -> None:
    """Real risk layer: trailer_safe SHAs must match git Ported-from trailers."""
    triage = load_trailer_triage(DEFAULT_TRAILER_TRIAGE)
    messages = list_local_commit_messages(ROOT, "HEAD")
    index = build_ported_index(
        messages, upstream_repo="ZhuLinsen/daily_stock_analysis"
    )
    missing = [
        entry.sha
        for entry in triage.trailer_safe
        if not match_ported_by(entry.sha, index)
    ]
    assert missing == [], f"trailer_safe SHAs missing well-formed trailers: {missing}"


def test_do_not_trailer_shas_are_not_ported_on_head() -> None:
    """Real risk layer: do_not_trailer SHAs must stay unported on this head."""
    triage = load_trailer_triage(DEFAULT_TRAILER_TRIAGE)
    messages = list_local_commit_messages(ROOT, "HEAD")
    index = build_ported_index(
        messages, upstream_repo="ZhuLinsen/daily_stock_analysis"
    )
    leaked = [
        (entry.sha, match_ported_by(entry.sha, index))
        for entry in triage.do_not_trailer
        if match_ported_by(entry.sha, index)
    ]
    assert leaked == [], f"do_not_trailer SHAs unexpectedly marked ported: {leaked}"


DATE_FREEZE_SHA = "5c964bf23bade6571d09a085fc42199882b77f8f"


def _triage_contains(entries, sha: str) -> bool:
    return any(sha.startswith(entry.sha) or entry.sha.startswith(sha[:9]) for entry in entries)


def test_date_freeze_sha_absorbed_on_main_is_not_denied_or_duplicated() -> None:
    """#1413 already trailered 5c964bf23; do not false-exclude or re-trailer it here."""
    triage = load_trailer_triage(DEFAULT_TRAILER_TRIAGE)
    assert not _triage_contains(triage.do_not_trailer, DATE_FREEZE_SHA)
    assert not _triage_contains(triage.trailer_safe, DATE_FREEZE_SHA)
    messages = list_local_commit_messages(ROOT, "HEAD")
    index = build_ported_index(
        messages, upstream_repo="ZhuLinsen/daily_stock_analysis"
    )
    assert match_ported_by(DATE_FREEZE_SHA, index), (
        "5c964bf23 must stay already ported via the #1413 well-formed trailer"
    )
