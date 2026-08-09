# -*- coding: utf-8 -*-
"""
===================================
趋势交易分析器 - 基于用户交易理念
===================================

交易理念核心原则：
1. 严进策略 - 不追高，追求每笔交易成功率
2. 趋势交易 - MA5>MA10>MA20 多头排列，顺势而为
3. 效率优先 - 关注筹码结构好的股票
4. 买点偏好 - 在 MA5/MA10 附近回踩买入

技术标准：
- 多头排列：MA5 > MA10 > MA20
- 乖离率：(Close - MA5) / MA5 < 5%（不追高）
- 量能形态：缩量回调优先
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum

import pandas as pd
import numpy as np

from src.config import get_config
from src.utils.indicator_periods import (
    DEFAULT_MA_PERIODS,
    DEFAULT_MACD_FAST,
    DEFAULT_MACD_SIGNAL,
    DEFAULT_MACD_SLOW,
    DEFAULT_RSI_PERIODS,
    IndicatorPeriodConfig,
    format_ma_label,
    insufficient_data_note,
)
from src.schemas.decision_scale import signal_key_for_score

logger = logging.getLogger(__name__)


class TrendStatus(Enum):
    """趋势状态枚举"""
    STRONG_BULL = "强势多头"      # MA5 > MA10 > MA20, and the gap expands
    BULL = "多头排列"             # MA5 > MA10 > MA20
    WEAK_BULL = "弱势多头"        # MA5 > MA10, but MA10 < MA20
    CONSOLIDATION = "盘整"        # Moving averages are intertwined
    WEAK_BEAR = "弱势空头"        # MA5 < MA10, but MA10 > MA20
    BEAR = "空头排列"             # MA5 < MA10 < MA20
    STRONG_BEAR = "强势空头"      # MA5 < MA10 < MA20, and the distance expands.


class VolumeStatus(Enum):
    """量能状态枚举"""
    HEAVY_VOLUME_UP = "放量上涨"       # Volume and price rising together
    HEAVY_VOLUME_DOWN = "放量下跌"     # Selloff on heavy volume
    SHRINK_VOLUME_UP = "缩量上涨"      # Price rise on weak volume
    SHRINK_VOLUME_DOWN = "缩量回调"    # Pullback on declining volume (favorable)
    NORMAL = "量能正常"


class BuySignal(Enum):
    """买入信号枚举"""
    STRONG_BUY = "强烈买入"       # Multiple conditions satisfied
    BUY = "买入"                  # Basic conditions met
    HOLD = "持有"                 # Already held; can continue holding
    WAIT = "观望"                 # Wait for a better entry
    SELL = "卖出"                 # Trend weakening
    STRONG_SELL = "强烈卖出"      # Trend breakdown


class MACDStatus(Enum):
    """MACD状态枚举"""
    GOLDEN_CROSS_ZERO = "零轴上金叉"      # DIF crosses DEA and is above the zero axis
    GOLDEN_CROSS = "金叉"                # DIF crosses DEA
    BULLISH = "多头"                    # DIF>DEA>0
    CROSSING_UP = "上穿零轴"             # DIF crosses above the zero axis
    CROSSING_DOWN = "下穿零轴"           # DIF crosses below the zero axis
    BEARISH = "空头"                    # DIF<DEA<0
    DEATH_CROSS = "死叉"                # DIF crosses below DEA


class RSIStatus(Enum):
    """RSI状态枚举"""
    OVERBOUGHT = "超买"        # RSI > 70
    STRONG_BUY = "强势买入"    # 50 < RSI < 70
    NEUTRAL = "中性"          # 40 <= RSI <= 60
    WEAK = "弱势"             # 30 < RSI < 40
    OVERSOLD = "超卖"         # RSI < 30


@dataclass(frozen=True)
class IndicatorReading:
    """Typed dynamic indicator value with explicit availability metadata."""

    kind: str
    period: int
    label: str
    value: Optional[float]
    available: bool
    reason: Optional[str]
    bar_count: int
    as_of: Optional[str]
    source: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "period": self.period,
            "label": self.label,
            "value": self.value,
            "available": self.available,
            "reason": self.reason,
            "bar_count": self.bar_count,
            "as_of": self.as_of,
            "source": self.source,
        }


@dataclass(frozen=True)
class MACDReading:
    """Typed MACD triplet with its configured periods and provenance."""

    fast_period: int
    slow_period: int
    signal_period: int
    label: str
    dif: Optional[float]
    dea: Optional[float]
    bar: Optional[float]
    available: bool
    reason: Optional[str]
    bar_count: int
    as_of: Optional[str]
    source: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "macd",
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
            "signal_period": self.signal_period,
            "label": self.label,
            "dif": self.dif,
            "dea": self.dea,
            "bar": self.bar,
            "available": self.available,
            "reason": self.reason,
            "bar_count": self.bar_count,
            "as_of": self.as_of,
            "source": self.source,
        }


@dataclass
class TrendAnalysisResult:
    """趋势分析结果"""
    code: str
    
    # Trend judgment
    trend_status: TrendStatus = TrendStatus.CONSOLIDATION
    ma_alignment: str = ""           # Moving average arrangement description
    trend_strength: float = 0.0      # Trend strength 0-100
    
    # Moving average data
    ma5: Optional[float] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None
    ma60: Optional[float] = None
    current_price: float = 0.0
    
    # bias ratio (deviation from MA5)
    bias_ma5: Optional[float] = None  # Always (Close - MA5) / MA5 * 100
    bias_ma10: Optional[float] = None
    bias_ma20: Optional[float] = None
    
    # Volume analysis
    volume_status: VolumeStatus = VolumeStatus.NORMAL
    volume_ratio_5d: float = 0.0     # Current-day volume / 5-day average volume
    volume_trend: str = ""           # Volume trend description
    
    # Support and resistance
    support_ma5: bool = False        # Whether MA5 acts as support
    support_ma10: bool = False       # Whether MA10 acts as support
    resistance_levels: List[float] = field(default_factory=list)
    support_levels: List[float] = field(default_factory=list)

    # MACD indicator
    macd_dif: float = 0.0          # DIF fast line
    macd_dea: float = 0.0          # DEA slow line
    macd_bar: float = 0.0           # MACD histogram
    macd_status: MACDStatus = MACDStatus.BULLISH
    macd_signal: str = ""            # MACD signal description
    macd_reading: Optional[MACDReading] = None

    # RSI indicator
    rsi_6: Optional[float] = None
    rsi_12: Optional[float] = None
    rsi_24: Optional[float] = None
    rsi_status: RSIStatus = RSIStatus.NEUTRAL
    rsi_signal: str = ""              # RSI Signal Description

    # Full period maps (period int -> value or None when insufficient data)
    ma_by_period: Dict[int, Any] = field(default_factory=dict)
    ma_periods_used: List[int] = field(default_factory=list)
    rsi_by_period: Dict[int, Any] = field(default_factory=dict)
    rsi_periods_used: List[int] = field(default_factory=list)
    ma_readings: Dict[int, IndicatorReading] = field(default_factory=dict)
    rsi_readings: Dict[int, IndicatorReading] = field(default_factory=dict)
    bias_by_period: Dict[int, Optional[float]] = field(default_factory=dict)
    support_by_period: Dict[int, bool] = field(default_factory=dict)
    primary_ma_periods: List[int] = field(default_factory=list)
    primary_bias_period: Optional[int] = None
    indicator_period_source: str = "defaults"
    indicator_bar_count: int = 0
    indicator_as_of: Optional[str] = None

    # Buy Signal
    buy_signal: BuySignal = BuySignal.WAIT
    signal_score: int = 0            # Overall score 0-100
    signal_reasons: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'code': self.code,
            'trend_status': self.trend_status.value,
            'ma_alignment': self.ma_alignment,
            'trend_strength': self.trend_strength,
            'ma5': self.ma5,
            'ma10': self.ma10,
            'ma20': self.ma20,
            'ma60': self.ma60,
            'ma_by_period': self.ma_by_period,
            'ma_periods_used': self.ma_periods_used,
            'ma_readings': {str(k): v.to_dict() for k, v in self.ma_readings.items()},
            'current_price': self.current_price,
            'bias_ma5': self.bias_ma5,
            'bias_ma10': self.bias_ma10,
            'bias_ma20': self.bias_ma20,
            'bias_by_period': self.bias_by_period,
            'support_by_period': self.support_by_period,
            'primary_ma_periods': self.primary_ma_periods,
            'primary_bias_period': self.primary_bias_period,
            'volume_status': self.volume_status.value,
            'volume_ratio_5d': self.volume_ratio_5d,
            'volume_trend': self.volume_trend,
            'support_ma5': self.support_ma5,
            'support_ma10': self.support_ma10,
            'buy_signal': self.buy_signal.value,
            'signal_score': self.signal_score,
            'signal_reasons': self.signal_reasons,
            'risk_factors': self.risk_factors,
            'macd_dif': self.macd_dif,
            'macd_dea': self.macd_dea,
            'macd_bar': self.macd_bar,
            'macd_status': self.macd_status.value,
            'macd_signal': self.macd_signal,
            'macd_reading': (
                self.macd_reading.to_dict() if self.macd_reading is not None else None
            ),
            'rsi_6': self.rsi_6,
            'rsi_12': self.rsi_12,
            'rsi_24': self.rsi_24,
            'rsi_by_period': self.rsi_by_period,
            'rsi_periods_used': self.rsi_periods_used,
            'rsi_readings': {str(k): v.to_dict() for k, v in self.rsi_readings.items()},
            'indicator_period_source': self.indicator_period_source,
            'indicator_bar_count': self.indicator_bar_count,
            'indicator_as_of': self.indicator_as_of,
            'rsi_status': self.rsi_status.value,
            'rsi_signal': self.rsi_signal,
        }


class StockTrendAnalyzer:
    """
    股票趋势分析器

    基于用户交易理念实现：
    1. 趋势判断 - MA5>MA10>MA20 多头排列
    2. 乖离率检测 - 不追高，偏离 MA5 超过 5% 不买
    3. 量能分析 - 偏好缩量回调
    4. 买点识别 - 回踩 MA5/MA10 支撑
    5. MACD 指标 - 趋势确认和金叉死叉信号
    6. RSI 指标 - 超买超卖判断
    """
    
    # Trading parameter configuration (BIAS_THRESHOLD read from Config, see _generate_signal)
    VOLUME_SHRINK_RATIO = 0.7   # Volume shrinkage judgment threshold (daily volume / 5-day average volume)
    VOLUME_HEAVY_RATIO = 1.5    # Heavy-volume threshold
    MA_SUPPORT_TOLERANCE = 0.02  # MA support judgment tolerance (2%).

    # Class-level defaults kept for tests/tools that still read attributes.
    # Runtime analysis prefers instance periods resolved from Config.
    MACD_FAST = DEFAULT_MACD_FAST
    MACD_SLOW = DEFAULT_MACD_SLOW
    MACD_SIGNAL = DEFAULT_MACD_SIGNAL
    RSI_SHORT = DEFAULT_RSI_PERIODS[0]
    RSI_MID = DEFAULT_RSI_PERIODS[1]
    RSI_LONG = DEFAULT_RSI_PERIODS[2]
    RSI_OVERBOUGHT = 70
    RSI_OVERSOLD = 30
    
    def __init__(self, periods: Optional[IndicatorPeriodConfig] = None):
        """Initialize analyzer with optional explicit period overrides."""
        self._periods = periods

    def _resolve_periods(self) -> IndicatorPeriodConfig:
        """Return injected periods or historical defaults (no process-config read)."""
        if self._periods is not None:
            return self._periods
        return IndicatorPeriodConfig()
    
    def analyze(self, df: pd.DataFrame, code: str) -> TrendAnalysisResult:
        """
        分析股票趋势
        
        Args:
            df: 包含 OHLCV 数据的 DataFrame
            code: 股票代码
            
        Returns:
            TrendAnalysisResult 分析结果
        """
        result = TrendAnalysisResult(code=code)
        periods = self._resolve_periods()
        result.ma_periods_used = list(periods.ma_periods)
        result.rsi_periods_used = list(periods.rsi_periods)
        result.primary_ma_periods = list(periods.ma_periods[:3])
        result.primary_bias_period = periods.ma_short
        result.indicator_period_source = periods.source

        if df is None or df.empty:
            self._initialize_indicator_evidence(periods, result)
            logger.warning(f"{code} 数据不足，无法进行趋势分析")
            result.risk_factors.append("数据不足，无法完成分析")
            return result

        # Ensure data is sorted by date
        df = df.sort_values('date').reset_index(drop=True)
        result.indicator_bar_count = len(df)
        result.indicator_as_of = str(df.iloc[-1].get("date"))[:10]
        self._initialize_indicator_evidence(periods, result)
        if len(df) < 20:
            logger.warning(f"{code} 数据不足，无法进行趋势分析")
            result.risk_factors.append("数据不足，无法完成分析")
            return result

        # Calculate moving average
        df = self._calculate_mas(df, periods, result)

        # Calculate MACD and RSI
        df = self._calculate_macd(df, periods)
        df = self._calculate_rsi(df, periods)

        # Get latest data
        latest = df.iloc[-1]
        result.current_price = float(latest['close'])
        self._assign_ma_slots(latest, periods, result)

        # 1. Trend judgment
        self._analyze_trend(df, result, periods)

        # 2. Bias ratio calculation
        self._calculate_bias(result, periods)

        # 3. Volume analysis
        self._analyze_volume(df, result)

        # 4. Support and resistance analysis
        self._analyze_support_resistance(df, result, periods)

        # 5. MACD analysis
        self._analyze_macd(df, result, periods)

        # 6. RSI Analysis
        self._analyze_rsi(df, result, periods)

        # 7. Generate buy signals (BIAS_THRESHOLD via existing get_config site)
        self._generate_signal(result)

        return result

    def _initialize_indicator_evidence(
        self,
        periods: IndicatorPeriodConfig,
        result: TrendAnalysisResult,
    ) -> None:
        """Create explicit unavailable evidence before any calculation succeeds."""
        result.ma_by_period = {period: None for period in periods.ma_periods}
        result.rsi_by_period = {period: None for period in periods.rsi_periods}
        result.ma_readings = {
            period: IndicatorReading(
                kind="ma",
                period=period,
                label=format_ma_label(period),
                value=None,
                available=False,
                reason=(
                    f"insufficient_history:need={period},got={result.indicator_bar_count}"
                ),
                bar_count=result.indicator_bar_count,
                as_of=result.indicator_as_of,
                source=result.indicator_period_source,
            )
            for period in periods.ma_periods
        }
        result.rsi_readings = {
            period: IndicatorReading(
                kind="rsi",
                period=period,
                label=f"RSI({period})",
                value=None,
                available=False,
                reason=(
                    f"insufficient_history:need={period},got={result.indicator_bar_count}"
                ),
                bar_count=result.indicator_bar_count,
                as_of=result.indicator_as_of,
                source=result.indicator_period_source,
            )
            for period in periods.rsi_periods
        }
        result.macd_reading = MACDReading(
            fast_period=periods.macd_fast,
            slow_period=periods.macd_slow,
            signal_period=periods.macd_signal,
            label=f"MACD({periods.macd_fast},{periods.macd_slow},{periods.macd_signal})",
            dif=None,
            dea=None,
            bar=None,
            available=False,
            reason=(
                f"insufficient_history:need={periods.macd_slow},"
                f"got={result.indicator_bar_count}"
            ),
            bar_count=result.indicator_bar_count,
            as_of=result.indicator_as_of,
            source=result.indicator_period_source,
        )

    def _assign_ma_slots(
        self,
        latest: pd.Series,
        periods: IndicatorPeriodConfig,
        result: TrendAnalysisResult,
    ) -> None:
        """Populate exact-period dynamic values and period-stable legacy fields."""
        ma_by_period: Dict[int, Any] = {}
        all_periods = tuple(dict.fromkeys((*periods.ma_periods, *DEFAULT_MA_PERIODS)))
        for period in all_periods:
            col = format_ma_label(period)
            raw = latest.get(col)
            if raw is None or (isinstance(raw, float) and np.isnan(raw)):
                ma_by_period[period] = None
            else:
                ma_by_period[period] = float(raw)
        result.ma_by_period = ma_by_period
        result.ma_readings = {
            period: IndicatorReading(
                kind="ma",
                period=period,
                label=format_ma_label(period),
                value=ma_by_period[period],
                available=ma_by_period[period] is not None,
                reason=(
                    None
                    if ma_by_period[period] is not None
                    else f"insufficient_history:need={period},got={result.indicator_bar_count}"
                ),
                bar_count=result.indicator_bar_count,
                as_of=result.indicator_as_of,
                source=result.indicator_period_source,
            )
            for period in periods.ma_periods
        }

        result.ma5 = ma_by_period.get(5)
        result.ma10 = ma_by_period.get(10)
        result.ma20 = ma_by_period.get(20)
        result.ma60 = ma_by_period.get(60)
    
    def _calculate_mas(
        self,
        df: pd.DataFrame,
        periods: IndicatorPeriodConfig,
        result: TrendAnalysisResult,
    ) -> pd.DataFrame:
        """Calculate configured moving averages without shorter-period substitution."""
        df = df.copy()
        bar_count = len(df)
        all_periods = tuple(dict.fromkeys((*periods.ma_periods, *DEFAULT_MA_PERIODS)))
        for period in all_periods:
            col = format_ma_label(period)
            if bar_count >= period:
                df[col] = df['close'].rolling(window=period).mean()
            else:
                # Leave column as NaN; annotate insufficient data (no MA20 substitution).
                df[col] = np.nan
                note = insufficient_data_note(period, bar_count)
                if note not in result.risk_factors:
                    result.risk_factors.append(note)
        return df

    def _calculate_macd(
        self,
        df: pd.DataFrame,
        periods: Optional[IndicatorPeriodConfig] = None,
    ) -> pd.DataFrame:
        """
        计算 MACD 指标

        公式：
        - EMA(fast)：fast-day exponential moving average
        - EMA(slow)：slow-day exponential moving average
        - DIF = EMA(fast) - EMA(slow)
        - DEA = EMA(DIF, signal)
        - MACD = (DIF - DEA) * 2
        """
        resolved = periods or self._resolve_periods()
        df = df.copy()

        # Calculate fast and slow line EMA
        ema_fast = df['close'].ewm(span=resolved.macd_fast, adjust=False).mean()
        ema_slow = df['close'].ewm(span=resolved.macd_slow, adjust=False).mean()

        # Calculate Quick Line DIF
        df['MACD_DIF'] = ema_fast - ema_slow

        # Calculate signal line DEA
        df['MACD_DEA'] = df['MACD_DIF'].ewm(span=resolved.macd_signal, adjust=False).mean()

        # Calculate histogram
        df['MACD_BAR'] = (df['MACD_DIF'] - df['MACD_DEA']) * 2

        return df

    def _calculate_rsi(
        self,
        df: pd.DataFrame,
        periods: Optional[IndicatorPeriodConfig] = None,
    ) -> pd.DataFrame:
        """
        计算 RSI 指标（Wilder's EMA / SMMA 口径）

        公式：
        - avg_gain / avg_loss 使用 ewm(alpha=1/period, adjust=False)
        - RS = avg_gain / avg_loss
        - RSI = 100 - (100 / (1 + RS))
        """
        resolved = periods or self._resolve_periods()
        df = df.copy()

        all_periods = tuple(dict.fromkeys((*resolved.rsi_periods, *DEFAULT_RSI_PERIODS)))
        for period in all_periods:
            col_name = f'RSI_{period}'
            if len(df) < period:
                df[col_name] = np.nan
                continue
            # Calculate price change
            delta = df['close'].diff()

            # Separate price gains and losses
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)

            # Use Wilder's EMA / SMMA convention, consistent with common RSI charting tools
            avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

            # Calculate RS and RSI
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

            # Fill NaN values
            rsi = rsi.fillna(50)  # Default is neutral value

            df[col_name] = rsi

        return df
    
    def _analyze_trend(
        self,
        df: pd.DataFrame,
        result: TrendAnalysisResult,
        periods: Optional[IndicatorPeriodConfig] = None,
    ) -> None:
        """
        分析趋势状态
        
        核心逻辑：判断均线排列和趋势强度
        """
        resolved = periods or self._resolve_periods()
        ma_short = result.ma_by_period.get(resolved.ma_short)
        ma_mid = result.ma_by_period.get(resolved.ma_mid)
        ma_long = result.ma_by_period.get(resolved.ma_long)
        short_col = format_ma_label(resolved.ma_short)
        long_col = format_ma_label(resolved.ma_long)

        if ma_short is None or ma_mid is None or ma_long is None:
            result.trend_status = TrendStatus.CONSOLIDATION
            result.ma_alignment = (
                "insufficient data for "
                f"{format_ma_label(resolved.ma_short)}/"
                f"{format_ma_label(resolved.ma_mid)}/"
                f"{format_ma_label(resolved.ma_long)}"
            )
            result.trend_strength = 0
            return
        
        # Determine moving average arrangement.
        if ma_short > ma_mid > ma_long > 0:
            # Check if the spacing is expanding (strong)
            prev = df.iloc[-5] if len(df) >= 5 else df.iloc[-1]
            prev_long = float(prev.get(long_col) or 0)
            prev_short = float(prev.get(short_col) or 0)
            prev_spread = (prev_short - prev_long) / prev_long * 100 if prev_long > 0 else 0
            curr_spread = (ma_short - ma_long) / ma_long * 100 if ma_long > 0 else 0
            
            if curr_spread > prev_spread and curr_spread > 5:
                result.trend_status = TrendStatus.STRONG_BULL
                result.ma_alignment = "强势多头排列，均线发散上行"
                result.trend_strength = 90
            else:
                result.trend_status = TrendStatus.BULL
                result.ma_alignment = (
                    f"多头排列 {format_ma_label(resolved.ma_short)}>"
                    f"{format_ma_label(resolved.ma_mid)}>"
                    f"{format_ma_label(resolved.ma_long)}"
                )
                result.trend_strength = 75
                
        elif ma_short > ma_mid and ma_mid <= ma_long and ma_short > 0 and ma_mid > 0:
            result.trend_status = TrendStatus.WEAK_BULL
            result.ma_alignment = (
                f"弱势多头，{format_ma_label(resolved.ma_short)}>"
                f"{format_ma_label(resolved.ma_mid)} 但 "
                f"{format_ma_label(resolved.ma_mid)}≤{format_ma_label(resolved.ma_long)}"
            )
            result.trend_strength = 55
            
        elif 0 < ma_short < ma_mid < ma_long:
            prev = df.iloc[-5] if len(df) >= 5 else df.iloc[-1]
            prev_long = float(prev.get(long_col) or 0)
            prev_short = float(prev.get(short_col) or 0)
            prev_spread = (prev_long - prev_short) / prev_short * 100 if prev_short > 0 else 0
            curr_spread = (ma_long - ma_short) / ma_short * 100 if ma_short > 0 else 0
            
            if curr_spread > prev_spread and curr_spread > 5:
                result.trend_status = TrendStatus.STRONG_BEAR
                result.ma_alignment = "强势空头排列，均线发散下行"
                result.trend_strength = 10
            else:
                result.trend_status = TrendStatus.BEAR
                result.ma_alignment = (
                    f"空头排列 {format_ma_label(resolved.ma_short)}<"
                    f"{format_ma_label(resolved.ma_mid)}<"
                    f"{format_ma_label(resolved.ma_long)}"
                )
                result.trend_strength = 25
                
        elif ma_short < ma_mid and ma_mid >= ma_long and ma_short > 0 and ma_mid > 0:
            result.trend_status = TrendStatus.WEAK_BEAR
            result.ma_alignment = (
                f"弱势空头，{format_ma_label(resolved.ma_short)}<"
                f"{format_ma_label(resolved.ma_mid)} 但 "
                f"{format_ma_label(resolved.ma_mid)}≥{format_ma_label(resolved.ma_long)}"
            )
            result.trend_strength = 40
            
        else:
            result.trend_status = TrendStatus.CONSOLIDATION
            result.ma_alignment = "均线缠绕，趋势不明"
            result.trend_strength = 50
    
    def _calculate_bias(
        self,
        result: TrendAnalysisResult,
        periods: IndicatorPeriodConfig,
    ) -> None:
        """
        计算乖离率
        
        乖离率 = (现价 - 均线) / 均线 * 100%
        
        严进策略：乖离率超过 5% 不追高
        """
        price = result.current_price
        
        if result.ma5 is not None and result.ma5 > 0:
            result.bias_ma5 = (price - result.ma5) / result.ma5 * 100
        if result.ma10 is not None and result.ma10 > 0:
            result.bias_ma10 = (price - result.ma10) / result.ma10 * 100
        if result.ma20 is not None and result.ma20 > 0:
            result.bias_ma20 = (price - result.ma20) / result.ma20 * 100
        result.bias_by_period = {
            period: (
                (price - value) / value * 100
                if value is not None and value > 0
                else None
            )
            for period, value in result.ma_by_period.items()
            if period in periods.ma_periods
        }
    
    def _analyze_volume(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        """
        分析量能
        
        偏好：缩量回调 > 放量上涨 > 缩量上涨 > 放量下跌
        """
        if len(df) < 5:
            return
        
        latest = df.iloc[-1]
        vol_5d_avg = df['volume'].iloc[-6:-1].mean()
        
        if vol_5d_avg > 0:
            result.volume_ratio_5d = float(latest['volume']) / vol_5d_avg
        
        # Determine price change.
        prev_close = df.iloc[-2]['close']
        price_change = (latest['close'] - prev_close) / prev_close * 100
        
        # Determine volume status
        if result.volume_ratio_5d >= self.VOLUME_HEAVY_RATIO:
            if price_change > 0:
                result.volume_status = VolumeStatus.HEAVY_VOLUME_UP
                result.volume_trend = "放量上涨，多头力量强劲"
            else:
                result.volume_status = VolumeStatus.HEAVY_VOLUME_DOWN
                result.volume_trend = "放量下跌，注意风险"
        elif result.volume_ratio_5d <= self.VOLUME_SHRINK_RATIO:
            if price_change > 0:
                result.volume_status = VolumeStatus.SHRINK_VOLUME_UP
                result.volume_trend = "缩量上涨，上攻动能不足"
            else:
                result.volume_status = VolumeStatus.SHRINK_VOLUME_DOWN
                result.volume_trend = "缩量回调，洗盘特征明显（好）"
        else:
            result.volume_status = VolumeStatus.NORMAL
            result.volume_trend = "量能正常"
    
    def _analyze_support_resistance(
        self,
        df: pd.DataFrame,
        result: TrendAnalysisResult,
        periods: IndicatorPeriodConfig,
    ) -> None:
        """
        分析支撑压力位
        
        买点偏好：回踩 MA5/MA10 获得支撑
        """
        price = result.current_price
        
        # Check if support is found near MA5
        if result.ma5 is not None and result.ma5 > 0:
            ma5_distance = abs(price - result.ma5) / result.ma5
            if ma5_distance <= self.MA_SUPPORT_TOLERANCE and price >= result.ma5:
                result.support_ma5 = True
                result.support_levels.append(result.ma5)
        
        # Check if support is found near MA10
        if result.ma10 is not None and result.ma10 > 0:
            ma10_distance = abs(price - result.ma10) / result.ma10
            if ma10_distance <= self.MA_SUPPORT_TOLERANCE and price >= result.ma10:
                result.support_ma10 = True
                if result.ma10 not in result.support_levels:
                    result.support_levels.append(result.ma10)
        
        # MA20 as an important support.
        if result.ma20 is not None and result.ma20 > 0 and price >= result.ma20:
            result.support_levels.append(result.ma20)

        for period in periods.ma_periods[:2]:
            value = result.ma_by_period.get(period)
            supported = False
            if value is not None and value > 0:
                distance = abs(price - value) / value
                supported = distance <= self.MA_SUPPORT_TOLERANCE and price >= value
                if supported and value not in result.support_levels:
                    result.support_levels.append(value)
            result.support_by_period[period] = supported
        
        # Recent high as resistance
        if len(df) >= 20:
            recent_high = df['high'].iloc[-20:].max()
            if recent_high > price:
                result.resistance_levels.append(recent_high)

    def _analyze_macd(
        self,
        df: pd.DataFrame,
        result: TrendAnalysisResult,
        periods: Optional[IndicatorPeriodConfig] = None,
    ) -> None:
        """
        分析 MACD 指标

        核心信号：
        - 零轴上金叉：最强买入信号
        - 金叉：DIF 上穿 DEA
        - 死叉：DIF 下穿 DEA
        """
        resolved = periods or self._resolve_periods()
        if len(df) < resolved.macd_slow:
            result.macd_signal = "数据不足"
            return

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # Get MACD data
        result.macd_dif = float(latest['MACD_DIF'])
        result.macd_dea = float(latest['MACD_DEA'])
        result.macd_bar = float(latest['MACD_BAR'])
        result.macd_reading = MACDReading(
            fast_period=resolved.macd_fast,
            slow_period=resolved.macd_slow,
            signal_period=resolved.macd_signal,
            label=(
                f"MACD({resolved.macd_fast},{resolved.macd_slow},"
                f"{resolved.macd_signal})"
            ),
            dif=result.macd_dif,
            dea=result.macd_dea,
            bar=result.macd_bar,
            available=True,
            reason=None,
            bar_count=result.indicator_bar_count,
            as_of=result.indicator_as_of,
            source=result.indicator_period_source,
        )

        # Identify golden crosses and death crosses.
        prev_dif_dea = prev['MACD_DIF'] - prev['MACD_DEA']
        curr_dif_dea = result.macd_dif - result.macd_dea

        # Golden cross: DIF crosses above DEA
        is_golden_cross = prev_dif_dea <= 0 and curr_dif_dea > 0

        # Death cross: DIF crosses below DEA
        is_death_cross = prev_dif_dea >= 0 and curr_dif_dea < 0

        # Zero-axis crossing
        prev_zero = prev['MACD_DIF']
        curr_zero = result.macd_dif
        is_crossing_up = prev_zero <= 0 and curr_zero > 0
        is_crossing_down = prev_zero >= 0 and curr_zero < 0

        # Check MACD status
        if is_golden_cross and curr_zero > 0:
            result.macd_status = MACDStatus.GOLDEN_CROSS_ZERO
            result.macd_signal = "⭐ 零轴上金叉，强烈买入信号！"
        elif is_crossing_up:
            result.macd_status = MACDStatus.CROSSING_UP
            result.macd_signal = "⚡ DIF上穿零轴，趋势转强"
        elif is_golden_cross:
            result.macd_status = MACDStatus.GOLDEN_CROSS
            result.macd_signal = "✅ 金叉，趋势向上"
        elif is_death_cross:
            result.macd_status = MACDStatus.DEATH_CROSS
            result.macd_signal = "❌ 死叉，趋势向下"
        elif is_crossing_down:
            result.macd_status = MACDStatus.CROSSING_DOWN
            result.macd_signal = "⚠️ DIF下穿零轴，趋势转弱"
        elif result.macd_dif > 0 and result.macd_dea > 0:
            result.macd_status = MACDStatus.BULLISH
            result.macd_signal = "✓ 多头排列，持续上涨"
        elif result.macd_dif < 0 and result.macd_dea < 0:
            result.macd_status = MACDStatus.BEARISH
            result.macd_signal = "⚠ 空头排列，持续下跌"
        else:
            result.macd_status = MACDStatus.BULLISH
            result.macd_signal = " MACD 中性区域"

    def _analyze_rsi(
        self,
        df: pd.DataFrame,
        result: TrendAnalysisResult,
        periods: Optional[IndicatorPeriodConfig] = None,
    ) -> None:
        """
        分析 RSI 指标

        核心判断：
        - RSI > 70：超买，谨慎追高
        - RSI < 30：超卖，关注反弹
        - 40-60：中性区域
        """
        resolved = periods or self._resolve_periods()
        latest = df.iloc[-1]

        rsi_by_period: Dict[int, Any] = {}
        all_periods = tuple(dict.fromkeys((*resolved.rsi_periods, *DEFAULT_RSI_PERIODS)))
        for period in all_periods:
            col = f"RSI_{period}"
            if col in latest.index and latest[col] == latest[col]:
                rsi_by_period[period] = float(latest[col])
            else:
                rsi_by_period[period] = None
        result.rsi_by_period = rsi_by_period
        result.rsi_readings = {
            period: IndicatorReading(
                kind="rsi",
                period=period,
                label=f"RSI({period})",
                value=rsi_by_period[period],
                available=rsi_by_period[period] is not None,
                reason=(
                    None
                    if rsi_by_period[period] is not None
                    else f"insufficient_history:need={period},got={result.indicator_bar_count}"
                ),
                bar_count=result.indicator_bar_count,
                as_of=result.indicator_as_of,
                source=result.indicator_period_source,
            )
            for period in resolved.rsi_periods
        }

        # Legacy fields always retain their exact periods.
        result.rsi_6 = rsi_by_period.get(6)
        result.rsi_12 = rsi_by_period.get(12)
        result.rsi_24 = rsi_by_period.get(24)

        primary_period = (
            resolved.rsi_periods[1]
            if len(resolved.rsi_periods) > 1
            else resolved.rsi_periods[0]
        )
        rsi_mid = rsi_by_period.get(primary_period)
        if rsi_mid is None:
            result.rsi_signal = f"RSI({primary_period}) 数据不足"
            return

        # Check RSI status
        if rsi_mid > self.RSI_OVERBOUGHT:
            result.rsi_status = RSIStatus.OVERBOUGHT
            result.rsi_signal = f"⚠️ RSI({primary_period})超买({rsi_mid:.1f}>70)，短期回调风险高"
        elif rsi_mid > 60:
            result.rsi_status = RSIStatus.STRONG_BUY
            result.rsi_signal = f"✅ RSI({primary_period})强势({rsi_mid:.1f})，多头力量充足"
        elif rsi_mid >= 40:
            result.rsi_status = RSIStatus.NEUTRAL
            result.rsi_signal = f" RSI({primary_period})中性({rsi_mid:.1f})，震荡整理中"
        elif rsi_mid >= self.RSI_OVERSOLD:
            result.rsi_status = RSIStatus.WEAK
            result.rsi_signal = f"⚡ RSI({primary_period})弱势({rsi_mid:.1f})，关注反弹"
        else:
            result.rsi_status = RSIStatus.OVERSOLD
            result.rsi_signal = f"⭐ RSI({primary_period})超卖({rsi_mid:.1f}<30)，反弹机会大"

    def _generate_signal(self, result: TrendAnalysisResult) -> None:
        """
        生成买入信号

        综合评分系统：
        - 趋势（30分）：多头排列得分高
        - 乖离率（20分）：接近 MA5 得分高
        - 量能（15分）：缩量回调得分高
        - 支撑（10分）：获得均线支撑得分高
        - MACD（15分）：金叉和多头得分高
        - RSI（10分）：超卖和强势得分高
        """
        score = 0
        reasons = []
        risks = []

        # === Trend Score (30 Points) ===
        trend_scores = {
            TrendStatus.STRONG_BULL: 30,
            TrendStatus.BULL: 26,
            TrendStatus.WEAK_BULL: 18,
            TrendStatus.CONSOLIDATION: 12,
            TrendStatus.WEAK_BEAR: 8,
            TrendStatus.BEAR: 4,
            TrendStatus.STRONG_BEAR: 0,
        }
        trend_score = trend_scores.get(result.trend_status, 12)
        score += trend_score

        if result.trend_status in [TrendStatus.STRONG_BULL, TrendStatus.BULL]:
            reasons.append(f"✅ {result.trend_status.value}，顺势做多")
        elif result.trend_status in [TrendStatus.BEAR, TrendStatus.STRONG_BEAR]:
            risks.append(f"⚠️ {result.trend_status.value}，不宜做多")

        # === configured short-MA bias score (20 points) ===
        bias_period = result.primary_bias_period or 5
        if bias_period in result.bias_by_period:
            bias = result.bias_by_period[bias_period]
        else:
            # Compatibility for callers constructing the historical result shape
            # directly. Analyzer-produced snapshots always populate bias_by_period.
            bias = {
                5: result.bias_ma5,
                10: result.bias_ma10,
                20: result.bias_ma20,
            }.get(bias_period)
        base_threshold = get_config().bias_threshold

        # Strong trend compensation: relax threshold for STRONG_BULL with high strength
        trend_strength = result.trend_strength if result.trend_strength == result.trend_strength else 0.0
        if result.trend_status == TrendStatus.STRONG_BULL and (trend_strength or 0) >= 70:
            effective_threshold = base_threshold * 1.5
            is_strong_trend = True
        else:
            effective_threshold = base_threshold
            is_strong_trend = False

        ma_label = format_ma_label(bias_period)
        if bias is None or bias != bias:
            risks.append(f"⚠️ {ma_label} 乖离率不可用，未计入位置评分")
        elif bias < 0:
            if bias > -3:
                score += 20
                reasons.append(f"✅ 价格略低于{ma_label}({bias:.1f}%)，回踩买点")
            elif bias > -5:
                score += 16
                reasons.append(f"✅ 价格回踩{ma_label}({bias:.1f}%)，观察支撑")
            else:
                score += 8
                risks.append(f"⚠️ 乖离率过大({bias:.1f}%)，可能破位")
        elif bias < 2:
            score += 18
            reasons.append(f"✅ 价格贴近{ma_label}({bias:.1f}%)，介入好时机")
        elif bias < base_threshold:
            score += 14
            reasons.append(f"⚡ 价格略高于{ma_label}({bias:.1f}%)，可小仓介入")
        elif bias > effective_threshold:
            score += 4
            risks.append(
                f"❌ 乖离率过高({bias:.1f}%>{effective_threshold:.1f}%)，严禁追高！"
            )
        elif bias > base_threshold and is_strong_trend:
            score += 10
            reasons.append(
                f"⚡ 强势趋势中乖离率偏高({bias:.1f}%)，可轻仓追踪"
            )
        else:
            score += 4
            risks.append(
                f"❌ 乖离率过高({bias:.1f}%>{base_threshold:.1f}%)，严禁追高！"
            )

        # === Volume score (15 points) ===
        volume_scores = {
            VolumeStatus.SHRINK_VOLUME_DOWN: 15,  # A pullback on declining volume is best
            VolumeStatus.HEAVY_VOLUME_UP: 12,     # A rise on heavy volume is next best
            VolumeStatus.NORMAL: 10,
            VolumeStatus.SHRINK_VOLUME_UP: 6,     # A rise on weak volume provides poor confirmation
            VolumeStatus.HEAVY_VOLUME_DOWN: 0,    # A decline on heavy volume is worst
        }
        vol_score = volume_scores.get(result.volume_status, 8)
        score += vol_score

        if result.volume_status == VolumeStatus.SHRINK_VOLUME_DOWN:
            reasons.append("✅ 缩量回调，主力洗盘")
        elif result.volume_status == VolumeStatus.HEAVY_VOLUME_DOWN:
            risks.append("⚠️ 放量下跌，注意风险")

        # === Support Score (10 points) ===
        support_periods = result.primary_ma_periods[:2] or [5, 10]

        def has_support(period: int) -> bool:
            if period in result.support_by_period:
                return result.support_by_period[period]
            return {5: result.support_ma5, 10: result.support_ma10}.get(period, False)

        if support_periods and has_support(support_periods[0]):
            score += 5
            reasons.append(f"✅ {format_ma_label(support_periods[0])}支撑有效")
        if len(support_periods) > 1 and has_support(support_periods[1]):
            score += 5
            reasons.append(f"✅ {format_ma_label(support_periods[1])}支撑有效")

        # === MACD score (15 points) ===
        macd_scores = {
            MACDStatus.GOLDEN_CROSS_ZERO: 15,  # Golden cross on the zero axis is strongest
            MACDStatus.GOLDEN_CROSS: 12,       # Golden cross
            MACDStatus.CROSSING_UP: 10,        # Crosses above the zero axis
            MACDStatus.BULLISH: 8,             # Bullish
            MACDStatus.BEARISH: 2,             # Bearish
            MACDStatus.CROSSING_DOWN: 0,       # Crosses below the zero axis
            MACDStatus.DEATH_CROSS: 0,         # Death cross
        }
        macd_score = macd_scores.get(result.macd_status, 5)
        score += macd_score

        if result.macd_status in [MACDStatus.GOLDEN_CROSS_ZERO, MACDStatus.GOLDEN_CROSS]:
            reasons.append(f"✅ {result.macd_signal}")
        elif result.macd_status in [MACDStatus.DEATH_CROSS, MACDStatus.CROSSING_DOWN]:
            risks.append(f"⚠️ {result.macd_signal}")
        else:
            reasons.append(result.macd_signal)

        # === RSI Score (10 points) ===
        rsi_scores = {
            RSIStatus.OVERSOLD: 10,       # Oversold is best
            RSIStatus.STRONG_BUY: 8,     # Strong
            RSIStatus.NEUTRAL: 5,        # Neutral
            RSIStatus.WEAK: 3,            # Weak
            RSIStatus.OVERBOUGHT: 0,       # Overbought is worst
        }
        rsi_score = rsi_scores.get(result.rsi_status, 5)
        score += rsi_score

        if result.rsi_status in [RSIStatus.OVERSOLD, RSIStatus.STRONG_BUY]:
            reasons.append(f"✅ {result.rsi_signal}")
        elif result.rsi_status == RSIStatus.OVERBOUGHT:
            risks.append(f"⚠️ {result.rsi_signal}")
        else:
            reasons.append(result.rsi_signal)

        # === Comprehensive Assessment ===
        result.signal_score = score
        result.signal_reasons = reasons
        # Preserve earlier structural notes (e.g. insufficient MA data) then append
        # signal-time risk factors without dropping pre-existing annotations.
        preserved = [
            note
            for note in result.risk_factors
            if note and note not in risks
        ]
        result.risk_factors = preserved + risks

        # Generate buy signals (consistent with canonical decision scale)
        score_signal = signal_key_for_score(score)
        if score_signal == "strong_buy" and result.trend_status in [TrendStatus.STRONG_BULL, TrendStatus.BULL]:
            result.buy_signal = BuySignal.STRONG_BUY
        elif score_signal in {"strong_buy", "buy"} and result.trend_status in [
            TrendStatus.STRONG_BULL,
            TrendStatus.BULL,
            TrendStatus.WEAK_BULL,
        ]:
            result.buy_signal = BuySignal.BUY
        elif score_signal in {"strong_buy", "buy"} and result.trend_status in [
            TrendStatus.CONSOLIDATION,
            TrendStatus.WEAK_BEAR,
        ]:
            result.buy_signal = BuySignal.WAIT
        elif score_signal == "watch":
            result.buy_signal = BuySignal.WAIT
        elif score_signal == "sell" or result.trend_status in [TrendStatus.BEAR, TrendStatus.STRONG_BEAR]:
            result.buy_signal = BuySignal.STRONG_SELL
        else:
            result.buy_signal = BuySignal.SELL
    
    def format_analysis(self, result: TrendAnalysisResult) -> str:
        """
        格式化分析结果为文本

        Args:
            result: 分析结果

        Returns:
            格式化的分析文本
        """
        def _fmt(value: Optional[float], digits: int = 2) -> str:
            return "N/A" if value is None else f"{value:.{digits}f}"

        primary_bias = result.bias_by_period.get(result.primary_bias_period or 5)
        dynamic_ma_lines = [
            f"   {reading.label}: {_fmt(reading.value)}"
            for reading in result.ma_readings.values()
        ]
        dynamic_rsi_lines = [
            f"   {reading.label}: {_fmt(reading.value, 1)}"
            for reading in result.rsi_readings.values()
        ]
        macd_reading = result.macd_reading
        macd_label = macd_reading.label if macd_reading is not None else "MACD"
        macd_dif = macd_reading.dif if macd_reading is not None else result.macd_dif
        macd_dea = macd_reading.dea if macd_reading is not None else result.macd_dea
        macd_bar = macd_reading.bar if macd_reading is not None else result.macd_bar
        lines = [
            f"=== {result.code} 趋势分析 ===",
            f"",
            f"📊 趋势判断: {result.trend_status.value}",
            f"   均线排列: {result.ma_alignment}",
            f"   趋势强度: {result.trend_strength}/100",
            f"",
            f"📈 均线数据:",
            f"   现价: {result.current_price:.2f}",
            *dynamic_ma_lines,
            f"   {format_ma_label(result.primary_bias_period or 5)}乖离: "
            f"{'N/A' if primary_bias is None else f'{primary_bias:+.2f}%'}",
            f"",
            f"📊 量能分析: {result.volume_status.value}",
            f"   量比(vs5日): {result.volume_ratio_5d:.2f}",
            f"   量能趋势: {result.volume_trend}",
            f"",
            f"📈 {macd_label}指标: {result.macd_status.value}",
            f"   DIF: {_fmt(macd_dif, 4)}",
            f"   DEA: {_fmt(macd_dea, 4)}",
            f"   MACD: {_fmt(macd_bar, 4)}",
            f"   信号: {result.macd_signal}",
            f"",
            f"📊 RSI指标: {result.rsi_status.value}",
            *dynamic_rsi_lines,
            f"   信号: {result.rsi_signal}",
            f"",
            f"🎯 操作建议: {result.buy_signal.value}",
            f"   综合评分: {result.signal_score}/100",
        ]

        if result.signal_reasons:
            lines.append(f"")
            lines.append(f"✅ 买入理由:")
            for reason in result.signal_reasons:
                lines.append(f"   {reason}")

        if result.risk_factors:
            lines.append(f"")
            lines.append(f"⚠️ 风险因素:")
            for risk in result.risk_factors:
                lines.append(f"   {risk}")

        return "\n".join(lines)


def analyze_stock(df: pd.DataFrame, code: str) -> TrendAnalysisResult:
    """
    便捷函数：分析单只股票
    
    Args:
        df: 包含 OHLCV 数据的 DataFrame
        code: 股票代码
        
    Returns:
        TrendAnalysisResult 分析结果
    """
    analyzer = StockTrendAnalyzer()
    return analyzer.analyze(df, code)


if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.INFO)
    
    # Simulate data testing
    import numpy as np
    
    dates = pd.date_range(start='2025-01-01', periods=60, freq='D')
    np.random.seed(42)
    
    # Simulate data with bullish alignment
    base_price = 10.0
    prices = [base_price]
    for i in range(59):
        change = np.random.randn() * 0.02 + 0.003  # Slightly rising trend
        prices.append(prices[-1] * (1 + change))
    
    df = pd.DataFrame({
        'date': dates,
        'open': prices,
        'high': [p * (1 + np.random.uniform(0, 0.02)) for p in prices],
        'low': [p * (1 - np.random.uniform(0, 0.02)) for p in prices],
        'close': prices,
        'volume': [np.random.randint(1000000, 5000000) for _ in prices],
    })
    
    analyzer = StockTrendAnalyzer()
    result = analyzer.analyze(df, '000001')
    print(analyzer.format_analysis(result))
