# -*- coding: utf-8 -*-
"""Shared types for prompt / Skill version identity and history."""

from __future__ import annotations

import hashlib
import re
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
_ARTIFACT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_VERSION_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
_CONTENT_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_ARTIFACT_CONTENT_BYTES = 2 * 1024 * 1024
_MAX_CHANGE_SUMMARY_LENGTH = 500
_MAX_REVISIONS_PER_ARTIFACT = 4096


def normalize_lifecycle(value: Any, *, default: LifecycleState = LifecycleState.ACTIVE) -> str:
    """Return a valid lifecycle label, defaulting only when it is absent."""
    text = str(value or "").strip().lower()
    if not text:
        return default.value
    if text in _LIFECYCLE_VALUES:
        return text
    raise ValueError(f"Unsupported artifact lifecycle: {value!r}")


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

    def validate(self) -> "ArtifactSnapshot":
        """Validate persisted history invariants and return this snapshot."""
        if not _ARTIFACT_ID_RE.fullmatch(self.artifact_id):
            raise ValueError("artifact_id must be a bounded portable identifier")
        if not self.revisions:
            raise ValueError("artifact history must contain at least one revision")
        if len(self.revisions) > _MAX_REVISIONS_PER_ARTIFACT:
            raise ValueError("artifact history exceeds the revision limit")
        versions = [revision.version for revision in self.revisions]
        if any(
            isinstance(version, bool) or not isinstance(version, int) or version < 1
            for version in versions
        ) or len(set(versions)) != len(versions):
            raise ValueError("artifact revision versions must be unique positive integers")
        if versions != sorted(versions):
            raise ValueError("artifact revisions must be stored in ascending version order")
        if self.latest_version != versions[-1]:
            raise ValueError("latest_version must match the newest revision")
        if self.active_version not in set(versions):
            raise ValueError("active_version must reference an existing revision")
        normalized_lifecycle = normalize_lifecycle(self.lifecycle)
        active_revision = self.active_revision()
        if active_revision is None or normalized_lifecycle != active_revision.lifecycle:
            raise ValueError("snapshot lifecycle must match the active revision")
        labels = [revision.label for revision in self.revisions]
        if len(set(labels)) != len(labels):
            raise ValueError("artifact revision labels must be unique")
        for revision in self.revisions:
            if not _VERSION_LABEL_RE.fullmatch(revision.label):
                raise ValueError("artifact revision label is invalid")
            if not _CONTENT_HASH_RE.fullmatch(revision.content_hash):
                raise ValueError("artifact revision content hash is invalid")
            if not revision.content:
                raise ValueError("artifact revision content is required")
            if len(revision.content.encode("utf-8")) > _MAX_ARTIFACT_CONTENT_BYTES:
                raise ValueError("artifact revision content exceeds the history limit")
            expected_hash = "sha256:" + hashlib.sha256(
                revision.content.encode("utf-8")
            ).hexdigest()
            if revision.content_hash != expected_hash:
                raise ValueError("artifact revision content hash does not match its body")
            normalize_lifecycle(revision.lifecycle)
            if revision.change_summary is not None and (
                not revision.change_summary.strip()
                or len(revision.change_summary) > _MAX_CHANGE_SUMMARY_LENGTH
            ):
                raise ValueError("artifact revision change summary is invalid")
            if not revision.created_at.strip():
                raise ValueError("artifact revision created_at is required")
        return self

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
        ).validate()
