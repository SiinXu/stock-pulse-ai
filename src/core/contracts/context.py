# -*- coding: utf-8 -*-
"""Shared run context carried across Pipeline stage boundaries.

Aligns identity fields with ``AnalysisSubject`` in
``src.schemas.analysis_context_pack`` so stage IO and context-pack assembly
share the same stock identity vocabulary without coupling stages to the full
pack schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Dict, Mapping, Optional, Union

from src.enums import ReportType
from src.schemas.analysis_context_pack import AnalysisSubject


@dataclass(frozen=True)
class RunContext:
    """Immutable cross-stage identity and request scope for one stock run.

    Fields here are the stable inputs stages may read without reaching back
    into ``StockAnalysisPipeline`` instance attributes. Stage-local artifacts
    (quotes, analysis results, rendered content) belong in stage IO types, not
    on this context.
    """

    query_id: str
    trace_id: str
    stock_code: str
    report_type: str
    query_source: Optional[str] = None
    stock_name: Optional[str] = None
    market: Optional[str] = None
    current_time: Optional[datetime] = None
    analysis_phase: str = "auto"
    portfolio_context: Optional[Dict[str, Any]] = None
    skip_analysis: bool = False
    single_stock_notify: bool = False
    save_context_snapshot: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.query_id, str) or not self.query_id:
            raise ValueError("RunContext.query_id must be a non-empty string")
        if not isinstance(self.trace_id, str) or not self.trace_id:
            raise ValueError("RunContext.trace_id must be a non-empty string")
        if not isinstance(self.stock_code, str) or not self.stock_code:
            raise ValueError("RunContext.stock_code must be a non-empty string")
        report_type = self.report_type
        if isinstance(report_type, ReportType):
            object.__setattr__(self, "report_type", report_type.value)
            report_type = self.report_type
        if not isinstance(report_type, str) or not report_type:
            raise ValueError("RunContext.report_type must be a non-empty string")
        if self.portfolio_context is not None and not isinstance(
            self.portfolio_context, Mapping
        ):
            raise TypeError("RunContext.portfolio_context must be a mapping or None")
        if self.portfolio_context is not None:
            object.__setattr__(self, "portfolio_context", dict(self.portfolio_context))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    @property
    def subject(self) -> AnalysisSubject:
        """Project the run identity into the AnalysisContextPack subject slot."""
        return AnalysisSubject(
            code=self.stock_code,
            stock_name=self.stock_name,
            market=self.market,
        )

    def with_stock_name(self, stock_name: Optional[str]) -> "RunContext":
        """Return a copy with an updated display name once it is resolved."""
        return replace(self, stock_name=stock_name)

    def with_market(self, market: Optional[str]) -> "RunContext":
        """Return a copy with an updated market once it is resolved."""
        return replace(self, market=market)

    def to_input_summary(self) -> Dict[str, Any]:
        """Low-sensitivity identity summary suitable for stage diagnostics."""
        summary: Dict[str, Any] = {
            "stock_code": self.stock_code,
            "query_id": self.query_id,
            "report_type": self.report_type,
        }
        if self.query_source is not None:
            summary["query_source"] = self.query_source
        if self.stock_name is not None:
            summary["stock_name"] = self.stock_name
        if self.market is not None:
            summary["market"] = self.market
        if self.skip_analysis:
            summary["mode"] = "dry_run"
        return summary


def build_run_context(
    *,
    query_id: str,
    trace_id: Optional[str] = None,
    stock_code: str,
    report_type: Union[ReportType, str],
    query_source: Optional[str] = None,
    stock_name: Optional[str] = None,
    market: Optional[str] = None,
    current_time: Optional[datetime] = None,
    analysis_phase: str = "auto",
    portfolio_context: Optional[Mapping[str, Any]] = None,
    skip_analysis: bool = False,
    single_stock_notify: bool = False,
    save_context_snapshot: bool = False,
    metadata: Optional[Mapping[str, Any]] = None,
) -> RunContext:
    """Build a ``RunContext`` from pipeline entry arguments."""
    report_type_value = (
        report_type.value if isinstance(report_type, ReportType) else str(report_type)
    )
    return RunContext(
        query_id=query_id,
        trace_id=trace_id or query_id,
        stock_code=stock_code,
        report_type=report_type_value,
        query_source=query_source,
        stock_name=stock_name,
        market=market,
        current_time=current_time,
        analysis_phase=analysis_phase or "auto",
        portfolio_context=dict(portfolio_context)
        if isinstance(portfolio_context, Mapping)
        else None,
        skip_analysis=bool(skip_analysis),
        single_stock_notify=bool(single_stock_notify),
        save_context_snapshot=bool(save_context_snapshot),
        metadata=dict(metadata or {}),
    )
