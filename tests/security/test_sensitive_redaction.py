# -*- coding: utf-8 -*-
"""End-to-end sensitive-data redaction regressions for issue #176."""

from __future__ import annotations

import json
import logging

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.middlewares.error_handler import add_error_handlers
from api.v1.errors import error_body
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
        "digest_auth_error": (
            'Authorization: Digest username="operator", '
            f'realm="{PLAIN_SECRET}", nonce="{BEARER_SECRET}", '
            f'response="{WEBHOOK_SECRET}" public_status=401'
        ),
        "secondary_provider_error": (
            f"Cookie: session={PLAIN_SECRET}; csrf={BEARER_SECRET}; "
            f"webhook={WEBHOOK_SECRET} public_status=401"
        ),
        "dsn": f"postgresql://svc:{DSN_SECRET}@db.example:5432/prod",
        "username_only_dsn": f"redis://{PLAIN_SECRET}@cache.example/0",
        "username_only_srv_dsn": (
            f"mongodb+srv://{BEARER_SECRET}@cluster.example/prod"
        ),
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
    assert redacted["digest_auth_error"] == (
        "Authorization: [REDACTED] public_status=401"
    )
    assert redacted["secondary_provider_error"] == (
        "Cookie: [REDACTED] public_status=401"
    )
    assert redacted["dsn"] == "postgresql://[REDACTED]@db.example:5432/prod"
    assert redacted["username_only_dsn"] == "redis://[REDACTED]@cache.example/0"
    assert redacted["username_only_srv_dsn"] == (
        "mongodb+srv://[REDACTED]@cluster.example/prod"
    )
    assert redacted["callback"] == "[REDACTED_URL]"
    assert redacted["encoded_callback"] == "[REDACTED_URL]"
    assert redacted["public_url"] == "https://example.com/docs?lang=en"
    assert redacted["stock_code"] == "600519"


def test_cookie_redaction_masks_empty_and_quoted_delimiter_pairs_at_boundaries() -> None:
    empty_middle_pair = (
        f"Cookie: first=public; empty=; session={PLAIN_SECRET}; "
        f"csrf={BEARER_SECRET}"
    )
    quoted_delimiter_pair = (
        f'Cookie: marker="public;split"; csrf={WEBHOOK_SECRET} public=401'
    )
    quoted_next_pair = (
        f'Cookie: marker="public; next remains private"; '
        f"csrf={PLAIN_SECRET} public=401"
    )
    public_named_cookie_pair = (
        f"Cookie: session={PLAIN_SECRET}; public={BEARER_SECRET}"
    )
    quoted_assignment = (
        f'cookie=marker="public; next remains private"; '
        f"csrf={WEBHOOK_SECRET} next"
    )
    folded_cookie = (
        f"Cookie: session={PLAIN_SECRET};\r\n csrf={BEARER_SECRET}"
    )
    quoted_set_cookie = (
        f'Set-Cookie: marker="public;split;{WEBHOOK_SECRET}"; Path=/ next'
    )
    malformed_cookie = (
        f'Cookie: marker="open; next hidden; csrf={WEBHOOK_SECRET}'
    )
    malformed_set_cookie = (
        f'Set-Cookie: session={PLAIN_SECRET} public={WEBHOOK_SECRET}'
    )
    escaped_next_cookie = (
        f"Cookie: marker=public\\; next hidden; csrf={BEARER_SECRET}"
    )
    cookie_header_assignment = (
        f'cookie_header=marker="public; next remains private"; '
        f"csrf={PLAIN_SECRET} next"
    )
    set_cookie_header_assignment = (
        f'set_cookie_header=marker="public;split;{WEBHOOK_SECRET}"; '
        "Path=/ next"
    )
    prefixed_cookie_assignment = (
        f"provider_cookie_header=session={PLAIN_SECRET}; "
        f"csrf={BEARER_SECRET} next"
    )
    prefixed_set_cookie_assignment = (
        f"provider_set_cookie_header=session={PLAIN_SECRET}; Path=/; "
        f"private_session={WEBHOOK_SECRET} next"
    )

    assert redact_sensitive_text(empty_middle_pair) == "Cookie: [REDACTED]"
    assert redact_sensitive_text(quoted_delimiter_pair) == (
        "Cookie: [REDACTED] public=401"
    )
    assert redact_sensitive_text(quoted_next_pair) == (
        "Cookie: [REDACTED] public=401"
    )
    assert redact_sensitive_text(public_named_cookie_pair) == (
        "Cookie: [REDACTED]"
    )
    assert redact_sensitive_text(quoted_assignment) == (
        "cookie=[REDACTED] next"
    )
    assert redact_sensitive_text(folded_cookie) == "Cookie: [REDACTED]"
    assert redact_sensitive_text(quoted_set_cookie) == (
        "Set-Cookie: [REDACTED]; Path=/ next"
    )
    assert redact_sensitive_text(malformed_cookie) == "Cookie: [REDACTED]"
    assert redact_sensitive_text(malformed_set_cookie) == (
        "Set-Cookie: [REDACTED]"
    )
    assert redact_sensitive_text(escaped_next_cookie) == "Cookie: [REDACTED]"
    assert redact_sensitive_text(cookie_header_assignment) == (
        "cookie_header=[REDACTED] next"
    )
    assert redact_sensitive_text(set_cookie_header_assignment) == (
        "set_cookie_header=[REDACTED]; Path=/ next"
    )
    assert redact_sensitive_text(prefixed_cookie_assignment) == (
        "provider_cookie_header=[REDACTED] next"
    )
    assert redact_sensitive_text(prefixed_set_cookie_assignment) == (
        "provider_set_cookie_header=[REDACTED]"
    )

    api_payload = error_body(
        "provider_rejected",
        empty_middle_pair,
        details={"provider_diagnostic": quoted_delimiter_pair},
    )
    stream_payload = sanitize_stream_event(
        {
            "type": "tool_progress",
            "details": {
                "empty_diagnostic": empty_middle_pair,
                "quoted_diagnostic": quoted_delimiter_pair,
            },
        },
        trace_id="trace-cookie-grammar",
    )

    _assert_no_secret({"api": api_payload, "stream": stream_payload})
    assert api_payload["message"] == "Cookie: [REDACTED]"
    assert api_payload["details"]["provider_diagnostic"] == (
        "Cookie: [REDACTED] public=401"
    )
    assert stream_payload["details"] == {
        "empty_diagnostic": "Cookie: [REDACTED]",
        "quoted_diagnostic": "Cookie: [REDACTED] public=401",
    }


def test_digest_redaction_masks_extended_parameters_and_assignment_labels() -> None:
    digest_header = (
        "Authorization: Digest username*=UTF-8''operator, "
        f"realm={PLAIN_SECRET}, nonce={BEARER_SECRET}, "
        f"response={WEBHOOK_SECRET} public_status=401"
    )
    digest_assignment = (
        "authorization_header=Digest username*=UTF-8''operator, "
        f"realm={PLAIN_SECRET}, nonce={BEARER_SECRET}, "
        f"response={WEBHOOK_SECRET} public_status=401"
    )
    quoted_digest_assignment = (
        'authorization_header="Digest username*=UTF-8\'\'operator, '
        f"realm={PLAIN_SECRET}, response={WEBHOOK_SECRET}" + '" public_status=401'
    )
    quoted_basic_assignment = (
        f"provider_proxy_authorization_header='Basic {BEARER_SECRET}' next"
    )
    quoted_authorization_before_cookie = (
        f"provider_proxy_authorization_header='Basic {BEARER_SECRET}' next "
        f"Cookie: session={WEBHOOK_SECRET}"
    )
    malformed_quoted_assignment = (
        'authorization_header="Digest username=operator, '
        f"response={WEBHOOK_SECRET}"
    )
    quoted_public_marker = (
        'Authorization: Digest username="operator '
        f'public_status={PLAIN_SECRET}", realm={BEARER_SECRET}, '
        f"response={WEBHOOK_SECRET} public_status=401"
    )
    public_named_digest_parameter = (
        "Authorization: Digest username=operator, "
        f"public={PLAIN_SECRET}, response={WEBHOOK_SECRET}"
    )
    folded_digest_header = (
        "Authorization: Digest username=operator,\r\n "
        f"response={WEBHOOK_SECRET}"
    )
    malformed_digest_header = (
        'Authorization: Digest username="open '
        f"public_status={PLAIN_SECRET}, response={WEBHOOK_SECRET}"
    )

    assert redact_sensitive_text(digest_header) == (
        "Authorization: [REDACTED] public_status=401"
    )
    assert redact_sensitive_text(digest_assignment) == (
        "authorization_header=[REDACTED] public_status=401"
    )
    assert redact_sensitive_text(quoted_digest_assignment) == (
        "authorization_header=[REDACTED] public_status=401"
    )
    assert redact_sensitive_text(quoted_basic_assignment) == (
        "provider_proxy_authorization_header=[REDACTED] next"
    )
    assert redact_sensitive_text(quoted_authorization_before_cookie) == (
        "provider_proxy_authorization_header=[REDACTED] next "
        "Cookie: [REDACTED]"
    )
    assert redact_sensitive_text(malformed_quoted_assignment) == (
        "authorization_header=[REDACTED]"
    )
    assert redact_sensitive_text(quoted_public_marker) == (
        "Authorization: [REDACTED] public_status=401"
    )
    assert redact_sensitive_text(public_named_digest_parameter) == (
        "Authorization: [REDACTED]"
    )
    assert redact_sensitive_text(folded_digest_header) == (
        "Authorization: [REDACTED]"
    )
    assert redact_sensitive_text(malformed_digest_header) == (
        "Authorization: [REDACTED]"
    )

    api_payload = error_body(
        "provider_rejected",
        digest_header,
        details={"provider_diagnostic": digest_assignment},
    )
    formatter = RelativePathFormatter("%(levelname)s %(message)s")
    record = logging.LogRecord(
        name="tests.security.digest",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg=quoted_digest_assignment,
        args=(),
        exc_info=None,
    )
    rendered_log = formatter.format(record)

    _assert_no_secret({"api": api_payload, "log": rendered_log})
    assert api_payload["message"] == (
        "Authorization: [REDACTED] public_status=401"
    )
    assert api_payload["details"]["provider_diagnostic"] == (
        "authorization_header=[REDACTED] public_status=401"
    )
    assert "authorization_header=[REDACTED] public_status=401" in rendered_log


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


def test_provider_trace_drops_hostile_equality_spoof_before_persistence() -> None:
    class EqualitySpoof:
        def __str__(self) -> str:
            return f"api_key={PLAIN_SECRET}"

        def __eq__(self, _other: object) -> bool:
            return True

    messages = [
        {"role": "user", "content": "current"},
        {
            "role": "assistant",
            "_trace_provider": "deepseek",
            "_trace_model": "deepseek/deepseek-chat",
            "reasoning_content": EqualitySpoof(),
            "tool_calls": [
                {
                    "id": "call-hostile",
                    "name": "echo",
                    "arguments": {"message": "public"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call-hostile",
            "content": "public result",
        },
    ]

    turns, diagnostics = extract_provider_trace_turns(messages, baseline_len=1)

    assert turns == []
    assert diagnostics.trace_dropped_reason == "sensitive_data_redacted"
    assert diagnostics.dropped_trace_count == 1


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
