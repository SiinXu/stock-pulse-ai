# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""SmartMoney money-flow service for optional analysis injection.

Network access is gated by ``config.smartmoney_enabled`` (env
``SMARTMONEY_ENABLED``, default false). When disabled, this service and the
manager entry point perform no provider I/O.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Protocol

from data_provider.money_flow_types import (
    MoneyFlowOutcome,
    MoneyFlowStatus,
    is_meaningful_money_flow,
    validate_history_days,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


class _MoneyFlowManager(Protocol):
    def get_money_flow(
        self,
        stock_code: str,
        days: int = 5,
    ) -> MoneyFlowOutcome:
        ...

    def close(self) -> None:
        ...


def is_smartmoney_enabled(config: Any = None) -> bool:
    """Return whether SmartMoney money-flow fetching is enabled.

    Prefer an injected config object. When absent, read ``SMARTMONEY_ENABLED``
    from the environment (default false) so this module never calls bare
    ``get_config()``.
    """
    if config is not None:
        value = getattr(config, "smartmoney_enabled", False)
        if not isinstance(value, bool):
            raise TypeError("smartmoney_enabled must be a boolean")
        return value
    raw = os.getenv("SMARTMONEY_ENABLED", "false").strip().lower()
    if raw in {"true", "1", "yes", "on"}:
        return True
    if raw in {"false", "0", "no", "off", ""}:
        return False
    raise ValueError("SMARTMONEY_ENABLED must be a boolean value")


def fetch_money_flow(
    stock_code: str,
    *,
    manager: Optional[_MoneyFlowManager] = None,
    days: int = 5,
    config: Any = None,
) -> Optional[MoneyFlowOutcome]:
    """Fetch one typed outcome; disabled execution remains a zero-I/O omission."""
    days = validate_history_days(days)
    if not is_smartmoney_enabled(config):
        logger.debug(
            "[smartmoney] disabled; skip money flow for %s",
            stock_code,
        )
        return None

    owned_manager = manager is None
    if owned_manager:
        try:
            from data_provider.base import DataFetcherManager

            manager = DataFetcherManager()
        except Exception as exc:  # broad-exception: fallback_recorded - manager init fail-open
            log_safe_exception(
                logger,
                "SmartMoney manager init failed",
                exc,
                error_code="smartmoney_manager_init_failed",
                level=logging.WARNING,
                context={"symbol": stock_code},
            )
            from data_provider.base import _market_tag, normalize_stock_code

            return MoneyFlowOutcome(
                status=MoneyFlowStatus.FETCH_FAILED,
                code=normalize_stock_code(stock_code),
                market=_market_tag(stock_code),
                requested_days=days,
                fetched_at=datetime.now(timezone.utc).isoformat(),
                error_code="smartmoney_manager_init_failed",
            )

    try:
        outcome = manager.get_money_flow(stock_code, days=days)
    except Exception as exc:  # broad-exception: fallback_recorded - money flow fail-open
        log_safe_exception(
            logger,
            "SmartMoney money flow fetch failed",
            exc,
            error_code="smartmoney_money_flow_failed",
            level=logging.WARNING,
            context={"symbol": stock_code},
        )
        from data_provider.base import _market_tag, normalize_stock_code

        return MoneyFlowOutcome(
            status=MoneyFlowStatus.FETCH_FAILED,
            code=normalize_stock_code(stock_code),
            market=_market_tag(stock_code),
            requested_days=days,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            error_code="smartmoney_money_flow_failed",
        )
    finally:
        if owned_manager and manager is not None:
            try:
                manager.close()
            except Exception as exc:  # broad-exception: fallback_recorded - best-effort owned cleanup
                log_safe_exception(
                    logger,
                    "SmartMoney manager close failed",
                    exc,
                    error_code="smartmoney_manager_close_failed",
                    level=logging.DEBUG,
                    context={"symbol": stock_code},
                )

    if not isinstance(outcome, MoneyFlowOutcome):
        raise TypeError("money-flow manager returned an invalid outcome contract")
    return outcome


def money_flow_to_context(outcome: Optional[MoneyFlowOutcome]) -> Optional[Dict[str, Any]]:
    """Project an explicit outcome without erasing failure or quality state."""
    if outcome is None:
        return None
    if not isinstance(outcome, MoneyFlowOutcome):
        raise TypeError("money-flow context requires MoneyFlowOutcome")
    payload = outcome.to_dict()
    if is_meaningful_money_flow(outcome) and outcome.snapshot is not None:
        payload["snapshot"]["attitude"] = outcome.snapshot.attitude()
        payload["snapshot"]["calibration_note"] = (
            "Order-size buckets follow bucket_definition; absolute amounts are "
            "omitted unless source currency and scale are authoritatively calibrated."
        )
    return payload


MONEY_FLOW_VIEW_SCHEMA_VERSION = "money_flow_view/1.0"
MONEY_FLOW_VIEW_DISCLAIMER = (
    "Research evidence only: order-size bucket net ratios are not institutional "
    "ownership, Northbound flow, or a prediction of future prices. Absolute "
    "amounts appear only when the provider calibrates currency and scale."
)


def _bounded_text(value: Any, max_length: int) -> Optional[str]:
    if type(value) is not str:
        return None
    text = value.strip()
    if not text:
        return None
    return text[:max_length]


def _project_source_chain(value: Any) -> list[Dict[str, Any]]:
    """Expose only the bounded provider-attempt contract used by the UI."""
    if not isinstance(value, list):
        return []
    projected: list[Dict[str, Any]] = []
    for item in value[:16]:
        if not isinstance(item, dict):
            continue
        provider = _bounded_text(item.get("provider") or item.get("source"), 160)
        status = _bounded_text(item.get("status"), 64)
        if provider is None or status is None:
            continue
        attempt: Dict[str, Any] = {"provider": provider, "status": status}
        for key in ("latency_ms", "provider_date", "error_code"):
            if item.get(key) is not None:
                attempt[key] = item[key]
        projected.append(attempt)
    return projected


def _project_warnings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    warnings = [
        text
        for item in value
        if (text := _bounded_text(item, 200)) is not None
    ]
    if len(warnings) <= 16:
        return warnings
    return warnings[:15] + ["money_flow_warnings_truncated"]


def build_money_flow_view(
    stock_code: str,
    *,
    days: int = 5,
    manager: Optional[_MoneyFlowManager] = None,
    config: Any = None,
) -> Dict[str, Any]:
    """Build a user-facing money-flow view with explicit gate and degradation.

    When SmartMoney is disabled this returns ``status=disabled`` with zero
    provider I/O. When enabled it reuses ``fetch_money_flow`` and projects
    provenance (as-of, source, warnings) without inventing numbers.
    """
    code = str(stock_code or "").strip()
    if not code:
        raise ValueError("stock_code is required")
    days = validate_history_days(days)
    base: Dict[str, Any] = {
        "schema_version": MONEY_FLOW_VIEW_SCHEMA_VERSION,
        "stock_code": code,
        "enabled": False,
        "status": "disabled",
        "requested_days": days,
        "fetched_at": None,
        "as_of": None,
        "provider_date": None,
        "age_days": None,
        "source": None,
        "source_chain": [],
        "market": None,
        "error_code": None,
        "warnings": [],
        "cache_state": None,
        "fallback_from": None,
        "snapshot": None,
        "message": None,
        "disclaimer": MONEY_FLOW_VIEW_DISCLAIMER,
    }

    if not is_smartmoney_enabled(config):
        base["message"] = (
            "SmartMoney money-flow is disabled (SMARTMONEY_ENABLED is false). "
            "Enable it in system settings or environment to fetch main-force "
            "order-size bucket evidence."
        )
        return base

    base["enabled"] = True
    outcome = fetch_money_flow(
        code, manager=manager, days=days, config=config
    )
    if outcome is None:
        # Gate was true but fetch returned omission — treat as explicit miss.
        base["status"] = "empty"
        base["error_code"] = "money_flow_missing"
        base["message"] = "Money-flow outcome was not produced."
        return base

    context = money_flow_to_context(outcome)
    if not isinstance(context, dict):
        raise TypeError("money-flow view requires a projected outcome dict")

    snapshot = context.get("snapshot")
    snapshot = dict(snapshot) if isinstance(snapshot, dict) else None
    source_chain = _project_source_chain(context.get("source_chain"))
    source = None
    if snapshot and snapshot.get("source"):
        source = str(snapshot.get("source"))
    elif source_chain:
        first = source_chain[0] if source_chain else None
        if isinstance(first, dict):
            provider = first.get("provider") or first.get("source")
            if provider is not None:
                source = str(provider)

    as_of = None
    if snapshot and snapshot.get("as_of"):
        as_of = str(snapshot.get("as_of"))
    elif context.get("fetched_at"):
        as_of = str(context.get("fetched_at"))

    status = str(context.get("status") or "empty")
    base.update(
        {
            "stock_code": str(context.get("code") or code),
            "status": status,
            "requested_days": int(context.get("requested_days") or days),
            "fetched_at": context.get("fetched_at"),
            "as_of": as_of,
            "provider_date": context.get("provider_date"),
            "age_days": context.get("age_days"),
            "source": source,
            "source_chain": source_chain,
            "market": context.get("market"),
            "error_code": context.get("error_code"),
            "warnings": _project_warnings(context.get("warnings")),
            "cache_state": context.get("cache_state"),
            "fallback_from": _bounded_text(context.get("fallback_from"), 160),
            "snapshot": snapshot,
        }
    )
    if snapshot is not None:
        snapshot.pop("raw_field_map", None)
    if status in {"not_supported", "fetch_failed", "empty"}:
        reason = base.get("error_code") or status
        base["message"] = f"Money-flow data unavailable ({reason})."
    elif status in {"stale", "fallback", "partial"}:
        base["message"] = (
            f"Money-flow data is degraded (status={status}); treat as supporting "
            "evidence only."
        )
    else:
        base["message"] = None
    return base
