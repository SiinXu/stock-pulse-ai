# -*- coding: utf-8 -*-
"""Tests for prompt/Skill version identity, history, rollback, and run traces (#249)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

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
from src.agent.prompt_versioning.registry import KeyPromptSpec
from src.agent.prompt_versioning.store import (
    PromptArtifactStore,
    PromptArtifactStoreError,
)
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
    skill_v3 = _make_skill(instructions="body v3", version="3.0.0")
    after_new_tip = isolated_service.ensure_skill(skill_v3)
    assert after_new_tip.content_hash == skill_v3.content_hash
    pinned_snapshot = isolated_service.get_snapshot(
        kind=ArtifactKind.SKILL,
        artifact_id="demo_skill",
    )
    assert pinned_snapshot is not None
    assert pinned_snapshot.active_version == 1
    assert pinned_snapshot.latest_version == 3
    history_after = isolated_service.list_history(
        kind=ArtifactKind.SKILL,
        artifact_id="demo_skill",
    )
    assert len(history_after) == 3


def test_skill_rollback_pin_never_mutates_runtime_skill_or_tool_surface(
    isolated_service: PromptArtifactService,
    tmp_path,
):
    """A management pin must not rewrite the runtime Skill or ToolSurface metadata."""
    path = tmp_path / "pinned.yaml"
    path.write_text(
        "\n".join(
            [
                "name: pin_skill",
                "display_name: Pin Skill",
                "description: pin test",
                "version: 1.0.0",
                "required_tools: [get_daily_history]",
                "allowed_tools: [get_daily_history]",
                "instructions: |",
                "  body v1",
                "",
            ]
        ),
        encoding="utf-8",
    )
    skill_v1 = load_skill_from_yaml(path)
    isolated_service.ensure_skill(skill_v1, change_summary="v1")
    assert skill_v1.instructions.strip() == "body v1"

    # Author tip moves forward on disk.
    path.write_text(
        "\n".join(
            [
                "name: pin_skill",
                "display_name: Pin Skill",
                "description: pin test",
                "version: 2.0.0",
                "required_tools: [search_stock_news]",
                "allowed_tools: [search_stock_news]",
                "instructions: |",
                "  body v2",
                "",
            ]
        ),
        encoding="utf-8",
    )
    skill_v2 = load_skill_from_yaml(path)
    # Without history pin mismatch, disk v2 wins.
    assert skill_v2.instructions.strip() == "body v2"
    isolated_service.ensure_skill(skill_v2, change_summary="v2")

    isolated_service.rollback(
        kind=ArtifactKind.SKILL,
        artifact_id="pin_skill",
        to_version=1,
    )

    # Runtime definitions remain source-controlled. Applying a history pin to
    # instructions or tool metadata is deferred to governed promotion (#1093).
    loaded = load_skill_from_yaml(path)
    assert loaded.instructions.strip() == "body v2"
    assert loaded.version == "2.0.0"
    assert loaded.required_tools == ["search_stock_news"]
    assert loaded.allowed_tools == ["search_stock_news"]

    # SkillManager.register must not apply history state either.
    manager = SkillManager()
    disk_skill = load_skill_from_yaml(path)
    # Registration must retain the current source-defined ToolSurface.
    from src.agent.prompt_versioning import attach_skill_identity

    raw = Skill(
        name="pin_skill",
        display_name="Pin Skill",
        description="pin test",
        instructions="body v2",
        version="2.0.0",
    )
    attach_skill_identity(raw, authored_version="2.0.0")
    assert raw.instructions.strip() == "body v2"
    manager.register(raw)
    registered = manager.get("pin_skill")
    assert registered is not None
    assert registered.instructions.strip() == "body v2"

    # Disk file must remain at tip (no rewrite).
    disk_text = path.read_text(encoding="utf-8")
    assert "body v2" in disk_text
    assert "version: 2.0.0" in disk_text


def test_key_prompt_pin_resolved_after_rollback(
    isolated_service: PromptArtifactService,
    monkeypatch,
):
    """Rolled-back key prompts serve pin body; tip stays live when not rolled back."""
    from src.agent.prompt_versioning import resolve_key_prompt_text

    prompt_id = "agent.system"
    from src.agent.prompt_versioning import registry

    live_v1 = resolve_key_prompt_text(prompt_id)
    assert live_v1
    monkeypatch.setitem(
        registry._SPECS_BY_ID,
        prompt_id,
        KeyPromptSpec(
            artifact_id=prompt_id,
            version="2.0.0",
            loader=lambda: "PINNED_V2_TEMPLATE {market_role}",
        ),
    )
    assert resolve_key_prompt_text(prompt_id) == "PINNED_V2_TEMPLATE {market_role}"

    isolated_service.rollback(
        kind=ArtifactKind.PROMPT,
        artifact_id=prompt_id,
        to_version=1,
    )
    assert resolve_key_prompt_text(prompt_id) == live_v1
    from src.agent.executor import AGENT_SYSTEM_PROMPT

    rendered = AGENT_SYSTEM_PROMPT.format(
        market_role="test market",
        market_guidelines="test guidelines",
        default_skill_policy_section="",
        skills_section="",
        language_section="",
    )
    assert rendered == live_v1.format(
        market_role="test market",
        market_guidelines="test guidelines",
        default_skill_policy_section="",
        skills_section="",
        language_section="",
    )

    # Soul must never be overlaid by a history pin.
    soul_live = resolve_key_prompt_text("agent.soul")
    soul_fake_v2 = isolated_service.ensure_content(
        kind=ArtifactKind.PROMPT,
        artifact_id="agent.soul",
        content="FAKE_SOUL_V2",
        label="2.0.0",
    )
    isolated_service.ensure_content(
        kind=ArtifactKind.PROMPT,
        artifact_id="agent.soul",
        content="FAKE_SOUL_V3",
        label="3.0.0",
    )
    isolated_service.rollback(
        kind=ArtifactKind.PROMPT,
        artifact_id="agent.soul",
        to_version=soul_fake_v2.latest_version,
    )
    assert resolve_key_prompt_text("agent.soul") == soul_live
    assert "FAKE_SOUL" not in resolve_key_prompt_text("agent.soul")


def test_corrupt_store_fails_closed_without_overwriting_history(tmp_path) -> None:
    root = tmp_path / "corrupt"
    root.mkdir()
    index = root / "index.json"
    index.write_text("{broken", encoding="utf-8")
    service = PromptArtifactService(PromptArtifactStore(root))

    with pytest.raises(PromptArtifactStoreError):
        service.ensure_content(
            kind=ArtifactKind.PROMPT,
            artifact_id="agent.system",
            content="new body",
            label="1.0.0",
        )

    assert index.read_text(encoding="utf-8") == "{broken"


def test_independent_store_instances_do_not_lose_concurrent_updates(tmp_path) -> None:
    root = tmp_path / "concurrent"

    def _record(index: int) -> None:
        service = PromptArtifactService(PromptArtifactStore(root))
        service.ensure_content(
            kind=ArtifactKind.PROMPT,
            artifact_id=f"prompt.{index}",
            content=f"body {index}",
            label="1.0.0",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(_record, range(32)))

    assert len(PromptArtifactStore(root).keys()) == 32


def test_identity_metadata_rejects_invalid_governance_values() -> None:
    with pytest.raises(ValueError):
        _make_skill(version="bad version")
    skill = Skill(
        name="bad_lifecycle",
        display_name="Bad",
        description="bad lifecycle",
        instructions="body",
        lifecycle="activ",
    )
    with pytest.raises(ValueError):
        attach_skill_identity(skill)


def test_content_hash_mismatch_and_duplicate_label_fail_closed(
    isolated_service: PromptArtifactService,
) -> None:
    with pytest.raises(ValueError, match="does not match"):
        isolated_service.ensure_content(
            kind=ArtifactKind.PROMPT,
            artifact_id="agent.system",
            content="body",
            label="1.0.0",
            content_hash=content_hash_for_text("different"),
        )
    with pytest.raises(ValueError, match="reserved"):
        isolated_service.ensure_content(
            kind=ArtifactKind.PROMPT,
            artifact_id="agent.system",
            content="body",
            label="ca-deadbeef0000",
        )
    isolated_service.ensure_content(
        kind=ArtifactKind.PROMPT,
        artifact_id="agent.system",
        content="body v1",
        label="1.0.0",
    )
    with pytest.raises(ValueError, match="already identifies different content"):
        isolated_service.ensure_content(
            kind=ArtifactKind.PROMPT,
            artifact_id="agent.system",
            content="body v2",
            label="1.0.0",
        )


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


def test_production_prompt_state_records_history_and_exact_prompt_use(
    isolated_service: PromptArtifactService,
    monkeypatch,
) -> None:
    from src.agent import runtime_assembly
    from src.agent.prompt_versioning import resolve_key_prompt_text

    manager = SkillManager()
    manager.register(_make_skill(name="runtime_skill", version="4.0.0"))
    monkeypatch.setattr(runtime_assembly, "get_skill_manager", lambda _config: manager)

    token = activate_run_diagnostic_context(trace_id="trace-runtime-versioning")
    try:
        runtime_assembly.resolve_skill_prompt_state(
            SimpleNamespace(agent_skills=[]),
            skills=["runtime_skill"],
        )
        prompt_text = resolve_key_prompt_text("agent.system")
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    assert prompt_text
    assert snapshot is not None
    versions = snapshot["prompt_artifact_versions"]
    assert versions["skill_versions"]["runtime_skill"] == "4.0.0"
    assert [item["artifact_id"] for item in versions["prompts"]] == ["agent.system"]
    assert versions["prompts"][0]["source_version"] == 1
    assert len(
        isolated_service.list_history(
            kind=ArtifactKind.SKILL,
            artifact_id="runtime_skill",
        )
    ) == 1
    assert len(
        isolated_service.list_history(
            kind=ArtifactKind.PROMPT,
            artifact_id="agent.system",
        )
    ) == 1


def test_chat_summary_builder_consumes_rolled_back_prompt(
    isolated_service: PromptArtifactService,
    monkeypatch,
) -> None:
    from src.agent.chat_context import VisibleMessage, build_summary_messages
    from src.agent.prompt_versioning import registry

    prompt_id = "agent.chat.summary"
    monkeypatch.setitem(
        registry._SPECS_BY_ID,
        prompt_id,
        KeyPromptSpec(prompt_id, "1.0.0", lambda: "summary v1"),
    )
    assert build_summary_messages("", [VisibleMessage(1, "user", "hello")])[0][
        "content"
    ] == "summary v1"
    monkeypatch.setitem(
        registry._SPECS_BY_ID,
        prompt_id,
        KeyPromptSpec(prompt_id, "2.0.0", lambda: "summary v2"),
    )
    assert build_summary_messages("", [VisibleMessage(1, "user", "hello")])[0][
        "content"
    ] == "summary v2"
    isolated_service.rollback(
        kind=ArtifactKind.PROMPT,
        artifact_id=prompt_id,
        to_version=1,
    )
    assert build_summary_messages("", [VisibleMessage(1, "user", "hello")])[0][
        "content"
    ] == "summary v1"
    assert len(
        isolated_service.list_history(
            kind=ArtifactKind.PROMPT,
            artifact_id=prompt_id,
        )
    ) == 2


def test_builtin_bull_trend_has_identity():
    skill = load_skill_from_yaml(
        Path(__file__).resolve().parents[2] / "strategies" / "bull_trend.yaml"
    )
    assert "默认多头趋势" in skill.instructions or "Default Bull Trend" in skill.instructions
    assert skill.version
    assert skill.content_hash.startswith("sha256:")
