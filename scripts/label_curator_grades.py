#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Opt-in CLI to ingest eval-fixture curator grades (Issue #1096).

Research-only. This is not investment advice automation. Invocation is the
gate: there is no config-registry key and no scheduler. Missing grades skip
the row (absence). Unknown tokens fail closed. Append-only ``agent_episodes``
are not updated.

Usage::

    python scripts/label_curator_grades.py --fixture path/to/grades.json
    python scripts/label_curator_grades.py --fixture path/to/grades.json --dry-run
    python scripts/label_curator_grades.py --fixture path/to/grades.json --episode-id ep-1
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
            "Ingest allowlisted curator grades from an eval fixture onto the "
            "episode sidecar. Research-only; missing grades stay absent. "
            "Invocation is the only gate."
        )
    )
    parser.add_argument(
        "--fixture",
        required=True,
        help="JSON fixture path. Object with version curator_grade/1.0 and grades[], or a grades array.",
    )
    parser.add_argument(
        "--episode-id",
        default=None,
        help="Optional episode_id filter. Other fixture rows are ignored.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    try:
        from src.services.curator_grade_ingester import CuratorGradeIngester

        summary = CuratorGradeIngester().ingest(
            fixture=args.fixture,
            episode_id=args.episode_id,
            dry_run=args.dry_run,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # broad-exception: fallback_recorded - CLI entrypoint reports failure and exits non-zero.
        logging.getLogger("label_curator_grades").exception(
            "curator-grade ingester failed: %s",
            exc,
        )
        return 1
    print(json.dumps(summary.to_dict(), ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
