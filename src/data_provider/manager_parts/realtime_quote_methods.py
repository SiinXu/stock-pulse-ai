# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Manager-owned realtime quote orchestration rebound onto DataFetcherManager.

Extracted from ``src.data_provider.base`` behind an ADR-006 compatibility
facade. Field-trust attempt bookkeeping stays in
``realtime_field_trust_methods``; ``prefetch_realtime_quotes`` and Local Only
policy stay on the facade. These descriptors own timestamp enrichment,
plugin realtime fallback, ``get_realtime_quote`` routing, supplement helpers,
and Longbridge preference. ``DataFetcherManager`` remains the public import
and patch surface.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Type,
)

from src.utils.sanitize import log_safe_exception

from .daily_cache_methods import _clone_facade_descriptor, _descriptor_function

# Facade-only symbols cannot be imported from ``src.data_provider.base`` while
# that module is still assembling this part (circular import). Declare anchors
# so flake8 F821 is clean; rebound methods resolve the real objects from the
# ``src.data_provider.base`` global namespace.
UnifiedRealtimeQuote = None  # type: ignore[assignment,misc]
normalize_stock_code = None  # type: ignore[assignment,misc]
_market_tag = None  # type: ignore[assignment,misc]
_is_hk_market = None  # type: ignore[assignment,misc]
_is_jp_market = None  # type: ignore[assignment,misc]
_is_kr_market = None  # type: ignore[assignment,misc]
_is_tw_market = None  # type: ignore[assignment,misc]
record_provider_run = None  # type: ignore[assignment,misc]
record_provider_run_started = None  # type: ignore[assignment,misc]
summarize_exception = None  # type: ignore[assignment,misc]
_field_trust = None  # type: ignore[assignment,misc]

logger = logging.getLogger("src.data_provider.base")

# ``importlib.reload`` retains a module dictionary. Preserve the callback
# installed by the loaded compatibility facade so an owner reload can
# atomically rebuild and rebind both sides of the seam.
_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)


class _RealtimeQuoteMethods:
    """Source descriptors rebound onto ``DataFetcherManager`` by its facade."""

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _parse_realtime_timestamp(value: Any) -> Optional[datetime]:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            parsed = value
        else:
            text = str(value).strip()
            if not text:
                return None
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError:
                return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _enrich_realtime_quote(
        self,
        quote,
        *,
        fallback_from: Optional[str] = None,
        realtime_cache_ttl: Optional[int] = None,
    ):
        """Attach runtime metadata without inventing provider-side timestamps."""
        if quote is None:
            return None

        fetched_at = self._utc_now_iso()
        setattr(quote, "fetched_at", fetched_at)
        if fallback_from:
            setattr(quote, "fallback_from", str(fallback_from))

        provider_dt = self._parse_realtime_timestamp(
            getattr(quote, "provider_timestamp", None)
        )
        if provider_dt is None:
            setattr(quote, "provider_timestamp", None)
            setattr(quote, "stale_seconds", None)
            setattr(quote, "is_stale", None)
            # Issue #1129: unknown provider timestamp means unknown staleness.
            _field_trust.finalize(quote)
            return quote

        setattr(quote, "provider_timestamp", provider_dt.isoformat())
        fetched_dt = self._parse_realtime_timestamp(fetched_at) or datetime.now(timezone.utc)
        stale_seconds = max(0, int((fetched_dt - provider_dt).total_seconds()))
        ttl = realtime_cache_ttl if realtime_cache_ttl is not None else 600
        setattr(quote, "stale_seconds", stale_seconds)
        setattr(quote, "is_stale", stale_seconds > int(ttl))
        # Issue #1129: complete per-field attribution at the single exit
        # point of every successful realtime-quote path.
        _field_trust.finalize(quote)
        return quote

    def _try_plugin_realtime_quote(
        self,
        stock_code: str,
        market: str,
    ) -> Tuple[Optional[UnifiedRealtimeQuote], Optional[str]]:
        """Try declared plugin providers after the frozen built-in route."""

        failed_attempts: List[Any] = []
        for fetcher in self._get_fetchers_for_capability(
            "realtime_quote",
            market=market,
            plugins_only=True,
        ):
            attempt_sink = _field_trust.QuoteAttemptSink()
            quote = self._try_fetcher_quote(
                stock_code,
                fetcher.name,
                _selected_fetcher=fetcher,
                _attempt_sink=attempt_sink,
            )
            if quote is not None:
                self._attach_prior_attempts(quote, failed_attempts)
                return quote, fetcher.name
            failed_attempts.append(
                self._sink_non_ok(
                    attempt_sink,
                    self._attempt_provider_token(
                        fetcher.name,
                        fetcher=fetcher,
                    ),
                    self._realtime_circuit_key(
                        fetcher.name,
                        fetcher=fetcher,
                        stock_code=stock_code,
                    ),
                )
            )
        return None, None

    def get_realtime_quote(self, stock_code: str, *, log_final_failure: bool = True):
        """
        获取实时行情数据（自动故障切换）

        故障切换策略（按配置的优先级）：
        1. 美股：使用 YfinanceFetcher.get_realtime_quote()
        2. EfinanceFetcher.get_realtime_quote()
        3. AkshareFetcher.get_realtime_quote(source="em")  - 东财
        4. AkshareFetcher.get_realtime_quote(source="sina") - 新浪
        5. AkshareFetcher.get_realtime_quote(source="tencent") - 腾讯
        6. 返回 None（降级兜底）

        Args:
            stock_code: 股票代码
            log_final_failure: Whether to emit the final "all sources failed"
                summary log when no realtime quote is available.

        Returns:
            UnifiedRealtimeQuote 对象，所有数据源都失败则返回 None
        """
        raw_stock_code = (stock_code or "").strip()
        # Normalize code (strip SH/SZ prefix etc.)
        stock_code = normalize_stock_code(stock_code)

        from .akshare_fetcher import _is_us_code
        from .us_index_mapping import is_us_index_code
        from src.config import get_config

        config = get_config()

        # If real-time market data functionality is disabled, return None directly.
        if not config.enable_realtime_quote:
            logger.debug(f"[实时行情] 功能已禁用，跳过 {stock_code}")
            return None

        if _market_tag(stock_code) == "crypto":
            failed_attempts: List[Any] = []
            for fetcher in self._get_fetchers_for_capability(
                "realtime_quote", market="crypto"
            ):
                if not self._is_fetcher_available(fetcher, capability="realtime_quote"):
                    continue
                attempt_sink = _field_trust.QuoteAttemptSink()
                quote = self._try_fetcher_quote(
                    stock_code,
                    fetcher.name,
                    _selected_fetcher=fetcher,
                    _attempt_sink=attempt_sink,
                )
                if quote is not None:
                    self._attach_prior_attempts(quote, failed_attempts)
                    return self._enrich_realtime_quote(
                        quote,
                        realtime_cache_ttl=getattr(config, "realtime_cache_ttl", None),
                    )
                failed_attempts.append(
                    self._sink_non_ok(
                        attempt_sink,
                        self._attempt_provider_token(
                            fetcher.name,
                            fetcher=fetcher,
                        ),
                        self._realtime_circuit_key(
                            fetcher.name,
                            fetcher=fetcher,
                            stock_code=stock_code,
                        ),
                    )
                )
            if log_final_failure:
                logger.info("[realtime quote] no crypto provider available for %s", stock_code)
            return None

        # ----------------------------------------------------------
        # U.S. Stocks (Indices + Individual Stocks) / Hong Kong Stocks — Dedicated Dual-Source Routing
        #   Configure Longbridge: Longbridge is preferred, YFinance/AkShare supplement.
        #   Without Longbridge credentials: prefer YFinance/AkShare; otherwise Longbridge supplements them.
        #   U.S. stock indices: Always use YFinance as the primary source (Longbridge does not provide index data)
        # ----------------------------------------------------------
        is_us_index = is_us_index_code(stock_code)
        is_us = is_us_index or _is_us_code(stock_code)
        is_hk = (not is_us) and _is_hk_market(stock_code)
        is_jp = (not is_us) and (not is_hk) and _is_jp_market(stock_code)
        is_kr = (not is_us) and (not is_hk) and _is_kr_market(stock_code)
        is_tw = (not is_us) and (not is_hk) and _is_tw_market(stock_code)

        if is_jp or is_kr or is_tw:
            market_label = "日股" if is_jp else "韩股" if is_kr else "台股"
            yfinance_sink = _field_trust.QuoteAttemptSink()
            quote = self._try_fetcher_quote(
                stock_code,
                "YfinanceFetcher",
                _attempt_sink=yfinance_sink,
            )
            if quote is not None:
                logger.info(f"[实时行情] {market_label} {stock_code} 成功获取 (来源: YfinanceFetcher)")
                return self._enrich_realtime_quote(
                    quote,
                    realtime_cache_ttl=getattr(config, "realtime_cache_ttl", None),
                )
            prior_attempts = [
                self._sink_non_ok(
                    yfinance_sink,
                    "yfinance",
                    self._realtime_circuit_key(
                        "YfinanceFetcher",
                        stock_code=stock_code,
                    ),
                ),
            ]
            market = "jp" if is_jp else "kr" if is_kr else "tw"
            quote, plugin_name = self._try_plugin_realtime_quote(
                stock_code,
                market,
            )
            if quote is not None:
                self._attach_prior_attempts(quote, prior_attempts)
                logger.info(
                    "Realtime quote plugin fallback succeeded "
                    "market=%s symbol=%s provider=%s",
                    market,
                    stock_code,
                    plugin_name,
                )
                return self._enrich_realtime_quote(
                    quote,
                    fallback_from="yfinance",
                    realtime_cache_ttl=getattr(config, "realtime_cache_ttl", None),
                )
            if log_final_failure:
                logger.info(f"[实时行情] {market_label} {stock_code} 无可用数据源")
            return None

        if is_us or is_hk:
            prefer_lb = self._longbridge_preferred() and not is_us_index
            if is_us:
                primary_src = "LongbridgeFetcher" if prefer_lb else "YfinanceFetcher"
                secondary_src = "YfinanceFetcher" if prefer_lb else "LongbridgeFetcher"
                market_label = "美股指数" if is_us_index else "美股"
                primary_kw: dict = {}
                secondary_kw: dict = {}
            else:
                primary_src = "LongbridgeFetcher" if prefer_lb else "AkshareFetcher"
                secondary_src = "AkshareFetcher" if prefer_lb else "LongbridgeFetcher"
                market_label = "港股"
                primary_kw = {"source": "hk"} if primary_src == "AkshareFetcher" else {}
                secondary_kw = {"source": "hk"} if secondary_src == "AkshareFetcher" else {}

            primary_token = self._realtime_fetcher_token(primary_src, **primary_kw)
            failed_attempts: List[Any] = []
            primary_sink = _field_trust.QuoteAttemptSink()
            primary_quote = self._try_fetcher_quote(
                stock_code,
                primary_src,
                _attempt_sink=primary_sink,
                **primary_kw,
            )
            fallback_from = primary_token if primary_quote is None else None
            if primary_quote is None:
                failed_attempts.append(
                    self._sink_non_ok(
                        primary_sink,
                        primary_token,
                        self._realtime_circuit_key(
                            primary_src,
                            stock_code=stock_code,
                            **primary_kw,
                        ),
                    )
                )
            else:
                logger.info(f"[实时行情] {market_label} {stock_code} 成功获取 (来源: {primary_src})")
            primary_quote = self._supplement_quote(
                stock_code,
                primary_quote,
                secondary_src,
                _failed_attempts=failed_attempts,
                **secondary_kw,
            )
            # U.S. Individual Stocks (non-indices) attempt to supplement missing fields from Finnhub/AlphaVantage
            if is_us and not is_us_index and primary_quote is not None:
                for extra_src in ["FinnhubFetcher", "AlphaVantageFetcher"]:
                    primary_quote = self._supplement_quote(
                        stock_code, primary_quote, extra_src,
                    )
            if primary_quote is not None:
                self._attach_prior_attempts(primary_quote, failed_attempts)
                return self._enrich_realtime_quote(
                    primary_quote,
                    fallback_from=fallback_from,
                    realtime_cache_ttl=getattr(config, "realtime_cache_ttl", None),
                )
            market = "us" if is_us else "hk"
            plugin_quote, plugin_name = self._try_plugin_realtime_quote(
                stock_code,
                market,
            )
            if plugin_quote is not None:
                self._attach_prior_attempts(plugin_quote, failed_attempts)
                logger.info(
                    "Realtime quote plugin fallback succeeded "
                    "market=%s symbol=%s provider=%s",
                    market,
                    stock_code,
                    plugin_name,
                )
                return self._enrich_realtime_quote(
                    plugin_quote,
                    fallback_from=primary_token,
                    realtime_cache_ttl=getattr(config, "realtime_cache_ttl", None),
                )
            if log_final_failure:
                logger.info(f"[实时行情] {market_label} {stock_code} 无可用数据源")
            return None

        # Get the priority of the data source for the configuration
        source_priority = [
            source.strip().lower()
            for source in config.realtime_source_priority.split(',')
            if source.strip()
        ]

        errors = []
        failed_sources: List[str] = []
        # primary_quote holds the first successful result; we may supplement
        # missing fields (volume_ratio, turnover_rate, etc.) from later sources.
        primary_quote = None
        primary_fallback_from: Optional[str] = None

        for source_index, source in enumerate(source_priority):
            attempt_start = time.time()
            fallback_to = source_priority[source_index + 1] if source_index + 1 < len(source_priority) else None
            fetcher = None
            try:
                quote = None

                if source == "efinance":
                    fetcher = self._get_fetcher_by_name("EfinanceFetcher", capability="realtime_quote")
                    if fetcher is not None and hasattr(fetcher, 'get_realtime_quote'):
                        record_provider_run_started(
                            data_type="realtime_quote",
                            provider=fetcher.name,
                            operation="get_realtime_quote",
                        )
                        quote = self._call_fetcher_method(fetcher, 'get_realtime_quote', stock_code)

                elif source == "akshare_em":
                    fetcher = self._get_fetcher_by_name("AkshareFetcher", capability="realtime_quote")
                    if fetcher is not None and hasattr(fetcher, 'get_realtime_quote'):
                        record_provider_run_started(
                            data_type="realtime_quote",
                            provider=fetcher.name,
                            operation="get_realtime_quote",
                        )
                        quote = self._call_fetcher_method(fetcher, 'get_realtime_quote', stock_code, source="em")

                elif source == "akshare_sina":
                    fetcher = self._get_fetcher_by_name("AkshareFetcher", capability="realtime_quote")
                    if fetcher is not None and hasattr(fetcher, 'get_realtime_quote'):
                        record_provider_run_started(
                            data_type="realtime_quote",
                            provider=fetcher.name,
                            operation="get_realtime_quote",
                        )
                        quote = self._call_fetcher_method(fetcher, 'get_realtime_quote', stock_code, source="sina")

                elif source in ("tencent", "akshare_qq"):
                    fetcher = self._get_fetcher_by_name("AkshareFetcher", capability="realtime_quote")
                    if fetcher is not None and hasattr(fetcher, 'get_realtime_quote'):
                        record_provider_run_started(
                            data_type="realtime_quote",
                            provider=fetcher.name,
                            operation="get_realtime_quote",
                        )
                        quote = self._call_fetcher_method(fetcher, 'get_realtime_quote', stock_code, source="tencent")

                elif source == "tushare":
                    fetcher = self._get_fetcher_by_name("TushareFetcher", capability="realtime_quote")
                    if fetcher is not None and hasattr(fetcher, 'get_realtime_quote'):
                        record_provider_run_started(
                            data_type="realtime_quote",
                            provider=fetcher.name,
                            operation="get_realtime_quote",
                        )
                        quote = self._call_fetcher_method(fetcher, 'get_realtime_quote', raw_stock_code or stock_code)

                elif source == "tickflow":
                    fetcher = self._get_fetcher_by_name("TickFlowFetcher", capability="realtime_quote")
                    if fetcher is not None and hasattr(fetcher, 'get_realtime_quote'):
                        record_provider_run_started(
                            data_type="realtime_quote",
                            provider=fetcher.name,
                            operation="get_realtime_quote",
                        )
                        quote = self._call_fetcher_method(fetcher, 'get_realtime_quote', raw_stock_code or stock_code)

                provider_name = fetcher.name if fetcher is not None else source

                if quote is not None and quote.has_basic_data():
                    record_provider_run(
                        data_type="realtime_quote",
                        provider=provider_name,
                        operation="get_realtime_quote",
                        success=True,
                        latency_ms=int((time.time() - attempt_start) * 1000),
                        fallback_to=fallback_to if primary_quote is None and self._quote_needs_supplement(quote) else None,
                        record_count=1,
                    )
                    if primary_quote is None:
                        # First successful source becomes primary
                        primary_quote = quote
                        primary_fallback_from = failed_sources[0] if failed_sources else None
                        logger.info(f"[实时行情] {stock_code} 成功获取 (来源: {source})")
                        # If all key supplementary fields are present, return early
                        if not self._quote_needs_supplement(primary_quote):
                            _field_trust.attach_failed_sources(
                                primary_quote,
                                failed_sources,
                                stock_code=stock_code,
                            )
                            return self._enrich_realtime_quote(
                                primary_quote,
                                fallback_from=primary_fallback_from,
                                realtime_cache_ttl=getattr(config, "realtime_cache_ttl", None),
                            )
                        # Otherwise, continue to try later sources for missing fields
                        logger.debug(f"[实时行情] {stock_code} 部分字段缺失，尝试从后续数据源补充")
                        supplement_attempts = 0
                    else:
                        # Supplement missing fields from this source (limit attempts)
                        supplement_attempts += 1
                        if supplement_attempts > 1:
                            logger.debug(f"[实时行情] {stock_code} 补充尝试已达上限，停止继续")
                            break
                        _field_trust.observe_cross_source_quotes(
                            primary_quote, quote, stock_code=stock_code,
                            market=_market_tag(normalize_stock_code(stock_code)),
                            primary_candidates=(getattr(primary_quote, "source", None),),
                            secondary_candidates=(getattr(quote, "source", None), source, provider_name),
                            asset_type=getattr(primary_quote, "instrument_type", None),
                        )
                        merged = self._merge_quote_fields(primary_quote, quote)
                        if merged:
                            logger.info(f"[实时行情] {stock_code} 从 {source} 补充了缺失字段: {merged}")
                        # Stop supplementing once all key fields are filled
                        if not self._quote_needs_supplement(primary_quote):
                            break
                else:
                    record_provider_run(
                        data_type="realtime_quote",
                        provider=provider_name,
                        operation="get_realtime_quote",
                        success=False,
                        latency_ms=int((time.time() - attempt_start) * 1000),
                        error_type="empty",
                        error_message="empty or incomplete quote",
                        fallback_to=fallback_to,
                        record_count=0,
                    )
                    if primary_quote is None:
                        failed_sources.append(source)
                    else:
                        _field_trust.record_provider_attempt(
                            primary_quote,
                            provider=source,
                            status=_field_trust.PROVIDER_STATUS_EMPTY,
                            role=_field_trust.PROVIDER_ROLE_ATTEMPTED,
                            stock_code=stock_code,
                        )

            except Exception as e:  # broad-exception: fallback_recorded - diagnostics precede realtime fallback
                error_msg = f"[{source}] 失败: {str(e)}"
                error_type, error_reason = summarize_exception(e)
                record_provider_run(
                    data_type="realtime_quote",
                    provider=getattr(fetcher, "name", source),
                    operation="get_realtime_quote",
                    success=False,
                    latency_ms=int((time.time() - attempt_start) * 1000),
                    error_type=error_type,
                    error_message=error_reason,
                    fallback_to=fallback_to,
                )
                log_safe_exception(
                    logger,
                    "Data provider realtime quote failed; trying next provider",
                    e,
                    error_code="data_provider_realtime_quote_failed",
                    level=logging.INFO,
                    context={
                        "symbol": stock_code,
                        "provider": getattr(fetcher, "name", source),
                    },
                )
                errors.append(error_msg)
                if primary_quote is None:
                    failed_sources.append(source)
                else:
                    _field_trust.record_provider_attempt(
                        primary_quote,
                        provider=source,
                        status=_field_trust.PROVIDER_STATUS_FAILED,
                        role=_field_trust.PROVIDER_ROLE_ATTEMPTED,
                        stock_code=stock_code,
                    )
                continue

        # Return primary even if some fields are still missing
        if primary_quote is not None:
            _field_trust.attach_failed_sources(
                primary_quote,
                failed_sources,
                stock_code=stock_code,
            )
            return self._enrich_realtime_quote(
                primary_quote,
                fallback_from=primary_fallback_from,
                realtime_cache_ttl=getattr(config, "realtime_cache_ttl", None),
            )

        plugin_quote, plugin_name = self._try_plugin_realtime_quote(
            stock_code,
            "cn",
        )
        if plugin_quote is not None:
            _field_trust.attach_failed_sources(
                plugin_quote,
                failed_sources,
                stock_code=stock_code,
            )
            logger.info(
                "Realtime quote plugin fallback succeeded "
                "market=cn symbol=%s provider=%s",
                stock_code,
                plugin_name,
            )
            return self._enrich_realtime_quote(
                plugin_quote,
                fallback_from=failed_sources[0] if failed_sources else None,
                realtime_cache_ttl=getattr(config, "realtime_cache_ttl", None),
            )

        # Return None (fallback) when all data sources fail
        if log_final_failure:
            if errors:
                logger.info(
                    "All realtime quote providers failed symbol=%s failure_count=%d",
                    stock_code,
                    len(errors),
                )
            else:
                logger.info(f"[实时行情] {stock_code} 无可用数据源")

        return None

    @classmethod
    def _quote_needs_supplement(cls, quote) -> bool:
        """Check if any key supplementary field is still None."""
        for f in cls._SUPPLEMENT_FIELDS:
            if getattr(quote, f, None) is None:
                return True
        return False

    @classmethod
    def _merge_quote_fields(cls, primary, secondary) -> list:
        """
        Copy non-None fields from *secondary* into *primary* where
        *primary* has None. Returns list of field names that were filled.
        """
        filled = []
        for f in cls._SUPPLEMENT_FIELDS:
            if getattr(primary, f, None) is None:
                val = getattr(secondary, f, None)
                if val is not None:
                    setattr(primary, f, val)
                    filled.append(f)
        # Issue #1129: attribute supplemented fields to their actual provider.
        _field_trust.record_supplement(primary, filled, secondary)
        return filled

    def _longbridge_preferred(self, capability: str = "realtime_quote") -> bool:
        """Return True when Longbridge keys are configured and available.

        When True, non-A-share routing (US & HK) uses Longbridge as the
        primary data source with Yfinance/AkShare as fallback.
        """
        return self._get_fetcher_by_name(
            "LongbridgeFetcher",
            capability=capability,
        ) is not None

    def _supplement_from_longbridge(
        self,
        stock_code: str,
        primary_quote: Optional[UnifiedRealtimeQuote],
    ) -> Optional[UnifiedRealtimeQuote]:
        """Shortcut kept for backward-compat with A-share general loop."""
        return self._supplement_quote(stock_code, primary_quote, "LongbridgeFetcher")


EXPECTED_REALTIME_QUOTE_METHOD_NAMES = (
    "_utc_now_iso",
    "_parse_realtime_timestamp",
    "_enrich_realtime_quote",
    "_try_plugin_realtime_quote",
    "get_realtime_quote",
    "_quote_needs_supplement",
    "_merge_quote_fields",
    "_longbridge_preferred",
    "_supplement_from_longbridge",
)


def bind_realtime_quote_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind realtime quote descriptors without changing the manager API."""

    bound_names = []
    for name, descriptor in vars(_RealtimeQuoteMethods).items():
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
