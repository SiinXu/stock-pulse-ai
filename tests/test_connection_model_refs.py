# -*- coding: utf-8 -*-
"""Connection-aware model catalog contract tests."""

from __future__ import annotations

import os

from src.config import Config
from src.core.config_manager import ConfigManager
from src.llm.model_ref import encode_model_ref
from src.services.system_config_service import ConfigValidationError, SystemConfigService
from tests._llm_env_isolation import restore_ambient_llm_env, strip_ambient_llm_env


def test_available_models_keeps_same_route_for_each_connection(tmp_path, monkeypatch) -> None:
    saved_llm_env = strip_ambient_llm_env()
    original_env_file = os.environ.get("ENV_FILE")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "LLM_CONFIG_MODE=channels",
                "LLM_CHANNELS=openai_personal,openai_work",
                "LLM_OPENAI_PERSONAL_PROVIDER=openai",
                "LLM_OPENAI_PERSONAL_PROTOCOL=openai",
                "LLM_OPENAI_PERSONAL_API_KEY=sk-personal",
                "LLM_OPENAI_PERSONAL_MODELS=gpt-4o",
                "LLM_OPENAI_PERSONAL_ENABLED=true",
                "LLM_OPENAI_WORK_PROVIDER=openai",
                "LLM_OPENAI_WORK_PROTOCOL=openai",
                "LLM_OPENAI_WORK_API_KEY=sk-work",
                "LLM_OPENAI_WORK_MODELS=gpt-4o",
                "LLM_OPENAI_WORK_ENABLED=true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        monkeypatch.setenv("ENV_FILE", str(env_path))
        Config.reset_instance()
        service = SystemConfigService(manager=ConfigManager(env_path=env_path))

        models = service.get_available_models()["models"]

        assert [(model["connection_id"], model["route"]) for model in models] == [
            ("openai_personal", "openai/gpt-4o"),
            ("openai_work", "openai/gpt-4o"),
        ]
        assert len({model["model_ref"] for model in models}) == 2
    finally:
        Config.reset_instance()
        if original_env_file is None:
            os.environ.pop("ENV_FILE", None)
        else:
            os.environ["ENV_FILE"] = original_env_file
        restore_ambient_llm_env(saved_llm_env)


def test_selected_model_ref_routes_to_exact_connection(tmp_path, monkeypatch) -> None:
    saved_llm_env = strip_ambient_llm_env()
    original_env_file = os.environ.get("ENV_FILE")
    selected_ref = encode_model_ref("openai_work", "openai/gpt-4o")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "LLM_CONFIG_MODE=channels",
                "LLM_CHANNELS=openai_personal,openai_work",
                "LLM_OPENAI_PERSONAL_PROVIDER=openai",
                "LLM_OPENAI_PERSONAL_PROTOCOL=openai",
                "LLM_OPENAI_PERSONAL_BASE_URL=https://personal.example/v1",
                "LLM_OPENAI_PERSONAL_API_KEY=sk-personal",
                "LLM_OPENAI_PERSONAL_MODELS=gpt-4o",
                "LLM_OPENAI_PERSONAL_ENABLED=true",
                "LLM_OPENAI_WORK_PROVIDER=openai",
                "LLM_OPENAI_WORK_PROTOCOL=openai",
                "LLM_OPENAI_WORK_BASE_URL=https://work.example/v1",
                "LLM_OPENAI_WORK_API_KEY=sk-work",
                "LLM_OPENAI_WORK_MODELS=gpt-4o",
                "LLM_OPENAI_WORK_ENABLED=true",
                f"LITELLM_MODEL={selected_ref}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        monkeypatch.setenv("ENV_FILE", str(env_path))
        Config.reset_instance()
        config = Config.get_instance()

        selected_entries = [
            entry
            for entry in config.llm_model_list
            if entry.get("model_name") == selected_ref
        ]

        assert len(selected_entries) == 1
        assert selected_entries[0]["litellm_params"] == {
            "model": "openai/gpt-4o",
            "api_key": "sk-work",
            "api_base": "https://work.example/v1",
        }
        assert config.litellm_model == selected_ref
    finally:
        Config.reset_instance()
        if original_env_file is None:
            os.environ.pop("ENV_FILE", None)
        else:
            os.environ["ENV_FILE"] = original_env_file
        restore_ambient_llm_env(saved_llm_env)


def test_system_config_accepts_connection_aware_task_assignment(tmp_path, monkeypatch) -> None:
    saved_llm_env = strip_ambient_llm_env()
    original_env_file = os.environ.get("ENV_FILE")
    selected_ref = encode_model_ref("openai_work", "openai/gpt-4o")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "LLM_CONFIG_MODE=channels",
                "LLM_CHANNELS=openai_personal,openai_work",
                "LLM_OPENAI_PERSONAL_PROVIDER=openai",
                "LLM_OPENAI_PERSONAL_PROTOCOL=openai",
                "LLM_OPENAI_PERSONAL_API_KEY=sk-personal",
                "LLM_OPENAI_PERSONAL_MODELS=gpt-4o",
                "LLM_OPENAI_PERSONAL_ENABLED=true",
                "LLM_OPENAI_WORK_PROVIDER=openai",
                "LLM_OPENAI_WORK_PROTOCOL=openai",
                "LLM_OPENAI_WORK_API_KEY=sk-work",
                "LLM_OPENAI_WORK_MODELS=gpt-4o",
                "LLM_OPENAI_WORK_ENABLED=true",
                "LITELLM_MODEL=openai/gpt-4o",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        monkeypatch.setenv("ENV_FILE", str(env_path))
        Config.reset_instance()
        service = SystemConfigService(manager=ConfigManager(env_path=env_path))

        result = service.validate([
            {"key": "LITELLM_MODEL", "value": selected_ref},
        ])

        assert result["valid"], result["issues"]
    finally:
        Config.reset_instance()
        if original_env_file is None:
            os.environ.pop("ENV_FILE", None)
        else:
            os.environ["ENV_FILE"] = original_env_file
        restore_ambient_llm_env(saved_llm_env)


def test_ambiguous_legacy_route_requires_connection_confirmation(tmp_path, monkeypatch) -> None:
    saved_llm_env = strip_ambient_llm_env()
    original_env_file = os.environ.get("ENV_FILE")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "LLM_CONFIG_MODE=channels",
                "LLM_CHANNELS=openai_personal,openai_work",
                "LLM_OPENAI_PERSONAL_PROVIDER=openai",
                "LLM_OPENAI_PERSONAL_PROTOCOL=openai",
                "LLM_OPENAI_PERSONAL_API_KEY=sk-personal",
                "LLM_OPENAI_PERSONAL_MODELS=gpt-4o",
                "LLM_OPENAI_PERSONAL_ENABLED=true",
                "LLM_OPENAI_WORK_PROVIDER=openai",
                "LLM_OPENAI_WORK_PROTOCOL=openai",
                "LLM_OPENAI_WORK_API_KEY=sk-work",
                "LLM_OPENAI_WORK_MODELS=gpt-4o",
                "LLM_OPENAI_WORK_ENABLED=true",
                "LITELLM_MODEL=openai/gpt-4o",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        monkeypatch.setenv("ENV_FILE", str(env_path))
        Config.reset_instance()
        service = SystemConfigService(manager=ConfigManager(env_path=env_path))

        result = service.validate([
            {"key": "LITELLM_MODEL", "value": "openai/gpt-4o"},
        ])

        assert not result["valid"]
        issue = next(issue for issue in result["issues"] if issue["code"] == "ambiguous_model_route")
        assert issue["key"] == "LITELLM_MODEL"
        assert issue["details"]["connection_ids"] == ["openai_personal", "openai_work"]
        assert len(issue["details"]["model_refs"]) == 2
    finally:
        Config.reset_instance()
        if original_env_file is None:
            os.environ.pop("ENV_FILE", None)
        else:
            os.environ["ENV_FILE"] = original_env_file
        restore_ambient_llm_env(saved_llm_env)


def test_connection_display_name_changes_without_changing_model_ref(tmp_path, monkeypatch) -> None:
    saved_llm_env = strip_ambient_llm_env()
    original_env_file = os.environ.get("ENV_FILE")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "LLM_CONFIG_MODE=channels",
                "LLM_CHANNELS=openai_work",
                "LLM_OPENAI_WORK_PROVIDER=openai",
                "LLM_OPENAI_WORK_PROTOCOL=openai",
                "LLM_OPENAI_WORK_API_KEY=sk-work",
                "LLM_OPENAI_WORK_MODELS=gpt-4o",
                "LLM_OPENAI_WORK_ENABLED=true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        monkeypatch.setenv("ENV_FILE", str(env_path))
        Config.reset_instance()
        manager = ConfigManager(env_path=env_path)
        service = SystemConfigService(manager=manager)

        result = service.update(
            config_version=manager.get_config_version(),
            items=[
                {"key": "LLM_OPENAI_WORK_DISPLAY_NAME", "value": "Trading desk"},
            ],
            reload_now=False,
        )
        models = service.get_available_models()["models"]

        assert result["success"]
        assert manager.read_config_map()["LLM_OPENAI_WORK_DISPLAY_NAME"] == "Trading desk"
        assert models[0]["connection_id"] == "openai_work"
        assert models[0]["connection_name"] == "Trading desk"
        assert models[0]["model_ref"] == encode_model_ref("openai_work", "openai/gpt-4o")
    finally:
        Config.reset_instance()
        if original_env_file is None:
            os.environ.pop("ENV_FILE", None)
        else:
            os.environ["ENV_FILE"] = original_env_file
        restore_ambient_llm_env(saved_llm_env)


def test_malformed_model_ref_is_a_validation_issue_not_an_exception(tmp_path, monkeypatch) -> None:
    saved_llm_env = strip_ambient_llm_env()
    original_env_file = os.environ.get("ENV_FILE")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "LLM_CONFIG_MODE=channels",
                "LLM_CHANNELS=openai_work",
                "LLM_OPENAI_WORK_PROVIDER=openai",
                "LLM_OPENAI_WORK_PROTOCOL=openai",
                "LLM_OPENAI_WORK_API_KEY=sk-work",
                "LLM_OPENAI_WORK_MODELS=gpt-4o",
                "LLM_OPENAI_WORK_ENABLED=true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        monkeypatch.setenv("ENV_FILE", str(env_path))
        Config.reset_instance()
        service = SystemConfigService(manager=ConfigManager(env_path=env_path))

        result = service.validate([
            {"key": "LITELLM_MODEL", "value": "modelref:v1:missing-route"},
        ])

        assert not result["valid"]
        issue = next(issue for issue in result["issues"] if issue["code"] == "invalid_model_ref")
        assert issue["key"] == "LITELLM_MODEL"
    finally:
        Config.reset_instance()
        if original_env_file is None:
            os.environ.pop("ENV_FILE", None)
        else:
            os.environ["ENV_FILE"] = original_env_file
        restore_ambient_llm_env(saved_llm_env)


def test_valid_model_ref_to_missing_connection_is_rejected_for_every_task_route() -> None:
    missing_ref = encode_model_ref("missing_connection", "minimax/MiniMax-M2.1")

    bases = (
        {},
        {
            "LLM_CONFIG_MODE": "channels",
            "LLM_CHANNELS": "openai_work",
            "LLM_OPENAI_WORK_PROVIDER": "openai",
            "LLM_OPENAI_WORK_PROTOCOL": "openai",
            "LLM_OPENAI_WORK_API_KEY": "sk-work",
            "LLM_OPENAI_WORK_MODELS": "",
            "LLM_OPENAI_WORK_ENABLED": "true",
            "OPENAI_API_KEY": "sk-legacy",
        },
    )

    for base in bases:
        for key in (
            "LITELLM_MODEL",
            "AGENT_LITELLM_MODEL",
            "LITELLM_FALLBACK_MODELS",
            "VISION_MODEL",
        ):
            effective = {**base, key: missing_ref}
            issues = SystemConfigService._validate_llm_runtime_selection(
                effective,
                updated_keys={key},
            )

            assert any(
                issue["key"] == key
                and issue["code"] == "unknown_model"
                and issue["severity"] == "error"
                for issue in issues
            ), (base, key, issues)


def test_update_rejects_missing_connection_model_ref_even_with_legacy_key(
    tmp_path,
    monkeypatch,
) -> None:
    saved_llm_env = strip_ambient_llm_env()
    original_env_file = os.environ.get("ENV_FILE")
    env_path = tmp_path / ".env"
    env_path.write_text("OPENAI_API_KEY=sk-legacy\n", encoding="utf-8")
    missing_ref = encode_model_ref("missing_connection", "openai/gpt-4o")

    try:
        monkeypatch.setenv("ENV_FILE", str(env_path))
        Config.reset_instance()
        manager = ConfigManager(env_path=env_path)
        service = SystemConfigService(manager=manager)
        before = env_path.read_bytes()

        for key in (
            "LITELLM_MODEL",
            "AGENT_LITELLM_MODEL",
            "LITELLM_FALLBACK_MODELS",
            "VISION_MODEL",
        ):
            try:
                service.update(
                    config_version=manager.get_config_version(),
                    items=[{"key": key, "value": missing_ref}],
                    reload_now=False,
                )
            except ConfigValidationError as exc:
                assert any(
                    issue["key"] == key
                    and issue["code"] == "unknown_model"
                    and issue["severity"] == "error"
                    for issue in exc.issues
                ), (key, exc.issues)
            else:
                raise AssertionError(f"{key} accepted a ModelRef for a missing Connection")

            assert env_path.read_bytes() == before
    finally:
        Config.reset_instance()
        if original_env_file is None:
            os.environ.pop("ENV_FILE", None)
        else:
            os.environ["ENV_FILE"] = original_env_file
        restore_ambient_llm_env(saved_llm_env)


def test_removing_one_duplicate_route_connection_rejects_its_exact_model_ref(
    tmp_path,
    monkeypatch,
) -> None:
    saved_llm_env = strip_ambient_llm_env()
    original_env_file = os.environ.get("ENV_FILE")
    selected_ref = encode_model_ref("openai_work", "openai/gpt-4o")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "LLM_CONFIG_MODE=channels",
                "LLM_CHANNELS=openai_personal,openai_work",
                "LLM_OPENAI_PERSONAL_PROVIDER=openai",
                "LLM_OPENAI_PERSONAL_PROTOCOL=openai",
                "LLM_OPENAI_PERSONAL_API_KEY=sk-personal",
                "LLM_OPENAI_PERSONAL_MODELS=gpt-4o",
                "LLM_OPENAI_PERSONAL_ENABLED=true",
                "LLM_OPENAI_WORK_PROVIDER=openai",
                "LLM_OPENAI_WORK_PROTOCOL=openai",
                "LLM_OPENAI_WORK_API_KEY=sk-work",
                "LLM_OPENAI_WORK_MODELS=gpt-4o",
                "LLM_OPENAI_WORK_ENABLED=true",
                f"LITELLM_MODEL={selected_ref}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        monkeypatch.setenv("ENV_FILE", str(env_path))
        Config.reset_instance()
        service = SystemConfigService(manager=ConfigManager(env_path=env_path))

        result = service.validate([
            {"key": "LLM_CHANNELS", "value": "openai_personal"},
        ])

        assert not result["valid"]
        issue = next(issue for issue in result["issues"] if issue["code"] == "model_in_use")
        assert issue["details"]["model_ref"] == selected_ref
        assert issue["details"]["connection_ids"] == ["openai_work"]
        assert issue["details"]["referenced_by"] == [
            {"task": "report", "key": "LITELLM_MODEL"},
        ]
    finally:
        Config.reset_instance()
        if original_env_file is None:
            os.environ.pop("ENV_FILE", None)
        else:
            os.environ["ENV_FILE"] = original_env_file
        restore_ambient_llm_env(saved_llm_env)


def test_removing_one_duplicate_route_requires_legacy_reference_confirmation(
    tmp_path,
    monkeypatch,
) -> None:
    saved_llm_env = strip_ambient_llm_env()
    original_env_file = os.environ.get("ENV_FILE")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "LLM_CONFIG_MODE=channels",
                "LLM_CHANNELS=openai_personal,openai_work",
                "LLM_OPENAI_PERSONAL_PROVIDER=openai",
                "LLM_OPENAI_PERSONAL_PROTOCOL=openai",
                "LLM_OPENAI_PERSONAL_API_KEY=sk-personal",
                "LLM_OPENAI_PERSONAL_MODELS=gpt-4o",
                "LLM_OPENAI_PERSONAL_ENABLED=true",
                "LLM_OPENAI_WORK_PROVIDER=openai",
                "LLM_OPENAI_WORK_PROTOCOL=openai",
                "LLM_OPENAI_WORK_API_KEY=sk-work",
                "LLM_OPENAI_WORK_MODELS=gpt-4o",
                "LLM_OPENAI_WORK_ENABLED=true",
                "LITELLM_MODEL=openai/gpt-4o",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        monkeypatch.setenv("ENV_FILE", str(env_path))
        Config.reset_instance()
        service = SystemConfigService(manager=ConfigManager(env_path=env_path))

        result = service.validate([
            {"key": "LLM_CHANNELS", "value": "openai_personal"},
        ])

        assert not result["valid"]
        issue = next(issue for issue in result["issues"] if issue["code"] == "ambiguous_model_route")
        assert issue["key"] == "LITELLM_MODEL"
        assert issue["details"]["connection_ids"] == ["openai_personal", "openai_work"]
    finally:
        Config.reset_instance()
        if original_env_file is None:
            os.environ.pop("ENV_FILE", None)
        else:
            os.environ["ENV_FILE"] = original_env_file
        restore_ambient_llm_env(saved_llm_env)


def test_removing_unreferenced_duplicate_route_connection_keeps_selected_model_ref(
    tmp_path,
    monkeypatch,
) -> None:
    saved_llm_env = strip_ambient_llm_env()
    original_env_file = os.environ.get("ENV_FILE")
    selected_ref = encode_model_ref("openai_personal", "openai/gpt-4o")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "LLM_CONFIG_MODE=channels",
                "LLM_CHANNELS=openai_personal,openai_work",
                "LLM_OPENAI_PERSONAL_PROVIDER=openai",
                "LLM_OPENAI_PERSONAL_PROTOCOL=openai",
                "LLM_OPENAI_PERSONAL_API_KEY=sk-personal",
                "LLM_OPENAI_PERSONAL_MODELS=gpt-4o",
                "LLM_OPENAI_PERSONAL_ENABLED=true",
                "LLM_OPENAI_WORK_PROVIDER=openai",
                "LLM_OPENAI_WORK_PROTOCOL=openai",
                "LLM_OPENAI_WORK_API_KEY=sk-work",
                "LLM_OPENAI_WORK_MODELS=gpt-4o",
                "LLM_OPENAI_WORK_ENABLED=true",
                f"LITELLM_MODEL={selected_ref}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        monkeypatch.setenv("ENV_FILE", str(env_path))
        Config.reset_instance()
        service = SystemConfigService(manager=ConfigManager(env_path=env_path))

        result = service.validate([
            {"key": "LLM_CHANNELS", "value": "openai_personal"},
        ])

        assert result["valid"], result["issues"]
        assert not any(issue["code"] == "model_in_use" for issue in result["issues"])
    finally:
        Config.reset_instance()
        if original_env_file is None:
            os.environ.pop("ENV_FILE", None)
        else:
            os.environ["ENV_FILE"] = original_env_file
        restore_ambient_llm_env(saved_llm_env)


def test_available_models_distinguishes_provider_identity_for_same_display_model(
    tmp_path,
    monkeypatch,
) -> None:
    saved_llm_env = strip_ambient_llm_env()
    original_env_file = os.environ.get("ENV_FILE")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "LLM_CONFIG_MODE=channels",
                "LLM_CHANNELS=openai_official,custom_gateway",
                "LLM_OPENAI_OFFICIAL_PROVIDER=openai",
                "LLM_OPENAI_OFFICIAL_PROTOCOL=openai",
                "LLM_OPENAI_OFFICIAL_API_KEY=sk-openai",
                "LLM_OPENAI_OFFICIAL_MODELS=gpt-4o",
                "LLM_OPENAI_OFFICIAL_ENABLED=true",
                "LLM_CUSTOM_GATEWAY_PROVIDER=custom",
                "LLM_CUSTOM_GATEWAY_PROTOCOL=openai",
                "LLM_CUSTOM_GATEWAY_BASE_URL=https://gateway.example/v1",
                "LLM_CUSTOM_GATEWAY_API_KEY=sk-custom",
                "LLM_CUSTOM_GATEWAY_MODELS=gpt-4o",
                "LLM_CUSTOM_GATEWAY_ENABLED=true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        monkeypatch.setenv("ENV_FILE", str(env_path))
        Config.reset_instance()
        service = SystemConfigService(manager=ConfigManager(env_path=env_path))

        models = service.get_available_models()["models"]

        assert [model["display"] for model in models] == ["gpt-4o", "gpt-4o"]
        assert [model["provider_id"] for model in models] == ["openai", "custom"]
        assert len({model["model_ref"] for model in models}) == 2
    finally:
        Config.reset_instance()
        if original_env_file is None:
            os.environ.pop("ENV_FILE", None)
        else:
            os.environ["ENV_FILE"] = original_env_file
        restore_ambient_llm_env(saved_llm_env)


def test_model_ref_aliases_do_not_become_implicit_fallbacks(tmp_path, monkeypatch) -> None:
    saved_llm_env = strip_ambient_llm_env()
    original_env_file = os.environ.get("ENV_FILE")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "LLM_CONFIG_MODE=channels",
                "LLM_CHANNELS=openai_work",
                "LLM_OPENAI_WORK_PROVIDER=openai",
                "LLM_OPENAI_WORK_PROTOCOL=openai",
                "LLM_OPENAI_WORK_API_KEY=sk-work",
                "LLM_OPENAI_WORK_MODELS=gpt-4o,gpt-4o-mini",
                "LLM_OPENAI_WORK_ENABLED=true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        monkeypatch.setenv("ENV_FILE", str(env_path))
        Config.reset_instance()
        config = Config.get_instance()

        assert config.litellm_model == "openai/gpt-4o"
        assert config.litellm_fallback_models == ["openai/gpt-4o-mini"]
    finally:
        Config.reset_instance()
        if original_env_file is None:
            os.environ.pop("ENV_FILE", None)
        else:
            os.environ["ENV_FILE"] = original_env_file
        restore_ambient_llm_env(saved_llm_env)


def test_explicit_model_ref_keeps_implicit_fallbacks_connection_aware(
    tmp_path,
    monkeypatch,
) -> None:
    saved_llm_env = strip_ambient_llm_env()
    original_env_file = os.environ.get("ENV_FILE")
    selected_ref = encode_model_ref("openai_work", "openai/gpt-4o")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "LLM_CONFIG_MODE=channels",
                "LLM_CHANNELS=openai_work,openai_personal",
                "LLM_OPENAI_WORK_PROVIDER=openai",
                "LLM_OPENAI_WORK_PROTOCOL=openai",
                "LLM_OPENAI_WORK_API_KEY=sk-work",
                "LLM_OPENAI_WORK_MODELS=gpt-4o,gpt-4o-mini",
                "LLM_OPENAI_WORK_ENABLED=true",
                "LLM_OPENAI_PERSONAL_PROVIDER=openai",
                "LLM_OPENAI_PERSONAL_PROTOCOL=openai",
                "LLM_OPENAI_PERSONAL_API_KEY=sk-personal",
                "LLM_OPENAI_PERSONAL_MODELS=gpt-4o",
                "LLM_OPENAI_PERSONAL_ENABLED=true",
                f"LITELLM_MODEL={selected_ref}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        monkeypatch.setenv("ENV_FILE", str(env_path))
        Config.reset_instance()
        config = Config.get_instance()

        assert config.litellm_fallback_models == [
            encode_model_ref("openai_work", "openai/gpt-4o-mini"),
            encode_model_ref("openai_personal", "openai/gpt-4o"),
        ]
    finally:
        Config.reset_instance()
        if original_env_file is None:
            os.environ.pop("ENV_FILE", None)
        else:
            os.environ["ENV_FILE"] = original_env_file
        restore_ambient_llm_env(saved_llm_env)


def test_exact_model_refs_keep_connection_specific_hermes_provenance(
    tmp_path,
    monkeypatch,
) -> None:
    saved_llm_env = strip_ambient_llm_env()
    original_env_file = os.environ.get("ENV_FILE")
    env_path = tmp_path / ".env"
    env_path.write_text("STOCK_LIST=600519\n", encoding="utf-8")
    shared_route = "openai/shared-route"
    remote_ref = encode_model_ref("remote", shared_route)
    hermes_ref = encode_model_ref("hermes", shared_route)
    common_items = [
        {"key": "LLM_CHANNELS", "value": "hermes,remote"},
        {"key": "LLM_HERMES_API_KEY", "value": "sk-hermes-test-value"},
        {"key": "LLM_HERMES_MODELS", "value": "shared-route"},
        {"key": "LLM_REMOTE_PROVIDER", "value": "openai"},
        {"key": "LLM_REMOTE_PROTOCOL", "value": "openai"},
        {"key": "LLM_REMOTE_BASE_URL", "value": "https://api.example.com/v1"},
        {"key": "LLM_REMOTE_API_KEY", "value": "sk-remote-test-value"},
        {"key": "LLM_REMOTE_MODELS", "value": "shared-route"},
    ]

    try:
        monkeypatch.setenv("ENV_FILE", str(env_path))
        Config.reset_instance()
        service = SystemConfigService(manager=ConfigManager(env_path=env_path))

        remote = service.validate(common_items + [
            {"key": "LITELLM_MODEL", "value": remote_ref},
            {"key": "AGENT_LITELLM_MODEL", "value": remote_ref},
            {"key": "VISION_MODEL", "value": remote_ref},
            {"key": "LITELLM_FALLBACK_MODELS", "value": remote_ref},
        ])
        hermes = service.validate(common_items + [
            {"key": "AGENT_LITELLM_MODEL", "value": hermes_ref},
            {"key": "VISION_MODEL", "value": hermes_ref},
        ])

        assert remote["valid"], remote["issues"]
        assert not hermes["valid"]
        assert {
            (issue["key"], issue["code"])
            for issue in hermes["issues"]
            if issue["severity"] == "error"
        } >= {
            ("AGENT_LITELLM_MODEL", "explicit_agent_model_no_safe_deployment"),
            ("VISION_MODEL", "hermes_vision_unsupported"),
        }
    finally:
        Config.reset_instance()
        if original_env_file is None:
            os.environ.pop("ENV_FILE", None)
        else:
            os.environ["ENV_FILE"] = original_env_file
        restore_ambient_llm_env(saved_llm_env)
