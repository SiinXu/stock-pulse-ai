# -*- coding: utf-8 -*-
"""Idempotent final-exit validation wrappers for ``DataFetcherManager``.

Daily and realtime provider candidates are validated inside the manager's
bounded provider loop. These wrappers cover cache/facade exits and never
mislabel outer-layer quote degradation as provider failover. Fundamental
upper-layer rejection is a separate, explicit configuration mode.
"""

from __future__ import annotations

import logging
from functools import wraps
from threading import RLock
from typing import Any, Callable, Dict, Optional, Type

from src.utils.sanitize import log_safe_exception


logger = logging.getLogger(__name__)

_WRAPPED_TOKEN_ATTR = "_stockpulse_data_validation_wrapper_token"
_WRAPPED_ORIGINAL_ATTR = "_stockpulse_data_validation_original"
_SUBCLASS_HOOK_TOKEN_ATTR = "_stockpulse_data_validation_subclass_hook_token"
_SUBCLASS_HOOK_ORIGINAL_ATTR = "_stockpulse_data_validation_subclass_hook_original"
_INSTALL_TOKEN = object()
_INSTALL_LOCK = RLock()

_EXIT_METHODS = (
    "get_daily_data",
    "get_realtime_quote",
    "get_fundamental_context",
)


def _infer_market_from_code(stock_code: Optional[str]) -> str:
    try:
        from data_provider.symbol_normalization import _market_tag, normalize_stock_code

        return _market_tag(normalize_stock_code(str(stock_code or "")))
    except (ImportError, TypeError, ValueError):
        return "unknown"


def _wrap_get_daily_data(original: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(original)
    def wrapped(self: Any, stock_code: str, *args: Any, **kwargs: Any) -> Any:
        result = original(self, stock_code, *args, **kwargs)
        try:
            from data_provider.data_validation import is_validation_enabled

            if not is_validation_enabled():
                return result
            frame = result[0] if isinstance(result, tuple) and result else result
            attrs = getattr(frame, "attrs", None)
            if not (isinstance(attrs, dict) and isinstance(attrs.get("data_validation"), dict)):
                from data_provider.data_validation import validate_and_annotate

                provider = (
                    str(result[1])
                    if isinstance(result, tuple) and len(result) > 1 and result[1]
                    else "cache_or_final_exit"
                )
                validate_and_annotate(
                    result,
                    data_type="daily_data",
                    market=_infer_market_from_code(stock_code),
                    stock_code=stock_code,
                    provider=provider,
                    strict=False,
                )
        except Exception as exc:  # broad-exception: fallback_recorded - final-exit evidence is fail-open
            log_safe_exception(
                logger,
                "Data validation daily final-exit observation failed",
                exc,
                error_code="data_validation_final_exit_failed",
                level=logging.WARNING,
                context={"data_type": "daily_data"},
            )
        return result

    return wrapped


def _wrap_get_realtime_quote(original: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(original)
    def wrapped(self: Any, stock_code: str, *args: Any, **kwargs: Any) -> Any:
        result = original(self, stock_code, *args, **kwargs)
        if result is None:
            return None
        try:
            from data_provider.data_validation import (
                is_validation_enabled,
                validate_and_annotate,
            )

            if not is_validation_enabled():
                return result
            source = getattr(result, "source", None)
            provider = getattr(source, "value", source)
            validate_and_annotate(
                result,
                data_type="realtime_quote",
                market=_infer_market_from_code(stock_code),
                stock_code=stock_code,
                provider=str(provider or "final_exit"),
                instrument_type=getattr(result, "instrument_type", None),
                strict=False,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - final-exit evidence is fail-open
            log_safe_exception(
                logger,
                "Data validation realtime final-exit observation failed",
                exc,
                error_code="data_validation_final_exit_failed",
                level=logging.WARNING,
                context={"data_type": "realtime_quote"},
            )
        return result

    return wrapped


def _wrap_get_fundamental_context(original: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(original)
    def wrapped(self: Any, stock_code: str, *args: Any, **kwargs: Any) -> Any:
        result = original(self, stock_code, *args, **kwargs)
        try:
            from data_provider.data_validation import (
                DataValidationRejected,
                is_validation_enabled,
                upper_layer_rejection_enabled,
                validate_and_annotate,
            )

            if not is_validation_enabled():
                return result
            market = result.get("market") if isinstance(result, dict) else None
            validate_and_annotate(
                result,
                data_type="fundamental_context",
                market=market or _infer_market_from_code(stock_code),
                stock_code=stock_code,
                provider="fundamental_pipeline",
                strict=upper_layer_rejection_enabled(),
            )
        except DataValidationRejected:
            raise
        except Exception as exc:  # broad-exception: fallback_recorded - optional upper evidence is fail-open
            log_safe_exception(
                logger,
                "Data validation fundamental final-exit observation failed",
                exc,
                error_code="data_validation_final_exit_failed",
                level=logging.WARNING,
                context={"data_type": "fundamental_context"},
            )
        return result

    return wrapped


_WRAPPERS: Dict[str, Callable[[Callable[..., Any]], Callable[..., Any]]] = {
    "get_daily_data": _wrap_get_daily_data,
    "get_realtime_quote": _wrap_get_realtime_quote,
    "get_fundamental_context": _wrap_get_fundamental_context,
}


def ensure_validation_wrappers(target_class: Type[Any]) -> bool:
    """Install each wrapper on the target class itself, once per module load.

    Per-method ownership avoids inherited class flags, covers subclass
    overrides and partial installs, and replaces wrappers after a module/facade
    reload without stacking old wrappers.
    """
    installed_or_present = False
    with _INSTALL_LOCK:
        for method_name in _EXIT_METHODS:
            local_method = target_class.__dict__.get(method_name)
            candidate = local_method or getattr(target_class, method_name, None)
            if candidate is None or not callable(candidate):
                continue
            if getattr(candidate, _WRAPPED_TOKEN_ATTR, None) is _INSTALL_TOKEN:
                installed_or_present = True
                continue
            original = getattr(candidate, _WRAPPED_ORIGINAL_ATTR, candidate)
            wrapped = _WRAPPERS[method_name](original)
            setattr(wrapped, _WRAPPED_TOKEN_ATTR, _INSTALL_TOKEN)
            setattr(wrapped, _WRAPPED_ORIGINAL_ATTR, original)
            setattr(target_class, method_name, wrapped)
            installed_or_present = True
        local_subclass_hook = target_class.__dict__.get("__init_subclass__")
        if getattr(local_subclass_hook, _SUBCLASS_HOOK_TOKEN_ATTR, None) is not _INSTALL_TOKEN:
            original_subclass_hook = getattr(
                local_subclass_hook,
                _SUBCLASS_HOOK_ORIGINAL_ATTR,
                local_subclass_hook,
            )

            @classmethod
            def validation_init_subclass(cls: Type[Any], **kwargs: Any) -> None:
                if original_subclass_hook is None:
                    super(target_class, cls).__init_subclass__(**kwargs)
                else:
                    original_subclass_hook.__get__(cls, target_class)(**kwargs)
                ensure_validation_wrappers(cls)

            setattr(validation_init_subclass, _SUBCLASS_HOOK_TOKEN_ATTR, _INSTALL_TOKEN)
            setattr(
                validation_init_subclass,
                _SUBCLASS_HOOK_ORIGINAL_ATTR,
                original_subclass_hook,
            )
            setattr(target_class, "__init_subclass__", validation_init_subclass)
            installed_or_present = True
    return installed_or_present
