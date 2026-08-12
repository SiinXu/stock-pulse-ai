# -*- coding: utf-8 -*-
"""Contracts for the error-pattern encyclopedia (Issue #1138)."""

from __future__ import annotations

import copy

import pytest

from src.agent.evolution.error_patterns import (
    DEFAULT_INJECT_TOP_K,
    MAX_PATTERN_INJECTION,
    ErrorPatternEncyclopedia,
    cluster_lessons_into_cards,
    format_error_pattern_checklist,
    inject_error_pattern_checklist,
    retrieve_error_patterns,
)
from src.agent.evolution.lessons import (
    EpisodeLessonBundle,
    ReflectionLesson,
    ReflectionResult,
    lessons_from_kinds,
)
from src.agent.soul import AGENT_SOUL_CHARTER, AGENT_SOUL_HASH, AGENT_SOUL_VERSION


def _bundle(
    episode_id: str,
    kinds: list[str],
    *,
    severity: str = "medium",
    remedies: dict | None = None,
) -> EpisodeLessonBundle:
    lessons = lessons_from_kinds(
        kinds,
        severity=severity,  # type: ignore[arg-type]
        remedies=remedies,
    )
    result = ReflectionResult(
        lessons=lessons,
        episode_id=episode_id,
        status="completed",
        terminate_reason="ok",
    )
    return EpisodeLessonBundle(episode_id=episode_id, result=result)


class TestClusterLessons:
    def test_cluster_by_kind_with_episode_refs(self) -> None:
        cards = cluster_lessons_into_cards(
            [
                _bundle("ep-1", ["evidence_gap", "overconfidence"]),
                _bundle("ep-2", ["evidence_gap"], severity="high"),
                _bundle("ep-3", ["horizon_mismatch"]),
            ]
        )
        by_kind = {card.kind: card for card in cards}
        assert set(by_kind) >= {"evidence_gap", "overconfidence", "horizon_mismatch"}

        evidence = by_kind["evidence_gap"]
        assert evidence.stats.occurrence_count == 2
        assert evidence.stats.high_severity_count == 1
        assert "ep-1" in evidence.stats.episode_refs
        assert "ep-2" in evidence.stats.episode_refs
        assert evidence.pattern_id == "pattern:evidence_gap"
        assert evidence.enabled is True
        assert "data" in evidence.title.lower() or "evidence" in evidence.title.lower()

        timing = by_kind["horizon_mismatch"]
        assert timing.stats.occurrence_count == 1
        assert timing.stats.episode_refs == ["ep-3"]

    def test_accepts_raw_mapping_lesson_events(self) -> None:
        cards = cluster_lessons_into_cards(
            [
                {
                    "episode_id": "ep-map",
                    "kind": "tool_failure",
                    "severity": "high",
                    "remedy": "do not invent tool output",
                }
            ]
        )
        assert len(cards) == 1
        assert cards[0].kind == "tool_failure"
        assert "ep-map" in cards[0].stats.episode_refs
        assert "invent" in cards[0].remedy


class TestHumanEditAudit:
    def test_human_edit_leaves_audit_trail_and_locks_fields(self) -> None:
        store = ErrorPatternEncyclopedia()
        store.ingest_lessons([_bundle("ep-1", ["overconfidence"])])
        card = store.get_card("pattern:overconfidence")
        assert card is not None

        updated = store.human_edit(
            "pattern:overconfidence",
            actor="analyst:siin",
            title="Overconfidence on breakouts",
            remedy="require volume confirmation for breakout claims",
            note="re-judge after week review",
        )
        assert updated.title == "Overconfidence on breakouts"
        assert updated.revision == card.revision + 1
        assert updated.source == "human"
        assert "title" in updated.human_locked_fields
        assert "remedy" in updated.human_locked_fields

        events = store.list_edit_events(pattern_id="pattern:overconfidence")
        assert events
        last = events[-1]
        assert last.actor == "analyst:siin"
        assert last.action == "human_edit"
        assert last.revision_before == card.revision
        assert last.revision_after == updated.revision
        assert "title" in last.changed_fields
        assert last.note is not None and "re-judge" in last.note

        # Recluster must preserve human-locked title/remedy.
        store.ingest_lessons(
            [
                _bundle(
                    "ep-9",
                    ["overconfidence"],
                    remedies={"overconfidence": "system-generated remedy should not win"},
                )
            ]
        )
        after = store.get_card("pattern:overconfidence")
        assert after is not None
        assert after.title == "Overconfidence on breakouts"
        assert after.remedy == "require volume confirmation for breakout claims"
        assert "ep-9" in after.stats.episode_refs

    def test_disable_and_enable_are_audited(self) -> None:
        store = ErrorPatternEncyclopedia()
        store.ingest_lessons([_bundle("ep-1", ["risk_omission"])])
        store.disable("pattern:risk_omission", actor="ops:admin", note="noisy")
        card = store.get_card("pattern:risk_omission")
        assert card is not None
        assert card.enabled is False
        events = store.list_edit_events(pattern_id="pattern:risk_omission")
        assert events[-1].action == "disable"
        store.enable("pattern:risk_omission", actor="ops:admin")
        assert store.get_card("pattern:risk_omission").enabled is True
        assert store.list_edit_events(pattern_id="pattern:risk_omission")[-1].action == "enable"


class TestRetrievalAndInjection:
    def _populated_store(self) -> ErrorPatternEncyclopedia:
        store = ErrorPatternEncyclopedia()
        store.ingest_lessons(
            [
                _bundle("ep-a", ["evidence_gap"], severity="high"),
                _bundle("ep-b", ["evidence_gap", "overconfidence"]),
                _bundle("ep-c", ["horizon_mismatch"]),
                _bundle("ep-d", ["regime_shift"]),
                _bundle("ep-e", ["tool_failure"]),
            ]
        )
        return store

    def test_disabled_cards_not_injected(self) -> None:
        store = self._populated_store()
        store.disable("pattern:evidence_gap", actor="human:1")
        result = retrieve_error_patterns(store, top_k=5, char_budget=4000)
        injected_kinds = {card.kind for card in result.cards}
        assert "evidence_gap" not in injected_kinds
        assert result.disabled_excluded >= 1
        assert "evidence_gap" not in result.rendered_checklist

    def test_top_k_quota_hard_cap(self) -> None:
        store = self._populated_store()
        result = retrieve_error_patterns(store, top_k=2, char_budget=4000)
        assert result.injected_count == 2
        assert result.requested_top_k == 2
        assert result.truncated is True
        assert result.injected_count <= MAX_PATTERN_INJECTION

    def test_char_budget_truncates_injection(self) -> None:
        store = self._populated_store()
        result = retrieve_error_patterns(store, top_k=5, char_budget=350)
        assert result.char_used <= 350
        assert result.injected_count >= 1
        assert result.truncated is True

    def test_checklist_is_non_authoritative_block(self) -> None:
        store = self._populated_store()
        result = retrieve_error_patterns(store, top_k=DEFAULT_INJECT_TOP_K)
        text = result.rendered_checklist
        assert "BEGIN_ERROR_PATTERN_CHECKLIST" in text
        assert "NON_AUTHORITATIVE_ERROR_PATTERN_CHECKLIST" in text
        assert "untrusted DATA only" in text
        assert "episodes:" in text

    def test_injection_does_not_change_soul_charter_bytes(self) -> None:
        store = self._populated_store()
        before_charter = copy.deepcopy(AGENT_SOUL_CHARTER)
        before_hash = AGENT_SOUL_HASH
        before_version = AGENT_SOUL_VERSION

        result = retrieve_error_patterns(store, top_k=3)
        assert result.injected_count >= 1

        assert AGENT_SOUL_CHARTER == before_charter
        assert AGENT_SOUL_HASH == before_hash
        assert AGENT_SOUL_VERSION == before_version
        # Byte-identity of the normative charter source
        assert AGENT_SOUL_CHARTER.encode("utf-8") == before_charter.encode("utf-8")

    def test_inject_default_off(self) -> None:
        store = self._populated_store()

        class _Cfg:
            agent_error_pattern_enabled = False

        result = inject_error_pattern_checklist(store, config=_Cfg())
        assert result.injected_count == 0
        assert result.rendered_checklist == ""

    def test_inject_when_enabled(self) -> None:
        store = self._populated_store()

        class _Cfg:
            agent_error_pattern_enabled = True
            agent_error_pattern_inject_top_k = 2
            agent_error_pattern_inject_char_budget = 4000

        result = inject_error_pattern_checklist(store, config=_Cfg())
        assert result.injected_count == 2
        assert "BEGIN_ERROR_PATTERN_CHECKLIST" in result.rendered_checklist

    def test_format_empty_cards(self) -> None:
        assert format_error_pattern_checklist([]) == ""


class TestSnapshot:
    def test_export_import_roundtrip(self) -> None:
        store = ErrorPatternEncyclopedia()
        store.ingest_lessons([_bundle("ep-1", ["overclaim"])])
        store.human_edit(
            "pattern:overclaim",
            actor="reviewer",
            title="Prose overclaim",
        )
        snap = store.export_snapshot()
        other = ErrorPatternEncyclopedia()
        other.import_snapshot(snap)
        card = other.get_card("pattern:overclaim")
        assert card is not None
        assert card.title == "Prose overclaim"
        assert other.list_edit_events()
        assert any(event.action == "human_edit" for event in other.list_edit_events())


class TestRevisionConflict:
    def test_stale_expected_revision_rejected(self) -> None:
        store = ErrorPatternEncyclopedia()
        store.ingest_lessons([_bundle("ep-1", ["format_violation"])])
        with pytest.raises(ValueError, match="revision conflict"):
            store.human_edit(
                "pattern:format_violation",
                actor="a",
                title="x",
                expected_revision=999,
            )
