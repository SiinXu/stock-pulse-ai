#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Emit a human-readable Daily Analysis run summary for GitHub Actions (#850).

Reads structured ``data/run_status.json`` when present, falls back to exit code,
job status, env readiness, and log keywords. Writes ``$GITHUB_STEP_SUMMARY`` and
optionally sends a short ``system_error`` notification.

This script always exits 0: summary/notify failures must not fail the Actions run.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.services.actions_daily_run_summary import (  # noqa: E402
    build_and_emit_summary,
    default_status_path,
)

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Write a plain-language Daily Analysis Step Summary and optional "
            "failure notification (issue #850)."
        )
    )
    parser.add_argument(
        "--status",
        type=Path,
        default=default_status_path(),
        help="Path to run_status.json (default: data/run_status.json)",
    )
    parser.add_argument(
        "--exit-code",
        type=int,
        default=None,
        help="Exit code from the analysis step (optional)",
    )
    parser.add_argument(
        "--job-status",
        default="",
        help="GitHub job.status (success|failure|cancelled)",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=None,
        help="Optional log file for keyword fallback classification",
    )
    parser.add_argument(
        "--write-step-summary",
        action="store_true",
        default=True,
        help="Append markdown to $GITHUB_STEP_SUMMARY (default: true)",
    )
    parser.add_argument(
        "--no-write-step-summary",
        action="store_true",
        help="Print summary to stdout only",
    )
    parser.add_argument(
        "--notify-on-failure",
        action="store_true",
        default=False,
        help="Attempt a short system_error notification on failed outcomes",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    try:
        summary = build_and_emit_summary(
            status_path=args.status,
            exit_code=args.exit_code,
            job_status=args.job_status or None,
            log_path=args.log_path,
            write_step_summary=not args.no_write_step_summary,
            notify_on_failure=bool(args.notify_on_failure),
        )
        logger.info(
            "Daily run summary: outcome=%s code=%s ok=%s failed=%s skipped=%s source=%s",
            summary.outcome,
            summary.primary_code,
            summary.ok_count,
            summary.failed_count,
            summary.skipped_count,
            summary.source,
        )
    except Exception as exc:  # broad-exception: fallback_recorded - summary CLI must always exit 0
        logger.warning("actions_daily_run_summary degraded: %s", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
