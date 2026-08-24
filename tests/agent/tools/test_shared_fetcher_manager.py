"""Identity contract for the process-shared DataFetcherManager (#1292 slice 4)."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import src.agent.runtime_assembly as runtime_assembly
import src.agent.tools.data_tools as data_tools
import src.agent.tools.market_tools as market_tools
import src.application_services as application_services_mod
import src.auth as auth_mod
from src.application_services import (
    ApplicationServices,
    get_installed_application_services,
    reset_application_services,
    resolve_process_data_fetcher_manager,
    set_application_services,
)
from src.auth import is_auth_enabled
from src.config import Config
from src.core.pipeline import StockAnalysisPipeline

_LEAKED_RUNTIME_SOURCE = "sk-leaked-runtime-source"
_ENV_RESTORE_SKIP = frozenset({"PYTEST_CURRENT_TEST"})


def _snapshot_governed_state() -> dict[str, Any]:
    """Capture every process singleton this file may mutate."""

    return {
        "environ": {
            key: value
            for key, value in os.environ.items()
            if key not in _ENV_RESTORE_SKIP
        },
        "config": Config._instance,
        "auth_enabled": auth_mod._auth_enabled,
        "session_secret": auth_mod._session_secret,
        "password_hash_salt": auth_mod._password_hash_salt,
        "password_hash_stored": auth_mod._password_hash_stored,
        "root": get_installed_application_services(),
        "fetcher": data_tools.active_fetcher_manager(),
        "tool_registry": runtime_assembly._TOOL_REGISTRY,
        "tool_registry_building": runtime_assembly._TOOL_REGISTRY_BUILDING,
    }


def _restore_environ(before: dict[str, str]) -> None:
    """Put process env back without clearing unrelated keys first."""

    current_test = os.environ.get("PYTEST_CURRENT_TEST")
    for key in list(os.environ):
        if key in _ENV_RESTORE_SKIP:
            continue
        if key not in before:
            os.environ.pop(key, None)
    for key, value in before.items():
        os.environ[key] = value
    if current_test is not None:
        os.environ["PYTEST_CURRENT_TEST"] = current_test


def _detach_installed_root_without_closing() -> None:
    """Hide the incoming composition root without shutting it down.

    Production ``set_application_services`` closes the previous root. Identity
    tests must install their own root, so the incoming pointer is stashed and
    restored instead of calling production reset on it.
    """

    with application_services_mod._services_lock:
        application_services_mod._services = None
        application_services_mod._services_transition_active = False
        application_services_mod._services_transition_target = None
        application_services_mod._services_transition_pending.clear()


def _restore_governed_state(snapshot: dict[str, Any]) -> None:
    """Reinstall the exact process state this file found."""

    current_root = get_installed_application_services()
    incoming_root = snapshot["root"]
    if current_root is not incoming_root:
        if current_root is not None:
            reset_application_services()
        with application_services_mod._services_lock:
            application_services_mod._services = incoming_root
            application_services_mod._services_transition_active = False
            application_services_mod._services_transition_target = None
            application_services_mod._services_transition_pending.clear()

    data_tools._fetcher_manager_singleton = snapshot["fetcher"]
    runtime_assembly._TOOL_REGISTRY = snapshot["tool_registry"]
    runtime_assembly._TOOL_REGISTRY_BUILDING = snapshot["tool_registry_building"]
    Config._instance = snapshot["config"]
    auth_mod._auth_enabled = snapshot["auth_enabled"]
    auth_mod._session_secret = snapshot["session_secret"]
    auth_mod._password_hash_salt = snapshot["password_hash_salt"]
    auth_mod._password_hash_stored = snapshot["password_hash_stored"]
    _restore_environ(snapshot["environ"])


def _assert_governed_state_matches(snapshot: dict[str, Any]) -> None:
    current = _snapshot_governed_state()
    assert current["config"] is snapshot["config"]
    assert current["auth_enabled"] is snapshot["auth_enabled"]
    assert current["session_secret"] is snapshot["session_secret"]
    assert current["root"] is snapshot["root"]
    assert current["fetcher"] is snapshot["fetcher"]
    assert current["tool_registry"] is snapshot["tool_registry"]
    assert current["tool_registry_building"] is snapshot["tool_registry_building"]
    for key in (
        "DATABASE_PATH",
        "ENV_FILE",
        "STOCK_LIST",
        "OPENAI_API_KEY",
        "ADMIN_AUTH_ENABLED",
    ):
        assert current["environ"].get(key) == snapshot["environ"].get(key)


@pytest.fixture(autouse=True)
def _isolate_manager_identity():
    """Leave Config, auth, env, root, fetcher, and tool-registry as found.

    Do not call ``refresh_auth_state()`` (that turns a cached False into None
    and later re-reads ``ENV_FILE``). Do not ``os.environ.clear()``. Do not
    close the incoming composition root: stash its pointer, then restore it.
    """

    snapshot = _snapshot_governed_state()
    _detach_installed_root_without_closing()
    data_tools.reset_fetcher_manager()
    try:
        yield
    finally:
        _restore_governed_state(snapshot)


def _root_config() -> SimpleNamespace:
    """Injected config so identity tests never call get_config()/load_dotenv()."""

    return SimpleNamespace(
        agent_skill_dir=None,
        agent_skills=None,
        agent_skill_routing="auto",
        kronos_enabled=False,
        ocr_agent_tool_enabled=False,
        plugin_data_provider_auto_bind_enabled=False,
    )


def _install_identity_services(*, data_fetcher_manager: Any = None) -> ApplicationServices:
    """Install a root that shares manager identity without loading production Config."""

    kwargs: dict[str, Any] = {
        "config": _root_config(),
        "builtin_plugins": (),
        "plugins_dir": "",
    }
    if data_fetcher_manager is not None:
        kwargs["data_fetcher_manager"] = data_fetcher_manager
    services = ApplicationServices(**kwargs)
    set_application_services(services)
    return services


def _pipeline_config() -> SimpleNamespace:
    return SimpleNamespace(
        max_workers=2,
        save_context_snapshot=False,
        bocha_api_keys=[],
        tavily_api_keys=[],
        anspire_api_keys=[],
        brave_api_keys=[],
        serpapi_keys=[],
        minimax_api_keys=[],
        searxng_base_urls=[],
        searxng_public_instances_enabled=False,
        news_max_age_days=7,
        news_strategy_profile="short",
        enable_realtime_quote=False,
        realtime_source_priority=[],
        enable_chip_distribution=False,
        social_sentiment_api_key="",
        social_sentiment_api_url="https://example.invalid/social",
        daily_market_context_enabled=False,
    )


def _build_pipeline(*, data_fetcher_manager=None) -> StockAnalysisPipeline:
    search_service = MagicMock()
    search_service.is_available = False
    social_service = MagicMock()
    social_service.is_available = False
    kwargs = {}
    if data_fetcher_manager is not None:
        kwargs["data_fetcher_manager"] = data_fetcher_manager
    with patch("src.core.pipeline.get_db", return_value=MagicMock()), \
         patch("src.core.pipeline.StockTrendAnalyzer", return_value=MagicMock()), \
         patch("src.core.pipeline.GeminiAnalyzer", return_value=MagicMock()), \
         patch("src.core.pipeline.NotificationService", return_value=MagicMock()), \
         patch("src.core.pipeline.SearchService", return_value=search_service), \
         patch("src.core.pipeline.SocialSentimentService", return_value=social_service):
        return StockAnalysisPipeline(config=_pipeline_config(), **kwargs)


def test_root_owned_manager_is_shared_with_pipeline_and_agent_tools() -> None:
    owned = MagicMock(name="root_manager")
    services = _install_identity_services(data_fetcher_manager=owned)

    pipeline = _build_pipeline()

    assert services.data_fetcher_manager is owned
    assert pipeline.fetcher_manager is owned
    assert data_tools._get_fetcher_manager() is owned
    assert market_tools._get_fetcher_manager() is owned
    assert resolve_process_data_fetcher_manager() is owned


def test_auto_bind_off_shares_the_fallback_singleton() -> None:
    fallback = MagicMock(name="fallback_manager")
    services = _install_identity_services()
    assert services.data_fetcher_manager is None

    with patch("src.data_provider.DataFetcherManager", return_value=fallback) as ctor:
        pipeline = _build_pipeline()
        from_data_tools = data_tools._get_fetcher_manager()
        from_market_tools = market_tools._get_fetcher_manager()

    assert ctor.call_count == 1
    assert pipeline.fetcher_manager is fallback
    assert from_data_tools is fallback
    assert from_market_tools is fallback
    assert data_tools.active_fetcher_manager() is fallback
    assert services.data_fetcher_manager is None


def test_no_root_constructs_fallback_singleton_on_first_resolve() -> None:
    fallback = MagicMock(name="fallback_manager")
    assert get_installed_application_services() is None
    assert data_tools.active_fetcher_manager() is None

    with patch("src.data_provider.DataFetcherManager", return_value=fallback):
        manager = data_tools._get_fetcher_manager()

    assert manager is fallback
    assert data_tools.active_fetcher_manager() is fallback
    assert market_tools._get_fetcher_manager() is fallback
    assert get_installed_application_services() is None


def test_market_tools_returns_the_same_instance_twice() -> None:
    fallback = MagicMock(name="fallback_manager")
    with patch("src.data_provider.DataFetcherManager", return_value=fallback) as ctor:
        first = market_tools._get_fetcher_manager()
        second = market_tools._get_fetcher_manager()

    assert ctor.call_count == 1
    assert first is second
    assert first is fallback


def test_reset_clears_fallback_singleton_only() -> None:
    owned = MagicMock(name="root_manager")
    fallback = MagicMock(name="fallback_manager")
    services = _install_identity_services(data_fetcher_manager=owned)

    with patch("src.data_provider.DataFetcherManager", return_value=fallback):
        constructed = data_tools._get_fallback_fetcher_manager()

    assert constructed is fallback
    assert data_tools.active_fetcher_manager() is fallback
    assert data_tools._get_fetcher_manager() is owned

    data_tools.reset_fetcher_manager()

    assert data_tools.active_fetcher_manager() is None
    assert services.data_fetcher_manager is owned
    assert data_tools._get_fetcher_manager() is owned


def test_reset_with_no_root_stays_none_until_reconstruct() -> None:
    first = MagicMock(name="first_fallback")
    second = MagicMock(name="second_fallback")
    with patch("src.data_provider.DataFetcherManager", return_value=first):
        data_tools._get_fetcher_manager()
    assert data_tools.active_fetcher_manager() is first

    data_tools.reset_fetcher_manager()
    assert data_tools.active_fetcher_manager() is None

    with patch("src.data_provider.DataFetcherManager", return_value=second):
        reconstructed = data_tools._get_fetcher_manager()

    assert reconstructed is second
    assert data_tools.active_fetcher_manager() is second


def test_explicit_pipeline_injection_still_wins() -> None:
    owned = MagicMock(name="root_manager")
    injected = MagicMock(name="injected_manager")
    _install_identity_services(data_fetcher_manager=owned)

    pipeline = _build_pipeline(data_fetcher_manager=injected)

    assert pipeline.fetcher_manager is injected
    assert data_tools._get_fetcher_manager() is owned


def test_patching_data_tools_get_fetcher_manager_still_isolates_tool_calls() -> None:
    patched = MagicMock(name="patched_manager")
    with patch(
        "src.agent.tools.data_tools._get_fetcher_manager",
        return_value=patched,
    ):
        assert data_tools._get_fetcher_manager() is patched
        assert market_tools._get_fetcher_manager() is patched
        assert data_tools.active_fetcher_manager() is None


def test_hosted_import_order_default_root_does_not_mutate_governed_state(
    tmp_path: Path,
) -> None:
    """PR #1495 hosted selective-suite counterexample (run 32753352534).

    Hosted CI already has nonempty ``DATABASE_PATH`` / ``ENV_FILE`` /
    ``STOCK_LIST`` from collection of ``tests/analysis_api_contract_support.py``,
    and ``Config`` may already exist so ``get_config()`` does not reload
    dotenv. A default-root install therefore does **not** bake
    ``OPENAI_API_KEY``. Isolation must still leave every governed singleton
    and env key exactly as this test found them.
    """

    from src.api.v1.services.system_config_write_audit import (
        system_config_write_audit_actor_id,
    )

    collection_env = tmp_path / "collection.env"
    collection_env.write_text("STOCK_LIST=600519,000001\n", encoding="utf-8")
    leaky_env = tmp_path / "leaky.env"
    leaky_env.write_text(
        "ADMIN_AUTH_ENABLED=true\n"
        f"OPENAI_API_KEY={_LEAKED_RUNTIME_SOURCE}\n",
        encoding="utf-8",
    )

    os.environ["ENV_FILE"] = str(collection_env)
    os.environ.setdefault("STOCK_LIST", "600519,000001")
    if Config._instance is None:
        Config.get_instance()
    preexisting_config = Config._instance
    assert preexisting_config is not None

    hosted = _snapshot_governed_state()
    assert hosted["environ"].get("OPENAI_API_KEY") != _LEAKED_RUNTIME_SOURCE
    database_path = os.environ.get("DATABASE_PATH")
    stock_list = os.environ.get("STOCK_LIST")

    os.environ["ENV_FILE"] = str(leaky_env)
    services = ApplicationServices(builtin_plugins=(), plugins_dir="")
    set_application_services(services)

    assert Config._instance is preexisting_config
    assert os.environ.get("OPENAI_API_KEY") == hosted["environ"].get("OPENAI_API_KEY")
    assert os.environ.get("OPENAI_API_KEY") != _LEAKED_RUNTIME_SOURCE
    assert os.environ.get("DATABASE_PATH") == database_path
    assert os.environ.get("STOCK_LIST") == stock_list

    _restore_governed_state(hosted)
    _assert_governed_state_matches(hosted)
    # Do not call is_auth_enabled() when the snapshot cache is None: that would
    # re-read ENV_FILE and warm a different cache value than this file found.
    if hosted["auth_enabled"] is False:
        assert system_config_write_audit_actor_id() == "local_operator"
    elif hosted["auth_enabled"] is True:
        assert system_config_write_audit_actor_id() == "authenticated_admin"


def test_cold_config_default_root_load_dotenv_is_restored(tmp_path: Path) -> None:
    """When Config is missing, default-root ``start_plugins`` does load_dotenv.

    That is the leak that poisons later system-config runtime-source checks,
    local-model ``audit_actor_id``, and paper API auth. Isolation must restore
    Config, auth cache, and runtime-source env to the pre-sequence snapshot.
    """

    from src.api.v1.services.system_config_write_audit import (
        system_config_write_audit_actor_id,
    )

    before = _snapshot_governed_state()
    leaky_env = tmp_path / "leaky.env"
    leaky_env.write_text(
        "ADMIN_AUTH_ENABLED=true\n"
        f"OPENAI_API_KEY={_LEAKED_RUNTIME_SOURCE}\n",
        encoding="utf-8",
    )
    Config._instance = None
    auth_mod._auth_enabled = None
    os.environ["ENV_FILE"] = str(leaky_env)
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("ADMIN_AUTH_ENABLED", None)

    try:
        services = ApplicationServices(builtin_plugins=(), plugins_dir="")
        set_application_services(services)
        assert Config._instance is not None
        assert os.environ.get("OPENAI_API_KEY") == _LEAKED_RUNTIME_SOURCE
        assert is_auth_enabled() is True
        assert system_config_write_audit_actor_id() == "authenticated_admin"
    finally:
        _restore_governed_state(before)

    _assert_governed_state_matches(before)
    assert os.environ.get("OPENAI_API_KEY") == before["environ"].get("OPENAI_API_KEY")
    assert os.environ.get("ADMIN_AUTH_ENABLED") == before["environ"].get(
        "ADMIN_AUTH_ENABLED"
    )
    assert os.environ.get("ENV_FILE") == before["environ"].get("ENV_FILE")
    assert os.environ.get("DATABASE_PATH") == before["environ"].get("DATABASE_PATH")
    assert Config._instance is before["config"]
    assert auth_mod._auth_enabled is before["auth_enabled"]
