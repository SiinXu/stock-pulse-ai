# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""External discovery boundary regressions for trusted plugin directories."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.plugins import ExternalPluginLoader, PluginManager


def _manifest_payload(plugin_id: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": plugin_id,
        "name": plugin_id,
        "version": "1.0.0",
        "minAppVersion": "1.0.0",
        "description": "External loader test plugin.",
        "author": "StockPulse Tests",
        "permissions": [],
    }
    payload.update(overrides)
    return payload


def _write_candidate(
    root: Path,
    directory_name: str,
    plugin_id: str,
    source: str | None,
    **manifest_overrides: object,
) -> Path:
    candidate = root / directory_name
    candidate.mkdir(parents=True)
    (candidate / "manifest.json").write_text(
        json.dumps(_manifest_payload(plugin_id, **manifest_overrides)),
        encoding="utf-8",
    )
    if source is not None:
        (candidate / "plugin.py").write_text(source, encoding="utf-8")
    return candidate


_VALID_PLUGIN = """\
from src.plugins import Plugin as BasePlugin


class Plugin(BasePlugin):
    pass
"""


def test_external_loader_is_explicit_and_registration_does_not_load(tmp_path: Path) -> None:
    manager = PluginManager(application_version="2.0.0")
    loader = ExternalPluginLoader(manager)
    root = tmp_path / "plugins"
    root.mkdir()
    _write_candidate(root, "valid", "valid-plugin", _VALID_PLUGIN)

    assert loader.register_from_directory(None) == ()
    assert loader.register_from_directory("   ") == ()

    results = loader.register_from_directory(root)

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].state == "registered"
    assert manager.snapshot("valid-plugin").state == "registered"  # type: ignore[union-attr]
    assert manager.load("valid-plugin").success is True


def test_bad_candidates_are_isolated_and_later_plugin_still_registers(
    tmp_path: Path,
    caplog: object,
) -> None:
    manager = PluginManager(application_version="2.0.0")
    loader = ExternalPluginLoader(manager)
    root = tmp_path / "plugins"
    root.mkdir()

    malformed = root / "01-malformed"
    malformed.mkdir()
    (malformed / "manifest.json").write_text("{not-json", encoding="utf-8")
    _write_candidate(root, "02-missing", "missing-plugin", None)
    _write_candidate(root, "03-invalid-class", "invalid-plugin", "class Plugin:\n    pass\n")
    _write_candidate(
        root,
        "04-import-failure",
        "import-plugin",
        'raise RuntimeError("token=leaked-value")\n',
    )
    _write_candidate(
        root,
        "05-constructor-failure",
        "constructor-plugin",
        "from src.plugins import Plugin as BasePlugin\n"
        "class Plugin(BasePlugin):\n"
        "    def __init__(self, manifest):\n"
        '        raise RuntimeError("password=constructor-value")\n',
    )
    _write_candidate(root, "06-valid", "valid-plugin", _VALID_PLUGIN)
    caplog.set_level(logging.ERROR)  # type: ignore[attr-defined]

    results = loader.register_from_directory(root)

    assert [result.candidate for result in results] == [
        "01-malformed",
        "02-missing",
        "03-invalid-class",
        "04-import-failure",
        "05-constructor-failure",
        "06-valid",
    ]
    assert [result.error_code for result in results] == [
        "external_manifest_invalid",
        "external_entrypoint_missing",
        "external_entrypoint_invalid",
        "external_import_failed",
        "external_constructor_failed",
        None,
    ]
    assert [result.success for result in results] == [False, False, False, False, False, True]
    assert manager.plugin_ids() == ("valid-plugin",)
    assert "leaked-value" not in caplog.text  # type: ignore[attr-defined]
    assert "constructor-value" not in caplog.text  # type: ignore[attr-defined]


def test_manifest_traversal_and_symlink_escape_are_rejected(tmp_path: Path) -> None:
    manager = PluginManager(application_version="2.0.0")
    loader = ExternalPluginLoader(manager)
    root = tmp_path / "plugins"
    root.mkdir()
    _write_candidate(
        root,
        "01-traversal",
        "traversal-plugin",
        None,
        entrypoint="../outside.py:Plugin",
    )
    outside = tmp_path / "outside.py"
    outside.write_text(_VALID_PLUGIN, encoding="utf-8")
    symlink_candidate = _write_candidate(
        root,
        "02-symlink",
        "symlink-plugin",
        None,
    )
    (symlink_candidate / "plugin.py").symlink_to(outside)

    results = loader.register_from_directory(root)

    assert [result.error_code for result in results] == [
        "external_manifest_invalid",
        "external_entrypoint_unsafe",
    ]
    assert manager.plugin_ids() == ()


def test_loader_scans_direct_child_directories_only(tmp_path: Path) -> None:
    manager = PluginManager(application_version="2.0.0")
    loader = ExternalPluginLoader(manager)
    root = tmp_path / "plugins"
    nested_root = root / "container"
    nested_root.mkdir(parents=True)
    _write_candidate(nested_root, "nested", "nested-plugin", _VALID_PLUGIN)
    (root / "README.txt").write_text("ignored", encoding="utf-8")

    results = loader.register_from_directory(root)

    assert len(results) == 1
    assert results[0].candidate == "container"
    assert results[0].error_code == "external_manifest_unavailable"
    assert manager.contains("nested-plugin") is False


def test_incompatible_and_duplicate_plugins_are_rejected_before_import(tmp_path: Path) -> None:
    manager = PluginManager(application_version="1.0.0")
    loader = ExternalPluginLoader(manager)
    incompatible_root = tmp_path / "incompatible"
    incompatible_root.mkdir()
    _write_candidate(
        incompatible_root,
        "future",
        "future-plugin",
        'raise RuntimeError("must not import")\n',
        minAppVersion="2.0.0",
    )

    incompatible = loader.register_from_directory(incompatible_root)

    assert incompatible[0].error_code == "plugin_app_version_unsupported"

    duplicate_root = tmp_path / "duplicate"
    duplicate_root.mkdir()
    candidate = _write_candidate(duplicate_root, "duplicate", "duplicate-plugin", _VALID_PLUGIN)
    assert loader.register_from_directory(duplicate_root)[0].success is True
    (candidate / "plugin.py").write_text('raise RuntimeError("must not reimport")\n', encoding="utf-8")

    duplicate = loader.register_from_directory(duplicate_root)

    assert duplicate[0].error_code == "plugin_id_conflict"
    assert manager.snapshot("duplicate-plugin").state == "registered"  # type: ignore[union-attr]


def test_unavailable_configured_directory_returns_safe_result(tmp_path: Path) -> None:
    loader = ExternalPluginLoader(PluginManager(application_version="1.0.0"))

    result = loader.register_from_directory(tmp_path / "missing")

    assert len(result) == 1
    assert result[0].candidate == "plugins_dir"
    assert result[0].error_code == "external_plugins_directory_unavailable"


def test_unexpected_candidate_failure_does_not_stop_later_candidate(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    manager = PluginManager(application_version="1.0.0")
    loader = ExternalPluginLoader(manager)
    root = tmp_path / "plugins"
    root.mkdir()
    _write_candidate(root, "01-failing", "failing-plugin", _VALID_PLUGIN)
    _write_candidate(root, "02-valid", "valid-plugin", _VALID_PLUGIN)
    original = loader._register_candidate

    def register_candidate(candidate: Path):
        if candidate.name == "01-failing":
            raise RuntimeError("token=unexpected-value")
        return original(candidate)

    monkeypatch.setattr(loader, "_register_candidate", register_candidate)  # type: ignore[attr-defined]

    results = loader.register_from_directory(root)

    assert [result.error_code for result in results] == ["external_candidate_failed", None]
    assert manager.plugin_ids() == ("valid-plugin",)
