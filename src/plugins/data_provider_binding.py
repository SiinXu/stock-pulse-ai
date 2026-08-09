# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Opt-in Data Provider auto-bind helpers for composition roots.

Default process composition keeps Data Provider plugins unbound (manual mode):
a composition caller must pass the exact ``DataFetcherManager.plugin_registry``
into ``PluginManager``. When ``PLUGIN_DATA_PROVIDER_AUTO_BIND=true``, callers
can use these helpers to obtain that exact registry instance so registered
providers become discoverable by the target manager without per-plugin glue.

Important: binding requires the **same** ``ExtensionRegistry`` instance owned
by the manager (not a reconstructed registry that only shares the native
backend). ``DataFetcherManager`` discovers plugins via
``runtime.active_provider_snapshot()``, which walks its own registry
registrations.

The flag defaults to false so unconfigured deployments keep today's behavior.
The default ``ApplicationServices`` composition root owns the process manager
when auto-bind is enabled; explicit composition callers may supply their own
target manager instance.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import Any

from src.utils.sanitize import log_safe_exception

from .registry import ExtensionContract, ExtensionPoint, ExtensionRegistry


logger = logging.getLogger(__name__)

PLUGIN_DATA_PROVIDER_AUTO_BIND_ENV = "PLUGIN_DATA_PROVIDER_AUTO_BIND"
DATA_PROVIDER_BIND_ERROR_INTERFACE = "data_provider_bind_interface_invalid"
DATA_PROVIDER_BIND_ERROR_PRIORITY = "data_provider_bind_priority_conflict"
DATA_PROVIDER_BIND_ERROR_UNAVAILABLE = "data_provider_bind_unavailable"


class DataProviderAutoBindError(RuntimeError):
    """Fail-closed process-composition error with a stable diagnostic code."""

    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


def data_provider_auto_bind_enabled(
    config: Any | None = None,
    env: Mapping[str, str] | None = None,
) -> bool:
    """Return whether opt-in Data Provider auto-bind is enabled.

    Unset / empty / unrecognized values keep the historical manual mode.
    """

    if config is not None:
        return (
            getattr(config, "plugin_data_provider_auto_bind_enabled", False)
            is True
        )
    source = os.environ if env is None else env
    raw = source.get(PLUGIN_DATA_PROVIDER_AUTO_BIND_ENV, "")
    if type(raw) is not str:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def extract_data_provider_contract(
    data_fetcher_manager: Any,
) -> ExtensionContract:
    """Return the live ``data_provider`` contract from a DataFetcherManager."""

    registry = getattr(data_fetcher_manager, "plugin_registry", None)
    if registry is None:
        raise TypeError("data fetcher manager has no plugin_registry")
    contract_getter = getattr(registry, "extension_contract", None)
    if not callable(contract_getter):
        raise TypeError("plugin registry cannot expose extension contracts")
    contract = contract_getter("data_provider")
    if not isinstance(contract, ExtensionContract):
        raise TypeError("data_provider contract is invalid")
    if contract.backend is None:
        raise ValueError("data_provider contract has no native backend")
    return contract


def build_data_provider_bound_contracts(
    data_fetcher_manager: Any,
    *,
    additional_contracts: Mapping[ExtensionPoint, ExtensionContract] | None = None,
) -> dict[ExtensionPoint, ExtensionContract]:
    """Build contract overlays that bind ``data_provider`` to one manager."""

    contracts: dict[ExtensionPoint, ExtensionContract] = {}
    if additional_contracts is not None:
        contracts.update(additional_contracts)
    contracts["data_provider"] = extract_data_provider_contract(data_fetcher_manager)
    return contracts


def build_data_provider_bound_registry(
    data_fetcher_manager: Any,
    *,
    additional_contracts: Mapping[ExtensionPoint, ExtensionContract] | None = None,
) -> ExtensionRegistry:
    """Return a new registry whose data_provider contract mirrors the manager.

    Prefer ``resolve_data_provider_registry`` for routing discoverability.
    """

    return ExtensionRegistry(
        build_data_provider_bound_contracts(
            data_fetcher_manager,
            additional_contracts=additional_contracts,
        )
    )


def resolve_data_provider_registry(
    data_fetcher_manager: Any,
) -> ExtensionRegistry:
    """Return the exact ``plugin_registry`` owned by one DataFetcherManager."""

    registry = getattr(data_fetcher_manager, "plugin_registry", None)
    if not isinstance(registry, ExtensionRegistry):
        raise TypeError("data fetcher manager has no ExtensionRegistry plugin_registry")
    extract_data_provider_contract(data_fetcher_manager)
    return registry


def try_build_auto_bound_registry(
    data_fetcher_manager: Any | None,
    *,
    additional_contracts: Mapping[ExtensionPoint, ExtensionContract] | None = None,
    config: Any | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[ExtensionRegistry | None, str | None]:
    """When auto-bind is on, compose and return the manager's exact registry."""

    if not data_provider_auto_bind_enabled(config=config, env=env):
        return None, None
    if data_fetcher_manager is None:
        return None, None
    try:
        registry = resolve_data_provider_registry(data_fetcher_manager)
        if additional_contracts:
            registry.bind_composition_contracts(additional_contracts)
        return registry, None
    except TypeError as exc:
        log_safe_exception(
            logger,
            "Data provider auto-bind failed: interface mismatch",
            exc,
            error_code=DATA_PROVIDER_BIND_ERROR_INTERFACE,
        )
        return None, DATA_PROVIDER_BIND_ERROR_INTERFACE
    except ValueError as exc:
        log_safe_exception(
            logger,
            "Data provider auto-bind failed: priority or contract conflict",
            exc,
            error_code=DATA_PROVIDER_BIND_ERROR_PRIORITY,
        )
        return None, DATA_PROVIDER_BIND_ERROR_PRIORITY
    except Exception as exc:  # broad-exception: fallback_recorded - callers receive a stable fail-closed bind code
        log_safe_exception(
            logger,
            "Data provider auto-bind failed",
            exc,
            error_code=DATA_PROVIDER_BIND_ERROR_UNAVAILABLE,
        )
        return None, DATA_PROVIDER_BIND_ERROR_UNAVAILABLE
