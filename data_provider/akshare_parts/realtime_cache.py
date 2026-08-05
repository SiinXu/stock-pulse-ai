# -*- coding: utf-8 -*-
"""AkShare realtime full-market snapshot cache.

Owns the process-local state and TTL / failure-TTL policy for:

* A-share Eastmoney spot snapshots (``stock_zh_a_spot_em``)
* ETF Eastmoney spot snapshots (``fund_etf_spot_em``)
* Hong Kong Eastmoney spot snapshots (``stock_hk_spot_em``), including
  keep-last-good semantics on failed refresh, short failure-TTL only when
  cold, and a lock used to coalesce concurrent full-market refreshes

The public fetcher re-exports ``_realtime_cache`` and ``_etf_realtime_cache``
so existing tests and patch targets on ``data_provider.akshare_fetcher`` remain
valid. Callers outside ``data_provider`` should not import this module.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# TTL set to 20 minutes (1200 seconds):
# - Bulk analysis: 30 stocks are typically analyzed within 5 minutes, so a
#   20-minute cache covers the run
# - Real-time data requirements: Stock analysis does not require sub-second
#   real-time data; 20-minute latency is acceptable.
# - Anti-ban: Reduce API call frequency
DEFAULT_SNAPSHOT_TTL_SECONDS = 1200
HK_FAILURE_TTL_SECONDS = 30

# Cache real-time market data (to avoid redundant requests)
_realtime_cache: Dict[str, Any] = {
    "data": None,
    "timestamp": 0,
    "ttl": DEFAULT_SNAPSHOT_TTL_SECONDS,
    # ``stock_hk_spot_em`` returns the full Hong Kong market, so reuse one
    # validated snapshot across per-symbol requests.
    "hk": {
        "data": None,
        # Timestamp of the last *successful* full-market snapshot.
        "timestamp": 0,
        "ttl": DEFAULT_SNAPSHOT_TTL_SECONDS,
        "failure_ttl": HK_FAILURE_TTL_SECONDS,
        # Timestamp of the last failed refresh. Kept separate from
        # ``timestamp`` so a short negative-cache window never rewrites a
        # still-usable snapshot's success age (and never forces Sina while
        # EM data is fresh).
        "failure_at": 0,
        "last_result": None,
        "lock": threading.Lock(),
    },
}

# ETF Real-time Quote Cache
_etf_realtime_cache: Dict[str, Any] = {
    "data": None,
    "timestamp": 0,
    "ttl": DEFAULT_SNAPSHOT_TTL_SECONDS,
}


def get_a_share_snapshot_if_fresh(
    now: Optional[float] = None,
) -> Optional[pd.DataFrame]:
    """Return the cached A-share EM snapshot when still inside its success TTL."""
    current_time = time.time() if now is None else now
    data = _realtime_cache["data"]
    if data is None:
        return None
    if current_time - _realtime_cache["timestamp"] >= _realtime_cache["ttl"]:
        return None
    cache_age = int(current_time - _realtime_cache["timestamp"])
    logger.debug(
        f"[缓存命中] A股实时行情(东财) - 缓存年龄 {cache_age}s/{_realtime_cache['ttl']}s"
    )
    return data


def store_a_share_snapshot(
    df: pd.DataFrame,
    now: Optional[float] = None,
) -> None:
    """Replace the A-share EM snapshot and stamp its success timestamp."""
    current_time = time.time() if now is None else now
    _realtime_cache["data"] = df
    _realtime_cache["timestamp"] = current_time
    logger.info(
        f"[缓存更新] A股实时行情(东财) 缓存已刷新，TTL={_realtime_cache['ttl']}s"
    )


def get_etf_snapshot_if_fresh(
    now: Optional[float] = None,
) -> Optional[pd.DataFrame]:
    """Return the cached ETF EM snapshot when still inside its success TTL."""
    current_time = time.time() if now is None else now
    data = _etf_realtime_cache["data"]
    if data is None:
        return None
    if current_time - _etf_realtime_cache["timestamp"] >= _etf_realtime_cache["ttl"]:
        return None
    logger.debug("[缓存命中] 使用缓存的ETF实时行情数据")
    return data


def store_etf_snapshot(
    df: pd.DataFrame,
    now: Optional[float] = None,
) -> None:
    """Replace the ETF EM snapshot and stamp its success timestamp."""
    current_time = time.time() if now is None else now
    _etf_realtime_cache["data"] = df
    _etf_realtime_cache["timestamp"] = current_time


def get_hk_cache() -> Dict[str, Any]:
    """Return the nested Hong Kong Eastmoney snapshot cache dict."""
    return _realtime_cache["hk"]


def hk_refresh_lock() -> threading.Lock:
    """Return the lock used to coalesce concurrent HK full-market refreshes."""
    return _realtime_cache["hk"]["lock"]


def lookup_hk_em_snapshot(
    now: Optional[float] = None,
) -> Tuple[bool, Optional[pd.DataFrame]]:
    """Classify the HK Eastmoney cache for a single lookup.

    Returns ``(hit, data)``:

    * ``(True, DataFrame)`` — still-fresh success snapshot; callers should
      parse a quote from ``data`` without refreshing.
    * ``(True, None)`` — short negative-cache window is active (no usable
      snapshot); callers should skip Eastmoney refresh and try fallbacks.
    * ``(False, None)`` — cache miss; a refresh is allowed.

    Prefer a still-fresh Eastmoney snapshot over any failure marker. A failed
    refresh must not hide previously-good data that is still inside its own
    success TTL.
    """
    hk_cache = _realtime_cache["hk"]
    current_time = time.time() if now is None else now
    cache_data = hk_cache["data"]
    cache_age = current_time - hk_cache["timestamp"]

    if cache_data is not None and cache_age < hk_cache["ttl"]:
        logger.debug(
            "Akshare Eastmoney HK realtime cache hit: age=%ds ttl=%ss",
            int(cache_age),
            hk_cache["ttl"],
        )
        return True, cache_data

    # Short negative cache only when there is no usable snapshot.
    failure_at = float(hk_cache.get("failure_at") or 0)
    if failure_at <= 0 and hk_cache.get("last_result") == "failure":
        # Backward-compatible: older process state used ``timestamp`` as
        # the failure clock after clearing ``data``.
        failure_at = float(hk_cache.get("timestamp") or 0)
    failure_age = current_time - failure_at if failure_at > 0 else None
    if (
        hk_cache.get("last_result") == "failure"
        and failure_age is not None
        and failure_age < hk_cache.get("failure_ttl", 0)
    ):
        logger.debug(
            "Akshare Eastmoney HK realtime negative cache hit: age=%ds ttl=%ss",
            int(failure_age),
            hk_cache.get("failure_ttl", 0),
        )
        return True, None

    return False, None


def record_hk_refresh_success(
    df: pd.DataFrame,
    now: Optional[float] = None,
) -> None:
    """Store a validated HK Eastmoney full-market snapshot after a refresh."""
    hk_cache = _realtime_cache["hk"]
    current_time = time.time() if now is None else now
    hk_cache["data"] = df
    hk_cache["timestamp"] = current_time
    hk_cache["failure_at"] = 0
    hk_cache["last_result"] = "success"


def record_hk_refresh_failure(now: Optional[float] = None) -> bool:
    """Apply keep-last-good / failure-TTL policy after a failed HK refresh.

    Never destroy a still-usable snapshot on refresh failure (network or
    validation). Keep serving it until its own success TTL expires; apply the
    short failure TTL only when there is no usable Eastmoney snapshot.

    Returns ``True`` when a still-usable snapshot was preserved (callers may
    log the preserve path). Returns ``False`` when the failure-TTL window was
    installed instead.
    """
    hk_cache = _realtime_cache["hk"]
    current_time = time.time() if now is None else now
    existing = hk_cache.get("data")
    success_ts = float(hk_cache.get("timestamp") or 0)
    still_usable = (
        existing is not None
        and (current_time - success_ts) < float(hk_cache.get("ttl") or 0)
    )
    if still_usable:
        logger.warning(
            "Akshare Eastmoney HK realtime refresh failed; "
            "preserving still-usable snapshot (age=%ds ttl=%ss)",
            int(current_time - success_ts),
            hk_cache.get("ttl", 0),
        )
        return True

    # Do not clear previously-good (possibly expired) DataFrames: only mark
    # the negative-cache window. When there was never a snapshot, stamp
    # timestamp so older readers that only inspect timestamp still see a
    # recent failure clock.
    if existing is None:
        hk_cache["timestamp"] = current_time
    hk_cache["failure_at"] = current_time
    hk_cache["last_result"] = "failure"
    return False
