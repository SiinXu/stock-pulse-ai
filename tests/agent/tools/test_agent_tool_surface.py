# -*- coding: utf-8 -*-
"""Tests for the internal DSA Tool Surface."""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from unittest.mock import patch

from src.agent.stock_scope import StockScope
from src.agent.runtime.tool_session import BoundToolSession
from src.agent.tool_surface import ToolSurface
from src.agent.tools.data_tools import get_portfolio_snapshot_tool
from src.agent.tools.execution import ToolAccessContext
from src.agent.tools.registry import (
    SUPPORTED_AGENT_TOOL_CAPABILITIES,
    ToolDefinition,
    ToolParameter,
    ToolPolicy,
    ToolRegistry,
)
from tests.security_audit_test_utils import SecurityAuditRecorderStub


_TEST_CAPABILITY = "analysis_context:read"


def _test_policy() -> ToolPolicy:
    return ToolPolicy.declared(
        read_only=True,
        side_effects=[],
        permissions=[_TEST_CAPABILITY],
    )


def _authorized_context(
    *capabilities: str,
    **values,
) -> ToolAccessContext:
    return ToolAccessContext(
        granted_capabilities=frozenset(capabilities or (_TEST_CAPABILITY,)),
        **values,
    )


def _registry_with_echo(executed=None) -> ToolRegistry:
    calls = executed if executed is not None else []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo",
            description="Echo a message.",
            parameters=[
                ToolParameter(name="message", type="string", description="Message"),
                ToolParameter(
                    name="mode",
                    type="string",
                    description="Mode",
                    required=False,
                    default="plain",
                    enum=["plain", "loud"],
                ),
            ],
            handler=lambda message, mode="plain": calls.append((message, mode)) or {"message": message, "mode": mode},
            category="data",
            policy=ToolPolicy.declared(
                read_only=True,
                side_effects=[],
                permissions=[_TEST_CAPABILITY],
            ),
        )
    )
    return registry


def _registry_with_url_payload(executed=None) -> ToolRegistry:
    calls = executed if executed is not None else []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="fetch_payload",
            description="Fetch a declared payload URL.",
            parameters=[
                ToolParameter(
                    name="payload",
                    type="object",
                    description="Nested URL payload",
                ),
            ],
            handler=lambda payload: calls.append(payload) or {"accepted": True},
            policy=_test_policy(),
        )
    )
    return registry


def test_public_descriptor_does_not_expose_handler_and_includes_policy_scope() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="quote",
            description="Quote",
            parameters=[ToolParameter(name="stock_code", type="string", description="Stock")],
            handler=lambda stock_code: {"code": stock_code},
            category="data",
            policy=ToolPolicy.declared(
                read_only=True,
                side_effects=["network_read"],
                permissions=["market_data:read"],
                scope_dimensions=["stock"],
            ),
        )
    )

    descriptor = ToolSurface(registry).list_tools("public")[0]
    encoded = json.dumps(descriptor, ensure_ascii=False)

    assert descriptor["policy"]["policy_status"] == "declared"
    assert descriptor["policy"]["capabilities"] == ["market_data:read"]
    assert descriptor["policy"]["permissions"] == ["market_data:read"]
    assert descriptor["scope"]["scope_dimensions"] == ["stock"]
    assert descriptor["scope"]["requires_stock_scope"] is True
    assert "handler" not in encoded
    assert "callable" not in encoded
    assert "<function" not in encoded


def test_openai_schema_is_structurally_equal_to_registry_output() -> None:
    registry = _registry_with_echo()

    assert ToolSurface(registry).list_tools("openai") == registry.to_openai_tools()
    encoded = json.dumps(ToolSurface(registry).list_tools("openai"))
    assert "policy" not in encoded
    assert "permissions" not in encoded
    assert "side_effects" not in encoded
    assert "scope" not in encoded


def test_mcp_descriptor_is_descriptor_only() -> None:
    descriptor = ToolSurface(_registry_with_echo()).list_tools("mcp_descriptor")[0]
    expected_schema = _registry_with_echo().get("echo")._params_json_schema()
    expected_schema.setdefault("required", [])
    expected_schema["additionalProperties"] = False

    assert descriptor == {
        "name": "echo",
        "description": "Echo a message.",
        "inputSchema": expected_schema,
    }
    assert "transport" not in descriptor
    assert "server" not in descriptor


def test_execute_exact_tool_name_success() -> None:
    calls = []
    result = ToolSurface(_registry_with_echo(calls)).execute_tool(
        "echo",
        {"message": "hello"},
        _authorized_context(backend="test", session_id="s1"),
    )

    assert result["ok"] is True
    assert result["result"] == {"message": "hello", "mode": "plain"}
    assert json.loads(result["result_text"]) == {"message": "hello", "mode": "plain"}
    assert result["audit"]["backend"] == "test"
    assert result["audit"]["session_id"] == "s1"
    assert calls == [("hello", "plain")]


def test_direct_surface_denies_missing_capability_before_handler() -> None:
    calls = []
    result = ToolSurface(_registry_with_echo(calls)).execute_tool(
        "echo",
        {"message": "blocked"},
        ToolAccessContext(),
    )

    assert result["error"]["code"] == "permission_denied"
    assert result["error"]["details"]["required_capabilities"] == [
        _TEST_CAPABILITY
    ]
    assert result["error"]["details"]["missing_capabilities"] == [
        _TEST_CAPABILITY
    ]
    assert calls == []


def test_direct_surface_does_not_normalize_noncanonical_grants() -> None:
    calls = []
    result = ToolSurface(_registry_with_echo(calls)).execute_tool(
        "echo",
        {"message": "blocked"},
        ToolAccessContext(
            granted_capabilities=frozenset({f" {_TEST_CAPABILITY}"})
        ),
    )

    assert result["error"]["code"] == "permission_denied"
    assert calls == []


def test_direct_surface_denies_unsupported_and_undeclared_capabilities() -> None:
    calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="unsupported",
            description="Unsupported capability",
            parameters=[],
            handler=lambda: calls.append("unsupported"),
            policy=ToolPolicy.declared(
                read_only=False,
                permissions=["filesystem:write"],
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="undeclared",
            description="Missing capability",
            parameters=[],
            handler=lambda: calls.append("undeclared"),
            policy=ToolPolicy.declared(read_only=True),
        )
    )

    unsupported = ToolSurface(registry).execute_tool(
        "unsupported",
        {},
        ToolAccessContext(
            granted_capabilities=frozenset({"filesystem:write"})
        ),
    )
    undeclared = ToolSurface(registry).execute_tool(
        "undeclared",
        {},
        _authorized_context(),
    )

    assert unsupported["error"]["code"] == "unsupported_capability"
    assert unsupported["error"]["details"]["unsupported_capabilities"] == [
        "filesystem:write"
    ]
    assert undeclared["error"]["code"] == "capability_undeclared"
    assert calls == []


def test_direct_surface_denies_noncanonical_or_empty_capabilities() -> None:
    calls = []
    registry = ToolRegistry()
    for name, capability in (
        ("whitespace", " market_data:read"),
        ("empty", ""),
    ):
        registry.register(
            ToolDefinition(
                name=name,
                description="Invalid capability declaration",
                parameters=[],
                handler=lambda marker=name: calls.append(marker),
                policy=ToolPolicy.declared(
                    read_only=True,
                    permissions=[capability],
                ),
            )
        )

    for name in ("whitespace", "empty"):
        result = ToolSurface(registry).execute_tool(
            name,
            {},
            _authorized_context("market_data:read"),
        )
        assert result["error"]["code"] == "unsupported_capability"

    assert calls == []


def test_direct_surface_denies_unknown_parameter_schema_type() -> None:
    calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="invalid_schema",
            description="Invalid schema",
            parameters=[
                ToolParameter(
                    name="value",
                    type="future_type",
                    description="Unsupported type",
                ),
            ],
            handler=lambda value: calls.append(value),
            policy=_test_policy(),
        )
    )

    result = ToolSurface(registry).execute_tool(
        "invalid_schema",
        {"value": "must-not-run"},
        _authorized_context(),
    )

    assert result["error"]["code"] == "schema_contract_violation"
    assert result["error"]["details"]["invalid_schema_fields"] == [
        "parameters[0].type"
    ]
    assert calls == []


def test_direct_surface_denies_cross_type_enum_contracts_without_dispatch() -> None:
    calls = []
    registry = ToolRegistry()
    for name, parameter_type, enum_value in (
        ("integer_bool_enum", "integer", True),
        ("number_bool_enum", "number", True),
        ("boolean_integer_enum", "boolean", 1),
    ):
        registry.register(
            ToolDefinition(
                name=name,
                description="Cross-type enum contract",
                parameters=[
                    ToolParameter(
                        name="value",
                        type=parameter_type,
                        description="Value",
                        enum=[enum_value],
                    ),
                ],
                handler=lambda value, marker=name: calls.append((marker, value)),
                policy=_test_policy(),
            )
        )

    for name, argument in (
        ("integer_bool_enum", 1),
        ("number_bool_enum", 1),
        ("boolean_integer_enum", True),
    ):
        result = ToolSurface(registry).execute_tool(
            name,
            {"value": argument},
            _authorized_context(),
        )
        assert result["error"]["code"] == "schema_contract_violation"
        assert result["error"]["details"]["invalid_schema_fields"] == [
            "parameters[0].enum"
        ]

    assert calls == []


def test_runtime_enum_comparison_keeps_boolean_distinct_from_number() -> None:
    calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="number_enum",
            description="Numeric enum",
            parameters=[
                ToolParameter(
                    name="value",
                    type="number",
                    description="Value",
                    enum=[1],
                ),
            ],
            handler=lambda value: calls.append(value),
            policy=_test_policy(),
        )
    )

    result = ToolSurface(registry).execute_tool(
        "number_enum",
        {"value": True},
        _authorized_context(),
    )
    compatible = ToolSurface(registry).execute_tool(
        "number_enum",
        {"value": 1.0},
        _authorized_context(),
    )

    assert result["error"]["code"] == "invalid_arguments"
    assert compatible["ok"] is True
    assert calls == [1.0]


def test_deep_optional_default_fails_as_structured_schema_denial() -> None:
    calls = []
    nested_default = []
    for _ in range(1500):
        nested_default = [nested_default]
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="deep_default",
            description="Deep default",
            parameters=[
                ToolParameter(
                    name="payload",
                    type="array",
                    description="Payload",
                    required=False,
                    default=nested_default,
                ),
            ],
            handler=lambda payload: calls.append(payload),
            policy=_test_policy(),
        )
    )

    result = ToolSurface(registry).execute_tool(
        "deep_default",
        {},
        _authorized_context(),
    )

    assert result["error"]["code"] == "schema_contract_violation"
    assert result["error"]["details"]["invalid_schema_fields"] == [
        "parameters[0].default"
    ]
    assert calls == []


def test_direct_surface_denies_invalid_policy_object() -> None:
    calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="invalid_policy",
            description="Invalid policy object",
            parameters=[],
            handler=lambda: calls.append("ran"),
            policy=None,
        )
    )

    result = ToolSurface(registry).execute_tool(
        "invalid_policy",
        {},
        _authorized_context(),
    )

    assert result["error"]["code"] == "policy_undeclared"
    assert calls == []


def test_direct_surface_denies_unknown_policy_before_handler() -> None:
    calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="unknown_policy",
            description="Unknown policy",
            parameters=[],
            handler=lambda: calls.append("ran"),
        )
    )

    result = ToolSurface(registry).execute_tool(
        "unknown_policy",
        {},
        _authorized_context(),
    )

    assert result["error"]["code"] == "policy_undeclared"
    assert calls == []


def test_nested_private_loopback_link_local_and_credential_urls_are_denied() -> None:
    calls = []
    surface = ToolSurface(_registry_with_url_payload(calls))
    cases = {
        "http://10.0.0.7/private": "private_ip_blocked",
        "http://127.0.0.1/admin": "private_ip_blocked",
        "http://169.254.10.20/latest": "restricted_ip_blocked",
        "https://agent:credential-canary@example.com/data": (
            "credentials_not_allowed"
        ),
    }

    for url, expected_reason in cases.items():
        result = surface.execute_tool(
            "fetch_payload",
            {"payload": {"callbacks": [{"redirect_url": url}]}},
            _authorized_context(),
        )

        assert result["error"]["code"] == "outbound_url_denied"
        assert result["error"]["details"]["reason"] == expected_reason
        assert "correlation_id" in result["error"]["details"]
        visible = json.dumps(result, ensure_ascii=False)
        assert url not in visible
        assert "credential-canary" not in visible

    assert calls == []


def test_nested_public_url_is_allowed_after_outbound_policy_validation() -> None:
    calls = []
    surface = ToolSurface(_registry_with_url_payload(calls))
    payload = {
        "targets": [
            {"destination": "https://example.com/market-data"},
        ],
    }
    public_dns = [
        (2, 1, 6, "", ("93.184.216.34", 443)),
    ]

    with patch(
        "src.security.outbound_policy.socket.getaddrinfo",
        return_value=public_dns,
    ) as getaddrinfo:
        result = surface.execute_tool(
            "fetch_payload",
            {"payload": payload},
            _authorized_context(),
        )

    assert result["ok"] is True
    assert calls == [payload]
    getaddrinfo.assert_called_once()


def test_replaced_definition_cannot_dispatch_stale_preflight_handler() -> None:
    validation_entered = threading.Event()
    release_validation = threading.Event()
    old_calls = []
    new_calls = []

    def _definition(handler) -> ToolDefinition:
        return ToolDefinition(
            name="fetch_url",
            description="Fetch a URL.",
            parameters=[
                ToolParameter(
                    name="target_url",
                    type="string",
                    description="Target URL",
                ),
            ],
            handler=handler,
            policy=_test_policy(),
        )

    registry = ToolRegistry()
    registry.register(
        _definition(
            lambda target_url: old_calls.append(target_url) or {"source": "old"}
        )
    )
    session = BoundToolSession(
        registry,
        execution_id="definition-replacement",
        allowed_tools=["fetch_url"],
        granted_permissions=[_TEST_CAPABILITY],
        security_audit=SecurityAuditRecorderStub(),
    )
    result_holder = {}

    def _pause_outbound_validation(url):
        validation_entered.set()
        assert release_validation.wait(timeout=2)
        return url

    def _execute():
        result_holder["result"] = session.execute(
            "fetch_url",
            {"target_url": "https://example.com/data"},
        )

    with patch(
        "src.agent.tool_surface.validate_outbound_url",
        side_effect=_pause_outbound_validation,
    ):
        worker = threading.Thread(target=_execute)
        worker.start()
        assert validation_entered.wait(timeout=1)
        registry.unregister("fetch_url")
        registry.register(
            _definition(
                lambda target_url: new_calls.append(target_url)
                or {"source": "new"}
            )
        )
        release_validation.set()
        worker.join(timeout=1)

    assert not worker.is_alive()
    assert result_holder["result"]["error"]["code"] == "tool_not_found"
    assert result_holder["result"]["error"]["details"]["reason"] == (
        "definition_changed"
    )
    assert old_calls == []
    assert new_calls == []
    assert session.dispatched_calls == 0


def test_direct_surface_rejects_in_place_mutation_after_preflight() -> None:
    validation_entered = threading.Event()
    release_validation = threading.Event()
    original_calls = []
    mutated_calls = []
    registry = _registry_with_url_payload(original_calls)
    live_definition = registry.resolve("fetch_payload")
    result_holder = {}

    def _pause_outbound_validation(url):
        validation_entered.set()
        assert release_validation.wait(timeout=2)
        return url

    def _execute():
        result_holder["result"] = ToolSurface(registry).execute_tool(
            "fetch_payload",
            {"payload": {"target_url": "https://example.com/data"}},
            _authorized_context(),
        )

    with patch(
        "src.agent.tool_surface.validate_outbound_url",
        side_effect=_pause_outbound_validation,
    ):
        worker = threading.Thread(target=_execute)
        worker.start()
        assert validation_entered.wait(timeout=1)
        live_definition.parameters = []
        live_definition.policy.permissions.clear()
        live_definition.handler = lambda: mutated_calls.append("ran")
        release_validation.set()
        worker.join(timeout=1)

    assert not worker.is_alive()
    assert result_holder["result"]["error"]["code"] == "tool_not_found"
    assert result_holder["result"]["error"]["details"] == {
        "reason": "definition_changed"
    }
    assert original_calls == []
    assert mutated_calls == []


def test_direct_surface_rechecks_binding_after_cancellation_callback() -> None:
    calls = []
    registry = _registry_with_echo(calls)
    armed = {"value": False}

    def _cancel_probe():
        if armed["value"]:
            registry.unregister("echo")
        return False

    result = ToolSurface(registry).execute_tool(
        "echo",
        {"message": "must-not-run"},
        _authorized_context(cancelled_check=_cancel_probe),
        dispatch_guard=lambda _definition: armed.update(value=True),
    )

    assert result["error"]["code"] == "tool_not_found"
    assert result["error"]["details"] == {
        "reason": "definition_changed",
        "handler_started": False,
    }
    assert calls == []


def test_nested_camel_case_url_key_is_validated_as_url_bearing() -> None:
    calls = []
    result = ToolSurface(_registry_with_url_payload(calls)).execute_tool(
        "fetch_payload",
        {
            "payload": {
                "callbacks": [
                    {"callbackUrl": "localhost:8080/private"},
                ],
            },
        },
        _authorized_context(),
    )

    assert result["error"]["code"] == "outbound_url_denied"
    assert result["error"]["details"]["reason"] == "scheme_not_allowed"
    assert calls == []


def test_omitted_url_default_is_materialized_and_denied_before_handler() -> None:
    calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="default_callback",
            description="Default callback",
            parameters=[
                ToolParameter(
                    name="callback_url",
                    type="string",
                    description="Callback URL",
                    required=False,
                    default="http://127.0.0.1/private",
                ),
            ],
            handler=lambda callback_url="http://127.0.0.1/private": calls.append(
                callback_url
            ),
            policy=_test_policy(),
            enforce_contract=False,
        )
    )

    result = ToolSurface(registry).execute_tool(
        "default_callback",
        {},
        _authorized_context(enforce_contract=False),
    )

    assert result["error"]["code"] == "outbound_url_denied"
    assert calls == []


def test_optional_stock_code_schema_fails_closed_before_handler() -> None:
    calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="optional_stock",
            description="Optional stock",
            parameters=[
                ToolParameter(
                    name="stock_code",
                    type="string",
                    description="Stock",
                    required=False,
                    default="AAPL",
                ),
            ],
            handler=lambda stock_code="AAPL": calls.append(stock_code),
            policy=ToolPolicy.declared(
                read_only=True,
                permissions=[_TEST_CAPABILITY],
                scope_dimensions=["stock"],
            ),
        )
    )

    result = ToolSurface(registry).execute_tool(
        "optional_stock",
        {},
        _authorized_context(
            stock_scope=StockScope(
                expected_stock_code="600519",
                allowed_stock_codes={"600519"},
            )
        ),
    )

    assert result["error"]["code"] == "scope_contract_violation"
    assert calls == []


def test_slow_outbound_policy_cannot_start_handler_after_call_deadline() -> None:
    calls = []
    surface = ToolSurface(_registry_with_url_payload(calls))

    def _slow_policy(_url):
        time.sleep(0.03)
        return object()

    with patch(
        "src.agent.tool_surface.validate_outbound_url",
        side_effect=_slow_policy,
    ):
        result = surface.execute_tool(
            "fetch_payload",
            {"payload": {"target_url": "https://example.com/data"}},
            _authorized_context(timeout_seconds=0.01),
        )

    assert result["error"]["code"] == "timeout"
    assert result["error"]["details"]["handler_started"] is False
    assert calls == []


def test_cancellation_during_outbound_policy_prevents_handler_dispatch() -> None:
    calls = []
    cancelled = {"value": False}
    surface = ToolSurface(_registry_with_url_payload(calls))

    def _policy_then_cancel(_url):
        cancelled["value"] = True
        return object()

    with patch(
        "src.agent.tool_surface.validate_outbound_url",
        side_effect=_policy_then_cancel,
    ):
        result = surface.execute_tool(
            "fetch_payload",
            {"payload": {"target_url": "https://example.com/data"}},
            _authorized_context(
                cancelled_check=lambda: cancelled["value"],
            ),
        )

    assert result["error"]["code"] == "cancelled"
    assert result["error"]["details"]["handler_started"] is False
    assert calls == []


def test_rejects_unregistered_namespaced_and_unknown_tools() -> None:
    surface = ToolSurface(_registry_with_echo())

    for name, code in (
        ("default_api:echo", "invalid_tool_name"),
        ("provider.tool", "invalid_tool_name"),
        ("provider:tool", "invalid_tool_name"),
        ("missing", "tool_not_found"),
    ):
        result = surface.execute_tool(name, {}, None)
        assert result["error"]["code"] == code
        assert result["tool_name"] == "unrecognized"
        assert name not in str(result)


def test_direct_surface_unknown_canary_is_absent_from_denial_audit() -> None:
    canary = "prompt_secret_surface_canary_123456789"

    result = ToolSurface(_registry_with_echo()).execute_tool(
        canary,
        {},
        None,
    )

    assert result["error"]["code"] == "tool_not_found"
    assert result["tool_name"] == "unrecognized"
    assert canary not in str(result)


def test_rejects_non_string_tool_names_without_rendering_them() -> None:
    surface = ToolSurface(_registry_with_echo())

    for malformed_name in (None, 7, ["echo"]):
        result = surface.execute_tool(malformed_name, {}, None)

        assert result["ok"] is False
        assert result["tool_name"] == "unrecognized"
        assert result["error"]["code"] == "invalid_tool_name"


def test_registered_dotted_name_uses_exact_match_only() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="provider.tool",
            description="Exact dotted tool",
            parameters=[],
            handler=lambda: {"ok": True},
            policy=_test_policy(),
        )
    )
    surface = ToolSurface(registry)

    assert surface.execute_tool(
        "provider.tool",
        {},
        _authorized_context(),
    )["ok"] is True
    assert surface.execute_tool("other.tool", {}, None)["error"]["code"] == "invalid_tool_name"


def test_argument_validation_errors_before_handler() -> None:
    calls = []
    surface = ToolSurface(_registry_with_echo(calls))

    cases = [
        (None, "arguments must be an object"),
        ({}, "missing required argument"),
        ({"message": "x", "extra": 1}, "unexpected argument"),
        ({"message": "x", "mode": "quiet"}, "must be one of"),
        ({"message": "x", "mode": None}, "must not be null"),
        ({"message": 123}, "must be string"),
    ]
    for arguments, expected in cases:
        result = surface.execute_tool("echo", arguments, _authorized_context())
        assert result["ok"] is False
        assert result["error"]["code"] == "invalid_arguments"
        assert expected in result["error"]["message"]

    assert calls == []


def test_denial_result_and_audit_do_not_retain_unexpected_argument_name() -> None:
    canary = "UNEXPECTED-ARGUMENT-CANARY"
    result = ToolSurface(_registry_with_echo()).execute_tool(
        "echo",
        {"message": "x", canary: "secret"},
        _authorized_context(),
    )

    assert result["error"]["code"] == "invalid_arguments"
    assert result["error"]["message"] == "unexpected argument"
    assert canary not in json.dumps(result, ensure_ascii=False)


def test_legacy_contract_flag_cannot_disable_security_validation() -> None:
    calls = []
    result = ToolSurface(_registry_with_echo(calls)).execute_tool(
        "echo",
        {"message": 123},
        _authorized_context(enforce_contract=False),
    )

    assert result["error"]["code"] == "invalid_arguments"
    assert calls == []


def test_bounded_integer_validation_rejects_arbitrarily_large_json_integer() -> None:
    calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="bounded_integer",
            description="Bounded integer test tool",
            parameters=[
                ToolParameter(
                    name="value",
                    type="integer",
                    description="Bounded value",
                    maximum=512,
                )
            ],
            handler=lambda value: calls.append(value),
            policy=_test_policy(),
        )
    )

    result = ToolSurface(registry).execute_tool(
        "bounded_integer",
        {"value": 10**1_000},
        _authorized_context(),
    )

    assert result["error"]["code"] == "invalid_arguments"
    assert result["error"]["message"] == "argument value must be <= 512"
    assert calls == []


def test_optional_null_arguments_are_rejected_but_omitted_defaults_still_work() -> None:
    calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="optional_params",
            description="Optional params",
            parameters=[
                ToolParameter(name="message", type="string", description="Message"),
                ToolParameter(name="count", type="integer", description="Count", required=False, default=1),
                ToolParameter(name="enabled", type="boolean", description="Enabled", required=False, default=True),
                ToolParameter(name="metadata", type="object", description="Metadata", required=False),
            ],
            handler=lambda message, count=1, enabled=True, metadata=None: calls.append(
                (message, count, enabled, metadata)
            )
            or {
                "message": message,
                "count": count,
                "enabled": enabled,
                "metadata": metadata,
            },
            policy=_test_policy(),
        )
    )
    surface = ToolSurface(registry)

    for key in ["count", "enabled", "metadata"]:
        result = surface.execute_tool(
            "optional_params",
            {"message": "x", key: None},
            _authorized_context(),
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "invalid_arguments"
        assert "must not be null" in result["error"]["message"]

    result = surface.execute_tool(
        "optional_params",
        {"message": "x"},
        _authorized_context(),
    )
    assert result["ok"] is True
    assert result["result"] == {
        "message": "x",
        "count": 1,
        "enabled": True,
        "metadata": None,
    }
    assert calls == [("x", 1, True, None)]


def test_extra_arguments_allowed_when_handler_accepts_kwargs() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="kwargs_tool",
            description="Allows kwargs",
            parameters=[],
            handler=lambda **kwargs: kwargs,
            policy=_test_policy(),
        )
    )

    result = ToolSurface(registry).execute_tool(
        "kwargs_tool",
        {"extra": 1},
        _authorized_context(),
    )
    descriptor = ToolSurface(registry).list_tools("public")[0]

    assert result["ok"] is True
    assert result["result"] == {"extra": 1}
    assert descriptor["parameters"]["additionalProperties"] is True


def test_stock_scope_violation_blocks_handler() -> None:
    calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="quote",
            description="Quote",
            parameters=[ToolParameter(name="stock_code", type="string", description="Stock")],
            handler=lambda stock_code: calls.append(stock_code) or {"code": stock_code},
            policy=ToolPolicy.declared(
                read_only=True,
                permissions=["market_data:read"],
                scope_dimensions=["stock"],
            ),
        )
    )

    result = ToolSurface(registry).execute_tool(
        "quote",
        {"stock_code": "AAPL"},
        _authorized_context(
            "market_data:read",
            stock_scope=StockScope(
                expected_stock_code="600519",
                allowed_stock_codes={"600519"},
            ),
        ),
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "stock_scope_violation"
    assert calls == []


def test_stock_scope_guard_uses_captured_definition_across_registry_aba() -> None:
    calls = []
    scoped_definition = ToolDefinition(
        name="quote",
        description="Scoped quote",
        parameters=[
            ToolParameter(
                name="stock_code",
                type="string",
                description="Stock",
            ),
        ],
        handler=lambda stock_code: calls.append(stock_code) or {"code": stock_code},
        policy=ToolPolicy.declared(
            read_only=True,
            permissions=["market_data:read"],
            scope_dimensions=["stock"],
        ),
    )
    transient_unscoped_definition = ToolDefinition(
        name="quote",
        description="Transient unscoped quote",
        parameters=[],
        handler=lambda: calls.append("transient"),
        policy=ToolPolicy.declared(
            read_only=True,
            permissions=["market_data:read"],
        ),
    )

    class _ABARegistry(ToolRegistry):
        def __init__(self):
            super().__init__()
            self._sequence = iter(
                [
                    scoped_definition,
                    scoped_definition,
                    transient_unscoped_definition,
                    scoped_definition,
                    scoped_definition,
                ]
            )

        def resolve(self, name):
            assert name == "quote"
            return next(self._sequence, scoped_definition)

    result = ToolSurface(_ABARegistry()).execute_tool(
        "quote",
        {"stock_code": "AAPL"},
        _authorized_context(
            "market_data:read",
            stock_scope=StockScope(
                expected_stock_code="600519",
                allowed_stock_codes={"600519"},
            ),
        ),
    )

    assert result["error"]["code"] == "stock_scope_violation"
    assert calls == []


def test_declared_stock_scope_requires_explicit_stock_context_before_handler() -> None:
    calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="quote",
            description="Quote",
            parameters=[ToolParameter(name="stock_code", type="string", description="Stock")],
            handler=lambda stock_code: calls.append(stock_code) or {"code": stock_code},
            policy=ToolPolicy.declared(
                read_only=True,
                permissions=["market_data:read"],
                scope_dimensions=["stock"],
            ),
        )
    )

    result = ToolSurface(registry).execute_tool(
        "quote",
        {"stock_code": "AAPL"},
        _authorized_context("market_data:read"),
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "stock_scope_violation"
    assert result["error"]["details"]["reason"] == "stock_scope_required"
    assert calls == []


def test_handler_error_is_structured_without_traceback() -> None:
    def _fail():
        raise RuntimeError("secret stack")

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="fail",
            description="Fail",
            parameters=[],
            handler=_fail,
            policy=_test_policy(),
        )
    )

    result = ToolSurface(registry).execute_tool(
        "fail",
        {},
        _authorized_context(),
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "handler_error"
    assert "Traceback" not in result["result_text"]
    assert "secret stack" not in result["result_text"]


def test_caught_portfolio_error_is_safe_across_tool_surface_result_and_log(caplog) -> None:
    canary = "TOOL_SURFACE_PORTFOLIO_DIAGNOSTIC_CANARY"
    raw_path = "/Users/private-user/.config/stockpulse/tool-surface-portfolio.json"

    class _FailingPortfolioService:
        def get_portfolio_snapshot(self, **_kwargs):
            raise OSError(5, f"portfolio provider failed: {canary}", raw_path)

    registry = ToolRegistry()
    registry.register(get_portfolio_snapshot_tool)
    caplog.set_level(logging.WARNING, logger="src.agent.tools.data_tools")

    with patch(
        "src.services.portfolio_service.PortfolioService",
        _FailingPortfolioService,
    ), patch(
        "src.services.portfolio_risk_service.PortfolioRiskService",
    ):
        result = ToolSurface(registry).execute_tool(
            "get_portfolio_snapshot",
            {"account_id": 1, "include_risk": False},
            _authorized_context("portfolio:read"),
        )

    # Domain failures remain successful ToolSurface invocations until AR-02 types them.
    assert result["ok"] is True
    assert result["result"] == {
        "status": "failed",
        "error": "Portfolio snapshot is unavailable.",
    }
    visible = json.dumps(result, ensure_ascii=False) + "\n" + "\n".join(
        record.getMessage() for record in caplog.records
    )
    assert canary not in visible
    assert raw_path not in visible
    assert "portfolio provider failed" not in visible


def test_serialization_fallback_for_non_json_native_object() -> None:
    class Payload:
        def __init__(self) -> None:
            self.value = "ok"

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="payload",
            description="Payload",
            parameters=[],
            handler=lambda: Payload(),
            policy=_test_policy(),
        )
    )

    result = ToolSurface(registry).execute_tool(
        "payload",
        {},
        _authorized_context(),
    )

    assert result["ok"] is True
    assert result["result"] == {"value": "ok"}
    assert json.loads(result["result_text"]) == {"value": "ok"}
    json.dumps(result)


def test_audit_and_diagnostics_are_redacted() -> None:
    plain_secret = "plainsecret1234567890"
    cookie_secret = "sessionid=abcdef1234567890"
    basic_auth_secret = "dXNlcjpwYXNzMTIzNDU2"
    proxy_auth_secret = "cHJveHk6c2VjcmV0MTIz"
    api_auth_secret = "plainauthsecret123456"
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="secret",
            description="Secret",
            parameters=[
                ToolParameter(name="message", type="string", description="Message"),
                ToolParameter(name="api_key", type="string", description="API key", required=False),
                ToolParameter(name="headers", type="object", description="Headers", required=False),
            ],
            handler=lambda message, api_key=None, headers=None: {
                "Authorization": "Bearer sk-secret-token-1234567890",
                "api_key": plain_secret,
                "token": plain_secret,
                "secret": plain_secret,
                "headers": {
                    "cookie": cookie_secret,
                    "set-cookie": cookie_secret,
                    "authorization": plain_secret,
                },
                "path": "/Users/massif/private/file.txt",
                "message": message * 50,
            },
            policy=_test_policy(),
        )
    )

    result = ToolSurface(registry).execute_tool(
        "secret",
        {
            "message": (
                "Authorization: Bearer sk-argument-token-1234567890 "
                f"Authorization: Basic {basic_auth_secret} "
                f"Proxy-Authorization: Basic {proxy_auth_secret} "
                f"authorization=ApiKey {api_auth_secret} "
                "/Users/massif/.env "
            ),
            "api_key": plain_secret,
            "headers": {
                "cookie": cookie_secret,
                "set-cookie": cookie_secret,
                "authorization": plain_secret,
            },
        },
        _authorized_context(audit_context={"secret": plain_secret}),
    )
    visible = json.dumps({"audit": result["audit"], "diagnostics": result["diagnostics"]}, ensure_ascii=False)

    assert "sk-secret-token-1234567890" not in visible
    assert "sk-argument-token-1234567890" not in visible
    assert basic_auth_secret not in visible
    assert proxy_auth_secret not in visible
    assert api_auth_secret not in visible
    assert plain_secret not in visible
    assert cookie_secret not in visible
    assert "/Users/massif/private" not in visible
    assert "/Users/massif/.env" not in visible
    assert "[REDACTED" in visible or "<truncated" in visible


def test_policy_unknown_does_not_break_registry_but_strict_validation_reports_issue() -> None:
    registry = ToolRegistry()
    registry.register(ToolDefinition(name="plain", description="Plain", parameters=[], handler=lambda: None))

    issues = registry.validate_tool_policies(strict=True)

    assert registry.validate_tool_policies(strict=False) == []
    assert issues
    assert issues[0]["code"] == "policy_unknown"


def test_strict_validation_reports_stock_scope_policy_mismatch() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="undeclared_stock",
            description="Stock param without policy scope.",
            parameters=[ToolParameter(name="stock_code", type="string", description="Stock")],
            handler=lambda stock_code: {"code": stock_code},
            policy=ToolPolicy.declared(read_only=True, permissions=["market_data:read"]),
        )
    )
    registry.register(
        ToolDefinition(
            name="missing_stock_param",
            description="Policy scope without stock_code param.",
            parameters=[ToolParameter(name="ticker", type="string", description="Ticker")],
            handler=lambda ticker: {"code": ticker},
            policy=ToolPolicy.declared(
                read_only=True,
                permissions=["market_data:read"],
                scope_dimensions=["stock"],
            ),
        )
    )
    registry.register(
        ToolDefinition(
            name="unsupported_market_scope",
            description="Unsupported market scope.",
            parameters=[ToolParameter(name="region", type="string", description="Region")],
            handler=lambda region: {"region": region},
            policy=ToolPolicy.declared(
                read_only=True,
                permissions=["market_data:read"],
                scope_dimensions=["market"],
            ),
        )
    )

    issue_codes = {issue["code"] for issue in registry.validate_tool_policies(strict=True)}
    non_strict_issue_codes = {issue["code"] for issue in registry.validate_tool_policies(strict=False)}

    assert "stock_scope_missing" in issue_codes
    assert "stock_scope_parameter_missing" in issue_codes
    assert "unsupported_scope_dimension" in issue_codes
    assert "stock_scope_missing" not in non_strict_issue_codes
    assert "stock_scope_parameter_missing" not in non_strict_issue_codes
    assert "unsupported_scope_dimension" not in non_strict_issue_codes


def test_tool_surface_stock_param_without_declared_scope_fails_closed() -> None:
    calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="undeclared_stock",
            description="Stock param without policy scope.",
            parameters=[ToolParameter(name="stock_code", type="string", description="Stock")],
            handler=lambda stock_code: calls.append(stock_code) or {"code": stock_code},
            policy=ToolPolicy.declared(read_only=True, permissions=["market_data:read"]),
        )
    )

    result = ToolSurface(registry).execute_tool(
        "undeclared_stock",
        {"stock_code": "AAPL"},
        _authorized_context(
            "market_data:read",
            stock_scope=StockScope(
                expected_stock_code="600519",
                allowed_stock_codes={"600519"},
            ),
        ),
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "scope_contract_violation"
    assert result["error"]["details"]["missing_scope_dimension"] == "stock"
    assert calls == []


def test_tool_surface_declared_stock_scope_without_stock_code_fails_closed() -> None:
    calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="ticker_tool",
            description="Declares stock scope with ticker parameter.",
            parameters=[ToolParameter(name="ticker", type="string", description="Ticker")],
            handler=lambda ticker: calls.append(ticker) or {"code": ticker},
            policy=ToolPolicy.declared(
                read_only=True,
                permissions=["market_data:read"],
                scope_dimensions=["stock"],
            ),
        )
    )

    result = ToolSurface(registry).execute_tool(
        "ticker_tool",
        {"ticker": "AAPL"},
        _authorized_context(
            "market_data:read",
            stock_scope=StockScope(
                expected_stock_code="600519",
                allowed_stock_codes={"600519"},
            ),
        ),
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "scope_contract_violation"
    assert result["error"]["details"]["missing_parameter"] == "stock_code"
    assert calls == []


def test_tool_surface_unsupported_scope_dimension_fails_closed() -> None:
    calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="market_tool",
            description="Declares unsupported market scope.",
            parameters=[ToolParameter(name="region", type="string", description="Region")],
            handler=lambda region: calls.append(region) or {"region": region},
            policy=ToolPolicy.declared(
                read_only=True,
                permissions=["market_data:read"],
                scope_dimensions=["market"],
            ),
        )
    )

    result = ToolSurface(registry).execute_tool(
        "market_tool",
        {"region": "us"},
        _authorized_context("market_data:read", market="cn"),
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "scope_contract_violation"
    assert result["error"]["details"]["unsupported_scope_dimensions"] == ["market"]
    assert calls == []


def test_tool_surface_invalid_scope_collection_fails_closed() -> None:
    calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="invalid_scope",
            description="Invalid scope collection.",
            parameters=[],
            handler=lambda: calls.append("ran"),
            policy=ToolPolicy(
                read_only=True,
                permissions=["analysis_context:read"],
                policy_status="declared",
                scope_dimensions=None,
            ),
        )
    )

    result = ToolSurface(registry).execute_tool(
        "invalid_scope",
        {},
        _authorized_context(),
    )

    assert result["error"]["code"] == "scope_contract_violation"
    assert result["error"]["details"]["invalid_scope_dimensions"] == [
        "invalid_collection"
    ]
    assert calls == []


def test_default_production_registry_has_supported_declared_policies() -> None:
    from src.agent.factory import get_tool_registry

    registry = get_tool_registry()

    assert registry.validate_tool_policies(strict=True) == []
    active_capabilities = registry.supported_declared_capabilities()
    assert active_capabilities <= SUPPORTED_AGENT_TOOL_CAPABILITIES
    assert {
        "analysis_context:read",
        "backtest:read",
        "intel:read",
        "market_data:read",
        "news:read",
        "portfolio:read",
    } <= active_capabilities


def test_future_scope_context_fields_do_not_block_undeclared_tools() -> None:
    result = ToolSurface(_registry_with_echo()).execute_tool(
        "echo",
        {"message": "ok"},
        _authorized_context(
            market="us",
            time_range={"from": "2026-01-01", "to": "2026-01-31"},
            data_sources=["fixture"],
        ),
    )

    assert result["ok"] is True


def test_timeout_returns_promptly_without_waiting_for_handler_shutdown() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="slow",
            description="Slow",
            parameters=[],
            handler=lambda: (time.sleep(0.4), {"done": True})[1],
            policy=_test_policy(),
        )
    )

    started = time.time()
    result = ToolSurface(registry).execute_tool(
        "slow",
        {},
        _authorized_context(timeout_seconds=0.01),
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "timeout"
    assert result["error"]["details"]["handler_may_continue"] is True
    assert time.time() - started < 0.2


def test_max_result_bytes_truncates_public_payload_and_marks_diagnostics() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="large",
            description="Large",
            parameters=[],
            handler=lambda: {"text": "x" * 200},
            policy=_test_policy(),
        )
    )

    result = ToolSurface(registry).execute_tool(
        "large",
        {},
        _authorized_context(max_result_bytes=20),
    )

    assert result["ok"] is True
    assert result["result"] is None
    assert result["diagnostics"]["result_truncated"] is True
    assert result["result_text"].endswith("<truncated>")
    assert len(result["result_text"].encode("utf-8")) <= 20


def test_max_result_bytes_does_not_return_raw_object_when_text_fits() -> None:
    class Payload:
        def __init__(self) -> None:
            self.value = "ok"
            self._private = "x" * 10000

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="payload",
            description="Payload",
            parameters=[],
            handler=lambda: Payload(),
            policy=_test_policy(),
        )
    )

    result = ToolSurface(registry).execute_tool(
        "payload",
        {},
        _authorized_context(max_result_bytes=100),
    )

    assert result["ok"] is True
    assert result["result_text"] == '{"value": "ok"}'
    assert result["result"] == {"value": "ok"}
    assert result["diagnostics"]["result_truncated"] is False


def test_descriptors_include_explicit_empty_required_without_changing_openai_shape() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="empty",
            description="Empty",
            parameters=[],
            handler=lambda: None,
            policy=_test_policy(),
        )
    )

    surface = ToolSurface(registry)

    assert surface.list_tools("public")[0]["parameters"]["required"] == []
    assert surface.list_tools("public")[0]["parameters"]["additionalProperties"] is False
    assert surface.list_tools("mcp_descriptor")[0]["inputSchema"]["required"] == []
    assert surface.list_tools("mcp_descriptor")[0]["inputSchema"]["additionalProperties"] is False
    assert "required" not in registry.to_openai_tools()[0]["function"]["parameters"]
    assert "additionalProperties" not in registry.to_openai_tools()[0]["function"]["parameters"]


def test_max_result_bytes_caps_error_result_text() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="empty",
            description="Empty",
            parameters=[],
            handler=lambda: None,
            policy=_test_policy(),
        )
    )

    result = ToolSurface(registry).execute_tool(
        "empty",
        {"unexpected": "x" * 200},
        _authorized_context(max_result_bytes=16),
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_arguments"
    assert result["diagnostics"]["result_truncated"] is True
    assert len(result["result_text"].encode("utf-8")) <= 16


def test_stock_scope_no_longer_imports_runner_for_normalization() -> None:
    source = Path("src/agent/stock_scope.py").read_text(encoding="utf-8")

    assert "from src.agent.runner import _normalize_tool_stock_code" not in source
