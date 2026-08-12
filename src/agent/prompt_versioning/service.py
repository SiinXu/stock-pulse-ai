# -*- coding: utf-8 -*-
"""Prompt / Skill artifact history service with active-pin rollback."""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from src.agent.prompt_versioning.identity import (
    attach_skill_identity,
    build_run_version_trace,
    content_hash_for_text,
    skill_content_body,
    skill_identity,
)
from src.agent.prompt_versioning.registry import (
    get_key_prompt_identity,
    get_key_prompt_spec,
    resolve_analysis_prompt_ids,
)
from src.agent.prompt_versioning.store import PromptArtifactStore
from src.agent.prompt_versioning.types import (
    ArtifactKind,
    ArtifactRevision,
    ArtifactSnapshot,
    LifecycleState,
    VersionedIdentity,
    normalize_lifecycle,
)

_SERVICE_LOCK = threading.RLock()
_SERVICE: Optional["PromptArtifactService"] = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_prompt_artifact_store_root() -> Path:
    """Resolve store root from env or beside the application database."""
    configured = os.getenv("PROMPT_ARTIFACT_STORE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    database_path = Path(
        os.getenv("DATABASE_PATH", "./data/stock_analysis.db")
    ).expanduser()
    return database_path.parent / "prompt_artifacts"


class PromptArtifactService:
    """Append-only content history with a movable active revision pin."""

    def __init__(self, store: PromptArtifactStore) -> None:
        self._store = store
        self._lock = threading.RLock()

    @property
    def store(self) -> PromptArtifactStore:
        return self._store

    def ensure_skill(
        self,
        skill: Any,
        *,
        change_summary: Optional[str] = None,
        record_history: bool = True,
    ) -> VersionedIdentity:
        """Attach identity and optionally append a history revision."""
        attach_skill_identity(skill)
        identity = skill_identity(skill)
        if not record_history or not identity.artifact_id:
            return identity
        content = skill_content_body(skill)
        self.ensure_content(
            kind=ArtifactKind.SKILL,
            artifact_id=identity.artifact_id,
            content=content,
            label=identity.version,
            lifecycle=identity.lifecycle,
            content_hash=identity.content_hash,
            change_summary=change_summary,
        )
        return identity

    def ensure_key_prompt(
        self,
        artifact_id: str,
        *,
        change_summary: Optional[str] = None,
        record_history: bool = True,
    ) -> VersionedIdentity:
        """Record a key prompt identity and optionally append history."""
        identity = get_key_prompt_identity(artifact_id)
        if not record_history:
            return identity
        content = get_key_prompt_spec(artifact_id).loader()
        self.ensure_content(
            kind=ArtifactKind.PROMPT,
            artifact_id=identity.artifact_id,
            content=content,
            label=identity.version,
            lifecycle=identity.lifecycle,
            content_hash=identity.content_hash,
            change_summary=change_summary,
        )
        return identity

    def ensure_content(
        self,
        *,
        kind: ArtifactKind | str,
        artifact_id: str,
        content: str,
        label: str = "",
        lifecycle: str = LifecycleState.ACTIVE.value,
        content_hash: Optional[str] = None,
        change_summary: Optional[str] = None,
    ) -> ArtifactSnapshot:
        """Append a revision when content hash changes; no-op when unchanged.

        Re-ensuring content that already exists in history does not create a
        new revision and does not move the active pin.
        """
        kind_enum = kind if isinstance(kind, ArtifactKind) else ArtifactKind(str(kind))
        artifact_key = str(artifact_id or "").strip()
        if not artifact_key:
            raise ValueError("artifact_id is required")
        body = content if content is not None else ""
        digest = content_hash or content_hash_for_text(body)
        life = normalize_lifecycle(lifecycle)
        version_label = str(label or "").strip() or digest

        with self._lock:
            existing = self._store.get(kind_enum, artifact_key)
            if existing is not None:
                for revision in existing.revisions:
                    if revision.content_hash == digest:
                        # Content already known — leave active pin and history alone.
                        return existing

                next_version = int(existing.latest_version) + 1
                revision = ArtifactRevision(
                    version=next_version,
                    label=version_label,
                    content_hash=digest,
                    content=body,
                    lifecycle=life,
                    change_summary=change_summary,
                    created_at=_utc_now_iso(),
                )
                revisions = tuple(existing.revisions) + (revision,)
                snapshot = ArtifactSnapshot(
                    kind=kind_enum,
                    artifact_id=artifact_key,
                    latest_version=next_version,
                    active_version=next_version,
                    lifecycle=life,
                    revisions=revisions,
                )
                return self._store.put(snapshot)

            revision = ArtifactRevision(
                version=1,
                label=version_label,
                content_hash=digest,
                content=body,
                lifecycle=life,
                change_summary=change_summary,
                created_at=_utc_now_iso(),
            )
            snapshot = ArtifactSnapshot(
                kind=kind_enum,
                artifact_id=artifact_key,
                latest_version=1,
                active_version=1,
                lifecycle=life,
                revisions=(revision,),
            )
            return self._store.put(snapshot)

    def list_history(
        self,
        *,
        kind: ArtifactKind | str,
        artifact_id: str,
        include_content: bool = False,
    ) -> List[Dict[str, Any]]:
        """Return revision dicts newest-first."""
        snapshot = self.get_snapshot(kind=kind, artifact_id=artifact_id)
        if snapshot is None:
            return []
        ordered = sorted(
            snapshot.revisions,
            key=lambda item: item.version,
            reverse=True,
        )
        return [
            revision.to_dict(include_content=include_content) for revision in ordered
        ]

    def get_snapshot(
        self,
        *,
        kind: ArtifactKind | str,
        artifact_id: str,
    ) -> Optional[ArtifactSnapshot]:
        kind_enum = kind if isinstance(kind, ArtifactKind) else ArtifactKind(str(kind))
        return self._store.get(kind_enum, str(artifact_id or "").strip())

    def get_active_revision(
        self,
        *,
        kind: ArtifactKind | str,
        artifact_id: str,
    ) -> Optional[ArtifactRevision]:
        snapshot = self.get_snapshot(kind=kind, artifact_id=artifact_id)
        if snapshot is None:
            return None
        return snapshot.active_revision()

    def rollback(
        self,
        *,
        kind: ArtifactKind | str,
        artifact_id: str,
        to_version: int,
    ) -> ArtifactSnapshot:
        """Move only the active pin to an existing revision; history is immutable."""
        kind_enum = kind if isinstance(kind, ArtifactKind) else ArtifactKind(str(kind))
        artifact_key = str(artifact_id or "").strip()
        target = int(to_version)
        with self._lock:
            snapshot = self._store.get(kind_enum, artifact_key)
            if snapshot is None:
                raise KeyError(
                    f"No artifact history for {kind_enum.value}:{artifact_key}"
                )
            revision = snapshot.revision(target)
            if revision is None:
                raise KeyError(
                    f"Version {target} not found for {kind_enum.value}:{artifact_key}"
                )
            updated = ArtifactSnapshot(
                kind=snapshot.kind,
                artifact_id=snapshot.artifact_id,
                latest_version=snapshot.latest_version,
                active_version=target,
                lifecycle=revision.lifecycle or snapshot.lifecycle,
                revisions=snapshot.revisions,
            )
            return self._store.put(updated)

    def resolve_active_content(
        self,
        *,
        kind: ArtifactKind | str,
        artifact_id: str,
    ) -> Optional[str]:
        """Return the body of the currently active revision, if any."""
        revision = self.get_active_revision(kind=kind, artifact_id=artifact_id)
        if revision is None:
            return None
        return revision.content

    def build_skill_run_trace(
        self,
        skills: Sequence[Any],
        *,
        active_skill_ids: Optional[Iterable[str]] = None,
        use_legacy_default_prompt: bool = False,
        record_history: bool = False,
        include_prompts: bool = True,
    ) -> Dict[str, Any]:
        """Build a run version trace for active skills and analysis prompts."""
        skill_list = list(skills or ())
        for skill in skill_list:
            self.ensure_skill(skill, record_history=record_history)

        prompts: List[VersionedIdentity] = []
        if include_prompts:
            for prompt_id in resolve_analysis_prompt_ids(
                use_legacy_default_prompt=use_legacy_default_prompt,
            ):
                identity = self.ensure_key_prompt(
                    prompt_id,
                    record_history=record_history,
                )
                prompts.append(identity)

        return build_run_version_trace(
            skills=skill_list,
            prompts=prompts,
            active_skill_ids=active_skill_ids,
        )


def get_prompt_artifact_service() -> PromptArtifactService:
    """Return the process singleton PromptArtifactService."""
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is None:
            root = default_prompt_artifact_store_root()
            _SERVICE = PromptArtifactService(PromptArtifactStore(root))
        return _SERVICE


def reset_prompt_artifact_service_for_tests(
    service: Optional[PromptArtifactService] = None,
) -> None:
    """Replace or clear the process singleton (tests only)."""
    global _SERVICE
    with _SERVICE_LOCK:
        _SERVICE = service


__all__ = [
    "PromptArtifactService",
    "default_prompt_artifact_store_root",
    "get_prompt_artifact_service",
    "reset_prompt_artifact_service_for_tests",
]
