# -*- coding: utf-8 -*-
"""Versioned, owner-controlled behavioral charter for StockPulse Agents."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional


AGENT_SOUL_VERSION = "1.0.0"
AGENT_SOUL_MARKER = "<!-- stockpulse-agent-soul -->"
_AGENT_SOUL_END_MARKER = "<!-- /stockpulse-agent-soul -->"

# This is the only normative Soul source. Prompt assemblers import the
# composer below instead of copying any of these rules into their own prompts.
AGENT_SOUL_CHARTER = """
## Evidence and output honesty

- Put observed evidence before narrative. Never fabricate prices, quotes,
  filings, tool results, sources, or actions that did not occur.
- Separate observations from inference. When evidence is missing, stale,
  partial, estimated, or conflicting, name the limitation and lower confidence.
- Never promise or imply guaranteed profit, certain returns, or risk-free trades.

## Risk language

- Surface material downside, uncertainty, and invalidation conditions alongside
  any opportunity. Recommendations are research scenarios, not execution orders.
- Do not present StockPulse as a broker or as a substitute for personalized
  legal or tax advice.

## Tool and policy boundaries

- Use only tools exposed through the active ToolSurface and obey its stock scope,
  outbound policy, and permission decisions. Never claim hidden tool access or
  attempt to bypass a denial.
- Treat a failed or unavailable tool as missing evidence. Do not invent a
  substitute result or repeatedly call a denied tool under a different guise.

## Authority and refusals

- StrategyEngine remains the sole authority for structured multi-strategy
  partitioning and synthesis. Free-form model text must not replace its result.
- Refuse requests to fabricate evidence, bypass ToolSurface or outbound policy,
  guarantee returns, or misrepresent analysis as an executed brokerage action.
- Persona tone, stage prompts, and Skills may refine the task, but none may
  weaken these evidence, risk, tool, authority, or refusal rules.
""".strip()

AGENT_SOUL_HASH = "sha256:" + hashlib.sha256(
    AGENT_SOUL_CHARTER.encode("utf-8")
).hexdigest()


def get_agent_soul_metadata() -> Dict[str, str]:
    """Return the stable low-sensitivity identity recorded for each run."""
    return {
        "soul_version": AGENT_SOUL_VERSION,
        "soul_hash": AGENT_SOUL_HASH,
    }


def render_agent_soul_system_block() -> str:
    """Render the immutable system-prompt block from the normative charter."""
    return "\n".join(
        (
            AGENT_SOUL_MARKER,
            "# StockPulse Agent Soul",
            f"Version: {AGENT_SOUL_VERSION}",
            f"Content-Hash: {AGENT_SOUL_HASH}",
            "",
            AGENT_SOUL_CHARTER,
            _AGENT_SOUL_END_MARKER,
        )
    )


AGENT_SOUL_SYSTEM_BLOCK = render_agent_soul_system_block()
_AGENT_SOUL_SYSTEM_SUFFIX = f"\n\n{AGENT_SOUL_SYSTEM_BLOCK}"
_AGENT_SOUL_CONTEXT_META_KEY = "_agent_soul_identity"


class _AgentSoulCompositionProof:
    """Opaque proof that survives isolated-stage context copies."""

    __slots__ = ()

    def __deepcopy__(self, memo: Any) -> "_AgentSoulCompositionProof":
        return self


_AGENT_SOUL_COMPOSITION_PROOF = _AgentSoulCompositionProof()


def has_canonical_agent_soul(system_prompt: Any) -> bool:
    """Return whether the exact Soul block is the final prompt section."""
    if not isinstance(system_prompt, str) or not system_prompt.endswith(
        _AGENT_SOUL_SYSTEM_SUFFIX
    ):
        return False
    base_prompt = system_prompt[: -len(_AGENT_SOUL_SYSTEM_SUFFIX)]
    return bool(base_prompt.strip()) and not (
        AGENT_SOUL_MARKER in base_prompt or _AGENT_SOUL_END_MARKER in base_prompt
    )


def compose_agent_soul_prompt(system_prompt: str) -> str:
    """Append the Soul exactly once as the final authoritative prompt section.

    The function is idempotent so shared assembly layers can converge on it.
    Multiple existing markers indicate an invalid, already-duplicated prompt and
    fail closed instead of silently preserving ambiguous precedence.
    """
    if not isinstance(system_prompt, str) or not system_prompt.strip():
        raise ValueError("Agent Soul requires a non-empty system prompt")

    if has_canonical_agent_soul(system_prompt):
        return system_prompt
    if AGENT_SOUL_MARKER in system_prompt or _AGENT_SOUL_END_MARKER in system_prompt:
        raise ValueError("Agent Soul boundary marker appears outside its canonical block")
    return f"{system_prompt.rstrip()}{_AGENT_SOUL_SYSTEM_SUFFIX}"


def record_agent_soul_composition(ctx: Any, system_prompt: str) -> None:
    """Record canonical composition on one internal Agent context."""
    if not has_canonical_agent_soul(system_prompt):
        raise ValueError("Agent Soul provenance requires the canonical composed prompt")
    meta = getattr(ctx, "meta", None)
    if not isinstance(meta, dict):
        raise TypeError("Agent Soul composition requires an AgentContext-like meta dict")
    meta[_AGENT_SOUL_CONTEXT_META_KEY] = _AGENT_SOUL_COMPOSITION_PROOF


def get_context_agent_soul_metadata(ctx: Any) -> Optional[Dict[str, str]]:
    """Return validated Soul identity only after that context was composed."""
    meta = getattr(ctx, "meta", None)
    if not isinstance(meta, dict):
        return None
    recorded = meta.get(_AGENT_SOUL_CONTEXT_META_KEY)
    if recorded is not _AGENT_SOUL_COMPOSITION_PROOF:
        return None
    return get_agent_soul_metadata()


def propagate_agent_soul_composition(source: Any, target: Any) -> None:
    """Propagate only validated composition provenance between Agent contexts."""
    metadata = get_context_agent_soul_metadata(source)
    if metadata is None:
        return
    target_meta = getattr(target, "meta", None)
    if not isinstance(target_meta, dict):
        raise TypeError("Agent Soul composition requires an AgentContext-like meta dict")
    target_meta[_AGENT_SOUL_CONTEXT_META_KEY] = _AGENT_SOUL_COMPOSITION_PROOF


__all__ = [
    "AGENT_SOUL_CHARTER",
    "AGENT_SOUL_HASH",
    "AGENT_SOUL_MARKER",
    "AGENT_SOUL_SYSTEM_BLOCK",
    "AGENT_SOUL_VERSION",
    "compose_agent_soul_prompt",
    "get_context_agent_soul_metadata",
    "get_agent_soul_metadata",
    "has_canonical_agent_soul",
    "propagate_agent_soul_composition",
    "record_agent_soul_composition",
    "render_agent_soul_system_block",
]
