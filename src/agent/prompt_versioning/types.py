# -*- coding: utf-8 -*-
"""Shared types for prompt / Skill version identity and history."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Tuple


class ArtifactKind(str, Enum):
    """First-class versioned artifact categories for #249."""

    SKILL = "skill"
    PROMPT = "prompt"


class LifecycleState(str, Enum):
    """Lifecycle labels for versioned artifacts.

    Promotion / approval workflows (issue #1093) may transition these later.
    This package only stores and validates the labels.
    """

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


_LIFECYCLE_VALUES = {state.value for state in LifecycleState}


def normalize_lifecycle(value: Any, *, default: LifecycleState = LifecycleState.ACTIVE) -> str:
    """Return a valid lifecycle label or the default."""
    text = str(value or "").strip().lower()
    if text in _LIFECYCLE_VALUES:
        return text
    return default.value


@dataclass(frozen=True)
class VersionedIdentity:
    """Stable identity for one artifact body at one moment."""

    kind: ArtifactKind
    artifact_id: str
    version: str
    content_hash: str
    lifecycle: str = LifecycleState.ACTIVE.value
    source_version: Optional[int] = None

    def to_trace_entry(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "kind": self.kind.value,
            "artifact_id": self.artifact_id,
            "version": self.version,
            "content_hash": self.content_hash,
            "lifecycle": self.lifecycle,
        }
        if self.source_version is not None:
            payload["source_version"] = self.source_version
        return payload


@dataclass(frozen=True)
class ArtifactRevision:
    """One immutable content revision in history."""

    version: int
    label: str
    content_hash: str
    content: str
    lifecycle: str
    change_summary: Optional[str]
    created_at: str

    def to_dict(self, *, include_content: bool = False) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "version": self.version,
            "label": self.label,
            "content_hash": self.content_hash,
            "lifecycle": self.lifecycle,
            "change_summary": self.change_summary,
            "created_at": self.created_at,
        }
        if include_content:
            payload["content"] = self.content
        return payload


@dataclass
class ArtifactSnapshot:
    """Mutable aggregate: history plus the currently active revision pointer."""

    kind: ArtifactKind
    artifact_id: str
    latest_version: int
    active_version: int
    lifecycle: str
    revisions: Tuple[ArtifactRevision, ...] = field(default_factory=tuple)

    def active_revision(self) -> Optional[ArtifactRevision]:
        for revision in self.revisions:
            if revision.version == self.active_version:
                return revision
        return None

    def revision(self, version: int) -> Optional[ArtifactRevision]:
        for item in self.revisions:
            if item.version == version:
                return item
        return None

    def to_dict(self, *, include_content: bool = False) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "artifact_id": self.artifact_id,
            "latest_version": self.latest_version,
            "active_version": self.active_version,
            "lifecycle": self.lifecycle,
            "revisions": [
                revision.to_dict(include_content=include_content)
                for revision in self.revisions
            ],
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ArtifactSnapshot":
        kind = ArtifactKind(str(raw["kind"]))
        revisions = tuple(
            ArtifactRevision(
                version=int(item["version"]),
                label=str(item.get("label") or ""),
                content_hash=str(item["content_hash"]),
                content=str(item.get("content") or ""),
                lifecycle=normalize_lifecycle(item.get("lifecycle")),
                change_summary=(
                    str(item["change_summary"])
                    if item.get("change_summary") is not None
                    else None
                ),
                created_at=str(item.get("created_at") or ""),
            )
            for item in (raw.get("revisions") or [])
            if isinstance(item, Mapping)
        )
        return cls(
            kind=kind,
            artifact_id=str(raw["artifact_id"]),
            latest_version=int(raw.get("latest_version") or 0),
            active_version=int(raw.get("active_version") or 0),
            lifecycle=normalize_lifecycle(raw.get("lifecycle")),
            revisions=revisions,
        )
