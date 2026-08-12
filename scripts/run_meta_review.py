#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline CLI for cross-run meta-review (Issue #1094).

Reads synthetic or exported episode JSON and writes Markdown/JSON report
artifacts. Never mutates Agent Soul, ToolSurface, or runtime config.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List


def _load_episodes(path: Path) -> List[Dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict) and isinstance(raw.get("episodes"), list):
        return [item for item in raw["episodes"] if isinstance(item, dict)]
    raise SystemExit("episodes JSON must be a list or {\"episodes\": [...]}")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run offline agent meta-review")
    parser.add_argument(
        "--episodes",
        required=True,
        help="Path to episode JSON list (or {episodes: [...]})",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/meta_review",
        help="Directory for Markdown/JSON report artifacts",
    )
    parser.add_argument(
        "--min-episodes",
        type=int,
        default=None,
        help="Sample threshold override (default from config / 30)",
    )
    parser.add_argument(
        "--min-kind-count",
        type=int,
        default=3,
        help="Minimum kind count before surfacing a failure kind",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run even when AGENT_META_REVIEW_ENABLED is false",
    )
    args = parser.parse_args(argv)

    # Local import after path setup for repo-root execution.
    from src.agent.evolution.meta_review import run_meta_review, write_meta_review_report

    episodes = _load_episodes(Path(args.episodes))
    config = SimpleNamespace(
        agent_meta_review_enabled=True if args.force else False,
        agent_meta_review_min_episodes=args.min_episodes or 30,
        agent_meta_review_llm_budget=0,
    )
    # Prefer live config when available.
    try:
        from src.config import get_config

        live = get_config()
        config = live
    except Exception:
        pass

    report = run_meta_review(
        episodes,
        config=config,
        min_episodes=args.min_episodes,
        min_kind_count=args.min_kind_count,
        force=args.force or True,
    )
    paths = write_meta_review_report(report, args.output_dir)
    print(json.dumps({"status": report.status, "paths": paths, "sample_count": report.sample_count}, ensure_ascii=False))
    return 0 if report.status in {"completed", "threshold_not_met", "disabled"} else 1


if __name__ == "__main__":
    sys.exit(main())
