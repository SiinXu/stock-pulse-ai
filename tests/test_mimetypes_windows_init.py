# -*- coding: utf-8 -*-
"""Contract tests for MIME database initialization during API startup."""

from __future__ import annotations

import mimetypes
from collections.abc import Iterator

import pytest

from api import app as app_module


@pytest.fixture
def isolated_mimetypes_state() -> Iterator[None]:
    attributes = (
        "inited",
        "_db",
        "suffix_map",
        "encodings_map",
        "types_map",
        "common_types",
    )
    original_state = {name: getattr(mimetypes, name) for name in attributes}
    try:
        yield
    finally:
        for name, value in original_state.items():
            setattr(mimetypes, name, value)


def _simulate_cold_start() -> None:
    mimetypes.inited = False
    mimetypes._db = None


def test_windows_cold_start_skips_registry_and_restores_reader(
    isolated_mimetypes_state: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _simulate_cold_start()
    monkeypatch.setattr(app_module.sys, "platform", "win32")

    def fail_registry_read(_self, strict: bool = True) -> None:
        raise AssertionError(f"Windows registry reader was called with strict={strict}")

    monkeypatch.setattr(
        mimetypes.MimeTypes,
        "read_windows_registry",
        fail_registry_read,
    )

    app_module._register_frontend_asset_mime_types()

    assert mimetypes.inited is True
    assert mimetypes.MimeTypes.read_windows_registry is fail_registry_read
    assert mimetypes.types_map is mimetypes._db.types_map[True]
    assert mimetypes.guess_type("app.js")[0] == "text/javascript"
    assert mimetypes.guess_type("style.css")[0] == "text/css"


def test_windows_cold_start_restores_reader_when_initialization_fails(
    isolated_mimetypes_state: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _simulate_cold_start()
    monkeypatch.setattr(app_module.sys, "platform", "win32")
    registry_reader = mimetypes.MimeTypes.read_windows_registry

    def fail_initialization() -> None:
        raise RuntimeError("synthetic initialization failure")

    monkeypatch.setattr(mimetypes, "init", fail_initialization)

    with pytest.raises(RuntimeError, match="synthetic initialization failure"):
        app_module._initialize_mimetypes_without_windows_registry()

    assert mimetypes.MimeTypes.read_windows_registry is registry_reader


def test_non_windows_cold_start_keeps_standard_mime_database(
    isolated_mimetypes_state: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _simulate_cold_start()
    monkeypatch.setattr(app_module.sys, "platform", "linux")

    app_module._register_frontend_asset_mime_types()

    assert mimetypes.guess_type("index.html")[0] == "text/html"
    assert mimetypes.guess_type("report.pdf")[0] == "application/pdf"
    assert mimetypes.guess_type("app.js")[0] == "text/javascript"


def test_initialized_windows_state_does_not_reinitialize(
    isolated_mimetypes_state: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mimetypes.init(files=[])
    monkeypatch.setattr(app_module.sys, "platform", "win32")

    def fail_reinitialization() -> None:
        raise AssertionError("MIME database was initialized twice")

    monkeypatch.setattr(mimetypes, "init", fail_reinitialization)

    app_module._register_frontend_asset_mime_types()

    assert mimetypes.guess_type("app.js")[0] == "text/javascript"
