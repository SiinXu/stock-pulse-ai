"""Adversarial isolation tests for untrusted memory prompt data."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.agent.memory_isolation import (
    assert_untrusted_isolation,
    isolate_layered_memory_for_prompt,
    iter_adversarial_memory_payloads,
    sanitize_untrusted_memory_text,
)
from src.agent.memory_layers import MemoryObservation
from src.agent.memory_retrieval import AuthorizedMemoryProjector

_BASE = datetime(2026, 8, 1, tzinfo=timezone.utc)
AS_OF = "2026-08-09T00:00:00Z"


def _instant(offset_minutes: int) -> str:
    return (_BASE + timedelta(minutes=offset_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record(index: int) -> MemoryObservation:
    return MemoryObservation(
        principal_id="alice",
        analysis_history_id=index,
        stock_code="600519",
        observed_at=_instant(index),
        expires_at=None,
        signal="buy",
        sentiment_score=60,
        price_at_analysis=100.0,
    )


def test_isolate_wraps_structured_bundle_as_untrusted_data() -> None:
    bundle = AuthorizedMemoryProjector(
        [_record(1)], principal_id="alice", as_of=AS_OF,
    ).retrieve_layered(stock_code="600519")
    rendered = isolate_layered_memory_for_prompt(bundle)
    assert_untrusted_isolation(rendered)
    assert "[NON_AUTHORITATIVE_MEMORY_DATA]" in rendered
    assert "outcome_patterns" in rendered


def test_adversarial_freeform_control_sequences_are_redacted() -> None:
    for payload in iter_adversarial_memory_payloads():
        cleaned = sanitize_untrusted_memory_text(payload)
        lowered = cleaned.lower()
        assert "system:" not in lowered
        assert "[inst]" not in lowered
        assert "<<sys>>" not in lowered
        assert "\x00" not in cleaned
        if "ignore all prior" in payload.lower() or "disregard previous" in payload.lower():
            assert "[redacted_control]" in lowered


def test_adversarial_strings_cannot_enter_structured_projection_fields() -> None:
    for payload in iter_adversarial_memory_payloads():
        with pytest.raises(ValueError):
            MemoryObservation(payload[:80] if payload else "x", 1, "600519", _instant(1), None, "buy", 50, 100)
        with pytest.raises(ValueError):
            MemoryObservation("alice", 1, payload[:20] if payload else "x", _instant(1), None, "buy", 50, 100)
        with pytest.raises(ValueError):
            MemoryObservation("alice", 1, "600519", payload if "T" in payload else "not-a-timestamp", None, "buy", 50, 100)


def test_assert_untrusted_isolation_rejects_bare_json() -> None:
    with pytest.raises(ValueError):
        assert_untrusted_isolation('{"principal_id":"alice"}')
    with pytest.raises(ValueError):
        assert_untrusted_isolation("")
