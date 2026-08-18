# -*- coding: utf-8 -*-
"""AkShare realtime quote methods (EM/Sina/Tencent, A-share/ETF/HK).

Method bodies are rebound onto ``AkshareFetcher`` by the compatibility facade
(ADR-006) so free-name lookups and test patches stay on
``data_provider.akshare_fetcher``.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd
import requests

from src.utils.sanitize import log_safe_exception

logger = logging.getLogger("src.data_provider.akshare_fetcher")
USER_AGENTS = []  # type: ignore[assignment]
SINA_REALTIME_ENDPOINT = ""
TENCENT_REALTIME_ENDPOINT = ""
UnifiedRealtimeQuote = None  # type: ignore[assignment,misc]
RealtimeSource = None  # type: ignore[assignment,misc]
safe_float = None  # type: ignore[assignment]
safe_int = None  # type: ignore[assignment]
get_realtime_circuit_breaker = None  # type: ignore[assignment]
_is_etf_code = None  # type: ignore[assignment]
_is_hk_code = None  # type: ignore[assignment]
_to_sina_tx_symbol = None  # type: ignore[assignment]
_normalize_tencent_volume = None  # type: ignore[assignment]
_parse_tencent_amount = None  # type: ignore[assignment]
_classify_realtime_http_error = None  # type: ignore[assignment]
_build_realtime_failure_message = None  # type: ignore[assignment]
get_a_share_snapshot_if_fresh = None  # type: ignore[assignment]
store_a_share_snapshot = None  # type: ignore[assignment]
get_etf_snapshot_if_fresh = None  # type: ignore[assignment]
store_etf_snapshot = None  # type: ignore[assignment]
get_hk_cache = None  # type: ignore[assignment]
hk_refresh_lock = None  # type: ignore[assignment]
lookup_hk_em_snapshot = None  # type: ignore[assignment]
record_hk_refresh_success = None  # type: ignore[assignment]
record_hk_refresh_failure = None  # type: ignore[assignment]
_realtime_cache = None  # type: ignore[assignment]
_etf_realtime_cache = None  # type: ignore[assignment]
_is_us_code = None  # type: ignore[assignment]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _RealtimeQuotesMethods:
    """Source descriptors rebound onto ``AkshareFetcher``."""

    def get_realtime_quote(self, stock_code: str, source: str = "em") -> Optional[UnifiedRealtimeQuote]:
        """
        获取实时行情数据（支持多数据源）

        数据源优先级（可配置）：
        1. em: 东方财富（akshare ak.stock_zh_a_spot_em）- 数据最全，含量比/PE/PB/市值等
        2. sina: 新浪财经（akshare ak.stock_zh_a_spot）- 轻量级，基本行情
        3. tencent: 腾讯直连接口 - 单股票查询，负载小

        Args:
            stock_code: 股票/ETF代码
            source: 数据源类型，可选 "em", "sina", "tencent"

        Returns:
            UnifiedRealtimeQuote 对象，获取失败返回 None
        """
        circuit_breaker = get_realtime_circuit_breaker()

        # Choose different retrieval methods based on code type:
        if _is_us_code(stock_code):
            # U.S. Stocks do not use Akshare, handled by YfinanceFetcher
            logger.debug(f"[API跳过] {stock_code} 是美股，Akshare 不支持美股实时行情")
            return None
        elif _is_hk_code(stock_code):
            return self._get_hk_realtime_quote(stock_code)
        elif _is_etf_code(stock_code):
            source_key = "akshare_etf"
            if not circuit_breaker.is_available(source_key):
                logger.info(f"[熔断] 数据源 {source_key} 处于熔断状态，跳过")
                return None
            return self._get_etf_realtime_quote(stock_code)
        else:
            source_key = f"akshare_{source}"
            if not circuit_breaker.is_available(source_key):
                logger.info(f"[熔断] 数据源 {source_key} 处于熔断状态，跳过")
                return None
            # Regular A-shares: selecting data source based on source
            if source == "sina":
                return self._get_stock_realtime_quote_sina(stock_code)
            elif source == "tencent":
                return self._get_stock_realtime_quote_tencent(stock_code)
            else:
                return self._get_stock_realtime_quote_em(stock_code)

    def _get_stock_realtime_quote_em(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        获取普通 A 股实时行情数据（东方财富数据源）
        
        数据来源：ak.stock_zh_a_spot_em()
        优点：数据最全，含量比、换手率、市盈率、市净率、总市值、流通市值等
        缺点：全量拉取，数据量大，容易超时/限流
        """
        import akshare as ak
        circuit_breaker = get_realtime_circuit_breaker()
        source_key = "akshare_em"
        
        try:
            # Check the cache
            current_time = time.time()
            df = get_a_share_snapshot_if_fresh(current_time)
            if df is None:
                # Trigger full refresh
                logger.info(f"[缓存未命中] 触发全量刷新 A股实时行情(东财)")
                df = None
                for attempt in range(1, 3):
                    try:
                        # Anti-ban strategy
                        self._set_random_user_agent()
                        self._enforce_rate_limit()

                        logger.info(f"[API调用] ak.stock_zh_a_spot_em() 获取A股实时行情... (attempt {attempt}/2)")
                        import time as _time
                        api_start = _time.time()

                        df = ak.stock_zh_a_spot_em()

                        api_elapsed = _time.time() - api_start
                        logger.info(f"[API返回] ak.stock_zh_a_spot_em 成功: 返回 {len(df)} 只股票, 耗时 {api_elapsed:.2f}s")
                        circuit_breaker.record_success(source_key)
                        break
                    except Exception as e:  # broad-exception: fallback_recorded - Provider I/O failure is safely logged before fallback or skip
                        log_safe_exception(
                            logger,
                            "Akshare A-share realtime snapshot attempt failed",
                            e,
                            error_code="akshare_a_share_realtime_snapshot_failed",
                            level=logging.INFO,
                            context={"attempt": attempt},
                        )
                        time.sleep(min(2 ** attempt, 5))

                # Update cache: Successfully caches data; also caches empty data if failure to avoid repeated requests for the same interface in the same task round
                if df is None:
                    logger.info(
                        "Akshare A-share realtime snapshot failed after retries"
                    )
                    circuit_breaker.record_failure(
                        source_key,
                        "akshare_a_share_realtime_snapshot_failed",
                    )
                    df = pd.DataFrame()
                store_a_share_snapshot(df, current_time)

            if df is None or df.empty:
                logger.info(f"[实时行情] A股实时行情数据为空，跳过 {stock_code}")
                return None
            
            # Find specified stock
            row = df[df['代码'] == stock_code]
            if row.empty:
                logger.info(f"[API返回] 未找到股票 {stock_code} 的实时行情")
                return None
            
            row = row.iloc[0]
            
            # Use unified conversion functions in realtime_types.py
            quote = UnifiedRealtimeQuote(
                code=stock_code,
                name=str(row.get('名称', '')),
                source=RealtimeSource.AKSHARE_EM,
                price=safe_float(row.get('最新价')),
                change_pct=safe_float(row.get('涨跌幅')),
                change_amount=safe_float(row.get('涨跌额')),
                volume=safe_int(row.get('成交量')),
                amount=safe_float(row.get('成交额')),
                volume_ratio=safe_float(row.get('量比')),
                turnover_rate=safe_float(row.get('换手率')),
                amplitude=safe_float(row.get('振幅')),
                open_price=safe_float(row.get('今开')),
                high=safe_float(row.get('最高')),
                low=safe_float(row.get('最低')),
                pe_ratio=safe_float(row.get('市盈率-动态')),
                pb_ratio=safe_float(row.get('市净率')),
                total_mv=safe_float(row.get('总市值')),
                circ_mv=safe_float(row.get('流通市值')),
                change_60d=safe_float(row.get('60日涨跌幅')),
                high_52w=safe_float(row.get('52周最高')),
                low_52w=safe_float(row.get('52周最低')),
            )
            
            logger.info(f"[实时行情-东财] {stock_code} {quote.name}: 价格={quote.price}, 涨跌={quote.change_pct}%, "
                       f"量比={quote.volume_ratio}, 换手率={quote.turnover_rate}%")
            return quote
            
        except Exception as e:  # broad-exception: fallback_recorded - Provider I/O failure is safely logged before fallback or skip
            log_safe_exception(
                logger,
                "Akshare Eastmoney realtime quote failed",
                e,
                error_code="akshare_eastmoney_realtime_quote_failed",
                level=logging.INFO,
                context={"symbol": stock_code},
            )
            circuit_breaker.record_failure(
                source_key,
                "akshare_eastmoney_realtime_quote_failed",
            )
            return None

    def _get_stock_realtime_quote_sina(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        获取普通 A 股实时行情数据（新浪财经数据源）
        
        数据来源：新浪财经接口（直连，单股票查询）
        优点：单股票查询，负载小，速度快
        缺点：数据字段较少，无量比/PE/PB等
        
        接口格式：http://hq.sinajs.cn/list=sh600519,sz000001
        """
        circuit_breaker = get_realtime_circuit_breaker()
        source_key = "akshare_sina"
        symbol = _to_sina_tx_symbol(stock_code)
        url = f"http://{SINA_REALTIME_ENDPOINT}={symbol}"
        api_start = time.time()
        
        try:
            headers = {
                'Referer': 'http://finance.sina.com.cn',
                'User-Agent': random.choice(USER_AGENTS)
            }
            
            logger.info(
                f"[API调用] 新浪财经接口获取 {stock_code} 实时行情: endpoint={SINA_REALTIME_ENDPOINT}, symbol={symbol}"
            )
            
            self._enforce_rate_limit()
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = 'gbk'
            api_elapsed = time.time() - api_start
            
            if response.status_code != 200:
                failure_message = _build_realtime_failure_message(
                    source_name="新浪",
                    endpoint=SINA_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="http_status",
                    detail=f"HTTP {response.status_code}",
                    elapsed=api_elapsed,
                    error_type="HTTPStatus",
                )
                logger.info(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            # parse data: var hq_str_sh600519="贵州茅台,1866.000,1870.000,..."
            content = response.text.strip()
            if '=""' in content or not content:
                failure_message = _build_realtime_failure_message(
                    source_name="新浪",
                    endpoint=SINA_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="empty_response",
                    detail="empty quote payload",
                    elapsed=api_elapsed,
                    error_type="EmptyResponse",
                )
                logger.info(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            # Extracts data within quotes
            data_start = content.find('"')
            data_end = content.rfind('"')
            if data_start == -1 or data_end == -1:
                failure_message = _build_realtime_failure_message(
                    source_name="新浪",
                    endpoint=SINA_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="malformed_payload",
                    detail="quote payload missing quotes",
                    elapsed=api_elapsed,
                    error_type="MalformedPayload",
                )
                logger.info(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            data_str = content[data_start+1:data_end]
            fields = data_str.split(',')
            
            if len(fields) < 32:
                failure_message = _build_realtime_failure_message(
                    source_name="新浪",
                    endpoint=SINA_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="insufficient_fields",
                    detail=f"field_count={len(fields)}",
                    elapsed=api_elapsed,
                    error_type="InsufficientFields",
                )
                logger.info(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            circuit_breaker.record_success(source_key)
            
            # Sina data field order:
            # 0: Name 1: Open today 2: Close yesterday 3: Latest price 4: High 5: Low 6: best bid 7: best ask
            # 8: Volume (shares) 9: trading value (yuan) ... 30: Date 31: Time
            # Use unified conversion functions in realtime_types.py
            price = safe_float(fields[3])
            pre_close = safe_float(fields[2])
            change_pct = None
            change_amount = None
            if price and pre_close and pre_close > 0:
                change_amount = price - pre_close
                change_pct = (change_amount / pre_close) * 100
            
            quote = UnifiedRealtimeQuote(
                code=stock_code,
                name=fields[0],
                source=RealtimeSource.AKSHARE_SINA,
                price=price,
                change_pct=change_pct,
                change_amount=change_amount,
                volume=safe_int(fields[8]),  # Volume (shares)
                amount=safe_float(fields[9]),  # trading value (yuan)
                open_price=safe_float(fields[1]),
                high=safe_float(fields[4]),
                low=safe_float(fields[5]),
                pre_close=pre_close,
            )
            
            logger.info(
                f"[实时行情-新浪] {stock_code} {quote.name}: endpoint={SINA_REALTIME_ENDPOINT}, "
                f"价格={quote.price}, 涨跌={quote.change_pct}, 成交量={quote.volume}, elapsed={api_elapsed:.2f}s"
            )
            return quote
            
        except Exception as e:  # broad-exception: fallback_recorded - Provider I/O failure is safely logged before fallback or skip
            category, _ = _classify_realtime_http_error(e)
            log_safe_exception(
                logger,
                "Akshare Sina realtime quote failed",
                e,
                error_code="akshare_sina_realtime_quote_failed",
                level=logging.INFO,
                context={
                    "symbol": symbol,
                    "endpoint": SINA_REALTIME_ENDPOINT,
                    "category": category,
                },
            )
            circuit_breaker.record_failure(
                source_key,
                "akshare_sina_realtime_quote_failed",
            )
            return None

    def _get_stock_realtime_quote_tencent(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        获取普通 A 股实时行情数据（腾讯财经数据源）
        
        数据来源：腾讯财经接口（直连，单股票查询）
        优点：单股票查询，负载小，包含换手率
        缺点：无量比/PE/PB等估值数据
        
        接口格式：http://qt.gtimg.cn/q=sh600519,sz000001
        """
        circuit_breaker = get_realtime_circuit_breaker()
        source_key = "akshare_tencent"
        symbol = _to_sina_tx_symbol(stock_code)
        url = f"http://{TENCENT_REALTIME_ENDPOINT}={symbol}"
        api_start = time.time()
        
        try:
            headers = {
                'Referer': 'http://finance.qq.com',
                'User-Agent': random.choice(USER_AGENTS)
            }
            
            logger.info(
                f"[API调用] 腾讯财经接口获取 {stock_code} 实时行情: endpoint={TENCENT_REALTIME_ENDPOINT}, symbol={symbol}"
            )
            
            self._enforce_rate_limit()
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = 'gbk'
            api_elapsed = time.time() - api_start
            
            if response.status_code != 200:
                failure_message = _build_realtime_failure_message(
                    source_name="腾讯",
                    endpoint=TENCENT_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="http_status",
                    detail=f"HTTP {response.status_code}",
                    elapsed=api_elapsed,
                    error_type="HTTPStatus",
                )
                logger.info(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            content = response.text.strip()
            if '=""' in content or not content:
                failure_message = _build_realtime_failure_message(
                    source_name="腾讯",
                    endpoint=TENCENT_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="empty_response",
                    detail="empty quote payload",
                    elapsed=api_elapsed,
                    error_type="EmptyResponse",
                )
                logger.info(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            # Extracts data
            data_start = content.find('"')
            data_end = content.rfind('"')
            if data_start == -1 or data_end == -1:
                failure_message = _build_realtime_failure_message(
                    source_name="腾讯",
                    endpoint=TENCENT_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="malformed_payload",
                    detail="quote payload missing quotes",
                    elapsed=api_elapsed,
                    error_type="MalformedPayload",
                )
                logger.info(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            data_str = content[data_start+1:data_end]
            fields = data_str.split('~')

            if len(fields) < 45:
                failure_message = _build_realtime_failure_message(
                    source_name="腾讯",
                    endpoint=TENCENT_REALTIME_ENDPOINT,
                    stock_code=stock_code,
                    symbol=symbol,
                    category="insufficient_fields",
                    detail=f"field_count={len(fields)}",
                    elapsed=api_elapsed,
                    error_type="InsufficientFields",
                )
                logger.info(failure_message)
                circuit_breaker.record_failure(source_key, failure_message)
                return None
            
            circuit_breaker.record_success(source_key)
            
            # Tencent data field order (complete):
            # 1: Name 2: Code 3: Latest price 4: Previous close 5: Open 6: Volume 7: Outside volume 8: Inside volume
            # 9-28: Five-level bid/ask data 30: Timestamp 31: Price change 32: Percentage change 33: High 34: Low 35: Price/volume/trading value
            # 36: Volume (scale varies by payload) 37: Trading value (CNY 10,000) 38: Turnover rate (%) 39: P/E ratio 43: Amplitude (%)
            # 44: Circulating market capitalization (in 100 million) 45: Total market capitalization (in 100 million) 46: Price-to-book ratio 47: limit-up price 48: limit-down price 49: Volume ratio
            # Use unified conversion functions in realtime_types.py
            amount = _parse_tencent_amount(fields)
            quote = UnifiedRealtimeQuote(
                code=stock_code,
                name=fields[1] if len(fields) > 1 else "",
                source=RealtimeSource.TENCENT,
                price=safe_float(fields[3]),
                change_pct=safe_float(fields[32]),
                change_amount=safe_float(fields[31]) if len(fields) > 31 else None,
                volume=_normalize_tencent_volume(fields),
                amount=amount,
                open_price=safe_float(fields[5]),
                high=safe_float(fields[33]) if len(fields) > 33 else None,  # Correct: Field 33 is the highest price
                low=safe_float(fields[34]) if len(fields) > 34 else None,  # Correct: Field 34 is the lowest price
                pre_close=safe_float(fields[4]),
                turnover_rate=safe_float(fields[38]) if len(fields) > 38 else None,
                amplitude=safe_float(fields[43]) if len(fields) > 43 else None,
                volume_ratio=safe_float(fields[49]) if len(fields) > 49 else None,  # volume ratio
                pe_ratio=safe_float(fields[39]) if len(fields) > 39 else None,  # Price-to-Earnings Ratio
                pb_ratio=safe_float(fields[46]) if len(fields) > 46 else None,  # Price-to-Book Ratio
                circ_mv=safe_float(fields[44]) * 100000000 if len(fields) > 44 and fields[44] else None,  # Circulating market capitalization (100 million -> yuan)
                total_mv=safe_float(fields[45]) * 100000000 if len(fields) > 45 and fields[45] else None,  # Total market capitalization (100 million -> yuan)
            )
            
            logger.info(
                f"[实时行情-腾讯] {stock_code} {quote.name}: endpoint={TENCENT_REALTIME_ENDPOINT}, "
                f"价格={quote.price}, 涨跌={quote.change_pct}%, 量比={quote.volume_ratio}, "
                f"换手率={quote.turnover_rate}%, elapsed={api_elapsed:.2f}s"
            )
            return quote
            
        except Exception as e:  # broad-exception: fallback_recorded - Provider I/O failure is safely logged before fallback or skip
            category, _ = _classify_realtime_http_error(e)
            log_safe_exception(
                logger,
                "Akshare Tencent realtime quote failed",
                e,
                error_code="akshare_tencent_realtime_quote_failed",
                level=logging.INFO,
                context={
                    "symbol": symbol,
                    "endpoint": TENCENT_REALTIME_ENDPOINT,
                    "category": category,
                },
            )
            circuit_breaker.record_failure(
                source_key,
                "akshare_tencent_realtime_quote_failed",
            )
            return None

    def _get_etf_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        获取 ETF 基金实时行情数据
        
        数据来源：ak.fund_etf_spot_em()
        包含：最新价、涨跌幅、成交量、成交额、换手率等
        
        Args:
            stock_code: ETF 代码
            
        Returns:
            UnifiedRealtimeQuote 对象，获取失败返回 None
        """
        import akshare as ak
        circuit_breaker = get_realtime_circuit_breaker()
        source_key = "akshare_etf"
        
        try:
            # Check the cache
            current_time = time.time()
            df = get_etf_snapshot_if_fresh(current_time)
            if df is None:
                df = None
                for attempt in range(1, 3):
                    try:
                        # Anti-ban strategy
                        self._set_random_user_agent()
                        self._enforce_rate_limit()

                        logger.info(f"[API调用] ak.fund_etf_spot_em() 获取ETF实时行情... (attempt {attempt}/2)")
                        import time as _time
                        api_start = _time.time()

                        df = ak.fund_etf_spot_em()

                        api_elapsed = _time.time() - api_start
                        logger.info(f"[API返回] ak.fund_etf_spot_em 成功: 返回 {len(df)} 只ETF, 耗时 {api_elapsed:.2f}s")
                        circuit_breaker.record_success(source_key)
                        break
                    except Exception as e:  # broad-exception: fallback_recorded - Provider I/O failure is safely logged before fallback or skip
                        log_safe_exception(
                            logger,
                            "Akshare ETF realtime snapshot attempt failed",
                            e,
                            error_code="akshare_etf_realtime_snapshot_failed",
                            level=logging.INFO,
                            context={"attempt": attempt},
                        )
                        time.sleep(min(2 ** attempt, 5))

                if df is None:
                    logger.info("Akshare ETF realtime snapshot failed after retries")
                    circuit_breaker.record_failure(
                        source_key,
                        "akshare_etf_realtime_snapshot_failed",
                    )
                    df = pd.DataFrame()
                store_etf_snapshot(df, current_time)

            if df is None or df.empty:
                logger.info(f"[实时行情] ETF实时行情数据为空，跳过 {stock_code}")
                return None
            
            # Find specified ETF
            row = df[df['代码'] == stock_code]
            if row.empty:
                logger.info(f"[API返回] 未找到 ETF {stock_code} 的实时行情")
                return None
            
            row = row.iloc[0]
            
            # Use unified conversion functions in realtime_types.py
            # ETF Quote Data Construction
            # IOPV / NAV columns vary by AkShare/Eastmoney snapshot version.
            iopv = None
            nav = None
            for key in (
                "IOPV",
                "iopv",
                "估算净值",
                "净值估算",
                "实时估值",
                "基金净值",
            ):
                if key in row.index:
                    iopv = safe_float(row.get(key))
                    if iopv is not None:
                        break
            for key in ("单位净值", "净值", "最新净值", "nav", "NAV"):
                if key in row.index:
                    nav = safe_float(row.get(key))
                    if nav is not None:
                        break
            quote = UnifiedRealtimeQuote(
                code=stock_code,
                name=str(row.get('名称', '')),
                source=RealtimeSource.AKSHARE_EM,
                price=safe_float(row.get('最新价')),
                change_pct=safe_float(row.get('涨跌幅')),
                change_amount=safe_float(row.get('涨跌额')),
                volume=safe_int(row.get('成交量')),
                amount=safe_float(row.get('成交额')),
                volume_ratio=safe_float(row.get('量比')),
                turnover_rate=safe_float(row.get('换手率')),
                amplitude=safe_float(row.get('振幅')),
                open_price=safe_float(row.get('开盘价')),
                high=safe_float(row.get('最高价')),
                low=safe_float(row.get('最低价')),
                total_mv=safe_float(row.get('总市值')),
                circ_mv=safe_float(row.get('流通市值')),
                high_52w=safe_float(row.get('52周最高')),
                low_52w=safe_float(row.get('52周最低')),
                iopv=iopv,
                nav=nav,
            )
            
            logger.info(f"[ETF实时行情] {stock_code} {quote.name}: 价格={quote.price}, 涨跌={quote.change_pct}%, "
                       f"换手率={quote.turnover_rate}%")
            return quote
            
        except Exception as e:  # broad-exception: fallback_recorded - Provider I/O failure is safely logged before fallback or skip
            log_safe_exception(
                logger,
                "Akshare ETF realtime quote failed",
                e,
                error_code="akshare_etf_realtime_quote_failed",
                level=logging.INFO,
                context={"symbol": stock_code},
            )
            circuit_breaker.record_failure(
                source_key,
                "akshare_etf_realtime_quote_failed",
            )
            return None

    def _get_hk_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        获取港股实时行情数据

        主数据源：ak.stock_hk_spot_em()（东方财富）
        备用数据源：ak.stock_hk_spot()（新浪）
        包含：最新价、涨跌幅、成交量、成交额等

        Args:
            stock_code: 港股代码

        Returns:
            UnifiedRealtimeQuote 对象，获取失败返回 None
        """
        import akshare as ak
        circuit_breaker = get_realtime_circuit_breaker()
        em_key = "akshare_hk_em"
        sina_key = "akshare_hk_sina"
        hk_cache = get_hk_cache()

        # Ensure code formatting is correct (5-digit number)
        raw_code = stock_code.strip().lower()
        if raw_code.endswith('.hk'):
            raw_code = raw_code[:-3]
        if raw_code.startswith('hk'):
            raw_code = raw_code[2:]
        code = raw_code.zfill(5)

        def build_em_quote(df: pd.DataFrame) -> Optional[UnifiedRealtimeQuote]:
            if df.empty:
                logger.info("Akshare Eastmoney HK realtime snapshot is empty")
                return None

            row = df[df['代码'] == code]
            if row.empty:
                logger.info(
                    "Akshare Eastmoney HK realtime snapshot has no row for %s",
                    code,
                )
                return None

            row = row.iloc[0]
            quote = UnifiedRealtimeQuote(
                code=stock_code,
                name=str(row.get('名称', '')),
                source=RealtimeSource.AKSHARE_EM,
                price=safe_float(row.get('最新价')),
                change_pct=safe_float(row.get('涨跌幅')),
                change_amount=safe_float(row.get('涨跌额')),
                volume=safe_int(row.get('成交量')),
                amount=safe_float(row.get('成交额')),
                volume_ratio=safe_float(row.get('量比')),
                turnover_rate=safe_float(row.get('换手率')),
                amplitude=safe_float(row.get('振幅')),
                pe_ratio=safe_float(row.get('市盈率')),
                pb_ratio=safe_float(row.get('市净率')),
                total_mv=safe_float(row.get('总市值')),
                circ_mv=safe_float(row.get('流通市值')),
                high_52w=safe_float(row.get('52周最高')),
                low_52w=safe_float(row.get('52周最低')),
            )
            logger.info(
                "Akshare HK realtime quote resolved for %s: price=%s change_pct=%s turnover_rate=%s",
                stock_code,
                quote.price,
                quote.change_pct,
                quote.turnover_rate,
            )
            return quote

        def read_cached_em_quote() -> Tuple[bool, Optional[UnifiedRealtimeQuote]]:
            cache_hit, cache_data = lookup_hk_em_snapshot()
            if not cache_hit:
                return False, None
            if cache_data is None:
                # Active failure-TTL (negative cache): skip EM refresh.
                return True, None
            try:
                return True, build_em_quote(cache_data)
            except Exception as exc:  # broad-exception: fallback_recorded - Safe diagnostics precede the preserved Sina fallback.
                log_safe_exception(
                    logger,
                    "Akshare Eastmoney HK realtime cache parse failed; trying Sina fallback",
                    exc,
                    error_code="akshare_hk_eastmoney_cache_parse_failed",
                    level=logging.WARNING,
                    context={"symbol": stock_code},
                )
                return True, None

        cache_hit, quote = read_cached_em_quote()
        if quote is not None:
            return quote

        # Coalesce concurrent full-market refreshes and recheck after acquiring
        # the lock so only one request populates a cold cache.
        if not cache_hit:
            with hk_refresh_lock():
                cache_hit, quote = read_cached_em_quote()
                if quote is not None:
                    return quote

                if circuit_breaker.is_available(em_key) and not cache_hit:
                    try:
                        # Rate limiting applies only to a real network refresh;
                        # hot-cache reads should return without artificial delay.
                        self._set_random_user_agent()
                        self._enforce_rate_limit()

                        logger.info("Fetching Akshare Eastmoney HK realtime market snapshot")
                        api_start = time.time()
                        df = ak.stock_hk_spot_em()
                        api_elapsed = time.time() - api_start

                        if not isinstance(df, pd.DataFrame):
                            raise TypeError("stock_hk_spot_em did not return a DataFrame")
                        if '代码' not in df.columns:
                            raise KeyError("stock_hk_spot_em response is missing the code column")
                        if df.empty:
                            raise ValueError("stock_hk_spot_em returned an empty market snapshot")

                        record_hk_refresh_success(df)
                        logger.info(
                            "Cached Akshare Eastmoney HK realtime snapshot: records=%d elapsed=%.2fs ttl=%ss",
                            len(df),
                            api_elapsed,
                            hk_cache['ttl'],
                        )

                        quote = build_em_quote(df)
                        circuit_breaker.record_success(em_key)
                        if quote is not None:
                            return quote
                    except Exception as exc:  # broad-exception: fallback_recorded - Safe diagnostics and circuit state preserve the Sina fallback.
                        record_hk_refresh_failure()
                        log_safe_exception(
                            logger,
                            "Akshare Eastmoney HK realtime quote failed; trying Sina fallback",
                            exc,
                            error_code="akshare_hk_eastmoney_realtime_quote_failed",
                            level=logging.WARNING,
                            context={"symbol": stock_code},
                        )
                        circuit_breaker.record_failure(
                            em_key,
                            "akshare_hk_eastmoney_realtime_quote_failed",
                        )
                elif not cache_hit:
                    logger.info(
                        "Akshare Eastmoney HK realtime circuit is open; trying Sina fallback"
                    )

        # --- Backup Data Source: Sina ---
        if not circuit_breaker.is_available(sina_key):
            logger.info(f"[熔断] 数据源 {sina_key} 处于熔断状态，跳过备用链路")
            return None

        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            logger.info(f"[API调用] ak.stock_hk_spot() 获取港股实时行情（备用）...")
            import time as _time
            api_start = _time.time()

            df_spot = ak.stock_hk_spot()

            api_elapsed = _time.time() - api_start
            logger.info(f"[API返回] ak.stock_hk_spot 成功: 返回 {len(df_spot)} 只港股, 耗时 {api_elapsed:.2f}s")

            row = df_spot[df_spot['代码'] == code]
            if row.empty:
                logger.info(f"[API返回] 未找到港股 {code} 的实时行情 (stock_hk_spot)")
                return None

            row = row.iloc[0]
            quote = UnifiedRealtimeQuote(
                code=stock_code,
                name=str(row.get('名称', '')),
                source=RealtimeSource.AKSHARE_SINA,
                price=safe_float(row.get('最新价')),
                change_pct=safe_float(row.get('涨跌幅')),
                change_amount=safe_float(row.get('涨跌额')),
                volume=safe_int(row.get('成交量')),
                amount=safe_float(row.get('成交额')),
            )
            circuit_breaker.record_success(sina_key)
            logger.info(f"[港股实时行情-备用] {stock_code} {quote.name}: 价格={quote.price}, 涨跌={quote.change_pct}%")
            return quote

        except Exception as e:  # broad-exception: fallback_recorded - Safe diagnostics and circuit state preserve provider failover.
            log_safe_exception(
                logger,
                "Akshare Sina HK realtime quote fallback failed",
                e,
                error_code="akshare_hk_sina_realtime_quote_failed",
                level=logging.INFO,
                context={"symbol": stock_code},
            )
            circuit_breaker.record_failure(
                sina_key,
                "akshare_hk_sina_realtime_quote_failed",
            )
            return None



def _rebind_loaded_facade() -> None:
    hook = _FACADE_RELOAD_HOOK
    if hook is not None:
        hook()


_rebind_loaded_facade()
