# -*- coding: utf-8 -*-
"""Strict MCP tool schemas and service dispatch."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Callable, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator

from src.mcp_server.capabilities import exposed_tool_names
from src.mcp_server.handlers import McpToolHandlers


class _ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


StockCode = Annotated[StrictStr, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9.*+_-]+$")]
RecordId = Annotated[StrictStr, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:@/-]+$")]


class QuoteInput(_ToolInput):
    stock_code: StockCode


class StockHistoryInput(_ToolInput):
    stock_code: StockCode
    period: Literal["daily"] = "daily"
    days: Annotated[StrictInt, Field(ge=1, le=3650)] = 30


class AnalysisHistoryInput(_ToolInput):
    stock_code: StockCode | None = None
    report_type: Literal["simple", "detailed", "full", "brief"] | None = None
    start_date: date | None = None
    end_date: date | None = None
    page: Annotated[StrictInt, Field(ge=1, le=10_000)] = 1
    limit: Annotated[StrictInt, Field(ge=1, le=100)] = 20

    @model_validator(mode="after")
    def dates_are_ordered(self) -> "AnalysisHistoryInput":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self


class AnalysisRecordInput(_ToolInput):
    record_id: RecordId


class PortfolioAccountsInput(_ToolInput):
    include_inactive: StrictBool = False


class PortfolioSnapshotInput(_ToolInput):
    account_id: Annotated[StrictInt, Field(ge=1)] | None = None
    as_of: date | None = None
    cost_method: Literal["fifo", "avg"] = "fifo"
    include_realtime: StrictBool = False


class AnalysisStatusInput(_ToolInput):
    task_id: RecordId


class TriggerAnalysisInput(_ToolInput):
    stock_code: StockCode | None = None
    stock_codes: Annotated[list[StockCode], Field(min_length=1, max_length=50)] | None = None
    report_type: Literal["simple", "detailed", "full", "brief"] = "detailed"
    force_refresh: StrictBool = False
    async_mode: Literal[True] = True

    @model_validator(mode="after")
    def one_source_and_unique_codes(self) -> "TriggerAnalysisInput":
        if (self.stock_code is None) == (self.stock_codes is None):
            raise ValueError("provide exactly one of stock_code or stock_codes")
        if self.stock_codes and len(set(self.stock_codes)) != len(self.stock_codes):
            raise ValueError("stock_codes must not contain duplicates")
        return self


class _Spec:
    def __init__(self, name: str, description: str, scope: str, input_model: type[_ToolInput]) -> None:
        self.name = name
        self.description = description
        self.scope = scope
        self.input_model = input_model


_SPECS = (
    _Spec("get_realtime_quote", "Get a realtime quote for one stock code (read-only).", "market.read", QuoteInput),
    _Spec("get_stock_history", "Get daily historical OHLCV bars for one stock (read-only).", "market.read", StockHistoryInput),
    _Spec("list_analysis_history", "List past analysis runs with bounded filters (read-only).", "history.read", AnalysisHistoryInput),
    _Spec("get_analysis_detail", "Get one analysis history record by id (read-only).", "history.read", AnalysisRecordInput),
    _Spec("get_analysis_report", "Get markdown report text for one analysis record (read-only).", "history.read", AnalysisRecordInput),
    _Spec("list_portfolio_accounts", "List portfolio accounts (read-only).", "portfolio.read", PortfolioAccountsInput),
    _Spec("get_portfolio_snapshot", "Get a bounded portfolio snapshot (read-only).", "portfolio.read", PortfolioSnapshotInput),
    _Spec("get_analysis_status", "Get status of an asynchronously submitted analysis task (read-only).", "history.read", AnalysisStatusInput),
    _Spec("trigger_analysis", "Submit bounded analysis work asynchronously; synchronous execution is not exposed.", "analysis.trigger", TriggerAnalysisInput),
)
TOOL_SPECS = {spec.name: spec for spec in _SPECS}


def list_tool_definitions(scopes: frozenset[str] | None = None) -> list[dict[str, Any]]:
    """Return advertised definitions, optionally filtered to principal scopes."""
    allowed_names = set(exposed_tool_names())
    result: list[dict[str, Any]] = []
    for spec in _SPECS:
        if spec.name not in allowed_names or (scopes is not None and spec.scope not in scopes):
            continue
        result.append(
            {
                "name": spec.name,
                "description": spec.description,
                "inputSchema": spec.input_model.model_json_schema(),
                "_meta": {"io.stockpulse/scope": spec.scope},
            }
        )
    return result


def required_scope(name: str) -> str:
    """Return the required scope for an exposed tool."""
    spec = TOOL_SPECS.get(name)
    if spec is None or name not in set(exposed_tool_names()):
        raise ValueError(f"Unknown or non-exposed tool: {name}")
    return spec.scope


def validate_tool_arguments(name: str, arguments: Mapping[str, Any] | None) -> dict[str, Any]:
    """Strictly validate the exact schema advertised for one tool."""
    spec = TOOL_SPECS.get(name)
    if spec is None or name not in set(exposed_tool_names()):
        raise ValueError(f"Unknown or non-exposed tool: {name}")
    validated = spec.input_model.model_validate(dict(arguments or {}))
    return validated.model_dump(mode="python", exclude_none=True)


def _handler_map(handlers: McpToolHandlers) -> Mapping[str, Callable[..., Any]]:
    return {
        "get_realtime_quote": handlers.get_realtime_quote,
        "get_stock_history": handlers.get_stock_history,
        "list_analysis_history": handlers.list_analysis_history,
        "get_analysis_detail": handlers.get_analysis_detail,
        "get_analysis_report": handlers.get_analysis_report,
        "list_portfolio_accounts": handlers.list_portfolio_accounts,
        "get_portfolio_snapshot": handlers.get_portfolio_snapshot,
        "get_analysis_status": handlers.get_analysis_status,
        "trigger_analysis": handlers.trigger_analysis,
    }


def call_tool(handlers: McpToolHandlers, name: str, arguments: Mapping[str, Any] | None = None) -> Any:
    """Validate once, then invoke the existing service-backed handler."""
    validated = validate_tool_arguments(name, arguments)
    fn = _handler_map(handlers).get(name)
    if fn is None:
        raise ValueError(f"Tool not implemented: {name}")
    return fn(**validated)
