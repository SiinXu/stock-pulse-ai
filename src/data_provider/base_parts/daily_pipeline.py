# -*- coding: utf-8 -*-
"""BaseFetcher daily-data template method and its post-processing steps.

Method bodies are rebound onto ``BaseFetcher`` by the compatibility facade
(ADR-006) so free-name lookups and test patches stay on
``src.data_provider.base``.

``get_daily_data`` is a template method: it calls ``_fetch_raw_data`` and
``_normalize_data``, which stay abstract on ``BaseFetcher`` and are implemented
by each provider subclass. Those, plus ``name`` and ``allow_empty_daily_data``,
resolve through ``self`` at call time, so every existing subclass override keeps
working without change.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple, Type

import pandas as pd

from src.utils.sanitize import log_safe_exception

from .facade_bind import bind_methods_from_class

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``src.data_provider.base`` globals at runtime (ADR-006).
logger = logging.getLogger("src.data_provider.base")
DataFetchError = Exception  # type: ignore[assignment,misc]
STANDARD_COLUMNS = ()  # type: ignore[assignment]
summarize_exception = None  # type: ignore[assignment]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _DailyPipelineMethods:
    """Source descriptors rebound onto ``BaseFetcher``."""

    def get_daily_data(
        self,
        stock_code: str, 
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days: int = 30
    ) -> pd.DataFrame:
        """
        获取日线数据（统一入口）
        
        流程：
        1. 计算日期范围
        2. 调用子类获取原始数据
        3. 标准化列名
        4. 计算技术指标
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期（可选）
            end_date: 结束日期（可选，默认今天）
            days: 获取天数（当 start_date 未指定时使用）
            
        Returns:
            标准化的 DataFrame，包含技术指标
        """
        # Calculate Date Range
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        if start_date is None:
            # Defaults to the most recent 30 trading days (estimated by calendar day, taking more if available)
            from datetime import timedelta
            start_dt = datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=days * 2)
            start_date = start_dt.strftime('%Y-%m-%d')

        request_start = time.time()
        logger.info(f"[{self.name}] 开始获取 {stock_code} 日线数据: 范围={start_date} ~ {end_date}")
        
        try:
            # Step 1: Get raw data
            raw_df = self._fetch_raw_data(stock_code, start_date, end_date)
            
            if raw_df is None:
                raise DataFetchError(f"[{self.name}] 未获取到 {stock_code} 的数据")
            if raw_df.empty:
                elapsed = time.time() - request_start
                logger.info(
                    f"[{self.name}] {stock_code} 返回空日线结果: 范围={start_date} ~ {end_date}, "
                    f"elapsed={elapsed:.2f}s"
                )
                if self.allow_empty_daily_data:
                    return pd.DataFrame(columns=STANDARD_COLUMNS)
                raise DataFetchError(f"[{self.name}] 未获取到 {stock_code} 的数据")
            
            # Step 2: Standardize Column Names
            df = self._normalize_data(raw_df, stock_code)
            
            # Step 3: Data Cleaning
            df = self._clean_data(df)
            
            # Step 4: Calculate Technical Indicators
            df = self._calculate_indicators(df)

            elapsed = time.time() - request_start
            logger.info(
                f"[{self.name}] {stock_code} 获取成功: 范围={start_date} ~ {end_date}, "
                f"rows={len(df)}, elapsed={elapsed:.2f}s"
            )
            return df
            
        except Exception as e:
            error_type, error_reason = summarize_exception(e)
            log_safe_exception(
                logger,
                "Data provider daily data fetch failed",
                e,
                error_code="data_provider_daily_data_failed",
                level=logging.ERROR,
                context={"symbol": stock_code, "provider": self.name},
            )
            raise DataFetchError(f"[{self.name}] {stock_code}: {error_reason}") from e

    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        数据清洗
        
        处理：
        1. 确保日期列格式正确
        2. 数值类型转换
        3. 去除空值行
        4. 按日期排序
        """
        df = df.copy()
        
        # Ensure the date column is of datetime type
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        
        # Value column type conversion
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Remove rows with empty key columns
        df = df.dropna(subset=['close', 'volume'])
        
        # Sort by date in ascending order.
        df = df.sort_values('date', ascending=True).reset_index(drop=True)
        
        return df

    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算技术指标
        
        计算指标：
        - MA5, MA10, MA20: 移动平均线
        - Volume_Ratio: 量比（今日成交量 / 5日平均成交量）
        """
        df = df.copy()
        
        # Moving Average
        df['ma5'] = df['close'].rolling(window=5, min_periods=1).mean()
        df['ma10'] = df['close'].rolling(window=10, min_periods=1).mean()
        df['ma20'] = df['close'].rolling(window=20, min_periods=1).mean()
        
        # Relative Volume: Daily Trading Volume / 5-Day Average Trading Volume
        # Note: This volume_ratio is the relative multiple of 'daily trading volume / 5-day average (shift 1)'.
        # This differs from the intraday volume ratio used by some trading tools (same-time comparison) and is closer to a volume-expansion multiple.
        # This behavior is currently retained (logic will not be modified based on demand).
        avg_volume_5 = df['volume'].rolling(window=5, min_periods=1).mean()
        df['volume_ratio'] = df['volume'] / avg_volume_5.shift(1)
        df['volume_ratio'] = df['volume_ratio'].fillna(1.0)
        
        # Retain two decimal places
        for col in ['ma5', 'ma10', 'ma20', 'volume_ratio']:
            if col in df.columns:
                df[col] = df[col].round(2)
        
        return df

EXPECTED_DAILY_PIPELINE_METHOD_NAMES: Tuple[str, ...] = (
    "get_daily_data",
    "_clean_data",
    "_calculate_indicators",
)


def bind_daily_pipeline_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind daily-pipeline descriptors without changing the fetcher API."""

    return bind_methods_from_class(
        _DailyPipelineMethods,
        target_class,
        global_namespace,
        expected_names=EXPECTED_DAILY_PIPELINE_METHOD_NAMES,
    )


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
