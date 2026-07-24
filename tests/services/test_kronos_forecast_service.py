"""Contract tests for local Kronos forecast aggregation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.services.kronos_forecast_service import (
    KRONOS_FORECAST_DISCLAIMER,
    KRONOS_MODEL_SPECS,
    KronosDataError,
    KronosForecastService,
    KronosInferenceError,
    KronosInputError,
    validate_kronos_request,
)


def _history(rows: int = 40) -> pd.DataFrame:
    close = np.linspace(100.0, 110.0, rows)
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2026-01-02", periods=rows),
            "open": close - 0.2,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.linspace(1_000_000, 1_200_000, rows),
            "amount": close * np.linspace(1_000_000, 1_200_000, rows),
        }
    )


class _ForecastBackend:
    def __init__(self, final_multipliers=None) -> None:
        self.calls = []
        self.final_multipliers = final_multipliers or (
            1.05,
            1.02,
            1.0005,
            0.98,
            0.95,
        )

    def predict_paths(
        self,
        history_frame,
        history_timestamps,
        future_timestamps,
        *,
        path_count,
    ):
        self.calls.append(
            (
                list(history_frame.columns),
                len(history_timestamps),
                len(future_timestamps),
                path_count,
            )
        )
        last_close = float(history_frame["close"].iloc[-1])
        paths = []
        for multiplier in self.final_multipliers:
            closes = np.linspace(
                last_close * (1 + (multiplier - 1) / len(future_timestamps)),
                last_close * multiplier,
                len(future_timestamps),
            )
            opens = closes * 0.999
            paths.append(
                pd.DataFrame(
                    {
                        "open": opens,
                        "high": np.maximum(opens, closes) * 1.01,
                        "low": np.minimum(opens, closes) * 0.99,
                        "close": closes,
                    },
                    index=future_timestamps,
                )
            )
        return paths


def test_mocked_inference_returns_versioned_probability_and_interval_contract() -> None:
    backend = _ForecastBackend()
    service = KronosForecastService(
        spec=KRONOS_MODEL_SPECS["mini"],
        backend=backend,
        history_loader=lambda _code, days: (_history(days), "db_cache"),
    )

    result = service.forecast(
        stock_code="600519",
        lookback_days=30,
        horizon_days=3,
    )

    assert result["schema_version"] == "kronos-forecast-v1"
    assert result["status"] == "ok"
    assert result["stock_code"] == "600519"
    assert result["data_source"] == "db_cache"
    assert result["direction"] == {
        "dominant": "ambiguous",
        "probabilities": {"up": 0.4, "flat": 0.2, "down": 0.4},
    }
    assert result["horizon_return_pct"]["p10"] < result["horizon_return_pct"]["p50"]
    assert result["horizon_return_pct"]["p50"] < result["horizon_return_pct"]["p90"]
    assert result["annualized_volatility_pct"]["p10"] >= 0
    assert len(result["daily_ohlc_intervals"]) == 3
    assert result["disclaimer"] == KRONOS_FORECAST_DISCLAIMER
    assert "not investment advice" in result["disclaimer"]
    assert backend.calls == [
        (
            ["open", "high", "low", "close", "volume", "amount"],
            30,
            3,
            5,
        )
    ]


def test_unique_direction_path_count_is_reported_as_dominant() -> None:
    backend = _ForecastBackend((1.05, 1.04, 1.03, 1.0005, 0.95))
    service = KronosForecastService(
        spec=KRONOS_MODEL_SPECS["mini"],
        backend=backend,
        history_loader=lambda _code, days: (_history(days), "db_cache"),
    )

    result = service.forecast(
        stock_code="600519",
        lookback_days=30,
        horizon_days=3,
    )

    assert result["direction"] == {
        "dominant": "up",
        "probabilities": {"up": 0.6, "flat": 0.2, "down": 0.2},
    }


@pytest.mark.parametrize(
    ("stock_code", "lookback_days", "horizon_days"),
    [
        ("../../weights", 30, 5),
        ("https://example.com/model", 30, 5),
        ("600519", 29, 5),
        ("600519", 513, 5),
        ("600519", 30, 0),
        ("600519", 30, 31),
        ("600519", True, 5),
    ],
)
def test_request_validation_rejects_paths_urls_and_out_of_range_windows(
    stock_code,
    lookback_days,
    horizon_days,
) -> None:
    with pytest.raises(KronosInputError):
        validate_kronos_request(
            stock_code=stock_code,
            lookback_days=lookback_days,
            horizon_days=horizon_days,
        )


def test_history_must_supply_the_complete_requested_valid_window() -> None:
    service = KronosForecastService(
        spec=KRONOS_MODEL_SPECS["mini"],
        backend=_ForecastBackend(),
        history_loader=lambda _code, days: (_history(days - 1), "provider"),
    )

    with pytest.raises(KronosDataError, match="fewer valid records"):
        service.forecast(
            stock_code="AAPL",
            lookback_days=30,
            horizon_days=3,
        )


def test_inconsistent_inference_path_is_rejected_instead_of_silently_repaired() -> None:
    class BadBackend:
        def predict_paths(self, *_args, **_kwargs):
            bad = pd.DataFrame(
                {
                    "open": [100.0, 100.0],
                    "high": [90.0, 90.0],
                    "low": [95.0, 95.0],
                    "close": [100.0, 100.0],
                }
            )
            return [bad, bad]

    service = KronosForecastService(
        spec=KRONOS_MODEL_SPECS["mini"],
        backend=BadBackend(),
        history_loader=lambda _code, days: (_history(days), "db_cache"),
        path_count=2,
    )

    with pytest.raises(KronosInferenceError, match="inconsistent high"):
        service.forecast(
            stock_code="AAPL",
            lookback_days=30,
            horizon_days=2,
        )


def test_non_finite_derived_return_is_rejected() -> None:
    class ExtremeBackend:
        def predict_paths(self, *_args, **_kwargs):
            extreme = pd.DataFrame(
                {
                    "open": [1e308],
                    "high": [1e308],
                    "low": [1e308],
                    "close": [1e308],
                }
            )
            return [extreme, extreme]

    history = _history(30)
    history.loc[history.index[-1], ["open", "high", "low", "close"]] = 5e-324
    service = KronosForecastService(
        spec=KRONOS_MODEL_SPECS["mini"],
        backend=ExtremeBackend(),
        history_loader=lambda _code, days: (history, "db_cache"),
        path_count=2,
    )

    with pytest.raises(KronosInferenceError, match="non-finite forecast returns"):
        service.forecast(
            stock_code="AAPL",
            lookback_days=30,
            horizon_days=1,
        )
