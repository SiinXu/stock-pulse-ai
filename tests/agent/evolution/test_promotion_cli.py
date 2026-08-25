# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Dry-run promotion CLI sidecar: non-activation, idempotency, and rollback."""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable, Tuple

import pytest

from src.agent.evolution.guards import assert_soul_unchanged, snapshot_soul_identity
from src.agent.evolution.promotion_cli import (
    AgentPromotionService,
    PromotionProposalError,
    REVIEW_NOTE,
)
from src.agent.sandbox.clock import FakeClock
from src.agent.sandbox.policy import SANDBOX_ISOLATION_POLICY
from src.agent.skills.defaults import DEFAULT_ROUTER_SKILL_IDS
from scripts import agent_evolve as evolve_cli

REPO_ROOT = Path(__file__).resolve().parents[3]
SEEDED_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "prediction_eval"
    / "cases"
    / "pred-seeded-miss-lesson.json"
)
STRATEGIES_DIR = REPO_ROOT / "strategies"
SKILLS_DIR = REPO_ROOT / "src" / "agent" / "skills"
PROMOTION_CLI_PATH = REPO_ROOT / "src" / "agent" / "evolution" / "promotion_cli.py"
FIXED_NOW = FakeClock.fixed("2026-08-01T00:00:00Z")


def _catalog_fingerprint(paths: Iterable[Path]) -> Tuple[str, Tuple[Tuple[str, int, int], ...]]:
    files = []
    for root in paths:
        if not root.exists():
            continue
        if root.is_file():
            files.append(root)
            continue
        files.extend(sorted(p for p in root.rglob("*") if p.is_file()))
    digest = hashlib.sha256()
    meta = []
    for path in files:
        data = path.read_bytes()
        digest.update(path.as_posix().encode("utf-8"))
        digest.update(data)
        stat = path.stat()
        meta.append((path.relative_to(REPO_ROOT).as_posix(), stat.st_size, stat.st_mtime_ns))
    return digest.hexdigest(), tuple(meta)


def _protected_fingerprint() -> Tuple[str, Tuple[Tuple[str, int, int], ...]]:
    return _catalog_fingerprint((STRATEGIES_DIR, SKILLS_DIR))


def _service(tmp_path: Path) -> AgentPromotionService:
    return AgentPromotionService(tmp_path / "agent_evolve", clock=FIXED_NOW)


def _module_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_library_does_not_import_activation_or_event_surfaces() -> None:
    names = _module_imports(PROMOTION_CLI_PATH)
    forbidden_prefixes = (
        "src.agent.skills.router",
        "src.agent.orchestrator",
        "src.agent.executor",
        "src.repositories.agent_evolution_event_repo",
        "src.schemas.evolution_event",
    )
    for prefix in forbidden_prefixes:
        assert all(not item.startswith(prefix) for item in names), names
    source = PROMOTION_CLI_PATH.read_text(encoding="utf-8")
    assert "EVOLUTION_AUTO_PROMOTE_SKILLS" not in source


def test_propose_from_seeded_fixture_writes_sidecar_without_catalog_mutation(
    tmp_path: Path,
) -> None:
    before_soul = snapshot_soul_identity()
    before_catalog = _protected_fingerprint()
    before_defaults = tuple(DEFAULT_ROUTER_SKILL_IDS)
    service = _service(tmp_path)

    result = service.propose(fixture=SEEDED_FIXTURE)
    payload = result.proposal
    proposal_id = payload["proposal_id"]
    sidecar = tmp_path / "agent_evolve" / f"{proposal_id}.json"

    assert result.idempotent is False
    assert sidecar.is_file()
    assert payload["review_state"] == "proposed"
    assert payload["candidate"]["kind"] == "experimental_skill_id"
    assert payload["candidate"]["source"]["case_id"] == "pred-seeded-miss-lesson"
    assert payload["promotion_receipt"]["auto_promote"] is False
    assert payload["promotion_receipt"]["review_required"] is True
    assert SANDBOX_ISOLATION_POLICY["auto_promote_to_production"] is False
    assert not (STRATEGIES_DIR / "experimental").exists()
    assert not (REPO_ROOT / "skills" / "experimental").exists()
    assert _protected_fingerprint() == before_catalog
    assert tuple(DEFAULT_ROUTER_SKILL_IDS) == before_defaults
    assert_soul_unchanged(before_soul)

    again = service.propose(fixture=SEEDED_FIXTURE)
    assert again.idempotent is True
    assert again.proposal["proposal_id"] == proposal_id
    assert again.proposal["review_state"] == "proposed"


def test_score_reuses_offline_eval_and_does_not_start_live_agent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*args, **kwargs):
        raise AssertionError("live agent path must not run")

    monkeypatch.setattr(
        "src.agent.skills.router.SkillRouter.select_skills",
        _boom,
    )
    monkeypatch.setattr(
        "src.agent.orchestrator.AgentOrchestrator.__init__",
        _boom,
    )

    service = _service(tmp_path)
    proposed = service.propose(fixture=SEEDED_FIXTURE)
    scored = service.score(proposed.proposal["proposal_id"])
    scores = scored.proposal["eval_scores"]

    assert scored.proposal["review_state"] == "scored"
    assert scores["live_agent_run"] is False
    assert scores["schema_version"] == "prediction-eval-v1"
    assert scores["case"]["case_id"] == "pred-seeded-miss-lesson"
    assert scores["case"]["total"] > 0
    assert scores["case"]["passed"] == scores["case"]["total"]


def test_approve_is_sidecar_only_and_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*args, **kwargs):
        raise AssertionError("SkillRouter must not run during approve")

    monkeypatch.setattr("src.agent.skills.router.SkillRouter.select_skills", _boom)
    before_catalog = _protected_fingerprint()
    before_soul = snapshot_soul_identity()
    service = _service(tmp_path)
    proposal_id = service.propose(fixture=SEEDED_FIXTURE).proposal["proposal_id"]
    service.score(proposal_id)

    first = service.approve(proposal_id)
    second = service.approve(proposal_id)
    receipt = first.proposal["promotion_receipt"]

    assert first.idempotent is False
    assert second.idempotent is True
    assert first.proposal["review_state"] == "approved"
    assert second.proposal["review_state"] == "approved"
    assert receipt["auto_promote"] is False
    assert receipt["review_required"] is True
    assert SANDBOX_ISOLATION_POLICY["auto_promote_to_production"] is False
    assert "experimental:" not in json.dumps(DEFAULT_ROUTER_SKILL_IDS)
    assert first.proposal["candidate"]["experimental_id"] not in DEFAULT_ROUTER_SKILL_IDS
    assert _protected_fingerprint() == before_catalog
    assert_soul_unchanged(before_soul)
    assert REVIEW_NOTE in first.proposal["review"]["note"]


def test_approve_unscored_proposal_fails_closed(tmp_path: Path) -> None:
    service = _service(tmp_path)
    proposal_id = service.propose(fixture=SEEDED_FIXTURE).proposal["proposal_id"]
    with pytest.raises(PromotionProposalError, match="requires a scored proposal"):
        service.approve(proposal_id)
    stored = json.loads((tmp_path / "agent_evolve" / f"{proposal_id}.json").read_text())
    assert stored["review_state"] == "proposed"


def test_missing_proposal_fails_without_creating_sidecar(tmp_path: Path) -> None:
    service = _service(tmp_path)
    missing = "promo-0123456789abcdef"
    with pytest.raises(PromotionProposalError, match="proposal not found"):
        service.score(missing)
    with pytest.raises(PromotionProposalError, match="proposal not found"):
        service.approve(missing)
    with pytest.raises(PromotionProposalError, match="proposal not found"):
        service.reject(missing)
    with pytest.raises(PromotionProposalError, match="proposal not found"):
        service.status(missing)
    assert list((tmp_path / "agent_evolve").glob("promo-*.json")) == []


def test_invalid_inputs_fail_closed(tmp_path: Path) -> None:
    service = _service(tmp_path)
    with pytest.raises(PromotionProposalError, match="exactly one"):
        service.propose()
    with pytest.raises(PromotionProposalError, match="not a file"):
        service.propose(fixture=tmp_path / "missing.json")
    with pytest.raises(PromotionProposalError, match="invalid proposal_id"):
        service.score("not-a-proposal")
    with pytest.raises(PromotionProposalError, match="unsupported candidate kind"):
        service.propose(fixture=SEEDED_FIXTURE, candidate_kind="production_skill")
    with pytest.raises(PromotionProposalError, match="must not be inside strategies"):
        AgentPromotionService(STRATEGIES_DIR / "agent_evolve")
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "EVOLUTION_AUTO_PROMOTE_SKILLS" not in env_example


def test_tampered_auto_promote_receipt_is_rejected(tmp_path: Path) -> None:
    service = _service(tmp_path)
    proposal_id = service.propose(fixture=SEEDED_FIXTURE).proposal["proposal_id"]
    path = tmp_path / "agent_evolve" / f"{proposal_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["promotion_receipt"]["auto_promote"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PromotionProposalError, match="auto_promote must remain false"):
        service.score(proposal_id)
    with pytest.raises(PromotionProposalError, match="auto_promote must remain false"):
        service.approve(proposal_id)
    assert json.loads(path.read_text(encoding="utf-8"))["review_state"] == "proposed"


def test_reject_is_idempotent_and_blocks_later_approve(tmp_path: Path) -> None:
    service = _service(tmp_path)
    proposal_id = service.propose(fixture=SEEDED_FIXTURE).proposal["proposal_id"]
    service.score(proposal_id)
    first = service.reject(proposal_id)
    second = service.reject(proposal_id)
    assert first.proposal["review_state"] == "rejected"
    assert second.idempotent is True
    with pytest.raises(PromotionProposalError, match="already rejected"):
        service.approve(proposal_id)
    assert first.proposal["promotion_receipt"]["auto_promote"] is False


def test_score_write_failure_leaves_proposed_sidecar(tmp_path: Path) -> None:
    store = tmp_path / "agent_evolve"
    service = AgentPromotionService(store, clock=FIXED_NOW)
    proposal_id = service.propose(fixture=SEEDED_FIXTURE).proposal["proposal_id"]
    sidecar = store / f"{proposal_id}.json"
    before = sidecar.read_text(encoding="utf-8")
    os.chmod(store, 0o555)
    try:
        with pytest.raises(OSError):
            service.score(proposal_id)
    finally:
        os.chmod(store, 0o755)
    after = json.loads(sidecar.read_text(encoding="utf-8"))
    assert sidecar.read_text(encoding="utf-8") == before
    assert after["review_state"] == "proposed"
    assert after["eval_scores"] is None


def test_status_lists_review_state(tmp_path: Path) -> None:
    service = _service(tmp_path)
    proposal_id = service.propose(fixture=SEEDED_FIXTURE).proposal["proposal_id"]
    listed = service.status()
    assert listed["count"] == 1
    assert listed["proposals"][0]["proposal_id"] == proposal_id
    assert listed["proposals"][0]["review_state"] == "proposed"
    assert listed["proposals"][0]["auto_promote"] is False
    one = service.status(proposal_id)
    assert one["proposals"][0]["review_note"] == REVIEW_NOTE


def test_cli_propose_score_approve_roundtrip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store = tmp_path / "sidecar"
    code = evolve_cli.main(
        ["--store-dir", str(store), "propose", "--fixture", str(SEEDED_FIXTURE)]
    )
    propose_out = json.loads(capsys.readouterr().out)
    assert code == 0
    proposal_id = propose_out["proposal_id"]
    assert propose_out["operation"] == "propose"

    assert evolve_cli.main(["--store-dir", str(store), "score", "--proposal-id", proposal_id]) == 0
    capsys.readouterr()
    assert evolve_cli.main(["--store-dir", str(store), "status", "--proposal-id", proposal_id]) == 0
    status_out = json.loads(capsys.readouterr().out)
    assert status_out["proposals"][0]["review_state"] == "scored"

    assert evolve_cli.main(["--store-dir", str(store), "approve", "--proposal-id", proposal_id]) == 0
    approve_out = json.loads(capsys.readouterr().out)
    assert approve_out["review_state"] == "approved"
    assert approve_out["promotion_receipt"]["auto_promote"] is False
    assert evolve_cli.main(["--store-dir", str(store), "approve", "--proposal-id", proposal_id]) == 0
    again = json.loads(capsys.readouterr().out)
    assert again["idempotent"] is True


def test_cli_invalid_and_missing_exit_nonzero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store = tmp_path / "sidecar"
    assert evolve_cli.main(["--store-dir", str(store), "score", "--proposal-id", "promo-0123456789abcdef"]) == 2
    err = capsys.readouterr().err
    assert "proposal not found" in err
    assert evolve_cli.main(["--store-dir", str(STRATEGIES_DIR), "status"]) == 2
    assert "must not be inside strategies" in capsys.readouterr().err


def test_episode_lessons_propose_path(tmp_path: Path) -> None:
    episodes = tmp_path / "episodes.json"
    episodes.write_text(
        json.dumps(
            [
                {
                    "run_id": "run-ep-1",
                    "lessons": [
                        {
                            "kind": "overconfidence",
                            "severity": "low",
                            "remedy": "Need more evidence.",
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    result = _service(tmp_path).propose(episodes=episodes)
    assert result.proposal["candidate"]["source"]["type"] == "episode_lessons"
    assert result.proposal["promotion_receipt"]["auto_promote"] is False
