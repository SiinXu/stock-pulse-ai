# -*- coding: utf-8 -*-
"""efinance stock-path realtime quote method.

Method bodies are rebound onto ``EfinanceFetcher`` by the compatibility facade
(ADR-006) so free-name lookups and test patches stay on
``src.data_provider.efinance_fetcher``.

No module-level helper moves with this slice. ``_realtime_cache`` and the
timeout / circuit-breaker helpers stay on the facade so ``get_market_stats``
and the moved quote path share the same objects. ETF codes still dispatch
through ``self._get_etf_realtime_quote``.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, Optional, Tuple, Type

from src.utils.sanitize import log_safe_exception

from .facade_bind import bind_methods_from_class

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``src.data_provider.efinance_fetcher`` globals at runtime (ADR-006).
logger = logging.getLogger("src.data_provider.efinance_fetcher")
FuturesTimeoutError = TimeoutError  # type: ignore[assignment,misc]
RealtimeSource = None  # type: ignore[assignment]
UnifiedRealtimeQuote = None  # type: ignore[assignment]
_EF_CALL_TIMEOUT = 0  # type: ignore[assignment]
_ef_call_with_timeout = None  # type: ignore[assignment]
_is_etf_code = None  # type: ignore[assignment]
_realtime_cache = None  # type: ignore[assignment]
get_realtime_circuit_breaker = None  # type: ignore[assignment]
safe_float = None  # type: ignore[assignment]
safe_int = None  # type: ignore[assignment]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _RealtimeMethods:
    """Source descriptors rebound onto ``EfinanceFetcher``."""

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        获取实时行情数据
        
        数据来源：ef.stock.get_realtime_quotes()
        ETF 数据源：ef.stock.get_realtime_quotes(['ETF'])
        
        Args:
            stock_code: 股票代码
            
        Returns:
            UnifiedRealtimeQuote 对象，获取失败返回 None
        """
        # ETFs require separate requests to the ETF real-time quote interface
        if _is_etf_code(stock_code):
            return self._get_etf_realtime_quote(stock_code)

        import efinance as ef
        circuit_breaker = get_realtime_circuit_breaker()
        source_key = "efinance"
        
        # Check the circuit breaker status
        if not circuit_breaker.is_available(source_key):
            logger.info(f"[熔断] 数据源 {source_key} 处于熔断状态，跳过")
            return None
        
        try:
            # Check the cache
            current_time = time.time()
            if (_realtime_cache['data'] is not None and 
                current_time - _realtime_cache['timestamp'] < _realtime_cache['ttl']):
                df = _realtime_cache['data']
                cache_age = int(current_time - _realtime_cache['timestamp'])
                logger.debug(f"[缓存命中] 实时行情(efinance) - 缓存年龄 {cache_age}s/{_realtime_cache['ttl']}s")
            else:
                # Trigger full refresh
                logger.info(f"[缓存未命中] 触发全量刷新 实时行情(efinance)")
                # Anti-ban strategy
                self._set_random_user_agent()
                self._enforce_rate_limit()
                
                logger.info(f"[API调用] ef.stock.get_realtime_quotes() 获取实时行情...")
                import time as _time
                api_start = _time.time()
                
                # efinance Real-time quotes API (with timeout to avoid indefinite hangs)
                df = _ef_call_with_timeout(ef.stock.get_realtime_quotes)
                
                api_elapsed = _time.time() - api_start
                logger.info(f"[API返回] ef.stock.get_realtime_quotes 成功: 返回 {len(df)} 只股票, 耗时 {api_elapsed:.2f}s")
                circuit_breaker.record_success(source_key)
                
                # Update cache
                _realtime_cache['data'] = df
                _realtime_cache['timestamp'] = current_time
                logger.info(f"[缓存更新] 实时行情(efinance) 缓存已刷新，TTL={_realtime_cache['ttl']}s")
            
            # Find specified stock
            # '股票代码' or 'code' might be the column names returned by efinance.
            code_col = '股票代码' if '股票代码' in df.columns else 'code'
            row = df[df[code_col] == stock_code]
            if row.empty:
                logger.info(f"[API返回] 未找到股票 {stock_code} 的实时行情")
                return None
            
            row = row.iloc[0]
            
            # Use unified conversion functions in realtime_types.py
            # Get column names (may be Chinese or English)
            name_col = '股票名称' if '股票名称' in df.columns else 'name'
            price_col = '最新价' if '最新价' in df.columns else 'price'
            pct_col = '涨跌幅' if '涨跌幅' in df.columns else 'pct_chg'
            chg_col = '涨跌额' if '涨跌额' in df.columns else 'change'
            vol_col = '成交量' if '成交量' in df.columns else 'volume'
            amt_col = '成交额' if '成交额' in df.columns else 'amount'
            turn_col = '换手率' if '换手率' in df.columns else 'turnover_rate'
            amp_col = '振幅' if '振幅' in df.columns else 'amplitude'
            high_col = '最高' if '最高' in df.columns else 'high'
            low_col = '最低' if '最低' in df.columns else 'low'
            open_col = '开盘' if '开盘' in df.columns else 'open'
            # Efinance also returns fields such as volume ratio, P/E ratio, market capitalization, etc.
            vol_ratio_col = '量比' if '量比' in df.columns else 'volume_ratio'
            pe_col = '市盈率' if '市盈率' in df.columns else 'pe_ratio'
            total_mv_col = '总市值' if '总市值' in df.columns else 'total_mv'
            circ_mv_col = '流通市值' if '流通市值' in df.columns else 'circ_mv'
            
            quote = UnifiedRealtimeQuote(
                code=stock_code,
                name=str(row.get(name_col, '')),
                source=RealtimeSource.EFINANCE,
                price=safe_float(row.get(price_col)),
                change_pct=safe_float(row.get(pct_col)),
                change_amount=safe_float(row.get(chg_col)),
                volume=safe_int(row.get(vol_col)),
                amount=safe_float(row.get(amt_col)),
                turnover_rate=safe_float(row.get(turn_col)),
                amplitude=safe_float(row.get(amp_col)),
                high=safe_float(row.get(high_col)),
                low=safe_float(row.get(low_col)),
                open_price=safe_float(row.get(open_col)),
                volume_ratio=safe_float(row.get(vol_ratio_col)),  # volume ratio
                pe_ratio=safe_float(row.get(pe_col)),  # Price-to-Earnings Ratio
                total_mv=safe_float(row.get(total_mv_col)),  # Total market capitalization
                circ_mv=safe_float(row.get(circ_mv_col)),  # Circulating market capitalization
            )
            
            logger.info(f"[实时行情-efinance] {stock_code} {quote.name}: 价格={quote.price}, 涨跌={quote.change_pct}%, "
                       f"量比={quote.volume_ratio}, 换手率={quote.turnover_rate}%")
            return quote
            
        except FuturesTimeoutError:
            logger.info(f"[超时] ef.stock.get_realtime_quotes() 超过 {_EF_CALL_TIMEOUT}s，跳过 {stock_code}")
            circuit_breaker.record_failure(source_key, "timeout")
            return None
        except Exception as e:  # broad-exception: fallback_recorded - Safe diagnostics and circuit failure are recorded before quote failover.
            log_safe_exception(
                logger,
                "Efinance realtime quote failed",
                e,
                error_code="efinance_realtime_quote_failed",
                level=logging.INFO,
                context={"symbol": stock_code},
            )
            circuit_breaker.record_failure(source_key, "efinance_realtime_quote_failed")
            return None

EXPECTED_REALTIME_METHOD_NAMES: Tuple[str, ...] = (
    "get_realtime_quote",
)


def bind_realtime_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind stock realtime-quote descriptors without changing the fetcher API."""

    return bind_methods_from_class(
        _RealtimeMethods,
        target_class,
        global_namespace,
        expected_names=EXPECTED_REALTIME_METHOD_NAMES,
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
