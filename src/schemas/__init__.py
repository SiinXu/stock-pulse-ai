# -*- coding: utf-8 -*-
"""
===================================
DSA Schemas
===================================

Internal analysis and domain contracts. This package intentionally includes
Pydantic models, dataclasses, and TypedDicts according to boundary needs;
public HTTP request and response DTOs live in ``api/v1/schemas``.
"""

from src.schemas.analysis_context_pack import (
    PACK_VERSION,
    AnalysisContextBlock,
    AnalysisContextItem,
    AnalysisContextPack,
    AnalysisSubject,
    ContextFieldStatus,
    DataQuality,
)
from src.schemas.report_schema import AnalysisReportSchema
from src.schemas.request_context import (
    AnalysisRequestContext,
    NotificationReplyTarget,
    ReplyTargetKind,
)
from src.schemas.run_flow import RunFlowSnapshot

__all__ = [
    "AnalysisReportSchema",
    "PACK_VERSION",
    "AnalysisContextBlock",
    "AnalysisContextItem",
    "AnalysisContextPack",
    "AnalysisSubject",
    "ContextFieldStatus",
    "DataQuality",
    "AnalysisRequestContext",
    "NotificationReplyTarget",
    "ReplyTargetKind",
    "RunFlowSnapshot",
]
