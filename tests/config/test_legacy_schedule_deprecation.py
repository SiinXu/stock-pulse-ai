# -*- coding: utf-8 -*-
"""Deprecation markers and one-shot startup log for legacy SCHEDULE_*."""

from __future__ import annotations

import logging

import pytest

from src.config_parts import loading as loading_module
from src.config_parts.model import Config


@pytest.fixture(autouse=True)
def _reset_deprecation_flag():
    loading_module._LEGACY_SCHEDULE_DEPRECATION_LOGGED = False
    yield
    loading_module._LEGACY_SCHEDULE_DEPRECATION_LOGGED = False


def test_legacy_schedule_deprecation_logs_once_when_env_key_present(caplog):
    present = {"SCHEDULE_ENABLED"}

    with caplog.at_level(logging.WARNING, logger="src.config_parts.defaults"):
        loading_module.emit_legacy_schedule_deprecation_if_needed(
            had_bootstrap_key=lambda key: key in present,
            get_env_file_value=lambda key: None,
        )
        loading_module.emit_legacy_schedule_deprecation_if_needed(
            had_bootstrap_key=lambda key: key in present,
            get_env_file_value=lambda key: None,
        )

    messages = [
        r.getMessage()
        for r in caplog.records
        if "Deprecation: legacy schedule" in r.getMessage()
    ]
    # logger name may be src.config_parts.defaults (loading.logger) — also try any logger
    if not messages:
        messages = [
            r.getMessage()
            for r in caplog.records
            if "Deprecation: legacy schedule" in r.getMessage()
        ]
    assert len(messages) == 1
    assert "SCHEDULE_ENABLED" in messages[0]
    assert "versioned scheduled tasks" in messages[0].lower()


def test_legacy_schedule_deprecation_logs_when_only_env_file_has_key(caplog):
    files = {"SCHEDULE_TIME": "18:00"}

    with caplog.at_level(logging.WARNING):
        loading_module.emit_legacy_schedule_deprecation_if_needed(
            had_bootstrap_key=lambda key: False,
            get_env_file_value=lambda key: files.get(key),
        )

    messages = [
        r.getMessage()
        for r in caplog.records
        if "Deprecation: legacy schedule" in r.getMessage()
    ]
    assert len(messages) == 1
    assert "SCHEDULE_TIME" in messages[0]


def test_legacy_schedule_deprecation_silent_when_unset(caplog):
    with caplog.at_level(logging.WARNING):
        loading_module.emit_legacy_schedule_deprecation_if_needed(
            had_bootstrap_key=lambda key: False,
            get_env_file_value=lambda key: None,
        )

    messages = [
        r.getMessage()
        for r in caplog.records
        if "Deprecation: legacy schedule" in r.getMessage()
    ]
    assert messages == []


def test_legacy_schedule_env_keys_constant_matches_registry_surface():
    assert loading_module.LEGACY_SCHEDULE_ENV_KEYS == (
        "SCHEDULE_ENABLED",
        "SCHEDULE_TIME",
        "SCHEDULE_TIMES",
        "SCHEDULE_RUN_IMMEDIATELY",
    )


def test_config_exposes_installed_deprecation_method():
    assert callable(getattr(Config, "_maybe_log_legacy_schedule_deprecation", None))
