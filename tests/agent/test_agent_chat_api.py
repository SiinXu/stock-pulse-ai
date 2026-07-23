# -*- coding: utf-8 -*-
"""Agent chat history API regressions."""

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from api.app import create_app
from src.agent.chat_context import build_agent_chat_market_context
from src.agent.orchestrator import AgentOrchestrator, OrchestratorResult
from src.agent.public_contract import (
    AGENT_CHAT_FAILED,
    AGENT_CHAT_FAILURE_HISTORY_SENTINEL,
    AGENT_CHAT_FAILURE_MESSAGE,
)
from src.agent.runtime.guards import RuntimeGuardPolicy
from src.agent.stock_scope import resolve_stock_scope
from src.agent.tools.registry import ToolRegistry
from src.config import Config
from src.storage import DatabaseManager


SENSITIVE_PROVIDER_ERROR = (
    "provider rejected token=super-secret api_key=super-secret "
    "x-api-key: super-secret credential=super-secret at "
    "https://private.example/v1/chat?token=super-secret"
)
SENSITIVE_STREAM_SESSION_ID = "api_key=sk-sec2-stream-session-1234567890"


def _build_all_unavailable_comparison_result() -> OrchestratorResult:
    orchestrator = AgentOrchestrator(
        tool_registry=ToolRegistry(),
        llm_adapter=MagicMock(),
        config=SimpleNamespace(agent_orchestrator_timeout_s=60),
        runtime_guard_policy=RuntimeGuardPolicy(),
    )
    scope = resolve_stock_scope("compare AAPL and HK00700", None).stock_scope
    market_context = build_agent_chat_market_context(
        {},
        scope,
        "en",
        per_symbol_tool_scopes=True,
    )
    return orchestrator._synthesize_multi_symbol_chat(
        message="compare AAPL and HK00700",
        market_context=market_context,
        report_language="en",
        per_symbol_results=[
            (
                "AAPL",
                OrchestratorResult(success=False, error="US quote unavailable"),
            ),
            (
                "HK00700",
                OrchestratorResult(success=False, error="HK quote unavailable"),
            ),
        ],
        cancelled_check=None,
        timeout_seconds=0,
    )


def teardown_function() -> None:
    DatabaseManager.reset_instance()
    Config.reset_instance()


def test_deprecated_agent_chat_failure_history_message_remains_importable() -> None:
    from src.agent.public_contract import AGENT_CHAT_FAILURE_HISTORY_MESSAGE

    assert AGENT_CHAT_FAILURE_HISTORY_MESSAGE == "[分析失败] Agent chat failed"


def test_chat_session_messages_api_does_not_expose_provider_trace(tmp_path: Path) -> None:
    DatabaseManager.reset_instance()
    Config.reset_instance()
    db = DatabaseManager(db_url=f"sqlite:///{tmp_path / 'trace.db'}")
    session_id = "api-trace-hidden"
    user_id = db.save_conversation_message(session_id, "user", "visible question")
    assistant_id = db.save_conversation_message(session_id, "assistant", "visible answer")
    db.save_conversation_message(
        session_id,
        "assistant",
        f"[分析失败] {SENSITIVE_PROVIDER_ERROR}",
    )
    db.save_conversation_message(
        session_id,
        "assistant",
        AGENT_CHAT_FAILURE_HISTORY_SENTINEL,
    )
    db.save_agent_provider_turn(
        session_id=session_id,
        run_id="run-hidden",
        provider="deepseek",
        model="deepseek/deepseek-chat",
        anchor_user_message_id=user_id,
        anchor_assistant_message_id=assistant_id,
        messages=[
            {
                "role": "assistant",
                "content": "checking",
                "reasoning_content": "SECRET_REASONING",
                "tool_calls": [{"id": "call_1", "name": "echo", "arguments": {}}],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "SECRET_TOOL_RESULT"},
        ],
        contains_reasoning=True,
        contains_tool_calls=True,
        contains_thinking_blocks=False,
        must_roundtrip=True,
        estimated_tokens=10,
    )

    assert db.get_conversation_history(session_id)[-1] == {
        "role": "assistant",
        "content": AGENT_CHAT_FAILURE_MESSAGE,
    }
    assert db.get_visible_conversation_messages(session_id)[-1]["content"] == AGENT_CHAT_FAILURE_MESSAGE

    with patch("api.middlewares.auth.is_auth_enabled", return_value=False):
        client = TestClient(create_app(static_dir=tmp_path / "static"))
        response = client.get(f"/api/v1/agent/chat/sessions/{session_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == session_id
    assert [(msg["role"], msg["content"]) for msg in payload["messages"]] == [
        ("user", "visible question"),
        ("assistant", "visible answer"),
        ("assistant", AGENT_CHAT_FAILURE_MESSAGE),
        ("assistant", AGENT_CHAT_FAILURE_MESSAGE),
    ]
    assert "error" not in payload["messages"][0]
    assert "params" not in payload["messages"][0]
    assert "error" not in payload["messages"][1]
    assert "params" not in payload["messages"][1]
    assert payload["messages"][2]["error"] == AGENT_CHAT_FAILED
    assert payload["messages"][2]["params"] == {}
    assert payload["messages"][3]["error"] == AGENT_CHAT_FAILED
    assert payload["messages"][3]["params"] == {}
    assert "SECRET_REASONING" not in response.text
    assert "SECRET_TOOL_RESULT" not in response.text
    assert "tool_calls" not in response.text


def test_agent_chat_forwards_stock_context_to_executor(tmp_path: Path) -> None:
    executor = MagicMock()
    executor.chat.return_value = SimpleNamespace(
        success=True,
        content="ok",
        error=None,
    )
    config = SimpleNamespace(is_agent_available=lambda: True)

    with patch("api.middlewares.auth.is_auth_enabled", return_value=False):
        with patch("api.v1.endpoints.agent.get_config", return_value=config):
            with patch("api.v1.endpoints.agent._build_executor", return_value=executor):
                client = TestClient(create_app(static_dir=tmp_path / "static"))
                response = client.post(
                    "/api/v1/agent/chat",
                    json={
                        "message": "如果不考虑 TTM 呢",
                        "session_id": "s1",
                        "context": {
                            "stock_code": "600519",
                            "stock_name": "匿名标的",
                        },
                    },
                )

    assert response.status_code == 200
    kwargs = executor.chat.call_args.kwargs
    assert kwargs["message"] == "如果不考虑 TTM 呢"
    assert kwargs["session_id"] == "s1"
    assert kwargs["context"]["stock_code"] == "600519"
    assert kwargs["context"]["stock_name"] == "匿名标的"


def test_agent_chat_failure_does_not_expose_executor_details(tmp_path: Path, caplog) -> None:
    executor = MagicMock()
    executor.chat.return_value = SimpleNamespace(
        success=False,
        content=SENSITIVE_PROVIDER_ERROR,
        error=SENSITIVE_PROVIDER_ERROR,
    )
    config = SimpleNamespace(is_agent_available=lambda: True)
    caplog.set_level(logging.ERROR, logger="api.v1.endpoints.agent")

    with patch("api.middlewares.auth.is_auth_enabled", return_value=False):
        with patch("api.v1.endpoints.agent.get_config", return_value=config):
            with patch("api.v1.endpoints.agent._build_executor", return_value=executor):
                client = TestClient(create_app(static_dir=tmp_path / "static"))
                response = client.post(
                    "/api/v1/agent/chat",
                    json={"message": "分析失败场景", "session_id": "private-rest"},
                )

    assert response.status_code == 200
    assert response.json() == {
        "success": False,
        "content": "",
        "session_id": "private-rest",
        "error": "agent_chat_failed",
    }
    assert "super-secret" not in response.text
    assert "private.example" not in response.text
    assert "super-secret" not in caplog.text
    assert "private.example" not in caplog.text


def test_agent_chat_keeps_all_unavailable_comparison_failure_content_empty(
    tmp_path: Path,
) -> None:
    executor = MagicMock()
    executor.chat.return_value = _build_all_unavailable_comparison_result()
    config = SimpleNamespace(is_agent_available=lambda: True)

    with patch("api.middlewares.auth.is_auth_enabled", return_value=False):
        with patch("api.v1.endpoints.agent.get_config", return_value=config):
            with patch("api.v1.endpoints.agent._build_executor", return_value=executor):
                client = TestClient(create_app(static_dir=tmp_path / "static"))
                response = client.post(
                    "/api/v1/agent/chat",
                    json={
                        "message": "compare AAPL and HK00700",
                        "session_id": "all-unavailable-rest",
                    },
                )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "success": False,
        "content": "",
        "session_id": "all-unavailable-rest",
        "error": AGENT_CHAT_FAILED,
    }


def test_agent_research_failure_does_not_expose_internal_result(tmp_path: Path) -> None:
    config = SimpleNamespace(
        is_agent_available=lambda: True,
        agent_deep_research_budget=30000,
        agent_deep_research_timeout=180,
    )
    research_result = SimpleNamespace(
        success=False,
        report=SENSITIVE_PROVIDER_ERROR,
        sub_questions=[SENSITIVE_PROVIDER_ERROR],
        total_tokens=42,
        error=SENSITIVE_PROVIDER_ERROR,
        timed_out=False,
    )

    with patch("api.middlewares.auth.is_auth_enabled", return_value=False):
        with patch("api.v1.endpoints.agent.get_config", return_value=config):
            with patch(
                "api.v1.endpoints.agent._run_research_in_background",
                new=AsyncMock(return_value=research_result),
            ):
                client = TestClient(create_app(static_dir=tmp_path / "static"))
                response = client.post(
                    "/api/v1/agent/research",
                    json={"question": "研究失败场景"},
                )

    assert response.status_code == 200
    assert response.json() == {
        "success": False,
        "content": "",
        "sources": [],
        "token_usage": 0,
        "error": "agent_research_failed",
    }
    assert "super-secret" not in response.text
    assert "private.example" not in response.text


def test_agent_research_timeout_does_not_expose_internal_result(tmp_path: Path) -> None:
    config = SimpleNamespace(
        is_agent_available=lambda: True,
        agent_deep_research_budget=30000,
        agent_deep_research_timeout=180,
    )
    research_result = SimpleNamespace(
        success=False,
        report=SENSITIVE_PROVIDER_ERROR,
        sub_questions=[SENSITIVE_PROVIDER_ERROR],
        total_tokens=42,
        error=SENSITIVE_PROVIDER_ERROR,
        timed_out=True,
    )

    with patch("api.middlewares.auth.is_auth_enabled", return_value=False):
        with patch("api.v1.endpoints.agent.get_config", return_value=config):
            with patch(
                "api.v1.endpoints.agent._run_research_in_background",
                new=AsyncMock(return_value=research_result),
            ):
                client = TestClient(create_app(static_dir=tmp_path / "static"))
                response = client.post(
                    "/api/v1/agent/research",
                    json={"question": "研究超时场景"},
                )

    assert response.status_code == 200
    assert response.json() == {
        "success": False,
        "content": "",
        "sources": [],
        "token_usage": 0,
        "error": "agent_research_failed",
    }
    assert "super-secret" not in response.text
    assert "private.example" not in response.text


def test_agent_chat_stream_forwards_stock_context_to_executor(tmp_path: Path) -> None:
    executor = MagicMock()
    executor.chat.return_value = SimpleNamespace(
        success=True,
        content="ok",
        error=None,
        total_steps=1,
    )
    config = SimpleNamespace(is_agent_available=lambda: True)

    with patch("api.middlewares.auth.is_auth_enabled", return_value=False):
        with patch("api.v1.endpoints.agent.get_config", return_value=config):
            with patch("api.v1.endpoints.agent._build_executor", return_value=executor):
                client = TestClient(create_app(static_dir=tmp_path / "static"))
                response = client.post(
                    "/api/v1/agent/chat/stream",
                    json={
                        "message": "如果不考虑 TTM 呢",
                        "session_id": "s1",
                        "context": {
                            "stock_code": "600519",
                            "stock_name": "匿名标的",
                        },
                    },
                )

    assert response.status_code == 200
    assert '"type": "done"' in response.text
    kwargs = executor.chat.call_args.kwargs
    assert kwargs["message"] == "如果不考虑 TTM 呢"
    assert kwargs["session_id"] == "s1"
    assert kwargs["context"]["stock_code"] == "600519"
    assert kwargs["context"]["stock_name"] == "匿名标的"


def test_agent_chat_stream_redacts_terminal_identifiers_but_not_chat_content(
    tmp_path: Path,
) -> None:
    product_content = "The model discussed sk-product-content-1234567890."
    executor = MagicMock()
    executor.chat.return_value = SimpleNamespace(
        success=True,
        content=product_content,
        error=None,
        total_steps=1,
    )
    config = SimpleNamespace(is_agent_available=lambda: True)

    with patch("api.middlewares.auth.is_auth_enabled", return_value=False):
        with patch("api.v1.endpoints.agent.get_config", return_value=config):
            with patch("api.v1.endpoints.agent._build_executor", return_value=executor):
                client = TestClient(create_app(static_dir=tmp_path / "static"))
                response = client.post(
                    "/api/v1/agent/chat/stream",
                    json={
                        "message": "terminal identifier redaction",
                        "session_id": SENSITIVE_STREAM_SESSION_ID,
                    },
                )

    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    terminal = events[-1]

    assert response.status_code == 200
    assert terminal["type"] == "done"
    assert terminal["content"] == product_content
    assert SENSITIVE_STREAM_SESSION_ID not in response.text
    assert terminal["trace_id"] == "api_key=[REDACTED]"
    assert terminal["session_id"] == "api_key=[REDACTED]"
    assert executor.chat.call_args.kwargs["session_id"] == SENSITIVE_STREAM_SESSION_ID


def test_agent_chat_stream_failure_does_not_expose_executor_details(tmp_path: Path, caplog) -> None:
    executor = MagicMock()
    executor.chat.return_value = SimpleNamespace(
        success=False,
        content=SENSITIVE_PROVIDER_ERROR,
        error=SENSITIVE_PROVIDER_ERROR,
        total_steps=1,
    )
    config = SimpleNamespace(is_agent_available=lambda: True)
    caplog.set_level(logging.ERROR, logger="api.v1.endpoints.agent")

    with patch("api.middlewares.auth.is_auth_enabled", return_value=False):
        with patch("api.v1.endpoints.agent.get_config", return_value=config):
            with patch("api.v1.endpoints.agent._build_executor", return_value=executor):
                client = TestClient(create_app(static_dir=tmp_path / "static"))
                response = client.post(
                    "/api/v1/agent/chat/stream",
                    json={"message": "流式失败场景", "session_id": "private-stream"},
                )

    assert response.status_code == 200
    assert '"type": "done"' in response.text
    assert '"success": false' in response.text
    assert '"content": ""' in response.text
    assert '"error": "agent_chat_failed"' in response.text
    assert "super-secret" not in response.text
    assert "private.example" not in response.text
    assert "super-secret" not in caplog.text
    assert "private.example" not in caplog.text


def test_agent_chat_stream_keeps_all_unavailable_failure_content_empty(
    tmp_path: Path,
) -> None:
    executor = MagicMock()
    executor.chat.return_value = _build_all_unavailable_comparison_result()
    config = SimpleNamespace(is_agent_available=lambda: True)

    with patch("api.middlewares.auth.is_auth_enabled", return_value=False):
        with patch("api.v1.endpoints.agent.get_config", return_value=config):
            with patch("api.v1.endpoints.agent._build_executor", return_value=executor):
                client = TestClient(create_app(static_dir=tmp_path / "static"))
                response = client.post(
                    "/api/v1/agent/chat/stream",
                    json={
                        "message": "compare AAPL and HK00700",
                        "session_id": "all-unavailable-stream",
                    },
                )

    assert response.status_code == 200
    assert '"type": "done"' in response.text
    assert '"success": false' in response.text
    assert '"content": ""' in response.text
    assert '"error": "agent_chat_failed"' in response.text
    assert "US quote unavailable" not in response.text
    assert "HK quote unavailable" not in response.text


def test_agent_chat_stream_callback_error_is_replaced_with_safe_event(tmp_path: Path) -> None:
    executor = MagicMock()

    def fail_with_callback(**kwargs):
        kwargs["progress_callback"]({
            "type": "error",
            "error": SENSITIVE_PROVIDER_ERROR,
            "message": SENSITIVE_PROVIDER_ERROR,
            "content": SENSITIVE_PROVIDER_ERROR,
            "details": {"url": SENSITIVE_PROVIDER_ERROR},
        })
        return SimpleNamespace(
            success=False,
            content=SENSITIVE_PROVIDER_ERROR,
            error=SENSITIVE_PROVIDER_ERROR,
            total_steps=1,
        )

    executor.chat.side_effect = fail_with_callback
    config = SimpleNamespace(is_agent_available=lambda: True)

    with patch("api.middlewares.auth.is_auth_enabled", return_value=False):
        with patch("api.v1.endpoints.agent.get_config", return_value=config):
            with patch("api.v1.endpoints.agent._build_executor", return_value=executor):
                client = TestClient(create_app(static_dir=tmp_path / "static"))
                response = client.post(
                    "/api/v1/agent/chat/stream",
                    json={"message": "回调失败场景", "session_id": "private-callback"},
                )

    assert response.status_code == 200
    assert '"type": "error"' in response.text
    assert '"error": "agent_stream_failed"' in response.text
    assert '"message": "Agent stream failed"' in response.text
    assert "super-secret" not in response.text
    assert "private.example" not in response.text


def test_agent_chat_stream_callback_error_redacts_secret_shaped_trace_id(
    tmp_path: Path,
) -> None:
    executor = MagicMock()

    def fail_with_callback(**kwargs):
        kwargs["progress_callback"]({
            "type": "error",
            "message": "provider callback failed",
        })
        return SimpleNamespace(
            success=False,
            content="",
            error="provider callback failed",
            total_steps=1,
        )

    executor.chat.side_effect = fail_with_callback
    config = SimpleNamespace(is_agent_available=lambda: True)

    with patch("api.middlewares.auth.is_auth_enabled", return_value=False):
        with patch("api.v1.endpoints.agent.get_config", return_value=config):
            with patch("api.v1.endpoints.agent._build_executor", return_value=executor):
                client = TestClient(create_app(static_dir=tmp_path / "static"))
                response = client.post(
                    "/api/v1/agent/chat/stream",
                    json={
                        "message": "callback identifier redaction",
                        "session_id": SENSITIVE_STREAM_SESSION_ID,
                    },
                )

    assert response.status_code == 200
    assert '"type": "error"' in response.text
    assert SENSITIVE_STREAM_SESSION_ID not in response.text
    assert '"trace_id": "api_key=[REDACTED]"' in response.text


def test_agent_chat_stream_exception_is_redacted_from_event_and_logs(tmp_path: Path, caplog) -> None:
    executor = MagicMock()
    executor.chat.side_effect = RuntimeError(SENSITIVE_PROVIDER_ERROR)
    config = SimpleNamespace(is_agent_available=lambda: True)
    caplog.set_level(logging.ERROR, logger="api.v1.endpoints.agent")

    with patch("api.middlewares.auth.is_auth_enabled", return_value=False):
        with patch("api.v1.endpoints.agent.get_config", return_value=config):
            with patch("api.v1.endpoints.agent._build_executor", return_value=executor):
                client = TestClient(create_app(static_dir=tmp_path / "static"))
                response = client.post(
                    "/api/v1/agent/chat/stream",
                    json={
                        "message": "流式异常场景",
                        "session_id": SENSITIVE_STREAM_SESSION_ID,
                    },
                )

    assert response.status_code == 200
    assert '"error": "agent_stream_failed"' in response.text
    assert "super-secret" not in response.text
    assert "private.example" not in response.text
    assert SENSITIVE_STREAM_SESSION_ID not in response.text
    assert "super-secret" not in caplog.text
    assert "private.example" not in caplog.text
    assert SENSITIVE_STREAM_SESSION_ID not in caplog.text
