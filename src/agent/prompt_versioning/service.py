# -*- coding: utf-8 -*-
"""Prompt / Skill artifact history service with active-pin rollback."""

from __future__ import annotations

import json
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
    skill_content_hash,
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

    def apply_active_skill_pin(self, skill: Any) -> Any:
        """Overlay a rolled-back active pin onto a live Skill (memory only).

        Disk / plugin loaders remain the authoring source. When
        ``active_version == latest_version`` the tip is the working set and the
        loaded body is kept so authors can advance content and history. After a
        rollback (``active_version < latest_version``) this method applies the
        pinned revision's definition-bearing fields in memory only (YAML is not
        rewritten). Fail-open: missing history, bad JSON, or store errors leave
        the Skill unchanged.
        """
        artifact_id = str(getattr(skill, "name", "") or "").strip()
        if not artifact_id:
            return skill
        try:
            snapshot = self.get_snapshot(
                kind=ArtifactKind.SKILL,
                artifact_id=artifact_id,
            )
        except Exception:
            return skill
        if snapshot is None:
            return skill
        # Tip is not rolled back: keep disk/plugin body as the working set.
        if int(snapshot.active_version) >= int(snapshot.latest_version):
            return skill
        active = snapshot.active_revision()
        if active is None or not str(active.content or "").strip():
            return skill

        try:
            disk_hash = str(getattr(skill, "content_hash", "") or "").strip()
            if not disk_hash:
                disk_hash = skill_content_hash(skill)
        except Exception:
            disk_hash = ""

        if disk_hash and disk_hash == str(active.content_hash or "").strip():
            # Pin matches loaded body; align identity fields with the pin label.
            try:
                if active.label:
                    skill.version = str(active.label)
                if active.content_hash:
                    skill.content_hash = str(active.content_hash)
                if active.lifecycle:
                    skill.lifecycle = str(active.lifecycle)
            except Exception:
                pass
            return skill

        try:
            payload = json.loads(active.content)
        except (TypeError, ValueError, json.JSONDecodeError):
            return skill
        if not isinstance(payload, dict):
            return skill

        def _string_list(value: Any) -> list:
            if value is None:
                return []
            if isinstance(value, str):
                return [value.strip()] if value.strip() else []
            if isinstance(value, (list, tuple)):
                return [str(item).strip() for item in value if str(item).strip()]
            text = str(value).strip()
            return [text] if text else []

        def _int_list(value: Any) -> list:
            result = []
            if not isinstance(value, (list, tuple)):
                return result
            for item in value:
                try:
                    result.append(int(item))
                except (TypeError, ValueError):
                    continue
            return result

        try:
            if "display_name" in payload:
                skill.display_name = str(payload.get("display_name") or "").strip()
            if "description" in payload:
                skill.description = str(payload.get("description") or "").strip()
            if "instructions" in payload:
                skill.instructions = str(payload.get("instructions") or "")
            if "category" in payload:
                skill.category = str(payload.get("category") or "").strip() or "trend"
            if "core_rules" in payload:
                skill.core_rules = _int_list(payload.get("core_rules"))
            if "required_tools" in payload:
                skill.required_tools = _string_list(payload.get("required_tools"))
            if "allowed_tools" in payload:
                skill.allowed_tools = _string_list(payload.get("allowed_tools"))
            if "aliases" in payload:
                skill.aliases = _string_list(payload.get("aliases"))
            if "market_regimes" in payload:
                skill.market_regimes = _string_list(payload.get("market_regimes"))
            if "default_active" in payload:
                skill.default_active = bool(payload.get("default_active"))
            if "default_router" in payload:
                skill.default_router = bool(payload.get("default_router"))
            if "default_priority" in payload:
                try:
                    skill.default_priority = int(payload.get("default_priority") or 100)
                except (TypeError, ValueError):
                    skill.default_priority = 100
            if "disable_model_invocation" in payload:
                skill.disable_model_invocation = bool(
                    payload.get("disable_model_invocation")
                )
            if "user_invocable" in payload:
                skill.user_invocable = bool(payload.get("user_invocable"))
            if "execution_context" in payload:
                skill.execution_context = (
                    str(payload.get("execution_context") or "").strip() or "inline"
                )
            if "subagent_type" in payload:
                skill.subagent_type = str(payload.get("subagent_type") or "").strip()
            if "preferred_model" in payload:
                skill.preferred_model = str(payload.get("preferred_model") or "").strip()
            # Identity comes from the pin itself (label may be author version).
            skill.version = str(active.label or "").strip() or str(
                getattr(skill, "version", "") or ""
            )
            skill.content_hash = str(active.content_hash or "").strip()
            skill.lifecycle = str(active.lifecycle or "active").strip() or "active"
        except Exception:
            return skill
        return skill

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


def apply_active_skill_pin(skill: Any) -> Any:
    """Process-wide helper: apply the active Skill pin when history exists."""
    try:
        return get_prompt_artifact_service().apply_active_skill_pin(skill)
    except Exception:
        return skill


__all__ = [
    "PromptArtifactService",
    "apply_active_skill_pin",
    "default_prompt_artifact_store_root",
    "get_prompt_artifact_service",
    "reset_prompt_artifact_service_for_tests",
]
