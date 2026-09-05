# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Manager-owned default-fetcher initialization rebound onto DataFetcherManager.

Extracted from ``src.data_provider.base`` behind an ADR-006 compatibility
facade. Facade ``__init__`` still calls live ``self._init_default_fetchers()``,
which resolves ``get_config()`` on the facade and passes the config into
rebound ``_init_default_fetchers_with_config``. This helper does not import
or call ``get_config`` and does not use ``_get_fundamental_config``.
``__del__`` and timeout-slot construction stay on the facade.
``DataFetcherManager`` remains the public import and patch surface.
"""

from __future__ import annotations

from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Type,
)

from .daily_cache_methods import _clone_facade_descriptor, _descriptor_function

# Facade-only symbols cannot be imported from ``src.data_provider.base`` while
# that module is still assembling this part (circular import). Declare anchors
# so flake8 F821 is clean; rebound methods resolve the real objects from the
# ``src.data_provider.base`` global namespace.
logger = None  # type: ignore[assignment,misc]
BaseFetcher = None  # type: ignore[assignment,misc]

# ``importlib.reload`` retains a module dictionary. Preserve the callback
# installed by the loaded compatibility facade so an owner reload can
# atomically rebuild and rebind both sides of the seam.
_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)


class _InitDefaultFetchersMethods:
    """Source descriptors rebound onto ``DataFetcherManager`` by its facade."""

    def _init_default_fetchers_with_config(self, config) -> None:
        """
        初始化默认数据源列表

        优先级动态调整逻辑：
        - 如果配置了 TUSHARE_TOKEN：实例化 TushareFetcher，并按其内部逻辑提升优先级
        - 如果配置了 Longbridge OAuth 或 Legacy 凭据：实例化 LongbridgeFetcher 作为美股/港股兜底
        - 未配置的可选数据源不实例化，避免在批量拉取时反复探测无效源
        - 默认优先级：
          0. EfinanceFetcher (Priority 0) - 最高优先级
          1. AkshareFetcher (Priority 1)
          2. PytdxFetcher (Priority 2) - 通达信
          3. BaostockFetcher (Priority 3)
          4. YfinanceFetcher (Priority 4)
          5. TencentFetcher (Priority 5) - A 股最终兜底
        """
        from .efinance_fetcher import EfinanceFetcher
        from .tencent_fetcher import TencentFetcher
        from .akshare_fetcher import AkshareFetcher
        from .tushare_fetcher import TushareFetcher
        from .tickflow_fetcher import TickFlowFetcher
        from .pytdx_fetcher import PytdxFetcher
        from .baostock_fetcher import BaostockFetcher
        from .yfinance_fetcher import YfinanceFetcher
        from .longbridge_fetcher import LongbridgeFetcher
        # Create all data source instances (priority is determined in each Fetcher's __init__)
        efinance = EfinanceFetcher()
        tencent = TencentFetcher()
        akshare = AkshareFetcher()
        pytdx = PytdxFetcher()      # Tongdaxin data source (configurable with PYTDX_HOST/PYTDX_PORT)
        baostock = BaostockFetcher()
        yfinance = YfinanceFetcher()
        optional_fetchers: List[BaseFetcher] = []

        tushare_token = (getattr(config, "tushare_token", None) or "").strip()
        if tushare_token:
            optional_fetchers.append(TushareFetcher())  # Automatically adjusts priority when a token is configured
        else:
            logger.debug("[数据源初始化] 跳过未配置的 TushareFetcher")

        tickflow_api_key = (getattr(config, "tickflow_api_key", None) or "").strip()
        if tickflow_api_key:
            optional_fetchers.append(
                TickFlowFetcher(
                    api_key=tickflow_api_key,
                    kline_adjust=getattr(config, "tickflow_kline_adjust", "none"),
                    batch_daily_enabled=getattr(config, "tickflow_batch_daily_enabled", True),
                    batch_size=getattr(config, "tickflow_batch_size", 100),
                    priority=getattr(config, "tickflow_priority", 2),
                )
            )
        else:
            logger.debug("[data source init] skip TickFlowFetcher because TICKFLOW_API_KEY is not configured")

        if LongbridgeFetcher.has_configured_credentials(config):
            optional_fetchers.append(LongbridgeFetcher())  # Longbridge (U.S./Hong Kong stock fallback, lazy loading)
        else:
            logger.debug("[数据源初始化] 跳过未配置的 LongbridgeFetcher")

        finnhub_api_key = (getattr(config, "finnhub_api_key", None) or "").strip()
        if finnhub_api_key:
            from .finnhub_fetcher import FinnhubFetcher
            optional_fetchers.append(FinnhubFetcher())
        else:
            logger.debug("[数据源初始化] 跳过未配置的 FinnhubFetcher")

        alphavantage_api_key = (getattr(config, "alphavantage_api_key", None) or "").strip()
        if alphavantage_api_key:
            from .alphavantage_fetcher import AlphaVantageFetcher
            optional_fetchers.append(AlphaVantageFetcher())
        else:
            logger.debug("[数据源初始化] 跳过未配置的 AlphaVantageFetcher")

        for fetcher in (
            efinance,
            akshare,
            pytdx,
            baostock,
            yfinance,
            tencent,
            *optional_fetchers,
        ):
            self._register_builtin_data_provider(fetcher)

        # The provider is default-off and must only be activated by an explicit
        # boolean value.  Partial config doubles (and older config objects) may
        # synthesize truthy attributes for unknown fields.
        if getattr(config, "crypto_provider_enabled", False) is True:
            from .crypto_coingecko_fetcher import build_crypto_provider_registration

            crypto_registration = build_crypto_provider_registration(config=config)
            self._builtin_provider_handles.append(
                self._data_provider_runtime.register_builtin(
                    registration=crypto_registration,
                    priority=getattr(config, "crypto_coingecko_priority", 10),
                    plugin_id=self._BUILTIN_DATA_PROVIDER_PLUGIN_ID,
                )
            )
        else:
            logger.debug("[data source init] skip CoinGecko because crypto provider is disabled")
        self._sync_registered_data_providers()

        # Build the priority summary from the synchronized registry snapshot.
        priority_info = ", ".join(
            f"{fetcher.name}(P{self._provider_priority(fetcher)})"
            for fetcher in self._get_fetchers_snapshot()
        )
        logger.info(f"已初始化 {len(self._fetchers)} 个数据源（按优先级）: {priority_info}")


EXPECTED_INIT_DEFAULT_FETCHERS_METHOD_NAMES: Tuple[str, ...] = (
    "_init_default_fetchers_with_config",
)


def bind_init_default_fetchers_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind default-fetcher-init descriptors without changing the manager API."""

    bound_names = []
    for name, descriptor in vars(_InitDefaultFetchersMethods).items():
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
