# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Data-provider capability inventory, selection, and plugin synchronization."""

import logging
from types import FunctionType
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Type,
)

from src.utils.sanitize import log_safe_exception

if TYPE_CHECKING:
    from src.plugins import ExtensionRegistry
    from .base import BaseFetcher, DataProvider
    from .plugin_registry import DataProviderRegistration


logger = logging.getLogger("data_provider.base")


# ``importlib.reload`` retains a module dictionary. Preserve the callback
# installed by the loaded compatibility facade so an owner reload can
# atomically rebuild and rebind both sides of the seam.
_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)


def _reset_capability_inventory() -> Tuple[str, ...]:
    """Rebuild facade-owned inventories and return their binding order."""

    global _DAILY_MARKET_FETCHER_SUPPORT
    global _BUILTIN_DATA_PROVIDER_IDS
    global _BUILTIN_DATA_PROVIDER_PLUGIN_ID
    global _DAILY_MARKETS

    _DAILY_MARKET_FETCHER_SUPPORT = {
        "EfinanceFetcher": {"cn"},
        "TencentFetcher": {"cn"},
        "AkshareFetcher": {"cn", "hk"},
        "TushareFetcher": {"cn", "hk"},
        "TickFlowFetcher": {"cn"},
        "PytdxFetcher": {"cn"},
        "BaostockFetcher": {"cn"},
        "YfinanceFetcher": {"cn", "hk", "us", "jp", "kr", "tw"},
        "LongbridgeFetcher": {"hk", "us"},
        "FinnhubFetcher": {"us"},
        "AlphaVantageFetcher": {"us"},
    }
    _BUILTIN_DATA_PROVIDER_IDS = {
        "EfinanceFetcher": "efinance",
        "TencentFetcher": "tencent",
        "AkshareFetcher": "akshare",
        "TushareFetcher": "tushare",
        "TickFlowFetcher": "tickflow",
        "PytdxFetcher": "pytdx",
        "BaostockFetcher": "baostock",
        "YfinanceFetcher": "yfinance",
        "LongbridgeFetcher": "longbridge",
        "FinnhubFetcher": "finnhub",
        "AlphaVantageFetcher": "alphavantage",
    }
    _BUILTIN_DATA_PROVIDER_PLUGIN_ID = "stockpulse.builtin.data-providers"
    _DAILY_MARKETS = frozenset({"cn", "hk", "us", "jp", "kr", "tw"})
    return (
        "_DAILY_MARKET_FETCHER_SUPPORT",
        "_BUILTIN_DATA_PROVIDER_IDS",
        "_BUILTIN_DATA_PROVIDER_PLUGIN_ID",
        "_DAILY_MARKETS",
    )


_reset_capability_inventory()


class _CapabilityCatalogMethods:
    """Source descriptors rebound onto ``DataFetcherManager`` by its facade."""

    @property
    def plugin_registry(self) -> "ExtensionRegistry":
        """Return the manager-owned X2 registry used by provider plugins."""

        self._ensure_concurrency_guards()
        if self._data_provider_runtime is None:
            from .plugin_registry import _DataProviderPluginRuntime

            self._data_provider_runtime = _DataProviderPluginRuntime(
                self._BUILTIN_DATA_PROVIDER_IDS
            )
            self._data_provider_runtime.reserve_provider_names(
                fetcher.name for fetcher in getattr(self, "_fetchers", [])
            )
        return self._data_provider_runtime.registry

    def _assign_fetcher_static_order_locked(
        self,
        fetcher: "DataProvider",
    ) -> None:
        fetcher_key = id(fetcher)
        if fetcher_key in self._fetcher_static_order:
            return
        self._fetcher_static_order[fetcher_key] = self._next_fetcher_static_order
        self._next_fetcher_static_order += 1

    def _provider_priority(self, fetcher: "DataProvider") -> int:
        resolver = getattr(fetcher, "_manager_plugin_priority", None)
        if callable(resolver):
            priority = resolver()
            if type(priority) is int:
                return priority
        return self._provider_priorities.get(id(fetcher), fetcher.priority)

    def _sort_fetchers_locked(self) -> None:
        self._fetchers.sort(
            key=lambda fetcher: (
                self._provider_priority(fetcher),
                self._fetcher_static_order.get(id(fetcher), 0),
            )
        )

    def _remove_registered_fetcher_locked(
        self,
        fetcher: "DataProvider",
    ) -> None:
        self._fetchers = [item for item in self._fetchers if item is not fetcher]
        fetcher_key = id(fetcher)
        self._provider_priorities.pop(fetcher_key, None)
        self._fetcher_static_order.pop(fetcher_key, None)
        # A caller may still hold a pre-unload provider snapshot. Retaining the
        # manager-owned guard keeps those late calls serialized on the same lock.

    def _sync_registered_data_providers(self) -> None:
        runtime = getattr(self, "_data_provider_runtime", None)
        if runtime is None:
            return
        while True:
            generation, active = runtime.active_provider_snapshot()
            active_by_id = {
                item.extension.registration_id: item
                for item in active
            }
            with self._fetchers_lock:
                for registration_id, fetcher in tuple(
                    self._registered_fetchers.items()
                ):
                    current = active_by_id.get(registration_id)
                    if current is None or current.provider is not fetcher:
                        self._remove_registered_fetcher_locked(fetcher)
                        del self._registered_fetchers[registration_id]

                for item in active:
                    registration_id = item.extension.registration_id
                    fetcher = item.provider
                    fetcher._manager_bind_plugin_priority(
                        item.extension.priority
                    )
                    if self._registered_fetchers.get(registration_id) is not fetcher:
                        self._registered_fetchers[registration_id] = fetcher
                        self._fetchers.append(fetcher)
                        self._assign_fetcher_static_order_locked(fetcher)
                    fetcher_key = id(fetcher)
                    self._provider_priorities[fetcher_key] = item.extension.priority

                self._sort_fetchers_locked()
                self._refresh_fetcher_indexes_locked()
            if runtime.generation == generation:
                return

    def _get_fetchers_snapshot(self) -> "List[DataProvider]":
        self._ensure_concurrency_guards()
        self._sync_registered_data_providers()
        with self._fetchers_lock:
            return list(getattr(self, "_fetchers", []))

    @staticmethod
    def _provider_plugin_registration(
        fetcher: object,
    ) -> Optional["DataProviderRegistration"]:
        resolver = getattr(fetcher, "_manager_plugin_registration", None)
        if not callable(resolver):
            return None
        registration = resolver()
        if registration is None:
            return None
        from .plugin_registry import DataProviderRegistration

        return (
            registration
            if isinstance(registration, DataProviderRegistration)
            else None
        )

    def _provider_supports_capability(
        self,
        fetcher: "DataProvider",
        capability: str,
        market: Optional[str] = None,
    ) -> bool:
        registration = self._provider_plugin_registration(fetcher)
        if registration is None:
            return True
        return (
            capability in registration.capabilities
            and (market is None or market in registration.markets)
        )

    def _get_fetchers_for_capability(
        self,
        capability: str,
        *,
        market: Optional[str] = None,
        plugins_only: bool = False,
    ) -> "List[DataProvider]":
        fetchers = self._get_fetchers_snapshot()
        selected: List[DataProvider] = []
        for fetcher in fetchers:
            is_plugin = self._provider_plugin_registration(fetcher) is not None
            if plugins_only and not is_plugin:
                continue
            if self._provider_supports_capability(
                fetcher,
                capability,
                market,
            ):
                selected.append(fetcher)
        return selected

    def _refresh_fetcher_indexes_locked(self) -> None:
        self._fetchers_by_name = {fetcher.name: fetcher for fetcher in self._fetchers}

    def _get_fetcher_by_name(
        self,
        fetcher_name: str,
        capability: str = "",
    ) -> "Optional[DataProvider]":
        self._ensure_concurrency_guards()
        self._sync_registered_data_providers()
        with self._fetchers_lock:
            fetcher = self._fetchers_by_name.get(fetcher_name)
            if fetcher is None and self._fetchers:
                self._refresh_fetcher_indexes_locked()
                fetcher = self._fetchers_by_name.get(fetcher_name)
        if fetcher is None:
            return None
        if capability and not self._provider_supports_capability(
            fetcher,
            capability,
        ):
            return None
        if not self._is_fetcher_available(fetcher, capability=capability):
            return None
        return fetcher

    @staticmethod
    def _call_availability_probe(
        fetcher: "BaseFetcher",
        probe_name: str,
        capability: str,
    ) -> Optional[bool]:
        probe = getattr(fetcher, probe_name, None)
        if not callable(probe):
            return None
        try:
            if probe_name == "is_available_for_request":
                return bool(probe(capability))
            return bool(probe())
        except TypeError:
            return bool(probe())
        except Exception as exc:  # broad-exception: fallback_recorded - Probe failure is safely logged before the provider is skipped.
            log_safe_exception(
                logger,
                "Data provider availability probe failed",
                exc,
                error_code="data_provider_availability_probe_failed",
                level=logging.DEBUG,
                context={
                    "provider": fetcher.name,
                    "probe": probe_name,
                    "capability": capability or "default",
                },
            )
            return False

    @classmethod
    def _is_fetcher_available(
        cls,
        fetcher: "BaseFetcher",
        capability: str = "",
    ) -> bool:
        for probe_name in (
            "is_available_for_request",
            "is_available",
            "_is_available",
        ):
            result = cls._call_availability_probe(
                fetcher,
                probe_name,
                capability,
            )
            if result is not None:
                return result
        return True

    def _filter_daily_fetchers_for_market(
        self,
        fetchers: "List[DataProvider]",
        market: str,
    ) -> "List[DataProvider]":
        """Apply plugin declarations without changing built-in CN eligibility."""

        kept: List[DataProvider] = []
        skipped: List[str] = []
        for fetcher in fetchers:
            registration = self._provider_plugin_registration(fetcher)
            if registration is not None:
                supported = registration.markets
            elif market != "cn":
                supported = self._DAILY_MARKET_FETCHER_SUPPORT.get(fetcher.name)
            else:
                supported = None
            if supported is not None and market not in supported:
                skipped.append(fetcher.name)
            else:
                kept.append(fetcher)

        if skipped:
            logger.info(
                "[数据源路由] %s 日线跳过不支持的数据源: %s",
                market,
                ", ".join(skipped),
            )
        return kept

    def _filter_fetchers_by_capability(
        self,
        fetchers: "List[DataProvider]",
        capability: str,
    ) -> "List[DataProvider]":
        """Skip request-time unavailable fetchers before entering route-specific loops."""

        kept: List[DataProvider] = []
        skipped: List[str] = []

        for fetcher in fetchers:
            declared = self._provider_supports_capability(fetcher, capability)
            if declared and self._is_fetcher_available(
                fetcher,
                capability=capability,
            ):
                kept.append(fetcher)
            else:
                skipped.append(fetcher.name)

        if skipped:
            logger.info(
                "[数据源路由] %s 跳过暂不可用的数据源: %s",
                capability or "request",
                ", ".join(skipped),
            )

        return kept

    def _register_builtin_data_provider(self, fetcher: object) -> None:
        from .plugin_registry import (
            DataProviderRegistration,
            _adapt_builtin_provider,
        )

        provider = _adapt_builtin_provider(fetcher)
        provider_id = self._BUILTIN_DATA_PROVIDER_IDS.get(provider.name)
        supported_markets = self._DAILY_MARKET_FETCHER_SUPPORT.get(provider.name)
        if provider_id is None or supported_markets is None:
            raise ValueError("built-in data provider identity is not configured")
        registration = DataProviderRegistration(
            provider_id=provider_id,
            factory=lambda provider=provider: provider,
            markets=supported_markets,
            capabilities={"daily_data"},
        )
        handle = self._data_provider_runtime.register_builtin(
            registration=registration,
            priority=provider.priority,
            plugin_id=self._BUILTIN_DATA_PROVIDER_PLUGIN_ID,
        )
        self._builtin_provider_handles.append(handle)

    def add_fetcher(self, fetcher: "DataProvider") -> None:
        """添加数据源并重新排序"""
        self._ensure_concurrency_guards()
        if self._data_provider_runtime is not None:
            self._data_provider_runtime.reserve_provider_names((fetcher.name,))
        with self._fetchers_lock:
            self._fetchers.append(fetcher)
            self._assign_fetcher_static_order_locked(fetcher)
            self._sort_fetchers_locked()
            self._refresh_fetcher_indexes_locked()

    @property
    def available_fetchers(self) -> List[str]:
        """返回可用数据源名称列表"""
        return [f.name for f in self._get_fetchers_snapshot()]


def _resolve_annotations(
    function: FunctionType,
    global_namespace: Dict[str, Any],
) -> Dict[str, Any]:
    """Resolve annotations exactly as they were defined in the legacy facade."""

    data_provider_type = global_namespace["DataProvider"]
    base_fetcher_type = global_namespace["BaseFetcher"]
    legacy_types = {
        "DataProvider": data_provider_type,
        "BaseFetcher": base_fetcher_type,
        "List[DataProvider]": List[data_provider_type],
        "Optional[DataProvider]": Optional[data_provider_type],
    }
    return {
        name: legacy_types.get(annotation, annotation)
        for name, annotation in function.__annotations__.items()
    }


def _clone_facade_function(
    function: FunctionType,
    global_namespace: Dict[str, Any],
    *,
    qualname: str,
) -> FunctionType:
    """Clone one method so global lookups retain ``data_provider.base`` seams."""

    cloned = FunctionType(
        function.__code__,
        global_namespace,
        name=function.__name__,
        argdefs=function.__defaults__,
        closure=function.__closure__,
    )
    cloned.__annotations__ = _resolve_annotations(function, global_namespace)
    cloned.__dict__.update(function.__dict__)
    cloned.__doc__ = function.__doc__
    cloned.__kwdefaults__ = (
        dict(function.__kwdefaults__) if function.__kwdefaults__ else None
    )
    cloned.__module__ = str(global_namespace["__name__"])
    cloned.__qualname__ = qualname
    if hasattr(function, "__type_params__"):
        cloned.__type_params__ = function.__type_params__
    return cloned


def _descriptor_function(descriptor: Any) -> Optional[FunctionType]:
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    if isinstance(descriptor, property):
        return descriptor.fget
    if isinstance(descriptor, FunctionType):
        return descriptor
    return None


def _clone_facade_descriptor(
    descriptor: Any,
    global_namespace: Dict[str, Any],
    *,
    owner_qualname: str,
) -> Any:
    def clone(function: Optional[FunctionType]) -> Optional[FunctionType]:
        if function is None:
            return None
        return _clone_facade_function(
            function,
            global_namespace,
            qualname=f"{owner_qualname}.{function.__name__}",
        )

    if isinstance(descriptor, staticmethod):
        return staticmethod(clone(descriptor.__func__))
    if isinstance(descriptor, classmethod):
        return classmethod(clone(descriptor.__func__))
    if isinstance(descriptor, property):
        return property(
            clone(descriptor.fget),
            clone(descriptor.fset),
            clone(descriptor.fdel),
            descriptor.__doc__,
        )
    return clone(descriptor)


def bind_capability_catalog_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind catalog descriptors without changing the manager's Interface."""

    bound_names = []
    for name, descriptor in vars(_CapabilityCatalogMethods).items():
        if name.startswith("__") or _descriptor_function(descriptor) is None:
            continue
        setattr(
            target_class,
            name,
            _clone_facade_descriptor(
                descriptor,
                global_namespace,
                owner_qualname=target_class.__qualname__,
            ),
        )
        bound_names.append(name)
    return tuple(bound_names)


def _install_facade_reload_hook(hook: Callable[[], None]) -> None:
    """Register the loaded facade assembly callback for owner reloads."""

    global _FACADE_RELOAD_HOOK
    _FACADE_RELOAD_HOOK = hook


def _rebind_loaded_facade() -> None:
    """Refresh a registered facade after this owner module is reloaded."""

    hook = _FACADE_RELOAD_HOOK
    if hook is not None:
        hook()


_rebind_loaded_facade()
