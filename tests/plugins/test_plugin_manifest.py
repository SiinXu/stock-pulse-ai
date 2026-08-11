# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Manifest contract regressions for the plugin core."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.plugins import PluginManifest


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "example-provider",
        "name": "Example Provider",
        "version": "1.2.0",
        "minAppVersion": "1.0.0",
        "description": "Adds a trusted test provider.",
        "author": "StockPulse Tests",
        "permissions": ["network", "environment.read"],
    }
    payload.update(overrides)
    return payload


def test_manifest_aliases_defaults_and_json_serialization() -> None:
    manifest = PluginManifest.model_validate(_payload())

    assert manifest.min_app_version == "1.0.0"
    assert manifest.api_version == "1"
    assert manifest.entrypoint == "plugin.py:Plugin"
    assert manifest.permissions == ("network", "environment.read")
    assert manifest.model_dump(by_alias=True, mode="json") == {
        **_payload(),
        "apiVersion": "1",
        "entrypoint": "plugin.py:Plugin",
        "settings": [],
    }

    with pytest.raises(ValidationError):
        manifest.name = "Changed"  # type: ignore[misc]


def test_manifest_accepts_python_field_names() -> None:
    payload = _payload()
    payload["min_app_version"] = payload.pop("minAppVersion")
    payload["api_version"] = "2"

    manifest = PluginManifest.model_validate(payload)

    assert manifest.min_app_version == "1.0.0"
    assert manifest.api_version == "2"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", "Example"),
        ("id", "-example"),
        ("version", "1.2"),
        ("version", "v1.2.3"),
        ("version", "01.2.3"),
        ("minAppVersion", "1.0"),
        ("apiVersion", 1),
        ("apiVersion", "0"),
        ("permissions", "network"),
        ("permissions", ["Network"]),
        ("permissions", ["network", "network"]),
        ("entrypoint", "../plugin.py:Plugin"),
        ("entrypoint", "/tmp/plugin.py:Plugin"),
        ("entrypoint", "nested/../plugin.py:Plugin"),
        ("entrypoint", "nested\\plugin.py:Plugin"),
        ("entrypoint", "plugin.txt:Plugin"),
        ("entrypoint", "plugin.py:invalid.class"),
    ],
)
def test_manifest_rejects_invalid_contract_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        PluginManifest.model_validate(_payload(**{field: value}))


def test_manifest_requires_permissions_and_rejects_extras() -> None:
    without_permissions = _payload()
    del without_permissions["permissions"]

    with pytest.raises(ValidationError):
        PluginManifest.model_validate(without_permissions)
    with pytest.raises(ValidationError):
        PluginManifest.model_validate(_payload(unknownField=True))


@pytest.mark.parametrize("field", ["name", "description", "author"])
def test_manifest_rejects_blank_required_text(field: str) -> None:
    with pytest.raises(ValidationError):
        PluginManifest.model_validate(_payload(**{field: "   "}))


def test_manifest_accepts_toolsurface_capability_permissions() -> None:
    manifest = PluginManifest.model_validate(
        _payload(permissions=["market_data:read", "local_model:execute"])
    )
    assert manifest.permissions == ("market_data:read", "local_model:execute")


def test_manifest_accepts_strict_declarative_settings_schema() -> None:
    manifest = PluginManifest.model_validate(
        _payload(
            settings=[
                {
                    "key": "risk.limit",
                    "title": "Risk limit",
                    "description": "Maximum accepted risk score.",
                    "dataType": "number",
                    "uiControl": "number",
                    "defaultValue": 0.5,
                    "validation": {"minimum": 0.0, "maximum": 1.0},
                    "displayOrder": 10,
                },
                {
                    "key": "mode",
                    "title": "Mode",
                    "dataType": "string",
                    "uiControl": "select",
                    "defaultValue": "safe",
                    "options": [
                        {"label": "Safe", "value": "safe"},
                        {"label": "Fast", "value": "fast"},
                    ],
                },
            ]
        )
    )

    assert [field.key for field in manifest.settings] == ["risk.limit", "mode"]
    assert manifest.settings[0].validation.maximum == 1.0


@pytest.mark.parametrize(
    "settings",
    [
        [
            {"key": "UPPER", "title": "Bad", "dataType": "string", "uiControl": "text"}
        ],
        [
            {"key": "flag", "title": "Flag", "dataType": "boolean", "uiControl": "text"}
        ],
        [
            {
                "key": "secret",
                "title": "Secret",
                "dataType": "string",
                "uiControl": "password",
                "isSensitive": True,
                "defaultValue": "must-not-ship",
            }
        ],
        [
            {"key": "mode", "title": "Mode", "dataType": "string", "uiControl": "select"}
        ],
        [
            {"key": "count", "title": "Count", "dataType": "integer", "uiControl": "number", "defaultValue": True}
        ],
        [
            {"key": "ratio", "title": "Ratio", "dataType": "number", "uiControl": "number", "defaultValue": float("nan")}
        ],
        [
            {"key": "same", "title": "One", "dataType": "string", "uiControl": "text"},
            {"key": "same", "title": "Two", "dataType": "string", "uiControl": "text"},
        ],
    ],
)
def test_manifest_rejects_invalid_settings_contract(settings: object) -> None:
    with pytest.raises(ValidationError):
        PluginManifest.model_validate(_payload(settings=settings))
