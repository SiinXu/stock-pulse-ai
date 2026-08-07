# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""HTTP contract tests for config preset / profile endpoints."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import yaml

from api.v1.endpoints import config_profiles
from src.services.config_presets import PROFILE_API_VERSION, PROFILE_KIND, is_secret_config_key
from src.services.config_profile_service import ConfigProfileService
from src.services.system_config_service import ConfigConflictError


class FakeSystemConfigService:
    def __init__(self) -> None:
        self.version = "cfg-1"
        self.items: List[Dict[str, Any]] = [
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
        ]
        self.update_calls: List[Dict[str, Any]] = []

    def get_config(self, include_schema: bool = True, mask_token: str = "******") -> Dict[str, Any]:
        del include_schema, mask_token
        return {"config_version": self.version, "items": list(self.items)}

    def update(self, **kwargs: Any) -> Dict[str, Any]:
        self.update_calls.append(kwargs)
        if kwargs.get("config_version") != self.version:
            raise ConfigConflictError(current_version=self.version)
        by_key = {str(item["key"]).upper(): item for item in self.items}
        updated: List[str] = []
        for entry in kwargs.get("items") or []:
            key = str(entry["key"]).upper()
            assert not is_secret_config_key(key)
            by_key[key] = {
                "key": key,
                "value": str(entry.get("value") or ""),
                "raw_value_exists": True,
                "is_masked": False,
            }
            updated.append(key)
        self.items = list(by_key.values())
        self.version = f"cfg-{len(self.update_calls) + 1}"
        return {"config_version": self.version, "updated_keys": updated}


@pytest.fixture
def client():
    fake_config = FakeSystemConfigService()
    service = ConfigProfileService(
        system_config_service=fake_config,
        ollama_probe=lambda: False,
        which_executable=lambda _name: None,
    )
    app = FastAPI()
    app.include_router(config_profiles.router, prefix="/api/v1/config-profiles")
    app.state.config_profile_service = service
    with TestClient(app) as test_client:
        yield test_client, fake_config


def test_list_presets(client) -> None:
    test_client, _fake = client
    response = test_client.get("/api/v1/config-profiles/presets")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "presets" in payload
    assert len(payload["presets"]) >= 3
    ids = {item["id"] for item in payload["presets"]}
    assert {"local-first", "cli-backends", "cloud-balanced"}.issubset(ids)


def test_preview_and_apply_preset(client) -> None:
    test_client, fake = client
    preview = test_client.post(
        "/api/v1/config-profiles/presets/local-first/preview",
        json={"config_version": fake.version},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["preset_id"] == "local-first"
    assert body["change_count"] >= 1
    assert all("from_value" in change for change in body["changes"])

    applied = test_client.post(
        "/api/v1/config-profiles/presets/local-first/apply",
        json={"config_version": fake.version, "reload_now": True},
    )
    assert applied.status_code == 200, applied.text
    result = applied.json()
    assert result["applied"] is True
    assert fake.update_calls
    for call in fake.update_calls:
        for item in call["items"]:
            assert not is_secret_config_key(item["key"])


def test_export_strips_secrets(client) -> None:
    test_client, _fake = client
    response = test_client.get("/api/v1/config-profiles/export")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "OPENAI_API_KEY" not in payload["content"]
    assert payload["keys_redacted"] >= 1
    document = yaml.safe_load(payload["content"])
    assert document["apiVersion"] == PROFILE_API_VERSION
    assert document["kind"] == PROFILE_KIND


def test_import_rejects_secrets(client) -> None:
    test_client, fake = client
    evil = yaml.safe_dump(
        {
            "apiVersion": PROFILE_API_VERSION,
            "kind": PROFILE_KIND,
            "metadata": {"name": "evil"},
            "spec": {
                "llm": {"config": {"OPENAI_API_KEY": "sk-x", "GENERATION_BACKEND": "litellm"}},
                "strategies": {"enabled": []},
                "features": {},
            },
        }
    )
    response = test_client.post(
        "/api/v1/config-profiles/import/preview",
        json={"config_version": fake.version, "content": evil},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error"] == "config_profile_secret_rejected"


def test_import_preview_and_apply_round_trip(client) -> None:
    test_client, fake = client
    test_client.post(
        "/api/v1/config-profiles/presets/cloud-balanced/apply",
        json={"config_version": fake.version},
    )
    exported = test_client.get("/api/v1/config-profiles/export").json()
    test_client.post(
        "/api/v1/config-profiles/presets/power-user/apply",
        json={"config_version": fake.version},
    )
    preview = test_client.post(
        "/api/v1/config-profiles/import/preview",
        json={"config_version": fake.version, "content": exported["content"]},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["valid"] is True
    applied = test_client.post(
        "/api/v1/config-profiles/import/apply",
        json={"config_version": fake.version, "content": exported["content"]},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["applied"] is True
