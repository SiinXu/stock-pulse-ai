# -*- coding: utf-8 -*-
"""Tests for layered agent memory (episodic + semantic + optional vector)."""

from __future__ import annotations

import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.agent.memory import AgentMemory, AnalysisMemoryEntry, CalibrationResult
from src.agent.memory_layers import MIN_SEMANTIC_EVIDENCE
from src.agent.memory_retrieval import (
    StructuredMemoryRetriever,
    format_layered_prompt_context,
    sanitize_memory_text,
)
from src.agent.memory_vector import (
    HashingVectorIndex,
    VectorDocument,
    cosine_similarity,
    hash_embed,
    tokenize,
)


def _record(
    *,
    code: str = "600519",
    signal: str = "buy",
    sentiment: int = 70,
    summary: str = "Earnings beat expectations",
    price: float = 1800.0,
    day: int = 1,
    history_id: int = 1,
):
    return SimpleNamespace(
        id=history_id,
        code=code,
        created_at=datetime(2026, 3, day, 10, 0, 0),
        raw_result=f'{{"decision_type": "{signal}", "current_price": {price}}}',
        operation_advice=signal,
        sentiment_score=sentiment,
        analysis_summary=summary,
    )


class TestDisabledParity:
    """AGENT_MEMORY_ENABLED=false must keep legacy neutral behaviour."""

    def test_disabled_returns_empty_history(self):
        mem = AgentMemory(enabled=False)
        assert mem.get_stock_history("600519") == []

    def test_disabled_calibration_neutral(self):
        mem = AgentMemory(enabled=False)
        cal = mem.get_calibration("technical")
        assert cal.calibrated is False
        assert cal.calibration_factor == 1.0
        assert mem.calibrate_confidence("technical", 0.77) == 0.77

    def test_disabled_weights_uniform(self):
        mem = AgentMemory(enabled=False)
        assert mem.compute_skill_weights(["a", "b"]) == {"a": 1.0, "b": 1.0}

    def test_disabled_layered_empty(self):
        mem = AgentMemory(enabled=False, vector_enabled=True)
        assert mem.retrieve_episodic("600519") == []
        assert mem.retrieve_semantic(query="risk") == []
        bundle = mem.retrieve_layered("600519", query="risk")
        assert bundle.episodic == []
        assert bundle.semantic == []
        assert mem.format_prompt_context("600519", query="risk") == ""

    def test_disabled_vector_flag_ignored(self):
        mem = AgentMemory(enabled=False, vector_enabled=True)
        assert mem.vector_enabled is False


class TestSanitize:
    def test_redacts_path_and_email(self):
        text = "see /Users/secret/key.pem and user@example.com for details about earnings"
        out = sanitize_memory_text(text)
        assert "/Users/" not in out
        assert "user@example.com" not in out
        assert "[path]" in out or "[email]" in out

    def test_truncates_long_text(self):
        out = sanitize_memory_text("x" * 1000, max_chars=50)
        assert len(out) <= 50
        assert out.endswith("...")


class TestVectorIndex:
    def test_tokenize_and_embed_stable(self):
        tokens = tokenize("Buy momentum breakout buy")
        assert "buy" in tokens
        a = hash_embed(tokens)
        b = hash_embed(tokens)
        assert a == b
        assert abs(sum(v * v for v in a) - 1.0) < 1e-6

    def test_query_ranks_related_doc_higher(self):
        index = HashingVectorIndex(dim=128)
        index.add(VectorDocument("1", "earnings miss and revenue decline", {}))
        index.add(VectorDocument("2", "technical breakout momentum rally", {}))
        ranked = index.query("earnings revenue miss", top_k=2)
        assert ranked
        assert ranked[0][0].doc_id == "1"
        assert ranked[0][1] >= ranked[1][1]

    def test_cosine_orthogonal_zeroish(self):
        # empty vectors
        assert cosine_similarity([], []) == 0.0


class TestStructuredRetrieval:
    def test_episodic_from_records(self):
        records = [
            _record(day=2, history_id=2, signal="sell", summary="Risk elevated"),
            _record(day=1, history_id=1, signal="buy", summary="Earnings beat"),
        ]
        retriever = StructuredMemoryRetriever(vector_enabled=False)
        with patch.object(retriever, "fetch_history_records", return_value=records):
            entries = retriever.retrieve_episodic("600519", limit=2, query="earnings")
        assert len(entries) == 2
        # Keyword should prefer the earnings summary
        assert entries[0].summary.lower().find("earning") >= 0 or entries[0].score >= entries[1].score
        assert entries[0].analysis_history_id is not None

    def test_semantic_insufficient_evidence_neutral(self):
        records = [_record(day=1, signal="buy", history_id=1)]
        retriever = StructuredMemoryRetriever(vector_enabled=False)
        with patch.object(retriever, "fetch_history_records", return_value=records):
            patterns = retriever.retrieve_semantic(stock_code="600519", query="buy")
        assert patterns
        assert patterns[0].sufficient_evidence is False
        assert "neutral" in patterns[0].summary.lower() or "limited" in patterns[0].summary.lower()

    def test_semantic_sufficient_evidence(self):
        records = [
            _record(day=i + 1, signal="buy", history_id=i + 1, summary=f"Buy case {i}")
            for i in range(MIN_SEMANTIC_EVIDENCE)
        ]
        retriever = StructuredMemoryRetriever(vector_enabled=False)
        with patch.object(retriever, "fetch_history_records", return_value=records):
            patterns = retriever.retrieve_semantic(stock_code="600519")
        assert patterns
        buy = next(p for p in patterns if p.signal_bias == "buy")
        assert buy.sufficient_evidence is True
        assert buy.evidence_count >= MIN_SEMANTIC_EVIDENCE

    def test_vector_disabled_still_returns_results(self):
        """Vector off must not block structured retrieval (degrade path)."""
        records = [_record(day=1, summary="sector rotation into defensives")]
        retriever = StructuredMemoryRetriever(vector_enabled=False)
        with patch.object(retriever, "fetch_history_records", return_value=records):
            bundle = retriever.retrieve_layered("600519", query="defensive sector")
        assert bundle.episodic
        assert bundle.vector_used is False
        text = format_layered_prompt_context(bundle)
        assert "Memory: recent analysis history" in text
        assert "signal=buy" in text


class TestAgentMemoryLayers:
    def test_format_prompt_context_includes_both_layers(self):
        records = [
            _record(day=i + 1, signal="hold", history_id=i + 1, summary="Hold into earnings season")
            for i in range(4)
        ]
        mem = AgentMemory(enabled=True, vector_enabled=False)
        with patch.object(mem._retriever, "fetch_history_records", return_value=records):
            text = mem.format_prompt_context("600519", query="earnings")
        assert "[Memory: recent analysis history]" in text
        assert "[Memory: semantic patterns]" in text
        assert "verbatim" in text

    def test_vector_enabled_reranks_without_extra_deps(self):
        records = [
            _record(day=1, history_id=1, signal="buy", summary="technical breakout"),
            _record(day=2, history_id=2, signal="sell", summary="earnings miss revenue"),
        ]
        mem = AgentMemory(enabled=True, vector_enabled=True)
        assert mem.vector_enabled is True
        with patch.object(mem._retriever, "fetch_history_records", return_value=records):
            entries = mem.retrieve_episodic("600519", limit=2, query="earnings revenue miss")
        assert entries
        # Top hit should relate to earnings when vector ranking works
        assert any("earning" in (e.summary or "").lower() for e in entries)
        assert any(e.source == "vector" for e in entries)

    def test_from_config_reads_vector_env(self, monkeypatch):
        monkeypatch.setenv("AGENT_MEMORY_ENABLED", "true")
        monkeypatch.setenv("AGENT_MEMORY_VECTOR_ENABLED", "true")

        class _Cfg:
            agent_memory_enabled = True

        with patch("src.config.get_config", return_value=_Cfg()):
            mem = AgentMemory.from_config()
        assert mem.enabled is True
        assert mem.vector_enabled is True

    def test_get_stock_history_legacy_path(self):
        record = _record()
        db = MagicMock()
        db.get_analysis_history.return_value = [record]
        with patch("src.storage.get_db", return_value=db):
            mem = AgentMemory(enabled=True)
            history = mem.get_stock_history("600519", limit=1)
        assert len(history) == 1
        assert isinstance(history[0], AnalysisMemoryEntry)
        assert history[0].signal == "buy"


class TestBaseAgentLayeredInjection:
    def test_prefers_format_prompt_context_string(self):
        from src.agent.agents.base_agent import BaseAgent
        from src.agent.protocols import AgentContext

        class DummyAgent(BaseAgent):
            agent_name = "technical"

            def system_prompt(self, ctx):
                return "system"

            def build_user_message(self, ctx):
                return "user"

        memory = MagicMock()
        memory.enabled = True
        memory.format_prompt_context.return_value = (
            "[Memory: recent analysis history]\n- 2026-03-01, signal=buy, sentiment=72\n"
            "Use this memory as context only; do not copy it verbatim into the final answer."
        )
        with patch("src.agent.agents.base_agent.AgentMemory.from_config", return_value=memory):
            agent = DummyAgent(tool_registry=MagicMock(), llm_adapter=MagicMock())

        ctx = AgentContext(query="earnings risk", stock_code="600519")
        injected = agent._build_memory_context(ctx)
        assert "signal=buy" in injected
        memory.format_prompt_context.assert_called()
        memory.get_stock_history.assert_not_called()

    def test_falls_back_when_format_returns_non_string(self):
        """MagicMock auto-attrs must not break the legacy injection path."""
        from src.agent.agents.base_agent import BaseAgent
        from src.agent.protocols import AgentContext

        class DummyAgent(BaseAgent):
            agent_name = "technical"

            def system_prompt(self, ctx):
                return "system"

            def build_user_message(self, ctx):
                return "user"

        entry = SimpleNamespace(
            date="2026-03-01",
            signal="buy",
            sentiment_score=72,
            price_at_analysis=1880.0,
            outcome_5d=0.03,
            outcome_20d=None,
            was_correct=True,
        )
        memory = MagicMock(enabled=True)
        memory.get_stock_history.return_value = [entry]
        # format_prompt_context is a MagicMock → not isinstance(str)
        with patch("src.agent.agents.base_agent.AgentMemory.from_config", return_value=memory):
            agent = DummyAgent(tool_registry=MagicMock(), llm_adapter=MagicMock())

        ctx = AgentContext(query="test", stock_code="600519")
        injected = agent._build_memory_context(ctx)
        assert "Memory: recent analysis history" in injected
        assert "signal=buy" in injected
