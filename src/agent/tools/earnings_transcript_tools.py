# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Default-off Agent tool for earnings-call transcript parsing (issue #253).

Separate from ``multimodal_tools.py`` (PDF/chart) and any OCR tool so parallel
workstreams (e.g. T29 OCR) do not share tool names or registration modules.
Registers only by calling ``ToolRegistry.register``; does not modify
``registry.py``.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional, Sequence

from src.agent.tools.registry import ToolDefinition, ToolParameter, ToolPolicy
from src.services.earnings_transcript_service import (
    MAX_CHUNK_CHARS,
    TRANSCRIPT_DISCLAIMER,
    TRANSCRIPT_SCHEMA_VERSION,
    EarningsTranscriptService,
)

logger = logging.getLogger(__name__)

PARSE_EARNINGS_TRANSCRIPT_TOOL_NAME = "parse_earnings_transcript"

_RELATIVE_PATH_PATTERN = r"^(?:$|(?!.*\.\.)(?!.*://)[A-Za-z0-9_./\- ()\[\]]{1,512})$"

_TRANSCRIPT_TOOL_POLICY = ToolPolicy.declared(
    read_only=True,
    side_effects=["fs_read"],
    permissions=["multimodal:read"],
    scope_dimensions=[],
)


class _ParseTranscriptHandler:
    def __init__(self, service: EarningsTranscriptService) -> None:
        self._service = service

    def __call__(
        self,
        file_path: str = "",
        text: str = "",
        max_chunk_chars: int = MAX_CHUNK_CHARS,
    ) -> dict[str, Any]:
        try:
            chunk_limit = int(max_chunk_chars)
        except (TypeError, ValueError):
            chunk_limit = MAX_CHUNK_CHARS
        chunk_limit = max(500, min(chunk_limit, MAX_CHUNK_CHARS))

        text_value = str(text or "").strip()
        path_value = str(file_path or "").strip()

        if text_value:
            result = self._service.parse_text(
                text_value,
                filename="inline_transcript.txt",
                max_chunk_chars=chunk_limit,
            )
        elif path_value:
            result = self._service.parse_path(
                path_value,
                max_chunk_chars=chunk_limit,
            )
        else:
            result = {
                "schema_version": TRANSCRIPT_SCHEMA_VERSION,
                "status": "unavailable",
                "reason_code": "missing_input",
                "source": {},
                "segments": [],
                "qa_items": [],
                "metrics": [],
                "forward_looking": [],
                "management_tone": None,
                "chunks": [],
                "method": "none",
                "text_char_count": 0,
                "disclaimer": TRANSCRIPT_DISCLAIMER,
            }

        result.setdefault("schema_version", TRANSCRIPT_SCHEMA_VERSION)
        result.setdefault("disclaimer", TRANSCRIPT_DISCLAIMER)
        return result


def _file_root_from_config(config: Any) -> Optional[str]:
    root = getattr(config, "multimodal_file_root", None)
    if root is None:
        return None
    text = str(root).strip()
    return text or None


def build_earnings_transcript_tools(
    config: Any,
    *,
    service_factory: Optional[Callable[[], EarningsTranscriptService]] = None,
) -> Optional[List[ToolDefinition]]:
    """Return the transcript tool only when the multimodal opt-in is enabled."""
    enabled = getattr(config, "multimodal_agent_tools_enabled", False) is True
    if not enabled:
        logger.debug(
            "Earnings transcript Agent Tool was not registered reason=disabled "
            "guidance=Set MULTIMODAL_AGENT_TOOLS_ENABLED=true, configure "
            "MULTIMODAL_FILE_ROOT for path inputs, and restart to opt in"
        )
        return None

    file_root = _file_root_from_config(config)
    if not file_root:
        logger.warning(
            "Earnings transcript Agent Tool was not registered reason=file_root_missing "
            "guidance=Set MULTIMODAL_FILE_ROOT to a local directory for transcript "
            "files (or provide text via the tool parameter after enabling with a root)"
        )
        return None

    try:
        service = (
            service_factory()
            if service_factory is not None
            else EarningsTranscriptService(file_root=file_root)
        )
    except Exception:  # broad-exception: fallback_recorded - optional tool stays absent.
        logger.warning(
            "Earnings transcript Agent Tool was not registered reason=service_init_failed "
            "guidance=Check MULTIMODAL_FILE_ROOT and restart"
        )
        return None

    tool = ToolDefinition(
        name=PARSE_EARNINGS_TRANSCRIPT_TOOL_NAME,
        description=(
            "Parse a user-supplied earnings-call transcript (inline text or a "
            "local .txt/.md/.pdf under MULTIMODAL_FILE_ROOT) into structured "
            "segments, Q&A turns, and source-traceable metrics. Metrics are "
            "exact source substrings with character offsets; missing numbers "
            "stay empty and are never invented. Default-off multimodal tool."
        ),
        parameters=[
            ToolParameter(
                name="file_path",
                type="string",
                description=(
                    "Relative path under MULTIMODAL_FILE_ROOT, or an absolute path "
                    "contained in that root. Optional when 'text' is provided. "
                    "Paths with '..', URLs, or home expansion are rejected."
                ),
                required=False,
                default="",
                pattern=_RELATIVE_PATH_PATTERN,
            ),
            ToolParameter(
                name="text",
                type="string",
                description=(
                    "Inline transcript text. When non-empty, takes precedence "
                    "over file_path. Prefer file_path for large transcripts."
                ),
                required=False,
                default="",
            ),
            ToolParameter(
                name="max_chunk_chars",
                type="integer",
                description=(
                    f"Maximum characters per chunk for long transcripts "
                    f"(500-{MAX_CHUNK_CHARS})."
                ),
                required=False,
                default=MAX_CHUNK_CHARS,
                minimum=500,
                maximum=MAX_CHUNK_CHARS,
            ),
        ],
        handler=_ParseTranscriptHandler(service),
        category="analysis",
        policy=_TRANSCRIPT_TOOL_POLICY,
        enforce_contract=True,
    )
    return [tool]


def register_earnings_transcript_tools(
    registry: Any,
    config: Any,
    **kwargs: Any,
) -> Sequence[str]:
    """Register transcript tools on a ToolRegistry when enabled. Returns names."""
    tools = build_earnings_transcript_tools(config, **kwargs)
    if not tools:
        return []
    names: list[str] = []
    for tool in tools:
        registry.register(tool)
        names.append(tool.name)
    return names
