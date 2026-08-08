# -*- coding: utf-8 -*-
"""Configurable indicator periods — defaults, validation, insufficient data (Issue #172)."""

from __future__ import annotations

import os
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from src.utils.indicator_periods import (
    DEFAULT_MA_PERIODS,
    DEFAULT_MACD_FAST,
    DEFAULT_MACD_SIGNAL,
    DEFAULT_MACD_SLOW,
    DEFAULT_RSI_PERIODS,
    IndicatorPeriodConfig,
    parse_positive_int_list,
    trading_days_to_calendar_days,
    validate_period_list_string,
)
from src.stock_analyzer import StockTrendAnalyzer


def _synthetic_ohlcv(n: int, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    close = 100 + np.cumsum(rng.normal(0.05, 0.8, size=n))
    return pd.DataFrame(
        {
            "date": dates,
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": rng.integers(1_000_000, 5_000_000, size=n),
        }
    )


def _legacy_ma_values(df: pd.DataFrame) -> dict:
    """Reproduce pre-#172 hard-coded MA computation for default equivalence."""
    close = df["close"]
    out = {
        5: float(close.rolling(window=5).mean().iloc[-1]),
        10: float(close.rolling(window=10).mean().iloc[-1]),
        20: float(close.rolling(window=20).mean().iloc[-1]),
    }
    if len(df) >= 60:
        out[60] = float(close.rolling(window=60).mean().iloc[-1])
    else:
        # Historical silent substitution (MA60 ← MA20) — new code must NOT do this.
        out[60] = out[20]
    return out


def _legacy_macd_values(df: pd.DataFrame) -> tuple[float, float, float]:
    ema_fast = df["close"].ewm(span=12, adjust=False).mean()
    ema_slow = df["close"].ewm(span=26, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=9, adjust=False).mean()
    bar = (dif - dea) * 2
    return float(dif.iloc[-1]), float(dea.iloc[-1]), float(bar.iloc[-1])


class TestParsePeriodList:
    def test_empty_uses_default(self) -> None:
        assert parse_positive_int_list(None, default=DEFAULT_MA_PERIODS, field_name="X") == DEFAULT_MA_PERIODS
        assert parse_positive_int_list("  ", default=DEFAULT_MA_PERIODS, field_name="X") == DEFAULT_MA_PERIODS

    def test_custom_periods(self) -> None:
        assert parse_positive_int_list(
            "5,10,20,60,120,250",
            default=DEFAULT_MA_PERIODS,
            field_name="X",
            min_items=3,
        ) == (5, 10, 20, 60, 120, 250)

    def test_invalid_falls_back(self) -> None:
        assert parse_positive_int_list(
            "5,abc,20",
            default=DEFAULT_MA_PERIODS,
            field_name="X",
            min_items=3,
        ) == DEFAULT_MA_PERIODS

    def test_out_of_range_falls_back(self) -> None:
        assert parse_positive_int_list(
            "5,10,9999",
            default=DEFAULT_MA_PERIODS,
            field_name="X",
            min_items=3,
            maximum=500,
        ) == DEFAULT_MA_PERIODS

    def test_strict_validation_rejects_bad(self) -> None:
        ok, msg = validate_period_list_string("5,10,20,60")
        assert ok and msg == ""
        ok, msg = validate_period_list_string("5,0,20")
        assert not ok
        ok, msg = validate_period_list_string("5,abc")
        assert not ok
        ok, msg = validate_period_list_string("5,10,501", maximum=500)
        assert not ok


class TestDefaultEquivalence:
    """Unconfigured periods must match pre-change indicator values on sufficient data."""

    def test_default_ma_macd_rsi_match_legacy_formula(self) -> None:
        df = _synthetic_ohlcv(120)
        analyzer = StockTrendAnalyzer(periods=IndicatorPeriodConfig())
        result = analyzer.analyze(df, "TEST")

        legacy_ma = _legacy_ma_values(df)
        assert result.ma5 == pytest.approx(legacy_ma[5])
        assert result.ma10 == pytest.approx(legacy_ma[10])
        assert result.ma20 == pytest.approx(legacy_ma[20])
        assert result.ma60 == pytest.approx(legacy_ma[60])
        assert result.ma_by_period[5] == pytest.approx(legacy_ma[5])
        assert result.ma_by_period[60] == pytest.approx(legacy_ma[60])

        dif, dea, bar = _legacy_macd_values(df)
        assert result.macd_dif == pytest.approx(dif)
        assert result.macd_dea == pytest.approx(dea)
        assert result.macd_bar == pytest.approx(bar)

        # RSI slots with defaults 6/12/24
        rsi_df = analyzer._calculate_rsi(df.copy(), IndicatorPeriodConfig())
        assert result.rsi_6 == pytest.approx(float(rsi_df.iloc[-1]["RSI_6"]))
        assert result.rsi_12 == pytest.approx(float(rsi_df.iloc[-1]["RSI_12"]))
        assert result.rsi_24 == pytest.approx(float(rsi_df.iloc[-1]["RSI_24"]))

    def test_get_config_defaults_match_constants(self) -> None:
        from src.config import Config

        with patch("src.config.setup_env"), patch.object(
            Config, "_parse_litellm_yaml", return_value=[]
        ), patch.object(Config, "_parse_stock_email_groups", return_value=[]):
            with patch.dict(os.environ, {"STOCK_LIST": "600519"}, clear=True):
                config = Config._load_from_env()
        assert tuple(config.indicator_ma_periods) == DEFAULT_MA_PERIODS
        assert config.indicator_macd_fast == DEFAULT_MACD_FAST
        assert config.indicator_macd_slow == DEFAULT_MACD_SLOW
        assert config.indicator_macd_signal == DEFAULT_MACD_SIGNAL
        assert tuple(config.indicator_rsi_periods) == DEFAULT_RSI_PERIODS


class TestCustomPeriods:
    def test_custom_ma_periods_including_long(self) -> None:
        df = _synthetic_ohlcv(300)
        periods = IndicatorPeriodConfig(ma_periods=(5, 10, 20, 60, 120, 250))
        analyzer = StockTrendAnalyzer(periods=periods)
        result = analyzer.analyze(df, "TEST")

        assert result.ma_by_period[120] is not None
        assert result.ma_by_period[250] is not None
        expected_120 = float(df["close"].rolling(window=120).mean().iloc[-1])
        expected_250 = float(df["close"].rolling(window=250).mean().iloc[-1])
        assert result.ma_by_period[120] == pytest.approx(expected_120)
        assert result.ma_by_period[250] == pytest.approx(expected_250)
        # Named slots still map first four
        assert result.ma5 == pytest.approx(float(df["close"].rolling(5).mean().iloc[-1]))
        assert result.ma60 == pytest.approx(float(df["close"].rolling(60).mean().iloc[-1]))

    def test_custom_macd_periods(self) -> None:
        df = _synthetic_ohlcv(100)
        periods = IndicatorPeriodConfig(macd_fast=8, macd_slow=17, macd_signal=5)
        analyzer = StockTrendAnalyzer(periods=periods)
        result = analyzer.analyze(df, "TEST")
        ema_fast = df["close"].ewm(span=8, adjust=False).mean()
        ema_slow = df["close"].ewm(span=17, adjust=False).mean()
        dif = ema_fast - ema_slow
        assert result.macd_dif == pytest.approx(float(dif.iloc[-1]))


class TestInsufficientData:
    def test_long_period_insufficient_is_none_not_substituted(self) -> None:
        """With only 40 bars, MA60 must be None/0 and annotated — not MA20."""
        df = _synthetic_ohlcv(40)
        periods = IndicatorPeriodConfig(ma_periods=(5, 10, 20, 60))
        analyzer = StockTrendAnalyzer(periods=periods)
        result = analyzer.analyze(df, "TEST")

        assert result.ma_by_period[5] is not None
        assert result.ma_by_period[20] is not None
        assert result.ma_by_period[60] is None
        assert result.ma60 == 0.0
        # Must not equal MA20 (the old silent substitution)
        assert result.ma60 != result.ma20
        notes = " ".join(result.risk_factors)
        assert "MA60" in notes
        assert "insufficient data" in notes

    def test_extra_long_period_insufficient(self) -> None:
        df = _synthetic_ohlcv(80)
        periods = IndicatorPeriodConfig(ma_periods=(5, 10, 20, 60, 250))
        analyzer = StockTrendAnalyzer(periods=periods)
        result = analyzer.analyze(df, "TEST")
        assert result.ma_by_period[60] is not None
        assert result.ma_by_period[250] is None
        assert any("MA250" in n for n in result.risk_factors)


class TestHistoryWindow:
    def test_calendar_lookback_scales_with_max_period(self) -> None:
        short = IndicatorPeriodConfig(ma_periods=(5, 10, 20, 60))
        long = IndicatorPeriodConfig(ma_periods=(5, 10, 20, 60, 250))
        assert long.required_history_calendar_days() > short.required_history_calendar_days()
        assert short.required_history_calendar_days() == trading_days_to_calendar_days(
            short.max_required_trading_days
        )


class TestRegistry:
    def test_indicator_fields_registered(self) -> None:
        from src.core.config_registry import get_field_definition, get_registered_field_keys

        keys = set(get_registered_field_keys())
        for key in (
            "INDICATOR_MA_PERIODS",
            "INDICATOR_MACD_FAST",
            "INDICATOR_MACD_SLOW",
            "INDICATOR_MACD_SIGNAL",
            "INDICATOR_RSI_PERIODS",
        ):
            assert key in keys
            field = get_field_definition(key)
            assert field["category"] == "indicators"
            assert field.get("help_key")
            assert field.get("examples")
            assert field.get("docs")
