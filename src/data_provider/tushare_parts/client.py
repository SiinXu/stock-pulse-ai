# -*- coding: utf-8 -*-
"""Tushare HTTP client, URL resolve, and rate-limit wrappers.

``_TushareHttpClient`` query/init/getattr are cloned onto this class with
``tushare_fetcher`` globals so ``safe_post`` patch seams stay on the facade
(ADR-006 / Issue #1068). Fetcher client methods are rebound onto
``TushareFetcher``. External callers must keep importing from
``data_provider.tushare_fetcher``.
"""

from __future__ import annotations

import json as _json
import logging
import os
import time
from typing import Callable, Optional

import pandas as pd

from src.config import get_config
from src.security.outbound_policy import safe_post
from src.utils.sanitize import log_safe_exception

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``data_provider.tushare_fetcher`` globals at runtime (ADR-006).
logger = logging.getLogger("src.data_provider.tushare_fetcher")
DataFetchError = Exception  # type: ignore[assignment,misc]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


# Default Tushare Pro HTTP endpoint. Overridable via TUSHARE_HTTP_URL for
# self-hosted nodes, proxies, or internal mirrors; when the variable is unset or
# blank the official endpoint is used so default behavior stays unchanged.
_TUSHARE_DEFAULT_API_URL = "http://api.tushare.pro"


def _resolve_tushare_api_url() -> str:
    """Resolve the Tushare Pro endpoint, honoring the optional TUSHARE_HTTP_URL override.

    A blank or unset TUSHARE_HTTP_URL falls back to the official endpoint, keeping the
    default request path unchanged. Custom endpoints remain subject to the outbound
    security policy, so private hosts still require OUTBOUND_HTTP_ALLOWLIST.
    """
    custom = (os.getenv("TUSHARE_HTTP_URL") or "").strip()
    return custom or _TUSHARE_DEFAULT_API_URL



class _TushareHttpClient:
    """Lightweight Tushare Pro client that does not require the tushare SDK."""

    def __init__(self, token: str, timeout: int = 30, api_url: str = _TUSHARE_DEFAULT_API_URL) -> None:
        self._token = token
        self._timeout = timeout
        self._api_url = api_url

    def query(self, api_name: str, fields: str = "", **kwargs) -> pd.DataFrame:
        req_params = {
            "api_name": api_name,
            "token": self._token,
            "params": kwargs,
            "fields": fields,
        }
        res = safe_post(
            self._api_url,
            json=req_params,
            timeout=self._timeout,
        )
        if res.status_code != 200:
            raise Exception(f"Tushare API HTTP {res.status_code}")

        result = _json.loads(res.text)
        if result.get("code") != 0:
            raise Exception(result.get("msg") or f"Tushare API error code {result.get('code')}")

        data = result.get("data") or {}
        columns = data.get("fields") or []
        items = data.get("items") or []
        return pd.DataFrame(items, columns=columns)

    def __getattr__(self, api_name: str):
        if api_name.startswith("_"):
            raise AttributeError(api_name)

        def caller(**kwargs) -> pd.DataFrame:
            return self.query(api_name, **kwargs)

        return caller


class _ClientMethods:
    """Source descriptors rebound onto ``TushareFetcher``."""

    def _init_api(self) -> None:
        """
        初始化 Tushare API

        如果 Token 未配置，此数据源将不可用。
        这里直接使用内置 HTTP client，避免运行时强依赖 tushare SDK，
        从而减少 Docker / PyInstaller / 多虚拟环境场景下因缺包导致的初始化失败。
        """
        config = get_config()

        if not config.tushare_token:
            logger.warning("Tushare Token 未配置，此数据源不可用")
            return

        try:
            self._api = self._build_api_client(config.tushare_token)
            logger.info("Tushare API 初始化成功")
        except Exception as e:  # broad-exception: fallback_recorded - Tushare API init failure is logged before leaving this source unavailable
            log_safe_exception(
                logger,
                "Tushare API initialization failed",
                e,
                error_code="tushare_api_initialization_failed",
                level=logging.ERROR,
            )
            self._api = None

    def _build_api_client(self, token: str) -> _TushareHttpClient:
        """
        Build a lightweight Tushare Pro client over direct HTTP requests.

        The project already normalizes all Pro calls through the same request
        contract, so we do not need the official tushare SDK during runtime.

        The endpoint honors the optional TUSHARE_HTTP_URL override so self-hosted
        nodes, proxies, or internal mirrors can be targeted; when it is unset the
        official Tushare Pro endpoint is used and behavior is unchanged.
        """
        api_url = _resolve_tushare_api_url()
        client = _TushareHttpClient(token=token, api_url=api_url)
        if api_url == _TUSHARE_DEFAULT_API_URL:
            logger.debug("Tushare API client configured for direct HTTP calls")
        else:
            logger.info("Tushare API endpoint overridden via TUSHARE_HTTP_URL: %s", api_url)
        return client

    def _check_rate_limit(self) -> None:
        """
        检查并执行速率限制
        
        流控策略：
        1. 检查是否进入新的一分钟
        2. 如果是，重置计数器
        3. 如果当前分钟调用次数超过限制，强制休眠
        """
        current_time = time.time()

        # Check if the counter needs to be reset (new minute)
        if self._minute_start is None:
            self._minute_start = current_time
            self._call_count = 0
        elif current_time - self._minute_start >= 60:
            # It has been more than a minute, reset the counter
            self._minute_start = current_time
            self._call_count = 0
            logger.debug("速率限制计数器已重置")

        # Check if quota limit has been exceeded.
        if self._call_count >= self.rate_limit_per_minute:
            # Calculate the waiting time (to the next minute)
            elapsed = current_time - self._minute_start
            sleep_time = max(0, 60 - elapsed) + 1  # +1 second buffer

            logger.warning(
                f"Tushare 达到速率限制 ({self._call_count}/{self.rate_limit_per_minute} 次/分钟)，"
                f"等待 {sleep_time:.1f} 秒..."
            )

            time.sleep(sleep_time)

            # Reset counter
            self._minute_start = time.time()
            self._call_count = 0

        # Increase call count
        self._call_count += 1
        logger.debug(f"Tushare 当前分钟调用次数: {self._call_count}/{self.rate_limit_per_minute}")

    def _call_api_with_rate_limit(self, method_name: str, **kwargs) -> pd.DataFrame:
        """统一通过速率限制包装 Tushare API 调用。"""
        if self._api is None:
            raise DataFetchError("Tushare API 未初始化，请检查 Token 配置")

        self._check_rate_limit()
        method = getattr(self._api, method_name)
        return method(**kwargs)


def _rebind_loaded_facade() -> None:
    hook = _FACADE_RELOAD_HOOK
    if hook is not None:
        hook()


_rebind_loaded_facade()
