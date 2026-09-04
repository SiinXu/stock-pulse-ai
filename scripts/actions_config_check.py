#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI entry for Actions configuration check (no analysis, no secret values).

Usage:
    python scripts/actions_config_check.py
    python scripts/actions_config_check.py --strict-notify
    python scripts/actions_config_check.py --probe-llm
    python scripts/actions_config_check.py --allow-missing-llm
    python scripts/actions_config_check.py --summary-file /tmp/summary.md

Exit codes:
    0 — no hard failures (warnings allowed unless --strict-notify elevates them)
    1 — hard failure (missing LLM and/or watchlist, path blocked, etc.)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.services.actions_config_check import (  # noqa: E402
    format_report_markdown,
    format_report_text,
    run_config_check,
)


def _reconfigure_output_stream(stream) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if not callable(reconfigure):
        return
    for kwargs in (
        {"encoding": "utf-8", "errors": "replace"},
        {"errors": "replace"},
    ):
        try:
            reconfigure(**kwargs)
            return
        except Exception:
            continue


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        _reconfigure_output_stream(stream)

    parser = argparse.ArgumentParser(
        description=(
            "Validate Actions / env configuration without running analysis. "
            "Never prints secret values."
        )
    )
    parser.add_argument(
        "--strict-notify",
        action="store_true",
        help="Treat missing notification channels as a hard failure (default: warning only).",
    )
    parser.add_argument(
        "--probe-llm",
        action="store_true",
        help=(
            "Optional: one cheap LLM connectivity call for the first detectable provider. "
            "Default is off (presence/format only; no token spend)."
        ),
    )
    parser.add_argument(
        "--allow-missing-llm",
        action="store_true",
        help=(
            "Treat a missing LLM key as a warning instead of a hard failure. "
            "Used by automated push/schedule Config Check canaries in repositories "
            "without LLM secrets. Malformed provided keys still fail. "
            "--probe-llm overrides this flag and keeps missing keys as a hard failure. "
            "Manual dispatch and the default CLI remain strict."
        ),
    )
    parser.add_argument(
        "--summary-file",
        type=str,
        default="",
        help="Write Markdown summary to this path (also used when GITHUB_STEP_SUMMARY is set).",
    )
    parser.add_argument(
        "--no-text",
        action="store_true",
        help="Do not print the text table to stdout (Markdown summary still written if configured).",
    )
    args = parser.parse_args(argv)

    report = run_config_check(
        os.environ,
        strict_notify=bool(args.strict_notify),
        probe_llm=bool(args.probe_llm),
        allow_missing_llm=bool(args.allow_missing_llm),
        repo_root=REPO_ROOT,
    )

    text = format_report_text(report)
    markdown = format_report_markdown(report)

    if not args.no_text:
        print(text)

    summary_targets: list[Path] = []
    if args.summary_file:
        summary_targets.append(Path(args.summary_file))
    github_summary = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if github_summary:
        summary_targets.append(Path(github_summary))

    for target in summary_targets:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as handle:
                handle.write(markdown)
                handle.write("\n")
        except OSError as exc:
            print(
                f"WARNING: could not write summary to {target}: {type(exc).__name__}",
                file=sys.stderr,
            )

    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
