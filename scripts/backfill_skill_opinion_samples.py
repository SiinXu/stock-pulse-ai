#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Opt-in backfill of skill-opinion samples from historical analysis reports.

Historical ``analysis_history`` rows that already contain a structured
``strategy_synthesis`` (supporting/opposing skills with canonical signal and
confidence) can seed immutable samples. This script is **idempotent**: identity
duplicates ``(analysis_history_id, skill_id, sample_schema_version)`` are
ignored.

Usage::

    python scripts/backfill_skill_opinion_samples.py --dry-run
    python scripts/backfill_skill_opinion_samples.py --limit 200
    python scripts/backfill_skill_opinion_samples.py --limit 200 --evaluate

Limitations (honest):
- Only histories whose ``raw_result`` contains ``strategy_synthesis`` with
  individual skill facts are eligible. Final Agent decisions alone cannot seed
  samples.
- Evaluation (optional ``--evaluate``) still requires local ``stock_daily`` bars
  and a persisted ``effective_daily_bar_date``; missing bars stay ``pending`` or
  ``unable`` rather than fetching network prices.
- Does not enable runtime Bayesian weights; that remains a separate default-off
  gate (``SKILL_OPINION_OUTCOME_WEIGHTS_ENABLED``).
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Optional


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def run_backfill(
    *,
    limit: int,
    stock_code: Optional[str],
    dry_run: bool,
    evaluate: bool,
    evaluate_limit: int,
) -> int:
    from src.services.skill_opinion_outcome_service import (
        SkillOpinionOutcomeService,
    )
    from src.services.skill_opinion_sample_service import (
        SKILL_OPINION_SAMPLE_SCHEMA_VERSION,
        SkillOpinionSampleService,
    )

    logger = logging.getLogger("backfill_skill_opinion_samples")
    sample_service = SkillOpinionSampleService()

    if dry_run:
        pending = sample_service.repo.list_unmaterialized_histories(
            sample_schema_version=SKILL_OPINION_SAMPLE_SCHEMA_VERSION,
            limit=limit,
            stock_code=stock_code,
        )
        logger.info(
            "dry-run: would scan up to %s unmaterialized histories "
            "(eligible with strategy_synthesis and no current samples): %s",
            limit,
            len(pending),
        )
        for history in pending[:20]:
            logger.info(
                "  history_id=%s stock_code=%s",
                history.id,
                history.stock_code,
            )
        if len(pending) > 20:
            logger.info("  ... and %s more", len(pending) - 20)
        if evaluate:
            logger.info(
                "dry-run: --evaluate would then run offline evaluation "
                "for up to %s outcome keys (no network price fetch)",
                evaluate_limit,
            )
        return 0

    materialize_result = sample_service.materialize_pending(
        limit=limit,
        stock_code=stock_code,
    )
    logger.info(
        "materialize complete: histories_scanned=%s samples_created=%s",
        materialize_result.get("histories_scanned"),
        materialize_result.get("samples_created"),
    )

    if evaluate:
        outcome_service = SkillOpinionOutcomeService()
        eval_result = outcome_service.run_outcomes(limit=evaluate_limit)
        logger.info("evaluate complete: %s", eval_result)

    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Idempotent opt-in backfill of skill-opinion samples from "
            "analysis_history rows that already contain strategy_synthesis."
        )
    )
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--stock-code", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--evaluate-limit", type=int, default=100)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    if args.limit < 1:
        print("--limit must be a positive integer", file=sys.stderr)
        return 2
    try:
        return run_backfill(
            limit=args.limit,
            stock_code=args.stock_code,
            dry_run=args.dry_run,
            evaluate=args.evaluate,
            evaluate_limit=args.evaluate_limit,
        )
    except Exception as exc:  # broad-exception: fallback_recorded - CLI entrypoint reports failure and exits non-zero.
        logging.getLogger("backfill_skill_opinion_samples").exception(
            "backfill failed: %s",
            exc,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
