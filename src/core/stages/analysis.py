# -*- coding: utf-8 -*-
"""Analysis and context stages for the stock analysis pipeline."""

import logging
import threading
import time
from datetime import date, datetime, timedelta
from types import FunctionType as _FunctionType, SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from data_provider.base import normalize_stock_code
from data_provider.realtime_types import ChipDistribution
from data_provider.us_index_mapping import is_us_stock_code
from src.analyzer import (
    AnalysisResult,
    fill_price_position_if_needed,
    normalize_chip_structure_availability,
    populate_decision_action_fields,
    stabilize_decision_with_structure,
)
from src.config import FUNDAMENTAL_STAGE_TIMEOUT_SECONDS_DEFAULT
from src.core.pipeline_stage_results import (
    PipelineStageName,
    PipelineStageResult,
)
from src.core.trading_calendar import (
    build_market_phase_context,
    get_effective_trading_date,
    get_market_for_stock,
    get_market_now,
    is_market_open,
)
from src.daily_market_context_guardrail import apply_daily_market_context_guardrail
from src.enums import ReportType
from src.market_phase_summary import render_market_phase_summary
from src.phase_decision_guardrail import apply_phase_decision_guardrails
from src.report_language import (
    get_placeholder_text,
    get_unknown_text,
    infer_decision_type_from_advice,
    localize_confidence_level,
    localize_operation_advice,
    localize_trend_prediction,
    normalize_report_language,
)
from src.search_service import SearchService
from src.services.daily_market_context import (
    DailyMarketContext,
    DailyMarketContextService,
    format_daily_market_context_prompt_section,
)
from src.services.market_hotspot_service import MarketHotspotService
from src.services.market_structure_service import MarketStructureService
from src.services.run_diagnostics import (
    PipelineStageObservation,
    current_diagnostic_snapshot,
    observe_pipeline_stage,
    record_llm_run,
    record_llm_run_started,
)
from src.stock_analyzer import TrendAnalysisResult
from src.utils.sanitize import log_safe_exception

from src.core.stages.analysis_agent import _AgentAnalysisStageMixin
from src.core.stages.analysis_context import _AnalysisContextStageMixin
from src.core.stages.analysis_results import _AnalysisResultStageMixin
from src.core.stages.analysis_stock import _StockAnalysisStageMixin


logger = logging.getLogger("src.core.pipeline")
_DAILY_MARKET_CONTEXT_SERVICE_LOCK_INIT_GUARD = threading.Lock()


class _AnalysisStageMixin:
    """Provide stock analysis, context, and result-normalization stages."""


def _clone_analysis_descriptor(descriptor: Any) -> Any:
    """Clone a stage descriptor with the analysis facade as its globals."""

    descriptor_type = None
    function = descriptor
    if isinstance(descriptor, staticmethod):
        descriptor_type = staticmethod
        function = descriptor.__func__
    elif isinstance(descriptor, classmethod):
        descriptor_type = classmethod
        function = descriptor.__func__

    if not isinstance(function, _FunctionType):
        raise TypeError("Analysis facade binding requires a Python function")

    rebound = _FunctionType(
        function.__code__,
        globals(),
        function.__name__,
        function.__defaults__,
        function.__closure__,
    )
    rebound.__kwdefaults__ = (
        dict(function.__kwdefaults__) if function.__kwdefaults__ else None
    )
    rebound.__annotations__ = dict(function.__annotations__)
    rebound.__dict__.update(function.__dict__)
    rebound.__doc__ = function.__doc__
    rebound.__module__ = __name__
    rebound.__qualname__ = (
        f"{_AnalysisStageMixin.__qualname__}.{function.__name__}"
    )
    if hasattr(function, "__type_params__"):
        rebound.__type_params__ = function.__type_params__

    if descriptor_type is not None:
        return descriptor_type(rebound)
    return rebound


def _bind_analysis_stage_methods(stage_container: Any) -> Tuple[str, ...]:
    """Bind implementation descriptors onto the stable analysis facade."""

    bound_names: List[str] = []
    rebound_descriptors: Dict[int, Any] = {}
    for name, descriptor in vars(stage_container).items():
        function = (
            descriptor.__func__
            if isinstance(descriptor, (staticmethod, classmethod))
            else descriptor
        )
        if name.startswith("__") or not isinstance(function, _FunctionType):
            continue
        descriptor_id = id(descriptor)
        if descriptor_id not in rebound_descriptors:
            rebound_descriptors[descriptor_id] = _clone_analysis_descriptor(
                descriptor
            )
        setattr(
            _AnalysisStageMixin,
            name,
            rebound_descriptors[descriptor_id],
        )
        bound_names.append(name)
    return tuple(bound_names)


_ANALYSIS_STAGE_CONTAINERS = (
    _StockAnalysisStageMixin,
    _AnalysisContextStageMixin,
    _AgentAnalysisStageMixin,
    _AnalysisResultStageMixin,
)
_bound_analysis_method_names: List[str] = []
for _stage_container in _ANALYSIS_STAGE_CONTAINERS:
    _bound_analysis_method_names.extend(
        _bind_analysis_stage_methods(_stage_container)
    )
_ANALYSIS_STAGE_METHOD_NAMES = tuple(_bound_analysis_method_names)


# Keep AST-preserved static self-references valid through the stable facade.
StockAnalysisPipeline = _AnalysisStageMixin
