# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Manager-owned money-flow orchestration rebound onto DataFetcherManager.

Extracted from ``src.data_provider.base`` behind an ADR-006 compatibility
facade. Cache lookup/store/invalidate/stats stay in
``money_flow_cache_methods``. These descriptors own ``_money_flow_timestamp``,
``get_money_flow`` routing, circuit failure/success, source_chain,
fallback_to, the stale-cache return path, and hit/miss accounting logic
that travels with ``get_money_flow``. TTL/size class attributes,
cache/circuit instance state, and hit/miss counter state remain on the
facade.
``DataFetcherManager`` remains the public import and patch surface.
"""

from __future__ import annotations

import inspect
import logging
import time
from dataclasses import replace
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
normalize_stock_code = None  # type: ignore[assignment,misc]
_market_tag = None  # type: ignore[assignment,misc]
record_provider_run = None  # type: ignore[assignment,misc]
record_provider_run_started = None  # type: ignore[assignment,misc]
summarize_exception = None  # type: ignore[assignment,misc]

logger = logging.getLogger("src.data_provider.base")

# ``importlib.reload`` retains a module dictionary. Preserve the callback
# installed by the loaded compatibility facade so an owner reload can
# atomically rebuild and rebind both sides of the seam.
_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)


class _MoneyFlowMethods:
    """Source descriptors rebound onto ``DataFetcherManager`` by its facade."""

    @staticmethod
    def _money_flow_timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    def get_money_flow(self, stock_code: str, days: int = 5):
        """Return an explicit, provenance-bearing money-flow provider outcome.

        Feature gating belongs to the composition service. This manager always
        executes its capability contract when called directly.
        """
        from src.core.trading_calendar import get_effective_trading_date
        from .money_flow_types import (
            MoneyFlowOutcome,
            MoneyFlowSnapshot,
            MoneyFlowStatus,
            is_meaningful_money_flow,
            validate_history_days,
        )

        days = validate_history_days(days)
        market = _market_tag(stock_code)
        stock_code = normalize_stock_code(stock_code)
        fetched_at = self._money_flow_timestamp()
        if market != "cn":
            return MoneyFlowOutcome(
                status=MoneyFlowStatus.NOT_SUPPORTED,
                code=stock_code,
                market=market,
                requested_days=days,
                fetched_at=fetched_at,
                error_code="money_flow_market_not_supported",
            )

        candidate_fetchers = [
            fetcher
            for fetcher in self._get_fetchers_for_capability("money_flow", market=market)
            if callable(getattr(fetcher, "get_money_flow", None))
        ]
        if not candidate_fetchers:
            return MoneyFlowOutcome(
                status=MoneyFlowStatus.NOT_SUPPORTED,
                code=stock_code,
                market=market,
                requested_days=days,
                fetched_at=fetched_at,
                error_code="money_flow_capability_missing",
            )

        effective_date = get_effective_trading_date("cn")
        route_identity = tuple(
            (
                fetcher.name,
                getattr(fetcher, "money_flow_calibration_identity", "provider_declared"),
            )
            for fetcher in candidate_fetchers
        )
        cache_key = (
            stock_code,
            market,
            effective_date.isoformat(),
            days,
            route_identity,
        )
        cached = self._money_flow_cache_lookup(cache_key)
        if cached is not None:
            with self._money_flow_cache_lock:
                self._money_flow_cache_hits += 1
            return replace(cached, cache_state="fresh")
        with self._money_flow_cache_lock:
            self._money_flow_cache_misses += 1

        source_chain: List[Dict[str, Any]] = []
        had_empty_observation = False
        had_provider_failure = False
        for index, fetcher in enumerate(candidate_fetchers):
            fetcher_name = fetcher.name
            fallback_to = candidate_fetchers[index + 1].name if index + 1 < len(candidate_fetchers) else None
            if not self._money_flow_circuit.is_available(fetcher_name):
                had_provider_failure = True
                source_chain.append({"provider": fetcher_name, "status": "circuit_open"})
                continue
            method = getattr(fetcher, "get_money_flow")
            try:
                inspect.signature(method).bind(stock_code, days=days)
            except (TypeError, ValueError) as exc:
                had_provider_failure = True
                self._money_flow_circuit.record_failure(fetcher_name, "incompatible_signature")
                source_chain.append({
                    "provider": fetcher_name,
                    "status": "fetch_failed",
                    "error_code": "money_flow_incompatible_signature",
                })
                log_safe_exception(
                    logger,
                    "Money flow provider has an incompatible signature",
                    exc,
                    error_code="money_flow_incompatible_signature",
                    level=logging.WARNING,
                    context={"provider": fetcher_name},
                )
                continue

            attempt_start = time.time()
            try:
                record_provider_run_started(
                    data_type="money_flow", provider=fetcher_name, operation="get_money_flow"
                )
                snapshot = self._call_fetcher_method(
                    fetcher, "get_money_flow", stock_code, days=days
                )
                latency_ms = int((time.time() - attempt_start) * 1000)
                if not isinstance(snapshot, MoneyFlowSnapshot):
                    raise TypeError("provider returned an invalid money-flow contract")
                if snapshot.code != stock_code or snapshot.market != market:
                    raise ValueError("provider returned mismatched money-flow identity")
                if not is_meaningful_money_flow(snapshot):
                    had_empty_observation = True
                    self._money_flow_circuit.record_quality_failure(fetcher_name, latency_ms)
                    source_chain.append({"provider": fetcher_name, "status": "empty", "latency_ms": latency_ms})
                    record_provider_run(
                        data_type="money_flow", provider=fetcher_name,
                        operation="get_money_flow", success=False,
                        latency_ms=latency_ms, error_type="empty",
                        error_message="empty money-flow observation",
                        fallback_to=fallback_to, record_count=0,
                    )
                    continue

                provider_date = datetime.fromisoformat(snapshot.date).date()
                if provider_date > effective_date:
                    raise ValueError("provider date is later than the effective CN session")
                age_days = (effective_date - provider_date).days
                chain_entry = {
                    "provider": fetcher_name,
                    "status": "success",
                    "latency_ms": latency_ms,
                    "provider_date": snapshot.date,
                }
                source_chain.append(chain_entry)
                self._money_flow_circuit.record_success(fetcher_name, latency_ms)
                record_provider_run(
                    data_type="money_flow", provider=fetcher_name,
                    operation="get_money_flow", success=True,
                    latency_ms=latency_ms, record_count=1,
                )
                if age_days > 0:
                    status = MoneyFlowStatus.STALE
                    warnings = ["money_flow_provider_session_is_stale"]
                elif snapshot.completeness == "partial" or snapshot.unit == "unknown" or snapshot.amount_scale == "unknown":
                    status = MoneyFlowStatus.PARTIAL
                    warnings = ["money_flow_amount_scale_is_not_authoritatively_calibrated"]
                else:
                    status = MoneyFlowStatus.AVAILABLE
                    warnings = []
                outcome = MoneyFlowOutcome(
                    status=status, code=stock_code, market=market,
                    requested_days=days, fetched_at=fetched_at,
                    snapshot=snapshot, provider_date=snapshot.date,
                    age_days=age_days, source_chain=source_chain,
                    warnings=warnings,
                )
                self._money_flow_cache_store(cache_key, outcome)
                return outcome
            except Exception as exc:  # broad-exception: fallback_recorded - provider fallback is explicit in outcome
                had_provider_failure = True
                latency_ms = int((time.time() - attempt_start) * 1000)
                error_type, error_reason = summarize_exception(exc)
                self._money_flow_circuit.record_failure(fetcher_name, error_type, latency_ms)
                source_chain.append({
                    "provider": fetcher_name,
                    "status": "fetch_failed",
                    "latency_ms": latency_ms,
                    "error_code": error_type,
                })
                record_provider_run(
                    data_type="money_flow", provider=fetcher_name,
                    operation="get_money_flow", success=False,
                    latency_ms=latency_ms, error_type=error_type,
                    error_message=error_reason, fallback_to=fallback_to,
                )
                log_safe_exception(
                    logger, "Data provider money flow fetch failed", exc,
                    error_code="data_provider_money_flow_failed",
                    level=logging.WARNING,
                    context={"symbol": stock_code, "provider": fetcher_name},
                )

        stale = self._money_flow_cache_lookup(cache_key, allow_stale=True)
        if stale is not None and stale.snapshot is not None:
            stale_provider_date = datetime.fromisoformat(stale.snapshot.date).date()
            return replace(
                stale,
                status=MoneyFlowStatus.FALLBACK,
                fetched_at=fetched_at,
                age_days=max(0, (effective_date - stale_provider_date).days),
                source_chain=source_chain + stale.source_chain,
                cache_state="stale",
                fallback_from="provider_failure",
                warnings=list(stale.warnings) + ["money_flow_stale_cache_fallback"],
            )
        final_status = (
            MoneyFlowStatus.EMPTY
            if had_empty_observation and not had_provider_failure
            else MoneyFlowStatus.FETCH_FAILED
        )
        return MoneyFlowOutcome(
            status=final_status,
            code=stock_code,
            market=market,
            requested_days=days,
            fetched_at=fetched_at,
            source_chain=source_chain,
            error_code=(
                "money_flow_all_providers_empty"
                if final_status == MoneyFlowStatus.EMPTY
                else "money_flow_all_providers_failed"
            ),
        )


EXPECTED_MONEY_FLOW_METHOD_NAMES = (
    "_money_flow_timestamp",
    "get_money_flow",
)


def bind_money_flow_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind money-flow orchestration descriptors without changing the manager API."""

    bound_names = []
    for name, descriptor in vars(_MoneyFlowMethods).items():
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
