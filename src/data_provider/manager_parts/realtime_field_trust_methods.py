# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Realtime quote attempt and field-trust manager methods.

These descriptors are rebound onto ``DataFetcherManager`` by the compatibility
facade. Keeping them here prevents field-trust bookkeeping from growing the
already-large realtime routing implementation in ``src.data_provider.base``.
"""

from __future__ import annotations

import logging
import time
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

from .. import field_trust as _field_trust
from ..errors import summarize_exception
from ..realtime_types import UnifiedRealtimeQuote
from ..symbol_normalization import _market_tag, normalize_stock_code
from .daily_cache_methods import _clone_facade_descriptor, _descriptor_function

# Facade-only symbols cannot be imported from ``src.data_provider.base`` while
# that module is still assembling this part (circular import). Declare anchors
# so flake8 F821 is clean; rebound methods resolve the real objects from the
# ``src.data_provider.base`` global namespace.
DataProvider = None  # type: ignore[assignment,misc]
record_provider_run = None  # type: ignore[assignment,misc]
record_provider_run_started = None  # type: ignore[assignment,misc]

logger = logging.getLogger("src.data_provider.base")

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)


class _RealtimeFieldTrustMethods:
    """Source descriptors rebound onto ``DataFetcherManager`` by its facade."""

    @staticmethod
    def _realtime_fetcher_token(fetcher_name: str, **kw) -> str:
        source = kw.get("source")
        if fetcher_name == "AkshareFetcher":
            if source == "hk":
                return "akshare_hk"
            if source == "tencent":
                return "tencent"
            if source == "sina":
                return "akshare_sina"
            if source == "em":
                return "akshare_em"
            return "akshare"
        mapping = {
            "LongbridgeFetcher": "longbridge",
            "YfinanceFetcher": "yfinance",
            "FinnhubFetcher": "finnhub",
            "AlphaVantageFetcher": "alphavantage",
            "EfinanceFetcher": "efinance",
            "TushareFetcher": "tushare",
            "TickFlowFetcher": "tickflow",
        }
        return mapping.get(fetcher_name, fetcher_name.replace("Fetcher", "").lower())

    def _plugin_registration_token(self, fetcher: Optional[DataProvider]) -> Optional[str]:
        if fetcher is None:
            return None
        resolver = getattr(self, "_provider_plugin_registration", None)
        if not callable(resolver):
            return None
        try:
            registration = resolver(fetcher)
        except Exception as exc:  # broad-exception: fallback_recorded - plugin identity is optional for trust
            log_safe_exception(
                logger,
                "Plugin registration identity unavailable",
                exc,
                error_code="field_trust_plugin_registration_token_failed",
                level=logging.DEBUG,
            )
            return None
        provider_id = getattr(registration, "provider_id", None)
        if isinstance(provider_id, str) and provider_id.strip():
            return provider_id.strip()
        return None

    def _attempt_provider_token(
        self,
        fetcher_name: str,
        *,
        fetcher: Optional[DataProvider] = None,
        quote: Any = None,
        **kw: Any,
    ) -> str:
        """Resolve the public attempt identity for one fetcher try."""
        if quote is not None:
            token = _field_trust.resolve_source_token(getattr(quote, "source", None))
            if _field_trust.is_concrete_source_token(token):
                return str(token)
        plugin_id = self._plugin_registration_token(fetcher)
        if plugin_id:
            return plugin_id
        name = getattr(fetcher, "name", None) or fetcher_name
        return self._realtime_fetcher_token(str(name), **kw)

    def _realtime_circuit_key(
        self,
        fetcher_name: str,
        *,
        fetcher: Optional[DataProvider] = None,
        quote: Any = None,
        stock_code: Optional[str] = None,
        **kw: Any,
    ) -> Optional[str]:
        """Resolve the exact circuit identity for one fetcher try."""
        token = self._attempt_provider_token(
            fetcher_name,
            fetcher=fetcher,
            quote=quote,
            **kw,
        )
        return _field_trust.derive_circuit_key(
            token,
            stock_code=stock_code or getattr(quote, "code", None),
            source=kw.get("source"),
            quote=quote,
            circuit_key=_field_trust.quote_circuit_key(quote),
        )

    @staticmethod
    def _attach_prior_attempts(
        quote: Any,
        attempts: Optional[List[Any]],
    ) -> None:
        for item in attempts or []:
            if isinstance(item, dict):
                provider = item.get("provider")
                status = item.get("status") or _field_trust.PROVIDER_STATUS_EMPTY
                circuit_key = item.get("circuit_key")
            elif isinstance(item, (tuple, list)) and item:
                provider = item[0]
                status = (
                    item[1]
                    if len(item) > 1
                    else _field_trust.PROVIDER_STATUS_EMPTY
                )
                circuit_key = item[2] if len(item) > 2 else None
            else:
                continue
            if not provider:
                continue
            _field_trust.record_provider_attempt(
                quote,
                provider=provider,
                status=status,
                role=_field_trust.PROVIDER_ROLE_ATTEMPTED,
                circuit_key=circuit_key,
                stock_code=getattr(quote, "code", None),
            )

    @staticmethod
    def _sink_non_ok(
        sink: Optional[_field_trust.QuoteAttemptSink],
        fallback_token: str,
        fallback_circuit_key: Optional[str] = None,
    ) -> Dict[str, str]:
        snapshot = sink.snapshot() if sink is not None else None
        if not snapshot:
            result = {
                "provider": fallback_token,
                "status": _field_trust.PROVIDER_STATUS_EMPTY,
            }
            if fallback_circuit_key:
                result["circuit_key"] = fallback_circuit_key
            return result
        result = {
            "provider": snapshot.get("provider") or fallback_token,
            "status": snapshot.get("status") or _field_trust.PROVIDER_STATUS_EMPTY,
        }
        circuit_key = snapshot.get("circuit_key") or fallback_circuit_key
        if circuit_key:
            result["circuit_key"] = circuit_key
        return result

    def _try_fetcher_quote(
        self,
        stock_code: str,
        fetcher_name: str,
        *,
        _selected_fetcher: Optional[DataProvider] = None,
        _attempt_sink: Optional[_field_trust.QuoteAttemptSink] = None,
        **kw,
    ):
        """Return one valid quote and optionally record the attempt outcome."""
        fetcher = _selected_fetcher
        if fetcher is None:
            fetcher = self._get_fetcher_by_name(
                fetcher_name,
                capability="realtime_quote",
            )
        elif not self._is_fetcher_available(
            fetcher,
            capability="realtime_quote",
        ):
            fetcher = None
        if fetcher is None or not hasattr(fetcher, "get_realtime_quote"):
            if _attempt_sink is not None:
                token = self._attempt_provider_token(fetcher_name, **kw)
                _attempt_sink.record(
                    token,
                    _field_trust.PROVIDER_STATUS_UNAVAILABLE,
                    circuit_key=self._realtime_circuit_key(
                        fetcher_name,
                        stock_code=stock_code,
                        **kw,
                    ),
                )
            record_provider_run(
                data_type="realtime_quote",
                provider=fetcher_name,
                operation="get_realtime_quote",
                success=False,
                error_type="unavailable",
                error_message="fetcher unavailable",
            )
            return None
        attempt_start = time.time()
        try:
            record_provider_run_started(
                data_type="realtime_quote",
                provider=fetcher.name,
                operation="get_realtime_quote",
            )
            quote = self._call_fetcher_method(
                fetcher,
                "get_realtime_quote",
                stock_code,
                **kw,
            )
            if quote is not None and quote.has_basic_data():
                circuit_key = self._realtime_circuit_key(
                    fetcher.name,
                    fetcher=fetcher,
                    quote=quote,
                    stock_code=stock_code,
                    **kw,
                )
                if circuit_key and not _field_trust.quote_circuit_key(quote):
                    _field_trust.set_quote_circuit_key(quote, circuit_key)
                if _attempt_sink is not None:
                    _attempt_sink.record(
                        self._attempt_provider_token(
                            fetcher.name,
                            fetcher=fetcher,
                            quote=quote,
                            **kw,
                        ),
                        _field_trust.PROVIDER_STATUS_OK,
                        circuit_key=circuit_key or _field_trust.quote_circuit_key(quote),
                    )
                record_provider_run(
                    data_type="realtime_quote",
                    provider=fetcher.name,
                    operation="get_realtime_quote",
                    success=True,
                    latency_ms=int((time.time() - attempt_start) * 1000),
                    record_count=1,
                )
                return quote
            if _attempt_sink is not None:
                _attempt_sink.record(
                    self._attempt_provider_token(
                        fetcher.name,
                        fetcher=fetcher,
                        **kw,
                    ),
                    _field_trust.PROVIDER_STATUS_EMPTY,
                    circuit_key=self._realtime_circuit_key(
                        fetcher.name,
                        fetcher=fetcher,
                        stock_code=stock_code,
                        **kw,
                    ),
                )
            record_provider_run(
                data_type="realtime_quote",
                provider=fetcher.name,
                operation="get_realtime_quote",
                success=False,
                latency_ms=int((time.time() - attempt_start) * 1000),
                error_type="empty",
                error_message="empty or incomplete quote",
                record_count=0,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - diagnostics precede realtime fallback
            if _attempt_sink is not None:
                _attempt_sink.record(
                    self._attempt_provider_token(
                        fetcher.name,
                        fetcher=fetcher,
                        **kw,
                    ),
                    _field_trust.PROVIDER_STATUS_FAILED,
                    circuit_key=self._realtime_circuit_key(
                        fetcher.name,
                        fetcher=fetcher,
                        stock_code=stock_code,
                        **kw,
                    ),
                )
            error_type, error_reason = summarize_exception(exc)
            record_provider_run(
                data_type="realtime_quote",
                provider=fetcher.name,
                operation="get_realtime_quote",
                success=False,
                latency_ms=int((time.time() - attempt_start) * 1000),
                error_type=error_type,
                error_message=error_reason,
            )
            log_safe_exception(
                logger,
                "Data provider realtime quote failed",
                exc,
                error_code="data_provider_realtime_quote_failed",
                level=logging.DEBUG,
                context={"symbol": stock_code, "provider": fetcher_name},
            )
        return None

    def _supplement_quote(
        self,
        stock_code: str,
        primary_quote: Optional[UnifiedRealtimeQuote],
        fetcher_name: str,
        *,
        _failed_attempts: Optional[List[Any]] = None,
        **kw: str,
    ) -> Optional[UnifiedRealtimeQuote]:
        """Fill missing fields or use the named fetcher as a sole source."""
        fallback_token = self._realtime_fetcher_token(fetcher_name, **kw)
        fallback_circuit_key = self._realtime_circuit_key(
            fetcher_name,
            stock_code=stock_code,
            **kw,
        )
        if primary_quote is not None:
            if not self._quote_needs_supplement(primary_quote):
                return primary_quote
            try:
                attempt_sink = _field_trust.QuoteAttemptSink()
                secondary = self._try_fetcher_quote(
                    stock_code,
                    fetcher_name,
                    _attempt_sink=attempt_sink,
                    **kw,
                )
                if secondary is None:
                    snapshot = self._sink_non_ok(
                        attempt_sink,
                        fallback_token,
                        fallback_circuit_key,
                    )
                    _field_trust.record_provider_attempt(
                        primary_quote,
                        provider=snapshot.get("provider") or fallback_token,
                        status=snapshot.get("status")
                        or _field_trust.PROVIDER_STATUS_EMPTY,
                        role=_field_trust.PROVIDER_ROLE_ATTEMPTED,
                        circuit_key=snapshot.get("circuit_key") or fallback_circuit_key,
                        stock_code=stock_code,
                    )
                else:
                    _field_trust.observe_cross_source_quotes(
                        primary_quote,
                        secondary,
                        stock_code=stock_code,
                        market=_market_tag(normalize_stock_code(stock_code)),
                        primary_candidates=(getattr(primary_quote, "source", None),),
                        secondary_candidates=(
                            getattr(secondary, "source", None),
                            fallback_token,
                            fetcher_name,
                        ),
                        asset_type=getattr(primary_quote, "instrument_type", None),
                    )
                    filled = self._merge_quote_fields(primary_quote, secondary)
                    if filled:
                        logger.info(
                            "[realtime quote] %s supplemented from %s: %s",
                            stock_code,
                            fetcher_name,
                            filled,
                        )
            except Exception as exc:  # broad-exception: fallback_recorded - safe log preserves the primary quote
                log_safe_exception(
                    logger,
                    "Realtime quote supplement failed",
                    exc,
                    error_code="realtime_quote_supplement_failed",
                    level=logging.DEBUG,
                    context={"symbol": stock_code, "provider": fetcher_name},
                )
                _field_trust.record_provider_attempt(
                    primary_quote,
                    provider=fallback_token,
                    status=_field_trust.PROVIDER_STATUS_FAILED,
                    role=_field_trust.PROVIDER_ROLE_ATTEMPTED,
                    circuit_key=fallback_circuit_key,
                    stock_code=stock_code,
                )
            return primary_quote

        attempt_sink = _field_trust.QuoteAttemptSink()
        quote = self._try_fetcher_quote(
            stock_code,
            fetcher_name,
            _attempt_sink=attempt_sink,
            **kw,
        )
        if quote is not None:
            logger.info(
                "[realtime quote] %s fetched from sole source %s",
                stock_code,
                fetcher_name,
            )
            return quote
        if _failed_attempts is not None:
            _failed_attempts.append(
                self._sink_non_ok(
                    attempt_sink,
                    fallback_token,
                    fallback_circuit_key,
                )
            )
        return None


EXPECTED_REALTIME_FIELD_TRUST_METHOD_NAMES = (
    "_realtime_fetcher_token",
    "_plugin_registration_token",
    "_attempt_provider_token",
    "_realtime_circuit_key",
    "_attach_prior_attempts",
    "_sink_non_ok",
    "_try_fetcher_quote",
    "_supplement_quote",
)


def bind_realtime_field_trust_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind realtime trust descriptors without changing the manager API."""
    bound_names = []
    for name, descriptor in vars(_RealtimeFieldTrustMethods).items():
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
    hook = _FACADE_RELOAD_HOOK
    if hook is not None:
        hook()


_rebind_loaded_facade()
