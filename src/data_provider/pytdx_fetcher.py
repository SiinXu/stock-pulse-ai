# -*- coding: utf-8 -*-
"""
===================================
PytdxFetcher - 通达信数据源 (Priority 2)
===================================

数据来源：通达信行情服务器（pytdx 库）
特点：免费、无需 Token、直连行情服务器
优点：实时数据、稳定、无配额限制

关键策略：
1. 多服务器自动切换
2. 连接超时自动重连
3. 失败后指数退避重试
"""

import logging
import re
import time
from contextlib import contextmanager
from typing import Optional, Generator, List, Tuple

import pandas as pd

from src.utils.sanitize import log_safe_exception

from .base import (
    BaseFetcher,
    DataFetchError,
    DataSourceUnavailableError,
    STANDARD_COLUMNS,
    is_bse_code,
    normalize_stock_code,
    _is_hk_market,
)
from src.data_provider.retry_policy import (
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    DEFAULT_RETRYABLE_EXCEPTIONS,
    call_with_timeout,
    provider_retry,
)
import os

logger = logging.getLogger(__name__)

_PYTDX_CONNECTION_COOLDOWN_SECONDS = 15.0
# Per-host connect deadline stays explicit and shorter than the overall request
# timeout (intentional deviation from DEFAULT_REQUEST_TIMEOUT_SECONDS).
_PYTDX_CONNECT_TIMEOUT_SECONDS = 5


def _parse_hosts_from_env() -> Optional[List[Tuple[str, int]]]:
    """
    从环境变量构建通达信服务器列表。

    优先级：
    1. PYTDX_SERVERS：逗号分隔 "ip:port,ip:port"（如 "192.168.1.1:7709,10.0.0.1:7709"）
    2. PYTDX_HOST + PYTDX_PORT：单个服务器
    3. 均未配置时返回 None（调用方使用 DEFAULT_HOSTS）
    """
    servers = os.getenv("PYTDX_SERVERS", "").strip()
    if servers:
        result = []
        for part in servers.split(","):
            part = part.strip()
            if ":" in part:
                host, port_str = part.rsplit(":", 1)
                host, port_str = host.strip(), port_str.strip()
                if host and port_str:
                    try:
                        result.append((host, int(port_str)))
                    except ValueError:
                        logger.warning(f"Invalid PYTDX_SERVERS entry: {part}")
            else:
                logger.warning(f"Invalid PYTDX_SERVERS entry (missing port): {part}")
        if result:
            return result

    host = os.getenv("PYTDX_HOST", "").strip()
    port_str = os.getenv("PYTDX_PORT", "").strip()
    if host and port_str:
        try:
            return [(host, int(port_str))]
        except ValueError:
            logger.warning(f"Invalid PYTDX_HOST/PYTDX_PORT: {host}:{port_str}")

    return None


def _is_us_code(stock_code: str) -> bool:
    """
    判断代码是否为美股
    
    美股代码规则：
    - 1-5个大写字母，如 'AAPL', 'TSLA'
    - 可能包含 '.'，如 'BRK.B'
    """
    code = stock_code.strip().upper()
    return bool(re.match(r'^[A-Z]{1,5}(\.[A-Z])?$', code))


class PytdxFetcher(BaseFetcher):
    """
    通达信数据源实现
    
    优先级：2（与 Tushare 同级）
    数据来源：通达信行情服务器
    
    关键策略：
    - 自动选择最优服务器
    - 连接失败自动切换服务器
    - 失败后指数退避重试
    
    Pytdx 特点：
    - 免费、无需注册
    - 直连行情服务器
    - 支持实时行情和历史数据
    - 支持股票名称查询
    """
    
    name = "PytdxFetcher"
    priority = int(os.getenv("PYTDX_PRIORITY", "2"))
    
    # Default TDX quote-server list.
    DEFAULT_HOSTS = [
        ("119.147.212.81", 7709),  # Shenzhen
        ("112.74.214.43", 7727),   # Shenzhen
        ("221.231.141.60", 7709),  # Shanghai
        ("101.227.73.20", 7709),   # Shanghai
        ("101.227.77.254", 7709),  # Shanghai
        ("14.215.128.18", 7709),   # Guangzhou
        ("59.173.18.140", 7709),   # Wuhan
        ("180.153.39.51", 7709),   # Hangzhou
    ]
    # Pytdx get_security_list returns at most 1000 items per page
    SECURITY_LIST_PAGE_SIZE = 1000
    
    def __init__(
        self,
        hosts: Optional[List[Tuple[str, int]]] = None,
        request_timeout_seconds: Optional[float] = None,
    ):
        """
        初始化 PytdxFetcher

        Args:
            hosts: 服务器列表 [(host, port), ...]。若未传入，优先使用环境变量
                   PYTDX_SERVERS（ip:port,ip:port）或 PYTDX_HOST+PYTDX_PORT，
                   否则使用内置 DEFAULT_HOSTS。
            request_timeout_seconds: Overall request deadline for a bars fetch
                (connect + query). Defaults to the shared provider request-timeout
                contract. Per-host connect still uses
                ``_PYTDX_CONNECT_TIMEOUT_SECONDS``.
        """
        if hosts is not None:
            self._hosts = hosts
        else:
            env_hosts = _parse_hosts_from_env()
            self._hosts = env_hosts if env_hosts else self.DEFAULT_HOSTS
        self._api = None
        self._connected = False
        self._current_host_idx = 0
        self._stock_list_cache = None  # Stock List Cache
        self._stock_name_cache = {}    # Stock Name Cache {code: name}
        self._unavailable_until = 0.0
        self._last_unavailable_reason = ""
        self._request_timeout_seconds = (
            DEFAULT_REQUEST_TIMEOUT_SECONDS
            if request_timeout_seconds is None
            else float(request_timeout_seconds)
        )

    def _is_in_connection_cooldown(self) -> bool:
        return time.time() < self._unavailable_until

    def _mark_connection_cooldown(self, reason: str) -> None:
        self._unavailable_until = time.time() + _PYTDX_CONNECTION_COOLDOWN_SECONDS
        self._last_unavailable_reason = str(reason or "").strip()
        logger.info(
            "Pytdx 连接失败，进入冷却 %.0fs: %s",
            _PYTDX_CONNECTION_COOLDOWN_SECONDS,
            self._last_unavailable_reason or "unknown",
        )

    def is_available_for_request(self, capability: str = "") -> bool:
        return not self._is_in_connection_cooldown()
    
    def _get_pytdx(self):
        """
        延迟加载 pytdx 模块
        
        只在首次使用时导入，避免未安装时报错
        """
        try:
            from pytdx.hq import TdxHq_API
            return TdxHq_API
        except ImportError:
            logger.warning("pytdx 未安装，请运行: pip install pytdx")
            return None
    
    @contextmanager
    def _pytdx_session(self) -> Generator:
        """
        Pytdx 连接上下文管理器
        
        确保：
        1. 进入上下文时自动连接
        2. 退出上下文时自动断开
        3. 异常时也能正确断开
        
        使用示例：
            with self._pytdx_session() as api:
                # 在这里执行数据查询
        """
        if self._is_in_connection_cooldown():
            raise DataSourceUnavailableError(
                f"Pytdx temporarily unavailable: {self._last_unavailable_reason or 'connection cooldown'}"
            )

        TdxHq_API = self._get_pytdx()
        if TdxHq_API is None:
            raise DataFetchError("pytdx 库未安装")
        
        api = TdxHq_API()
        connected = False
        
        try:
            # Attempt to connect to the server (automatically selects the optimal one)
            for i in range(len(self._hosts)):
                host_idx = (self._current_host_idx + i) % len(self._hosts)
                host, port = self._hosts[host_idx]
                
                try:
                    if api.connect(host, port, time_out=_PYTDX_CONNECT_TIMEOUT_SECONDS):
                        connected = True
                        self._current_host_idx = host_idx
                        logger.debug(f"Pytdx 连接成功: {host}:{port}")
                        break
                except Exception as e:  # broad-exception: fallback_recorded - Try next host after connection failure.
                    log_safe_exception(
                        logger,
                        "Pytdx server connection failed",
                        e,
                        error_code="pytdx_server_connection_failed",
                        level=logging.DEBUG,
                        context={"host": host, "port": port},
                    )
                    continue
            
            if not connected:
                self._mark_connection_cooldown("Pytdx 无法连接任何服务器")
                raise DataFetchError("Pytdx 无法连接任何服务器")
            
            yield api
            
        finally:
            # Ensure connection is broken
            try:
                api.disconnect()
                logger.debug("Pytdx 连接已断开")
            except Exception as e:
                log_safe_exception(
                    logger,
                    "Pytdx disconnect failed",
                    e,
                    error_code="pytdx_disconnect_failed",
                    level=logging.WARNING,
                )
    
    def _get_market_code(self, stock_code: str) -> Tuple[int, str]:
        """
        根据股票代码判断市场
        
        Pytdx 市场代码：
        - 0: 深圳
        - 1: 上海
        
        Args:
            stock_code: 股票代码
            
        Returns:
            (market, code) 元组
        """
        raw_code = stock_code.strip()
        upper = raw_code.upper()
        prefix, separator, suffix = raw_code.partition(".")
        if separator and prefix:
            prefix_upper = prefix.strip().upper()
            if prefix_upper in ('SH', 'SS'):
                normalized = normalize_stock_code(suffix.strip())
                if normalized.isdigit() and len(normalized) == 6:
                    return 1, normalized
            if prefix_upper == 'SZ':
                normalized = normalize_stock_code(suffix.strip())
                if normalized.isdigit() and len(normalized) == 6:
                    return 0, normalized

        code = normalize_stock_code(raw_code)

        if upper.startswith(('SH', 'SS')) or upper.endswith(('.SH', '.SS')):
            return 1, code
        if upper.startswith('SZ') or upper.endswith('.SZ'):
            return 0, code
        
        # Determine the market based on code prefix
        # Shanghai: 60xxxx, 68xxxx (STAR Market)
        # Shenzhen: 00xxxx, 30xxxx (ChiNext), 002xxx (SME Board)
        if code.startswith(('60', '68')):
            return 1, code  # Shanghai
        else:
            return 0, code  # Shenzhen

    def _build_stock_list_cache(self, api) -> None:
        """
        Build a full stock code -> name cache from paginated security lists.
        """
        self._stock_list_cache = {}

        for market in (0, 1):
            start = 0
            while True:
                stocks = api.get_security_list(market, start) or []
                for stock in stocks:
                    code = stock.get('code')
                    name = stock.get('name')
                    if code and name:
                        self._stock_list_cache[code] = name

                if len(stocks) < self.SECURITY_LIST_PAGE_SIZE:
                    break

                start += self.SECURITY_LIST_PAGE_SIZE
    
    # Rebound from pytdx_parts.history after the class is built.
    # provider_retry is re-applied in _assemble_pytdx_fetcher_facade.
    _fetch_raw_data = None

    _normalize_data = None

    def get_stock_name(self, stock_code: str) -> Optional[str]:
        """
        获取股票名称
        
        Args:
            stock_code: 股票代码
            
        Returns:
            股票名称，失败返回 None
        """
        # Hong Kong stocks are not supported (pytdx does not include Hong Kong stock data)
        if _is_hk_market(stock_code):
            return None

        # Check cache
        if stock_code in self._stock_name_cache:
            return self._stock_name_cache[stock_code]
        
        try:
            market, code = self._get_market_code(stock_code)
            
            with self._pytdx_session() as api:
                # Get stock list (caching)
                if self._stock_list_cache is None:
                    self._build_stock_list_cache(api)
                
                # Search for stock name
                name = self._stock_list_cache.get(code)
                if name:
                    self._stock_name_cache[stock_code] = name
                    return name
                
                # Attempt to use get_finance_info
                finance_info = api.get_finance_info(market, code)
                if finance_info and 'name' in finance_info:
                    name = finance_info['name']
                    self._stock_name_cache[stock_code] = name
                    return name
                
        except Exception as e:
            log_safe_exception(
                logger,
                "Pytdx stock name lookup failed",
                e,
                error_code="pytdx_stock_name_lookup_failed",
                level=logging.DEBUG,
                context={"symbol": stock_code},
            )
        
        return None
    
    def get_realtime_quote(self, stock_code: str) -> Optional[dict]:
        """
        获取实时行情
        
        Args:
            stock_code: 股票代码
            
        Returns:
            实时行情数据字典，失败返回 None
        """
        if is_bse_code(stock_code):
            raise DataFetchError(
                f"PytdxFetcher 不支持北交所 {stock_code}，将自动切换其他数据源"
            )
        try:
            market, code = self._get_market_code(stock_code)
            
            with self._pytdx_session() as api:
                data = api.get_security_quotes([(market, code)])
                
                if data and len(data) > 0:
                    quote = data[0]
                    return {
                        'code': stock_code,
                        'name': quote.get('name', ''),
                        'price': quote.get('price', 0),
                        'open': quote.get('open', 0),
                        'high': quote.get('high', 0),
                        'low': quote.get('low', 0),
                        'pre_close': quote.get('last_close', 0),
                        'volume': quote.get('vol', 0),
                        'amount': quote.get('amount', 0),
                        'bid_prices': [quote.get(f'bid{i}', 0) for i in range(1, 6)],
                        'ask_prices': [quote.get(f'ask{i}', 0) for i in range(1, 6)],
                    }
        except Exception as e:
            log_safe_exception(
                logger,
                "Pytdx realtime quote failed",
                e,
                error_code="pytdx_realtime_quote_failed",
                level=logging.WARNING,
                context={"symbol": stock_code},
            )
        
        return None


# Keep ``src.data_provider.pytdx_fetcher.PytdxFetcher`` as the ADR-006
# compatibility facade while ``pytdx_parts`` owns daily-history bodies.
# Rebinding preserves method globals so existing patches against this
# module continue to intercept moved implementations.
from .pytdx_parts import history as _history_module  # noqa: E402
from .pytdx_parts.history import _HistoryMethods  # noqa: E402
from .pytdx_parts.facade_bind import bind_methods_from_class  # noqa: E402


def _apply_history_retry(name: str, bound):
    """Re-apply provider_retry after facade cloning so timeout retries survive bind."""

    if name != "_fetch_raw_data":
        return bound
    return provider_retry(
        target_logger=logger,
        event="Pytdx daily data retry scheduled",
        error_code="pytdx_daily_data_retry",
    )(bound)


def _assemble_pytdx_fetcher_facade() -> None:
    """Bind capability-domain method bodies onto the public fetcher class."""

    global _HistoryMethods
    _HistoryMethods = _history_module._HistoryMethods
    bind_methods_from_class(
        _HistoryMethods,
        PytdxFetcher,
        globals(),
        expected_names=_history_module.EXPECTED_HISTORY_METHOD_NAMES,
        post_bind=_apply_history_retry,
    )
    # Rebound methods are assigned after class body evaluation; clear ABC
    # abstracts that are now implemented so instantiation matches the legacy
    # monofile class (BaseFetcher marks _fetch_raw_data / _normalize_data).
    abstracts = set(getattr(PytdxFetcher, "__abstractmethods__", ()))
    if abstracts:
        abstracts.difference_update(
            {
                name
                for name in (
                    "_fetch_raw_data",
                    "_normalize_data",
                    "get_daily_data",
                )
                if callable(getattr(PytdxFetcher, name, None))
            }
        )
        abstracts = {
            name
            for name in abstracts
            if name not in PytdxFetcher.__dict__
            or getattr(PytdxFetcher.__dict__[name], "__isabstractmethod__", False)
        }
        PytdxFetcher.__abstractmethods__ = frozenset(abstracts)


_assemble_pytdx_fetcher_facade()


def _install_part_reload_hooks() -> None:
    """Keep an owner reload able to rebuild and rebind every owner module."""

    _history_module._FACADE_RELOAD_HOOK = _assemble_pytdx_fetcher_facade  # type: ignore[attr-defined]


_install_part_reload_hooks()


if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.DEBUG)
    
    fetcher = PytdxFetcher()
    
    try:
        # Test historical data
        df = fetcher.get_daily_data('600519')  # Maotai
        print(f"获取成功，共 {len(df)} 条数据")
        print(df.tail())
        
        # Test stock name
        name = fetcher.get_stock_name('600519')
        print(f"股票名称: {name}")
        
        # Test real-time quotes
        quote = fetcher.get_realtime_quote('600519')
        print(f"实时行情: {quote}")
        
    except Exception as e:  # broad-exception: fallback_recorded - Manual smoke failure is logged safely.
        log_safe_exception(
            logger,
            "Pytdx manual smoke failed",
            e,
            error_code="pytdx_manual_smoke_failed",
            level=logging.ERROR,
        )
        print(f"获取失败: {e}")
