# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""CLI entrypoint for external cron / multi-process deploys.

Usage::

    python -m src.services.prediction_resolver
    python -m src.services.prediction_resolver --limit 20 --json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Optional, Sequence

from src.services.prediction_resolver.resolver import build_prediction_resolver
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.services.prediction_resolver",
        description=(
            "Run one PredictionResolver.tick for external schedulers "
            "(cron / Docker / multi-process)."
        ),
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--worker-id", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    _configure_logging(bool(args.verbose))

    lease_seconds = 120
    max_per_tick = 50
    max_attempts = 5
    try:
        from src.application_services import get_application_services

        config = get_application_services().config
        lease_seconds = int(
            getattr(config, "prediction_resolve_lease_seconds", lease_seconds)
        )
        max_per_tick = int(
            getattr(config, "prediction_resolve_max_per_tick", max_per_tick)
        )
        max_attempts = int(
            getattr(config, "prediction_resolve_max_attempts", max_attempts)
        )
    except Exception as exc:  # broad-exception: fallback_recorded - do not run with invented defaults
        log_safe_exception(
            logger,
            "PredictionResolver configuration load failed",
            exc,
            error_code="prediction_resolver_config_load_failed",
        )
        return 2

    resolver = build_prediction_resolver(
        worker_id=args.worker_id,
        lease_seconds=lease_seconds,
        max_per_tick=max_per_tick,
        max_attempts=max_attempts,
        require_persistence=True,
    )
    if resolver is None:
        logger.error(
            "PredictionResolver unavailable: need A3 store + A4 ActualsFetcher + A5 ClaimScorer"
        )
        return 1

    try:
        summary = resolver.tick(limit=args.limit)
    except Exception as exc:  # broad-exception: fallback_recorded - CLI returns exit 2 on tick failure
        logger.exception("PredictionResolver.tick failed: %s", exc)
        return 2

    if args.json:
        print(json.dumps(summary.as_dict(), ensure_ascii=False, sort_keys=True))
    else:
        logger.info(
            "tick claimed=%s resolved=%s data_unavailable=%s skipped=%s errors=%s overlap=%s",
            summary.claimed,
            summary.resolved,
            summary.data_unavailable,
            summary.skipped,
            summary.errors,
            summary.skipped_overlap,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
