# -*- coding: utf-8 -*-
"""Regression coverage for the local CLI Agent tool bridge."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.agent.llm_adapter import LLMToolAdapter
from src.agent.local_cli_tool_bridge import (
    build_local_cli_agent_prompt,
    call_local_cli_agent,
    parse_local_cli_agent_response,
)
from src.agent.runner import run_agent_loop
from src.agent.tools.registry import (
    ToolDefinition,
    ToolParameter,
    ToolPolicy,
    ToolRegistry,
)
from src.llm.generation_backend import GenerationResult
from tests.security_audit_test_utils import SecurityAuditRecorderStub


_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_realtime_quote",
            "description": "Get a quote",
            "parameters": {
                "type": "object",
                "properties": {"stock_code": {"type": "string"}},
                "required": ["stock_code"],
            },
        },
    }
]


class _FakeBackend:
    backend_id = "codex_cli"

    def __init__(self, response: str) -> None:
        self.response = response
        self.received = None

    def generate(self, prompt, generation_config, **kwargs):
        self.received = (prompt, generation_config, kwargs)
        validator = kwargs.get("response_validator")
        if validator is not None:
            validator(self.response)
        return GenerationResult(
            text=self.response,
            model="codex_cli",
            provider="codex_cli",
            backend="codex_cli",
            usage={"usage_available": False},
        )


class _SequenceBackend(_FakeBackend):
    def __init__(self, responses: list[str]) -> None:
        super().__init__("")
        self.responses = iter(responses)

    def generate(self, prompt, generation_config, **kwargs):
        self.response = next(self.responses)
        return super().generate(prompt, generation_config, **kwargs)


def test_prompt_preserves_tool_roundtrip_without_internal_trace_fields() -> None:
    prompt = build_local_cli_agent_prompt(
        [
            {"role": "user", "content": "分析 600519", "_trace_provider": "secret-route"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "name": "get_realtime_quote",
                        "arguments": {"stock_code": "600519"},
                    }
                ],
            },
            {
                "role": "tool",
                "name": "get_realtime_quote",
                "tool_call_id": "call-1",
                "content": '{"price": 1500}',
            },
        ],
        _TOOLS,
    )

    assert "get_realtime_quote" in prompt
    assert "call-1" in prompt
    assert "secret-route" not in prompt
    assert "untrusted data" in prompt


def test_parse_accepts_final_and_fenced_tool_calls() -> None:
    final = parse_local_cli_agent_response('{"type":"final","content":"结论"}')
    tools = parse_local_cli_agent_response(
        """```json
        {"type":"tool_calls","calls":[{"name":"get_realtime_quote","arguments":{"stock_code":"600519"}}]}
        ```""",
        allowed_tool_names={"get_realtime_quote"},
    )

    assert final.content == "结论"
    assert final.tool_calls == []
    assert tools.content is None
    assert len(tools.tool_calls) == 1
    assert tools.tool_calls[0].id.startswith("cli-")
    assert tools.tool_calls[0].arguments == {"stock_code": "600519"}


@pytest.mark.parametrize(
    "response,reason",
    [
        ('{"type":"tool_calls","calls":[{"name":"unknown","arguments":{}}]}', "tool_name_unknown"),
        ('{"type":"tool_calls","calls":[{"name":"get_realtime_quote","arguments":"600519"}]}', "tool_arguments_invalid"),
        ('{"type":"final","content":""}', "final_content_missing"),
        ("not-json", "invalid_json"),
    ],
)
def test_parse_rejects_invalid_or_untrusted_calls(response: str, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        parse_local_cli_agent_response(
            response,
            allowed_tool_names={"get_realtime_quote"},
        )


def test_call_bridge_passes_agent_timeout_and_returns_normalized_turn() -> None:
    backend = _FakeBackend(
        json.dumps(
            {
                "type": "tool_calls",
                "content": "正在查询",
                "calls": [
                    {
                        "name": "get_realtime_quote",
                        "arguments": {"stock_code": "600519"},
                    }
                ],
            },
            ensure_ascii=False,
        )
    )

    turn = call_local_cli_agent(
        backend,
        [{"role": "user", "content": "分析 600519"}],
        _TOOLS,
        temperature=0.2,
        max_tokens=400,
        timeout=12.8,
    )

    assert turn.provider == "codex_cli"
    assert turn.model == "codex_cli"
    assert turn.tool_calls[0].name == "get_realtime_quote"
    assert backend.received is not None
    assert backend.received[1] == {
        "temperature": 0.2,
        "max_tokens": 400,
        "timeout_seconds": 12.8,
    }
    assert backend.received[2]["audit_context"] == {
        "call_type": "agent",
        "tool_bridge": "structured_json",
    }


def test_local_cli_adapter_executes_tools_through_bound_session() -> None:
    handler_calls: list[str] = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo_value",
            description="Echo one value",
            parameters=[
                ToolParameter(
                    name="value",
                    type="string",
                    description="Value to echo",
                )
            ],
            handler=lambda value: handler_calls.append(value) or {"echo": value},
            policy=ToolPolicy.declared(
                read_only=True,
                permissions=["analysis_context:read"],
            ),
        )
    )
    backend = _SequenceBackend(
        [
            json.dumps(
                {
                    "type": "tool_calls",
                    "calls": [
                        {
                            "name": "echo_value",
                            "arguments": {"value": "bound-session-ok"},
                        }
                    ],
                }
            ),
            json.dumps({"type": "final", "content": "bound-session-ok"}),
        ]
    )
    adapter = object.__new__(LLMToolAdapter)
    adapter._config = object()
    adapter._backend_error = None
    adapter._local_cli_backend = backend
    adapter._generation_backend_id = "codex_cli"

    with patch(
        "src.agent.runner_parts.loop._get_security_audit_service",
        return_value=SecurityAuditRecorderStub(),
    ):
        result = run_agent_loop(
            messages=[{"role": "user", "content": "Echo the requested value"}],
            tool_registry=registry,
            llm_adapter=adapter,
            max_steps=3,
        )

    assert result.success is True
    assert result.content == "bound-session-ok"
    assert result.provider == "codex_cli"
    assert result.models_used == ["codex_cli", "codex_cli"]
    assert handler_calls == ["bound-session-ok"]
    assert result.tool_calls_log[0]["tool"] == "echo_value"
