#!/usr/bin/env python3
"""Build the exact text-only Playwright diagnostics upload directory."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import TypedDict
from zipfile import is_zipfile


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
WEBM_EBML_SIGNATURE = b"\x1a\x45\xdf\xa3"
MEDIA_SIGNATURES = (PNG_SIGNATURE, JPEG_SIGNATURE, WEBM_EBML_SIGNATURE)
ALLOWED_LOG_SUFFIXES = frozenset({".log", ".txt"})


class ManifestEntry(TypedDict):
    path: str
    sha256: str
    size: int


class DiagnosticsManifest(TypedDict):
    version: int
    files: list[ManifestEntry]


def _safe_relative_label(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return "[diagnostic]"


def _read_uploadable_text(path: Path, source_root: Path) -> bytes:
    label = _safe_relative_label(path, source_root)
    if path.is_symlink():
        raise ValueError(f'{label}: symbolic links are not uploadable')
    if not path.is_file():
        raise ValueError(f'{label}: only ordinary files are uploadable')
    if is_zipfile(path):
        raise ValueError(f'{label}: archive content is not uploadable')
    data = path.read_bytes()
    if data.startswith(MEDIA_SIGNATURES):
        raise ValueError(f'{label}: media content is not uploadable')
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f'{label}: diagnostics must be UTF-8 text') from error
    if b"\x00" in data:
        raise ValueError(f'{label}: diagnostics must be text, not binary data')
    return data


def _validate_playwright_report(data: bytes) -> None:
    try:
        report = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("playwright-results.json is not valid JSON") from error
    if not isinstance(report, dict):
        raise ValueError("playwright-results.json must contain a JSON object")
    stats = report.get("stats")
    if not isinstance(stats, dict):
        raise ValueError("playwright-results.json must contain reporter stats")
    for key in ("expected", "skipped", "unexpected", "flaky"):
        value = stats.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"playwright-results.json has invalid stats.{key}")


def _service_log_files(source_root: Path) -> list[Path]:
    log_root = source_root / "service-logs"
    if not log_root.exists():
        return []
    if log_root.is_symlink() or not log_root.is_dir():
        raise ValueError("service-logs: symbolic links and non-directories are not uploadable")

    files: list[Path] = []
    for path in sorted(log_root.rglob("*")):
        label = _safe_relative_label(path, source_root)
        if path.is_symlink():
            raise ValueError(f'{label}: symbolic links are not uploadable')
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f'{label}: only ordinary files are uploadable')
        if path.suffix.lower() not in ALLOWED_LOG_SUFFIXES:
            raise ValueError(f'{label}: service log is not allowlisted')
        files.append(path)
    return files


def _manifest_entry(relative_path: str, data: bytes) -> ManifestEntry:
    return {
        "path": relative_path,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    }


def stage_playwright_diagnostics(
    source_root: Path,
    staging_root: Path,
) -> DiagnosticsManifest:
    """Validate and copy the exact JSON/text diagnostics upload set."""
    if source_root.is_symlink():
        raise ValueError("Playwright diagnostics source directory cannot be a symbolic link")
    if staging_root.is_symlink():
        raise ValueError("Playwright diagnostics staging directory cannot be a symbolic link")
    source_root = source_root.resolve()
    staging_root = staging_root.resolve()
    if (
        source_root == staging_root
        or source_root in staging_root.parents
        or staging_root in source_root.parents
    ):
        raise ValueError("staging directory and Playwright run directory must not overlap")
    if not source_root.is_dir():
        raise ValueError("Playwright diagnostics source directory is unavailable")

    report_path = source_root / "playwright-results.json"
    report_data = _read_uploadable_text(report_path, source_root)
    _validate_playwright_report(report_data)

    validated_files: list[tuple[str, bytes]] = [
        ("playwright-results.json", report_data),
    ]
    for path in _service_log_files(source_root):
        relative_path = path.relative_to(source_root).as_posix()
        validated_files.append((relative_path, _read_uploadable_text(path, source_root)))
    validated_files.sort(key=lambda item: item[0])

    if staging_root.exists():
        raise ValueError("staging directory must not already exist")
    staging_root.mkdir(parents=True)

    entries: list[ManifestEntry] = []
    for relative_path, data in validated_files:
        destination = staging_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        entries.append(_manifest_entry(relative_path, data))

    manifest: DiagnosticsManifest = {"version": 1, "files": entries}
    (staging_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path)
    parser.add_argument("staging_root", type=Path)
    args = parser.parse_args(argv)
    try:
        manifest = stage_playwright_diagnostics(args.source_root, args.staging_root)
    except (OSError, ValueError) as error:
        print(f"Playwright diagnostics staging failed: {error}", file=sys.stderr)
        return 1
    print(f"Playwright diagnostics staged: {len(manifest['files'])} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
