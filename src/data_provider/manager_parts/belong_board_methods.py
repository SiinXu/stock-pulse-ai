# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Manager-owned belong-board helpers and routing rebound onto DataFetcherManager.

Extracted from ``src.data_provider.base`` behind an ADR-006 compatibility
facade. These descriptors own missing-value / normalization helpers
(``_try_scalar_isna``, ``_is_missing_board_value``,
``_normalize_belong_boards``) and ``get_belong_boards`` routing,
capability probing, and provider fallback. Fundamental payload helpers
that only *call* ``_try_scalar_isna`` stay on the facade.
``DataFetcherManager`` remains the public import and patch surface.
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

import numpy as np
import pandas as pd

from src.utils.sanitize import log_safe_exception

from .daily_cache_methods import _clone_facade_descriptor, _descriptor_function

# Facade-only symbols cannot be imported from ``src.data_provider.base`` while
# that module is still assembling this part (circular import). Declare anchors
# so flake8 F821 is clean; rebound methods resolve the real objects from the
# ``src.data_provider.base`` global namespace.
DataFetcherManager = None  # type: ignore[assignment,misc]
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


class _BelongBoardMethods:
    """Source descriptors rebound onto ``DataFetcherManager`` by its facade."""

    @staticmethod
    def _try_scalar_isna(value: Any, context: str) -> Optional[bool]:
        """Return scalar ``pd.isna`` result, or ``None`` when callers should use fallback logic."""
        if isinstance(value, (dict, list, tuple, set, pd.DataFrame, pd.Series, pd.Index)):
            return None

        if isinstance(value, np.ndarray):
            if value.ndim != 0:
                return None
            value = value.item()

        try:
            isna_result = pd.isna(value)
        except (TypeError, ValueError) as exc:
            if hasattr(value, "__array__"):
                logger.debug(
                    "[%s] pd.isna failed for array-like object; re-raise: value_type=%s error_type=%s",
                    context,
                    type(value).__name__,
                    type(exc).__name__,
                )
                raise
            logger.debug(
                "[%s] pd.isna fallback: value_type=%s error_type=%s",
                context,
                type(value).__name__,
                type(exc).__name__,
            )
            return None

        if isinstance(isna_result, (bool, np.bool_)):
            return bool(isna_result)

        if isinstance(isna_result, np.ndarray):
            if isna_result.ndim == 0:
                return bool(isna_result.item())
            logger.debug(
                "[%s] pd.isna returned non-scalar result: value_type=%s result_type=%s",
                context,
                type(value).__name__,
                type(isna_result).__name__,
            )
            return None

        logger.debug(
            "[%s] pd.isna returned unexpected result type: value_type=%s result_type=%s",
            context,
            type(value).__name__,
            type(isna_result).__name__,
        )
        return None

    @staticmethod
    def _is_missing_board_value(value: Any) -> bool:
        """Return True when a board field value should be treated as missing."""
        if value is None:
            return True
        is_missing = DataFetcherManager._try_scalar_isna(value, "board_value")
        if is_missing is True:
            return True
        text = str(value).strip()
        return text == "" or text.lower() in {"nan", "none", "null", "na", "n/a"}

    @staticmethod
    def _normalize_belong_boards(raw_data: Any) -> List[Dict[str, Any]]:
        """Normalize belong-board results from heterogeneous providers."""
        if DataFetcherManager._is_missing_board_value(raw_data):
            return []

        normalized: List[Dict[str, Any]] = []
        dedupe = set()

        if isinstance(raw_data, pd.DataFrame):
            if raw_data.empty:
                return []
            name_col = next(
                (
                    col
                    for col in raw_data.columns
                    if str(col) in {"板块名称", "板块", "所属板块", "板块名", "name", "industry"}
                ),
                None,
            )
            code_col = next(
                (
                    col
                    for col in raw_data.columns
                    if str(col) in {"板块代码", "代码", "code"}
                ),
                None,
            )
            type_col = next(
                (
                    col
                    for col in raw_data.columns
                    if str(col) in {"板块类型", "类别", "type"}
                ),
                None,
            )
            if name_col is None:
                return []
            for _, row in raw_data.iterrows():
                board_name_raw = row.get(name_col, "")
                if DataFetcherManager._is_missing_board_value(board_name_raw):
                    continue
                board_name = str(board_name_raw).strip()
                if board_name in dedupe:
                    continue
                dedupe.add(board_name)
                item = {"name": board_name}
                if code_col is not None:
                    board_code_raw = row.get(code_col, "")
                    if not DataFetcherManager._is_missing_board_value(board_code_raw):
                        item["code"] = str(board_code_raw).strip()
                if type_col is not None:
                    board_type_raw = row.get(type_col, "")
                    if not DataFetcherManager._is_missing_board_value(board_type_raw):
                        item["type"] = str(board_type_raw).strip()
                normalized.append(item)
            return normalized

        if isinstance(raw_data, dict):
            raw_data = [raw_data]

        if isinstance(raw_data, (list, tuple, set)):
            for item in raw_data:
                if isinstance(item, dict):
                    board_name_raw = (
                        item.get("name")
                        or item.get("board_name")
                        or item.get("板块名称")
                        or item.get("板块")
                        or item.get("所属板块")
                        or item.get("板块名")
                        or item.get("industry")
                        or item.get("行业")
                    )
                    if DataFetcherManager._is_missing_board_value(board_name_raw):
                        continue
                    board_name = str(board_name_raw).strip()
                    if board_name in dedupe:
                        continue
                    dedupe.add(board_name)
                    normalized_item: Dict[str, Any] = {"name": board_name}
                    code_raw = (
                        item.get("code")
                        or item.get("板块代码")
                        or item.get("代码")
                    )
                    if not DataFetcherManager._is_missing_board_value(code_raw):
                        normalized_item["code"] = str(code_raw).strip()
                    type_raw = (
                        item.get("type")
                        or item.get("板块类型")
                        or item.get("类别")
                    )
                    if not DataFetcherManager._is_missing_board_value(type_raw):
                        normalized_item["type"] = str(type_raw).strip()
                    normalized.append(normalized_item)
                    continue
                if DataFetcherManager._is_missing_board_value(item):
                    continue
                board_name = str(item).strip()
                if board_name in dedupe:
                    continue
                dedupe.add(board_name)
                normalized.append({"name": board_name})
            return normalized

        if not DataFetcherManager._is_missing_board_value(raw_data):
            board_name = str(raw_data).strip()
            return [{"name": board_name}]
        return []

    def get_belong_boards(self, stock_code: str) -> List[Dict[str, Any]]:
        """
        Get stock membership boards through capability probing.

        Keep this at manager layer to avoid changing BaseFetcher abstraction.
        """
        stock_code = normalize_stock_code(stock_code)
        if _market_tag(stock_code) != "cn":
            return []
        candidate_fetchers = [
            fetcher
            for fetcher in self._get_fetchers_for_capability(
                "belong_boards",
                market="cn",
            )
            if hasattr(fetcher, "get_belong_board")
        ]
        for index, fetcher in enumerate(candidate_fetchers):
            fallback_to = (
                candidate_fetchers[index + 1].name
                if index + 1 < len(candidate_fetchers)
                else None
            )
            start = time.time()
            try:
                record_provider_run_started(
                    data_type="belong_boards",
                    provider=fetcher.name,
                    operation="get_belong_board",
                )
                raw_data = fetcher.get_belong_board(stock_code)
                boards = self._normalize_belong_boards(raw_data)
                if boards:
                    record_provider_run(
                        data_type="belong_boards",
                        provider=fetcher.name,
                        operation="get_belong_board",
                        success=True,
                        latency_ms=int((time.time() - start) * 1000),
                        record_count=len(boards),
                    )
                    logger.info(f"[{fetcher.name}] 获取所属板块成功: {stock_code}, count={len(boards)}")
                    return boards
                record_provider_run(
                    data_type="belong_boards",
                    provider=fetcher.name,
                    operation="get_belong_board",
                    success=False,
                    latency_ms=int((time.time() - start) * 1000),
                    error_type="empty",
                    error_message="empty belong boards",
                    fallback_to=fallback_to,
                    record_count=0,
                )
            except Exception as e:
                error_type, error_reason = summarize_exception(e)
                record_provider_run(
                    data_type="belong_boards",
                    provider=fetcher.name,
                    operation="get_belong_board",
                    success=False,
                    latency_ms=int((time.time() - start) * 1000),
                    error_type=error_type,
                    error_message=error_reason,
                    fallback_to=fallback_to,
                )
                log_safe_exception(
                    logger,
                    "Data provider stock board membership fetch failed",
                    e,
                    error_code="data_provider_stock_board_membership_failed",
                    level=logging.DEBUG,
                    context={"symbol": stock_code, "provider": fetcher.name},
                )
                continue
        return []


EXPECTED_BELONG_BOARD_METHOD_NAMES = (
    "_try_scalar_isna",
    "_is_missing_board_value",
    "_normalize_belong_boards",
    "get_belong_boards",
)


def bind_belong_board_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind belong-board descriptors without changing the manager API."""

    bound_names = []
    for name, descriptor in vars(_BelongBoardMethods).items():
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
