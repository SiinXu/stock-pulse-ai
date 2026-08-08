# -*- coding: utf-8 -*-
"""Investment Committee mode — config-gated persona preset resolution (#545).

Default-off. When disabled, helpers are no-ops so existing Single/Multi paths
stay byte-identical. When enabled, the mode injects a bounded persona Skill set
into ``skills_requested`` so the existing specialist path + StrategyEngine run
unchanged. Does **not** touch the pipeline weight-aggregation seam.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from src.agent.committee_presets import (
    COMMITTEE_MAX_PERSONAS,
    COMMITTEE_MODE_NAME,
    default_committee_persona_ids,
)
from src.agent.protocols import AgentContext
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

META_COMMITTEE_MODE = "committee_mode"
META_COMMITTEE_RESOLUTION = "committee_resolution"
REQUEST_COMMITTEE_MODE = "committee_mode"
REQUEST_PERSONAS = "personas"


@dataclass(frozen=True)
class CommitteePersonaResolution:
    """Result of resolving a requested persona list for committee mode."""

    selected: List[str] = field(default_factory=list)
    invalid: List[str] = field(default_factory=list)
    truncated: List[str] = field(default_factory=list)
    source: str = "default"  # default | request | skills_requested
    max_count: int = COMMITTEE_MAX_PERSONAS
    mode: str = COMMITTEE_MODE_NAME

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "source": self.source,
            "max_count": self.max_count,
            "selected": list(self.selected),
            "invalid": list(self.invalid),
            "truncated": list(self.truncated),
        }


def is_committee_mode_enabled(config: Any = None) -> bool:
    """Return whether the default-off investment committee flag is on."""
    if config is None:
        return False
    return getattr(config, "agent_investment_committee_mode", False) is True


def _normalize_id_list(values: Optional[Sequence[Any]]) -> List[str]:
    out: List[str] = []
    if not values:
        return out
    for item in values:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out


def _available_id_set(
    available_skill_ids: Optional[Iterable[str]],
    *,
    skill_manager: Any = None,
) -> Optional[set]:
    if available_skill_ids is not None:
        return {
            str(skill_id).strip()
            for skill_id in available_skill_ids
            if isinstance(skill_id, str) and str(skill_id).strip()
        }
    if skill_manager is None:
        return None
    try:
        return {
            str(skill.name).strip()
            for skill in skill_manager.list_skills()
            if getattr(skill, "name", None)
        }
    except Exception as exc:  # broad-exception: fallback_recorded - Catalog lookup failures fall open to id-only validation.
        log_safe_exception(
            logger,
            "[committee] skill catalog unavailable; resolving personas without catalog filter",
            exc,
            error_code="agent_committee_skill_catalog_unavailable",
            level=logging.DEBUG,
        )
        return None


def resolve_committee_personas(
    requested: Optional[Sequence[Any]] = None,
    *,
    available_skill_ids: Optional[Iterable[str]] = None,
    skill_manager: Any = None,
    max_count: int = COMMITTEE_MAX_PERSONAS,
    source: str = "default",
) -> CommitteePersonaResolution:
    """Resolve persona skill ids with invalid isolation and truncation policy.

    - Empty / missing ``requested`` → default committee pack.
    - Unknown ids (when a catalog is available) → ``invalid`` (fail closed for
      those ids; never silent success as if they ran).
    - Counts above ``max_count`` → keep the first ``max_count`` stable order and
      record the remainder in ``truncated``.
    """
    cap = max(1, int(max_count) if max_count else COMMITTEE_MAX_PERSONAS)
    candidates = _normalize_id_list(requested)
    resolved_source = source
    if not candidates:
        candidates = default_committee_persona_ids()
        resolved_source = "default"

    available = _available_id_set(available_skill_ids, skill_manager=skill_manager)
    valid: List[str] = []
    invalid: List[str] = []
    for skill_id in candidates:
        if available is not None and skill_id not in available:
            invalid.append(skill_id)
            continue
        if skill_id not in valid:
            valid.append(skill_id)

    selected = valid[:cap]
    truncated = valid[cap:]
    return CommitteePersonaResolution(
        selected=selected,
        invalid=invalid,
        truncated=truncated,
        source=resolved_source,
        max_count=cap,
    )


def _request_enables_committee(request_context: Optional[Dict[str, Any]]) -> Optional[bool]:
    """Return explicit request override, or None when the request is silent."""
    if not isinstance(request_context, dict):
        return None
    if REQUEST_COMMITTEE_MODE not in request_context:
        if request_context.get(REQUEST_PERSONAS):
            return True
        return None
    raw = request_context.get(REQUEST_COMMITTEE_MODE)
    if raw is True or raw is False:
        return raw
    if isinstance(raw, str):
        lowered = raw.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return bool(raw)


def should_activate_committee(
    config: Any = None,
    request_context: Optional[Dict[str, Any]] = None,
) -> bool:
    """Combine config flag with optional per-request override."""
    override = _request_enables_committee(request_context)
    if override is False:
        return False
    if override is True:
        return True
    return is_committee_mode_enabled(config)


def apply_committee_mode(
    ctx: AgentContext,
    config: Any = None,
    *,
    request_context: Optional[Dict[str, Any]] = None,
    skill_manager: Any = None,
    available_skill_ids: Optional[Iterable[str]] = None,
    max_count: int = COMMITTEE_MAX_PERSONAS,
) -> bool:
    """Activate committee mode on ``ctx`` when enabled.

    When disabled, returns False without mutating ``ctx`` (flag-off parity).
    When enabled, writes resolution metadata and replaces ``skills_requested``
    with the resolved persona list for the existing specialist router path.
    """
    if not should_activate_committee(config, request_context):
        return False

    request_context = request_context if isinstance(request_context, dict) else {}
    personas = request_context.get(REQUEST_PERSONAS)
    source = "request"
    if personas is None:
        existing = ctx.meta.get("skills_requested") or ctx.meta.get("strategies_requested")
        if existing:
            personas = existing
            source = "skills_requested"
        else:
            personas = None
            source = "default"

    resolution = resolve_committee_personas(
        personas,
        available_skill_ids=available_skill_ids,
        skill_manager=skill_manager,
        max_count=max_count,
        source=source,
    )

    ctx.meta[META_COMMITTEE_MODE] = True
    ctx.meta[META_COMMITTEE_RESOLUTION] = resolution.to_public_dict()
    ctx.meta["skills_requested"] = list(resolution.selected)
    ctx.meta["strategies_requested"] = list(resolution.selected)

    if resolution.invalid:
        logger.info(
            "[committee] invalid persona ids isolated: %s",
            resolution.invalid,
        )
    if resolution.truncated:
        logger.info(
            "[committee] truncated personas beyond max=%s: %s",
            resolution.max_count,
            resolution.truncated,
        )
    logger.info(
        "[committee] activated mode=%s selected=%s source=%s",
        COMMITTEE_MODE_NAME,
        resolution.selected,
        resolution.source,
    )
    return True


def committee_active(ctx: Optional[AgentContext]) -> bool:
    """Return whether the current context is running in committee mode."""
    if ctx is None:
        return False
    return ctx.meta.get(META_COMMITTEE_MODE) is True


def get_committee_resolution(ctx: Optional[AgentContext]) -> Optional[Dict[str, Any]]:
    """Return the public resolution dict from context meta, if any."""
    if ctx is None:
        return None
    raw = ctx.meta.get(META_COMMITTEE_RESOLUTION)
    return dict(raw) if isinstance(raw, dict) else None


__all__ = [
    "CommitteePersonaResolution",
    "META_COMMITTEE_MODE",
    "META_COMMITTEE_RESOLUTION",
    "REQUEST_COMMITTEE_MODE",
    "REQUEST_PERSONAS",
    "apply_committee_mode",
    "committee_active",
    "get_committee_resolution",
    "is_committee_mode_enabled",
    "resolve_committee_personas",
    "should_activate_committee",
]
