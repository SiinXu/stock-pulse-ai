# -*- coding: utf-8 -*-
"""Versioned, owner-controlled behavioral charter for StockPulse Agents."""

from __future__ import annotations

import hashlib
from typing import Dict


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
_AGENT_SOUL_SYSTEM_PREFIX = f"{AGENT_SOUL_SYSTEM_BLOCK}\n\n"


def compose_agent_soul_prompt(system_prompt: str) -> str:
    """Prepend the Soul exactly once to one non-empty system prompt.

    The function is idempotent so shared assembly layers can converge on it.
    Multiple existing markers indicate an invalid, already-duplicated prompt and
    fail closed instead of silently preserving ambiguous precedence.
    """
    if not isinstance(system_prompt, str) or not system_prompt.strip():
        raise ValueError("Agent Soul requires a non-empty system prompt")

    if system_prompt.startswith(_AGENT_SOUL_SYSTEM_PREFIX):
        remaining_prompt = system_prompt[len(_AGENT_SOUL_SYSTEM_PREFIX) :]
        if (
            AGENT_SOUL_MARKER in remaining_prompt
            or _AGENT_SOUL_END_MARKER in remaining_prompt
        ):
            raise ValueError("Agent Soul boundary marker appears outside its canonical block")
        return system_prompt
    if AGENT_SOUL_MARKER in system_prompt or _AGENT_SOUL_END_MARKER in system_prompt:
        raise ValueError("Agent Soul boundary marker appears outside its canonical block")
    return f"{_AGENT_SOUL_SYSTEM_PREFIX}{system_prompt}"


__all__ = [
    "AGENT_SOUL_CHARTER",
    "AGENT_SOUL_HASH",
    "AGENT_SOUL_MARKER",
    "AGENT_SOUL_SYSTEM_BLOCK",
    "AGENT_SOUL_VERSION",
    "compose_agent_soul_prompt",
    "get_agent_soul_metadata",
    "render_agent_soul_system_block",
]
