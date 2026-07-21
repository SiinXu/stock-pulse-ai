# -*- coding: utf-8 -*-
"""
===================================
Trend trading analyzer - Based on user trading philosophy
===================================

Core principles of trading philosophy:
1. Strict entry strategy - don't chase highs, pursue the success rate of each trade
2. Trend trading - MA5 > MA10 > MA20 bullish alignment, follow the trend
3. Efficiency first. - Focus on stocks with good volume flow structure.
4. Entry Preference - Rebound to MA5/MA10 for entry

Technical standards:
- bullish alignment: MA5 > MA10 > MA20
- bias ratio: (Close - MA5) / MA5 < 5% (Do not chase highs)
- Momentum Patterns: Prioritize Shrinking Volume Rebound
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List
from enum import Enum

import pandas as pd
import numpy as np

from src.config import get_config
from src.schemas.decision_scale import signal_key_for_score

logger = logging.getLogger(__name__)


class TrendStatus(Enum):
    """Trend status enumeration"""
    STRONG_BULL = "强势多头"      # MA5 > MA10 > MA20, and the gap expands
    BULL = "多头排列"             # MA5 > MA10 > MA20
    WEAK_BULL = "弱势多头"        # MA5 > MA10, but MA10 < MA20
    CONSOLIDATION = "盘整"        # Moving average wrapping
    WEAK_BEAR = "弱势空头"        # MA5 < MA10, but MA10 > MA20
    BEAR = "空头排列"             # MA5 < MA10 < MA20
    STRONG_BEAR = "强势空头"      # MA5 < MA10 < MA20, and the distance expands.


class VolumeStatus(Enum):
    """Momentum Enumeration"""
    HEAVY_VOLUME_UP = "放量上涨"       # Volume and price rising together
    HEAVY_VOLUME_DOWN = "放量下跌"     # Stop-loss kill
    SHRINK_VOLUME_UP = "缩量上涨"      # No volume increase
    SHRINK_VOLUME_DOWN = "缩量回调"    # Volume shrinkage callback (good)
    NORMAL = "量能正常"


class BuySignal(Enum):
    """Buy Signal Enum"""
    STRONG_BUY = "强烈买入"       # Multiple conditions satisfied
    BUY = "买入"                  # Basic conditions met
    HOLD = "持有"                 # Currently holding, can continue
    WAIT = "观望"                 # Wait for a better opportunity.
    SELL = "卖出"                 # Weak trend
    STRONG_SELL = "强烈卖出"      # Trend disruption


class MACDStatus(Enum):
    """MACD state enumeration"""
    GOLDEN_CROSS_ZERO = "零轴上金叉"      # DIF crosses DEA and is above the zero axis
    GOLDEN_CROSS = "金叉"                # DIF crosses DEA
    BULLISH = "多头"                    # DIF>DEA>0
    CROSSING_UP = "上穿零轴"             # DIF crosses the zero axis
    CROSSING_DOWN = "下穿零轴"           # DIF crosses below the zero axis
    BEARISH = "空头"                    # DIF<DEA<0
    DEATH_CROSS = "死叉"                # DIF crosses below DEA


class RSIStatus(Enum):
    """RSI Status Enumeration"""
    OVERBOUGHT = "超买"        # RSI > 70
    STRONG_BUY = "强势买入"    # 50 < RSI < 70
    NEUTRAL = "中性"          # 40 <= RSI <= 60
    WEAK = "弱势"             # 30 < RSI < 40
    OVERSOLD = "超卖"         # RSI < 30


@dataclass
class TrendAnalysisResult:
    """Trend analysis results"""
    code: str
    
    # Trend judgment
    trend_status: TrendStatus = TrendStatus.CONSOLIDATION
    ma_alignment: str = ""           # Moving average arrangement description
    trend_strength: float = 0.0      # Trend strength 0-100
    
    # Moving average data
    ma5: float = 0.0
    ma10: float = 0.0
    ma20: float = 0.0
    ma60: float = 0.0
    current_price: float = 0.0
    
    # bias ratio (deviation from MA5)
    bias_ma5: float = 0.0            # (Close - MA5) / MA5 * 100
    bias_ma10: float = 0.0
    bias_ma20: float = 0.0
    
    # Momentum Analysis
    volume_status: VolumeStatus = VolumeStatus.NORMAL
    volume_ratio_5d: float = 0.0     # Daily trading volume / 5-day average
    volume_trend: str = ""           # Momentum Trend Description
    
    # Support resistance
    support_ma5: bool = False        # Whether MA5 acts as support
    support_ma10: bool = False       # Whether MA10 acts as support
    resistance_levels: List[float] = field(default_factory=list)
    support_levels: List[float] = field(default_factory=list)

    # MACD indicator
    macd_dif: float = 0.0          # DIF fast line
    macd_dea: float = 0.0          # DEA slow line
    macd_bar: float = 0.0           # MACD candlestick chart
    macd_status: MACDStatus = MACDStatus.BULLISH
    macd_signal: str = ""            # MACD signal description

    # RSI Indicator
    rsi_6: float = 0.0              # RSI(6) Short-Term
    rsi_12: float = 0.0             # RSI(12) Medium-Term
    rsi_24: float = 0.0             # RSI(24) Long-Term
    rsi_status: RSIStatus = RSIStatus.NEUTRAL
    rsi_signal: str = ""              # RSI Signal Description

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
            'current_price': self.current_price,
            'bias_ma5': self.bias_ma5,
            'bias_ma10': self.bias_ma10,
            'bias_ma20': self.bias_ma20,
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
            'rsi_6': self.rsi_6,
            'rsi_12': self.rsi_12,
            'rsi_24': self.rsi_24,
            'rsi_status': self.rsi_status.value,
            'rsi_signal': self.rsi_signal,
        }


class StockTrendAnalyzer:
    """
    Stock Trend Analyzer

    Implemented based on user trading concepts:
    1. Trend judgment - bullish alignment with MA5 > MA10 > MA20
    2. bias ratio detection - Do not chase highs, do not buy when deviated from MA5 by more than 5%
    3. Momentum Analysis - Prefer Shrinking Volume Rebound
    4. Entry Identification - Support after rebounding MA5/MA10
    5. MACD indicator - trend confirmation and bullish/bearish crossover signals
    6. RSI Indicator - Overbought/Oversold Judgment
    """
    
    # Trading parameter configuration (BIAS_THRESHOLD read from Config, see _generate_signal)
    VOLUME_SHRINK_RATIO = 0.7   # Volume shrinkage judgment threshold (daily volume / 5-day average volume)
    VOLUME_HEAVY_RATIO = 1.5    # Threshold for significant judgment
    MA_SUPPORT_TOLERANCE = 0.02  # MA support judgment tolerance (2%).

    # MACD parameters (standard 12/26/9)
    MACD_FAST = 12              # Fast cycle period
    MACD_SLOW = 26             # Slow line cycle
    MACD_SIGNAL = 9             # Signal line cycle

    # RSI Parameters
    RSI_SHORT = 6               # Short RSI Cycle
    RSI_MID = 12               # Medium-term RSI cycle
    RSI_LONG = 24              # Long RSI period
    RSI_OVERBOUGHT = 70        # Overbought threshold
    RSI_OVERSOLD = 30          # Oversold threshold
    
    def __init__(self):
        """Initialize analyzer"""
        pass
    
    def analyze(self, df: pd.DataFrame, code: str) -> TrendAnalysisResult:
        """
        Analyze stock trends
        
        Args:
            df: DataFrame containing OHLCV data
            code: stock code
            
        Returns:
            TrendAnalysisResult analysis results
        """
        result = TrendAnalysisResult(code=code)
        
        if df is None or df.empty or len(df) < 20:
            logger.warning(f"{code} 数据不足，无法进行趋势分析")
            result.risk_factors.append("数据不足，无法完成分析")
            return result
        
        # Ensure data is sorted by date
        df = df.sort_values('date').reset_index(drop=True)
        
        # Calculate moving average
        df = self._calculate_mas(df)

        # Calculate MACD and RSI
        df = self._calculate_macd(df)
        df = self._calculate_rsi(df)

        # Get latest data
        latest = df.iloc[-1]
        result.current_price = float(latest['close'])
        result.ma5 = float(latest['MA5'])
        result.ma10 = float(latest['MA10'])
        result.ma20 = float(latest['MA20'])
        result.ma60 = float(latest.get('MA60', 0))

        # 1. Trend judgment
        self._analyze_trend(df, result)

        # 2. bias ratio calculation
        self._calculate_bias(result)

        # 3. Momentum Analysis
        self._analyze_volume(df, result)

        # 4. Resistance support analysis
        self._analyze_support_resistance(df, result)

        # 5. MACD analysis
        self._analyze_macd(df, result)

        # 6. RSI Analysis
        self._analyze_rsi(df, result)

        # 7. Generate buy signals
        self._generate_signal(result)

        return result
    
    def _calculate_mas(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate moving average"""
        df = df.copy()
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA10'] = df['close'].rolling(window=10).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        if len(df) >= 60:
            df['MA60'] = df['close'].rolling(window=60).mean()
        else:
            df['MA60'] = df['MA20']  # Use MA20 as a replacement when data is insufficient
        return df

    def _calculate_macd(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate MACD indicator

        Formula:
        - EMA(12): 12-day exponential moving average
        - EMA(26): 26-day exponential moving average
        - DIF = EMA(12) - EMA(26)
        - DEA = EMA(DIF, 9)
        - MACD = (DIF - DEA) * 2
        """
        df = df.copy()

        # Calculate fast and slow line EMA
        ema_fast = df['close'].ewm(span=self.MACD_FAST, adjust=False).mean()
        ema_slow = df['close'].ewm(span=self.MACD_SLOW, adjust=False).mean()

        # Calculate Quick Line DIF
        df['MACD_DIF'] = ema_fast - ema_slow

        # Calculate signal line DEA
        df['MACD_DEA'] = df['MACD_DIF'].ewm(span=self.MACD_SIGNAL, adjust=False).mean()

        # Calculate Bar Chart
        df['MACD_BAR'] = (df['MACD_DIF'] - df['MACD_DEA']) * 2

        return df

    def _calculate_rsi(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate RSI indicator (Wilder's EMA / SMMA)

        Formula:
        - avg_gain / avg_loss Use ewm(alpha=1/period, adjust=False)
        - RS = avg_gain / avg_loss
        - RSI = 100 - (100 / (1 + RS))
        """
        df = df.copy()

        for period in [self.RSI_SHORT, self.RSI_MID, self.RSI_LONG]:
            # Calculate price change
            delta = df['close'].diff()

            # Separate rising and falling stocks
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)

            # Use Wilder's EMA / SMMA range, consistent with common RSI chart tools
            avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

            # Calculate RS and RSI
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

            # Fill NaN values
            rsi = rsi.fillna(50)  # Default is neutral value

            # Add to DataFrame
            col_name = f'RSI_{period}'
            df[col_name] = rsi

        return df
    
    def _analyze_trend(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        """
        Analyze trend status
        
        Core Logic: Analyze MA Arrangement and Trend Strength
        """
        ma5, ma10, ma20 = result.ma5, result.ma10, result.ma20
        
        # Determine moving average arrangement.
        if ma5 > ma10 > ma20:
            # Check if the spacing is expanding (strong)
            prev = df.iloc[-5] if len(df) >= 5 else df.iloc[-1]
            prev_spread = (prev['MA5'] - prev['MA20']) / prev['MA20'] * 100 if prev['MA20'] > 0 else 0
            curr_spread = (ma5 - ma20) / ma20 * 100 if ma20 > 0 else 0
            
            if curr_spread > prev_spread and curr_spread > 5:
                result.trend_status = TrendStatus.STRONG_BULL
                result.ma_alignment = "强势多头排列，均线发散上行"
                result.trend_strength = 90
            else:
                result.trend_status = TrendStatus.BULL
                result.ma_alignment = "多头排列 MA5>MA10>MA20"
                result.trend_strength = 75
                
        elif ma5 > ma10 and ma10 <= ma20:
            result.trend_status = TrendStatus.WEAK_BULL
            result.ma_alignment = "弱势多头，MA5>MA10 但 MA10≤MA20"
            result.trend_strength = 55
            
        elif ma5 < ma10 < ma20:
            prev = df.iloc[-5] if len(df) >= 5 else df.iloc[-1]
            prev_spread = (prev['MA20'] - prev['MA5']) / prev['MA5'] * 100 if prev['MA5'] > 0 else 0
            curr_spread = (ma20 - ma5) / ma5 * 100 if ma5 > 0 else 0
            
            if curr_spread > prev_spread and curr_spread > 5:
                result.trend_status = TrendStatus.STRONG_BEAR
                result.ma_alignment = "强势空头排列，均线发散下行"
                result.trend_strength = 10
            else:
                result.trend_status = TrendStatus.BEAR
                result.ma_alignment = "空头排列 MA5<MA10<MA20"
                result.trend_strength = 25
                
        elif ma5 < ma10 and ma10 >= ma20:
            result.trend_status = TrendStatus.WEAK_BEAR
            result.ma_alignment = "弱势空头，MA5<MA10 但 MA10≥MA20"
            result.trend_strength = 40
            
        else:
            result.trend_status = TrendStatus.CONSOLIDATION
            result.ma_alignment = "均线缠绕，趋势不明"
            result.trend_strength = 50
    
    def _calculate_bias(self, result: TrendAnalysisResult) -> None:
        """
        Calculate bias ratio
        
        bias ratio = (Current price - Moving average) / Moving average * 100%
        
        Strict entry strategy: If the bias ratio exceeds 5%, do not chase highs
        """
        price = result.current_price
        
        if result.ma5 > 0:
            result.bias_ma5 = (price - result.ma5) / result.ma5 * 100
        if result.ma10 > 0:
            result.bias_ma10 = (price - result.ma10) / result.ma10 * 100
        if result.ma20 > 0:
            result.bias_ma20 = (price - result.ma20) / result.ma20 * 100
    
    def _analyze_volume(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        """
        Analyze K-line data
        
        Preference: Shrinkage callback > Volume expansion increase > Shrinkage increase > Volume decrease
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
        
        # Momentum Status Judgment
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
    
    def _analyze_support_resistance(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        """
        Analyze support and resistance levels.
        
        Entry Preference: Support after rebounding MA5/MA10
        """
        price = result.current_price
        
        # Check if support is found near MA5
        if result.ma5 > 0:
            ma5_distance = abs(price - result.ma5) / result.ma5
            if ma5_distance <= self.MA_SUPPORT_TOLERANCE and price >= result.ma5:
                result.support_ma5 = True
                result.support_levels.append(result.ma5)
        
        # Check if support is found near MA10
        if result.ma10 > 0:
            ma10_distance = abs(price - result.ma10) / result.ma10
            if ma10_distance <= self.MA_SUPPORT_TOLERANCE and price >= result.ma10:
                result.support_ma10 = True
                if result.ma10 not in result.support_levels:
                    result.support_levels.append(result.ma10)
        
        # MA20 as an important support.
        if result.ma20 > 0 and price >= result.ma20:
            result.support_levels.append(result.ma20)
        
        # Recent high as resistance
        if len(df) >= 20:
            recent_high = df['high'].iloc[-20:].max()
            if recent_high > price:
                result.resistance_levels.append(recent_high)

    def _analyze_macd(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        """
        Analyze MACD indicator

        Core signal:
        - Golden cross on the zero axis: strongest buy signal
        - Green cross: DIF breaks above DEA
        - Dead cross: DIF below DEA
        """
        if len(df) < self.MACD_SLOW:
            result.macd_signal = "数据不足"
            return

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # Get MACD data
        result.macd_dif = float(latest['MACD_DIF'])
        result.macd_dea = float(latest['MACD_DEA'])
        result.macd_bar = float(latest['MACD_BAR'])

        # Identify golden crosses and death crosses.
        prev_dif_dea = prev['MACD_DIF'] - prev['MACD_DEA']
        curr_dif_dea = result.macd_dif - result.macd_dea

        # Green cross: DIF breaks above DEA
        is_golden_cross = prev_dif_dea <= 0 and curr_dif_dea > 0

        # Dead cross: DIF below DEA
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

    def _analyze_rsi(self, df: pd.DataFrame, result: TrendAnalysisResult) -> None:
        """
        Analyze RSI indicator

        Core Judgment:
        - RSI > 70: Overbought, be cautious of chasing highs
        - RSI < 30: Overbought, watch for rebound
        - 40-60: Neutral zone
        """
        if len(df) < self.RSI_LONG:
            result.rsi_signal = "数据不足"
            return

        latest = df.iloc[-1]

        # Get RSI data
        result.rsi_6 = float(latest[f'RSI_{self.RSI_SHORT}'])
        result.rsi_12 = float(latest[f'RSI_{self.RSI_MID}'])
        result.rsi_24 = float(latest[f'RSI_{self.RSI_LONG}'])

        # Use medium-term RSI(12) as the primary indicator
        rsi_mid = result.rsi_12

        # Check RSI status
        if rsi_mid > self.RSI_OVERBOUGHT:
            result.rsi_status = RSIStatus.OVERBOUGHT
            result.rsi_signal = f"⚠️ RSI超买({rsi_mid:.1f}>70)，短期回调风险高"
        elif rsi_mid > 60:
            result.rsi_status = RSIStatus.STRONG_BUY
            result.rsi_signal = f"✅ RSI强势({rsi_mid:.1f})，多头力量充足"
        elif rsi_mid >= 40:
            result.rsi_status = RSIStatus.NEUTRAL
            result.rsi_signal = f" RSI中性({rsi_mid:.1f})，震荡整理中"
        elif rsi_mid >= self.RSI_OVERSOLD:
            result.rsi_status = RSIStatus.WEAK
            result.rsi_signal = f"⚡ RSI弱势({rsi_mid:.1f})，关注反弹"
        else:
            result.rsi_status = RSIStatus.OVERSOLD
            result.rsi_signal = f"⭐ RSI超卖({rsi_mid:.1f}<30)，反弹机会大"

    def _generate_signal(self, result: TrendAnalysisResult) -> None:
        """
        Generate buy signals

        Overall rating system:
        - Trend (30 points): bullish alignment scores highly
        - Bias ratio (20 points): proximity to MA5 scores highly
        - Momentum (15min): High Score for Shrinking Volume Rebound
        - Support (10 points): Obtain high scoring for moving average support
        - MACD (15-minute): Golden cross and bullish score high
        - RSI (10min): Oversold and Strong Score High
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

        # === bias ratio Score (20 points, strong trend compensation) ===
        bias = result.bias_ma5
        if bias != bias or bias is None:  # NaN or None defense
            bias = 0.0
        base_threshold = get_config().bias_threshold

        # Strong trend compensation: relax threshold for STRONG_BULL with high strength
        trend_strength = result.trend_strength if result.trend_strength == result.trend_strength else 0.0
        if result.trend_status == TrendStatus.STRONG_BULL and (trend_strength or 0) >= 70:
            effective_threshold = base_threshold * 1.5
            is_strong_trend = True
        else:
            effective_threshold = base_threshold
            is_strong_trend = False

        if bias < 0:
            # Price below MA5 (pullback)
            if bias > -3:
                score += 20
                reasons.append(f"✅ 价格略低于MA5({bias:.1f}%)，回踩买点")
            elif bias > -5:
                score += 16
                reasons.append(f"✅ 价格回踩MA5({bias:.1f}%)，观察支撑")
            else:
                score += 8
                risks.append(f"⚠️ 乖离率过大({bias:.1f}%)，可能破位")
        elif bias < 2:
            score += 18
            reasons.append(f"✅ 价格贴近MA5({bias:.1f}%)，介入好时机")
        elif bias < base_threshold:
            score += 14
            reasons.append(f"⚡ 价格略高于MA5({bias:.1f}%)，可小仓介入")
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

        # === Quant Score (15 points) ===
        volume_scores = {
            VolumeStatus.SHRINK_VOLUME_DOWN: 15,  # Volume shrinkage callback optimal
            VolumeStatus.HEAVY_VOLUME_UP: 12,     # Significant increase is secondary; significant decrease is worst
            VolumeStatus.NORMAL: 10,
            VolumeStatus.SHRINK_VOLUME_UP: 6,     # Poor volume increase
            VolumeStatus.HEAVY_VOLUME_DOWN: 0,    # Significant decrease is the worst
        }
        vol_score = volume_scores.get(result.volume_status, 8)
        score += vol_score

        if result.volume_status == VolumeStatus.SHRINK_VOLUME_DOWN:
            reasons.append("✅ 缩量回调，主力洗盘")
        elif result.volume_status == VolumeStatus.HEAVY_VOLUME_DOWN:
            risks.append("⚠️ 放量下跌，注意风险")

        # === Support Score (10 points) ===
        if result.support_ma5:
            score += 5
            reasons.append("✅ MA5支撑有效")
        if result.support_ma10:
            score += 5
            reasons.append("✅ MA10支撑有效")

        # === MACD Score (15 period) ===
        macd_scores = {
            MACDStatus.GOLDEN_CROSS_ZERO: 15,  # Golden cross on the zero axis is strongest
            MACDStatus.GOLDEN_CROSS: 12,      # Golden Cross
            MACDStatus.CROSSING_UP: 10,       # Breakthrough zero axis
            MACDStatus.BULLISH: 8,            # Long positions
            MACDStatus.BEARISH: 2,            # Trailing stop
            MACDStatus.CROSSING_DOWN: 0,       # Fall below zero axis
            MACDStatus.DEATH_CROSS: 0,        # Dead cross
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
            RSIStatus.OVERSOLD: 10,       # Extreme oversold
            RSIStatus.STRONG_BUY: 8,     # Strong
            RSIStatus.NEUTRAL: 5,        # Neutral
            RSIStatus.WEAK: 3,            # Weak
            RSIStatus.OVERBOUGHT: 0,       # Extreme overbought
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
        result.risk_factors = risks

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
        Format analysis results as text.

        Args:
            result: analysis result

        Returns:
            Formatted analytical text
        """
        lines = [
            f"=== {result.code} 趋势分析 ===",
            f"",
            f"📊 趋势判断: {result.trend_status.value}",
            f"   均线排列: {result.ma_alignment}",
            f"   趋势强度: {result.trend_strength}/100",
            f"",
            f"📈 均线数据:",
            f"   现价: {result.current_price:.2f}",
            f"   MA5:  {result.ma5:.2f} (乖离 {result.bias_ma5:+.2f}%)",
            f"   MA10: {result.ma10:.2f} (乖离 {result.bias_ma10:+.2f}%)",
            f"   MA20: {result.ma20:.2f} (乖离 {result.bias_ma20:+.2f}%)",
            f"",
            f"📊 量能分析: {result.volume_status.value}",
            f"   量比(vs5日): {result.volume_ratio_5d:.2f}",
            f"   量能趋势: {result.volume_trend}",
            f"",
            f"📈 MACD指标: {result.macd_status.value}",
            f"   DIF: {result.macd_dif:.4f}",
            f"   DEA: {result.macd_dea:.4f}",
            f"   MACD: {result.macd_bar:.4f}",
            f"   信号: {result.macd_signal}",
            f"",
            f"📊 RSI指标: {result.rsi_status.value}",
            f"   RSI(6): {result.rsi_6:.1f}",
            f"   RSI(12): {result.rsi_12:.1f}",
            f"   RSI(24): {result.rsi_24:.1f}",
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
    Convenient function: Analyze a single stock
    
    Args:
        df: DataFrame containing OHLCV data
        code: stock code
        
    Returns:
        TrendAnalysisResult analysis results
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
