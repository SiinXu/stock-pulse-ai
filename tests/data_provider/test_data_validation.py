# -*- coding: utf-8 -*-
"""Offline tests for the financial data validation layer (Issue #185 / T11)."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from data_provider.data_validation import (
    ATTR_KEY,
    CODE_AMOUNT_NEGATIVE,
    CODE_CLOSE_OUT_OF_RANGE,
    CODE_DATE_DUPLICATE,
    CODE_DATE_OUT_OF_ORDER,
    CODE_EMPTY_PAYLOAD,
    CODE_FUND_PB_EXTREME,
    CODE_FUND_PE_EXTREME,
    CODE_FUND_PE_NEGATIVE,
    CODE_FUND_PE_NON_FINITE,
    CODE_HIGH_BELOW_LOW,
    CODE_PCT_CHG_INCONSISTENT,
    CODE_PRICE_MISSING,
    CODE_PRICE_NON_FINITE,
    CODE_PRICE_NON_POSITIVE,
    CODE_VOLUME_NEGATIVE,
    CODE_VOLUME_UNIT_SUSPECT,
    DataValidationRejected,
    ValidationSeverity,
    is_strict_mode,
    is_validation_enabled,
    validate_and_annotate,
    validate_daily_frame,
    validate_fundamental_context,
    validate_fundamental_metrics,
    validate_ohlcv_bar,
    validate_realtime_quote,
)


def _normal_bar(**overrides):
    bar = {
        "date": "2024-01-02",
        "open": 10.0,
        "high": 10.5,
        "low": 9.8,
        "close": 10.2,
        "volume": 1_000_000,
        "amount": 10_200_000.0,
        "pct_chg": 2.0,
        "pre_close": 10.0,
    }
    bar.update(overrides)
    return bar


def _normal_frame(rows=None) -> pd.DataFrame:
    if rows is None:
        rows = [
            _normal_bar(
                date="2024-01-02",
                open=10.0,
                high=10.5,
                low=9.8,
                close=10.2,
                volume=1_000_000,
                amount=10_200_000.0,
                pct_chg=2.0,
                pre_close=10.0,
            ),
            _normal_bar(
                date="2024-01-03",
                open=10.2,
                high=10.8,
                low=10.0,
                close=10.5,
                volume=1_100_000,
                amount=11_550_000.0,
                pct_chg=2.941176,  # (10.5-10.2)/10.2*100
                pre_close=10.2,
            ),
        ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Dirty-data inventory: one case per form
# ---------------------------------------------------------------------------


def test_dirty_price_missing():
    result = validate_ohlcv_bar({"open": 1.0, "high": 1.0, "low": 1.0, "volume": 10})
    assert result.has_reject
    assert any(i.code == CODE_PRICE_MISSING for i in result.issues)


def test_dirty_price_zero_and_negative():
    zero = validate_ohlcv_bar(_normal_bar(close=0.0))
    assert any(i.code == CODE_PRICE_NON_POSITIVE for i in zero.issues)
    neg = validate_ohlcv_bar(_normal_bar(close=-3.5))
    assert any(i.code == CODE_PRICE_NON_POSITIVE for i in neg.issues)


def test_dirty_price_nan_and_infinity():
    nan = validate_ohlcv_bar(_normal_bar(close=float("nan")))
    assert any(i.code == CODE_PRICE_NON_FINITE for i in nan.issues)
    inf = validate_ohlcv_bar(_normal_bar(high=float("inf")))
    assert any(i.code == CODE_PRICE_NON_FINITE for i in inf.issues)
    ninf = validate_ohlcv_bar(_normal_bar(low=float("-inf")))
    assert any(i.code == CODE_PRICE_NON_FINITE for i in ninf.issues)


def test_dirty_pct_chg_inconsistent():
    # close 10.2 vs pre_close 10.0 => expected +2%; claim +9%
    result = validate_ohlcv_bar(_normal_bar(close=10.2, pre_close=10.0, pct_chg=9.0))
    assert result.status in {ValidationSeverity.WARN, ValidationSeverity.REJECT}
    assert any(i.code == CODE_PCT_CHG_INCONSISTENT for i in result.issues)


def test_dirty_high_below_low():
    result = validate_ohlcv_bar(_normal_bar(high=9.0, low=10.0, close=9.5))
    assert any(i.code == CODE_HIGH_BELOW_LOW for i in result.issues)
    assert result.has_reject


def test_dirty_close_out_of_range():
    result = validate_ohlcv_bar(_normal_bar(high=10.5, low=9.8, close=11.0))
    assert any(i.code == CODE_CLOSE_OUT_OF_RANGE for i in result.issues)


def test_dirty_volume_negative():
    result = validate_ohlcv_bar(_normal_bar(volume=-100))
    assert any(i.code == CODE_VOLUME_NEGATIVE for i in result.issues)


def test_dirty_amount_negative():
    result = validate_ohlcv_bar(_normal_bar(amount=-1.0))
    assert any(i.code == CODE_AMOUNT_NEGATIVE for i in result.issues)


def test_dirty_volume_unit_suspect_lots_vs_shares():
    # amount/volume ≈ 100 * close when volume is in 手 and amount in 元
    close = 10.0
    volume_lots = 10_000  # 手
    amount = close * volume_lots * 100  # 元, as if volume were shares*100
    result = validate_ohlcv_bar(
        _normal_bar(close=close, high=10.5, low=9.5, volume=volume_lots, amount=amount, pct_chg=0.0, pre_close=10.0)
    )
    assert any(i.code == CODE_VOLUME_UNIT_SUSPECT for i in result.issues)
    assert not any(
        i.code == CODE_VOLUME_UNIT_SUSPECT and i.severity == ValidationSeverity.REJECT
        for i in result.issues
    )


def test_dirty_date_duplicate_and_out_of_order():
    frame = _normal_frame(
        [
            _normal_bar(date="2024-01-03", close=10.0, high=10.2, low=9.8, pct_chg=0.0, pre_close=10.0),
            _normal_bar(date="2024-01-02", close=10.1, high=10.3, low=9.9, pct_chg=1.0, pre_close=10.0),
            _normal_bar(date="2024-01-02", close=10.2, high=10.4, low=10.0, pct_chg=1.0, pre_close=10.1),
        ]
    )
    result = validate_daily_frame(frame)
    codes = {i.code for i in result.issues}
    assert CODE_DATE_OUT_OF_ORDER in codes
    assert CODE_DATE_DUPLICATE in codes


def test_dirty_fundamental_pe_extreme_and_non_finite():
    extreme = validate_fundamental_metrics({"pe_ratio": 100_000.0})
    assert any(i.code == CODE_FUND_PE_EXTREME for i in extreme.issues)
    non_finite = validate_fundamental_metrics({"pe_ratio": float("nan")})
    assert any(i.code == CODE_FUND_PE_NON_FINITE for i in non_finite.issues)
    pb = validate_fundamental_metrics({"pb_ratio": 20_000.0})
    assert any(i.code == CODE_FUND_PB_EXTREME for i in pb.issues)


def test_dirty_fundamental_pe_negative_is_warn_only():
    result = validate_fundamental_metrics({"pe_ratio": -12.5, "pb_ratio": 1.2})
    assert any(i.code == CODE_FUND_PE_NEGATIVE for i in result.issues)
    assert result.status == ValidationSeverity.WARN
    assert not result.has_reject


def test_dirty_fundamental_earnings_period_order():
    ctx = {
        "market": "cn",
        "valuation": {"data": {"pe_ratio": 15.0, "pb_ratio": 2.0}},
        "earnings": {"data": {"periods": ["2024-06-30", "2023-12-31", "2023-12-31"]}},
    }
    result = validate_fundamental_context(ctx)
    codes = {i.code for i in result.issues}
    assert CODE_DATE_OUT_OF_ORDER in codes
    assert CODE_DATE_DUPLICATE in codes


# ---------------------------------------------------------------------------
# Zero false-positive: normal fixtures must pass cleanly
# ---------------------------------------------------------------------------


def test_zero_false_positive_normal_daily_frame():
    frame = _normal_frame()
    result = validate_daily_frame(frame, market="cn", stock_code="600519")
    assert result.ok, result.to_dict()
    assert result.issues == []


def test_zero_false_positive_normal_quote():
    quote = SimpleNamespace(
        price=10.2,
        open_price=10.0,
        high=10.5,
        low=9.8,
        pre_close=10.0,
        volume=1_000_000,
        amount=10_200_000.0,
        change_pct=2.0,
        pe_ratio=18.5,
        pb_ratio=3.2,
        to_dict=lambda: {
            "price": 10.2,
            "open_price": 10.0,
            "high": 10.5,
            "low": 9.8,
            "pre_close": 10.0,
            "volume": 1_000_000,
            "amount": 10_200_000.0,
            "change_pct": 2.0,
            "pe_ratio": 18.5,
            "pb_ratio": 3.2,
        },
    )
    result = validate_realtime_quote(quote, market="cn")
    assert result.ok, result.to_dict()


def test_zero_false_positive_etf_missing_valuation():
    """ETFs often lack PE/PB — missing metrics must not flag."""
    result = validate_fundamental_metrics({"pe_ratio": None, "pb_ratio": None})
    assert result.ok
    assert result.issues == []


def test_zero_false_positive_mild_pct_rounding():
    # expected 2.0%; provider reports 2.01% within tolerance
    result = validate_ohlcv_bar(_normal_bar(close=10.2, pre_close=10.0, pct_chg=2.01))
    assert result.ok, result.to_dict()


def test_zero_false_positive_fundamental_context_partial():
    ctx = {
        "market": "us",
        "valuation": {"status": "partial", "data": {}},
        "growth": {},
        "earnings": {},
        "coverage": {},
        "errors": [],
    }
    result = validate_fundamental_context(ctx, stock_code="AAPL")
    assert result.ok, result.to_dict()


# ---------------------------------------------------------------------------
# Default mode: annotate + pass-through; strict rejects
# ---------------------------------------------------------------------------


def test_default_mode_does_not_raise_on_reject(monkeypatch):
    monkeypatch.delenv("DATA_VALIDATION_STRICT", raising=False)
    monkeypatch.setenv("DATA_VALIDATION_ENABLED", "true")
    assert is_validation_enabled()
    assert not is_strict_mode()
    frame = _normal_frame([_normal_bar(close=-1.0, high=1.0, low=0.5)])
    result = validate_and_annotate(
        frame,
        data_type="daily_data",
        stock_code="600519",
        strict=False,
    )
    assert result.has_reject
    # Data still present and annotated
    assert frame.attrs.get(ATTR_KEY) is not None
    assert frame.attrs[ATTR_KEY]["status"] == "reject"


def test_strict_mode_raises_on_reject(monkeypatch):
    monkeypatch.setenv("DATA_VALIDATION_STRICT", "true")
    frame = _normal_frame([_normal_bar(close=0.0)])
    with pytest.raises(DataValidationRejected) as exc_info:
        validate_and_annotate(
            frame,
            data_type="daily_data",
            stock_code="600519",
            strict=True,
        )
    assert exc_info.value.data_type == "daily_data"
    assert exc_info.value.validation_payload.get("status") == "reject"


def test_disabled_validation_is_noop(monkeypatch):
    monkeypatch.setenv("DATA_VALIDATION_ENABLED", "false")
    frame = _normal_frame([_normal_bar(close=-5.0)])
    result = validate_and_annotate(frame, data_type="daily_data", stock_code="x")
    assert result.ok
    assert result.context.get("enabled") is False


def test_never_silently_drops_rows_on_warn():
    frame = _normal_frame()
    # Inject inconsistent pct on second row only
    frame.loc[1, "pct_chg"] = 50.0
    before = len(frame)
    result = validate_and_annotate(frame, data_type="daily_data", strict=False)
    assert len(frame) == before
    assert any(i.code == CODE_PCT_CHG_INCONSISTENT for i in result.issues)


# ---------------------------------------------------------------------------
# Manager wiring: default path passes normal data unchanged
# ---------------------------------------------------------------------------


def test_manager_wrapper_default_mode_preserves_daily_result(monkeypatch):
    monkeypatch.delenv("DATA_VALIDATION_STRICT", raising=False)
    monkeypatch.setenv("DATA_VALIDATION_ENABLED", "true")

    from data_provider.manager_parts.data_validation_wiring import (
        ensure_validation_wrappers,
        reset_validation_wrappers_state_for_tests,
    )

    frame = _normal_frame()

    class FakeManager:
        def get_daily_data(self, stock_code, start_date=None, end_date=None, days=30):
            return frame, "FakeFetcher"

        def get_realtime_quote(self, stock_code, *, log_final_failure=True):
            return None

        def get_fundamental_context(self, stock_code, budget_seconds=None):
            return {"market": "cn", "valuation": {"data": {"pe_ratio": 12.0}}}

    reset_validation_wrappers_state_for_tests()
    # Clear flag if re-used in process
    if hasattr(FakeManager, "_stockpulse_data_validation_wrapped"):
        delattr(FakeManager, "_stockpulse_data_validation_wrapped")

    ensure_validation_wrappers(FakeManager)
    mgr = FakeManager()
    out_frame, source = mgr.get_daily_data("600519")
    assert source == "FakeFetcher"
    assert out_frame is frame
    assert len(out_frame) == 2
    assert out_frame.attrs.get(ATTR_KEY, {}).get("status") == "pass"


def test_manager_wrapper_strict_quote_returns_none(monkeypatch):
    monkeypatch.setenv("DATA_VALIDATION_STRICT", "true")
    monkeypatch.setenv("DATA_VALIDATION_ENABLED", "true")

    from data_provider.manager_parts.data_validation_wiring import (
        ensure_validation_wrappers,
        reset_validation_wrappers_state_for_tests,
    )

    bad_quote = SimpleNamespace(
        price=-1.0,
        open_price=1.0,
        high=1.0,
        low=1.0,
        pre_close=1.0,
        volume=10,
        amount=10.0,
        change_pct=0.0,
        pe_ratio=None,
        pb_ratio=None,
        to_dict=lambda: {
            "price": -1.0,
            "open_price": 1.0,
            "high": 1.0,
            "low": 1.0,
            "pre_close": 1.0,
            "volume": 10,
            "amount": 10.0,
            "change_pct": 0.0,
        },
    )

    class FakeManager:
        def get_daily_data(self, stock_code, start_date=None, end_date=None, days=30):
            return _normal_frame(), "FakeFetcher"

        def get_realtime_quote(self, stock_code, *, log_final_failure=True):
            return bad_quote

        def get_fundamental_context(self, stock_code, budget_seconds=None):
            return {}

    reset_validation_wrappers_state_for_tests()
    if hasattr(FakeManager, "_stockpulse_data_validation_wrapped"):
        delattr(FakeManager, "_stockpulse_data_validation_wrapped")

    ensure_validation_wrappers(FakeManager)
    assert FakeManager().get_realtime_quote("600519") is None


def test_data_fetcher_manager_has_validation_wrappers_installed():
    """Facade bind path must install wrappers without touching base.py source."""
    from data_provider.base import DataFetcherManager

    assert getattr(DataFetcherManager, "_stockpulse_data_validation_wrapped", False)


def test_empty_frame_is_reject():
    result = validate_daily_frame(pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"]))
    assert result.has_reject
    assert any(i.code == CODE_EMPTY_PAYLOAD for i in result.issues)
