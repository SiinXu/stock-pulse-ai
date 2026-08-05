#!/usr/bin/env python3
"""Report upstream-only commit drift against StockPulse (manual port workflow).

Upstream is treated as a read-only reference repository. This checker:

1. Finds the merge-base (fork point) between the local and upstream refs.
2. Lists commits that exist only on upstream since that fork point.
3. Classifies each commit by changed paths against a maintained whitelist of
   deliberately diverged prefixes (informational) vs shared paths (attention).
4. Cross-references local ``Ported-from: <upstream_repo>@<sha>`` trailers so
   already-ported upstream commits are marked separately.
5. Emits a Markdown drift report for humans and the weekly workflow.

Network fetch is optional and intended for the scheduled workflow, not the
offline CI gate. Use ``--self-test`` for fixture-repo regressions.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WHITELIST = ROOT / "scripts" / "upstream_parity_whitelist.json"
DEFAULT_UPSTREAM_REMOTE = "upstream"
DEFAULT_UPSTREAM_URL = "https://github.com/ZhuLinsen/daily_stock_analysis.git"
DEFAULT_LOCAL_REF = "HEAD"
DEFAULT_UPSTREAM_REF = "upstream/main"
MIN_PORTED_SHA_LEN = 7

PORTED_FROM_RE = re.compile(
    r"^Ported-from:\s*(?P<repo>[^\s@]+)@(?P<sha>[0-9a-fA-F]{7,40})\s*$",
    re.MULTILINE,
)

STATUS_ATTENTION = "attention"
STATUS_INFORMATIONAL = "informational"
STATUS_PORTED = "already_ported"


@dataclass(frozen=True)
class WhitelistConfig:
    """Loaded path-classification policy."""

    version: int
    upstream_repo: str
    deliberately_diverged_prefixes: tuple[str, ...]
    description: str = ""


@dataclass(frozen=True)
class UpstreamCommit:
    """One upstream-only commit with classification metadata."""

    sha: str
    short_sha: str
    subject: str
    author_date: str
    paths: tuple[str, ...]
    status: str
    shared_paths: tuple[str, ...] = ()
    diverged_paths: tuple[str, ...] = ()
    ported_by: tuple[str, ...] = ()


@dataclass
class ParityReport:
    """Structured parity scan result."""

    local_ref: str
    upstream_ref: str
    fork_point: str
    upstream_repo: str
    generated_at: str
    commits: list[UpstreamCommit] = field(default_factory=list)
    ported_sha_index: dict[str, list[str]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def attention(self) -> list[UpstreamCommit]:
        return [c for c in self.commits if c.status == STATUS_ATTENTION]

    @property
    def informational(self) -> list[UpstreamCommit]:
        return [c for c in self.commits if c.status == STATUS_INFORMATIONAL]

    @property
    def already_ported(self) -> list[UpstreamCommit]:
        return [c for c in self.commits if c.status == STATUS_PORTED]


class ParityError(RuntimeError):
    """Fatal parity-check failure."""


def _run_git(
    args: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the completed process."""
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=False,
        text=True,
        capture_output=True,
    )
    if check and completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise ParityError(
            f"git {' '.join(args)} failed (exit {completed.returncode}): {stderr}"
        )
    return completed


def load_whitelist(path: Path) -> WhitelistConfig:
    """Load and validate the deliberately-diverged path whitelist."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ParityError(f"whitelist not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ParityError(f"invalid whitelist JSON: {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ParityError("whitelist root must be an object")

    version = raw.get("version")
    if version != 1:
        raise ParityError(f"unsupported whitelist version: {version!r}")

    upstream_repo = raw.get("upstream_repo")
    if not isinstance(upstream_repo, str) or not upstream_repo.strip():
        raise ParityError("whitelist.upstream_repo must be a non-empty string")

    prefixes = raw.get("deliberately_diverged_prefixes")
    if not isinstance(prefixes, list) or not prefixes:
        raise ParityError(
            "whitelist.deliberately_diverged_prefixes must be a non-empty list"
        )
    cleaned: list[str] = []
    for item in prefixes:
        if not isinstance(item, str) or not item.strip():
            raise ParityError(
                "whitelist.deliberately_diverged_prefixes entries must be non-empty strings"
            )
        cleaned.append(item.strip())

    description = raw.get("description", "")
    if description is not None and not isinstance(description, str):
        raise ParityError("whitelist.description must be a string when present")

    return WhitelistConfig(
        version=int(version),
        upstream_repo=upstream_repo.strip(),
        deliberately_diverged_prefixes=tuple(cleaned),
        description=(description or "").strip(),
    )


def path_is_deliberately_diverged(path: str, prefixes: Sequence[str]) -> bool:
    """Return True when *path* matches a deliberately diverged prefix."""
    normalized = path.replace("\\", "/").lstrip("./")
    for prefix in prefixes:
        candidate = prefix.replace("\\", "/")
        if candidate.endswith("/"):
            if normalized == candidate.rstrip("/") or normalized.startswith(candidate):
                return True
        elif normalized == candidate or normalized.startswith(candidate + "/"):
            return True
    return False


def classify_paths(
    paths: Sequence[str],
    prefixes: Sequence[str],
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """Classify changed paths into shared vs deliberately diverged."""
    shared: list[str] = []
    diverged: list[str] = []
    for path in paths:
        if path_is_deliberately_diverged(path, prefixes):
            diverged.append(path)
        else:
            shared.append(path)
    if shared:
        return STATUS_ATTENTION, tuple(shared), tuple(diverged)
    return STATUS_INFORMATIONAL, tuple(shared), tuple(diverged)


def parse_ported_from_trailers(
    message: str,
    *,
    upstream_repo: str,
) -> list[str]:
    """Extract upstream SHAs from ``Ported-from:`` trailers for *upstream_repo*."""
    found: list[str] = []
    for match in PORTED_FROM_RE.finditer(message):
        repo = match.group("repo").strip()
        sha = match.group("sha").lower()
        if repo.casefold() == upstream_repo.casefold() and len(sha) >= MIN_PORTED_SHA_LEN:
            found.append(sha)
    return found


def build_ported_index(
    messages: Iterable[str],
    *,
    upstream_repo: str,
) -> dict[str, list[str]]:
    """Map abbreviated ported SHAs to local commit subjects that reference them."""
    index: dict[str, list[str]] = {}
    for message in messages:
        subject = message.splitlines()[0].strip() if message.strip() else ""
        for sha in parse_ported_from_trailers(message, upstream_repo=upstream_repo):
            index.setdefault(sha, []).append(subject)
    return index


def match_ported_by(full_sha: str, ported_index: dict[str, list[str]]) -> list[str]:
    """Return local subjects that claim to have ported *full_sha*."""
    full = full_sha.lower()
    matches: list[str] = []
    seen: set[str] = set()
    for prefix, subjects in ported_index.items():
        if len(prefix) < MIN_PORTED_SHA_LEN:
            continue
        if full.startswith(prefix) or prefix.startswith(full[: len(prefix)]):
            for subject in subjects:
                if subject not in seen:
                    seen.add(subject)
                    matches.append(subject)
    return matches


def ensure_upstream_remote(
    repo: Path,
    *,
    remote: str,
    url: str,
    fetch: bool,
) -> None:
    """Ensure *remote* exists and optionally fetch it."""
    completed = _run_git(["remote"], cwd=repo)
    remotes = {line.strip() for line in completed.stdout.splitlines() if line.strip()}
    if remote not in remotes:
        _run_git(["remote", "add", remote, url], cwd=repo)
    if fetch:
        _run_git(["fetch", remote, "--prune"], cwd=repo)


def resolve_fork_point(repo: Path, local_ref: str, upstream_ref: str) -> str:
    """Return the merge-base SHA between local and upstream refs."""
    completed = _run_git(["merge-base", local_ref, upstream_ref], cwd=repo)
    sha = completed.stdout.strip()
    if not sha:
        raise ParityError(
            f"empty merge-base between {local_ref!r} and {upstream_ref!r}"
        )
    return sha


def list_upstream_only_commits(
    repo: Path,
    *,
    fork_point: str,
    upstream_ref: str,
) -> list[tuple[str, str, str, str]]:
    """Return ``(sha, short_sha, subject, author_date)`` for upstream-only commits."""
    pretty = "%H%x1f%h%x1f%s%x1f%aI"
    completed = _run_git(
        [
            "log",
            "--reverse",
            f"--pretty=format:{pretty}",
            f"{fork_point}..{upstream_ref}",
        ],
        cwd=repo,
    )
    rows: list[tuple[str, str, str, str]] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f")
        if len(parts) != 4:
            raise ParityError(f"unexpected git log row: {line!r}")
        rows.append((parts[0], parts[1], parts[2], parts[3]))
    return rows


def commit_paths(repo: Path, sha: str) -> tuple[str, ...]:
    """Return paths changed by *sha*."""
    completed = _run_git(
        ["diff-tree", "--no-commit-id", "--name-only", "-r", sha],
        cwd=repo,
    )
    paths = [
        line.replace("\\", "/").strip()
        for line in completed.stdout.splitlines()
        if line.strip()
    ]
    return tuple(paths)


def list_local_commit_messages(repo: Path, local_ref: str) -> list[str]:
    """Return full messages for commits reachable from *local_ref*."""
    completed = _run_git(
        ["log", "--pretty=format:%B%x1e", local_ref],
        cwd=repo,
    )
    return [
        chunk.strip("\n")
        for chunk in completed.stdout.split("\x1e")
        if chunk.strip()
    ]


def collect_parity_report(
    repo: Path,
    *,
    whitelist: WhitelistConfig,
    local_ref: str,
    upstream_ref: str,
) -> ParityReport:
    """Build the structured parity report for *repo*."""
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fork_point = resolve_fork_point(repo, local_ref, upstream_ref)
    messages = list_local_commit_messages(repo, local_ref)
    ported_index = build_ported_index(messages, upstream_repo=whitelist.upstream_repo)

    commits: list[UpstreamCommit] = []
    for sha, short_sha, subject, author_date in list_upstream_only_commits(
        repo, fork_point=fork_point, upstream_ref=upstream_ref
    ):
        paths = commit_paths(repo, sha)
        status, shared, diverged = classify_paths(
            paths, whitelist.deliberately_diverged_prefixes
        )
        ported_by = match_ported_by(sha, ported_index)
        if ported_by:
            status = STATUS_PORTED
        commits.append(
            UpstreamCommit(
                sha=sha,
                short_sha=short_sha,
                subject=subject,
                author_date=author_date,
                paths=paths,
                status=status,
                shared_paths=shared,
                diverged_paths=diverged,
                ported_by=tuple(ported_by),
            )
        )

    return ParityReport(
        local_ref=local_ref,
        upstream_ref=upstream_ref,
        fork_point=fork_point,
        upstream_repo=whitelist.upstream_repo,
        generated_at=generated_at,
        commits=commits,
        ported_sha_index={k: list(v) for k, v in ported_index.items()},
    )


def _md_escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_markdown_report(report: ParityReport, *, whitelist: WhitelistConfig) -> str:
    """Render a human-readable Markdown drift report."""
    lines: list[str] = [
        "# Upstream parity drift report",
        "",
        f"- Generated at (UTC): `{report.generated_at}`",
        f"- Local ref: `{report.local_ref}`",
        f"- Upstream ref: `{report.upstream_ref}`",
        f"- Upstream repository: `{report.upstream_repo}`",
        f"- Fork point (merge-base): `{report.fork_point}`",
        f"- Upstream-only commits: **{len(report.commits)}**",
        f"- Attention (shared paths, not ported): **{len(report.attention)}**",
        f"- Already ported (`Ported-from`): **{len(report.already_ported)}**",
        f"- Informational (deliberately diverged paths only): **{len(report.informational)}**",
        "",
        "## Classification policy",
        "",
        (
            "Paths matching `scripts/upstream_parity_whitelist.json` prefixes are "
            "treated as deliberately diverged (informational). Any other changed "
            "path is a shared path that needs maintainer attention unless a local "
            f"commit records `Ported-from: {whitelist.upstream_repo}@<sha>`."
        ),
        "",
        "### Triage flow",
        "",
        "1. Review **Attention** commits first; port foundation fixes deliberately.",
        "2. When porting, include a `Ported-from:` trailer with the upstream SHA.",
        "3. Expand the whitelist only for product-only or governance paths that "
        "StockPulse intentionally will not mirror.",
        "4. Informational commits can stay unported; re-check if paths later move "
        "into shared foundation code.",
        "",
    ]

    def _section(title: str, items: Sequence[UpstreamCommit], empty: str) -> None:
        lines.append(f"## {title}")
        lines.append("")
        if not items:
            lines.append(empty)
            lines.append("")
            return
        lines.append("| SHA | Date | Subject | Paths (sample) |")
        lines.append("| --- | --- | --- | --- |")
        for commit in items:
            sample_paths = commit.shared_paths or commit.paths
            sample = ", ".join(sample_paths[:4])
            if len(sample_paths) > 4:
                sample += f", ... (+{len(sample_paths) - 4})"
            if commit.status == STATUS_PORTED and commit.ported_by:
                sample = f"ported by: {commit.ported_by[0]}" + (
                    f"; paths: {sample}" if sample else ""
                )
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{commit.short_sha}`",
                        _md_escape_cell(commit.author_date[:10]),
                        _md_escape_cell(commit.subject),
                        _md_escape_cell(sample or "(no paths)"),
                    ]
                )
                + " |"
            )
        lines.append("")

    _section(
        "Attention (shared paths)",
        report.attention,
        "_No unported shared-path commits since the fork point._",
    )
    _section(
        "Already ported",
        report.already_ported,
        "_No upstream commits matched a local `Ported-from:` trailer._",
    )
    _section(
        "Informational (deliberately diverged only)",
        report.informational,
        "_No informational-only upstream commits._",
    )

    lines.extend(["## Whitelist prefixes", ""])
    for prefix in whitelist.deliberately_diverged_prefixes:
        lines.append(f"- `{prefix}`")
    lines.append("")
    return "\n".join(lines)


def render_issue_summary(report: ParityReport) -> str:
    """Compact summary suitable for a tracking issue body header."""
    return "\n".join(
        [
            "<!-- upstream-parity-tracking-issue -->",
            "",
            "## Summary",
            "",
            f"- Generated at (UTC): `{report.generated_at}`",
            f"- Local ref: `{report.local_ref}`",
            f"- Upstream ref: `{report.upstream_ref}`",
            f"- Fork point: `{report.fork_point}`",
            f"- Upstream-only commits: **{len(report.commits)}**",
            f"- Attention: **{len(report.attention)}**",
            f"- Already ported: **{len(report.already_ported)}**",
            f"- Informational: **{len(report.informational)}**",
            "",
            "Full Markdown report is attached as a workflow artifact "
            "(`upstream-parity-report.md`).",
            "",
            "This issue is updated in place by the weekly "
            "`upstream-parity` workflow. Do not open duplicate tracking issues.",
            "",
        ]
    )


def _git_identity(repo: Path) -> None:
    _run_git(["config", "user.email", "parity-self-test@example.com"], cwd=repo)
    _run_git(["config", "user.name", "Parity Self Test"], cwd=repo)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _commit(repo: Path, message: str) -> str:
    _run_git(["add", "-A"], cwd=repo)
    _run_git(["commit", "-m", message], cwd=repo)
    return _run_git(["rev-parse", "HEAD"], cwd=repo).stdout.strip()


def run_self_tests() -> None:
    """Build fixture repos and exercise classification end-to-end."""
    cases = 0

    prefixes = ("apps/dsa-desktop/", "examples/", "AGENTS.md")
    status, shared, diverged = classify_paths(
        ["apps/dsa-desktop/package.json", "examples/demo.py"],
        prefixes,
    )
    assert status == STATUS_INFORMATIONAL and not shared and len(diverged) == 2
    cases += 1

    status, shared, diverged = classify_paths(
        ["src/core/pipeline.py", "apps/dsa-desktop/main.ts"],
        prefixes,
    )
    assert status == STATUS_ATTENTION and shared == ("src/core/pipeline.py",)
    cases += 1

    status, shared, diverged = classify_paths([], prefixes)
    assert status == STATUS_INFORMATIONAL
    cases += 1

    assert path_is_deliberately_diverged("AGENTS.md", prefixes)
    assert not path_is_deliberately_diverged("AGENTS.md.bak", prefixes)
    cases += 1

    trailers = parse_ported_from_trailers(
        "fix: port health\n\nPorted-from: ZhuLinsen/daily_stock_analysis@abc1234\n",
        upstream_repo="ZhuLinsen/daily_stock_analysis",
    )
    assert trailers == ["abc1234"]
    cases += 1

    assert (
        parse_ported_from_trailers(
            "Ported-from: other/repo@abcdef0\nPorted-from: ZhuLinsen/daily_stock_analysis@abc\n",
            upstream_repo="ZhuLinsen/daily_stock_analysis",
        )
        == []
    )
    cases += 1

    with tempfile.TemporaryDirectory(prefix="upstream-parity-") as tmp:
        tmp_path = Path(tmp)
        upstream = tmp_path / "upstream.git"
        local = tmp_path / "local"
        upstream.mkdir()
        _run_git(["init", "--bare"], cwd=upstream)

        seed = tmp_path / "seed"
        seed.mkdir()
        # Prefer init -b main so the first commit already lives on main even when
        # the runner default branch is master (or unset). Fall back for older git.
        init = _run_git(["init", "-b", "main"], cwd=seed, check=False)
        if init.returncode != 0:
            _run_git(["init"], cwd=seed)
        _git_identity(seed)
        _write(seed / "shared" / "core.py", "v1\n")
        _write(seed / "examples" / "demo.py", "demo\n")
        fork_sha = _commit(seed, "initial shared baseline")
        # Ensure the first commit is on main before push (covers init without -b).
        _run_git(["branch", "-M", "main"], cwd=seed)
        _run_git(["remote", "add", "origin", str(upstream)], cwd=seed)
        _run_git(["push", "-u", "origin", "main"], cwd=seed)

        work_up = tmp_path / "work-up"
        _run_git(["clone", str(upstream), str(work_up)], cwd=tmp_path)
        _git_identity(work_up)
        _write(work_up / "shared" / "core.py", "v2-upstream\n")
        attention_sha = _commit(work_up, "fix shared core behavior")
        _write(work_up / "examples" / "demo.py", "demo-upstream\n")
        info_sha = _commit(work_up, "docs examples only")
        _write(work_up / "shared" / "util.py", "util\n")
        ported_upstream_sha = _commit(work_up, "fix shared util")
        _run_git(["push", "origin", "main"], cwd=work_up)

        _run_git(["clone", str(upstream), str(local)], cwd=tmp_path)
        _git_identity(local)
        _run_git(["reset", "--hard", fork_sha], cwd=local)
        _write(local / "shared" / "util.py", "util-ported\n")
        short = ported_upstream_sha[:8]
        _commit(
            local,
            "fix: port shared util\n\n"
            f"Ported-from: ZhuLinsen/daily_stock_analysis@{short}\n",
        )
        _write(local / "AGENTS.md", "stockpulse rules\n")
        _commit(local, "chore: local governance")

        whitelist_path = tmp_path / "whitelist.json"
        whitelist_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "upstream_repo": "ZhuLinsen/daily_stock_analysis",
                    "deliberately_diverged_prefixes": ["examples/", "AGENTS.md"],
                }
            ),
            encoding="utf-8",
        )
        whitelist = load_whitelist(whitelist_path)

        ensure_upstream_remote(
            local, remote="upstream", url=str(upstream), fetch=True
        )
        report = collect_parity_report(
            local,
            whitelist=whitelist,
            local_ref="HEAD",
            upstream_ref="upstream/main",
        )

        assert report.fork_point.startswith(fork_sha[:7])
        assert len(report.commits) == 3
        by_sha = {c.sha: c for c in report.commits}
        assert by_sha[attention_sha].status == STATUS_ATTENTION
        assert "shared/core.py" in by_sha[attention_sha].shared_paths
        assert by_sha[info_sha].status == STATUS_INFORMATIONAL
        assert by_sha[ported_upstream_sha].status == STATUS_PORTED
        cases += 1

        markdown = render_markdown_report(report, whitelist=whitelist)
        assert "Attention (shared paths)" in markdown
        assert "Already ported" in markdown
        assert attention_sha[:7] in markdown
        summary = render_issue_summary(report)
        assert "<!-- upstream-parity-tracking-issue -->" in summary
        cases += 1

        bad = tmp_path / "bad.json"
        bad.write_text("{}", encoding="utf-8")
        try:
            load_whitelist(bad)
            raise AssertionError("expected invalid whitelist to fail")
        except ParityError:
            cases += 1

    print(f"Upstream parity self-tests passed ({cases} cases).")


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
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Fetch the upstream remote before comparing (network; default: off)",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--issue-summary", type=Path, default=None)
    parser.add_argument("--self-test", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.self_test:
        run_self_tests()
        return 0

    repo = args.repo.resolve()
    if not (repo / ".git").exists():
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
        markdown = render_markdown_report(report, whitelist=whitelist)
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(markdown, encoding="utf-8")
        if args.issue_summary is not None:
            summary = render_issue_summary(report) + markdown
            args.issue_summary.parent.mkdir(parents=True, exist_ok=True)
            args.issue_summary.write_text(summary, encoding="utf-8")
        print(markdown)
        return 0
    except ParityError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
