# -*- coding: utf-8 -*-
"""Runtime immutability proofs for Agent Soul and ToolSurface denials.

Reflection and post-mortem paths must never rewrite the owner-controlled Soul
charter or expand/relax ToolSurface denial boundaries. These helpers snapshot
identity before optional work and re-check afterward.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.agent.soul import (
    AGENT_SOUL_CHARTER,
    AGENT_SOUL_HASH,
    AGENT_SOUL_VERSION,
)


@dataclass(frozen=True)
class SoulIdentitySnapshot:
    """Content-addressed Soul identity captured at a single moment."""

    version: str
    content_hash: str
    charter: str


@dataclass(frozen=True)
class ToolSurfaceDenialSnapshot:
    """Stable projection of ToolSurface denial / allow boundaries."""

    tool_names: Tuple[str, ...]
    denial_codes: Tuple[str, ...]
    surface_id: Optional[str] = None


def snapshot_soul_identity() -> SoulIdentitySnapshot:
    """Capture the live module-level Soul identity."""
    return SoulIdentitySnapshot(
        version=str(AGENT_SOUL_VERSION),
        content_hash=str(AGENT_SOUL_HASH),
        charter=str(AGENT_SOUL_CHARTER),
    )


def assert_soul_unchanged(before: SoulIdentitySnapshot) -> None:
    """Fail closed if any Soul identity field changed at runtime."""
    after = snapshot_soul_identity()
    if after != before:
        raise RuntimeError(
            "Agent Soul identity changed during reflection/post-mortem; "
            "runtime Soul mutation is forbidden"
        )


def snapshot_tool_surface_denials(
    tool_surface: Any = None,
    *,
    denied_tools: Optional[Sequence[str]] = None,
    denial_codes: Optional[Sequence[str]] = None,
) -> ToolSurfaceDenialSnapshot:
    """Snapshot public tool names and explicit denial codes.

    When a live ``ToolSurface`` is provided, public tool names are listed.
    Callers may also pass explicit denial lists from the active permission
    fence; those are compared byte-for-byte after the reflection path.
    """
    names: List[str] = []
    if tool_surface is not None:
        try:
            public = tool_surface.list_tools(format="public")
        except Exception:
            public = []
        for item in public or []:
            if isinstance(item, dict):
                name = item.get("name") or (item.get("function") or {}).get("name")
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
            elif isinstance(item, str) and item.strip():
                names.append(item.strip())
    if denied_tools:
        for name in denied_tools:
            if isinstance(name, str) and name.strip() and name.strip() not in names:
                names.append(f"denied:{name.strip()}")
    codes = tuple(
        sorted(
            {
                str(code).strip()
                for code in (denial_codes or ())
                if str(code).strip()
            }
        )
    )
    surface_id = None
    if tool_surface is not None:
        surface_id = f"{type(tool_surface).__module__}.{type(tool_surface).__name__}"
    return ToolSurfaceDenialSnapshot(
        tool_names=tuple(sorted(names)),
        denial_codes=codes,
        surface_id=surface_id,
    )


def assert_tool_surface_unchanged(
    before: ToolSurfaceDenialSnapshot,
    tool_surface: Any = None,
    *,
    denied_tools: Optional[Sequence[str]] = None,
    denial_codes: Optional[Sequence[str]] = None,
) -> None:
    """Fail closed if ToolSurface allow/deny identity drifted."""
    after = snapshot_tool_surface_denials(
        tool_surface,
        denied_tools=denied_tools,
        denial_codes=denial_codes,
    )
    if after != before:
        raise RuntimeError(
            "ToolSurface denial/allow boundary changed during reflection/"
            "post-mortem; runtime mutation is forbidden"
        )


def freeze_context_meta_keys(meta: Dict[str, Any], keys: Sequence[str]) -> Dict[str, Any]:
    """Deep-copy selected meta keys so callers can prove they were not rewritten."""
    frozen: Dict[str, Any] = {}
    for key in keys:
        if key in meta:
            frozen[key] = copy.deepcopy(meta[key])
    return frozen


__all__ = [
    "SoulIdentitySnapshot",
    "ToolSurfaceDenialSnapshot",
    "assert_soul_unchanged",
    "assert_tool_surface_unchanged",
    "freeze_context_meta_keys",
    "snapshot_soul_identity",
    "snapshot_tool_surface_denials",
]
