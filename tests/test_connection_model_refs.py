# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Connection-aware model identity and runtime routing contracts."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

from src.config import Config
from src.core.config_manager import ConfigManager
from src.llm.model_ref import decode_model_ref, encode_model_ref
from src.services.system_config_service import SystemConfigService
from tests._llm_env_isolation import restore_ambient_llm_env, strip_ambient_llm_env


_DUPLICATE_CONNECTIONS = (
    "LLM_CONFIG_MODE=channels\n"
    "LLM_CHANNELS=openai_personal,openai_work\n"
    "LLM_OPENAI_PERSONAL_PROVIDER=openai\n"
    "LLM_OPENAI_PERSONAL_PROTOCOL=openai\n"
    "LLM_OPENAI_PERSONAL_BASE_URL=https://personal.example/v1\n"
    "LLM_OPENAI_PERSONAL_API_KEY=sk-personal\n"
    "LLM_OPENAI_PERSONAL_MODELS=gpt-4o\n"
    "LLM_OPENAI_PERSONAL_ENABLED=true\n"
    "LLM_OPENAI_WORK_PROVIDER=openai\n"
    "LLM_OPENAI_WORK_PROTOCOL=openai\n"
    "LLM_OPENAI_WORK_BASE_URL=https://work.example/v1\n"
    "LLM_OPENAI_WORK_API_KEY=sk-work\n"
    "LLM_OPENAI_WORK_MODELS=gpt-4o\n"
    "LLM_OPENAI_WORK_ENABLED=true\n"
)


@contextmanager
def _isolated_service(
    tmp_path: Path,
    monkeypatch,
    content: str,
) -> Iterator[tuple[SystemConfigService, Path]]:
    saved_llm_env = strip_ambient_llm_env()
    original_env_file = os.environ.get("ENV_FILE")
    env_path = tmp_path / ".env"
    env_path.write_text(content, encoding="utf-8")
    try:
        monkeypatch.setenv("ENV_FILE", str(env_path))
        Config.reset_instance()
        yield SystemConfigService(manager=ConfigManager(env_path=env_path)), env_path
    finally:
        Config.reset_instance()
        if original_env_file is None:
            os.environ.pop("ENV_FILE", None)
        else:
            os.environ["ENV_FILE"] = original_env_file
        restore_ambient_llm_env(saved_llm_env)


def test_model_ref_round_trip_is_versioned_and_csv_safe() -> None:
    value = encode_model_ref("openai_work", "openai/org/model:latest")
    assert "," not in value
    assert decode_model_ref(value) is not None
    assert decode_model_ref(value).connection_id == "openai_work"
    assert decode_model_ref(value).runtime_route == "openai/org/model:latest"
    assert decode_model_ref("openai/gpt-4o") is None


def test_available_models_keeps_same_route_for_each_connection(tmp_path, monkeypatch) -> None:
    with _isolated_service(tmp_path, monkeypatch, _DUPLICATE_CONNECTIONS) as (service, _):
        models = service.get_available_models()["models"]

    assert [(model["connection_id"], model["route"]) for model in models] == [
        ("openai_personal", "openai/gpt-4o"),
        ("openai_work", "openai/gpt-4o"),
    ]
    assert len({model["model_ref"] for model in models}) == 2


def test_selected_model_ref_routes_to_exact_connection(tmp_path, monkeypatch) -> None:
    selected_ref = encode_model_ref("openai_work", "openai/gpt-4o")
    with _isolated_service(
        tmp_path,
        monkeypatch,
        _DUPLICATE_CONNECTIONS + f"LITELLM_MODEL={selected_ref}\n",
    ):
        config = Config.get_instance()
        selected_entries = [
            entry for entry in config.llm_model_list
            if entry.get("model_name") == selected_ref
        ]
        assert len(selected_entries) == 1
        assert selected_entries[0]["litellm_params"] == {
            "model": "openai/gpt-4o",
            "api_key": "sk-work",
            "api_base": "https://work.example/v1",
        }
        assert config.litellm_model == selected_ref
        assert not [
            issue
            for issue in config.validate_structured()
            if issue.field == "LITELLM_MODEL" and issue.severity == "error"
        ]


def test_ambiguous_legacy_route_requires_connection_confirmation(tmp_path, monkeypatch) -> None:
    with _isolated_service(
        tmp_path,
        monkeypatch,
        _DUPLICATE_CONNECTIONS + "LITELLM_MODEL=openai/gpt-4o\n",
    ) as (service, _):
        result = service.validate([
            {"key": "LITELLM_MODEL", "value": "openai/gpt-4o"},
        ])

    issue = next(issue for issue in result["issues"] if issue["code"] == "ambiguous_model_route")
    assert not result["valid"]
    assert issue["details"]["connection_ids"] == ["openai_personal", "openai_work"]
    assert len(issue["details"]["model_refs"]) == 2


@pytest.mark.parametrize(
    "assignment_key",
    [
        "LITELLM_MODEL",
        "AGENT_LITELLM_MODEL",
        "VISION_MODEL",
        "LITELLM_FALLBACK_MODELS",
    ],
)
def test_all_task_routes_reject_ambiguous_legacy_assignment(
    tmp_path,
    monkeypatch,
    assignment_key: str,
) -> None:
    route = "openai/gpt-4o"
    with _isolated_service(
        tmp_path,
        monkeypatch,
        _DUPLICATE_CONNECTIONS + f"{assignment_key}={route}\n",
    ) as (service, _):
        result = service.validate([{"key": assignment_key, "value": route}])

    matching_issues = [
        issue
        for issue in result["issues"]
        if issue["key"] == assignment_key
        and issue["code"] == "ambiguous_model_route"
    ]
    assert len(matching_issues) == 1
    assert matching_issues[0]["severity"] == "error"


def test_ambiguous_route_registers_only_exact_connection_aliases(tmp_path, monkeypatch) -> None:
    with _isolated_service(tmp_path, monkeypatch, _DUPLICATE_CONNECTIONS):
        config = Config.get_instance()

    runtime_names = [
        str(entry.get("model_name") or "")
        for entry in config.llm_model_list
    ]
    assert "openai/gpt-4o" not in runtime_names
    assert runtime_names == [
        encode_model_ref("openai_personal", "openai/gpt-4o"),
        encode_model_ref("openai_work", "openai/gpt-4o"),
    ]
    assert config.litellm_model == ""


def test_explicit_ambiguous_legacy_agent_route_is_unavailable(tmp_path, monkeypatch) -> None:
    content = (
        _DUPLICATE_CONNECTIONS
        + "LITELLM_MODEL=openai/gpt-4o\n"
        + "AGENT_LITELLM_MODEL=openai/gpt-4o\n"
        + "AGENT_MODE=true\n"
    )
    with _isolated_service(tmp_path, monkeypatch, content):
        config = Config.get_instance()

    assert config.is_agent_available() is False


@pytest.mark.parametrize(
    "selected_model",
    [
        encode_model_ref("deleted_connection", "openai/gpt-4o"),
        "modelref:v1:missing-route-separator",
    ],
)
def test_unknown_or_malformed_model_ref_is_not_agent_available(
    tmp_path,
    monkeypatch,
    selected_model: str,
) -> None:
    with _isolated_service(tmp_path, monkeypatch, _DUPLICATE_CONNECTIONS):
        config = Config.get_instance()
        config.agent_litellm_model = selected_model
        config.litellm_model = selected_model
        config.agent_mode = True
        config._agent_mode_explicit = True

        assert config.is_agent_available() is False


@pytest.mark.parametrize(
    "reserved_ref",
    [
        "modelref:v2:openai_work:openai%2Fgpt-4o",
        "modelref:",
        "modelref:not-a-version",
    ],
)
def test_reserved_model_ref_namespace_is_not_agent_available(
    tmp_path,
    monkeypatch,
    reserved_ref: str,
) -> None:
    with _isolated_service(tmp_path, monkeypatch, _DUPLICATE_CONNECTIONS):
        config = Config.get_instance()
        config.agent_litellm_model = reserved_ref
        config.litellm_model = reserved_ref
        config.agent_mode = True
        config._agent_mode_explicit = True

        assert config.is_agent_available() is False


def test_connection_display_name_does_not_change_model_ref(tmp_path, monkeypatch) -> None:
    content = _DUPLICATE_CONNECTIONS.replace(
        "LLM_CHANNELS=openai_personal,openai_work",
        "LLM_CHANNELS=openai_work",
    ) + "LLM_OPENAI_WORK_DISPLAY_NAME=Trading desk\n"
    with _isolated_service(tmp_path, monkeypatch, content) as (service, _):
        models = service.get_available_models()["models"]

    assert len(models) == 1
    assert models[0]["connection_id"] == "openai_work"
    assert models[0]["connection_name"] == "Trading desk"
    assert models[0]["model_ref"] == encode_model_ref("openai_work", "openai/gpt-4o")


def test_uppercase_connection_id_matches_runtime_model_ref(tmp_path, monkeypatch) -> None:
    content = _DUPLICATE_CONNECTIONS.replace(
        "LLM_CHANNELS=openai_personal,openai_work",
        "LLM_CHANNELS=OPENAI_WORK",
    ) + "LLM_OPENAI_WORK_DISPLAY_NAME=Uppercase work\n"
    with _isolated_service(tmp_path, monkeypatch, content) as (service, _):
        models = service.get_available_models()["models"]
        config = Config.get_instance()

    assert len(models) == 1
    model = models[0]
    assert model["connection"] == "openai_work"
    assert model["connection_id"] == "openai_work"
    assert model["connection_name"] == "Uppercase work"
    assert model["model_ref"] == encode_model_ref("openai_work", "openai/gpt-4o")

    runtime_entry = next(
        entry
        for entry in config.llm_model_list
        if entry.get("model_name") == model["model_ref"]
    )
    assert runtime_entry["model_info"]["dsa_connection_id"] == "openai_work"
    assert runtime_entry["litellm_params"] == {
        "model": "openai/gpt-4o",
        "api_key": "sk-work",
        "api_base": "https://work.example/v1",
    }


def test_legacy_uppercase_model_ref_is_normalized_at_runtime(tmp_path, monkeypatch) -> None:
    legacy_ref = "modelref:v1:OPENAI_WORK:openai%2Fgpt-4o"
    canonical_ref = encode_model_ref("openai_work", "openai/gpt-4o")
    content = _DUPLICATE_CONNECTIONS.replace(
        "LLM_CHANNELS=openai_personal,openai_work",
        "LLM_CHANNELS=OPENAI_WORK",
    ) + f"LITELLM_MODEL={legacy_ref}\n"

    with _isolated_service(tmp_path, monkeypatch, content) as (service, _):
        config = Config.get_instance()
        validation = service.validate([])

    assert config.litellm_model == canonical_ref
    assert any(
        entry.get("model_name") == config.litellm_model
        for entry in config.llm_model_list
    )
    assert not [
        issue
        for issue in validation["issues"]
        if issue["key"] == "LITELLM_MODEL" and issue["severity"] == "error"
    ]


def test_malformed_model_ref_is_a_validation_issue(tmp_path, monkeypatch) -> None:
    content = _DUPLICATE_CONNECTIONS.replace(
        "LLM_CHANNELS=openai_personal,openai_work",
        "LLM_CHANNELS=openai_work",
    )
    with _isolated_service(tmp_path, monkeypatch, content) as (service, _):
        result = service.validate([
            {"key": "LITELLM_MODEL", "value": "modelref:v1:missing-route"},
        ])

    assert not result["valid"]
    assert any(issue["code"] == "invalid_model_ref" for issue in result["issues"])


def test_removing_duplicate_route_connection_rejects_exact_model_ref(tmp_path, monkeypatch) -> None:
    selected_ref = encode_model_ref("openai_work", "openai/gpt-4o")
    with _isolated_service(
        tmp_path,
        monkeypatch,
        _DUPLICATE_CONNECTIONS + f"LITELLM_MODEL={selected_ref}\n",
    ) as (service, _):
        result = service.validate([
            {"key": "LLM_CHANNELS", "value": "openai_personal"},
        ])

    issue = next(issue for issue in result["issues"] if issue["code"] == "model_in_use")
    assert not result["valid"]
    assert issue["details"]["model_ref"] == selected_ref
    assert issue["details"]["connection_ids"] == ["openai_work"]


def test_removing_duplicate_route_requires_legacy_reference_confirmation(tmp_path, monkeypatch) -> None:
    with _isolated_service(
        tmp_path,
        monkeypatch,
        _DUPLICATE_CONNECTIONS + "LITELLM_MODEL=openai/gpt-4o\n",
    ) as (service, _):
        result = service.validate([
            {"key": "LLM_CHANNELS", "value": "openai_personal"},
        ])

    issue = next(issue for issue in result["issues"] if issue["code"] == "ambiguous_model_route")
    assert not result["valid"]
    assert issue["key"] == "LITELLM_MODEL"


def test_model_ref_aliases_do_not_become_implicit_fallbacks(tmp_path, monkeypatch) -> None:
    content = (
        _DUPLICATE_CONNECTIONS.replace(
            "LLM_CHANNELS=openai_personal,openai_work",
            "LLM_CHANNELS=openai_work",
        ).replace(
            "LLM_OPENAI_WORK_MODELS=gpt-4o",
            "LLM_OPENAI_WORK_MODELS=gpt-4o,gpt-4o-mini",
        )
    )
    with _isolated_service(tmp_path, monkeypatch, content):
        config = Config.get_instance()
        assert config.litellm_model == "openai/gpt-4o"
        assert config.litellm_fallback_models == ["openai/gpt-4o-mini"]
