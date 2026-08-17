# -*- coding: utf-8 -*-
"""AkShare market overview boards: indices, stats, rankings, hot, limit-up.

Method bodies are rebound onto ``AkshareFetcher`` by the compatibility facade
(ADR-006) so free-name lookups and test patches stay on
``data_provider.akshare_fetcher``.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from src.utils.sanitize import log_safe_exception

logger = logging.getLogger("data_provider.akshare_fetcher")
safe_float = None  # type: ignore[assignment]
safe_int = None  # type: ignore[assignment]
normalize_stock_code = None  # type: ignore[assignment]
is_bse_code = None  # type: ignore[assignment]
is_kc_cy_stock = None  # type: ignore[assignment]
is_st_stock = None  # type: ignore[assignment]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _MarketBoardsMethods:
    """Source descriptors rebound onto ``AkshareFetcher``."""

    def get_main_indices(self, region: str = "cn") -> Optional[List[Dict[str, Any]]]:
        """
        获取主要指数实时行情 (新浪接口)，仅支持 A 股
        """
        if region != "cn":
            return None
        import akshare as ak

        # Major Index Code Mapping
        indices_map = {
            'sh000001': '上证指数',
            'sz399001': '深证成指',
            'sz399006': '创业板指',
            'sh000688': '科创50',
            'sh000016': '上证50',
            'sh000300': '沪深300',
        }

        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            # Use akshare to get stock market data (Sina Finance interface).
            df = ak.stock_zh_index_spot_sina()

            results = []
            if df is not None and not df.empty:
                for code, name in indices_map.items():
                    # Find corresponding index
                    row = df[df['代码'] == code]
                    if row.empty:
                        # Attempt to search with prefix
                        row = df[df['代码'].str.contains(code)]

                    if not row.empty:
                        row = row.iloc[0]
                        current = safe_float(row.get('最新价', 0))
                        prev_close = safe_float(row.get('昨收', 0))
                        high = safe_float(row.get('最高', 0))
                        low = safe_float(row.get('最低', 0))

                        # Calculate Amplitude
                        amplitude = 0.0
                        if prev_close > 0:
                            amplitude = (high - low) / prev_close * 100

                        results.append({
                            'code': code,
                            'name': name,
                            'current': current,
                            'change': safe_float(row.get('涨跌额', 0)),
                            'change_pct': safe_float(row.get('涨跌幅', 0)),
                            'open': safe_float(row.get('今开', 0)),
                            'high': high,
                            'low': low,
                            'prev_close': prev_close,
                            'volume': safe_float(row.get('成交量', 0)),
                            'amount': safe_float(row.get('成交额', 0)),
                            'amplitude': amplitude,
                        })
            return results

        except Exception as e:  # broad-exception: fallback_recorded - Provider I/O failure is safely logged before fallback or skip
            log_safe_exception(
                logger,
                "Akshare market indices fetch failed",
                e,
                error_code="akshare_market_indices_failed",
                level=logging.ERROR,
                context={"market": region},
            )
            return None

    def get_market_stats(self) -> Optional[Dict[str, Any]]:
        """
        获取市场涨跌统计

        数据源优先级：
        1. 东财接口 (ak.stock_zh_a_spot_em)
        2. 新浪接口 (ak.stock_zh_a_spot)
        """
        import akshare as ak

        # Prioritize Eastmoney interface
        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            started_at = time.monotonic()
            logger.info(
                "[MarketStats] component=market_stats provider=AkshareFetcher "
                "api=ak.stock_zh_a_spot_em action=request_start"
            )
            df = ak.stock_zh_a_spot_em()
            elapsed = time.monotonic() - started_at
            logger.info(
                "[MarketStats] component=market_stats provider=AkshareFetcher "
                "api=ak.stock_zh_a_spot_em action=request_complete elapsed=%.2fs",
                elapsed,
            )
            if df is not None and not df.empty:
                return self._calc_market_stats(df)
            logger.warning(
                "[MarketStats] component=market_stats provider=AkshareFetcher "
                "api=ak.stock_zh_a_spot_em action=parse status=empty"
            )
        except Exception as e:  # broad-exception: fallback_recorded - Provider I/O failure is safely logged before fallback or skip
            log_safe_exception(
                logger,
                "Akshare Eastmoney market statistics failed; trying Sina fallback",
                e,
                error_code="akshare_eastmoney_market_stats_failed",
                level=logging.WARNING,
            )

        # After Eastmoney failure, try Sina interface
        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            started_at = time.monotonic()
            logger.info(
                "[MarketStats] component=market_stats provider=AkshareFetcher "
                "api=ak.stock_zh_a_spot action=request_start"
            )
            df = ak.stock_zh_a_spot()
            elapsed = time.monotonic() - started_at
            logger.info(
                "[MarketStats] component=market_stats provider=AkshareFetcher "
                "api=ak.stock_zh_a_spot action=request_complete elapsed=%.2fs",
                elapsed,
            )
            if df is not None and not df.empty:
                return self._calc_market_stats(df)
            logger.warning(
                "[MarketStats] component=market_stats provider=AkshareFetcher "
                "api=ak.stock_zh_a_spot action=parse status=empty"
            )
        except Exception as e:  # broad-exception: fallback_recorded - Provider I/O failure is safely logged before fallback or skip
            log_safe_exception(
                logger,
                "Akshare Sina market statistics fallback failed",
                e,
                error_code="akshare_sina_market_stats_failed",
                level=logging.ERROR,
            )

        return None

    def _calc_market_stats(
        self,
        df: pd.DataFrame,
        ) -> Optional[Dict[str, Any]]:
        """从行情 DataFrame 计算涨跌统计。"""
        import numpy as np

        df = df.copy()
        
        # 1. Extracts basic comparison data: latest price, previous close
        # Compatible with column names returned from different interfaces sina/em efinance tushare xtdata
        code_col = next((c for c in ['代码', '股票代码', 'ts_code','stock_code'] if c in df.columns), None)
        name_col = next((c for c in ['名称', '股票名称','name','name'] if c in df.columns), None)
        close_col = next((c for c in ['最新价', '最新价', 'close','lastPrice'] if c in df.columns), None)
        pre_close_col = next((c for c in ['昨收', '昨日收盘', 'pre_close','lastClose'] if c in df.columns), None)
        amount_col = next((c for c in ['成交额', '成交额', 'amount','amount'] if c in df.columns), None) 
        
        limit_up_count = 0
        limit_down_count = 0
        up_count = 0
        down_count = 0
        flat_count = 0

        for code, name, current_price, pre_close, amount in zip(
            df[code_col], df[name_col], df[close_col], df[pre_close_col], df[amount_col]
        ):
            
            # Pause filtering of efinance's pause data sometimes missing price display as '-', em display as none
            if pd.isna(current_price) or pd.isna(pre_close) or current_price in ['-'] or pre_close in ['-'] or amount == 0:
                continue
            
            # em and efinance may return strings; convert them to floats
            current_price = float(current_price)
            pre_close = float(pre_close)
            
            # Get pure numeric code without prefix
            pure_code = normalize_stock_code(str(code)) 

            # A. Determine the percentage change of each stock (using pure numeric codes to judge)
            if is_bse_code(pure_code): 
                ratio = 0.30
            elif is_kc_cy_stock(pure_code): #pure_code.startswith(('688', '30')):
                ratio = 0.20
            elif is_st_stock(name): #'ST' in str_name:
                ratio = 0.05
            else:
                ratio = 0.10

            # B. Calculate A-share limit-up and limit-down prices strictly: previous close * (1 +/- percentage), rounded to two decimals.
            limit_up_price = np.floor(pre_close * (1 + ratio) * 100 + 0.5) / 100.0
            limit_down_price = np.floor(pre_close * (1 - ratio) * 100 + 0.5) / 100.0

            limit_up_price_Tolerance = round(abs(pre_close * (1 + ratio) - limit_up_price), 10)
            limit_down_price_Tolerance = round(abs(pre_close * (1 - ratio) - limit_down_price), 10)

            # C. Exact matching
            if current_price > 0 :
                is_limit_up = (current_price > 0) and (abs(current_price - limit_up_price) <= limit_up_price_Tolerance)
                is_limit_down = (current_price > 0) and (abs(current_price - limit_down_price) <= limit_down_price_Tolerance)

                if is_limit_up:
                    limit_up_count += 1
                if is_limit_down:
                    limit_down_count += 1

                if current_price > pre_close:
                    up_count += 1
                elif current_price < pre_close:
                    down_count += 1
                else:
                    flat_count += 1
                
        # Count quantity
        stats = {
            'up_count': up_count,
            'down_count': down_count,
            'flat_count': flat_count,
            'limit_up_count': limit_up_count,
            'limit_down_count': limit_down_count,
            'total_amount': 0.0,
        }
        
        # trading value statistics
        if amount_col and amount_col in df.columns:
            df[amount_col] = pd.to_numeric(df[amount_col], errors='coerce')
            stats['total_amount'] = (df[amount_col].sum() / 1e8)
            
        return stats

    def get_sector_rankings(self, n: int = 5) -> Optional[Tuple[List[Dict], List[Dict]]]:
        """
        获取行业板块涨跌榜

        数据源优先级：
        1. 东财接口 (ak.stock_board_industry_name_em)
        2. 新浪接口 (ak.stock_sector_spot)
        """
        import akshare as ak

        def _get_rank_top_n(df: pd.DataFrame, change_col: str, industry_name: str, n: int) -> Tuple[list, list]:
            df[change_col] = pd.to_numeric(df[change_col], errors='coerce')
            df = df.dropna(subset=[change_col])

            # Top N rising
            top = df.nlargest(n, change_col)
            top_sectors = [
                {'name': row[industry_name], 'change_pct': row[change_col]}
                for _, row in top.iterrows()
            ]

            bottom = df.nsmallest(n, change_col)
            bottom_sectors = [
                {'name': row[industry_name], 'change_pct': row[change_col]}
                for _, row in bottom.iterrows()
            ]
            return top_sectors, bottom_sectors
        
        # Prioritize Eastmoney interface
        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            logger.info("[API调用] ak.stock_board_industry_name_em() 获取板块排行...")
            df = ak.stock_board_industry_name_em()
            if df is not None and not df.empty:
                change_col = '涨跌幅'
                name = '板块名称'
                return _get_rank_top_n(df, change_col, name, n)
            
        except Exception as e:  # broad-exception: fallback_recorded - Provider I/O failure is safely logged before fallback or skip
            log_safe_exception(
                logger,
                "Akshare Eastmoney sector ranking failed; trying Sina fallback",
                e,
                error_code="akshare_eastmoney_sector_ranking_failed",
                level=logging.WARNING,
            )

        # After Eastmoney failure, try Sina interface
        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            logger.info("[API调用] ak.stock_sector_spot() 获取行业板块排行(新浪)...")
            df = ak.stock_sector_spot(indicator='行业')
            if df is None or df.empty:
                return None
            change_col = '涨跌幅'
            name = '板块'
            return _get_rank_top_n(df, change_col, name, n)
        
        except Exception as e:  # broad-exception: fallback_recorded - Provider I/O failure is safely logged before fallback or skip
            log_safe_exception(
                logger,
                "Akshare Sina sector ranking fallback failed",
                e,
                error_code="akshare_sina_sector_ranking_failed",
                level=logging.ERROR,
            )
            return None

    def get_concept_rankings(self, n: int = 5) -> Optional[Tuple[List[Dict], List[Dict]]]:
        """获取概念/题材涨跌榜。"""
        import akshare as ak

        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            logger.info("[API调用] ak.stock_board_concept_name_em() 获取概念排行...")
            df = ak.stock_board_concept_name_em()
            if df is None or df.empty:
                return None

            change_col = '涨跌幅'
            name_col = '板块名称'
            if change_col not in df.columns or name_col not in df.columns:
                return None

            df = df.copy()
            df[change_col] = pd.to_numeric(df[change_col], errors='coerce')
            df = df.dropna(subset=[change_col])
            top = df.nlargest(n, change_col)
            bottom = df.nsmallest(n, change_col)
            return (
                [
                    {'name': str(row[name_col]), 'change_pct': float(row[change_col])}
                    for _, row in top.iterrows()
                ],
                [
                    {'name': str(row[name_col]), 'change_pct': float(row[change_col])}
                    for _, row in bottom.iterrows()
                ],
            )
        except Exception as e:  # broad-exception: fallback_recorded - Provider I/O failure is safely logged before fallback or skip
            log_safe_exception(
                logger,
                "Akshare concept ranking fetch failed",
                e,
                error_code="akshare_concept_ranking_failed",
                level=logging.WARNING,
            )
            return None

    def get_hot_stocks(self, n: int = 10) -> Optional[List[Dict[str, Any]]]:
        """获取人气股榜，按免配置热榜数据源降级。"""
        import akshare as ak

        fetch_attempts = (
            ("东方财富人气榜", lambda top_n: self._get_eastmoney_hot_stocks(ak, top_n)),
            ("东方财富飙升榜", lambda top_n: self._get_eastmoney_hot_up_stocks(ak, top_n)),
            ("雪球关注榜", lambda top_n: self._get_xueqiu_hot_stocks(ak, top_n)),
        )
        had_error = False
        for source, fetch in fetch_attempts:
            try:
                rows = fetch(n)
                if rows:
                    return rows[:n]
            except Exception as e:  # broad-exception: fallback_recorded - Provider I/O failure is safely logged before fallback or skip
                had_error = True
                log_safe_exception(
                    logger,
                    "Akshare hot stock source failed",
                    e,
                    error_code="akshare_hot_stock_source_failed",
                    level=logging.DEBUG,
                    context={"source": source},
                )
        if had_error:
            logger.warning("Akshare hot stock sources returned no data")
        return None

    def _get_eastmoney_hot_stocks(self, ak: Any, n: int = 10) -> Optional[List[Dict[str, Any]]]:
        """获取东方财富人气股榜。"""
        self._set_random_user_agent()
        self._enforce_rate_limit()

        logger.info("[API调用] ak.stock_hot_rank_em() 获取东方财富人气股...")
        df = ak.stock_hot_rank_em()
        if df is None or df.empty:
            return None

        rows: List[Dict[str, Any]] = []
        for _, row in df.head(n).iterrows():
            rows.append({
                'rank': self._safe_int(row.get('当前排名')),
                'code': str(row.get('代码', '')).strip(),
                'name': str(row.get('股票名称', '')).strip(),
                'price': self._safe_float(row.get('最新价')),
                'change_pct': self._safe_float(row.get('涨跌幅')),
                'source': '东方财富人气榜',
            })
        return rows

    def _get_eastmoney_hot_up_stocks(self, ak: Any, n: int = 10) -> Optional[List[Dict[str, Any]]]:
        """获取东方财富飙升榜。"""
        self._set_random_user_agent()
        self._enforce_rate_limit()

        logger.info("[API调用] ak.stock_hot_up_em() 获取东方财富飙升榜...")
        df = ak.stock_hot_up_em()
        if df is None or df.empty:
            return None

        code_col = self._find_first_column(df, ("代码", "股票代码"))
        name_col = self._find_first_column(df, ("股票名称", "名称", "股票简称"))
        rank_col = self._find_first_column(df, ("当前排名", "排名", "序号"))
        price_col = self._find_first_column(df, ("最新价", "现价"))
        change_col = self._find_column_containing(df, ("涨跌幅",))
        if not code_col or not name_col:
            return None

        rows: List[Dict[str, Any]] = []
        for _, row in df.head(n).iterrows():
            rows.append({
                'rank': self._safe_int(row.get(rank_col)) if rank_col else len(rows) + 1,
                'code': str(row.get(code_col, '')).strip(),
                'name': str(row.get(name_col, '')).strip(),
                'price': self._safe_float(row.get(price_col)) if price_col else None,
                'change_pct': self._safe_float(row.get(change_col)) if change_col else None,
                'source': '东方财富飙升榜',
            })
        return rows

    def _get_xueqiu_hot_stocks(self, ak: Any, n: int = 10) -> Optional[List[Dict[str, Any]]]:
        """获取雪球关注榜兜底。该接口较慢，仅在人气榜失败后尝试。"""
        self._set_random_user_agent()
        self._enforce_rate_limit()

        logger.info("[API调用] ak.stock_hot_follow_xq() 获取雪球关注榜...")
        df = ak.stock_hot_follow_xq(symbol='最热门')
        if df is None or df.empty:
            return None

        rows: List[Dict[str, Any]] = []
        for idx, (_, row) in enumerate(df.head(n).iterrows(), 1):
            rows.append({
                'rank': idx,
                'code': str(row.get('股票代码', '')).strip(),
                'name': str(row.get('股票简称', '')).strip(),
                'price': self._safe_float(row.get('最新价')),
                'change_pct': None,
                'source': '雪球关注榜',
            })
        return rows

    def get_limit_up_pool(
        self,
        date: Optional[str] = None,
        n: int = 20,
    ) -> Optional[List[Dict[str, Any]]]:
        """获取涨停池，优先按连板数和封板时间展示。"""
        import akshare as ak

        query_date = date or datetime.now().strftime('%Y%m%d')
        try:
            self._set_random_user_agent()
            self._enforce_rate_limit()

            logger.info("[API调用] ak.stock_zt_pool_em(date=%s) 获取涨停池...", query_date)
            df = ak.stock_zt_pool_em(date=query_date)
            if df is None or df.empty:
                return None

            df = df.copy()
            for col in ('连板数', '封板资金', '成交额', '换手率', '涨跌幅'):
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            if '首次封板时间' in df.columns:
                df['首次封板时间'] = df['首次封板时间'].map(self._normalize_limit_time_value)
                df['_首次封板时间排序'] = df['首次封板时间'].where(df['首次封板时间'] != '', '999999')
            sort_cols = [col for col in ('连板数', '_首次封板时间排序') if col in df.columns]
            if sort_cols:
                ascending = [False if col == '连板数' else True for col in sort_cols]
                df = df.sort_values(sort_cols, ascending=ascending)

            rows: List[Dict[str, Any]] = []
            for _, row in df.head(n).iterrows():
                rows.append({
                    'code': str(row.get('代码', '')).strip(),
                    'name': str(row.get('名称', '')).strip(),
                    'change_pct': self._safe_float(row.get('涨跌幅')),
                    'price': self._safe_float(row.get('最新价')),
                    'amount': self._safe_float(row.get('成交额')),
                    'turnover_rate': self._safe_float(row.get('换手率')),
                    'seal_amount': self._safe_float(row.get('封板资金')),
                    'first_limit_time': str(row.get('首次封板时间', '')).strip(),
                    'last_limit_time': self._normalize_limit_time_value(row.get('最后封板时间')),
                    'break_count': self._safe_int(row.get('炸板次数')),
                    'limit_stat': str(row.get('涨停统计', '')).strip(),
                    'consecutive_boards': self._safe_int(row.get('连板数')),
                    'industry': str(row.get('所属行业', '')).strip(),
                })
            return rows
        except Exception as e:  # broad-exception: fallback_recorded - Provider I/O failure is safely logged before fallback or skip
            log_safe_exception(
                logger,
                "Akshare limit-up pool fetch failed",
                e,
                error_code="akshare_limit_up_pool_failed",
                level=logging.WARNING,
            )
            return None

    @staticmethod
    def _normalize_limit_time_value(value: Any) -> str:
        """Normalize AkShare HHMMSS-like seal time values to zero-padded HHMMSS."""
        try:
            if pd.isna(value):
                return ""
        except TypeError:
            pass

        text = str(value).strip()
        if not text or text.lower() in {"nan", "nat", "none", "null", "-", "--"}:
            return ""

        if ":" in text:
            parts = text.split(":")
            try:
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
                second = int(parts[2]) if len(parts) > 2 else 0
                return f"{hour:02d}{minute:02d}{second:02d}"
            except (TypeError, ValueError):
                return text

        try:
            return f"{int(float(text)):06d}"
        except (TypeError, ValueError):
            digits = "".join(ch for ch in text if ch.isdigit())
            return digits.zfill(6) if digits else text

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            if pd.isna(value):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            if pd.isna(value):
                return 0
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _find_first_column(df: pd.DataFrame, candidates: Tuple[str, ...]) -> Optional[str]:
        columns = [str(col) for col in df.columns]
        for candidate in candidates:
            if candidate in columns:
                return candidate
        return None

    @staticmethod
    def _find_column_containing(df: pd.DataFrame, keywords: Tuple[str, ...]) -> Optional[str]:
        for col in df.columns:
            col_text = str(col)
            if all(keyword in col_text for keyword in keywords):
                return col
        return None



def _rebind_loaded_facade() -> None:
    hook = _FACADE_RELOAD_HOOK
    if hook is not None:
        hook()


_rebind_loaded_facade()
