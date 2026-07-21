# -*- coding: utf-8 -*-
"""
===================================
实时行情统一类型定义 & 熔断机制
===================================

设计目标：
1. 统一各数据源的实时行情返回结构
2. 实现熔断/冷却机制，避免连续失败时反复请求
3. 支持多数据源故障切换

使用方式：
- 所有 Fetcher 的 get_realtime_quote() 统一返回 UnifiedRealtimeQuote
- CircuitBreaker 管理各数据源的熔断状态
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
# 通用类型转换工具函数
# ============================================
# 设计说明：
# 各数据源返回的原始数据类型不一致（str/float/int/NaN），
# 使用这些函数统一转换，避免在各 Fetcher 中重复定义。

def safe_float(val: Any, default: Optional[float] = None) -> Optional[float]:
    """
    安全转换为浮点数
    
    处理场景：
    - None / 空字符串 → default
    - pandas NaN / numpy NaN → default
    - 数值字符串 → float
    - 已是数值 → float
    
    Args:
        val: 待转换的值
        default: 转换失败时的默认值
        
    Returns:
        转换后的浮点数，或默认值
    """
    try:
        if val is None:
            return default
        
        # 处理字符串
        if isinstance(val, str):
            val = val.strip()
            if val == "" or val == "-" or val == "--":
                return default
        
        # 处理 pandas/numpy NaN
        # 使用 math.isnan 而不是 pd.isna，避免强制依赖 pandas
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
    安全转换为整数
    
    先转换为 float，再取整，处理 "123.0" 这类情况
    
    Args:
        val: 待转换的值
        default: 转换失败时的默认值
        
    Returns:
        转换后的整数，或默认值
    """
    f_val = safe_float(val, default=None)
    if f_val is not None:
        return int(f_val)
    return default


class RealtimeSource(Enum):
    """实时行情数据源"""
    EFINANCE = "efinance"           # 东方财富（efinance库）
    AKSHARE_EM = "akshare_em"       # 东方财富（akshare库）
    AKSHARE_SINA = "akshare_sina"   # 新浪财经
    AKSHARE_QQ = "akshare_qq"       # 腾讯财经
    TUSHARE = "tushare"             # Tushare Pro
    TICKFLOW = "tickflow"           # TickFlow
    TENCENT = "tencent"             # 腾讯直连
    SINA = "sina"                   # 新浪直连
    STOOQ = "stooq"                 # Stooq 美股兜底
    LONGBRIDGE = "longbridge"       # 长桥（美股/港股兜底）
    FALLBACK = "fallback"           # 降级兜底


@dataclass
class UnifiedRealtimeQuote:
    """
    统一实时行情数据结构
    
    设计原则：
    - 各数据源返回的字段可能不同，缺失字段用 None 表示
    - 主流程使用 getattr(quote, field, None) 获取，保证兼容性
    - source 字段标记数据来源，便于调试
    """
    code: str
    name: str = ""
    source: RealtimeSource = RealtimeSource.FALLBACK

    # === 数据质量元数据（由 DataFetcherManager 统一补齐）===
    fetched_at: Optional[str] = None             # 本系统获取时间（ISO 8601 datetime）
    provider_timestamp: Optional[str] = None     # Provider 真实行情时间（ISO 8601 datetime）
    is_stale: Optional[bool] = None              # provider_timestamp 超过最小 TTL 阈值时为 True
    stale_seconds: Optional[int] = None          # provider_timestamp 距 fetched_at 的秒数
    fallback_from: Optional[str] = None          # 整源 fallback 的失败首选源 token
    market: Optional[str] = None                 # 市场标签（cn/hk/us/jp/kr/tw）
    currency: Optional[str] = None               # 报价币种（JPY/KRW/TWD/USD/HKD/CNY 等）
    data_quality: Optional[str] = None           # ok/partial/unavailable
    missing_fields: Optional[list[str]] = None   # provider 缺失的关键字段
    
    # === 核心价格数据（几乎所有源都有）===
    price: Optional[float] = None           # 最新价
    change_pct: Optional[float] = None      # 涨跌幅(%)
    change_amount: Optional[float] = None   # 涨跌额
    
    # === 量价指标（部分源可能缺失）===
    volume: Optional[int] = None            # 成交量（股，与历史日线口径一致）
    amount: Optional[float] = None          # 成交额（元）
    volume_ratio: Optional[float] = None    # 量比
    turnover_rate: Optional[float] = None   # 换手率(%)
    amplitude: Optional[float] = None       # 振幅(%)
    
    # === 价格区间 ===
    open_price: Optional[float] = None      # 开盘价
    high: Optional[float] = None            # 最高价
    low: Optional[float] = None             # 最低价
    pre_close: Optional[float] = None       # 昨收价
    
    # === 估值指标（仅东财等全量接口有）===
    pe_ratio: Optional[float] = None        # 市盈率(动态)
    pb_ratio: Optional[float] = None        # 市净率
    total_mv: Optional[float] = None        # 总市值(元)
    circ_mv: Optional[float] = None         # 流通市值(元)
    
    # === 其他指标 ===
    change_60d: Optional[float] = None      # 60日涨跌幅(%)
    high_52w: Optional[float] = None        # 52周最高
    low_52w: Optional[float] = None         # 52周最低
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（过滤 None 值）"""
        result = {
            'code': self.code,
            'name': self.name,
            'source': self.source.value,
        }
        # 只添加非 None 的字段
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
        """检查是否有基本的价格数据"""
        return self.price is not None and self.price > 0
    
    def has_volume_data(self) -> bool:
        """检查是否有量价数据"""
        return self.volume_ratio is not None or self.turnover_rate is not None


@dataclass
class ChipDistribution:
    """
    筹码分布数据
    
    反映持仓成本分布和获利情况
    """
    code: str
    date: str = ""
    source: str = "akshare"
    
    # 获利情况
    profit_ratio: float = 0.0     # 获利比例(0-1)
    avg_cost: float = 0.0         # 平均成本
    
    # 筹码集中度
    cost_90_low: float = 0.0      # 90%筹码成本下限
    cost_90_high: float = 0.0     # 90%筹码成本上限
    concentration_90: float = 0.0  # 90%筹码集中度（越小越集中）
    
    cost_70_low: float = 0.0      # 70%筹码成本下限
    cost_70_high: float = 0.0     # 70%筹码成本上限
    concentration_70: float = 0.0  # 70%筹码集中度
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
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
        获取筹码状态描述
        
        Args:
            current_price: 当前股价
            
        Returns:
            筹码状态描述
        """
        status_parts = []
        
        # 获利比例分析
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
        
        # 筹码集中度分析 (90%集中度 < 10% 表示集中)
        if self.concentration_90 < 0.08:
            status_parts.append("筹码高度集中")
        elif self.concentration_90 < 0.15:
            status_parts.append("筹码较集中")
        elif self.concentration_90 < 0.25:
            status_parts.append("筹码分散度中等")
        else:
            status_parts.append("筹码较分散")
        
        # 成本与现价关系
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
        available = (
            not self.enabled
            or state["state"] == self.CLOSED
            or (state["state"] == self.OPEN and cooldown_remaining <= 0.0)
            or (
                state["state"] == self.HALF_OPEN
                and state["half_open_calls"] < self.half_open_max_calls
            )
        )
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


# 全局熔断器实例（实时行情专用）
_realtime_circuit_breaker = CircuitBreaker(
    failure_threshold=3,      # 连续失败3次熔断
    cooldown_seconds=300.0,   # 冷却5分钟
    half_open_max_calls=1
)

# 筹码接口熔断器（更保守的策略，因为该接口更不稳定）
_chip_circuit_breaker = CircuitBreaker(
    failure_threshold=2,      # 连续失败2次熔断
    cooldown_seconds=600.0,   # 冷却10分钟
    half_open_max_calls=1
)


def get_realtime_circuit_breaker() -> CircuitBreaker:
    """获取实时行情熔断器"""
    return _realtime_circuit_breaker


def get_chip_circuit_breaker() -> CircuitBreaker:
    """获取筹码接口熔断器"""
    return _chip_circuit_breaker
