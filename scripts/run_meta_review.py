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
from typing import Any, Callable, Dict, List, Optional

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

MAX_EPISODE_FILE_BYTES = 16 * 1024 * 1024
MAX_META_EPISODES = 50_000


def _load_episodes(path: Path) -> List[Dict[str, Any]]:
    with path.open("rb") as stream:
        payload = stream.read(MAX_EPISODE_FILE_BYTES + 1)
    if len(payload) > MAX_EPISODE_FILE_BYTES:
        raise ValueError(
            f"episodes JSON exceeds {MAX_EPISODE_FILE_BYTES} bytes"
        )
    raw = json.loads(payload.decode("utf-8"))
    if isinstance(raw, list):
        episodes = raw
    elif isinstance(raw, dict) and isinstance(raw.get("episodes"), list):
        episodes = raw["episodes"]
    else:
        raise ValueError("episodes JSON must be a list or {\"episodes\": [...]}")
    if len(episodes) > MAX_META_EPISODES:
        raise ValueError(f"episodes JSON exceeds {MAX_META_EPISODES} items")
    if any(not isinstance(item, dict) for item in episodes):
        raise ValueError("every episodes JSON item must be an object")
    return episodes


def resolve_cli_runtime(
    *,
    force: bool,
    min_episodes: Optional[int],
    get_config: Optional[Callable[[], Any]] = None,
) -> Any:
    """Resolve the config object used by the CLI.

    ``force`` is a real gate: when false, the job respects
    ``AGENT_META_REVIEW_ENABLED`` on live config.
    When true, ``run_meta_review(..., force=True)`` bypasses the enable flag.
    """
    if type(force) is not bool:
        raise TypeError("force must be a boolean")
    loader = get_config
    if loader is None:
        try:
            from src.config import get_config as _default_get_config

            loader = _default_get_config
        except ImportError as exc:
            raise RuntimeError("cannot import repository configuration") from exc
    if loader is not None:
        return loader()
    raise RuntimeError("repository configuration loader is unavailable")


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

    try:
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
    except (OSError, ValueError, TypeError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"meta-review failed: {exc}", file=sys.stderr)
        return 2
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
