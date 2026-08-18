# -*- coding: utf-8 -*-
"""
===================================
DSA Schemas
===================================

Internal analysis and domain contracts. Prefer Pydantic v2
(``model_validate`` / ``model_dump``, explicit ``model_config``) for new or
migrated service-boundary DTOs; dataclasses and TypedDicts remain valid for
stable internal or performance-sensitive shapes. Public HTTP request and
response DTOs live in ``src/api/v1/schemas``. Do not adopt PydanticAI as the
agent orchestrator from this package.
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
from src.schemas.report_strata import (
    REPORT_STRATA_SCHEMA_VERSION,
    DataGapOrConflict,
    FrameworkAlignment,
    ReportStrata,
    VerifiedFact,
    empty_report_strata,
    ensure_report_strata,
    normalize_report_strata,
    resolve_report_strata,
    attach_report_strata_to_dashboard,
    project_report_strata_for_api,
)
from src.schemas.request_context import (
    AnalysisRequestContext,
    NotificationReplyTarget,
    ReplyTargetKind,
)
from src.schemas.run_flow import RunFlowSnapshot

__all__ = [
    "AnalysisReportSchema",
    "REPORT_STRATA_SCHEMA_VERSION",
    "DataGapOrConflict",
    "FrameworkAlignment",
    "ReportStrata",
    "VerifiedFact",
    "empty_report_strata",
    "ensure_report_strata",
    "normalize_report_strata",
    "resolve_report_strata",
    "attach_report_strata_to_dashboard",
    "project_report_strata_for_api",
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
