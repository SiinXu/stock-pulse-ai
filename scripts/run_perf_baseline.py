#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic offline runner for key-path performance baselines (#227).

No network. No live LLM. Exercises synthetic data-fetch, analysis, and report
workloads with realistic sizes, then optionally compares to a committed baseline.

Examples:

  python scripts/run_perf_baseline.py
  python scripts/run_perf_baseline.py --json-out /tmp/perf.json --md-out /tmp/perf.md
  python scripts/run_perf_baseline.py --write-baseline
  python scripts/run_perf_baseline.py --compare --strict
  python scripts/run_perf_baseline.py --profile --profile-out /tmp/perf.pstats
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.litellm_stub import ensure_litellm_stub  # noqa: E402

ensure_litellm_stub()

from src.perf.baseline import (  # noqa: E402
    SCHEMA_VERSION,
    compare_to_baseline,
    load_baseline,
    render_markdown_report,
    write_baseline,
)
from src.perf.profiler import run_with_optional_profile  # noqa: E402
from src.perf.workloads import KEY_PATH_WORKLOADS, run_all_workloads  # noqa: E402

DEFAULT_BASELINE_PATH = (
    REPO_ROOT / "tests" / "perf" / "baselines" / "offline_key_paths.json"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run offline key-path performance baselines "
            "(data fetch / analysis / report; no network / no live LLM)."
        )
    )
    parser.add_argument("--workload", action="append", dest="workloads", default=None)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--md-out", type=Path, default=None)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE_PATH)
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--regression-ratio", type=float, default=2.5)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--profile-out", type=Path, default=None)
    parser.add_argument("--list", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.list:
        for name in sorted(KEY_PATH_WORKLOADS):
            print(name)
        return 0

    def _run():
        return run_all_workloads(args.workloads, collect=True)

    report, profile_text = run_with_optional_profile(
        _run,
        enabled=bool(args.profile),
        stats_out=args.profile_out,
    )
    report["schema_version"] = SCHEMA_VERSION

    comparison = None
    if args.compare or args.strict:
        if not args.baseline.is_file():
            print(f"[perf-baseline] baseline missing: {args.baseline}", file=sys.stderr)
            return 2
        baseline = load_baseline(args.baseline)
        comparison = compare_to_baseline(
            report,
            baseline,
            regression_ratio=args.regression_ratio,
        )
        report["comparison"] = comparison

    if args.write_baseline:
        write_baseline(args.baseline, report)
        print(f"[perf-baseline] wrote baseline: {args.baseline}")

    md = render_markdown_report(report, comparison=comparison)
    print(md)
    if profile_text:
        print("## cProfile (top cumulative)\n")
        print("```")
        print(profile_text.rstrip())
        print("```")

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"[perf-baseline] wrote json: {args.json_out}")
    if args.md_out is not None:
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(md, encoding="utf-8")
        print(f"[perf-baseline] wrote markdown: {args.md_out}")

    if args.strict and comparison is not None and not comparison.get("ok"):
        print(
            f"[perf-baseline] REGRESSION: {', '.join(comparison.get('regressed') or [])}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
