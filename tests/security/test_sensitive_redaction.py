# -*- coding: utf-8 -*-
"""End-to-end sensitive-data redaction regressions for issue #176."""

from __future__ import annotations

import json
import logging

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.middlewares.error_handler import add_error_handlers
from src.agent.provider_trace import extract_provider_trace_turns
from src.agent.public_contract import sanitize_stream_event
from src.agent.tools.execution import redact_diagnostic_value
from src.llm.hermes import sanitize_hermes_error_text
from src.llm.local_cli_backend import redact_diagnostic_text as redact_local_cli_text
from src.logging_config import RelativePathFormatter
from src.services.run_diagnostics import (
    activate_run_diagnostic_context,
    build_run_diagnostic_summary,
    current_diagnostic_snapshot,
    record_llm_run,
    reset_run_diagnostic_context,
)
from src.services.alphasift_service import _sanitize_public_alphasift_diagnostics
from src.utils.sanitize import redact_sensitive_data, redact_sensitive_text


PLAIN_SECRET = "sec2-plain-secret-canary"
BEARER_SECRET = "sec2-bearer-secret-canary"
DSN_SECRET = "sec2-dsn-password-canary"
WEBHOOK_SECRET = "sec2-webhook-secret-canary"
PREFIXED_API_KEY = "sk-sec2-api-key-1234567890"
OPAQUE_LOCAL_TOKEN = "SEC2OpaqueLocalCliToken1234567890ABCDEF"
ALL_SECRETS = (
    PLAIN_SECRET,
    BEARER_SECRET,
    DSN_SECRET,
    WEBHOOK_SECRET,
    PREFIXED_API_KEY,
    OPAQUE_LOCAL_TOKEN,
)


def _assert_no_secret(value) -> None:
    rendered = json.dumps(value, ensure_ascii=False, default=str)
    for secret in ALL_SECRETS:
        assert secret not in rendered


def test_central_redaction_masks_supported_shapes_and_preserves_public_values() -> None:
    payload = {
        "api_key": PLAIN_SECRET,
        "provider_error": f"request rejected {PREFIXED_API_KEY}",
        "authorization": f"Bearer {BEARER_SECRET}",
        "provider_auth_error": f"authorization=ApiKey {PLAIN_SECRET}",
        "dsn": f"postgresql://svc:{DSN_SECRET}@db.example:5432/prod",
        "callback": f"https://hooks.slack.com/services/T/B/{WEBHOOK_SECRET}",
        "encoded_callback": (
            f"https://discord.com/api/%2577ebhooks/123/{WEBHOOK_SECRET}"
        ),
        "public_url": "https://example.com/docs?lang=en",
        "stock_code": "600519",
    }

    redacted = redact_sensitive_data(payload)

    _assert_no_secret(redacted)
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["provider_auth_error"] == "authorization=[REDACTED]"
    assert redacted["dsn"] == "postgresql://[REDACTED]@db.example:5432/prod"
    assert redacted["callback"] == "[REDACTED_URL]"
    assert redacted["encoded_callback"] == "[REDACTED_URL]"
    assert redacted["public_url"] == "https://example.com/docs?lang=en"
    assert redacted["stock_code"] == "600519"


def test_central_redaction_fails_closed_for_recursive_and_hostile_values() -> None:
    class HostileKey:
        def __str__(self) -> str:
            raise RuntimeError(PLAIN_SECRET)

    recursive = {
        "prompt_tokens": 42,
        "header_count": 2,
        "system_prompt": PLAIN_SECRET,
        "prompt_text": PLAIN_SECRET,
        "request_headers_raw": {"X-Diagnostic": PLAIN_SECRET},
    }
    recursive["self"] = recursive

    redacted_recursive = redact_sensitive_data(recursive)
    redacted_hostile = redact_sensitive_data({HostileKey(): PLAIN_SECRET})
    malformed_url = redact_sensitive_text(
        f"provider=https://[invalid/webhook/{WEBHOOK_SECRET}"
    )

    _assert_no_secret(
        {
            "recursive": redacted_recursive,
            "hostile": redacted_hostile,
            "malformed_url": malformed_url,
        }
    )
    assert redacted_recursive["prompt_tokens"] == 42
    assert redacted_recursive["header_count"] == 2
    assert redacted_recursive["system_prompt"] == "[REDACTED]"
    assert redacted_recursive["prompt_text"] == "[REDACTED]"
    assert redacted_recursive["request_headers_raw"] == "[REDACTED]"
    assert redacted_recursive["self"] == "[REDACTED]"
    assert redacted_hostile == {"[UNRENDERABLE]": "[REDACTED]"}
    assert malformed_url == "provider=[REDACTED_URL]"


def test_serialized_json_redaction_is_structural_and_idempotent() -> None:
    serialized = json.dumps(
        {
            "Authorization": f"Bearer {BEARER_SECRET}",
            "api_key": PLAIN_SECRET,
            "headers": {"X-Diagnostic": WEBHOOK_SECRET},
        }
    )

    redacted_once = redact_sensitive_text(serialized)
    redacted_twice = redact_sensitive_text(redacted_once)
    parsed = json.loads(redacted_once)

    _assert_no_secret(redacted_once)
    assert redacted_twice == redacted_once
    assert parsed == {
        "Authorization": "[REDACTED]",
        "api_key": "[REDACTED]",
        "headers": "[REDACTED]",
    }


def test_api_client_error_payload_uses_central_recursive_redaction() -> None:
    app = FastAPI()
    add_error_handlers(app)

    @app.get("/provider-error")
    def provider_error() -> None:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "provider_rejected",
                "message": f"Authorization: Bearer {BEARER_SECRET}",
                "params": {"api_key": PLAIN_SECRET},
                "details": {
                    "dsn": f"redis://svc:{DSN_SECRET}@cache.example/0",
                    "provider_error": PREFIXED_API_KEY,
                },
            },
            headers={
                "Retry-After": "3",
                "Authorization": f"Bearer {BEARER_SECRET}",
                "X-Api-Key": PLAIN_SECRET,
            },
        )

    response = TestClient(app, raise_server_exceptions=False).get("/provider-error")
    payload = response.json()

    assert response.status_code == 400
    _assert_no_secret(payload)
    assert payload["params"]["api_key"] == "[REDACTED]"
    assert payload["details"] == payload["detail"]
    assert payload["details"]["dsn"] == "redis://[REDACTED]@cache.example/0"
    assert response.headers["retry-after"] == "3"
    assert "authorization" not in response.headers
    assert "x-api-key" not in response.headers
    _assert_no_secret(dict(response.headers))


def test_debug_log_formatter_never_bypasses_redaction() -> None:
    formatter = RelativePathFormatter("%(levelname)s %(message)s")
    record = logging.LogRecord(
        name="tests.security.debug",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg=(
            "provider debug api_key=%s Authorization: Bearer %s "
            "postgresql://svc:%s@db.example/prod"
        ),
        args=(PLAIN_SECRET, BEARER_SECRET, DSN_SECRET),
        exc_info=None,
    )

    rendered = formatter.format(record)

    _assert_no_secret(rendered)
    assert "DEBUG" in rendered
    assert "[REDACTED]" in rendered


def test_agent_trace_and_sse_boundaries_fail_closed_on_secrets() -> None:
    messages = [
        {"role": "user", "content": "current"},
        {
            "role": "assistant",
            "_trace_provider": "deepseek",
            "_trace_model": "deepseek/deepseek-chat",
            "reasoning_content": f"api_key={PLAIN_SECRET}",
            "tool_calls": [
                {
                    "id": "call-1",
                    "name": "echo",
                    "arguments": {"authorization": BEARER_SECRET},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call-1",
            "content": f"postgresql://svc:{DSN_SECRET}@db.example/prod",
        },
    ]

    turns, diagnostics = extract_provider_trace_turns(messages, baseline_len=1)
    public_event = sanitize_stream_event(
        {
            "type": "tool_done",
            "tool": "echo",
            "details": {
                "api_key": PLAIN_SECRET,
                "error": f"Authorization: Bearer {BEARER_SECRET}",
            },
        },
        trace_id="trace-sec2",
    )

    assert turns == []
    assert diagnostics.trace_dropped_reason == "sensitive_data_redacted"
    assert diagnostics.dropped_trace_count == 1
    _assert_no_secret(public_event)
    assert public_event["details"]["api_key"] == "[REDACTED]"


def test_diagnostics_snapshot_and_copy_export_share_central_redaction() -> None:
    token = activate_run_diagnostic_context(
        trace_id="trace-sec2-diagnostics",
        query_id="query-sec2-diagnostics",
        stock_code="600519",
    )
    try:
        record_llm_run(
            success=False,
            provider="test-provider",
            model="test-model",
            error_type="ProviderError",
            error_message=(
                f"api_key={PLAIN_SECRET} Authorization: Bearer {BEARER_SECRET} "
                f"postgresql://svc:{DSN_SECRET}@db.example/prod"
            ),
        )
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    summary = build_run_diagnostic_summary(
        context_snapshot={"diagnostics": snapshot},
        raw_result={
            "success": False,
            "error_message": f"webhook_url=https://hooks.example/{WEBHOOK_SECRET}",
        },
        report_saved=False,
    )

    _assert_no_secret(snapshot)
    _assert_no_secret(summary)
    assert "<redacted>" in summary["copy_text"]


def test_provider_and_tool_diagnostics_use_the_central_pattern_set() -> None:
    provider_error = (
        f"postgresql://svc:{DSN_SECRET}@db.example/prod "
        f"Authorization: Bearer {BEARER_SECRET}"
    )
    hermes = sanitize_hermes_error_text(provider_error)
    local_cli = redact_local_cli_text(
        f"{provider_error} opaque={OPAQUE_LOCAL_TOKEN}",
        limit=1000,
    )
    tool_audit = redact_diagnostic_value(
        {
            "api_key": PLAIN_SECRET,
            "provider_error": provider_error,
        }
    )
    alphasift = _sanitize_public_alphasift_diagnostics(
        {
            "api_key": PLAIN_SECRET,
            "provider_error": provider_error,
        }
    )

    _assert_no_secret(
        {
            "hermes": hermes,
            "local_cli": local_cli,
            "tool": tool_audit,
            "alphasift": alphasift,
        }
    )
    assert "db.example" in hermes
    assert "db.example" in local_cli
    assert redact_local_cli_text("already [REDACTED]") == "already [REDACTED]"
    assert alphasift["api_key"] == "[REDACTED]"
    assert redact_sensitive_text("ordinary provider failure") == "ordinary provider failure"
