# -*- coding: utf-8 -*-
"""
===================================
Unified type definition & circuit breaker mechanism for real-time quotes
===================================

Design goals:
1. Unified real-time quote data return structure from all data sources.
2. Implement circuit breaker/cooling mechanism to avoid repeated requests when continuously failing
3. Supports multi-data source failover

Usage:
- All Fetcher's get_realtime_quote() uniformly return UnifiedRealtimeQuote
- CircuitBreaker manages the circuit break status for each data source
"""

import logging
import time
from threading import RLock
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Union
from enum import Enum

from src.utils.sanitize import sanitize_diagnostic_text

logger = logging.getLogger(__name__)


# ============================================
# Generic Type Conversion Utility Function
# ============================================
# Design specifications:
# The raw data types returned by each data source are inconsistent (str/float/int/NaN),
# Use these functions to unify the conversion, avoiding duplication in each Fetcher.

def safe_float(val: Any, default: Optional[float] = None) -> Optional[float]:
    """
    Safely convert to float.
    
    Process scenario:
    - None / Empty string → default
    - pandas NaN / numpy NaN → default
    - Convert numeric string to float
    - Already numeric → float
    
    Args:
        val: Value to be converted
        default: default value when conversion fails
        
    Returns:
        Converted float, or default value
    """
    try:
        if val is None:
            return default
        
        # Process string
        if isinstance(val, str):
            val = val.strip()
            if val == "" or val == "-" or val == "--":
                return default
        
        # Handle pandas/numpy NaN values
        # Use math.isnan instead of pd.isna, avoid forced dependency on pandas
        import math
        try:
            if math.isnan(float(val)):
                return default
        except (ValueError, TypeError):
            pass
        
        return float(val)
    except (ValueError, TypeError):
        return default


def safe_int(val: Any, default: Optional[int] = None) -> Optional[int]:
    """
    Safely convert to integer
    
    Convert to float first, then truncate, handle cases like "123.0"
    
    Args:
        val: Value to be converted
        default: default value when conversion fails
        
    Returns:
        Converted integer, or default value
    """
    f_val = safe_float(val, default=None)
    if f_val is not None:
        return int(f_val)
    return default


class RealtimeSource(Enum):
    """Real-time quote data source"""
    EFINANCE = "efinance"           # Eastmoney (Eastmoney library)
    AKSHARE_EM = "akshare_em"       # Eastmoney (akshare library)
    AKSHARE_SINA = "akshare_sina"   # Sina Finance
    AKSHARE_QQ = "akshare_qq"       # Tencent Finance.
    TUSHARE = "tushare"             # Tushare Pro
    TICKFLOW = "tickflow"           # TickFlow
    TENCENT = "tencent"             # Direct connection to Tencent.
    SINA = "sina"                   # Sina direct connection
    STOOQ = "stooq"                 # Stooq U.S. stocks fallback
    LONGBRIDGE = "longbridge"       # Longbridge (U.S. stocks/Hong Kong stocks fallback)
    FALLBACK = "fallback"           # Fallback to degraded mode.


@dataclass
class UnifiedRealtimeQuote:
    """
    Unified real-time market data structure.
    
    Design principles:
    - The fields returned by each data source may be different, with missing fields represented by None
    - Main Process uses getattr(quote, field, None) to get, ensuring compatibility.
    - source field indicates data source for debugging
    """
    code: str
    name: str = ""
    source: RealtimeSource = RealtimeSource.FALLBACK

    # === Data Quality Metadata (Unified supplemented by DataFetcherManager) ===
    fetched_at: Optional[str] = None             # System acquisition timestamp (ISO 8601 datetime)
    provider_timestamp: Optional[str] = None     # Provider Real-time market data(ISO 8601 datetime)
    is_stale: Optional[bool] = None              # provider_timestamp Exceeds minimum TTL Threshold value is for True
    stale_seconds: Optional[int] = None          # provider_timestamp Distance fetched_at Seconds
    fallback_from: Optional[str] = None          # Fallback source token for the primary source
    market: Optional[str] = None                 # Market Tags (cn/hk/us/jp/kr/tw)
    currency: Optional[str] = None               # Quote currency (JPY/KRW/TWD/USD/HKD/CNY etc.)
    data_quality: Optional[str] = None           # ok/partial/unavailable
    missing_fields: Optional[list[str]] = None   # provider missing key fields
    
    # === Core Price Data (Almost All Sources Have It) ===
    price: Optional[float] = None           # Latest price
    change_pct: Optional[float] = None      # Percentage change
    change_amount: Optional[float] = None   # Change in value
    
    # === Quantitative and Price Indicators (Some sources may be missing) ===
    volume: Optional[int] = None            # Volume (shares, consistent with historical daily line scale)
    amount: Optional[float] = None          # trading value (yuan)
    volume_ratio: Optional[float] = None    # volume ratio
    turnover_rate: Optional[float] = None   # Turnover Rate (%)
    amplitude: Optional[float] = None       # Amplitude (%)
    
    # === Price Range ===
    open_price: Optional[float] = None      # Opening price
    high: Optional[float] = None            # Highest price
    low: Optional[float] = None             # Lowest price
    pre_close: Optional[float] = None       # Yesterday's closing price
    
    # === Valuation Metrics (only available with full interfaces like Eastmoney) ===
    pe_ratio: Optional[float] = None        # Dynamic Price-to-Earnings Ratio
    pb_ratio: Optional[float] = None        # Price-to-Book Ratio
    total_mv: Optional[float] = None        # Total market capitalization (yuan)
    circ_mv: Optional[float] = None         # Circulating market capitalization (yuan)
    
    # === Other Indicators ===
    change_60d: Optional[float] = None      # 60-day percentage change (%)
    high_52w: Optional[float] = None        # Highest price in 52 weeks
    low_52w: Optional[float] = None         # 52 weeks low
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to Dictionary (filter None values)"""
        result = {
            'code': self.code,
            'name': self.name,
            'source': self.source.value,
        }
        # Add only non-null fields.
        optional_fields = [
            'fetched_at', 'provider_timestamp', 'is_stale', 'stale_seconds',
            'fallback_from', 'market', 'currency', 'data_quality', 'missing_fields',
            'price', 'change_pct', 'change_amount', 'volume', 'amount',
            'volume_ratio', 'turnover_rate', 'amplitude',
            'open_price', 'high', 'low', 'pre_close',
            'pe_ratio', 'pb_ratio', 'total_mv', 'circ_mv',
            'change_60d', 'high_52w', 'low_52w'
        ]
        for f in optional_fields:
            val = getattr(self, f, None)
            if val is not None:
                result[f] = val
        return result
    
    def has_basic_data(self) -> bool:
        """Check if basic price data is available."""
        return self.price is not None and self.price > 0
    
    def has_volume_data(self) -> bool:
        """Check if volume and price data is available."""
        return self.volume_ratio is not None or self.turnover_rate is not None


@dataclass
class ChipDistribution:
    """
    Chip distribution data
    
    Reflects the distribution of holding costs and profit figures
    """
    code: str
    date: str = ""
    source: str = "akshare"
    
    # Profit situation
    profit_ratio: float = 0.0     # Profit ratio (0-1)
    avg_cost: float = 0.0         # Average Cost
    
    # Chip concentration
    cost_90_low: float = 0.0      # 90% chip cost lower limit
    cost_90_high: float = 0.0     # 90% chip cost upper limit
    concentration_90: float = 0.0  # 90% chip concentration (smaller is more concentrated)
    
    cost_70_low: float = 0.0      # 70% chip cost lower limit
    cost_70_high: float = 0.0     # 70% chip cost upper limit
    concentration_70: float = 0.0  # 70% chip concentration
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to Dictionary"""
        return {
            'code': self.code,
            'date': self.date,
            'source': self.source,
            'profit_ratio': self.profit_ratio,
            'avg_cost': self.avg_cost,
            'cost_90_low': self.cost_90_low,
            'cost_90_high': self.cost_90_high,
            'concentration_90': self.concentration_90,
            'concentration_70': self.concentration_70,
        }
    
    def get_chip_status(self, current_price: float) -> str:
        """
        Get holding status description
        
        Args:
            current_price: Current stock price
            
        Returns:
            Chip status description
        """
        status_parts = []
        
        # Profit ratio analysis
        if self.profit_ratio >= 0.9:
            status_parts.append("获利盘极高(获利盘>90%)")
        elif self.profit_ratio >= 0.7:
            status_parts.append("获利盘较高(获利盘70-90%)")
        elif self.profit_ratio >= 0.5:
            status_parts.append("获利盘中等(获利盘50-70%)")
        elif self.profit_ratio >= 0.3:
            status_parts.append("套牢盘中等(套牢盘50-70%)")
        elif self.profit_ratio >= 0.1:
            status_parts.append("套牢盘较高(套牢盘70-90%)")
        else:
            status_parts.append("套牢盘极高(套牢盘>90%)")
        
        # Chip concentration analysis (90% concentration < 10% indicates concentration)
        if self.concentration_90 < 0.08:
            status_parts.append("筹码高度集中")
        elif self.concentration_90 < 0.15:
            status_parts.append("筹码较集中")
        elif self.concentration_90 < 0.25:
            status_parts.append("筹码分散度中等")
        else:
            status_parts.append("筹码较分散")
        
        # Relationship between cost and current price
        if current_price > 0 and self.avg_cost > 0:
            cost_diff = (current_price - self.avg_cost) / self.avg_cost * 100
            if cost_diff > 20:
                status_parts.append(f"现价高于平均成本{cost_diff:.1f}%")
            elif cost_diff > 5:
                status_parts.append(f"现价略高于成本{cost_diff:.1f}%")
            elif cost_diff > -5:
                status_parts.append("现价接近平均成本")
            else:
                status_parts.append(f"现价低于平均成本{abs(cost_diff):.1f}%")
        
        return "，".join(status_parts)


class CircuitBreaker:
    """
    Circuit Breaker - Manage data source throttling/cooling status
    
    Strategy:
    - Enter a circuit break state after failing N times consecutively.
    - Skip this data source during the circuit breaker period
    - Restore half-open state automatically after cooling time
    - Order succeeds once in half-open state, then fully recovers; failure continues to trigger a circuit breaker
    
    Status machine:
    CLOSED (normal) --failure N times--> OPEN (circuit break) --cooling time expired--> HALF_OPEN (half-open)
    HALF_OPEN --Success--> CLOSED
    HALF_OPEN --Failure--> OPEN
    """
    
    # Status constants
    CLOSED = "closed"      # Normal state
    OPEN = "open"          # Circuit breaker status (unavailable)
    HALF_OPEN = "half_open"  # Half-open state (probe request)
    
    def __init__(
        self,
        failure_threshold: int = 3,       # Consecutive failure threshold
        cooldown_seconds: float = 300.0,  # Cooling time (seconds), default 5 minutes
        half_open_max_calls: int = 1      # Maximum attempt times for half-open state
    ):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.half_open_max_calls = half_open_max_calls
        
        # Data source status {source_name: {state, failures, last_failure_time, half_open_calls}}
        self._states: Dict[str, Dict[str, Any]] = {}
        self._lock = RLock()
    
    def _get_state_locked(self, source: str) -> Dict[str, Any]:
        """Get or initialize data source status (caller must hold lock)."""
        if source not in self._states:
            self._states[source] = {
                'state': self.CLOSED,
                'failures': 0,
                'last_failure_time': 0.0,
                'half_open_calls': 0
            }
        return self._states[source]
    
    def is_available(self, source: str) -> bool:
        """
        Check if the data source is available
        
        Return True if the request can be attempted
        Return False to skip this data source
        """
        with self._lock:
            state = self._get_state_locked(source)
            current_time = time.time()

            if state['state'] == self.CLOSED:
                return True

            if state['state'] == self.OPEN:
                # Check cooldown time
                time_since_failure = current_time - state['last_failure_time']
                if time_since_failure >= self.cooldown_seconds:
                    # Cooling complete, entering half-open state (does not preempt quota, managed by HALF_OPEN branch)
                    state['state'] = self.HALF_OPEN
                    state['half_open_calls'] = 0
                    state['last_failure_time'] = current_time
                    logger.info(f"[熔断器] {source} 冷却完成，进入半开状态")
                    # Fall through to HALF_OPEN check below
                else:
                    remaining = self.cooldown_seconds - time_since_failure
                    logger.debug(f"[熔断器] {source} 处于熔断状态，剩余冷却时间: {remaining:.0f}s")
                    return False

            if state['state'] == self.HALF_OPEN:
                if state['half_open_calls'] < self.half_open_max_calls:
                    state['half_open_calls'] += 1
                    return True
                # All probe slots are full; if the cooldown time does not receive it again when it expires
                # record_success/record_failure Callback, Reset quota allows re-detection,
                # Avoid getting permanently stuck in HALF_OPEN.
                time_since_failure = current_time - state['last_failure_time']
                if time_since_failure >= self.cooldown_seconds:
                    state['half_open_calls'] = 1
                    state['last_failure_time'] = current_time
                    logger.info(f"[熔断器] {source} 半开状态探测超时，重新探测")
                    return True
                return False

            return True
    
    def record_inconclusive(self, source: str) -> None:
        """Record uncertain detection results (such as returning None).

        Only affects HALF_OPEN state: converts it back to OPEN to allow cooldown detection.
        If in CLOSED state, it's an empty operation and does not affect failure counts.
        """
        with self._lock:
            state = self._get_state_locked(source)
            if state['state'] == self.HALF_OPEN:
                state['state'] = self.OPEN
                state['half_open_calls'] = 0
                state['last_failure_time'] = time.time()
                logger.info(f"[熔断器] {source} 半开探测结果不确定，重新进入冷却")

    def record_success(self, source: str) -> None:
        """Record successful request"""
        with self._lock:
            state = self._get_state_locked(source)

            if state['state'] == self.HALF_OPEN:
                # Success in half-open state, fully recovers
                logger.info(f"[熔断器] {source} 半开状态请求成功，恢复正常")

            # Reset state
            state['state'] = self.CLOSED
            state['failures'] = 0
            state['half_open_calls'] = 0
    
    def record_failure(self, source: str, error: Optional[str] = None) -> None:
        """Record failed requests"""
        with self._lock:
            state = self._get_state_locked(source)
            current_time = time.time()

            state['failures'] += 1
            state['last_failure_time'] = current_time

            if state['state'] == self.HALF_OPEN:
                # Failure continues to trigger a circuit breaker in half-open state
                state['state'] = self.OPEN
                state['half_open_calls'] = 0
                logger.warning(f"[熔断器] {source} 半开状态请求失败，继续熔断 {self.cooldown_seconds}s")
            elif state['failures'] >= self.failure_threshold:
                # Reached threshold, entering circuit break.
                state['state'] = self.OPEN
                logger.warning(f"[熔断器] {source} 连续失败 {state['failures']} 次，进入熔断状态 "
                              f"(冷却 {self.cooldown_seconds}s)")
                if error:
                    logger.warning(
                        "Circuit breaker last failure source=%s error_code=%s",
                        source,
                        sanitize_diagnostic_text(error, max_length=120),
                    )
    
    def get_status(self) -> Dict[str, str]:
        """Get the status of all data sources"""
        with self._lock:
            return {source: info['state'] for source, info in self._states.items()}
    
    def reset(self, source: Optional[str] = None) -> None:
        """Reset circuit breaker status"""
        with self._lock:
            if source:
                if source in self._states:
                    del self._states[source]
            else:
                self._states.clear()


# Global circuit breaker instance(Real-time quote dedicated)
_realtime_circuit_breaker = CircuitBreaker(
    failure_threshold=3,      # Enter a circuit break state after 3 consecutive failures
    cooldown_seconds=300.0,   # Cooling for 5 minutes
    half_open_max_calls=1
)

# Chip interface circuit breaker (more conservative strategy because this interface is more unstable)
_chip_circuit_breaker = CircuitBreaker(
    failure_threshold=2,      # Enter a circuit break state after 2 consecutive failures.
    cooldown_seconds=600.0,   # Cooling for 10 minutes
    half_open_max_calls=1
)


def get_realtime_circuit_breaker() -> CircuitBreaker:
    """Get real-time quote circuit breaker"""
    return _realtime_circuit_breaker


def get_chip_circuit_breaker() -> CircuitBreaker:
    """Get holding interface circuit breaker"""
    return _chip_circuit_breaker
