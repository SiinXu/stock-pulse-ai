"""Offline tests for the Kronos weight download helper."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "download_kronos_weights.py"


def test_help_works_without_optional_deps() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "download" in result.stdout.lower()
    assert "--yes" in result.stdout
    assert "--weights-dir" in result.stdout


def test_list_sizes_works_without_huggingface_hub() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--list-sizes"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "mini" in result.stdout
    assert "MB" in result.stdout


def test_dry_run_requires_weights_dir_and_does_not_download(tmp_path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--size",
            "mini",
            "--weights-dir",
            str(tmp_path / "kronos"),
            "--dry-run",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Dry run" in result.stdout
    assert "approx" in result.stdout.lower() or "MB" in result.stdout
    assert not (tmp_path / "kronos").exists() or not any((tmp_path / "kronos").iterdir())


def test_missing_yes_in_noninteractive_aborts_without_download(tmp_path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--size",
            "mini",
            "--weights-dir",
            str(tmp_path / "kronos"),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    assert result.returncode != 0
    assert not (tmp_path / "kronos" / "Kronos-mini").exists()
