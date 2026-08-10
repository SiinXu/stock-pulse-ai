# -*- coding: utf-8 -*-
"""What-if isolation and marker contracts (Issue #130 / T27)."""
from __future__ import annotations
import os, sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from sqlalchemy import func, select
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.agent.chat_context import build_agent_chat_market_context
from src.agent.executor import AgentExecutor, AgentResult
from src.agent.tools.registry import ToolRegistry
from src.agent.what_if_scenario import (
    DEFAULT_WHAT_IF_MAX_TURNS, HYPOTHETICAL_ASSUMPTION_MARKER, HYPOTHETICAL_RESULT_MARKER,
    build_what_if_prompt_section, content_has_hypothetical_marker, count_what_if_turns_in_messages,
    get_what_if_isolation_policy, is_what_if_turn_allowed, parse_what_if_from_context,
)
from src.config import Config
from src.storage import AnalysisHistory, DatabaseManager, DecisionSignalRecord
from src.storage_parts.schema import DecisionSignalMemoryFlagRecord

def teardown_function():
    DatabaseManager.reset_instance(); Config.reset_instance()

def _payload(**o):
    b={"enabled":True,"turn_index":1,"max_turns":DEFAULT_WHAT_IF_MAX_TURNS,"assumptions":[{"dimension":"interest_rate","direction":"down","magnitude":50}]}
    b.update(o); return b

def test_parse_structured():
    s=parse_what_if_from_context({"what_if":_payload()}); assert s and s.is_active and s.assumptions[0].magnitude==50.0

def test_reject_free_text():
    assert parse_what_if_from_context({"what_if":{"text":"x"}}) is None
    assert parse_what_if_from_context({"what_if":{"assumptions":[{"dimension":"free_text"}]}}) is None

def test_markers():
    s=parse_what_if_from_context({"what_if":_payload()}); assert s
    zh=build_what_if_prompt_section(s,"zh"); en=build_what_if_prompt_section(s,"en")
    for section in (zh,en):
        assert HYPOTHETICAL_ASSUMPTION_MARKER in section and HYPOTHETICAL_RESULT_MARKER in section and "preview_only" in section
    assert "协同推演预览，不改变系统最终建议" in zh
    assert "does not change the system's final recommendation" in en

def test_market_inject():
    m=build_agent_chat_market_context({"stock_code":"600519","what_if":_payload()}, report_language="zh")
    assert HYPOTHETICAL_ASSUMPTION_MARKER in m.prompt_section

def test_market_inject_no_stock():
    m=build_agent_chat_market_context({"what_if":_payload()}, report_language="en")
    assert HYPOTHETICAL_ASSUMPTION_MARKER in m.prompt_section

def test_turn_limit():
    s=parse_what_if_from_context({"what_if":_payload(max_turns=2)}); assert s
    assert is_what_if_turn_allowed(s, prior_turn_count=1) and not is_what_if_turn_allowed(s, prior_turn_count=2)
    assert count_what_if_turns_in_messages([{"role":"user","content":HYPOTHETICAL_ASSUMPTION_MARKER+" x"}])==1
    assert "limit" in build_what_if_prompt_section(s,"en",prior_turn_count=2).lower()

def test_isolation_policy():
    p=get_what_if_isolation_policy()
    assert p["mode"]=="preview_only" and p["persist_analysis_history"] is False and p["persist_decision_signal"] is False and p["persist_agent_memory"] is False

def test_marker_detect():
    assert content_has_hypothetical_marker(HYPOTHETICAL_RESULT_MARKER+" x")
    assert not content_has_hypothetical_marker("normal")

def _counts(db):
    with db.session_scope() as s:
        return {
            "a": int(s.scalar(select(func.count()).select_from(AnalysisHistory)) or 0),
            "d": int(s.scalar(select(func.count()).select_from(DecisionSignalRecord)) or 0),
            "m": int(s.scalar(select(func.count()).select_from(DecisionSignalMemoryFlagRecord)) or 0),
        }

def test_what_if_chat_round_isolation():
    DatabaseManager.reset_instance(); Config.reset_instance()
    db=DatabaseManager(db_url="sqlite:///:memory:")
    before=_counts(db)
    registry=ToolRegistry(); adapter=MagicMock()
    adapter._config=SimpleNamespace(agent_context_compression_enabled=False, agent_context_compression_profile="balanced", agent_context_compression_trigger_tokens=999999, agent_context_protected_turns=1, llm_model_list=[], agent_litellm_model="openai/test-model", litellm_model="openai/test-model", litellm_fallback_models=[])
    executor=AgentExecutor(registry, adapter, max_steps=2)
    captured={}
    def fake_run_loop(messages, tool_decls, parse_dashboard, progress_callback=None, stock_scope=None, cancelled_check=None):
        captured["messages"]=messages; captured["parse_dashboard"]=parse_dashboard
        return AgentResult(success=True, content=f"{HYPOTHETICAL_RESULT_MARKER}\n协同推演预览，不改变系统最终建议.")
    with patch.object(executor, "_run_loop", side_effect=fake_run_loop):
        with patch("src.agent.executor_parts.chat.build_agent_chat_context_bundle", return_value=SimpleNamespace(context_messages=[], diagnostics={})):
            result=executor.chat("If Fed cuts 50bp?", "what-if-isolation-session", context={"stock_code":"600519","report_language":"zh","what_if":_payload()})
    assert result.success and captured["parse_dashboard"] is False
    joined="\n".join(str(m.get("content") or "") for m in captured["messages"] if isinstance(m, dict))
    assert HYPOTHETICAL_ASSUMPTION_MARKER in joined and content_has_hypothetical_marker(result.content)
    after=_counts(db)
    assert after==before=={"a":0,"d":0,"m":0}
    hist=db.get_conversation_history("what-if-isolation-session")
    assert any(r.get("role")=="user" for r in hist) and any(r.get("role")=="assistant" for r in hist)
