# -*- coding: utf-8 -*-
"""Tests for prompt/Skill version identity, history, rollback, and run traces (#249)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agent.prompt_versioning import (
    ArtifactKind,
    PromptArtifactService,
    attach_skill_identity,
    build_run_version_trace,
    content_hash_for_text,
    get_key_prompt_identity,
    list_key_prompt_identities,
    reset_prompt_artifact_service_for_tests,
    skill_content_hash,
)
from src.agent.prompt_versioning.store import PromptArtifactStore
from src.agent.skills.base import Skill, SkillManager, load_skill_from_yaml
from src.services.run_diagnostics import (
    activate_run_diagnostic_context,
    attach_prompt_artifact_versions,
    current_diagnostic_snapshot,
    reset_run_diagnostic_context,
)


@pytest.fixture()
def isolated_service(tmp_path, monkeypatch):
    store_root = tmp_path / "prompt_artifacts"
    monkeypatch.setenv("PROMPT_ARTIFACT_STORE_DIR", str(store_root))
    service = PromptArtifactService(PromptArtifactStore(store_root))
    reset_prompt_artifact_service_for_tests(service)
    try:
        yield service
    finally:
        reset_prompt_artifact_service_for_tests(None)


def _make_skill(
    *,
    name: str = "demo_skill",
    instructions: str = "rule one",
    version: str = "",
) -> Skill:
    skill = Skill(
        name=name,
        display_name="Demo",
        description="demo skill",
        instructions=instructions,
        version=version,
    )
    return attach_skill_identity(skill, authored_version=version or None)


def test_skill_gets_content_addressed_version_when_unauthored():
    skill = _make_skill()
    assert skill.content_hash.startswith("sha256:")
    assert skill.version.startswith("ca-")
    assert skill.lifecycle == "active"
    before = skill.content_hash
    skill.enabled = True
    assert skill_content_hash(skill) == before


def test_skill_prefers_authored_version_label():
    skill = _make_skill(version="1.2.3")
    assert skill.version == "1.2.3"
    assert skill.content_hash.startswith("sha256:")


def test_yaml_loader_attaches_identity_without_changing_instructions(tmp_path):
    path = tmp_path / "demo.yaml"
    instructions = "Do not change this instruction body."
    path.write_text(
        "\n".join(
            [
                "name: demo_yaml",
                "display_name: Demo YAML",
                "description: loader test",
                "version: 2.0.0",
                "lifecycle: draft",
                "instructions: |",
                f"  {instructions}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    skill = load_skill_from_yaml(path)
    assert skill.instructions == instructions
    assert skill.version == "2.0.0"
    assert skill.lifecycle == "draft"
    assert skill.content_hash.startswith("sha256:")


def test_history_and_rollback(isolated_service: PromptArtifactService):
    skill_v1 = _make_skill(instructions="body v1", version="1.0.0")
    isolated_service.ensure_skill(skill_v1, change_summary="initial")

    skill_v2 = _make_skill(instructions="body v2", version="2.0.0")
    isolated_service.ensure_skill(skill_v2, change_summary="update")

    history = isolated_service.list_history(
        kind=ArtifactKind.SKILL,
        artifact_id="demo_skill",
    )
    assert len(history) == 2
    assert history[0]["version"] == 2
    assert history[0]["label"] == "2.0.0"
    assert history[1]["label"] == "1.0.0"

    active = isolated_service.get_active_revision(
        kind=ArtifactKind.SKILL,
        artifact_id="demo_skill",
    )
    assert active.version == 2

    rolled = isolated_service.rollback(
        kind=ArtifactKind.SKILL,
        artifact_id="demo_skill",
        to_version=1,
    )
    assert rolled.active_version == 1
    assert rolled.latest_version == 2
    body = isolated_service.resolve_active_content(
        kind=ArtifactKind.SKILL,
        artifact_id="demo_skill",
    )
    assert body is not None
    assert "body v1" in body

    isolated_service.ensure_skill(skill_v1)
    history_after = isolated_service.list_history(
        kind=ArtifactKind.SKILL,
        artifact_id="demo_skill",
    )
    assert len(history_after) == 2


def test_history_persists_across_store_reopen(tmp_path, monkeypatch):
    root = tmp_path / "store"
    monkeypatch.setenv("PROMPT_ARTIFACT_STORE_DIR", str(root))
    first = PromptArtifactService(PromptArtifactStore(root))
    skill = _make_skill(instructions="persist me", version="1.0.0")
    first.ensure_skill(skill)

    second = PromptArtifactService(PromptArtifactStore(root))
    history = second.list_history(kind=ArtifactKind.SKILL, artifact_id="demo_skill")
    assert len(history) == 1
    assert history[0]["label"] == "1.0.0"
    assert Path(root / "index.json").is_file()


def test_key_prompt_identity_does_not_require_content_change():
    identity = get_key_prompt_identity("agent.soul")
    assert identity.artifact_id == "agent.soul"
    assert identity.version == "1.0.0"
    assert identity.content_hash.startswith("sha256:")
    from src.agent.soul import AGENT_SOUL_CHARTER, AGENT_SOUL_HASH

    assert identity.content_hash == content_hash_for_text(AGENT_SOUL_CHARTER)
    assert identity.content_hash == AGENT_SOUL_HASH


def test_list_key_prompt_identities_covers_registry():
    identities = list_key_prompt_identities()
    ids = {item.artifact_id for item in identities}
    assert "agent.system" in ids
    assert "analyzer.system" in ids
    assert "image.extract" in ids


def test_run_version_trace_and_diagnostics(isolated_service: PromptArtifactService):
    skill = _make_skill(version="9.9.9")
    isolated_service.ensure_skill(skill)
    trace = build_run_version_trace(
        skills=[skill],
        prompts=[get_key_prompt_identity("agent.system")],
        active_skill_ids=["demo_skill"],
    )
    assert trace["schema_version"] == "1"
    assert trace["skill_versions"]["demo_skill"] == "9.9.9"
    assert trace["prompt_version"] == "1.0.0"
    assert trace["active_skill_ids"] == ["demo_skill"]

    token = activate_run_diagnostic_context(trace_id="trace-versioning")
    try:
        assert attach_prompt_artifact_versions(trace) is True
        snapshot = current_diagnostic_snapshot()
        assert snapshot is not None
        assert snapshot["prompt_version"] == "1.0.0"
        assert snapshot["skill_versions"]["demo_skill"] == "9.9.9"
        assert snapshot["prompt_artifact_versions"]["schema_version"] == "1"
    finally:
        reset_run_diagnostic_context(token)


def test_skill_manager_version_trace(isolated_service: PromptArtifactService, tmp_path):
    path = tmp_path / "mgr.yaml"
    path.write_text(
        "\n".join(
            [
                "name: mgr_skill",
                "display_name: Manager Skill",
                "description: manager trace",
                "version: 3.1.4",
                "instructions: |",
                "  manager body",
                "",
            ]
        ),
        encoding="utf-8",
    )
    manager = SkillManager()
    manager.register(load_skill_from_yaml(path))
    manager.activate(["mgr_skill"])
    trace = manager.get_version_trace(
        active_only=True,
        include_prompts=False,
        record_history=True,
    )
    assert trace["skill_versions"]["mgr_skill"] == "3.1.4"
    history = isolated_service.list_history(
        kind=ArtifactKind.SKILL,
        artifact_id="mgr_skill",
    )
    assert len(history) == 1


def test_builtin_bull_trend_has_identity():
    skill = load_skill_from_yaml(
        Path(__file__).resolve().parents[2] / "strategies" / "bull_trend.yaml"
    )
    assert "默认多头趋势" in skill.instructions or "Default Bull Trend" in skill.instructions
    assert skill.version
    assert skill.content_hash.startswith("sha256:")
