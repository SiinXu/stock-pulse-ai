"""Typed API contracts for history report export."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


ReportExportFormat = Literal["md", "pdf"]
ReportExportCapabilityLanguage = Literal["en", "zh", "zh-TW", "ja", "ko"]
ReportExportCapabilityStatus = Literal[
    "ready",
    "dependency_missing",
    "dependency_import_invalid",
    "dependency_version_invalid",
    "legacy_namespace_conflict",
    "configured_font_invalid",
    "font_not_found",
    "font_invalid",
    "font_empty_cmap",
    "font_coverage_missing",
    "font_smoke_failed",
    "not_checked",
]


class ReportExportFormatCapability(BaseModel):
    """Readiness of one archive format without host filesystem details."""

    available: bool
    status: ReportExportCapabilityStatus
    media_type: str
    dependency: Optional[str] = None
    dependency_installed: bool
    dependency_version: Optional[str] = None
    font_validated: Optional[bool] = None
    missing_glyph_count: int = Field(default=0, ge=0)


class ReportExportPdfLimits(BaseModel):
    """Deterministic synchronous PDF resource bounds."""

    max_input_bytes: int = Field(gt=0)
    max_pages: int = Field(gt=0)
    max_table_rows: int = Field(gt=0)
    max_table_columns: int = Field(gt=0)
    max_output_bytes: int = Field(gt=0)
    max_render_seconds: float = Field(gt=0)
    max_concurrency: int = Field(gt=0)


class ReportExportFormats(BaseModel):
    """Closed format map so generated clients expose both known keys."""

    md: ReportExportFormatCapability
    pdf: ReportExportFormatCapability


class ReportExportCapabilitiesResponse(BaseModel):
    """Language-aware export capabilities."""

    formats: ReportExportFormats
    requested_language: ReportExportCapabilityLanguage
    supported_query_formats: List[ReportExportFormat]
    office_formats_status: Literal["not_implemented"]
    chart_handling: Literal["markdown_images_omitted_without_destinations"]
    pdf_limits: ReportExportPdfLimits
