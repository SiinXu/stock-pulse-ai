#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Opt-in CLI to label episode forward-return buckets (Issue #1096).

Research-only. This is not investment advice automation. Invocation is the
gate: there is no config-registry key and no scheduler. Missing bars skip the
row. Prices are never fabricated. Append-only ``agent_episodes`` are not
updated.

Usage::

    python scripts/label_forward_returns.py --as-of 2026-08-25
    python scripts/label_forward_returns.py --as-of 2026-08-25 --horizon 5d
    python scripts/label_forward_returns.py --as-of 2026-08-25 --horizon 1d --horizon 5d --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Optional, Sequence


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Label allowlisted 1d/5d forward-return buckets onto the episode "
            "sidecar. Research-only; missing bars are skipped. Invocation is "
            "the only gate."
        )
    )
    parser.add_argument(
        "--as-of",
        required=True,
        help="UTC calendar date YYYY-MM-DD. Horizons ending after this date are skipped.",
    )
    parser.add_argument(
        "--horizon",
        action="append",
        choices=("1d", "5d"),
        dest="horizons",
        help="Trading-session horizon to label. Repeatable. Default: 1d.",
    )
    parser.add_argument("--run-id", default=None, help="Optional episode run_id filter.")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    if args.limit < 1:
        print("--limit must be a positive integer", file=sys.stderr)
        return 2
    try:
        from src.services.forward_return_labeler import ForwardReturnLabeler

        summary = ForwardReturnLabeler().label(
            as_of=args.as_of,
            horizons=args.horizons,
            run_id=args.run_id,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # broad-exception: fallback_recorded - CLI entrypoint reports failure and exits non-zero.
        logging.getLogger("label_forward_returns").exception(
            "forward-return labeler failed: %s",
            exc,
        )
        return 1
    print(json.dumps(summary.to_dict(), ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
