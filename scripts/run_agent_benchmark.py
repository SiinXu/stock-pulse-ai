#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic offline runner for the financial agent evaluation benchmark (#252 V0).

No network. No live LLM. Replays frozen agent_runtime transcripts through the
existing ReplayLLMAdapter harness and scores structural metrics.

Examples:

  python scripts/run_agent_benchmark.py
  python scripts/run_agent_benchmark.py --json-out /tmp/report.json --md-out /tmp/report.md
  python scripts/run_agent_benchmark.py --write-baseline
  python scripts/run_agent_benchmark.py --strict-baseline   # non-zero exit on score drop

V0 default exit policy: infrastructure failures fail the process; score drops
versus the committed baseline are printed but do not fail unless --strict-baseline.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.agent.benchmark.loader import BASELINE_PATH  # noqa: E402
from tests.agent.benchmark.runner import (  # noqa: E402
    build_full_outputs,
    canonical_json,
    run_benchmark,
    write_baseline,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the offline financial agent evaluation benchmark "
            "(no network / no live LLM)."
        )
    )
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenarios",
        default=None,
        help="Limit to one scenario id (repeatable).",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path for the full JSON report.",
    )
    parser.add_argument(
        "--md-out",
        type=Path,
        default=None,
        help="Optional path for the markdown report.",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help=f"Rewrite the committed baseline score file at {BASELINE_PATH}.",
    )
    parser.add_argument(
        "--strict-baseline",
        action="store_true",
        help=(
            "Exit non-zero when the aggregate or any scenario score drops vs "
            "baseline (off by default in V0)."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Print only the aggregate score line to stdout.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    print(f"[agent-eval-benchmark] repo={REPO_ROOT}", file=sys.stderr)
    print(
        "[agent-eval-benchmark] offline replay (ReplayLLMAdapter + frozen fixtures)",
        file=sys.stderr,
    )

    report = run_benchmark(scenario_ids=args.scenarios)
    outputs = build_full_outputs(report, with_baseline=not args.write_baseline)
    score_view = outputs["score_view"]
    comparison = outputs["comparison"]
    markdown = outputs["markdown"]

    if args.write_baseline:
        path = write_baseline(report)
        print(f"[agent-eval-benchmark] wrote baseline {path}", file=sys.stderr)
        outputs = build_full_outputs(report, with_baseline=True)
        comparison = outputs["comparison"]
        markdown = outputs["markdown"]

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(canonical_json(score_view), encoding="utf-8")
        print(f"[agent-eval-benchmark] wrote json {args.json_out}", file=sys.stderr)

    if args.md_out is not None:
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(markdown, encoding="utf-8")
        print(f"[agent-eval-benchmark] wrote markdown {args.md_out}", file=sys.stderr)

    agg = score_view.get("aggregate") or {}
    if args.quiet:
        print(f"{float(agg.get('score') or 0.0):.4f}")
    else:
        sys.stdout.write(markdown)
        if not markdown.endswith("\n"):
            sys.stdout.write("\n")

    if args.strict_baseline and comparison is not None:
        if comparison.get("dropped") or comparison.get("drop_count"):
            print(
                "[agent-eval-benchmark] FAIL: score drop vs baseline "
                f"(delta={float(comparison.get('delta') or 0.0):+.4f}, "
                f"drop_count={comparison.get('drop_count')})",
                file=sys.stderr,
            )
            return 2

    print("[agent-eval-benchmark] OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
