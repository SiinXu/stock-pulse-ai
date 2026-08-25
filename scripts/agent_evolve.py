#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Opt-in dry-run agent promotion CLI (Issue #1093).

Invocation is the only gate: there is no config-registry key, scheduler, or
auto-promote environment variable. Sidecar approve/reject never activate
SkillRouter, catalog skills, or production routing.

Usage::

    python scripts/agent_evolve.py propose --fixture tests/fixtures/prediction_eval/cases/pred-seeded-miss-lesson.json
    python scripts/agent_evolve.py score --proposal-id promo-...
    python scripts/agent_evolve.py status
    python scripts/agent_evolve.py approve --proposal-id promo-...
    python scripts/agent_evolve.py reject --proposal-id promo-...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run agent promotion sidecar. Propose, score, and review "
            "experimental candidates without activating production skills."
        )
    )
    parser.add_argument(
        "--store-dir",
        default=None,
        help="Sidecar directory (default: artifacts/agent_evolve). Refuses strategies/ and skill catalogs.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    propose = sub.add_parser("propose", help="Write a sidecar proposal from fixture or episode lessons")
    source = propose.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture", help="Prediction-eval case JSON path")
    source.add_argument("--case-id", help="Committed prediction-eval case id")
    source.add_argument("--episodes", help="Episode JSON list with lessons[]")
    propose.add_argument(
        "--kind",
        default="experimental_skill_id",
        choices=("experimental_skill_id", "router_rule"),
        help="Sidecar candidate kind. Never copied into SkillRouter or strategies/.",
    )

    score = sub.add_parser("score", help="Score a sidecar with offline prediction eval")
    score.add_argument("--proposal-id", required=True)

    status = sub.add_parser("status", help="List sidecar review state")
    status.add_argument("--proposal-id", default=None)

    approve = sub.add_parser(
        "approve",
        help="Mark sidecar review_state=approved (does not activate runtime skills)",
    )
    approve.add_argument("--proposal-id", required=True)

    reject = sub.add_parser("reject", help="Mark sidecar review_state=rejected")
    reject.add_argument("--proposal-id", required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    from src.agent.evolution.promotion_cli import (
        AgentPromotionService,
        PromotionProposalError,
        default_store_dir,
    )

    store_dir = Path(args.store_dir) if args.store_dir else default_store_dir()
    try:
        service = AgentPromotionService(store_dir)
        if args.command == "propose":
            result = service.propose(
                fixture=args.fixture,
                case_id=args.case_id,
                episodes=args.episodes,
                candidate_kind=args.kind,
            )
            payload = result.to_dict()
        elif args.command == "score":
            payload = service.score(args.proposal_id).to_dict()
        elif args.command == "status":
            payload = service.status(args.proposal_id)
        elif args.command == "approve":
            payload = service.approve(args.proposal_id).to_dict()
        elif args.command == "reject":
            payload = service.reject(args.proposal_id).to_dict()
        else:
            parser.error(f"unknown command: {args.command}")
    except (PromotionProposalError, ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
