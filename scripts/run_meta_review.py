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
from typing import Any, Callable, Dict, List, Optional


def _load_episodes(path: Path) -> List[Dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict) and isinstance(raw.get("episodes"), list):
        return [item for item in raw["episodes"] if isinstance(item, dict)]
    raise SystemExit("episodes JSON must be a list or {\"episodes\": [...]}")


def resolve_cli_runtime(
    *,
    force: bool,
    min_episodes: Optional[int],
    get_config: Optional[Callable[[], Any]] = None,
) -> Any:
    """Resolve the config object used by the CLI.

    ``force`` is a real gate: when false, the job respects
    ``AGENT_META_REVIEW_ENABLED`` on live config (or falls back to disabled).
    When true, ``run_meta_review(..., force=True)`` bypasses the enable flag.
    """
    force = bool(force)
    # Fallback only used when live config cannot be loaded.
    config: Any = SimpleNamespace(
        agent_meta_review_enabled=False,
        agent_meta_review_min_episodes=int(min_episodes or 30),
        agent_meta_review_llm_budget=0,
    )
    loader = get_config
    if loader is None:
        try:
            from src.config import get_config as _default_get_config

            loader = _default_get_config
        except Exception:
            loader = None
    if loader is not None:
        try:
            config = loader()
        except Exception:
            pass
    # Attach force for callers that want to inspect CLI intent.
    try:
        setattr(config, "_meta_review_cli_force", force)
    except Exception:
        pass
    return config


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
    force = bool(args.force)
    config = resolve_cli_runtime(
        force=force,
        min_episodes=args.min_episodes,
    )

    report = run_meta_review(
        episodes,
        config=config,
        min_episodes=args.min_episodes,
        min_kind_count=args.min_kind_count,
        force=force,
    )
    paths = write_meta_review_report(report, args.output_dir)
    print(
        json.dumps(
            {
                "status": report.status,
                "paths": paths,
                "sample_count": report.sample_count,
                "force": force,
            },
            ensure_ascii=False,
        )
    )
    return 0 if report.status in {"completed", "threshold_not_met", "disabled"} else 1


if __name__ == "__main__":
    sys.exit(main())
