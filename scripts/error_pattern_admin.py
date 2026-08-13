#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Admin CLI for the persisted Agent error-pattern encyclopedia."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent.evolution.error_patterns import (  # noqa: E402
    ErrorPatternEncyclopedia,
    resolve_error_pattern_state_path,
)


def _read_json(path: str) -> Any:
    if path == "-":
        return json.load(sys.stdin)
    with Path(path).expanduser().open(encoding="utf-8") as handle:
        return json.load(handle)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-path",
        type=Path,
        default=resolve_error_pattern_state_path(),
        help="State file (defaults beside DATABASE_PATH).",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List all cards and audit events.")

    ingest = commands.add_parser("ingest", help="Ingest a JSON list of lesson bundles.")
    ingest.add_argument("--input", required=True, help="JSON file, or - for stdin.")
    ingest.add_argument("--actor", required=True)

    for name in ("enable", "disable"):
        command = commands.add_parser(name, help=f"{name.title()} one card.")
        command.add_argument("pattern_id")
        command.add_argument("--actor", required=True)
        command.add_argument("--note")

    edit = commands.add_parser("edit", help="Edit one card with revision checking.")
    edit.add_argument("pattern_id")
    edit.add_argument("--actor", required=True)
    edit.add_argument("--expected-revision", type=int, required=True)
    edit.add_argument("--title")
    edit.add_argument("--description")
    edit.add_argument("--remedy")
    edit.add_argument("--trigger", action="append", dest="triggers")
    edit.add_argument("--note")
    return parser


def main() -> int:
    args = _parser().parse_args()
    store = ErrorPatternEncyclopedia(args.state_path)
    if args.command == "ingest":
        payload = _read_json(args.input)
        if not isinstance(payload, list):
            raise ValueError("ingest input must be a JSON list")
        result: Any = [
            card.to_public_dict()
            for card in store.ingest_lessons(payload, actor=args.actor)
        ]
    elif args.command == "enable":
        result = store.enable(
            args.pattern_id,
            actor=args.actor,
            note=args.note,
        ).to_public_dict()
    elif args.command == "disable":
        result = store.disable(
            args.pattern_id,
            actor=args.actor,
            note=args.note,
        ).to_public_dict()
    elif args.command == "edit":
        result = store.human_edit(
            args.pattern_id,
            actor=args.actor,
            expected_revision=args.expected_revision,
            title=args.title,
            description=args.description,
            remedy=args.remedy,
            triggers=args.triggers,
            note=args.note,
        ).to_public_dict()
    else:
        result = store.export_snapshot()
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
