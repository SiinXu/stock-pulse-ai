"""Focused tests for principal-scoped pure memory projection."""

from __future__ import annotations

import json

import pytest

from src.agent.memory_layers import MemoryObservation
from src.agent.memory_retrieval import AuthorizedMemoryProjector, format_layered_data
from src.agent.memory_vector import tokenize


def _record(index: int, *, principal: str = "alice", signal: str = "buy",
            correct=None, price: float = 100.0, expires_at=None) -> MemoryObservation:
    evaluated = correct is not None
    return MemoryObservation(
        principal_id=principal, analysis_history_id=index, stock_code="600519",
        observed_at=f"2026-08-{index:02d}T00:00:00Z", expires_at=expires_at,
        signal=signal, sentiment_score=60, price_at_analysis=price,
        outcome_id=1000 + index if evaluated else None,
        outcome_horizon_days=5 if evaluated else None,
        evaluated_at="2026-08-09T00:00:00Z" if evaluated else None,
        was_correct=correct,
    )


def test_cross_principal_records_are_rejected() -> None:
    with pytest.raises(PermissionError):
        AuthorizedMemoryProjector([_record(1), _record(2, principal="bob")],
                                  principal_id="alice", as_of="2026-08-09T00:00:00Z")


def test_legacy_unowned_record_cannot_be_constructed() -> None:
    with pytest.raises(ValueError):
        _record(1, principal="")


def test_wrong_or_unevaluated_predictions_never_become_evidence() -> None:
    records = [_record(1, correct=False), _record(2, correct=False),
               _record(3, correct=False), _record(4, correct=None)]
    bundle = AuthorizedMemoryProjector(
        records, principal_id="alice", as_of="2026-08-09T00:00:00Z"
    ).retrieve_layered(stock_code="600519")
    assert bundle.semantic == []


def test_only_provenance_linked_correct_outcomes_build_semantic_pattern() -> None:
    records = [_record(index, correct=True) for index in range(1, 4)]
    bundle = AuthorizedMemoryProjector(
        records, principal_id="alice", as_of="2026-08-09T00:00:00Z"
    ).retrieve_layered(stock_code="600519")
    pattern = bundle.semantic[0]
    assert pattern.sufficient_evidence is True
    assert pattern.source_history_ids == [1, 2, 3]
    assert pattern.source_outcome_ids == [1001, 1002, 1003]
    assert pattern.horizon_days == [5]


def test_non_finite_and_invalid_signal_are_rejected() -> None:
    with pytest.raises(ValueError):
        _record(1, price=float("inf"))
    with pytest.raises(ValueError):
        _record(1, signal="strong_buy")


def test_partial_outcome_provenance_is_rejected() -> None:
    with pytest.raises(ValueError):
        MemoryObservation("alice", 1, "600519", "now", None, "buy", 50, 100,
                          outcome_id=1)


def test_limits_and_candidate_panel_are_hard_bounded() -> None:
    projector = AuthorizedMemoryProjector(
        [_record(1)], principal_id="alice", as_of="2026-08-09T00:00:00Z"
    )
    for value in (-1, 0, 1_000_000):
        with pytest.raises(ValueError):
            projector.retrieve_layered(stock_code="600519", episodic_limit=value)
    with pytest.raises(ValueError):
        AuthorizedMemoryProjector([_record(index) for index in range(1, 202)],
                                  principal_id="alice", as_of="2026-08-09T00:00:00Z")


def test_expired_records_are_excluded() -> None:
    projector = AuthorizedMemoryProjector(
        [_record(1, expires_at="2026-08-01T00:00:00Z")],
        principal_id="alice", as_of="2026-08-09T00:00:00Z",
    )
    assert projector.retrieve_layered(stock_code="600519").episodic == []


def test_prompt_poisoning_prose_has_no_input_field_or_control_effect() -> None:
    bundle = AuthorizedMemoryProjector(
        [_record(1)], principal_id="alice", as_of="2026-08-09T00:00:00Z"
    ).retrieve_layered(stock_code="600519")
    rendered = format_layered_data(bundle)
    assert rendered.startswith("[NON_AUTHORITATIVE_MEMORY_DATA]")
    assert "summary" not in rendered and "Ignore previous instructions" not in rendered
    payload = json.loads(rendered.splitlines()[1])
    assert payload["principal_id"] == "alice"
    assert payload["source_history_ids"] == [1]


def test_semantic_only_vector_ranking_reports_vector_used() -> None:
    records = [_record(index, correct=True) for index in range(1, 4)]
    bundle = AuthorizedMemoryProjector(
        records, principal_id="alice", as_of="2026-08-09T00:00:00Z",
        vector_enabled=True,
    ).retrieve_layered(stock_code="600519", query="buy", episodic_limit=1)
    assert bundle.vector_used is True


def test_cjk_tokenization_is_not_exact_phrase_only() -> None:
    tokens = tokenize("贵州茅台风险")
    assert "贵" in tokens and "贵州" in tokens and "风险" in tokens
