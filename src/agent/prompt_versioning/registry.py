# -*- coding: utf-8 -*-
"""Baseline registry of shipped key prompts (identity only; no text edits)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from src.agent.prompt_versioning.identity import content_hash_for_text
from src.agent.prompt_versioning.types import (
    ArtifactKind,
    LifecycleState,
    VersionedIdentity,
)

# Baseline author labels for currently shipped bodies. Future text edits must
# bump the label in a dedicated PR; this module must not rewrite prompt text.
_BASELINE_VERSION = "1.0.0"


@dataclass(frozen=True)
class KeyPromptSpec:
    """Static registration for one key prompt identity."""

    artifact_id: str
    version: str
    loader: Callable[[], str]
    description: str = ""


def _load_agent_system() -> str:
    from src.agent.executor import AGENT_SYSTEM_PROMPT

    return AGENT_SYSTEM_PROMPT


def _load_agent_system_legacy() -> str:
    from src.agent.executor import LEGACY_DEFAULT_AGENT_SYSTEM_PROMPT

    return LEGACY_DEFAULT_AGENT_SYSTEM_PROMPT


def _load_agent_chat() -> str:
    from src.agent.executor import CHAT_SYSTEM_PROMPT

    return CHAT_SYSTEM_PROMPT


def _load_agent_chat_legacy() -> str:
    from src.agent.executor import LEGACY_DEFAULT_CHAT_SYSTEM_PROMPT

    return LEGACY_DEFAULT_CHAT_SYSTEM_PROMPT


def _load_agent_soul() -> str:
    from src.agent.soul import AGENT_SOUL_CHARTER

    return AGENT_SOUL_CHARTER


def _load_analyzer_system() -> str:
    from src.analyzer import GeminiAnalyzer

    return GeminiAnalyzer.SYSTEM_PROMPT


def _load_analyzer_system_legacy() -> str:
    from src.analyzer import GeminiAnalyzer

    return GeminiAnalyzer.LEGACY_DEFAULT_SYSTEM_PROMPT


def _load_analyzer_text() -> str:
    from src.analyzer import GeminiAnalyzer

    return GeminiAnalyzer.TEXT_SYSTEM_PROMPT


def _load_image_extract() -> str:
    from src.services.image_stock_extractor import EXTRACT_PROMPT

    return EXTRACT_PROMPT


def _load_agent_chat_summary() -> str:
    from src.agent.chat_context import SUMMARY_SYSTEM_PROMPT

    return SUMMARY_SYSTEM_PROMPT


KEY_PROMPT_SPECS: Tuple[KeyPromptSpec, ...] = (
    KeyPromptSpec(
        artifact_id="agent.system",
        version=_BASELINE_VERSION,
        loader=_load_agent_system,
        description="Agent analysis system prompt",
    ),
    KeyPromptSpec(
        artifact_id="agent.system.legacy",
        version=_BASELINE_VERSION,
        loader=_load_agent_system_legacy,
        description="Legacy default agent analysis system prompt",
    ),
    KeyPromptSpec(
        artifact_id="agent.chat",
        version=_BASELINE_VERSION,
        loader=_load_agent_chat,
        description="Agent chat system prompt",
    ),
    KeyPromptSpec(
        artifact_id="agent.chat.legacy",
        version=_BASELINE_VERSION,
        loader=_load_agent_chat_legacy,
        description="Legacy default agent chat system prompt",
    ),
    KeyPromptSpec(
        artifact_id="agent.soul",
        version=_BASELINE_VERSION,
        loader=_load_agent_soul,
        description="Agent soul charter body",
    ),
    KeyPromptSpec(
        artifact_id="analyzer.system",
        version=_BASELINE_VERSION,
        loader=_load_analyzer_system,
        description="Stock analyzer system prompt",
    ),
    KeyPromptSpec(
        artifact_id="analyzer.system.legacy",
        version=_BASELINE_VERSION,
        loader=_load_analyzer_system_legacy,
        description="Legacy default analyzer system prompt",
    ),
    KeyPromptSpec(
        artifact_id="analyzer.text",
        version=_BASELINE_VERSION,
        loader=_load_analyzer_text,
        description="Analyzer text assistant system prompt",
    ),
    KeyPromptSpec(
        artifact_id="image.extract",
        version=_BASELINE_VERSION,
        loader=_load_image_extract,
        description="Vision stock-code extraction prompt",
    ),
    KeyPromptSpec(
        artifact_id="agent.chat.summary",
        version=_BASELINE_VERSION,
        loader=_load_agent_chat_summary,
        description="Chat history summary compression prompt",
    ),
)

KEY_PROMPT_IDS: Tuple[str, ...] = tuple(spec.artifact_id for spec in KEY_PROMPT_SPECS)

_SPECS_BY_ID: Dict[str, KeyPromptSpec] = {
    spec.artifact_id: spec for spec in KEY_PROMPT_SPECS
}


def get_key_prompt_spec(artifact_id: str) -> KeyPromptSpec:
    """Return the registered KeyPromptSpec or raise KeyError."""
    key = str(artifact_id or "").strip()
    if key not in _SPECS_BY_ID:
        raise KeyError(f"Unknown key prompt id: {artifact_id!r}")
    return _SPECS_BY_ID[key]


def get_key_prompt_identity(artifact_id: str) -> VersionedIdentity:
    """Return VersionedIdentity for a registered key prompt without mutating text."""
    spec = get_key_prompt_spec(artifact_id)
    content = spec.loader()
    return VersionedIdentity(
        kind=ArtifactKind.PROMPT,
        artifact_id=spec.artifact_id,
        version=spec.version,
        content_hash=content_hash_for_text(content),
        lifecycle=LifecycleState.ACTIVE.value,
    )


def list_key_prompt_identities(
    artifact_ids: Optional[Sequence[str]] = None,
) -> List[VersionedIdentity]:
    """Return identities for all registered key prompts, or a subset."""
    if artifact_ids is None:
        ids = KEY_PROMPT_IDS
    else:
        ids = tuple(str(item).strip() for item in artifact_ids if str(item).strip())
    return [get_key_prompt_identity(item) for item in ids]


def resolve_analysis_prompt_ids(
    *,
    use_legacy_default_prompt: bool = False,
) -> Tuple[str, ...]:
    """Return key prompt ids relevant to an analysis skill activation.

    The legacy default path pins the bull_trend-era agent system prompt; the
    modern path uses the skill-switchable agent system prompt. Soul charter is
    always included because runtime composition injects it into system prompts.
    """
    system_id = (
        "agent.system.legacy" if use_legacy_default_prompt else "agent.system"
    )
    return (system_id, "agent.soul")


__all__ = [
    "KEY_PROMPT_IDS",
    "KEY_PROMPT_SPECS",
    "KeyPromptSpec",
    "get_key_prompt_identity",
    "get_key_prompt_spec",
    "list_key_prompt_identities",
    "resolve_analysis_prompt_ids",
]
