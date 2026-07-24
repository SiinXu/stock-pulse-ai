# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""ToolDefinition factory for the optional local Kronos plugin."""

from __future__ import annotations

import logging
from typing import Any, Callable

from src.agent.tools.registry import ToolDefinition, ToolParameter, ToolPolicy
from src.services.kronos_forecast_service import (
    KRONOS_DEFAULT_HORIZON_DAYS,
    KRONOS_DEFAULT_LOOKBACK_DAYS,
    KRONOS_FORECAST_DISCLAIMER,
    KRONOS_MAX_HORIZON_DAYS,
    KRONOS_MAX_LOOKBACK_DAYS,
    KRONOS_MIN_HORIZON_DAYS,
    KRONOS_MIN_LOOKBACK_DAYS,
    KRONOS_STOCK_CODE_PATTERN,
    KronosAvailability,
    KronosForecastError,
    KronosForecastService,
    OfficialKronosInferenceBackend,
    assess_kronos_availability,
)


logger = logging.getLogger(__name__)

KRONOS_FORECAST_TOOL_NAME = "forecast_kline_with_kronos"

_KRONOS_TOOL_POLICY = ToolPolicy.declared(
    read_only=True,
    side_effects=["network_read", "db_read", "local_model_inference"],
    permissions=["market_data:read", "local_model:execute"],
    scope_dimensions=["stock"],
)


class _KronosToolHandler:
    def __init__(self, service: KronosForecastService) -> None:
        self._service = service

    def __call__(
        self,
        stock_code: str,
        lookback_days: int = KRONOS_DEFAULT_LOOKBACK_DAYS,
        horizon_days: int = KRONOS_DEFAULT_HORIZON_DAYS,
    ) -> dict[str, Any]:
        try:
            return self._service.forecast(
                stock_code=stock_code,
                lookback_days=lookback_days,
                horizon_days=horizon_days,
            )
        except KronosForecastError as exc:
            return {
                "schema_version": "kronos-forecast-v1",
                "status": "error",
                "error": str(exc),
                "code": exc.code,
                "retriable": exc.retriable,
                "disclaimer": KRONOS_FORECAST_DISCLAIMER,
            }


def _default_service_factory(
    availability: KronosAvailability,
) -> KronosForecastService:
    if (
        availability.spec is None
        or availability.model_dir is None
        or availability.tokenizer_dir is None
    ):
        raise ValueError("Kronos availability is missing resolved local artifacts")
    backend = OfficialKronosInferenceBackend(
        spec=availability.spec,
        model_dir=availability.model_dir,
        tokenizer_dir=availability.tokenizer_dir,
    )
    backend.prepare()
    return KronosForecastService(spec=availability.spec, backend=backend)


def build_kronos_tool(
    config: Any,
    *,
    dependency_probe: Callable[[str], bool] | None = None,
    service_factory: Callable[[KronosAvailability], KronosForecastService] = (
        _default_service_factory
    ),
) -> ToolDefinition | None:
    """Return a ready tool or log why no registration may occur."""

    readiness_kwargs = {}
    if dependency_probe is not None:
        readiness_kwargs["dependency_probe"] = dependency_probe
    availability = assess_kronos_availability(config, **readiness_kwargs)
    if not availability.ready:
        log_method = logger.debug if availability.reason == "disabled" else logger.warning
        log_method(
            "Kronos Agent Tool was not registered reason=%s guidance=%s",
            availability.reason,
            availability.message,
        )
        return None

    try:
        service = service_factory(availability)
    except Exception:  # broad-exception: fallback_recorded - Offline model-load failures are reported and keep the optional tool absent.
        logger.warning(
            "Kronos Agent Tool was not registered reason=model_load_failed "
            "guidance=Reinstall requirements-kronos.txt and replace both local "
            "directories with the selected official model/tokenizer artifacts."
        )
        return None
    return ToolDefinition(
        name=KRONOS_FORECAST_TOOL_NAME,
        description=(
            "Forecast bounded future K-line direction probabilities, return "
            "intervals, and volatility intervals from recent daily OHLCV using "
            "the configured local Kronos time-series model."
        ),
        parameters=[
            ToolParameter(
                name="stock_code",
                type="string",
                description=(
                    "Stock code such as 600519, hk00700, or AAPL. Paths and URLs "
                    "are not accepted."
                ),
                pattern=KRONOS_STOCK_CODE_PATTERN,
            ),
            ToolParameter(
                name="lookback_days",
                type="integer",
                description=(
                    "Historical trading-day window used as model context "
                    f"({KRONOS_MIN_LOOKBACK_DAYS}-{KRONOS_MAX_LOOKBACK_DAYS})."
                ),
                required=False,
                default=KRONOS_DEFAULT_LOOKBACK_DAYS,
                minimum=KRONOS_MIN_LOOKBACK_DAYS,
                maximum=KRONOS_MAX_LOOKBACK_DAYS,
            ),
            ToolParameter(
                name="horizon_days",
                type="integer",
                description=(
                    "Future business-day forecast horizon "
                    f"({KRONOS_MIN_HORIZON_DAYS}-{KRONOS_MAX_HORIZON_DAYS})."
                ),
                required=False,
                default=KRONOS_DEFAULT_HORIZON_DAYS,
                minimum=KRONOS_MIN_HORIZON_DAYS,
                maximum=KRONOS_MAX_HORIZON_DAYS,
            ),
        ],
        handler=_KronosToolHandler(service),
        category="analysis",
        policy=_KRONOS_TOOL_POLICY,
        enforce_contract=True,
    )
