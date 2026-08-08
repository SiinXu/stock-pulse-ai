# -*- coding: utf-8 -*-
"""Manager-layer wiring for the financial data validation layer (T11 / #185).

Wraps unified exit methods on ``DataFetcherManager``:

- ``get_daily_data``
- ``get_realtime_quote``
- ``get_fundamental_context``

Default mode is warn-only (annotate + log). Strict mode
(``DATA_VALIDATION_STRICT=true``) raises ``DataValidationRejected`` on REJECT
findings so upper layers can degrade.

This module is owned by T11 (``manager_parts/``). It must not modify
``data_provider/base.py`` (T10), fetchers, ``symbol_normalization``, or
``decision_signal_data_quality``.
"""

from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable, Dict, Optional, Type

from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

_WRAPPED_FLAG = "_stockpulse_data_validation_wrapped"
_INSTALLED_ON: Dict[int, bool] = {}

_EXIT_METHODS = (
    "get_daily_data",
    "get_realtime_quote",
    "get_fundamental_context",
)


def _infer_market_from_code(stock_code: Optional[str]) -> Optional[str]:
    if not stock_code:
        return None
    try:
        from data_provider.base import _market_tag  # local import; avoid cycles

        return _market_tag(stock_code)
    except Exception:  # broad-exception: optional_metadata - market tag is best-effort context only
        text = str(stock_code).strip().lower()
        if text.startswith(("hk", "0")) and len(text) <= 7:
            return "hk"
        if text.isalpha():
            return "us"
        return "cn"


def _wrap_get_daily_data(original: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(original)
    def wrapped(self: Any, stock_code: str, *args: Any, **kwargs: Any) -> Any:
        from data_provider.data_validation import (
            DataValidationRejected,
            is_validation_enabled,
            validate_and_annotate,
        )

        result = original(self, stock_code, *args, **kwargs)
        if not is_validation_enabled():
            return result
        market = _infer_market_from_code(stock_code)
        try:
            outcome = validate_and_annotate(
                result,
                data_type="daily_data",
                market=market,
                stock_code=stock_code,
            )
            # Structured detail lives on frame.attrs["data_validation"]; keep the
            # runtime log free of exception-tainted dynamic fields.
            if not outcome.ok:
                logger.info("[data_validation] daily_data findings annotated on frame")
        except DataValidationRejected as rejected:
            log_safe_exception(
                logger,
                "data_validation daily_data rejected",
                rejected,
                error_code="data_validation_reject",
                level=logging.WARNING,
            )
            raise
        except Exception as exc:  # broad-exception: fallback_recorded - never break fetch path on validator bugs
            log_safe_exception(
                logger,
                "data_validation daily_data failed open",
                exc,
                error_code="data_validation_open",
                level=logging.WARNING,
            )
        return result

    return wrapped


def _wrap_get_realtime_quote(original: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(original)
    def wrapped(self: Any, stock_code: str, *args: Any, **kwargs: Any) -> Any:
        from data_provider.data_validation import (
            DataValidationRejected,
            is_validation_enabled,
            validate_and_annotate,
        )

        result = original(self, stock_code, *args, **kwargs)
        if result is None or not is_validation_enabled():
            return result
        market = _infer_market_from_code(stock_code)
        try:
            outcome = validate_and_annotate(
                result,
                data_type="realtime_quote",
                market=market,
                stock_code=stock_code,
            )
            if not outcome.ok:
                logger.info("[data_validation] realtime_quote findings annotated")
        except DataValidationRejected as rejected:
            # Strict mode: treat as unavailable so existing failover/None paths apply.
            log_safe_exception(
                logger,
                "data_validation realtime_quote rejected",
                rejected,
                error_code="data_validation_reject",
                level=logging.WARNING,
            )
            return None
        except Exception as exc:  # broad-exception: fallback_recorded - never break fetch path on validator bugs
            log_safe_exception(
                logger,
                "data_validation realtime_quote failed open",
                exc,
                error_code="data_validation_open",
                level=logging.WARNING,
            )
        return result

    return wrapped


def _wrap_get_fundamental_context(original: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(original)
    def wrapped(self: Any, stock_code: str, *args: Any, **kwargs: Any) -> Any:
        from data_provider.data_validation import (
            DataValidationRejected,
            is_validation_enabled,
            validate_and_annotate,
        )

        result = original(self, stock_code, *args, **kwargs)
        if not is_validation_enabled():
            return result
        market = None
        if isinstance(result, dict):
            market = result.get("market")
        market = market or _infer_market_from_code(stock_code)
        try:
            outcome = validate_and_annotate(
                result,
                data_type="fundamental_context",
                market=market,
                stock_code=stock_code,
            )
            if not outcome.ok:
                logger.info("[data_validation] fundamental_context findings annotated")
        except DataValidationRejected as rejected:
            # Strict mode: annotate reject and re-raise so callers see the failure
            # without silent data drop.
            if isinstance(result, dict):
                result["data_validation"] = dict(rejected.validation_payload)
            log_safe_exception(
                logger,
                "data_validation fundamental_context rejected",
                rejected,
                error_code="data_validation_reject",
                level=logging.WARNING,
            )
            raise
        except Exception as exc:  # broad-exception: fallback_recorded - never break fetch path on validator bugs
            log_safe_exception(
                logger,
                "data_validation fundamental_context failed open",
                exc,
                error_code="data_validation_open",
                level=logging.WARNING,
            )
        return result

    return wrapped


_WRAPPERS: Dict[str, Callable[[Callable[..., Any]], Callable[..., Any]]] = {
    "get_daily_data": _wrap_get_daily_data,
    "get_realtime_quote": _wrap_get_realtime_quote,
    "get_fundamental_context": _wrap_get_fundamental_context,
}


def ensure_validation_wrappers(target_class: Type[Any]) -> bool:
    """Idempotently wrap manager unified-exit methods.

    Returns True when wrappers were installed on this call (or already present).
    """
    class_id = id(target_class)
    if _INSTALLED_ON.get(class_id):
        return True
    if getattr(target_class, _WRAPPED_FLAG, False):
        _INSTALLED_ON[class_id] = True
        return True

    for method_name in _EXIT_METHODS:
        original = getattr(target_class, method_name, None)
        if original is None or not callable(original):
            logger.debug(
                "[data_validation] skip wrap; missing method %s on %s",
                method_name,
                target_class.__name__,
            )
            continue
        # Avoid double-wrap if another path already installed.
        if getattr(original, _WRAPPED_FLAG, False):
            continue
        wrapper_factory = _WRAPPERS[method_name]
        wrapped = wrapper_factory(original)
        setattr(wrapped, _WRAPPED_FLAG, True)
        setattr(target_class, method_name, wrapped)

    setattr(target_class, _WRAPPED_FLAG, True)
    _INSTALLED_ON[class_id] = True
    logger.debug(
        "[data_validation] installed validation wrappers on %s",
        target_class.__name__,
    )
    return True


def reset_validation_wrappers_state_for_tests() -> None:
    """Test helper: clear install bookkeeping (does not unwrap methods)."""
    _INSTALLED_ON.clear()


__all__ = [
    "ensure_validation_wrappers",
    "reset_validation_wrappers_state_for_tests",
]
