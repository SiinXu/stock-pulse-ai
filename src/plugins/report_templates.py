# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Public contract and validation for plugin-owned report templates."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Mapping, Protocol, cast

from .registry import JSONValue

if TYPE_CHECKING:
    from src.analyzer import AnalysisResult


ReportPlatform = Literal["markdown", "wechat", "brief"]
SUPPORTED_REPORT_PLATFORMS: frozenset[ReportPlatform] = frozenset(
    {"markdown", "wechat", "brief"}
)


@dataclass(frozen=True, slots=True)
class ReportRenderRequest:
    """Immutable top-level input passed to one report template candidate."""

    platform: ReportPlatform
    results: tuple[AnalysisResult, ...]
    report_date: str
    summary_only: bool
    report_language: str
    extra_context: Mapping[str, JSONValue]


class ReportTemplate(Protocol):
    """Code-backed renderer registered by a trusted plugin."""

    template_id: str
    platforms: frozenset[str]

    def render(self, request: ReportRenderRequest) -> str | None:
        """Return a complete report or decline this request with ``None``."""


def normalize_report_platform(platform: object) -> ReportPlatform | None:
    """Normalize a supported platform without guessing unknown capabilities."""

    if type(platform) is not str:
        return None
    normalized = platform.strip().lower()
    if normalized not in SUPPORTED_REPORT_PLATFORMS:
        return None
    return cast(ReportPlatform, normalized)


def validate_report_template(implementation: object) -> bool:
    """Return whether an implementation can satisfy contract version 1."""

    template_id = getattr(implementation, "template_id")
    platforms = getattr(implementation, "platforms")
    renderer = getattr(implementation, "render")
    if (
        type(template_id) is not str
        or not template_id
        or type(platforms) is not frozenset
        or not platforms
        or any(
            type(platform) is not str
            or platform not in SUPPORTED_REPORT_PLATFORMS
            for platform in platforms
        )
        or not callable(renderer)
    ):
        return False
    try:
        inspect.signature(renderer).bind(object())
    except (TypeError, ValueError):
        return False
    return True
