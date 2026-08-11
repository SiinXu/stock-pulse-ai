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
