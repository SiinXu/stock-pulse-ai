# -*- coding: utf-8 -*-
"""Prompt and Skill version identity, history, and rollback foundation (issue #249).

This package is the versioning base for Skills and key prompts. Promotion /
experimental activation stays in issue #1093 and is intentionally not
implemented here.
"""

from src.agent.prompt_versioning.identity import (
    attach_skill_identity,
    build_run_version_trace,
    content_hash_for_text,
    skill_canonical_payload,
    skill_content_hash,
    skill_version_label,
)
from src.agent.prompt_versioning.registry import (
    KEY_PROMPT_IDS,
    KeyPromptSpec,
    get_key_prompt_identity,
    list_key_prompt_identities,
)
from src.agent.prompt_versioning.service import (
    PromptArtifactService,
    apply_active_skill_pin,
    get_prompt_artifact_service,
    reset_prompt_artifact_service_for_tests,
    resolve_key_prompt_text,
)
from src.agent.prompt_versioning.types import (
    ArtifactKind,
    ArtifactRevision,
    ArtifactSnapshot,
    LifecycleState,
    VersionedIdentity,
)

__all__ = [
    "ArtifactKind",
    "ArtifactRevision",
    "ArtifactSnapshot",
    "KEY_PROMPT_IDS",
    "KeyPromptSpec",
    "LifecycleState",
    "PromptArtifactService",
    "VersionedIdentity",
    "apply_active_skill_pin",
    "attach_skill_identity",
    "build_run_version_trace",
    "content_hash_for_text",
    "get_key_prompt_identity",
    "get_prompt_artifact_service",
    "list_key_prompt_identities",
    "reset_prompt_artifact_service_for_tests",
    "resolve_key_prompt_text",
    "skill_canonical_payload",
    "skill_content_hash",
    "skill_version_label",
]
