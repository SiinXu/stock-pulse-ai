# -*- coding: utf-8 -*-
"""Prompt / Skill artifact history service with active-pin rollback."""

from __future__ import annotations

import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.agent.prompt_versioning.identity import (
    attach_skill_identity,
    build_run_version_trace,
    content_addressed_version,
    content_hash_for_text,
    normalize_version_label,
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
_ARTIFACT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MAX_ARTIFACT_CONTENT_BYTES = 2 * 1024 * 1024
_MAX_CHANGE_SUMMARY_LENGTH = 500


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_prompt_artifact_store_root() -> Path:
    """Resolve the durable store beside the application database."""
    import os

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
        if not _ARTIFACT_ID_RE.fullmatch(artifact_key):
            raise ValueError("artifact_id must be a bounded portable identifier")
        body = content if content is not None else ""
        if not body:
            raise ValueError("artifact content is required")
        if len(body.encode("utf-8")) > _MAX_ARTIFACT_CONTENT_BYTES:
            raise ValueError("artifact content exceeds the 2 MiB history limit")
        computed_digest = content_hash_for_text(body)
        if content_hash is not None and str(content_hash) != computed_digest:
            raise ValueError("content_hash does not match artifact content")
        digest = computed_digest
        life = normalize_lifecycle(lifecycle)
        label_text = str(label or "").strip()
        if label_text:
            version_label = normalize_version_label(label_text)
            if version_label is None:
                raise ValueError(f"Invalid artifact version label: {label!r}")
            if version_label.startswith("ca-"):
                raise ValueError("Authored version labels must not use the reserved 'ca-' prefix")
        else:
            version_label = content_addressed_version(digest)
        summary = None
        if change_summary is not None:
            summary = str(change_summary).strip()[:_MAX_CHANGE_SUMMARY_LENGTH] or None

        def _update(existing: Optional[ArtifactSnapshot]) -> ArtifactSnapshot:
            if existing is not None:
                for revision in existing.revisions:
                    if revision.content_hash == digest:
                        # Content already known — leave active pin and history alone.
                        return existing
                    if revision.label == version_label:
                        raise ValueError(
                            f"Version label {version_label!r} already identifies different content"
                        )

                next_version = int(existing.latest_version) + 1
                revision = ArtifactRevision(
                    version=next_version,
                    label=version_label,
                    content_hash=digest,
                    content=body,
                    lifecycle=life,
                    change_summary=summary,
                    created_at=_utc_now_iso(),
                )
                revisions = tuple(existing.revisions) + (revision,)
                snapshot = ArtifactSnapshot(
                    kind=kind_enum,
                    artifact_id=artifact_key,
                    latest_version=next_version,
                    active_version=(
                        existing.active_version
                        if existing.active_version < existing.latest_version
                        else next_version
                    ),
                    lifecycle=(
                        existing.active_revision().lifecycle
                        if existing.active_version < existing.latest_version
                        and existing.active_revision() is not None
                        else life
                    ),
                    revisions=revisions,
                )
                return snapshot

            revision = ArtifactRevision(
                version=1,
                label=version_label,
                content_hash=digest,
                content=body,
                lifecycle=life,
                change_summary=summary,
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
            return snapshot

        with self._lock:
            return self._store.update(kind_enum, artifact_key, _update)

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
        artifact_key = str(artifact_id or "").strip()
        if not _ARTIFACT_ID_RE.fullmatch(artifact_key):
            raise ValueError("artifact_id must be a bounded portable identifier")
        return self._store.get(kind_enum, artifact_key)

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
        if not _ARTIFACT_ID_RE.fullmatch(artifact_key):
            raise ValueError("artifact_id must be a bounded portable identifier")
        if isinstance(to_version, bool) or not isinstance(to_version, int) or to_version < 1:
            raise ValueError("to_version must be a positive integer")
        target = to_version

        def _update(snapshot: Optional[ArtifactSnapshot]) -> ArtifactSnapshot:
            if snapshot is None:
                raise KeyError(
                    f"No artifact history for {kind_enum.value}:{artifact_key}"
                )
            revision = snapshot.revision(target)
            if revision is None:
                raise KeyError(
                    f"Version {target} not found for {kind_enum.value}:{artifact_key}"
                )
            return ArtifactSnapshot(
                kind=snapshot.kind,
                artifact_id=snapshot.artifact_id,
                latest_version=snapshot.latest_version,
                active_version=target,
                lifecycle=revision.lifecycle or snapshot.lifecycle,
                revisions=snapshot.revisions,
            )

        with self._lock:
            return self._store.update(kind_enum, artifact_key, _update)

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
                _, identity = self.resolve_key_prompt(
                    prompt_id,
                    record_history=record_history,
                )
                prompts.append(identity)

        return build_run_version_trace(
            skills=skill_list,
            prompts=prompts,
            active_skill_ids=active_skill_ids,
        )

    def resolve_key_prompt(
        self,
        artifact_id: str,
        *,
        record_history: bool = True,
    ) -> Tuple[str, VersionedIdentity]:
        """Select the precise live or pinned prompt revision and its identity."""
        spec = get_key_prompt_spec(artifact_id)
        live = spec.loader()
        live_digest = content_hash_for_text(live)
        snapshot = (
            self.ensure_content(
                kind=ArtifactKind.PROMPT,
                artifact_id=artifact_id,
                content=live,
                label=spec.version,
                lifecycle=LifecycleState.ACTIVE.value,
            )
            if record_history
            else self.get_snapshot(kind=ArtifactKind.PROMPT, artifact_id=artifact_id)
        )
        selected: Optional[ArtifactRevision] = None
        if snapshot is not None:
            selected = next(
                (
                    revision
                    for revision in snapshot.revisions
                    if revision.content_hash == live_digest
                ),
                None,
            )
            if (
                artifact_id not in _PIN_FORBIDDEN_PROMPT_IDS
                and snapshot.active_version < snapshot.latest_version
            ):
                selected = snapshot.active_revision()
                if selected is None:
                    raise RuntimeError(
                        f"Active prompt revision is missing for {artifact_id!r}"
                    )

        if selected is None:
            return live, VersionedIdentity(
                kind=ArtifactKind.PROMPT,
                artifact_id=artifact_id,
                version=spec.version,
                content_hash=live_digest,
                lifecycle=LifecycleState.ACTIVE.value,
            )
        return selected.content, VersionedIdentity(
            kind=ArtifactKind.PROMPT,
            artifact_id=artifact_id,
            version=selected.label,
            content_hash=selected.content_hash,
            lifecycle=selected.lifecycle,
            source_version=selected.version,
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


# Soul charter is identity-proofed elsewhere; never overlay a history pin onto it.
_PIN_FORBIDDEN_PROMPT_IDS = frozenset({"agent.soul"})


def resolve_key_prompt_text(prompt_id: str) -> str:
    """Return live key-prompt text, or a rolled-back pin body when active < latest.

    Does not rewrite module-level prompt constants. ``agent.soul`` always uses
    the live charter (runtime Soul identity proofs forbid pin overlays). Store
    corruption raises instead of silently executing content outside the pin.
    """
    from src.services.run_diagnostics import attach_prompt_artifact_versions

    artifact_id = str(prompt_id or "").strip()
    service = get_prompt_artifact_service()
    selected_content, identity = service.resolve_key_prompt(artifact_id)
    attach_prompt_artifact_versions(
        build_run_version_trace(prompts=[identity])
    )
    return selected_content


__all__ = [
    "PromptArtifactService",
    "default_prompt_artifact_store_root",
    "get_prompt_artifact_service",
    "reset_prompt_artifact_service_for_tests",
    "resolve_key_prompt_text",
]
