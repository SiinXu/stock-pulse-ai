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
from typing import Callable, Optional, Dict, Any, Union
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
    EFINANCE = "efinance"           # Efinance (efinance library)
    AKSHARE_EM = "akshare_em"       # Efinance (akshare library)
    AKSHARE_SINA = "akshare_sina"   # Sina Finance
    AKSHARE_QQ = "akshare_qq"       # Tencent Finance.
    TUSHARE = "tushare"             # Tushare Pro
    TICKFLOW = "tickflow"           # TickFlow
    TENCENT = "tencent"             # Direct connection to Tencent.
    SINA = "sina"                   # Sina direct connection
    STOOQ = "stooq"                 # Stooq US equities bottom fishing
    LONGBRIDGE = "longbridge"       # Longbridge (US stocks/Hong Kong stocks bottom-fishing)
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
    
    # Core Price Data (Almost All Sources Have It)
    price: Optional[float] = None           # Latest price
    change_pct: Optional[float] = None      # Percentage change
    change_amount: Optional[float] = None   # Change in value
    
    # === Quantitative and Price Indicators (Some sources may be missing) ===
    volume: Optional[int] = None            # Volume (shares, consistent with historical daily line scale)
    amount: Optional[float] = None          # Value (yuan)
    volume_ratio: Optional[float] = None    # Relative Volume
    turnover_rate: Optional[float] = None   # Turnover Rate (%)
    amplitude: Optional[float] = None       # Amplitude (%)
    
    # === Price Range ===
    open_price: Optional[float] = None      # Opening price
    high: Optional[float] = None            # Highest price
    low: Optional[float] = None             # Lowest price
    pre_close: Optional[float] = None       # Yesterday's closing price
    
    # === Valuation Metrics (only available with full interfaces like East China Securities) ===
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
    """Track bounded provider health and enforce circuit/cooldown transitions."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: float = 300.0,
        half_open_max_calls: int = 1,
        health_window_size: int = 20,
        enabled: bool = True,
        clock: Optional[Callable[[], float]] = None,
    ):
        self.failure_threshold = max(1, int(failure_threshold))
        self.cooldown_seconds = max(0.0, float(cooldown_seconds))
        self.half_open_max_calls = max(1, int(half_open_max_calls))
        self.health_window_size = max(1, int(health_window_size))
        self.enabled = bool(enabled)
        self._clock = clock or time.time
        self._states: Dict[str, Dict[str, Any]] = {}
        self._lock = RLock()

    def configure(
        self,
        *,
        failure_threshold: Optional[int] = None,
        cooldown_seconds: Optional[float] = None,
        health_window_size: Optional[int] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        """Update runtime policy without discarding accumulated health observations."""
        with self._lock:
            if failure_threshold is not None:
                self.failure_threshold = max(1, int(failure_threshold))
            if cooldown_seconds is not None:
                self.cooldown_seconds = max(0.0, float(cooldown_seconds))
            if health_window_size is not None:
                self.health_window_size = max(1, int(health_window_size))
                for state in self._states.values():
                    state["outcomes"] = state["outcomes"][-self.health_window_size:]
                    state["latencies_ms"] = state["latencies_ms"][-self.health_window_size:]
            if enabled is not None:
                self.enabled = bool(enabled)
                if not self.enabled:
                    for state in self._states.values():
                        state["state"] = self.CLOSED
                        state["half_open_calls"] = 0

    def _get_state_locked(self, source: str) -> Dict[str, Any]:
        """Return mutable source state while the caller holds ``self._lock``."""
        if source not in self._states:
            self._states[source] = {
                "state": self.CLOSED,
                "failures": 0,
                "last_failure_time": 0.0,
                "last_success_time": 0.0,
                "half_open_calls": 0,
                "outcomes": [],
                "latencies_ms": [],
            }
        return self._states[source]

    def _record_observation_locked(
        self,
        state: Dict[str, Any],
        *,
        success: bool,
        latency_ms: Optional[float],
    ) -> None:
        state["outcomes"].append(bool(success))
        state["outcomes"] = state["outcomes"][-self.health_window_size:]
        self._record_latency_locked(state, latency_ms)

    def _record_latency_locked(
        self,
        state: Dict[str, Any],
        latency_ms: Optional[float],
    ) -> None:
        if latency_ms is not None:
            try:
                normalized_latency = max(0.0, float(latency_ms))
            except (TypeError, ValueError):
                normalized_latency = None
            if normalized_latency is not None:
                state["latencies_ms"].append(normalized_latency)
                state["latencies_ms"] = state["latencies_ms"][-self.health_window_size:]

    def record_latency(self, source: str, latency_ms: Optional[float]) -> None:
        """Record request latency independently from its eventual outcome classification."""
        with self._lock:
            state = self._get_state_locked(source)
            self._record_latency_locked(state, latency_ms)

    def _snapshot_locked(self, source: str, state: Dict[str, Any], now: float) -> Dict[str, Any]:
        outcomes = list(state["outcomes"])
        latencies = list(state["latencies_ms"])
        sample_count = len(outcomes)
        failure_count = sum(1 for outcome in outcomes if not outcome)
        success_count = sample_count - failure_count
        success_rate = success_count / sample_count if sample_count else 1.0
        error_rate = failure_count / sample_count if sample_count else 0.0
        average_latency_ms = sum(latencies) / len(latencies) if latencies else None
        latency_factor = (
            1.0
            if average_latency_ms is None
            else 1.0 / (1.0 + (average_latency_ms / 1000.0))
        )
        streak_factor = max(
            0.0,
            1.0 - (state["failures"] / float(self.failure_threshold)),
        )
        health_score = max(
            0.0,
            min(100.0, (success_rate * 70.0) + (latency_factor * 20.0) + (streak_factor * 10.0)),
        )
        cooldown_remaining = 0.0
        if self.enabled and state["state"] == self.OPEN:
            cooldown_remaining = max(
                0.0,
                self.cooldown_seconds - (now - state["last_failure_time"]),
            )
        available = self._can_attempt_locked(state, now)
        return {
            "source": source,
            "state": state["state"],
            "circuit_enabled": self.enabled,
            "available": available,
            "health_score": round(health_score, 2),
            "success_rate": round(success_rate, 4),
            "error_rate": round(error_rate, 4),
            "sample_count": sample_count,
            "success_count": success_count,
            "failure_count": failure_count,
            "recent_failure_count": failure_count,
            "consecutive_failures": state["failures"],
            "average_latency_ms": (
                round(average_latency_ms, 2)
                if average_latency_ms is not None
                else None
            ),
            "cooldown_remaining_seconds": round(cooldown_remaining, 3),
            "last_failure_time": state["last_failure_time"] or None,
            "last_success_time": state["last_success_time"] or None,
        }

    def _can_attempt_locked(self, state: Dict[str, Any], now: float) -> bool:
        if not self.enabled or state["state"] == self.CLOSED:
            return True
        elapsed = now - state["last_failure_time"]
        if state["state"] == self.OPEN:
            return elapsed >= self.cooldown_seconds
        if state["state"] == self.HALF_OPEN:
            return (
                state["half_open_calls"] < self.half_open_max_calls
                or elapsed >= self.cooldown_seconds
            )
        return True

    def can_attempt(self, source: str) -> bool:
        """Peek at admission without transitioning state or reserving a half-open probe."""
        with self._lock:
            state = self._get_state_locked(source)
            return self._can_attempt_locked(state, self._clock())

    def is_available(self, source: str) -> bool:
        """Return whether a request may enter the source, reserving half-open probes."""
        with self._lock:
            state = self._get_state_locked(source)
            if not self.enabled:
                return True
            current_time = self._clock()

            if state["state"] == self.CLOSED:
                return True

            if state["state"] == self.OPEN:
                time_since_failure = current_time - state["last_failure_time"]
                if time_since_failure >= self.cooldown_seconds:
                    state["state"] = self.HALF_OPEN
                    state["half_open_calls"] = 0
                    state["last_failure_time"] = current_time
                    logger.info(
                        "provider_circuit event=half_open source=%s",
                        source,
                    )
                else:
                    remaining = self.cooldown_seconds - time_since_failure
                    logger.debug(
                        "provider_circuit event=skip_open source=%s cooldown_remaining_seconds=%.3f",
                        source,
                        remaining,
                    )
                    return False

            if state["state"] == self.HALF_OPEN:
                if state["half_open_calls"] < self.half_open_max_calls:
                    state["half_open_calls"] += 1
                    return True
                time_since_failure = current_time - state["last_failure_time"]
                if time_since_failure >= self.cooldown_seconds:
                    state["half_open_calls"] = 1
                    state["last_failure_time"] = current_time
                    logger.info(
                        "provider_circuit event=half_open_probe_retry source=%s",
                        source,
                    )
                    return True
                return False

            return True

    def record_inconclusive(self, source: str) -> None:
        """Release an inconclusive half-open probe back into cooldown."""
        with self._lock:
            state = self._get_state_locked(source)
            if self.enabled and state["state"] == self.HALF_OPEN:
                state["state"] = self.OPEN
                state["half_open_calls"] = 0
                state["last_failure_time"] = self._clock()
                logger.info(
                    "provider_circuit event=half_open_inconclusive source=%s",
                    source,
                )

    def record_success(self, source: str, latency_ms: Optional[float] = None) -> None:
        """Record a successful provider request and close a half-open circuit."""
        with self._lock:
            state = self._get_state_locked(source)
            self._record_observation_locked(state, success=True, latency_ms=latency_ms)
            state["last_success_time"] = self._clock()

            if state["state"] == self.HALF_OPEN:
                logger.info(
                    "provider_circuit event=recovered source=%s",
                    source,
                )

            state["state"] = self.CLOSED
            state["failures"] = 0
            state["half_open_calls"] = 0

    def record_quality_failure(
        self,
        source: str,
        latency_ms: Optional[float] = None,
    ) -> None:
        """Record unusable data without incrementing the circuit failure streak."""
        with self._lock:
            state = self._get_state_locked(source)
            self._record_observation_locked(state, success=False, latency_ms=latency_ms)
            state["last_failure_time"] = self._clock()

            if self.enabled and state["state"] == self.HALF_OPEN:
                state["state"] = self.OPEN
                state["half_open_calls"] = 0
                logger.info(
                    "provider_circuit event=half_open_quality_failed source=%s",
                    source,
                )
                return

            state["state"] = self.CLOSED
            state["failures"] = 0
            state["half_open_calls"] = 0

    def record_failure(
        self,
        source: str,
        error: Optional[str] = None,
        latency_ms: Optional[float] = None,
    ) -> None:
        """Record a provider failure and open the circuit at the configured threshold."""
        with self._lock:
            state = self._get_state_locked(source)
            current_time = self._clock()

            self._record_observation_locked(state, success=False, latency_ms=latency_ms)
            state["failures"] += 1
            state["last_failure_time"] = current_time

            if not self.enabled:
                return

            if state["state"] == self.HALF_OPEN:
                state["state"] = self.OPEN
                state["half_open_calls"] = 0
                logger.warning(
                    "provider_circuit event=half_open_failed source=%s cooldown_seconds=%.3f",
                    source,
                    self.cooldown_seconds,
                )
            elif state["failures"] >= self.failure_threshold:
                state["state"] = self.OPEN
                logger.warning(
                    "provider_circuit event=open source=%s consecutive_failures=%d "
                    "cooldown_seconds=%.3f",
                    source,
                    state["failures"],
                    self.cooldown_seconds,
                )
                if error:
                    logger.warning(
                        "Circuit breaker last failure source=%s error_code=%s",
                        source,
                        sanitize_diagnostic_text(error, max_length=120),
                    )
    
    def get_status(self) -> Dict[str, str]:
        """Return the existing compact source-to-circuit-state contract."""
        with self._lock:
            return {source: info["state"] for source, info in self._states.items()}

    def get_snapshot(self, source: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Return a non-mutating, secret-free health snapshot for diagnostics."""
        with self._lock:
            now = self._clock()
            if source is not None:
                state = self._get_state_locked(source)
                return {source: self._snapshot_locked(source, state, now)}
            return {
                source_name: self._snapshot_locked(source_name, state, now)
                for source_name, state in sorted(self._states.items())
            }

    def reset(self, source: Optional[str] = None) -> None:
        """Reset one source or all circuit and health observations."""
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
