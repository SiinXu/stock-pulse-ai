# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for config presets and stockpulse-profile YAML (no secrets)."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest
import yaml

from src.services.config_presets import (
    PROFILE_API_VERSION,
    PROFILE_KIND,
    get_official_preset,
    is_exportable_config_key,
    is_secret_config_key,
    list_official_presets,
)
from src.services.config_profile_service import (
    ConfigProfileNotFoundError,
    ConfigProfileService,
    ConfigProfileValidationError,
)
from src.services.system_config_service import ConfigConflictError


class FakeSystemConfigService:
    def __init__(self, items: List[Dict[str, Any]] | None = None) -> None:
        self.version = "v1"
        self.items = list(items or [])
        self.update_calls: List[Dict[str, Any]] = []

    def get_config(self, include_schema: bool = True, mask_token: str = "******") -> Dict[str, Any]:
        del include_schema, mask_token
        return {
            "config_version": self.version,
            "items": list(self.items),
            "mask_token": "******",
        }

    def update(self, **kwargs: Any) -> Dict[str, Any]:
        self.update_calls.append(kwargs)
        if kwargs.get("config_version") != self.version:
            raise ConfigConflictError(current_version=self.version)
        updated_keys: List[str] = []
        by_key = {str(item["key"]).upper(): item for item in self.items}
        for entry in kwargs.get("items") or []:
            key = str(entry["key"]).upper()
            value = str(entry.get("value") or "")
            if is_secret_config_key(key):
                raise AssertionError(f"secret key reached update: {key}")
            by_key[key] = {
                "key": key,
                "value": value,
                "raw_value_exists": True,
                "is_masked": False,
            }
            updated_keys.append(key)
        self.items = list(by_key.values())
        self.version = f"v{len(self.update_calls) + 1}"
        return {
            "config_version": self.version,
            "updated_keys": updated_keys,
        }


def _service(**kwargs: Any):
    fake = FakeSystemConfigService(
        items=[
            {
                "key": "GENERATION_BACKEND",
                "value": "litellm",
                "raw_value_exists": True,
                "is_masked": False,
            },
            {
                "key": "OPENAI_API_KEY",
                "value": "******",
                "raw_value_exists": True,
                "is_masked": True,
            },
            {
                "key": "LLM_DEEPSEEK_API_KEY",
                "value": "sk-secret-should-never-export",
                "raw_value_exists": True,
                "is_masked": True,
            },
        ]
    )
    return ConfigProfileService(system_config_service=fake, **kwargs), fake


def test_official_presets_are_secret_free() -> None:
    presets = list_official_presets()
    assert len(presets) >= 3
    for preset in presets:
        assert get_official_preset(preset["id"]) is not None
        for key in (preset.get("config_values") or {}):
            assert not is_secret_config_key(key)


def test_secret_key_detection() -> None:
    assert is_secret_config_key("OPENAI_API_KEY")
    assert is_secret_config_key("LLM_FOO_API_KEYS")
    assert is_secret_config_key("WECHAT_TOKEN")
    assert is_secret_config_key("FEISHU_APP_SECRET")
    assert is_secret_config_key("ADMIN_PASSWORD")
    assert is_secret_config_key("LLM_X_EXTRA_HEADERS")
    assert not is_secret_config_key("GENERATION_BACKEND")
    assert not is_secret_config_key("LITELLM_MODEL")
    assert is_exportable_config_key("GENERATION_BACKEND")
    assert not is_exportable_config_key("OPENAI_API_KEY")


def test_list_presets_prefers_local_when_ollama_healthy() -> None:
    service, _fake = _service(ollama_probe=lambda: True, which_executable=lambda _name: None)
    payload = service.list_presets()
    assert payload["recommended_preset_id"] == "local-first"
    assert payload["detection"]["ollama_healthy"] is True
    assert payload["presets"][0]["id"] == "local-first"
    assert payload["presets"][0]["recommended"] is True


def test_list_presets_prefers_cli_when_cli_present() -> None:
    service, _fake = _service(
        ollama_probe=lambda: False,
        which_executable=lambda name: "/usr/bin/codex" if name == "codex" else None,
    )
    payload = service.list_presets()
    assert payload["recommended_preset_id"] == "cli-backends"
    assert "codex_cli" in payload["detection"]["cli_detected"]


def test_export_never_contains_secret_keys_or_values() -> None:
    service, fake = _service()
    fake.items.append(
        {
            "key": "CUSTOM_API_TOKEN",
            "value": "tok_live_should_not_export",
            "raw_value_exists": True,
            "is_masked": False,
        }
    )
    exported = service.export_profile(name="unit-test")
    content = exported["content"]
    assert "OPENAI_API_KEY" not in content
    assert "LLM_DEEPSEEK_API_KEY" not in content
    assert "CUSTOM_API_TOKEN" not in content
    assert "sk-secret" not in content
    assert "tok_live_should_not_export" not in content
    assert "GENERATION_BACKEND" in content
    document = yaml.safe_load(content)
    assert document["apiVersion"] == PROFILE_API_VERSION
    assert document["kind"] == PROFILE_KIND
    config = document["spec"]["llm"]["config"]
    assert "OPENAI_API_KEY" not in config
    assert exported["keys_redacted"] >= 2


def test_import_rejects_secret_bearing_profile() -> None:
    service, fake = _service()
    bad = {
        "apiVersion": PROFILE_API_VERSION,
        "kind": PROFILE_KIND,
        "metadata": {"name": "evil", "displayName": "Evil"},
        "spec": {
            "llm": {
                "preferenceOrder": ["cloud"],
                "config": {
                    "GENERATION_BACKEND": "litellm",
                    "OPENAI_API_KEY": "sk-evil",
                },
            },
            "strategies": {"enabled": []},
            "features": {},
            "requirements": {},
        },
    }
    with pytest.raises(ConfigProfileValidationError) as exc_info:
        service.preview_import(
            content=yaml.safe_dump(bad),
            config_version=fake.version,
        )
    assert exc_info.value.error_code == "config_profile_secret_rejected"


def test_import_rejects_unknown_api_version() -> None:
    service, fake = _service()
    bad = {
        "apiVersion": "stockpulse/v999",
        "kind": PROFILE_KIND,
        "metadata": {"name": "x"},
        "spec": {"llm": {"config": {}}, "strategies": {}, "features": {}},
    }
    with pytest.raises(ConfigProfileValidationError) as exc_info:
        service.preview_import(content=yaml.safe_dump(bad), config_version=fake.version)
    assert exc_info.value.error_code == "config_profile_api_version_unsupported"


def test_round_trip_export_import_preview_and_apply() -> None:
    service, fake = _service()
    applied = service.apply_preset(
        "local-first",
        config_version=fake.version,
        reload_now=True,
    )
    assert applied["applied"] is True
    assert fake.update_calls
    for call in fake.update_calls:
        for item in call["items"]:
            assert not is_secret_config_key(item["key"])

    exported = service.export_profile(name="roundtrip")
    content = exported["content"]
    service.apply_preset("cloud-balanced", config_version=fake.version)
    preview = service.preview_import(content=content, config_version=fake.version)
    assert preview["valid"] is True
    assert preview["change_count"] >= 1
    result = service.apply_import(content=content, config_version=fake.version)
    assert result["applied"] is True
    re_export = service.export_profile(name="after")
    assert "OPENAI_API_KEY" not in re_export["content"]
    restored = yaml.safe_load(re_export["content"])
    assert restored["spec"]["llm"]["config"].get("LLM_OLLAMA_PROTOCOL") == "ollama"


def test_apply_unknown_preset() -> None:
    service, fake = _service()
    with pytest.raises(ConfigProfileNotFoundError):
        service.apply_preset("does-not-exist", config_version=fake.version)


def test_version_conflict_on_preview() -> None:
    service, _fake = _service()
    with pytest.raises(ConfigConflictError):
        service.preview_preset_apply("local-first", config_version="stale")
