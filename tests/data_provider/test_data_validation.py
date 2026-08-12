# -*- coding: utf-8 -*-
"""Offline tests for the financial data validation layer (Issue #185 / T11)."""

from __future__ import annotations

import importlib
import json
import math
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import numpy as np
import pytest

from data_provider.data_validation import (
    ATTR_KEY,
    CODE_CROSS_SOURCE_DIVERGENCE,
    CODE_DATE_DUPLICATE,
    CODE_DATE_OUT_OF_ORDER,
    CODE_EMPTY_PAYLOAD,
    CODE_FUND_PB_EXTREME,
    CODE_FUND_PB_INVALID_TYPE,
    CODE_FUND_PB_SUSPECT,
    CODE_FUND_PE_EXTREME,
    CODE_FUND_PE_INVALID_TYPE,
    CODE_FUND_PE_NEGATIVE,
    CODE_FUND_PE_NON_FINITE,
    CODE_FUND_PE_SUSPECT,
    CODE_INDICATOR_INPUT_INSUFFICIENT,
    DataValidationRejected,
    ValidationSeverity,
    compare_cross_source_fields,
    compare_cross_source_quotes,
    infer_instrument_type,
    is_strict_mode,
    is_validation_enabled,
    prepare_indicator_inputs,
    project_technical_indicators,
    validate_and_annotate,
    validate_daily_frame,
    validate_fundamental_context,
    validate_fundamental_metrics,
    validate_indicator_inputs,
    validate_ohlcv_bar,
    validate_realtime_quote,
    validate_technical_indicators,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "data_validation"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _reset_config_singleton():
    from src.application_services import reset_application_services
    from src.config import Config

    reset_application_services()
    Config.reset_instance()
    yield
    reset_application_services()
    Config.reset_instance()


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
    assert any(i.code == "dv_ohlcv_close_missing" for i in result.issues)


def test_dirty_price_zero_and_negative():
    zero = validate_ohlcv_bar(_normal_bar(close=0.0))
    assert any(i.code == "dv_ohlcv_close_out_of_range" for i in zero.issues)
    neg = validate_ohlcv_bar(_normal_bar(close=-3.5))
    assert any(i.code == "dv_ohlcv_close_out_of_range" for i in neg.issues)


def test_dirty_price_nan_and_infinity():
    nan = validate_ohlcv_bar(_normal_bar(close=float("nan")))
    assert any(i.code == "dv_ohlcv_close_non_finite" for i in nan.issues)
    inf = validate_ohlcv_bar(_normal_bar(high=float("inf")))
    assert any(i.code == "dv_ohlcv_high_non_finite" for i in inf.issues)
    ninf = validate_ohlcv_bar(_normal_bar(low=float("-inf")))
    assert any(i.code == "dv_ohlcv_low_non_finite" for i in ninf.issues)


def test_nonnumeric_and_bool_numeric_inputs_are_rejected_with_field_codes():
    close = validate_ohlcv_bar(_normal_bar(close="not-a-number"))
    assert any(i.code == "dv_ohlcv_close_invalid_type" for i in close.issues)
    bool_volume = validate_ohlcv_bar(_normal_bar(volume=True))
    assert any(i.code == "dv_ohlcv_volume_invalid_type" for i in bool_volume.issues)
    numpy_bool_volume = validate_ohlcv_bar(_normal_bar(volume=np.bool_(True)))
    assert any(
        i.code == "dv_ohlcv_volume_invalid_type"
        for i in numpy_bool_volume.issues
    )


def test_dirty_pct_chg_inconsistent():
    # close 10.2 vs pre_close 10.0 => expected +2%; claim +9%
    result = validate_ohlcv_bar(_normal_bar(close=10.2, pre_close=10.0, pct_chg=9.0))
    assert result.status in {ValidationSeverity.WARN, ValidationSeverity.REJECT}
    assert any(i.code == "dv_ohlcv_pct_chg_inconsistent" for i in result.issues)


def test_dirty_high_below_low():
    result = validate_ohlcv_bar(_normal_bar(high=9.0, low=10.0, close=9.5))
    assert any(i.code == "dv_ohlcv_high_below_low" for i in result.issues)
    assert result.has_reject


def test_dirty_close_out_of_range():
    result = validate_ohlcv_bar(_normal_bar(high=10.5, low=9.8, close=11.0))
    assert any(i.code == "dv_ohlcv_close_out_of_range" for i in result.issues)


def test_dirty_volume_negative():
    result = validate_ohlcv_bar(_normal_bar(volume=-100))
    assert any(i.code == "dv_ohlcv_volume_out_of_range" for i in result.issues)


def test_dirty_amount_negative():
    result = validate_ohlcv_bar(_normal_bar(amount=-1.0))
    assert any(i.code == "dv_ohlcv_amount_out_of_range" for i in result.issues)


def test_dirty_volume_unit_suspect_lots_vs_shares():
    # amount/volume ≈ 100 * close when volume is in 手 and amount in 元
    close = 10.0
    volume_lots = 10_000  # 手
    amount = close * volume_lots * 100  # 元, as if volume were shares*100
    result = validate_ohlcv_bar(
        _normal_bar(close=close, high=10.5, low=9.5, volume=volume_lots, amount=amount, pct_chg=0.0, pre_close=10.0)
    )
    assert any(i.code == "dv_ohlcv_volume_unit_suspect" for i in result.issues)
    assert not any(
        i.code == "dv_ohlcv_volume_unit_suspect"
        and i.severity == ValidationSeverity.REJECT
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


def test_invalid_fundamental_strings_use_pe_pb_specific_codes():
    result = validate_fundamental_metrics(
        {"pe_ratio": "not-a-number", "pb_ratio": "unknown"}
    )
    assert {issue.code for issue in result.issues} == {
        CODE_FUND_PE_INVALID_TYPE,
        CODE_FUND_PB_INVALID_TYPE,
    }
    assert result.has_reject


def test_non_finite_selected_technical_outputs_are_rejected_and_json_safe():
    result = validate_technical_indicators(
        {
            "ma5": float("nan"),
            "ma10": float("inf"),
            "ma20": 10.0,
            "trend_strength": 101,
            "signal_score": "not-a-number",
        },
        market="cn",
        stock_code="600519",
    )
    codes = {issue.code for issue in result.issues}
    assert "dv_technical_ma5_non_finite" in codes
    assert "dv_technical_ma10_non_finite" in codes
    assert "dv_technical_trend_strength_out_of_range" in codes
    assert "dv_technical_signal_score_invalid_type" in codes
    json.dumps(result.to_dict(), allow_nan=False)


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


@pytest.mark.parametrize(
    ("asset_type", "market", "overrides"),
    [
        (
            "etf",
            "cn",
            {
                "open": 10.0,
                "high": 10.0,
                "low": 10.0,
                "close": 10.0,
                "volume": 0,
                "amount": 0,
                "pct_chg": 0.0,
            },
        ),
        ("index", "us", {"volume": 0, "amount": None, "pct_chg": 2.01}),
        ("equity", "hk", {"amount": None, "pct_chg": 2.01}),
    ],
    ids=["suspended-etf", "index-no-turnover", "offshore-partial-rounding"],
)
def test_representative_instrument_fixtures_bound_false_positives(
    asset_type,
    market,
    overrides,
):
    result = validate_ohlcv_bar(
        _normal_bar(**overrides),
        asset_type=asset_type,
        market=market,
    )
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
    assert any(i.code == "dv_ohlcv_pct_chg_inconsistent" for i in result.issues)


# ---------------------------------------------------------------------------
# Manager wiring: default path passes normal data unchanged
# ---------------------------------------------------------------------------


def test_manager_wrapper_default_mode_preserves_daily_result(monkeypatch):
    monkeypatch.delenv("DATA_VALIDATION_STRICT", raising=False)
    monkeypatch.setenv("DATA_VALIDATION_ENABLED", "true")

    from data_provider.manager_parts.data_validation_wiring import (
        ensure_validation_wrappers,
    )

    frame = _normal_frame()

    class FakeManager:
        def get_daily_data(self, stock_code, start_date=None, end_date=None, days=30):
            return frame, "FakeFetcher"

        def get_realtime_quote(self, stock_code, *, log_final_failure=True):
            return None

        def get_fundamental_context(self, stock_code, budget_seconds=None):
            return {"market": "cn", "valuation": {"data": {"pe_ratio": 12.0}}}

    ensure_validation_wrappers(FakeManager)
    mgr = FakeManager()
    out_frame, source = mgr.get_daily_data("600519")
    assert source == "FakeFetcher"
    assert out_frame is frame
    assert len(out_frame) == 2
    assert out_frame.attrs.get(ATTR_KEY, {}).get("status") == "pass"


def test_outer_manager_wrapper_does_not_mislabel_quote_rejection_as_failover(monkeypatch):
    monkeypatch.setenv("DATA_VALIDATION_STRICT", "true")
    monkeypatch.setenv("DATA_VALIDATION_ENABLED", "true")

    from data_provider.manager_parts.data_validation_wiring import (
        ensure_validation_wrappers,
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

    ensure_validation_wrappers(FakeManager)
    quote = FakeManager().get_realtime_quote("600519")
    assert quote is bad_quote
    assert quote.data_quality_evidence["severity"] == "reject"
    assert quote.data_quality_evidence["rejected"] is False


def test_data_fetcher_manager_has_validation_wrappers_installed():
    """Facade bind path must install wrappers without touching base.py source."""
    from data_provider.base import DataFetcherManager

    for method_name in (
        "get_daily_data",
        "get_realtime_quote",
        "get_fundamental_context",
    ):
        method = DataFetcherManager.__dict__[method_name]
        assert getattr(
            method,
            "_stockpulse_data_validation_wrapper_token",
            None,
        ) is not None


def test_empty_frame_is_reject():
    result = validate_daily_frame(pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"]))
    assert result.has_reject
    assert any(i.code == CODE_EMPTY_PAYLOAD for i in result.issues)


def test_strict_daily_rejection_reaches_next_provider_candidate(monkeypatch):
    from unittest.mock import patch

    from data_provider.base import DataFetcherManager
    from data_provider.realtime_types import CircuitBreaker
    from src.services.run_diagnostics import (
        activate_run_diagnostic_context,
        current_diagnostic_snapshot,
        reset_run_diagnostic_context,
    )
    class Provider:
        def __init__(self, name, priority, frame):
            self.name = name
            self.priority = priority
            self.frame = frame
            self.calls = 0

        def get_daily_data(self, **_kwargs):
            self.calls += 1
            return self.frame.copy(deep=True)

    rejected = Provider(
        "EfinanceFetcher",
        0,
        _normal_frame([_normal_bar(close="not-a-number")]),
    )
    accepted = Provider("TencentFetcher", 1, _normal_frame())
    monkeypatch.setenv("DATA_VALIDATION_ENABLED", "true")
    monkeypatch.setenv("DATA_VALIDATION_STRICT", "true")
    monkeypatch.setenv("DATA_VALIDATION_STRICT_SCOPES", "cn/equity")
    monkeypatch.setenv("PROVIDER_DAILY_CACHE_ENABLED", "false")
    manager = DataFetcherManager(fetchers=[rejected, accepted])
    breaker = CircuitBreaker(
        failure_threshold=99,
        cooldown_seconds=60.0,
        health_window_size=20,
    )
    token = activate_run_diagnostic_context(
        trace_id="trace-data-validation-fallback",
        stock_code="600519",
    )
    try:
        with patch.object(DataFetcherManager, "_daily_source_health", breaker):
            frame, source = manager.get_daily_data("600519")
        diagnostics = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    assert source == "TencentFetcher"
    assert not frame.empty
    assert rejected.calls == 1
    assert accepted.calls == 1
    rejected_evidence = [
        item
        for item in diagnostics["data_quality_evidence"]
        if item["provider"] == "EfinanceFetcher"
    ]
    assert rejected_evidence
    assert rejected_evidence[0]["rejected"] is True
    assert rejected_evidence[0]["issues"][0]["code"] == "dv_ohlcv_close_invalid_type"
    failed_runs = [run for run in diagnostics["provider_runs"] if not run["success"]]
    assert failed_runs[0]["provider"] == "EfinanceFetcher"
    assert failed_runs[0]["fallback_to"] == "TencentFetcher"
    assert failed_runs[0]["error_type"] == "DataValidationRejected"


def test_daily_evidence_survives_dataframe_to_rows_and_strict_json(caplog):
    from src.core.stages.persistence import _PersistenceStageMixin
    from src.services.run_diagnostics import (
        activate_run_diagnostic_context,
        current_diagnostic_snapshot,
        reset_run_diagnostic_context,
    )

    frame = _normal_frame([_normal_bar(close=float("nan"))])
    caplog.set_level(logging.INFO, logger="src.services.run_diagnostics")
    token = activate_run_diagnostic_context(
        trace_id="trace-data-validation-persistence",
        stock_code="600519",
    )
    try:
        validate_and_annotate(
            frame,
            data_type="daily_data",
            stock_code="600519",
            provider="fixture_provider",
            strict=False,
        )
        rows = frame.to_dict(orient="records")
        assert rows and "data_validation" not in rows[0]
        snapshot = current_diagnostic_snapshot()
        persistence = SimpleNamespace(
            analysis_skills=None,
            _without_runtime_prompt_context=lambda value: value,
            _safe_to_dict=lambda value: value,
        )
        database_snapshot = _PersistenceStageMixin._build_context_snapshot(
            persistence,
            {},
            None,
            None,
            None,
        )
    finally:
        reset_run_diagnostic_context(token)

    assert snapshot["data_quality_evidence"][0]["schema_version"] == (
        "data_quality_evidence.v1"
    )
    assert snapshot["data_quality_evidence"][0]["provider"] == "fixture_provider"
    assert database_snapshot["diagnostics"]["data_quality_evidence"] == (
        snapshot["data_quality_evidence"]
    )
    assert "severity=reject symbol=600519 provider=fixture_provider" in caplog.text
    assert "codes=dv_ohlcv_close_non_finite" in caplog.text
    json.dumps(snapshot, allow_nan=False)


def test_realtime_evidence_is_readable_without_mutating_public_dict():
    from data_provider.realtime_types import UnifiedRealtimeQuote

    quote = UnifiedRealtimeQuote(code="600519", price=10.0, pe_ratio="bad")
    result = validate_and_annotate(
        quote,
        data_type="realtime_quote",
        stock_code="600519",
        provider="fixture_provider",
        strict=False,
    )
    assert result.has_reject
    assert quote.data_quality_evidence["schema_version"] == "data_quality_evidence.v1"
    assert "data_quality_evidence" in quote.to_dict()
    json.dumps(quote.data_quality_evidence, allow_nan=False)


def test_wrappers_cover_subclass_partial_reload_and_concurrent_install(monkeypatch):
    monkeypatch.setenv("DATA_VALIDATION_ENABLED", "true")
    import data_provider.manager_parts.data_validation_wiring as wiring

    class BaseManager:
        def get_daily_data(self, _stock_code):
            return _normal_frame(), "base"

        def get_realtime_quote(self, _stock_code):
            return None

        def get_fundamental_context(self, _stock_code):
            return {}

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert all(executor.map(wiring.ensure_validation_wrappers, [BaseManager] * 32))

    class OverrideManager(BaseManager):
        def get_daily_data(self, _stock_code):
            return _normal_frame(), "override"

    assert "get_daily_data" in OverrideManager.__dict__
    assert getattr(
        OverrideManager.__dict__["get_daily_data"],
        "_stockpulse_data_validation_wrapper_token",
        None,
    ) is not None
    assert OverrideManager().get_daily_data("600519")[1] == "override"

    class PartialManager:
        def get_daily_data(self, _stock_code):
            return _normal_frame(), "partial"

    wiring.ensure_validation_wrappers(PartialManager)

    def quote_method(self, _stock_code):
        return None

    PartialManager.get_realtime_quote = quote_method
    wiring.ensure_validation_wrappers(PartialManager)
    assert getattr(
        PartialManager.__dict__["get_realtime_quote"],
        "_stockpulse_data_validation_wrapper_token",
        None,
    ) is not None

    old_wrapper = BaseManager.__dict__["get_daily_data"]
    reloaded = importlib.reload(wiring)
    reloaded.ensure_validation_wrappers(BaseManager)
    new_wrapper = BaseManager.__dict__["get_daily_data"]
    assert new_wrapper is not old_wrapper
    assert getattr(
        new_wrapper,
        "_stockpulse_data_validation_wrapper_token",
        None,
    ) is not None
    assert getattr(new_wrapper, "_stockpulse_data_validation_original") is getattr(
        old_wrapper,
        "_stockpulse_data_validation_original",
    )


def test_validation_configuration_is_owned_by_typed_config(monkeypatch):
    from src.config import Config

    monkeypatch.setenv("DATA_VALIDATION_ENABLED", "false")
    monkeypatch.setenv("DATA_VALIDATION_STRICT", "true")
    monkeypatch.setenv("DATA_VALIDATION_STRICT_SCOPES", "hk/etf")
    monkeypatch.setenv("DATA_VALIDATION_UPPER_LAYER_MODE", "reject")
    Config.reset_instance()

    config = Config.get_instance()
    assert infer_instrument_type("510300") == "etf"
    assert infer_instrument_type("SPX") == "index"
    assert config.data_validation_enabled is False
    assert config.data_validation_strict is True
    assert config.data_validation_strict_scopes == "hk/etf"
    assert config.data_validation_upper_layer_mode == "reject"
    assert is_strict_mode(market="hk", instrument_type="etf")
    assert not is_strict_mode(market="cn", instrument_type="equity")

    monkeypatch.setenv("DATA_VALIDATION_STRICT_SCOPES", "invalid-scope")
    Config.reset_instance()
    assert is_strict_mode(market="cn", instrument_type="equity")


@pytest.mark.parametrize(
    ("symbol", "market"),
    [
        ("SPY", "us"),
        ("HK02800", "hk"),
        ("1306.T", "jp"),
        ("069500.KS", "kr"),
        ("0050.TW", "tw"),
    ],
)
def test_offshore_etf_override_reaches_real_manager_strict_policy(
    monkeypatch,
    symbol,
    market,
):
    from data_provider.base import DataFetchError, DataFetcherManager
    from src.application_services import reset_application_services
    from src.config import Config
    from src.services.run_diagnostics import (
        activate_run_diagnostic_context,
        current_diagnostic_snapshot,
        reset_run_diagnostic_context,
    )

    class Provider:
        name = "YfinanceFetcher"
        priority = 0

        def get_daily_data(self, **_kwargs):
            return _normal_frame([_normal_bar(close="not-a-number")])

    monkeypatch.setenv("DATA_VALIDATION_ENABLED", "true")
    monkeypatch.setenv("DATA_VALIDATION_STRICT", "true")
    monkeypatch.setenv("DATA_VALIDATION_STRICT_SCOPES", f"{market}/etf")
    monkeypatch.setenv(
        "DATA_VALIDATION_INSTRUMENT_OVERRIDES",
        "SPY=etf,HK02800=etf,1306.T=etf,069500.KS=etf,0050.TW=etf",
    )
    monkeypatch.setenv("PROVIDER_DAILY_CACHE_ENABLED", "false")
    reset_application_services()
    Config.reset_instance()
    manager = DataFetcherManager(fetchers=[Provider()])
    token = activate_run_diagnostic_context(
        trace_id=f"trace-offshore-etf-{market}",
        stock_code=symbol,
    )
    try:
        with pytest.raises(DataFetchError):
            manager.get_daily_data(symbol)
        evidence = current_diagnostic_snapshot()["data_quality_evidence"]
    finally:
        reset_run_diagnostic_context(token)

    assert evidence
    assert evidence[0]["market"] == market
    assert evidence[0]["instrument_type"] == "etf"
    assert evidence[0]["rejected"] is True


def test_validation_rejected_fundamental_context_is_typed_not_pipeline_failure():
    from data_provider.base import DataFetcherManager

    result = validate_fundamental_context(
        {"valuation": {"data": {"pe_ratio": "bad"}}},
        market="cn",
        stock_code="600519",
    )
    evidence = result.to_evidence(
        data_type="fundamental_context",
        stock_code="600519",
        provider="fundamental_pipeline",
        market="cn",
        instrument_type="equity",
        rejected=True,
    )
    rejection = DataValidationRejected(
        result,
        data_type="fundamental_context",
        evidence=evidence,
    )
    context = DataFetcherManager(fetchers=[]).build_validation_rejected_fundamental_context(
        "600519",
        rejection,
    )

    assert context["status"] == "validation_rejected"
    assert context["data_quality"] == "rejected"
    assert context["source_chain"] == [
        {"provider": "data_validation", "result": "rejected", "duration_ms": 0}
    ]
    assert context["validation_rejection"]["reason_codes"] == [
        "dv_fund_pe_invalid_type"
    ]
    assert context["data_quality_evidence"] == [evidence]


# ---------------------------------------------------------------------------
# Issue #185 remaining scope: indicator I/O, fund suspect, cross-source, fixtures
# ---------------------------------------------------------------------------


def test_indicator_inputs_reject_non_finite_rows_and_drop_them():
    frame = _normal_frame(
        [
            _normal_bar(date="2024-01-02", close=10.2, pre_close=10.0, pct_chg=2.0),
            _normal_bar(
                date="2024-01-03",
                close=float("nan"),
                high=10.8,
                low=10.0,
                open=10.2,
                volume=1_100_000,
                amount=11_550_000.0,
                pct_chg=2.9,
                pre_close=10.2,
            ),
            _normal_bar(
                date="2024-01-04",
                close=10.7,
                high=10.9,
                low=10.5,
                open=10.5,
                volume=1_200_000,
                amount=12_840_000.0,
                pct_chg=1.9,
                pre_close=10.5,
            ),
        ]
    )
    cleaned, result = prepare_indicator_inputs(
        frame, market="cn", stock_code="600519", provider="unit_test"
    )
    assert result.has_reject
    assert any("non_finite" in issue.code for issue in result.issues)
    assert len(cleaned) == 2
    assert float(cleaned.iloc[0]["close"]) == 10.2
    assert float(cleaned.iloc[1]["close"]) == 10.7
    assert all(math.isfinite(float(v)) for v in cleaned["close"].tolist())


def test_indicator_inputs_all_dirty_degrades_without_clean_rows():
    frame = _normal_frame(
        [
            _normal_bar(close=float("inf")),
            _normal_bar(date="2024-01-03", close=float("nan"), volume=float("nan")),
        ]
    )
    cleaned, result = prepare_indicator_inputs(frame, stock_code="600519")
    assert result.has_reject
    assert any(i.code == CODE_INDICATOR_INPUT_INSUFFICIENT for i in result.issues)
    assert cleaned is not None
    assert len(cleaned) == 0


def test_project_technical_indicators_never_returns_non_finite():
    projected = project_technical_indicators(
        {
            "ma5": float("nan"),
            "ma10": 10.5,
            "ma20": float("inf"),
            "bias_ma5": 1.2,
            "trend_strength": 55,
            "signal_score": 70,
            "macd_dif": float("nan"),
            "rsi_by_period": {"6": float("inf"), "12": 45.0},
        },
        market="cn",
        stock_code="600519",
    )
    assert "ma5" not in projected or projected.get("ma5") is None
    assert projected.get("ma10") == 10.5
    assert "ma20" not in projected or projected.get("ma20") is None
    assert projected.get("rsi_by_period", {}).get("12") == 45.0
    assert projected.get("rsi_by_period", {}).get("6") is None
    json.dumps(projected, allow_nan=False)


def test_fundamental_suspect_pe_pb_are_warn_and_kept():
    result = validate_fundamental_metrics({"pe_ratio": 250.0, "pb_ratio": 60.0})
    codes = {issue.code for issue in result.issues}
    assert CODE_FUND_PE_SUSPECT in codes
    assert CODE_FUND_PB_SUSPECT in codes
    assert result.status == ValidationSeverity.WARN
    assert not result.has_reject
    for issue in result.issues:
        if issue.code in {CODE_FUND_PE_SUSPECT, CODE_FUND_PB_SUSPECT}:
            assert issue.detail and issue.detail.get("kept") is True


def test_fundamental_normal_pe_pb_not_suspect():
    result = validate_fundamental_metrics({"pe_ratio": 18.5, "pb_ratio": 3.2})
    assert result.ok
    assert result.issues == []


def test_fundamental_extreme_still_rejects_above_suspect():
    result = validate_fundamental_metrics({"pe_ratio": 100_000.0, "pb_ratio": 20_000.0})
    codes = {issue.code for issue in result.issues}
    assert CODE_FUND_PE_EXTREME in codes
    assert CODE_FUND_PB_EXTREME in codes
    assert CODE_FUND_PE_SUSPECT not in codes
    assert result.has_reject


def test_cross_source_divergence_warns_with_attribution_and_keeps_values():
    result = compare_cross_source_fields(
        {
            "efinance": {"price": 10.0, "pe_ratio": 15.0},
            "akshare_em": {"price": 11.0, "pe_ratio": 15.1},
        },
        relative_threshold=0.05,
        stock_code="600519",
        market="cn",
    )
    assert result.status == ValidationSeverity.WARN
    assert any(i.code == CODE_CROSS_SOURCE_DIVERGENCE for i in result.issues)
    price_issue = next(i for i in result.issues if i.field == "price")
    assert price_issue.detail["kept"] is True
    providers = {item["provider"] for item in price_issue.detail["values"]}
    assert providers == {"efinance", "akshare_em"}
    assert not any(i.field == "pe_ratio" for i in result.issues)


def test_cross_source_single_provider_is_noop():
    result = compare_cross_source_fields(
        {"efinance": {"price": 10.0}},
        stock_code="600519",
    )
    assert result.ok
    assert result.context.get("compared") is False


def test_cross_source_quotes_compare_attributes():
    primary = SimpleNamespace(
        price=100.0,
        pe_ratio=20.0,
        volume=1_000_000,
        to_dict=lambda: {"price": 100.0, "pe_ratio": 20.0, "volume": 1_000_000},
    )
    secondary = SimpleNamespace(
        price=112.0,
        pe_ratio=20.2,
        volume=1_050_000,
        to_dict=lambda: {"price": 112.0, "pe_ratio": 20.2, "volume": 1_050_000},
    )
    result = compare_cross_source_quotes(
        primary,
        secondary,
        primary_provider="primary",
        secondary_provider="secondary",
        stock_code="AAPL",
        market="us",
        log=False,
    )
    assert any(
        i.code == CODE_CROSS_SOURCE_DIVERGENCE and i.field == "price"
        for i in result.issues
    )


def test_config_suspect_and_cross_source_thresholds(monkeypatch):
    from src.config import Config

    monkeypatch.setenv("DATA_VALIDATION_FUND_PE_SUSPECT_ABS", "150")
    monkeypatch.setenv("DATA_VALIDATION_FUND_PB_SUSPECT_ABS", "40")
    monkeypatch.setenv("DATA_VALIDATION_CROSS_SOURCE_REL_THRESHOLD", "0.1")
    Config.reset_instance()
    config = Config.get_instance()
    assert config.data_validation_fund_pe_suspect_abs == 150.0
    assert config.data_validation_fund_pb_suspect_abs == 40.0
    assert config.data_validation_cross_source_rel_threshold == 0.1
    result = validate_fundamental_metrics({"pe_ratio": 160.0, "pb_ratio": 45.0})
    codes = {issue.code for issue in result.issues}
    assert CODE_FUND_PE_SUSPECT in codes
    assert CODE_FUND_PB_SUSPECT in codes


@pytest.mark.parametrize(
    "fixture_name",
    [
        "cn_etf_510300_daily.json",
        "us_etf_spy_daily.json",
        "suspended_etf_zero_turnover.json",
    ],
)
def test_etf_daily_fixtures_have_zero_false_positives(fixture_name):
    payload = _load_fixture(fixture_name)
    meta = payload["meta"]
    rows = payload.get("rows")
    if rows is None:
        rows = [payload["bar"]]
    frame = pd.DataFrame(rows)
    daily = validate_daily_frame(
        frame,
        market=meta["market"],
        asset_type=meta["instrument_type"],
        stock_code=meta["symbol"],
    )
    assert daily.ok, daily.to_dict()
    fund = validate_fundamental_metrics(
        payload.get("valuation") or {},
        market=meta["market"],
        asset_type=meta["instrument_type"],
    )
    assert fund.ok, fund.to_dict()
    cleaned, inputs = prepare_indicator_inputs(
        frame,
        market=meta["market"],
        asset_type=meta["instrument_type"],
        stock_code=meta["symbol"],
    )
    assert len(cleaned) == len(frame)
    assert all(math.isfinite(float(v)) for v in cleaned["close"].tolist())


def test_hk_etf_quote_fixture_zero_false_positive():
    payload = _load_fixture("hk_etf_02800_quote.json")
    meta = payload["meta"]
    quote = payload["quote"]
    result = validate_realtime_quote(
        quote,
        market=meta["market"],
        asset_type=meta["instrument_type"],
        stock_code=meta["symbol"],
    )
    assert result.ok, result.to_dict()


def test_index_fixture_zero_false_positive():
    payload = _load_fixture("cn_index_000300_bar.json")
    meta = payload["meta"]
    result = validate_ohlcv_bar(
        payload["bar"],
        market=meta["market"],
        asset_type=meta["instrument_type"],
    )
    assert result.ok, result.to_dict()
    fund = validate_fundamental_metrics(
        payload["valuation"],
        market=meta["market"],
        asset_type=meta["instrument_type"],
    )
    assert fund.ok, fund.to_dict()


def test_high_pe_growth_fixture_is_suspect_not_discarded():
    payload = _load_fixture("us_equity_high_pe_growth.json")
    meta = payload["meta"]
    bar = validate_ohlcv_bar(
        payload["bar"],
        market=meta["market"],
        asset_type=meta["instrument_type"],
    )
    assert bar.ok, bar.to_dict()
    fund = validate_fundamental_metrics(
        payload["valuation"],
        market=meta["market"],
        asset_type=meta["instrument_type"],
    )
    assert fund.status == ValidationSeverity.WARN
    assert any(i.code == CODE_FUND_PE_SUSPECT for i in fund.issues)
    assert not fund.has_reject
    assert payload["valuation"]["pe_ratio"] == 285.4


def test_validate_indicator_inputs_via_annotate_data_type():
    frame = _normal_frame([_normal_bar(close=float("nan"))])
    result = validate_and_annotate(
        frame,
        data_type="indicator_inputs",
        stock_code="600519",
        market="cn",
        strict=False,
    )
    assert result.has_reject
    assert any("non_finite" in i.code for i in result.issues)
