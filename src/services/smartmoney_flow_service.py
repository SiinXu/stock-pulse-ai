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
from typing import Any, Dict, Optional, Protocol

from data_provider.money_flow_types import MoneyFlowSnapshot, is_meaningful_money_flow
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


class _MoneyFlowManager(Protocol):
    def get_money_flow(
        self,
        stock_code: str,
        days: int = 5,
    ) -> Optional[MoneyFlowSnapshot]:
        ...


def is_smartmoney_enabled(config: Any = None) -> bool:
    """Return whether SmartMoney money-flow fetching is enabled.

    Prefer an injected config object. When absent, read ``SMARTMONEY_ENABLED``
    from the environment (default false) so this module never calls bare
    ``get_config()``.
    """
    if config is not None:
        return bool(getattr(config, "smartmoney_enabled", False))
    return os.getenv("SMARTMONEY_ENABLED", "false").lower() == "true"


def fetch_money_flow(
    stock_code: str,
    *,
    manager: Optional[_MoneyFlowManager] = None,
    days: int = 5,
    config: Any = None,
) -> Optional[MoneyFlowSnapshot]:
    """Fetch normalized money flow for one stock; fail-open to None."""
    if not is_smartmoney_enabled(config):
        logger.debug(
            "[smartmoney] disabled; skip money flow for %s",
            stock_code,
        )
        return None

    if manager is None:
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
            return None

    try:
        snapshot = manager.get_money_flow(stock_code, days=days)
    except Exception as exc:  # broad-exception: fallback_recorded - money flow fail-open
        log_safe_exception(
            logger,
            "SmartMoney money flow fetch failed",
            exc,
            error_code="smartmoney_money_flow_failed",
            level=logging.WARNING,
            context={"symbol": stock_code},
        )
        return None

    if not is_meaningful_money_flow(snapshot):
        return None
    return snapshot


def money_flow_to_context(snapshot: Optional[MoneyFlowSnapshot]) -> Optional[Dict[str, Any]]:
    """Project a snapshot into analysis-context friendly fields."""
    if not is_meaningful_money_flow(snapshot):
        return None
    assert snapshot is not None
    payload = snapshot.to_dict()
    payload["attitude"] = snapshot.attitude()
    # Surface calibration explicitly so prompts do not invent cross-source math.
    payload["calibration_note"] = (
        "Order-size buckets follow the source bucket_definition; "
        "do not mix values across providers without recalibration."
    )
    return payload
