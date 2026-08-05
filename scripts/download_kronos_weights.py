#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Explicit opt-in helper to download official Kronos weights.

This script never runs from the Web UI. It prints approximate download size
before transferring any bytes, and requires an affirmative --yes flag for
non-interactive downloads.

Usage examples:

  python scripts/download_kronos_weights.py --help
  python scripts/download_kronos_weights.py --size mini --weights-dir ~/kronos --yes

Requires optional packages from requirements-kronos.txt (huggingface_hub).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_repo_on_path() -> None:
    root = str(_repo_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def _print_size_table() -> None:
    _ensure_repo_on_path()
    from src.services.kronos_forecast_service import (
        KRONOS_DOWNLOAD_SIZE_HINTS,
        KRONOS_MODEL_SPECS,
    )

    print("Approximate download sizes (model + matching tokenizer):")
    for size in ("mini", "small", "base"):
        spec = KRONOS_MODEL_SPECS[size]
        hint = KRONOS_DOWNLOAD_SIZE_HINTS[size]
        print(
            f"  {size:5}  {hint}\n"
            f"         model={spec.model_repo_id}  tokenizer={spec.tokenizer_repo_id}"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="download_kronos_weights.py",
        description=(
            "Download official Kronos model and tokenizer weights into a local "
            "directory. Explicit opt-in only; no silent multi-gigabyte downloads."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Install optional deps first:\n"
            "  python -m pip install --constraint constraints.txt "
            "--build-constraint build-constraints.txt -r requirements-kronos.txt\n\n"
            "Docs: docs/kronos-local-model.md"
        ),
    )
    parser.add_argument(
        "--size",
        choices=("mini", "small", "base"),
        default=os.environ.get("KRONOS_MODEL_SIZE", "mini").strip().lower() or "mini",
        help="Kronos model size (default: env KRONOS_MODEL_SIZE or mini)",
    )
    parser.add_argument(
        "--weights-dir",
        default=os.environ.get("KRONOS_WEIGHTS_DIR", "").strip() or None,
        help="Target directory (default: env KRONOS_WEIGHTS_DIR)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm the download after the size statement (required for non-interactive use)",
    )
    parser.add_argument(
        "--list-sizes",
        action="store_true",
        help="Print approximate sizes and exit without downloading",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions and size estimate without downloading",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.list_sizes:
        try:
            _print_size_table()
        except Exception as exc:  # broad-exception: fallback_recorded - Help path must work even if repo import fails.
            print(
                "Could not load Kronos size metadata from the repository. "
                f"Detail: {exc}",
                file=sys.stderr,
            )
            print(
                "Approximate sizes: mini ~40 MB, small ~150 MB, base ~500 MB "
                "(model + tokenizer).",
            )
        return 0

    if not args.weights_dir:
        parser.error(
            "--weights-dir is required (or set KRONOS_WEIGHTS_DIR). "
            "Example: --weights-dir $HOME/.local/share/stockpulse/kronos"
        )

    _ensure_repo_on_path()
    try:
        from src.services.kronos_forecast_service import (
            KRONOS_DOWNLOAD_SIZE_HINTS,
            KRONOS_MODEL_SPECS,
        )
    except Exception as exc:  # broad-exception: fallback_recorded - Surface import issues without traceback dump for operators.
        print(
            "Failed to import StockPulse Kronos metadata. Run this script from "
            f"the repository root. Detail: {exc}",
            file=sys.stderr,
        )
        return 2

    size = str(args.size).strip().lower()
    if size not in KRONOS_MODEL_SPECS:
        print(f"Unsupported size: {size}", file=sys.stderr)
        return 2

    spec = KRONOS_MODEL_SPECS[size]
    size_hint = KRONOS_DOWNLOAD_SIZE_HINTS[size]
    weights_dir = Path(args.weights_dir).expanduser().resolve()
    model_dir = weights_dir / spec.model_directory
    tokenizer_dir = weights_dir / spec.tokenizer_directory

    print("Kronos weight download plan")
    print(f"  size:           {size}")
    print(f"  approx. size:   {size_hint}")
    print(f"  weights dir:    {weights_dir}")
    print(f"  model repo:     {spec.model_repo_id} -> {model_dir}")
    print(f"  tokenizer repo: {spec.tokenizer_repo_id} -> {tokenizer_dir}")
    print(
        "  note:           Downloads only after --yes (or interactive confirm). "
        "Resumable when huggingface_hub supports it."
    )

    if args.dry_run:
        print("Dry run only; no bytes transferred.")
        return 0

    if not args.yes:
        try:
            answer = input(
                f"Proceed with approximately {size_hint} download into "
                f"{weights_dir}? [y/N] "
            ).strip().lower()
        except EOFError:
            print(
                "Non-interactive session: re-run with --yes after reviewing the size.",
                file=sys.stderr,
            )
            return 2
        if answer not in {"y", "yes"}:
            print("Aborted; no download started.")
            return 1

    try:
        from huggingface_hub import snapshot_download
    except Exception:  # broad-exception: fallback_recorded - Optional dep missing is an expected first-use path.
        print(
            "huggingface_hub is not installed. Install optional Kronos deps first:\n"
            "  python -m pip install --constraint constraints.txt "
            "--build-constraint build-constraints.txt -r requirements-kronos.txt",
            file=sys.stderr,
        )
        return 2

    weights_dir.mkdir(parents=True, exist_ok=True)
    try:
        print(f"Downloading {spec.model_repo_id} ...")
        snapshot_download(
            repo_id=spec.model_repo_id,
            local_dir=str(model_dir),
            local_dir_use_symlinks=False,
            resume_download=True,
        )
        print(f"Downloading {spec.tokenizer_repo_id} ...")
        snapshot_download(
            repo_id=spec.tokenizer_repo_id,
            local_dir=str(tokenizer_dir),
            local_dir_use_symlinks=False,
            resume_download=True,
        )
    except TypeError:
        # Older huggingface_hub versions may not accept resume_download /
        # local_dir_use_symlinks. Retry with the minimal stable signature.
        try:
            snapshot_download(repo_id=spec.model_repo_id, local_dir=str(model_dir))
            snapshot_download(
                repo_id=spec.tokenizer_repo_id,
                local_dir=str(tokenizer_dir),
            )
        except Exception as exc:  # broad-exception: fallback_recorded - Surface download failures as operator guidance.
            print(f"Download failed: {exc}", file=sys.stderr)
            return 1
    except Exception as exc:  # broad-exception: fallback_recorded - Surface download failures as operator guidance.
        print(f"Download failed: {exc}", file=sys.stderr)
        return 1

    print("Download complete.")
    print(f"Set KRONOS_WEIGHTS_DIR={weights_dir}")
    print(f"Set KRONOS_MODEL_SIZE={size}")
    print("Set KRONOS_ENABLED=true and restart StockPulse.")
    print("Verify readiness in Settings → AI & Models → Local Models (Kronos status).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# requeue
