# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""X2 registry adapter for manager-owned data provider instances."""

from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass
from threading import RLock, local
from typing import Callable, Iterable, Iterator, Mapping

from src.plugins import (
    ExtensionContract,
    ExtensionRegistration,
    ExtensionRegistry,
    RegistrationHandle,
)

from .base import DataProvider


_PROVIDER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_CAPABILITY_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
DATA_PROVIDER_MARKETS = frozenset({"cn", "hk", "us", "jp", "kr", "tw"})
DATA_PROVIDER_CAPABILITY_METHODS = {
    "daily_data": "get_daily_data",
    "realtime_quote": "get_realtime_quote",
    "chip_distribution": "get_chip_distribution",
    "stock_name": "get_stock_name",
    "stock_list": "get_stock_list",
    "belong_boards": "get_belong_board",
    "main_indices": "get_main_indices",
    "market_stats": "get_market_stats",
    "sector_rankings": "get_sector_rankings",
    "concept_rankings": "get_concept_rankings",
    "hot_stocks": "get_hot_stocks",
    "limit_up_pool": "get_limit_up_pool",
}


def _freeze_string_set(
    values: Iterable[str],
    *,
    field_name: str,
    pattern: re.Pattern[str] | None = None,
) -> frozenset[str]:
    if isinstance(values, str):
        raise TypeError(f"{field_name} must be a collection of strings")
    try:
        frozen = frozenset(values)
    except TypeError:
        raise TypeError(f"{field_name} must be a collection of strings") from None
    if not frozen or any(type(value) is not str for value in frozen):
        raise ValueError(f"{field_name} must contain strings")
    if pattern is not None and any(pattern.fullmatch(value) is None for value in frozen):
        raise ValueError(f"{field_name} contains an invalid identifier")
    return frozen


def _is_valid_provider_name(value: object) -> bool:
    return (
        type(value) is str
        and bool(value.strip())
        and value == value.strip()
        and len(value) <= 120
        and all(ord(character) >= 32 and ord(character) != 127 for character in value)
    )


@dataclass(frozen=True, slots=True)
class DataProviderRegistration:
    """Immutable factory and eligibility declaration for one provider."""

    provider_id: str
    factory: Callable[[], DataProvider]
    markets: frozenset[str]
    capabilities: frozenset[str]

    def __post_init__(self) -> None:
        if (
            type(self.provider_id) is not str
            or len(self.provider_id) > 128
            or _PROVIDER_ID_PATTERN.fullmatch(self.provider_id) is None
        ):
            raise ValueError("provider_id is invalid")
        if not callable(self.factory):
            raise TypeError("factory must be callable")
        markets = _freeze_string_set(self.markets, field_name="markets")
        if not markets.issubset(DATA_PROVIDER_MARKETS):
            raise ValueError("markets contains an unsupported market")
        capabilities = _freeze_string_set(
            self.capabilities,
            field_name="capabilities",
            pattern=_CAPABILITY_ID_PATTERN,
        )
        if not capabilities.issubset(DATA_PROVIDER_CAPABILITY_METHODS):
            raise ValueError("capabilities contains an unsupported capability")
        object.__setattr__(self, "markets", markets)
        object.__setattr__(self, "capabilities", capabilities)


class _LegacyDataProviderAdapter(DataProvider):
    """Keep patched or historical fetcher objects on the stable interface."""

    def __init__(self, fetcher: object) -> None:
        self._fetcher = fetcher

    @property
    def name(self) -> str:
        return self._fetcher.name

    @property
    def priority(self) -> int:
        return self._fetcher.priority

    @property
    def allow_empty_daily_data(self) -> bool:
        return getattr(self._fetcher, "allow_empty_daily_data", False)

    def get_daily_data(
        self,
        stock_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        days: int = 30,
    ):
        return self._fetcher.get_daily_data(
            stock_code=stock_code,
            start_date=start_date,
            end_date=end_date,
            days=days,
        )

    def __getattr__(self, attribute: str):
        return getattr(self._fetcher, attribute)


def _adapt_builtin_provider(fetcher: object) -> DataProvider:
    if isinstance(fetcher, DataProvider):
        return fetcher
    return _LegacyDataProviderAdapter(fetcher)


@dataclass(frozen=True, slots=True)
class _NativeProviderEntry:
    registration: DataProviderRegistration
    provider: DataProvider
    provider_name: str


@dataclass(frozen=True, slots=True)
class _ActiveDataProvider:
    extension: ExtensionRegistration
    registration: DataProviderRegistration
    provider: DataProvider


class _DataProviderBackend:
    """Instantiate and remove exact provider registrations for X2 ownership."""

    def __init__(
        self,
        builtin_identities: Mapping[str, str],
    ) -> None:
        identities = dict(builtin_identities)
        if any(
            not _is_valid_provider_name(provider_name)
            or type(provider_id) is not str
            or _PROVIDER_ID_PATTERN.fullmatch(provider_id) is None
            for provider_name, provider_id in identities.items()
        ):
            raise ValueError("built-in provider identities are invalid")
        if len(set(identities.values())) != len(identities):
            raise ValueError("built-in provider IDs must be unique")
        self._entries: dict[str, _NativeProviderEntry] = {}
        self._provider_names: dict[str, str] = {}
        self._builtin_ids_by_name = identities
        self._builtin_names_by_id = {
            provider_id: provider_name
            for provider_name, provider_id in identities.items()
        }
        self._reserved_names: set[str] = set(identities)
        self._builtin_registration_handoff = local()
        self._generation = 0
        self._lock = RLock()

    def _builtin_registration_is_allowed(
        self,
        registration_id: str,
        implementation: object | None = None,
    ) -> bool:
        handoff = getattr(
            self._builtin_registration_handoff,
            "registration",
            None,
        )
        if handoff is None or handoff[0] != registration_id:
            return False
        return implementation is None or handoff[1] is implementation

    @contextmanager
    def allow_builtin_registration(
        self,
        registration_id: str,
        implementation: DataProviderRegistration,
    ) -> Iterator[None]:
        """Authorize one exact built-in registration on the current thread."""

        if registration_id not in self._builtin_names_by_id:
            raise ValueError("built-in provider ID is not reserved")
        previous = getattr(
            self._builtin_registration_handoff,
            "registration",
            None,
        )
        self._builtin_registration_handoff.registration = (
            registration_id,
            implementation,
        )
        try:
            yield
        finally:
            if previous is None:
                del self._builtin_registration_handoff.registration
            else:
                self._builtin_registration_handoff.registration = previous

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    def reserve_provider_names(self, provider_names: Iterable[str]) -> None:
        """Protect legacy manager names from later plugin registrations."""

        names = tuple(provider_names)
        if any(type(name) is not str or not name.strip() for name in names):
            raise ValueError("provider names must be non-empty strings")
        with self._lock:
            conflicts = [name for name in names if name in self._provider_names]
            if conflicts:
                raise ValueError("provider name conflicts with an active registration")
            self._reserved_names.update(names)

    def contains(self, registration_id: str) -> bool:
        with self._lock:
            return (
                registration_id in self._entries
                or (
                    registration_id in self._builtin_names_by_id
                    and not self._builtin_registration_is_allowed(registration_id)
                )
            )

    def register(self, registration_id: str, implementation: object) -> None:
        if not isinstance(implementation, DataProviderRegistration):
            raise TypeError("implementation must be a DataProviderRegistration")
        provider = implementation.factory()
        if not isinstance(provider, DataProvider):
            raise TypeError("data provider factory must return DataProvider")
        provider_name = getattr(provider, "name", None)
        if not _is_valid_provider_name(provider_name):
            raise ValueError("data provider name must be a non-empty string")
        builtin_allowed = self._builtin_registration_is_allowed(
            registration_id,
            implementation,
        )
        expected_builtin_name = self._builtin_names_by_id.get(registration_id)
        if builtin_allowed and provider_name != expected_builtin_name:
            raise ValueError("built-in provider name does not match its stable ID")
        for capability in implementation.capabilities:
            method_name = DATA_PROVIDER_CAPABILITY_METHODS[capability]
            if not callable(getattr(provider, method_name, None)):
                raise TypeError(
                    f"data provider does not implement {capability}"
                )

        with self._lock:
            if registration_id in self._entries:
                raise ValueError("provider registration already exists")
            if (
                (
                    provider_name in self._reserved_names
                    and not builtin_allowed
                )
                or provider_name in self._provider_names
            ):
                raise ValueError("provider name already exists")
            self._entries[registration_id] = _NativeProviderEntry(
                registration=implementation,
                provider=provider,
                provider_name=provider_name,
            )
            self._provider_names[provider_name] = registration_id
            self._generation += 1

    def unregister(self, registration_id: str, implementation: object) -> None:
        with self._lock:
            entry = self._entries.get(registration_id)
            if entry is None or entry.registration is not implementation:
                return
            del self._entries[registration_id]
            provider_name = entry.provider_name
            if self._provider_names.get(provider_name) == registration_id:
                del self._provider_names[provider_name]
            self._generation += 1

    def provider_for(
        self,
        registration_id: str,
        implementation: object,
    ) -> DataProvider | None:
        with self._lock:
            entry = self._entries.get(registration_id)
            if entry is None or entry.registration is not implementation:
                return None
            return entry.provider


class _DataProviderPluginRuntime:
    """Point-specific backend attached to the unified X2 registry."""

    def __init__(self, builtin_identities: Mapping[str, str]) -> None:
        self._backend = _DataProviderBackend(builtin_identities)
        self.registry = ExtensionRegistry(
            {
                "data_provider": ExtensionContract(
                    identity_resolver=lambda implementation: implementation.provider_id,
                    validator=lambda implementation: isinstance(
                        implementation,
                        DataProviderRegistration,
                    ),
                    backend=self._backend,
                )
            }
        )

    def reserve_provider_names(self, provider_names: Iterable[str]) -> None:
        self._backend.reserve_provider_names(provider_names)

    def register_builtin(
        self,
        *,
        registration: DataProviderRegistration,
        priority: int,
        plugin_id: str,
    ) -> RegistrationHandle:
        with self._backend.allow_builtin_registration(
            registration.provider_id,
            registration,
        ):
            return self.registry.register(
                plugin_id=plugin_id,
                extension_point="data_provider",
                registration_id=registration.provider_id,
                implementation=registration,
                priority=priority,
            )

    @property
    def generation(self) -> int:
        return self._backend.generation

    def active_provider_snapshot(
        self,
    ) -> tuple[int, tuple[_ActiveDataProvider, ...]]:
        while True:
            generation = self._backend.generation
            active: list[_ActiveDataProvider] = []
            for extension in self.registry.registrations("data_provider"):
                registration = extension.implementation
                if not isinstance(registration, DataProviderRegistration):
                    continue
                provider = self._backend.provider_for(
                    extension.registration_id,
                    registration,
                )
                if provider is None:
                    continue
                active.append(
                    _ActiveDataProvider(
                        extension=extension,
                        registration=registration,
                        provider=provider,
                    )
                )
            if self._backend.generation == generation:
                return generation, tuple(active)
