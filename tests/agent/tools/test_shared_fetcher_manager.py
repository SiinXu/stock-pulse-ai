"""Identity contract for the process-shared DataFetcherManager (#1292 slice 4)."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import src.agent.tools.data_tools as data_tools
import src.agent.tools.market_tools as market_tools
from src.application_services import (
    ApplicationServices,
    get_installed_application_services,
    reset_application_services,
    resolve_process_data_fetcher_manager,
    set_application_services,
)
from src.auth import is_auth_enabled, refresh_auth_state
from src.config import Config
from src.core.pipeline import StockAnalysisPipeline


def _reset_identity_root_and_auth() -> None:
    """Clear the composition root and auth cache this file may install.

    Tests only. Do not reset the process ToolRegistry here: the next
    ``get_tool_registry()`` would call ``get_application_services()`` and
    lazily install a default root, which is the Config/auth leak path.
    """

    data_tools.reset_fetcher_manager()
    reset_application_services()
    refresh_auth_state()


@pytest.fixture(autouse=True)
def _isolate_manager_identity():
    original = data_tools.active_fetcher_manager()
    _reset_identity_root_and_auth()
    yield
    _reset_identity_root_and_auth()
    if original is not None:
        data_tools._fetcher_manager_singleton = original


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


def test_default_root_install_does_not_leave_config_auth_or_runtime_sources(
    tmp_path: Path,
) -> None:
    """PR #1495 hosted selective-suite counterexample.

    Predecessor API tests can leave ``ENV_FILE`` pointing at a temp env with
    ``ADMIN_AUTH_ENABLED=true`` and a legacy ``OPENAI_API_KEY``. Installing a
    default ``ApplicationServices`` starts plugins via ``get_config()``, which
    ``load_dotenv``-bakes those values into ``os.environ`` and caches
    ``is_auth_enabled()``. Later system-config validation then treats the leaked
    key as a runtime source, local-model audit actors become
    ``authenticated_admin``, and paper API returns 401.

    Isolation must restore Config, auth, and env so those contracts stay
    deterministic. This test runs the contaminating sequence, then the same
    reset used by this file's autouse fixture.
    """

    from src.api.v1.services.system_config_write_audit import (
        system_config_write_audit_actor_id,
    )

    original_env = os.environ.copy()
    previous_config = Config._instance
    env_path = tmp_path / ".env"
    env_path.write_text(
        "ADMIN_AUTH_ENABLED=true\nOPENAI_API_KEY=sk-leaked-runtime-source\n",
        encoding="utf-8",
    )
    os.environ["ENV_FILE"] = str(env_path)
    refresh_auth_state()
    try:
        # Same leak as the original identity tests: no injected config, so
        # start_plugins() calls get_config() → load_dotenv. Empty builtins keep
        # the counterexample on Config/auth/env rather than plugin catalog load.
        services = ApplicationServices(builtin_plugins=(), plugins_dir="")
        set_application_services(services)
        assert Config._instance is not None
        assert os.environ.get("OPENAI_API_KEY") == "sk-leaked-runtime-source"
        assert is_auth_enabled() is True
        assert system_config_write_audit_actor_id() == "authenticated_admin"
    finally:
        _reset_identity_root_and_auth()
        os.environ.clear()
        os.environ.update(original_env)
        Config._instance = previous_config
        refresh_auth_state()

    assert get_installed_application_services() is None
    assert Config._instance is None
    assert os.environ.get("OPENAI_API_KEY") is None
    assert os.environ.get("ADMIN_AUTH_ENABLED") is None
    assert os.environ.get("ENV_FILE") == original_env.get("ENV_FILE")
    assert is_auth_enabled() is False
    assert system_config_write_audit_actor_id() == "local_operator"
