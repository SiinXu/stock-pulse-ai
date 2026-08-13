#!/usr/bin/env python3
"""Build an actionable upstream drift inventory for maintainer triage.

Complements ``scripts/check_upstream_parity.py`` (commit classification +
``Ported-from`` matching) with a path-presence inventory:

* What upstream changed (Attention commits and shared paths)
* What this repository already has on disk (path exists vs missing)
* Suggested triage action (port / design / record trailer / skip docs / manual)

This script never merges upstream and never opens issues. It is intended for
weekly consumption after the ``upstream-parity`` workflow refreshes #1002.

Example::

    python scripts/inventory_upstream_drift.py \\
      --local-ref origin/main \\
      --upstream-ref upstream/main \\
      --output /tmp/upstream-drift-inventory.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

# Allow ``python scripts/inventory_upstream_drift.py`` without PYTHONPATH hacks.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_upstream_parity import (  # noqa: E402
    DEFAULT_LOCAL_REF,
    DEFAULT_UPSTREAM_REF,
    DEFAULT_UPSTREAM_REMOTE,
    DEFAULT_UPSTREAM_URL,
    DEFAULT_WHITELIST,
    STATUS_ATTENTION,
    ParityError,
    ParityReport,
    UpstreamCommit,
    collect_parity_report,
    ensure_upstream_remote,
    load_whitelist,
)

ACTION_PORT_NOW = "port_now"
ACTION_DESIGN_NEEDED = "design_needed"
ACTION_RECORD_TRAILER = "record_trailer"
ACTION_SKIP_DOCS = "skip_docs"
ACTION_MANUAL_TRIAGE = "manual_triage"

_DOCS_ONLY_NAMES = frozenset(
    {
        "README.md",
        "THIRD_PARTY_NOTICES.md",
        "docs/CHANGELOG.md",
    }
)

_DESIGN_MARKERS = (
    "codex_app_server",
    "codex_agent_backend",
    "codex_tool_process",
    "agent_backend.py",
    "AgentBackendStatusPanel",
)

_FORK_NATIVE_CLUSTERS = (
    ("skill opinion", ("skill_opinion", "multi-strategy")),
    ("decision profile", ("decision_signal", "decision_profile", "decisionSignals")),
    ("screening / alphasift", ("screening", "alphasift")),
    ("share image", ("share_image", "ShareImage", "md2img")),
    ("responses api", ("LLMChannel", "provider_cache", "responses")),
    ("session skill", ("agent_chat_session", "ChatPage", "agentChatStore")),
)


@dataclass(frozen=True)
class PathPresence:
    """Local disk presence for one shared path from an upstream commit."""

    path: str
    exists: bool


@dataclass
class AttentionInventoryRow:
    """One Attention commit with inventory fields for maintainers."""

    sha: str
    short_sha: str
    subject: str
    author_date: str
    shared_paths: tuple[str, ...]
    paths_total: int
    paths_present: int
    paths_missing: int
    presence_ratio: float
    missing_paths: tuple[str, ...]
    present_paths_sample: tuple[str, ...]
    top_areas: tuple[str, ...]
    suggested_action: str
    rationale: str
    cluster: str = ""


@dataclass
class DriftInventory:
    """Full inventory payload."""

    generated_at: str
    local_ref: str
    upstream_ref: str
    upstream_repo: str
    fork_point: str
    totals: dict[str, int]
    action_counts: dict[str, int]
    attention_rows: list[AttentionInventoryRow] = field(default_factory=list)
    already_ported_count: int = 0
    informational_count: int = 0
    cadence: dict[str, str] = field(default_factory=dict)
    consumers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _path_area(path: str) -> str:
    normalized = path.replace("\\", "/").lstrip("./")
    if "/" not in normalized:
        return normalized
    return normalized.split("/", 1)[0]


def _is_docs_only_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    if normalized in _DOCS_ONLY_NAMES:
        return True
    if normalized.startswith("docs/") and (
        normalized.endswith(".md") or normalized.startswith("docs/assets/")
    ):
        return True
    if normalized.startswith("docs/README"):
        return True
    return False


def _docs_only_paths(paths: Sequence[str]) -> bool:
    if not paths:
        return True
    return all(_is_docs_only_path(path) for path in paths)


def _looks_like_release_changelog(subject: str, paths: Sequence[str]) -> bool:
    if set(paths) <= {"docs/CHANGELOG.md"}:
        return True
    lowered = subject.lower()
    return bool(
        re.search(r"\bv\d+\.\d+", lowered)
        and "changelog" in lowered
        and _docs_only_paths(paths)
    )


def _has_design_marker(paths: Sequence[str], subject: str) -> bool:
    blob = " ".join(paths) + " " + subject
    return any(marker in blob for marker in _DESIGN_MARKERS)


def _match_fork_native_cluster(subject: str, paths: Sequence[str]) -> str:
    blob = (subject + " " + " ".join(paths)).lower()
    for name, markers in _FORK_NATIVE_CLUSTERS:
        if any(marker.lower() in blob for marker in markers):
            return name
    return ""


def suggest_action(
    *,
    subject: str,
    paths: Sequence[str],
    missing_paths: Sequence[str],
    presence_ratio: float,
) -> tuple[str, str, str]:
    """Return ``(action, rationale, cluster)`` for one Attention commit."""
    cluster = _match_fork_native_cluster(subject, paths)

    if _looks_like_release_changelog(subject, paths) or (
        _docs_only_paths(paths) and "changelog" in subject.lower()
    ):
        return (
            ACTION_SKIP_DOCS,
            "Docs/changelog-only surface; do not port upstream release notes as-is.",
            cluster or "docs",
        )

    if _docs_only_paths(paths):
        return (
            ACTION_SKIP_DOCS,
            "Shared paths are documentation or marketing only.",
            cluster or "docs",
        )

    if _has_design_marker(paths, subject):
        return (
            ACTION_DESIGN_NEEDED,
            "Touches a large product prototype (e.g. Codex App Server); "
            "needs a design issue before any port.",
            cluster or "codex-app-server",
        )

    if presence_ratio >= 0.75 and len(missing_paths) <= 4:
        if cluster:
            return (
                ACTION_RECORD_TRAILER,
                f"Most shared paths exist locally (ratio={presence_ratio:.0%}); "
                f"treat as already absorbed under cluster '{cluster}' and add "
                "Ported-from trailers after a quick semantic spot-check.",
                cluster,
            )
        return (
            ACTION_RECORD_TRAILER,
            f"Most shared paths exist locally (ratio={presence_ratio:.0%}); "
            "spot-check behavior, then record Ported-from trailers.",
            cluster or "likely-absorbed",
        )

    if presence_ratio <= 0.35 and any(
        p.startswith("src/") or p.startswith("api/") or p.startswith("data_provider/")
        for p in missing_paths
    ):
        if len(paths) <= 12:
            return (
                ACTION_PORT_NOW,
                "Many foundation shared paths are missing locally; "
                "candidate for a focused port PR with tests.",
                cluster or "missing-foundation",
            )
        return (
            ACTION_MANUAL_TRIAGE,
            "Many foundation paths missing and change surface is large; "
            "manual triage required.",
            cluster or "missing-foundation",
        )

    if 0 < len(missing_paths) <= 6 and presence_ratio >= 0.5:
        code_missing = [
            p
            for p in missing_paths
            if p.startswith("src/")
            or p.startswith("api/")
            or p.startswith("data_provider/")
        ]
        if code_missing and len(code_missing) <= 3:
            return (
                ACTION_PORT_NOW,
                "Small residual shared-code gap against an otherwise present surface; "
                "prefer a focused port with regression tests.",
                cluster or "residual-gap",
            )

    return (
        ACTION_MANUAL_TRIAGE,
        "Path presence is mixed; maintainer must classify Port / Design / Skip.",
        cluster or "mixed",
    )


def inventory_attention_commit(
    commit: UpstreamCommit,
    *,
    repo: Path,
) -> AttentionInventoryRow:
    """Enrich one Attention commit with local path presence and triage."""
    shared = commit.shared_paths or commit.paths
    presence: list[PathPresence] = []
    for path in shared:
        exists = (repo / path).exists()
        presence.append(PathPresence(path=path, exists=exists))

    present = [p.path for p in presence if p.exists]
    missing = [p.path for p in presence if not p.exists]
    total = len(presence)
    present_n = len(present)
    missing_n = len(missing)
    ratio = (present_n / total) if total else 1.0

    area_counts = Counter(_path_area(p) for p in shared)
    top_areas = tuple(area for area, _ in area_counts.most_common(6))

    action, rationale, cluster = suggest_action(
        subject=commit.subject,
        paths=shared,
        missing_paths=missing,
        presence_ratio=ratio,
    )

    return AttentionInventoryRow(
        sha=commit.sha,
        short_sha=commit.short_sha,
        subject=commit.subject,
        author_date=commit.author_date,
        shared_paths=tuple(shared),
        paths_total=total,
        paths_present=present_n,
        paths_missing=missing_n,
        presence_ratio=round(ratio, 4),
        missing_paths=tuple(missing[:20]),
        present_paths_sample=tuple(present[:8]),
        top_areas=top_areas,
        suggested_action=action,
        rationale=rationale,
        cluster=cluster,
    )


def build_inventory(
    report: ParityReport,
    *,
    repo: Path,
) -> DriftInventory:
    """Build the drift inventory from a parity report."""
    rows = [
        inventory_attention_commit(commit, repo=repo) for commit in report.attention
    ]
    action_counts = Counter(row.suggested_action for row in rows)
    return DriftInventory(
        generated_at=report.generated_at
        or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        local_ref=report.local_ref,
        upstream_ref=report.upstream_ref,
        upstream_repo=report.upstream_repo,
        fork_point=report.fork_point,
        totals={
            "upstream_only_commits": len(report.commits),
            "attention": len(report.attention),
            "already_ported": len(report.already_ported),
            "informational": len(report.informational),
        },
        action_counts=dict(action_counts),
        attention_rows=rows,
        already_ported_count=len(report.already_ported),
        informational_count=len(report.informational),
        cadence={
            "machine_report": (
                "Weekly Monday 04:00 UTC via `.github/workflows/upstream-parity.yml` "
                "(plus workflow_dispatch). Updates tracking issue #1002 in place."
            ),
            "human_triage": (
                "Within a few days of each #1002 refresh: triage Attention using this "
                "inventory; open or update child issues; never half-port entangled "
                "clusters."
            ),
            "re_run_local": (
                "After port PRs land: re-run this script and "
                "`scripts/check_upstream_parity.py` so Attention shrinks."
            ),
        },
        consumers=[
            "Maintainers triaging #1002 (upstream-parity tracking issue)",
            "Issue #1061 cadence owners (Port now / DESIGN-NEEDED / Whitelist)",
            "Port PR authors who need a prioritized residual-gap list",
        ],
        notes=[
            "Path presence is a heuristic, not semantic equivalence. "
            "Fork-native renames (e.g. screening → alphasift, share_image package) "
            "can show missing upstream paths while behavior is already absorbed.",
            "Suggested actions never replace maintainer judgment for foundation ports.",
            "Record Ported-from: ZhuLinsen/daily_stock_analysis@<sha> only after a "
            "semantic spot-check confirms the intent is covered.",
        ],
    )


def _md_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_inventory_markdown(inventory: DriftInventory) -> str:
    """Render the human-readable inventory report (English)."""
    lines: list[str] = [
        "# Upstream drift inventory",
        "",
        "Actionable maintainer inventory for `ZhuLinsen/daily_stock_analysis` drift. "
        "Machine commit classification remains the source of truth in "
        "`scripts/check_upstream_parity.py` and tracking issue **#1002**. "
        "Governance cadence: **#1061**.",
        "",
        f"- Generated at (UTC): `{inventory.generated_at}`",
        f"- Local ref: `{inventory.local_ref}`",
        f"- Upstream ref: `{inventory.upstream_ref}`",
        f"- Upstream repository: `{inventory.upstream_repo}`",
        f"- Fork point (merge-base): `{inventory.fork_point}`",
        f"- Upstream-only commits: **{inventory.totals.get('upstream_only_commits', 0)}**",
        f"- Attention (shared paths, not ported): **{inventory.totals.get('attention', 0)}**",
        f"- Already ported (`Ported-from`): **{inventory.already_ported_count}**",
        f"- Informational (whitelist-only): **{inventory.informational_count}**",
        "",
        "## What upstream has vs this repository",
        "",
        "| Dimension | Upstream (since fork point) | This repository |",
        "| --- | --- | --- |",
        (
            f"| Commits only on upstream | {inventory.totals.get('upstream_only_commits', 0)} "
            f"| n/a (local has its own history) |"
        ),
        (
            f"| Unported shared-path commits (Attention) | "
            f"{inventory.totals.get('attention', 0)} | "
            "Needs triage (table below) |"
        ),
        (
            f"| Matched `Ported-from` trailers | n/a | "
            f"{inventory.already_ported_count} upstream SHAs marked ported |"
        ),
        (
            f"| Deliberately diverged only | {inventory.informational_count} | "
            "Expected product/governance divergence |"
        ),
        "",
        "### Suggested-action histogram (Attention only)",
        "",
        "| Suggested action | Count | Meaning |",
        "| --- | --- | --- |",
        (
            f"| `{ACTION_PORT_NOW}` | {inventory.action_counts.get(ACTION_PORT_NOW, 0)} | "
            "Focused foundation fix; port with tests + `Ported-from` |"
        ),
        (
            f"| `{ACTION_DESIGN_NEEDED}` | {inventory.action_counts.get(ACTION_DESIGN_NEEDED, 0)} | "
            "Entangled product prototype; design issue first |"
        ),
        (
            f"| `{ACTION_RECORD_TRAILER}` | {inventory.action_counts.get(ACTION_RECORD_TRAILER, 0)} | "
            "Likely already absorbed; spot-check then record trailers |"
        ),
        (
            f"| `{ACTION_SKIP_DOCS}` | {inventory.action_counts.get(ACTION_SKIP_DOCS, 0)} | "
            "Docs/changelog/marketing only; do not mirror blindly |"
        ),
        (
            f"| `{ACTION_MANUAL_TRIAGE}` | {inventory.action_counts.get(ACTION_MANUAL_TRIAGE, 0)} | "
            "Mixed signal; human classification required |"
        ),
        "",
        "## Difference list (Attention commits)",
        "",
        "For each Attention commit: upstream subject, local path presence, missing "
        "shared paths, and suggested action. **Do not treat this table as closed "
        "work** — open or update child issues for real residual gaps.",
        "",
        "| SHA | Date | Subject | Present/Total | Suggested action | Cluster | Missing sample |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]

    for row in inventory.attention_rows:
        missing_sample = ", ".join(row.missing_paths[:3]) or "—"
        if len(row.missing_paths) > 3:
            missing_sample += f", … (+{len(row.missing_paths) - 3})"
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row.short_sha}`",
                    _md_escape(row.author_date[:10]),
                    _md_escape(row.subject[:80]),
                    f"{row.paths_present}/{row.paths_total} ({row.presence_ratio:.0%})",
                    f"`{row.suggested_action}`",
                    _md_escape(row.cluster or "—"),
                    _md_escape(missing_sample),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "### Per-commit rationale (Attention)",
            "",
        ]
    )
    if not inventory.attention_rows:
        lines.append("_No Attention commits since the fork point._")
        lines.append("")
    else:
        for row in inventory.attention_rows:
            lines.append(f"#### `{row.short_sha}` — {_md_escape(row.subject)}")
            lines.append("")
            lines.append(f"- Date: `{row.author_date[:10]}`")
            lines.append(
                f"- Areas: {', '.join(f'`{a}`' for a in row.top_areas) or '—'}"
            )
            lines.append(
                f"- Local path presence: **{row.paths_present}/{row.paths_total}** "
                f"({row.presence_ratio:.0%})"
            )
            lines.append(f"- Suggested action: **`{row.suggested_action}`**")
            lines.append(f"- Rationale: {row.rationale}")
            if row.missing_paths:
                lines.append("- Missing shared paths (sample):")
                for path in row.missing_paths[:10]:
                    lines.append(f"  - `{path}`")
            if row.present_paths_sample:
                lines.append("- Present shared paths (sample):")
                for path in row.present_paths_sample[:6]:
                    lines.append(f"  - `{path}`")
            lines.append("")

    lines.extend(
        [
            "## Governance cadence (who / when)",
            "",
            f"- **Machine report:** {inventory.cadence.get('machine_report', '')}",
            f"- **Human triage:** {inventory.cadence.get('human_triage', '')}",
            f"- **After ports:** {inventory.cadence.get('re_run_local', '')}",
            "",
            "### Consumers",
            "",
        ]
    )
    for consumer in inventory.consumers:
        lines.append(f"- {consumer}")
    lines.extend(
        [
            "",
            "### Recommended run frequency",
            "",
            "1. **Weekly** (or on each `upstream-parity` workflow run): generate this "
            "inventory after #1002 refreshes.",
            "2. **On demand** before planning a port wave: re-run with `--fetch` to "
            "pick up new upstream commits.",
            "3. **After merge of port PRs**: re-run to confirm Attention shrinks and "
            "trailers match.",
            "",
            "## Notes and limits",
            "",
        ]
    )
    for note in inventory.notes:
        lines.append(f"- {note}")
    lines.extend(
        [
            "",
            "## Local commands",
            "",
            "```bash",
            "python scripts/check_upstream_parity.py --self-test",
            "python scripts/inventory_upstream_drift.py --self-test",
            "python scripts/inventory_upstream_drift.py \\",
            "  --fetch \\",
            "  --local-ref origin/main \\",
            "  --upstream-ref upstream/main \\",
            "  --output /tmp/upstream-drift-inventory.md",
            "```",
            "",
            "Related docs: [Upstream Parity Checker](../upstream-parity.md), "
            "tracking issue #1002, cadence issue #1061.",
            "",
        ]
    )
    return "\n".join(lines)


def inventory_to_jsonable(inventory: DriftInventory) -> dict:
    """Convert inventory dataclass tree to JSON-serializable dict."""
    return asdict(inventory)


def run_self_tests() -> None:
    """Lightweight offline regressions for triage heuristics."""
    cases = 0

    action, _rationale, _cluster = suggest_action(
        subject="docs: prepare v3.30.0 release",
        paths=("docs/CHANGELOG.md",),
        missing_paths=(),
        presence_ratio=1.0,
    )
    assert action == ACTION_SKIP_DOCS, action
    cases += 1

    action, rationale, cluster = suggest_action(
        subject="feat: add Codex App Server agent prototype",
        paths=(
            "src/agent/codex_agent_backend.py",
            "src/agent/codex_app_server_transport.py",
            "api/v1/endpoints/agent.py",
        ),
        missing_paths=(
            "src/agent/codex_agent_backend.py",
            "src/agent/codex_app_server_transport.py",
        ),
        presence_ratio=0.2,
    )
    assert action == ACTION_DESIGN_NEEDED, action
    assert "codex" in cluster or "codex" in rationale.lower()
    cases += 1

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
    assert action == ACTION_RECORD_TRAILER, action
    assert cluster == "skill opinion"
    cases += 1

    action, _rationale, _cluster = suggest_action(
        subject="fix: split level-one headings without recursion",
        paths=("src/formatters.py", "tests/test_formatters.py", "docs/CHANGELOG.md"),
        missing_paths=(),
        presence_ratio=1.0,
    )
    assert action == ACTION_RECORD_TRAILER, action
    cases += 1

    action, _rationale, _cluster = suggest_action(
        subject="fix: small foundation gap",
        paths=("src/core/foo.py", "tests/test_foo.py", "docs/CHANGELOG.md"),
        missing_paths=("src/core/foo.py",),
        presence_ratio=0.66,
    )
    assert action == ACTION_PORT_NOW, action
    cases += 1

    commit = UpstreamCommit(
        sha="a" * 40,
        short_sha="aaaaaaa",
        subject="docs: add v9.9.9 release changelog",
        author_date="2026-08-01T00:00:00+00:00",
        paths=("docs/CHANGELOG.md",),
        status=STATUS_ATTENTION,
        shared_paths=("docs/CHANGELOG.md",),
    )
    row = inventory_attention_commit(commit, repo=ROOT)
    assert row.suggested_action == ACTION_SKIP_DOCS
    assert row.paths_present == 1
    cases += 1

    print(f"Upstream drift inventory self-tests passed ({cases} cases).")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--whitelist", type=Path, default=DEFAULT_WHITELIST)
    parser.add_argument("--local-ref", default=DEFAULT_LOCAL_REF)
    parser.add_argument("--upstream-ref", default=DEFAULT_UPSTREAM_REF)
    parser.add_argument("--upstream-remote", default=DEFAULT_UPSTREAM_REMOTE)
    parser.add_argument("--upstream-url", default=DEFAULT_UPSTREAM_URL)
    parser.add_argument(
        "--fetch",
        action="store_true",
        default=False,
        help="Fetch the upstream remote before comparing (network; default: off)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write Markdown inventory to this path (also prints to stdout)",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Optional JSON inventory path for tooling",
    )
    parser.add_argument("--self-test", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.self_test:
        run_self_tests()
        return 0

    repo = args.repo.resolve()
    if not (repo / ".git").exists() and not (repo / ".git").is_file():
        # worktree: .git is a file; resolve parent gitdir via git rev-parse below
        # but still require a git-controlled tree.
        from subprocess import run

        probe = run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode != 0 or probe.stdout.strip() != "true":
            print(f"ERROR: not a git repository: {repo}", file=sys.stderr)
            return 2

    try:
        whitelist = load_whitelist(args.whitelist.resolve())
        if args.fetch:
            ensure_upstream_remote(
                repo,
                remote=args.upstream_remote,
                url=args.upstream_url,
                fetch=True,
            )
        report = collect_parity_report(
            repo,
            whitelist=whitelist,
            local_ref=args.local_ref,
            upstream_ref=args.upstream_ref,
        )
        inventory = build_inventory(report, repo=repo)
        markdown = render_inventory_markdown(inventory)

        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(markdown, encoding="utf-8")
        if args.json_output is not None:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(
                json.dumps(
                    inventory_to_jsonable(inventory), indent=2, ensure_ascii=False
                )
                + "\n",
                encoding="utf-8",
            )
        print(markdown)
        return 0
    except ParityError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
