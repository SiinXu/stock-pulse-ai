"""Opt-in real inference smoke test for reviewed local Kronos weights."""

from __future__ import annotations

import os
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.services.kronos_forecast_service import (
    OfficialKronosInferenceBackend,
    assess_kronos_availability,
)


@pytest.mark.network
def test_real_local_kronos_inference() -> None:
    if os.getenv("KRONOS_RUN_REAL_TEST") != "1":
        pytest.skip("Set KRONOS_RUN_REAL_TEST=1 with reviewed local weights.")

    config = SimpleNamespace(
        kronos_enabled=True,
        kronos_model_size=os.getenv("KRONOS_MODEL_SIZE", "mini"),
        kronos_weights_dir=os.getenv("KRONOS_WEIGHTS_DIR"),
    )
    availability = assess_kronos_availability(config)
    assert availability.ready, availability.message
    assert availability.spec is not None
    assert availability.model_dir is not None
    assert availability.tokenizer_dir is not None

    close = np.linspace(100.0, 110.0, 30)
    history = pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.linspace(1_000_000, 1_100_000, 30),
            "amount": close * np.linspace(1_000_000, 1_100_000, 30),
        }
    )
    history_timestamps = pd.Series(pd.bdate_range("2026-01-02", periods=30))
    future_timestamps = pd.Series(
        pd.bdate_range(history_timestamps.iloc[-1] + pd.offsets.BDay(1), periods=2)
    )
    backend = OfficialKronosInferenceBackend(
        spec=availability.spec,
        model_dir=availability.model_dir,
        tokenizer_dir=availability.tokenizer_dir,
    )

    paths = backend.predict_paths(
        history,
        history_timestamps,
        future_timestamps,
        path_count=2,
    )

    assert len(paths) == 2
    assert all(len(path) == 2 for path in paths)
    assert all({"open", "high", "low", "close"} <= set(path.columns) for path in paths)
