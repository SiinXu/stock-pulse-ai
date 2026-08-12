# -*- coding: utf-8 -*-
"""Primary stage input/output contracts for fetch, analyze, and render.

Value types used as ``PipelineStageResult.value`` preserve the historical
shapes stages already unpack or compare:

- daily fetch: tuple-compatible ``(data_ready, error)``
- market-input fetch: mapping-compatible artifact bundle
- analyze: ``AnalysisResult`` (domain type, unchanged)
- render: string content, or tuple-compatible ``(content, saved_path)`` for
  local report persistence

This keeps behavior identical while giving stages an explicit IO surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import (
    Any,
    ClassVar,
    Dict,
    Iterator,
    Literal,
    Mapping,
    Optional,
    Tuple,
    Union,
)

from src.core.contracts.context import RunContext
from src.enums import ReportType


RenderStageRoute = Literal[
    "single_stock",
    "local_report",
    "aggregate_notification",
]


@dataclass(frozen=True)
class FetchStageInput:
    """Inputs for a ``fetch`` stage attempt."""

    stock_code: str
    operation: Literal["prepare_daily_data", "assemble_market_inputs"]
    force_refresh: bool = False
    current_time: Optional[datetime] = None
    realtime_enabled: Optional[bool] = None
    chip_enabled: Optional[bool] = None
    daily_market_context_enabled: Optional[bool] = None
    run: Optional[RunContext] = None

    def to_input_summary(self) -> Dict[str, Any]:
        """Diagnostic input summary matching historical fetch observations."""
        summary: Dict[str, Any] = {
            "stock_code": self.stock_code,
            "operation": self.operation,
        }
        if self.operation == "prepare_daily_data":
            summary["force_refresh"] = bool(self.force_refresh)
        if self.realtime_enabled is not None:
            summary["realtime_enabled"] = bool(self.realtime_enabled)
        if self.chip_enabled is not None:
            summary["chip_enabled"] = bool(self.chip_enabled)
        if self.daily_market_context_enabled is not None:
            summary["daily_market_context_enabled"] = bool(
                self.daily_market_context_enabled
            )
        return summary


@dataclass(frozen=True)
class FetchDailyDataOutput:
    """Result of preparing/saving daily bars for one stock.

    Tuple-compatible so existing ``success, error = value`` and
    ``value[0]`` call sites keep working without behavior change.
    """

    data_ready: bool
    error: Optional[str] = None

    def as_legacy_value(self) -> Tuple[bool, Optional[str]]:
        """Return the historical ``(bool, Optional[str])`` stage value."""
        return (bool(self.data_ready), self.error)

    def to_output_summary(self) -> Dict[str, Any]:
        return {"data_ready": bool(self.data_ready)}

    def __iter__(self) -> Iterator[Any]:
        yield self.data_ready
        yield self.error

    def __getitem__(self, index: int) -> Any:
        return self.as_legacy_value()[index]

    def __len__(self) -> int:
        return 2

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FetchDailyDataOutput):
            return self.as_legacy_value() == other.as_legacy_value()
        if isinstance(other, tuple):
            return self.as_legacy_value() == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.as_legacy_value())


@dataclass(frozen=True)
class FetchMarketInputsOutput:
    """Assembled market inputs used by later analysis stages.

    Mapping-compatible for the historical dict keys stored on the fetch
    stage result. Values remain opaque artifacts owned by their producers.
    """

    realtime_quote: Any = None
    chip_data: Any = None
    fundamental_context: Any = None
    trend_result: Any = None
    daily_market_context: Any = None

    _LEGACY_KEYS: ClassVar[Tuple[str, ...]] = (
        "realtime_quote",
        "chip_data",
        "fundamental_context",
        "trend_result",
        "daily_market_context",
    )

    def as_legacy_value(self) -> Dict[str, Any]:
        """Return the historical dict shape stored on fetch results."""
        return {
            "realtime_quote": self.realtime_quote,
            "chip_data": self.chip_data,
            "fundamental_context": self.fundamental_context,
            "trend_result": self.trend_result,
            "daily_market_context": self.daily_market_context,
        }

    def to_output_summary(
        self,
        *,
        fundamental_status: Optional[str] = None,
        daily_market_context_enabled: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Diagnostic output summary matching historical fetch observations."""
        status = fundamental_status
        if status is None and isinstance(self.fundamental_context, Mapping):
            status = str(self.fundamental_context.get("status") or "").lower() or None
        summary: Dict[str, Any] = {
            "realtime_available": self.realtime_quote is not None,
            "chip_available": self.chip_data is not None,
            "fundamental_status": status or "available",
            "trend_available": self.trend_result is not None,
            "daily_market_context_available": self.daily_market_context is not None,
        }
        if daily_market_context_enabled is not None:
            summary["daily_market_context_enabled"] = bool(
                daily_market_context_enabled
            )
        return summary

    def get(self, key: str, default: Any = None) -> Any:
        return self.as_legacy_value().get(key, default)

    def keys(self):
        return self.as_legacy_value().keys()

    def items(self):
        return self.as_legacy_value().items()

    def values(self):
        return self.as_legacy_value().values()

    def __getitem__(self, key: str) -> Any:
        return self.as_legacy_value()[key]

    def __contains__(self, key: object) -> bool:
        return key in self._LEGACY_KEYS

    def __iter__(self) -> Iterator[str]:
        return iter(self._LEGACY_KEYS)

    def __len__(self) -> int:
        return len(self._LEGACY_KEYS)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FetchMarketInputsOutput):
            return self.as_legacy_value() == other.as_legacy_value()
        if isinstance(other, Mapping):
            return self.as_legacy_value() == dict(other)
        return NotImplemented


@dataclass(frozen=True)
class AnalyzeStageInput:
    """Inputs for the ``analyze`` stage (LLM or Agent path)."""

    stock_code: str
    report_type: str
    query_id: str
    current_time: Optional[datetime] = None
    stock_name: Optional[str] = None
    market_inputs: Optional[FetchMarketInputsOutput] = None
    run: Optional[RunContext] = None

    def __post_init__(self) -> None:
        report_type = self.report_type
        if isinstance(report_type, ReportType):
            object.__setattr__(self, "report_type", report_type.value)

    def to_input_summary(self) -> Dict[str, Any]:
        summary: Dict[str, Any] = {
            "stock_code": self.stock_code,
            "query_id": self.query_id,
            "report_type": self.report_type,
        }
        if self.stock_name is not None:
            summary["stock_name"] = self.stock_name
        return summary


@dataclass(frozen=True)
class AnalyzeStageOutput:
    """Analyze stage value wrapper around the domain ``AnalysisResult``."""

    result: Any
    analysis_success: bool = True
    model: Optional[str] = None

    @classmethod
    def from_result(cls, result: Any) -> "AnalyzeStageOutput":
        succeeded = bool(result is not None and getattr(result, "success", True))
        return cls(
            result=result,
            analysis_success=succeeded,
            model=getattr(result, "model_used", None) if result is not None else None,
        )

    def to_output_summary(self) -> Dict[str, Any]:
        return {
            "analysis_result_available": self.result is not None,
            "analysis_success": bool(self.analysis_success),
            "model": self.model,
        }

    def as_legacy_value(self) -> Any:
        """Historical analyze stage value is the ``AnalysisResult`` itself."""
        return self.result

    def __eq__(self, other: object) -> bool:
        if isinstance(other, AnalyzeStageOutput):
            return self.result == other.result
        return self.result == other


@dataclass(frozen=True)
class RenderStageInput:
    """Inputs for a ``render`` stage attempt."""

    report_type: str
    result_count: int
    route: RenderStageRoute
    stock_code: Optional[str] = None
    run: Optional[RunContext] = None

    def __post_init__(self) -> None:
        report_type = self.report_type
        if isinstance(report_type, ReportType):
            object.__setattr__(self, "report_type", report_type.value)

    def to_input_summary(self) -> Dict[str, Any]:
        """Diagnostic input summary matching historical render observations."""
        summary: Dict[str, Any] = {
            "report_type": self.report_type,
            "result_count": int(self.result_count),
        }
        if self.route == "single_stock":
            if self.stock_code is not None:
                summary["stock_code"] = self.stock_code
            return summary
        summary["route"] = self.route
        return summary


@dataclass(frozen=True)
class RenderStageOutput:
    """Rendered report content, optionally with a local saved path.

    - Notification / aggregate render values are string-compatible.
    - Local report values are tuple-compatible ``(content, saved_path)``.
    """

    content: Any
    saved_path: Any = None
    route: Optional[RenderStageRoute] = None
    includes_path: bool = False

    @classmethod
    def from_content(
        cls,
        content: Any,
        *,
        route: Optional[RenderStageRoute] = None,
        saved_path: Any = None,
    ) -> "RenderStageOutput":
        includes_path = saved_path is not None or route == "local_report"
        return cls(
            content=content,
            saved_path=saved_path,
            route=route,
            includes_path=includes_path,
        )

    def as_legacy_value(self) -> Any:
        if self.includes_path:
            return (self.content, self.saved_path)
        return self.content

    def to_output_summary(self, *, reused: Optional[bool] = None) -> Dict[str, Any]:
        summary: Dict[str, Any] = {
            "content_length": (
                len(self.content)
                if isinstance(self.content, (str, bytes))
                else None
            ),
        }
        if self.route is not None:
            summary["route"] = self.route
        if self.includes_path:
            summary["report_saved"] = self.saved_path is not None
        if reused is not None:
            summary["reused"] = bool(reused)
        return summary

    def __iter__(self) -> Iterator[Any]:
        if self.includes_path:
            yield self.content
            yield self.saved_path
        else:
            yield self.content

    def __getitem__(self, index: int) -> Any:
        if self.includes_path:
            return (self.content, self.saved_path)[index]
        if index == 0:
            return self.content
        raise IndexError(index)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, RenderStageOutput):
            return self.as_legacy_value() == other.as_legacy_value()
        return self.as_legacy_value() == other

    def __hash__(self) -> int:
        legacy = self.as_legacy_value()
        try:
            return hash(legacy)
        except TypeError:
            return hash(id(self))

    def __len__(self) -> int:
        if isinstance(self.content, (str, bytes)):
            return len(self.content)
        if self.includes_path:
            return 2
        return 0
