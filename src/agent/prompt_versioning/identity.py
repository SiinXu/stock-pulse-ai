# -*- coding: utf-8 -*-
"""Content hashing and identity helpers for Skills and key prompts."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from src.agent.prompt_versioning.types import (
    ArtifactKind,
    LifecycleState,
    VersionedIdentity,
    normalize_lifecycle,
)

_VERSION_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
_CONTENT_ADDRESSED_PREFIX = "ca-"


def content_hash_for_text(text: str) -> str:
    """Return a stable sha256 content hash with a type prefix."""
    digest = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def normalize_version_label(value: Any) -> Optional[str]:
    """Return a bounded version label or None when absent/invalid."""
    text = str(value or "").strip()
    if not text or len(text) > 64:
        return None
    if not _VERSION_LABEL_RE.match(text):
        return None
    return text


def content_addressed_version(content_hash: str) -> str:
    """Derive a short content-addressed version label from a content hash."""
    raw = str(content_hash or "")
    if raw.startswith("sha256:"):
        raw = raw[len("sha256:") :]
    short = re.sub(r"[^0-9a-fA-F]", "", raw)[:12].lower()
    if not short:
        short = "0" * 12
    return f"{_CONTENT_ADDRESSED_PREFIX}{short}"


def skill_canonical_payload(skill: Any) -> Dict[str, Any]:
    """Build a deterministic payload used for Skill content hashing."""

    def _string_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        return [text] if text else []

    def _int_list(value: Any) -> List[int]:
        result: List[int] = []
        if not isinstance(value, (list, tuple)):
            return result
        for item in value:
            try:
                result.append(int(item))
            except (TypeError, ValueError):
                continue
        return result

    def _integer(value: Any, default: int) -> int:
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            return default

    return {
        "name": str(getattr(skill, "name", "") or "").strip(),
        "display_name": str(getattr(skill, "display_name", "") or "").strip(),
        "description": str(getattr(skill, "description", "") or "").strip(),
        "instructions": str(getattr(skill, "instructions", "") or ""),
        "category": str(getattr(skill, "category", "") or "").strip(),
        "core_rules": _int_list(getattr(skill, "core_rules", None)),
        "required_tools": _string_list(getattr(skill, "required_tools", None)),
        "allowed_tools": _string_list(getattr(skill, "allowed_tools", None)),
        "aliases": _string_list(getattr(skill, "aliases", None)),
        "market_regimes": _string_list(getattr(skill, "market_regimes", None)),
        "default_active": bool(getattr(skill, "default_active", False)),
        "default_router": bool(getattr(skill, "default_router", False)),
        "default_priority": _integer(getattr(skill, "default_priority", 100), 100),
        "disable_model_invocation": bool(getattr(skill, "disable_model_invocation", False)),
        "user_invocable": bool(getattr(skill, "user_invocable", True)),
        "execution_context": str(getattr(skill, "execution_context", "") or "").strip(),
        "subagent_type": str(getattr(skill, "subagent_type", "") or "").strip(),
        "preferred_model": str(getattr(skill, "preferred_model", "") or "").strip(),
    }


def skill_content_body(skill: Any) -> str:
    """Serialize the canonical Skill payload for hashing and history bodies."""
    return json.dumps(
        skill_canonical_payload(skill),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def skill_content_hash(skill: Any) -> str:
    """Return the content hash for a Skill definition."""
    return content_hash_for_text(skill_content_body(skill))


def resolve_version_label(authored_version: Any, *, content_hash: str) -> str:
    """Prefer an author-supplied label; otherwise use content-addressed identity."""
    authored_text = str(authored_version or "").strip()
    if not authored_text:
        return content_addressed_version(content_hash)
    explicit = normalize_version_label(authored_version)
    if explicit is None:
        raise ValueError(f"Invalid artifact version label: {authored_version!r}")
    if explicit.startswith(_CONTENT_ADDRESSED_PREFIX):
        raise ValueError("Author version labels must not use the reserved 'ca-' prefix")
    return explicit


def attach_skill_identity(
    skill: Any,
    *,
    authored_version: Optional[str] = None,
    lifecycle: Optional[str] = None,
) -> Any:
    """Mutate a Skill-like object with version, content_hash, and lifecycle."""
    digest = skill_content_hash(skill)
    if authored_version is None:
        authored_version = getattr(skill, "version", None)
    version = resolve_version_label(authored_version, content_hash=digest)
    life = normalize_lifecycle(
        lifecycle if lifecycle is not None else getattr(skill, "lifecycle", None)
    )
    skill.version = version
    skill.content_hash = digest
    skill.lifecycle = life
    return skill


def skill_identity(skill: Any) -> VersionedIdentity:
    """Project a Skill-like object into a VersionedIdentity."""
    name = str(getattr(skill, "name", "") or "").strip()
    digest = str(getattr(skill, "content_hash", "") or "").strip() or skill_content_hash(skill)
    authored = getattr(skill, "version", None)
    version = str(authored or "").strip() or resolve_version_label(None, content_hash=digest)
    return VersionedIdentity(
        kind=ArtifactKind.SKILL,
        artifact_id=name,
        version=version,
        content_hash=digest,
        lifecycle=normalize_lifecycle(getattr(skill, "lifecycle", None)),
    )


def skill_version_label(skill: Any, *, content_hash: Optional[str] = None) -> str:
    """Resolve the Skill version label for a Skill-like object."""
    digest = content_hash or (
        str(getattr(skill, "content_hash", "") or "").strip() or skill_content_hash(skill)
    )
    return resolve_version_label(getattr(skill, "version", None), content_hash=digest)


def build_run_version_trace(
    *,
    skills: Optional[Sequence[Any]] = None,
    prompts: Optional[Sequence[VersionedIdentity | Mapping[str, Any]]] = None,
    active_skill_ids: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Build a low-sensitivity run trace of Skill and prompt versions."""
    skill_entries: List[Dict[str, Any]] = []
    for skill in skills or ():
        identity = skill_identity(skill)
        if not identity.artifact_id:
            continue
        skill_entries.append(identity.to_trace_entry())

    prompt_entries: List[Dict[str, Any]] = []
    for item in prompts or ():
        if isinstance(item, VersionedIdentity):
            prompt_entries.append(item.to_trace_entry())
        elif isinstance(item, Mapping):
            prompt_entries.append(dict(item))

    active_ids = [str(item).strip() for item in (active_skill_ids or ()) if str(item).strip()]
    primary_prompt_version = None
    if prompt_entries:
        primary_prompt_version = (
            prompt_entries[0].get("version") or prompt_entries[0].get("content_hash")
        )
    return {
        "schema_version": "1",
        "skills": skill_entries,
        "prompts": prompt_entries,
        "active_skill_ids": active_ids,
        "skill_versions": {
            entry["artifact_id"]: entry.get("version")
            for entry in skill_entries
            if entry.get("artifact_id")
        },
        "prompt_version": primary_prompt_version,
    }
