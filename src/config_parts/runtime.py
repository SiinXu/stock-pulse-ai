"""Runtime helper methods for :class:`src.config.Config`."""

import os
from pathlib import Path

from dotenv import dotenv_values

from src.config_parts.parsers import get_effective_agent_primary_model
from src.llm.backend_registry import (
    AUTO_AGENT_BACKEND_ID,
    GENERATION_ONLY_BACKEND_IDS,
)
from src.llm.hermes import route_deployment_origins
from src.services.stock_list_parser import split_stock_list


class _ConfigRuntimeMethods:
    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (mainly for testing)."""
        cls._instance = None
        cls._BOOTSTRAP_RUNTIME_ENV_OVERRIDES_CAPTURED = False
        cls._BOOTSTRAP_RUNTIME_ENV_OVERRIDES = frozenset()
        cls._BOOTSTRAP_RUNTIME_ENV_PRESENT_KEYS = frozenset()

    def has_searxng_enabled(self) -> bool:
        """Whether SearXNG fallback is enabled via self-hosted or public mode."""
        return bool(self.searxng_base_urls) or bool(self.searxng_public_instances_enabled)

    def has_search_capability_enabled(self) -> bool:
        """Whether any search provider is configured or SearXNG fallback is enabled."""
        return bool(
            self.anspire_api_keys
            or self.bocha_api_keys
            or self.minimax_api_keys
            or self.tavily_api_keys
            or self.brave_api_keys
            or self.serpapi_keys
            or self.has_searxng_enabled()
        )

    def is_agent_available(self) -> bool:
        """Check whether agent capabilities are usable.

        Decision table:

        +-----------------------+----------------------------+-----------------+
        | AGENT_MODE env        | Agent-safe route available | Result          |
        +-----------------------+----------------------------+-----------------+
        | ``false`` (explicit)  | any                        | False           |
        | ``true``              | yes                        | True            |
        | ``true``              | no                         | False           |
        | not set (default)     | yes                        | True            |
        | not set (default)     | no                         | False           |
        +-----------------------+----------------------------+-----------------+

        ``AGENT_MODE=true`` expresses user intent, but Phase 3 Hermes safety
        still requires a non-Hermes Agent route. Hermes-only deployments cannot
        satisfy Agent tool roundtrip support; mixed routes are usable only via
        their non-Hermes deployments. ``AGENT_MODE=false`` remains an explicit
        kill-switch. Explicit local CLI Agent backends are unavailable because
        they are text generation backends, not Agent tool-calling runtimes.
        """
        if (self.agent_generation_backend or AUTO_AGENT_BACKEND_ID).strip().lower() in GENERATION_ONLY_BACKEND_IDS:
            return False
        # Phase 3 no longer lets AGENT_MODE=true bypass tool-route safety.
        if self._agent_mode_explicit and not self.agent_mode:
            return False
        # Auto-detect inherits the global model when AGENT_LITELLM_MODEL is empty.
        primary_model = get_effective_agent_primary_model(self)
        if not primary_model:
            return False
        origins = route_deployment_origins(self.llm_model_list, primary_model)
        from src.llm.model_ref import decode_model_ref, is_model_ref

        if primary_model.startswith("modelref:"):
            if not is_model_ref(primary_model):
                return False
            try:
                decode_model_ref(primary_model)
            except ValueError:
                return False
            if not origins.has_hermes and not origins.has_non_hermes:
                return False
        return (
            not origins.is_hermes_only
            and not origins.requires_connection_confirmation
        )

    def refresh_stock_list(self) -> None:
        """
        Read STOCK_LIST environment variable and update the watchlist stocks list in configuration.
\x20\x20\x20\x20\x20\x20\x20\x20
        Supports two configuration methods:
        1. .env file (Local development, scheduled task mode) - Changes will take effect automatically on the next execution
        2. System environment variables (GitHub Actions, Docker) - Fixed at startup, unchanged during runtime
        """
        # Prioritize reading the latest configuration from .env file, so even in container environments, if you modify the .env file,
        # It can also obtain the latest stock list configuration
        env_file = os.getenv("ENV_FILE")
        env_path = Path(env_file) if env_file else (Path(__file__).parent.parent / '.env')
        stock_list_str = ''
        if env_path.exists():
            # Read the latest configuration directly from .env file
            env_values = dotenv_values(env_path)
            stock_list_str = (env_values.get('STOCK_LIST') or '').strip()

        # If .env file does not exist or is not configured, try reading from system environment variables.
        if not stock_list_str:
            stock_list_str = os.getenv('STOCK_LIST', '')

        stock_list = [
            (c or "").strip().upper()
            for c in split_stock_list(stock_list_str)
            if (c or "").strip()
        ]

        self.stock_list = stock_list


    def get_db_url(self, *, create_parent: bool = True) -> str:
        """Return the configured SQLAlchemy URL, optionally creating its parent."""
        db_path = Path(self.database_path)
        if create_parent:
            db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_path.absolute()}"
