from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.stage_playwright_diagnostics import stage_playwright_diagnostics


def _write_report(root: Path, *, unexpected: int = 1) -> None:
    (root / "playwright-results.json").write_text(
        json.dumps({
            "stats": {
                "expected": 0,
                "skipped": 0,
                "unexpected": unexpected,
                "flaky": 0,
            },
            "errors": [{"message": "assertion failed"}],
            "suites": [],
        }),
        encoding="utf-8",
    )


def test_stages_strict_json_and_nested_text_logs_with_manifest(tmp_path: Path) -> None:
    source = tmp_path / "source"
    staging = tmp_path / "staging"
    nested_logs = source / "service-logs" / "backend-app"
    nested_logs.mkdir(parents=True)
    _write_report(source)
    (source / "service-logs" / "backend.log").write_text(
        "backend ready\n",
        encoding="utf-8",
    )
    (nested_logs / "stock_analysis.log").write_text(
        "analysis failed safely\n",
        encoding="utf-8",
    )

    manifest = stage_playwright_diagnostics(source, staging)

    assert sorted(path.relative_to(staging).as_posix() for path in staging.rglob("*") if path.is_file()) == [
        "manifest.json",
        "playwright-results.json",
        "service-logs/backend-app/stock_analysis.log",
        "service-logs/backend.log",
    ]
    assert [entry["path"] for entry in manifest["files"]] == [
        "playwright-results.json",
        "service-logs/backend-app/stock_analysis.log",
        "service-logs/backend.log",
    ]
    persisted_manifest = json.loads((staging / "manifest.json").read_text(encoding="utf-8"))
    assert persisted_manifest == manifest
    assert all(len(entry["sha256"]) == 64 for entry in manifest["files"])


@pytest.mark.parametrize("relative_path", [
    "playwright-results.json",
    "service-logs/diagnostic.txt",
])
def test_rejects_zip_content_disguised_as_allowlisted_file(
    tmp_path: Path,
    relative_path: str,
) -> None:
    source = tmp_path / "source"
    staging = tmp_path / "staging"
    source.mkdir()
    _write_report(source)
    target = source / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(target, "w") as archive:
        archive.writestr("opaque-resource", b"\x00\x01safe-looking-binary")

    with pytest.raises(ValueError, match="archive content is not uploadable"):
        stage_playwright_diagnostics(source, staging)

    assert not staging.exists()


def test_rejects_invalid_playwright_json(tmp_path: Path) -> None:
    source = tmp_path / "source"
    staging = tmp_path / "staging"
    source.mkdir()
    (source / "playwright-results.json").write_text("{truncated", encoding="utf-8")

    with pytest.raises(ValueError, match="playwright-results.json is not valid JSON"):
        stage_playwright_diagnostics(source, staging)

    assert not staging.exists()


def test_rejects_symlinks_and_nonallowlisted_service_files(tmp_path: Path) -> None:
    source = tmp_path / "source"
    staging = tmp_path / "staging"
    logs = source / "service-logs"
    logs.mkdir(parents=True)
    _write_report(source)
    outside = tmp_path / "outside.log"
    outside.write_text("outside\n", encoding="utf-8")
    (logs / "linked.log").symlink_to(outside)

    with pytest.raises(ValueError, match="symbolic links are not uploadable"):
        stage_playwright_diagnostics(source, staging)

    (logs / "linked.log").unlink()
    (logs / "debug.bin").write_bytes(b"opaque")
    with pytest.raises(ValueError, match="service log is not allowlisted"):
        stage_playwright_diagnostics(source, staging)


def test_rejects_a_symlinked_staging_directory(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_report(source)
    outside = tmp_path / "outside"
    outside.mkdir()
    staging = tmp_path / "staging"
    staging.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="staging directory cannot be a symbolic link"):
        stage_playwright_diagnostics(source, staging)

    assert staging.is_symlink()
    assert list(outside.iterdir()) == []


def test_rejects_a_staging_directory_that_contains_the_source(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    source = staging / "source"
    source.mkdir(parents=True)
    _write_report(source)

    with pytest.raises(ValueError, match="must not overlap"):
        stage_playwright_diagnostics(source, staging)

    assert (source / "playwright-results.json").is_file()


def test_rejects_staging_inside_source_without_deleting_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_report(source)
    marker = source / "keep.txt"
    marker.write_text("keep\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must not overlap"):
        stage_playwright_diagnostics(source, source / "staging")

    assert marker.read_text(encoding="utf-8") == "keep\n"
    assert (source / "playwright-results.json").is_file()


def test_rejects_an_existing_staging_directory_without_deleting_it(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_report(source)
    staging = tmp_path / "staging"
    staging.mkdir()
    marker = staging / "keep.txt"
    marker.write_text("keep\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must not already exist"):
        stage_playwright_diagnostics(source, staging)

    assert marker.read_text(encoding="utf-8") == "keep\n"


@pytest.mark.parametrize("payload", [
    b"\x89PNG\r\n\x1a\nopaque",
    b"\xff\xd8\xffopaque",
    b"\x1a\x45\xdf\xa3opaque",
])
def test_rejects_media_magic_in_text_log(tmp_path: Path, payload: bytes) -> None:
    source = tmp_path / "source"
    staging = tmp_path / "staging"
    logs = source / "service-logs"
    logs.mkdir(parents=True)
    _write_report(source)
    (logs / "diagnostic.log").write_bytes(payload)

    with pytest.raises(ValueError, match="media content is not uploadable"):
        stage_playwright_diagnostics(source, staging)
