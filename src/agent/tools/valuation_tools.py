# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""ToolDefinition factory for optional DCF / relative valuation estimation."""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Optional, Sequence

from src.agent.tools.registry import ToolDefinition, ToolParameter, ToolPolicy
from src.services.valuation_service import (
    DEFAULT_DISCOUNT_RATE,
    DEFAULT_GROWTH_RATE,
    DEFAULT_PROJECTION_YEARS,
    DEFAULT_TERMINAL_GROWTH_RATE,
    MAX_DISCOUNT_RATE,
    MAX_GROWTH_RATE,
    MAX_PROJECTION_YEARS,
    MAX_TERMINAL_GROWTH_RATE,
    MIN_DISCOUNT_RATE,
    MIN_GROWTH_RATE,
    MIN_PROJECTION_YEARS,
    MIN_TERMINAL_GROWTH_RATE,
    VALUATION_DISCLAIMER,
    VALUATION_SCHEMA_VERSION,
    ValuationService,
)

logger = logging.getLogger(__name__)

VALUATION_TOOL_NAME = "estimate_stock_valuation"
VALUATION_STOCK_CODE_PATTERN = (
    r"^(?:"
    r"[0-9]{6}|"
    r"(?:[Hh][Kk])?[0-9]{5}|"
    r"[A-Za-z]{1,5}(?:\.(?:[Uu][Ss]|[A-Za-z]))?|"
    r"(?:[Ss][Hh]|[Ss][Zz]|[Bb][Jj])[0-9]{6}|"
    r"[0-9]{6}\.(?:[Ss][Hh]|[Ss][Zz]|[Bb][Jj])|"
    r"[0-9]{1,5}\.[Hh][Kk]"
    r")$"
)

_VALUATION_TOOL_POLICY = ToolPolicy.declared(
    read_only=True,
    side_effects=["network_read"],
    permissions=["market_data:read"],
    scope_dimensions=["stock"],
)


def _parse_peer_codes(peer_codes: Any) -> list[str]:
    if peer_codes is None:
        return []
    if isinstance(peer_codes, str):
        parts = re.split(r"[,;\s]+", peer_codes.strip())
        return [part for part in parts if part]
    if isinstance(peer_codes, (list, tuple)):
        result: list[str] = []
        for item in peer_codes:
            text = str(item or "").strip()
            if text:
                result.append(text)
        return result
    return []


class _ValuationToolHandler:
    def __init__(self, service: ValuationService) -> None:
        self._service = service

    def __call__(
        self,
        stock_code: str,
        growth_rate: Optional[float] = None,
        discount_rate: Optional[float] = None,
        terminal_growth_rate: Optional[float] = None,
        projection_years: Optional[int] = None,
        peer_codes: Optional[str] = None,
    ) -> dict[str, Any]:
        peers = _parse_peer_codes(peer_codes)
        return self._service.estimate(
            stock_code=stock_code,
            growth_rate=growth_rate,
            discount_rate=discount_rate,
            terminal_growth_rate=terminal_growth_rate,
            projection_years=projection_years,
            peer_codes=peers,
        )


def build_valuation_tool(
    config: Any,
    *,
    service_factory: Callable[[], ValuationService] | None = None,
) -> ToolDefinition | None:
    """Return the valuation tool only when the default-off flag is enabled.

    When ``valuation_agent_tool_enabled`` is false (the default), the factory
    returns ``None`` so no tool is registered in the process catalog.
    """
    enabled = getattr(config, "valuation_agent_tool_enabled", False) is True
    if not enabled:
        logger.debug(
            "Valuation Agent Tool was not registered reason=disabled "
            "guidance=Set VALUATION_AGENT_TOOL_ENABLED=true and restart to opt in"
        )
        return None

    try:
        service = (
            service_factory()
            if service_factory is not None
            else ValuationService()
        )
    except Exception:  # broad-exception: fallback_recorded - optional tool stays absent on construction failure.
        logger.warning(
            "Valuation Agent Tool was not registered reason=service_init_failed "
            "guidance=Check DataFetcherManager availability and restart after fix"
        )
        return None

    return ToolDefinition(
        name=VALUATION_TOOL_NAME,
        description=(
            "Estimate intrinsic value using a transparent DCF model and peer "
            "relative valuation (P/E, P/B). Returns explicit assumptions, a "
            "growth×discount sensitivity range, and never fabricates numbers "
            "when fundamentals are insufficient. Research support only."
        ),
        parameters=[
            ToolParameter(
                name="stock_code",
                type="string",
                description=(
                    "Stock code such as 600519, hk00700, or AAPL. Paths and URLs "
                    "are not accepted."
                ),
                pattern=VALUATION_STOCK_CODE_PATTERN,
            ),
            ToolParameter(
                name="growth_rate",
                type="number",
                description=(
                    "Optional high-growth FCF growth rate as a decimal "
                    f"(e.g. {DEFAULT_GROWTH_RATE}). When omitted, the service "
                    "derives growth from available revenue/net-profit YoY and "
                    "records that source in assumptions."
                ),
                required=False,
                default=None,
                minimum=MIN_GROWTH_RATE,
                maximum=MAX_GROWTH_RATE,
            ),
            ToolParameter(
                name="discount_rate",
                type="number",
                description=(
                    "Optional discount rate / WACC as a decimal. When omitted, "
                    f"uses {DEFAULT_DISCOUNT_RATE}."
                ),
                required=False,
                default=None,
                minimum=MIN_DISCOUNT_RATE,
                maximum=MAX_DISCOUNT_RATE,
            ),
            ToolParameter(
                name="terminal_growth_rate",
                type="number",
                description=(
                    "Optional perpetual terminal growth rate as a decimal. When "
                    f"omitted, uses {DEFAULT_TERMINAL_GROWTH_RATE}. Must stay "
                    "strictly below discount_rate."
                ),
                required=False,
                default=None,
                minimum=MIN_TERMINAL_GROWTH_RATE,
                maximum=MAX_TERMINAL_GROWTH_RATE,
            ),
            ToolParameter(
                name="projection_years",
                type="integer",
                description=(
                    "Optional high-growth projection horizon in years "
                    f"({MIN_PROJECTION_YEARS}-{MAX_PROJECTION_YEARS}). When "
                    f"omitted, uses {DEFAULT_PROJECTION_YEARS}."
                ),
                required=False,
                default=None,
                minimum=MIN_PROJECTION_YEARS,
                maximum=MAX_PROJECTION_YEARS,
            ),
            ToolParameter(
                name="peer_codes",
                type="string",
                description=(
                    "Optional comma-separated peer stock codes used for relative "
                    "valuation medians (P/E, P/B). Leave empty when peers are "
                    "unknown; relative valuation then reports insufficient "
                    "fundamentals instead of inventing peers."
                ),
                required=False,
                default=None,
            ),
        ],
        handler=_ValuationToolHandler(service),
        category="analysis",
        policy=_VALUATION_TOOL_POLICY,
        enforce_contract=True,
    )


def valuation_tool_disabled_payload(*, reason: str = "disabled") -> dict[str, Any]:
    """Stable payload for callers that probe the tool while it is off."""
    return {
        "schema_version": VALUATION_SCHEMA_VERSION,
        "status": "disabled",
        "reason": reason,
        "message": (
            "Valuation Agent Tool is default-off. Set "
            "VALUATION_AGENT_TOOL_ENABLED=true and restart the process to register it."
        ),
        "disclaimer": VALUATION_DISCLAIMER,
    }


def resolve_peer_code_sequence(peer_codes: Any) -> Sequence[str]:
    """Public helper for tests and thin adapters."""
    return _parse_peer_codes(peer_codes)
