# -*- coding: utf-8 -*-
"""End-to-end sensitive-data redaction regressions for issue #176."""

from __future__ import annotations

import json
import logging
import time
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.middlewares.error_handler import add_error_handlers
from api.v1.errors import error_body
from src.agent import executor as executor_module
from src.agent.llm_adapter import ToolCall
from src.agent.provider_trace import extract_provider_trace_turns
from src.agent.public_contract import sanitize_stream_event
from src.agent.runner import _execute_tools
from src.agent.tools.execution import (
    ToolAccessContext,
    build_tool_audit,
    redact_diagnostic_value,
)
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
from src.utils import sanitize as sanitize_module
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
    malformed_structural_cookie = (
        f"Cookie: session={PLAIN_SECRET}}} other={WEBHOOK_SECRET}"
    )
    injected_marker_cookie = (
        f"Cookie: [REDACTED]; session={PLAIN_SECRET}"
    )
    injected_marker_cookie_closer = (
        f"Cookie: [REDACTED]}} session={BEARER_SECRET}"
    )
    injected_set_cookie_marker = (
        f"Set-Cookie: [REDACTED]; session={WEBHOOK_SECRET}"
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
    assert redact_sensitive_text(malformed_structural_cookie) == (
        "Cookie: [REDACTED]"
    )
    assert redact_sensitive_text(injected_marker_cookie) == "Cookie: [REDACTED]"
    assert redact_sensitive_text(injected_marker_cookie_closer) == (
        "Cookie: [REDACTED]"
    )
    assert redact_sensitive_text(injected_set_cookie_marker) == (
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
        "provider_set_cookie_header=[REDACTED] next"
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
        'authorization_header="[REDACTED]" public_status=401'
    )
    assert redact_sensitive_text(quoted_basic_assignment) == (
        "provider_proxy_authorization_header='[REDACTED]' next"
    )
    assert redact_sensitive_text(quoted_authorization_before_cookie) == (
        "provider_proxy_authorization_header='[REDACTED]' next "
        "Cookie: [REDACTED]"
    )
    assert redact_sensitive_text(malformed_quoted_assignment) == (
        'authorization_header="[REDACTED]"'
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
    assert 'authorization_header="[REDACTED]" public_status=401' in rendered_log


def test_authorization_redaction_handles_escaped_and_unknown_schemes() -> None:
    escaped_assignment = (
        rf'authorization_header=\"Basic {PLAIN_SECRET}\" next'
    )
    escaped_json_fragment = (
        rf'{{\"authorization_header\":\"Basic {BEARER_SECRET}\"}}'
    )
    unknown_scheme = (
        "Authorization: AWS4-HMAC-SHA256 "
        "Credential=operator/20260722/us-east-1/service/aws4_request, "
        "SignedHeaders=host;x-date, "
        f"Signature={WEBHOOK_SECRET} public_status=403"
    )

    assert redact_sensitive_text(escaped_assignment) == (
        "authorization_header=[REDACTED] next"
    )
    escaped_json_redacted = redact_sensitive_text(escaped_json_fragment)
    assert escaped_json_redacted == redact_sensitive_text(escaped_json_redacted)
    assert "authorization_header" in escaped_json_redacted
    assert "[REDACTED]" in escaped_json_redacted
    assert redact_sensitive_text(unknown_scheme) == (
        "Authorization: [REDACTED] public_status=403"
    )

    api_payload = error_body(
        "provider_rejected",
        escaped_assignment,
        details={"provider_diagnostic": escaped_json_fragment},
    )
    stream_payload = sanitize_stream_event(
        {
            "type": "tool_progress",
            "details": {"provider_diagnostic": unknown_scheme},
        },
        trace_id="trace-authorization-grammar",
    )
    formatter = RelativePathFormatter("%(levelname)s %(message)s")
    record = logging.LogRecord(
        name="tests.security.authorization",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg=unknown_scheme,
        args=(),
        exc_info=None,
    )
    rendered_log = formatter.format(record)

    _assert_no_secret(
        {"api": api_payload, "stream": stream_payload, "log": rendered_log}
    )
    assert api_payload["message"] == "authorization_header=[REDACTED] next"
    assert stream_payload["details"]["provider_diagnostic"] == (
        "Authorization: [REDACTED] public_status=403"
    )
    assert "Authorization: [REDACTED] public_status=403" in rendered_log


def test_authorization_review_counterexamples_fail_closed_across_boundaries() -> None:
    spaced_parameters = (
        'Authorization: Digest username = "operator", '
        f'response = "{WEBHOOK_SECRET}"'
    )
    injected_marker = (
        "Authorization: Digest realm=public [REDACTED_URL] "
        f"response={WEBHOOK_SECRET}"
    )
    injected_structural_closer = (
        "Authorization: Digest realm=public} "
        f"response={WEBHOOK_SECRET}"
    )
    escaped_public_label = (
        rf'{{\"authorization_header\":\"Basic dG9rZW4 '
        rf'public_status={WEBHOOK_SECRET}\"}}'
    )
    twice_escaped = (
        rf'{{\\"authorization_header\\":\\"Basic {WEBHOOK_SECRET}\\"}}'
    )
    escaped_with_sibling = (
        rf'{{\"authorization_header\":\"Basic {WEBHOOK_SECRET}\", '
        r'\"note\":\"public\"}'
    )
    escaped_array_fragment = (
        rf'[\"authorization_header\":\"Basic {WEBHOOK_SECRET}\"]'
    )
    unknown_scheme = "Authorization: Weird alpha beta gamma"
    marker_prefix_assignment = f"api_key=[REDACTED]{WEBHOOK_SECRET}"
    punctuated_marker_assignment = (
        f"api_key=[REDACTED].{WEBHOOK_SECRET}"
    )
    escaped_marker_assignment = (
        rf'api_key=\"[REDACTED]/{WEBHOOK_SECRET}\"'
    )
    escaped_sensitive_key = (
        rf'{{\"api_key\":\"{WEBHOOK_SECRET}\"}}'
    )
    injected_redaction_marker = (
        f"Authorization: [REDACTED], response={WEBHOOK_SECRET}"
    )
    bare_marker_suffix = (
        f"Authorization: [REDACTED] {WEBHOOK_SECRET}"
    )
    punctuated_marker_suffix = (
        f"Authorization: [REDACTED]. {WEBHOOK_SECRET}"
    )
    url_marker_parameter_suffix = (
        "Authorization: [REDACTED] [REDACTED_URL] "
        f"response={WEBHOOK_SECRET}"
    )
    token_parameter_names = (
        "Authorization: Weird 1foo=public, "
        f"2bar={WEBHOOK_SECRET}"
    )
    malformed_multiword = (
        f"Authorization: Weird alpha beta={WEBHOOK_SECRET}"
    )
    malformed_public_boundary = (
        "Authorization: Digest realm=public "
        f"public_status={WEBHOOK_SECRET}"
    )
    malformed_cookie_boundary = (
        f"Cookie: session=first-token next {WEBHOOK_SECRET}"
    )

    expected = {
        spaced_parameters: "Authorization: [REDACTED]",
        injected_marker: "Authorization: [REDACTED]",
        injected_structural_closer: "Authorization: [REDACTED]",
        escaped_public_label: (
            r'{\"authorization_header\":[REDACTED]}'
        ),
        twice_escaped: (
            r'{\\"authorization_header\\":[REDACTED]}'
        ),
        escaped_with_sibling: (
            r'{\"authorization_header\":[REDACTED], '
            r'\"note\":\"public\"}'
        ),
        escaped_array_fragment: (
            r'[\"authorization_header\":[REDACTED]]'
        ),
        unknown_scheme: "Authorization: [REDACTED]",
        marker_prefix_assignment: "api_key=[REDACTED]",
        punctuated_marker_assignment: "api_key=[REDACTED]",
        escaped_marker_assignment: "api_key=[REDACTED]",
        escaped_sensitive_key: r'{\"api_key\":[REDACTED]}',
        injected_redaction_marker: "Authorization: [REDACTED]",
        bare_marker_suffix: "Authorization: [REDACTED]",
        punctuated_marker_suffix: "Authorization: [REDACTED]",
        url_marker_parameter_suffix: "Authorization: [REDACTED]",
        token_parameter_names: "Authorization: [REDACTED]",
        malformed_multiword: "Authorization: [REDACTED]",
        malformed_public_boundary: "Authorization: [REDACTED]",
        malformed_cookie_boundary: "Cookie: [REDACTED]",
    }
    for raw, redacted in expected.items():
        assert redact_sensitive_text(raw) == redacted
        assert redact_sensitive_text(redacted) == redacted

    api_payload = error_body(
        "provider_rejected",
        spaced_parameters,
        details={"provider_diagnostic": twice_escaped},
    )
    stream_payload = sanitize_stream_event(
        {
            "type": "tool_progress",
            "details": {
                "marker_diagnostic": injected_marker,
                "escaped_diagnostic": escaped_public_label,
            },
        },
        trace_id="trace-authorization-review-counterexamples",
    )
    formatter = RelativePathFormatter("%(levelname)s %(message)s")
    record = logging.LogRecord(
        name="tests.security.authorization_review",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg=escaped_public_label,
        args=(),
        exc_info=None,
    )

    _assert_no_secret(
        {
            "api": api_payload,
            "stream": stream_payload,
            "log": formatter.format(record),
        }
    )


def test_marker_punctuation_cannot_hide_labelled_secrets_across_boundaries() -> None:
    marker_injection = f"api_key=[REDACTED].{PLAIN_SECRET}"
    escaped_injection = rf'api_key=\"[REDACTED]/{BEARER_SECRET}\"'
    serialized = json.dumps({"diagnostic": marker_injection})

    redacted = redact_sensitive_text(marker_injection)
    escaped_redacted = redact_sensitive_text(escaped_injection)
    serialized_redacted = redact_sensitive_text(serialized)
    api_payload = error_body(
        "provider_rejected",
        marker_injection,
        details={"provider_diagnostic": escaped_injection},
    )
    stream_payload = sanitize_stream_event(
        {
            "type": "tool_progress",
            "details": {"provider_diagnostic": marker_injection},
        },
        trace_id="trace-marker-punctuation",
    )
    formatter = RelativePathFormatter("%(levelname)s %(message)s")
    record = logging.LogRecord(
        name="tests.security.marker_punctuation",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg=escaped_injection,
        args=(),
        exc_info=None,
    )
    tool_audit = redact_diagnostic_value({"diagnostic": marker_injection})
    local_cli = redact_local_cli_text(marker_injection, limit=1000)
    messages = [
        {"role": "user", "content": "current"},
        {
            "role": "assistant",
            "_trace_provider": "deepseek",
            "_trace_model": "deepseek/deepseek-chat",
            "reasoning_content": marker_injection,
            "tool_calls": [
                {
                    "id": "call-marker",
                    "name": "echo",
                    "arguments": {"message": "public"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call-marker",
            "content": "public result",
        },
    ]
    turns, diagnostics = extract_provider_trace_turns(messages, baseline_len=1)

    _assert_no_secret(
        {
            "redacted": redacted,
            "escaped": escaped_redacted,
            "serialized": serialized_redacted,
            "api": api_payload,
            "stream": stream_payload,
            "log": formatter.format(record),
            "tool": tool_audit,
            "local_cli": local_cli,
        }
    )
    assert redacted == "api_key=[REDACTED]"
    assert escaped_redacted == "api_key=[REDACTED]"
    assert redact_sensitive_text(
        f"api_key={PLAIN_SECRET} operation=context-probe"
    ) == "api_key=[REDACTED] operation=context-probe"
    assert redact_sensitive_text(serialized_redacted) == serialized_redacted
    assert turns == []
    assert diagnostics.trace_dropped_reason == "sensitive_data_redacted"


def test_final_review_field_scanner_counterexamples_fail_closed() -> None:
    cases = {
        (
            f'Cookie: "first=public"; csrf={PLAIN_SECRET}'
        ): 'Cookie: "[REDACTED]"',
        (
            rf'Cookie: \"first=public\"; csrf={BEARER_SECRET}'
        ): "Cookie: [REDACTED]",
        (
            f'Set-Cookie: "id=public", session={WEBHOOK_SECRET}'
        ): 'Set-Cookie: "[REDACTED]"',
        (
            f'Cookie: "[REDACTED]"; csrf={PLAIN_SECRET}'
        ): 'Cookie: "[REDACTED]"',
        (
            f"Authorization: [REDACTED], {BEARER_SECRET}"
        ): "Authorization: [REDACTED]",
        (
            f"api_key=[REDACTED],{WEBHOOK_SECRET}"
        ): "api_key=[REDACTED]",
        (
            "Authorization: Digest realm=private <- RuntimeError: "
            f"response={PLAIN_SECRET}"
        ): "Authorization: [REDACTED]",
        (
            f"Cookie: first=private <- RuntimeError: csrf={BEARER_SECRET}"
        ): "Cookie: [REDACTED]",
        (
            "Authorization: Weird alpha "
            f"https://example.com/{WEBHOOK_SECRET}"
        ): "Authorization: [REDACTED]",
        (
            f"dsn=1postgresql://svc:{DSN_SECRET}@db.example/prod"
        ): "dsn=1postgresql://[REDACTED]@db.example/prod",
        (
            f"dsn=9-postgresql://svc:{DSN_SECRET}@db.example/prod"
        ): "dsn=9-postgresql://[REDACTED]@db.example/prod",
        f"asset_cookie={PLAIN_SECRET}": "asset_cookie=[REDACTED]",
        f"offset_cookie={BEARER_SECRET}": "offset_cookie=[REDACTED]",
        f"reset_cookie={WEBHOOK_SECRET}": "reset_cookie=[REDACTED]",
        f"openaiApiKey={PLAIN_SECRET}": "openaiApiKey=[REDACTED]",
        f"myAccessToken={BEARER_SECRET}": "myAccessToken=[REDACTED]",
    }

    for raw, expected in cases.items():
        redacted = redact_sensitive_text(raw)

        assert redacted == expected
        assert redact_sensitive_text(redacted) == redacted
        _assert_no_secret(redacted)

    structural_suffix_injection = (
        rf'{{\"authorization_header\":\"[REDACTED]\"}}; '
        rf'csrf={WEBHOOK_SECRET}'
    )
    structural_redacted = redact_sensitive_text(structural_suffix_injection)

    _assert_no_secret(structural_redacted)
    assert redact_sensitive_text(structural_redacted) == structural_redacted


def test_final_review_counterexamples_are_closed_at_every_output_boundary() -> None:
    hostile = f'Cookie: "[REDACTED]"; csrf={WEBHOOK_SECRET}'
    labelled = f"asset_cookie={PLAIN_SECRET}"
    api_payload = error_body(
        "provider_rejected",
        hostile,
        details={"provider_diagnostic": labelled},
    )
    stream_payload = sanitize_stream_event(
        {
            "type": "tool_progress",
            "details": {
                "cookie_diagnostic": hostile,
                "labelled_diagnostic": labelled,
            },
        },
        trace_id="trace-final-review-counterexamples",
    )
    formatter = RelativePathFormatter("%(levelname)s %(message)s")
    record = logging.LogRecord(
        name="tests.security.final_review",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg=hostile,
        args=(),
        exc_info=None,
    )
    tool_audit = redact_diagnostic_value({"diagnostic": hostile})
    local_cli = redact_local_cli_text(hostile, limit=1000)
    hermes = sanitize_hermes_error_text(labelled)
    alphasift = _sanitize_public_alphasift_diagnostics(
        {"provider_error": hostile}
    )

    diagnostic_token = activate_run_diagnostic_context(
        trace_id="trace-final-review-diagnostics",
        query_id="query-final-review-diagnostics",
        stock_code="600519",
    )
    try:
        record_llm_run(
            success=False,
            provider="test-provider",
            model="test-model",
            error_type="ProviderError",
            error_message=hostile,
        )
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(diagnostic_token)

    messages = [
        {"role": "user", "content": "current"},
        {
            "role": "assistant",
            "_trace_provider": "deepseek",
            "_trace_model": "deepseek/deepseek-chat",
            "reasoning_content": hostile,
            "tool_calls": [
                {
                    "id": "call-final-review",
                    "name": "echo",
                    "arguments": {"message": "public"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call-final-review",
            "content": "public result",
        },
    ]
    turns, diagnostics = extract_provider_trace_turns(messages, baseline_len=1)

    _assert_no_secret(
        {
            "api": api_payload,
            "stream": stream_payload,
            "log": formatter.format(record),
            "tool": tool_audit,
            "local_cli": local_cli,
            "hermes": hermes,
            "alphasift": alphasift,
            "snapshot": snapshot,
        }
    )
    assert turns == []
    assert diagnostics.trace_dropped_reason == "sensitive_data_redacted"


def test_composite_text_labels_share_mapping_classification_across_boundaries() -> None:
    labelled_secrets = {
        "api.key": PLAIN_SECRET,
        "api key": BEARER_SECRET,
        "private.key": DSN_SECRET,
        "webhook.url": WEBHOOK_SECRET,
        "proxy.url": PREFIXED_API_KEY,
        "raw.response": OPAQUE_LOCAL_TOKEN,
        "request.headers.raw": PLAIN_SECRET,
        "license/key": BEARER_SECRET,
        "private$key": DSN_SECRET,
        "api&key": WEBHOOK_SECRET,
        "api,key": PLAIN_SECRET,
        "api:key": BEARER_SECRET,
        "api(key": DSN_SECRET,
        "api]key": WEBHOOK_SECRET,
        r"api\key": PREFIXED_API_KEY,
        "api\u00a0key": PLAIN_SECRET,
        "api·key": BEARER_SECRET,
        "api🔐key": DSN_SECRET,
    }

    for label, secret in labelled_secrets.items():
        assert sanitize_module.is_sensitive_key(label)
        raw = f"{label}={secret}"
        expected = f"{label}=[REDACTED]"

        assert redact_sensitive_text(raw) == expected
        assert redact_sensitive_text(expected) == expected

    long_label = (
        "api.key."
        + ".".join(["filler"] * sanitize_module._TEXT_FIELD_KEY_PART_LIMIT)
        + ".value"
    )
    assert sanitize_module.is_sensitive_key(long_label)
    assert redact_sensitive_text(
        f"{long_label}=alpha {PLAIN_SECRET}"
    ) == f"{long_label}=[REDACTED]"

    raw = rf"api\key={PLAIN_SECRET}"
    spaced = f"private key={BEARER_SECRET}"
    api_payload = error_body(
        "provider_rejected",
        raw,
        details={"provider_diagnostic": spaced},
    )
    stream_payload = sanitize_stream_event(
        {
            "type": "tool_progress",
            "details": {
                "dotted_diagnostic": raw,
                "spaced_diagnostic": spaced,
            },
        },
        trace_id="trace-composite-labels",
    )
    formatter = RelativePathFormatter("%(levelname)s %(message)s")
    record = logging.LogRecord(
        name="tests.security.composite_labels",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg=raw,
        args=(),
        exc_info=None,
    )
    tool_preview = redact_diagnostic_value({"diagnostic": raw})
    local_cli = redact_local_cli_text(raw, limit=1000)
    hermes = sanitize_hermes_error_text(spaced)
    alphasift = _sanitize_public_alphasift_diagnostics(
        {"provider_error": raw}
    )

    diagnostic_token = activate_run_diagnostic_context(
        trace_id="trace-composite-label-diagnostics",
        query_id="query-composite-label-diagnostics",
        stock_code="600519",
    )
    try:
        record_llm_run(
            success=False,
            provider="test-provider",
            model="test-model",
            error_type="ProviderError",
            error_message=raw,
        )
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(diagnostic_token)

    messages = [
        {"role": "user", "content": "current"},
        {
            "role": "assistant",
            "_trace_provider": "deepseek",
            "_trace_model": "deepseek/deepseek-chat",
            "reasoning_content": raw,
            "tool_calls": [
                {
                    "id": "call-composite-label",
                    "name": "echo",
                    "arguments": {"message": "public"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call-composite-label",
            "content": "public result",
        },
    ]
    turns, diagnostics = extract_provider_trace_turns(messages, baseline_len=1)

    _assert_no_secret(
        {
            "api": api_payload,
            "stream": stream_payload,
            "log": formatter.format(record),
            "tool": tool_preview,
            "local_cli": local_cli,
            "hermes": hermes,
            "alphasift": alphasift,
            "snapshot": snapshot,
        }
    )
    assert turns == []
    assert diagnostics.trace_dropped_reason == "sensitive_data_redacted"


def test_prose_prefixed_diagnostic_fields_survive_composite_key_walk() -> None:
    """Long prose prefixes must not swallow structured diagnostic values.

    Regression: the composite-key walker previously fail-closed to
    "authorization" whenever it hit its 16-part budget, or matched a single
    sensitive word from an ambiguous log prefix. Both paths redacted the
    trailing ``key=value`` in ordinary log lines such as debug messages and
    retry summaries, hiding diagnostic fields the operator relies on. The
    ambiguous webhook prefix is fixed at its call site so the central
    sanitizer retains fail-closed text/mapping classification parity.
    """

    prose_cases = {
        "Vision provider call failed; retrying error_code=vision_provider_failed"
        " model=gemini/gemini-3.1-pro-preview attempt=1/3 retry_delay_seconds=1"
        " exception_type=RuntimeError": (
            "error_code=vision_provider_failed",
            "exception_type=RuntimeError",
        ),
        "[BotHandler] Parsed request: body_bytes=181": (
            "body_bytes=181",
        ),
        "File logging initialization failed; using console output."
        " Check Docker mount permissions, read-only mounts, rootless Docker, NFS,"
        " or --user restrictions error_code=main_file_logging_setup_failed"
        " log_dir=/app/logs exception_type=PermissionError": (
            "error_code=main_file_logging_setup_failed",
            "log_dir=/app/logs",
            "exception_type=PermissionError",
        ),
    }
    for message, expected_survivors in prose_cases.items():
        sanitized = sanitize_module.sanitize_diagnostic_text(
            message,
            max_length=4000,
        )
        for expected in expected_survivors:
            assert expected in sanitized, (message, expected, sanitized)

    # Canonical multi-word compounds (``api key``, ``private key``, etc.) and
    # structural long-compound keys (``api.key.filler.…value``) must still
    # redact so PR #508's contract is not weakened.
    assert sanitize_module.sanitize_diagnostic_text(
        "api key=hunter2"
    ) == "api key=[REDACTED]"
    assert sanitize_module.sanitize_diagnostic_text(
        "session token=hunter2"
    ) == "session token=[REDACTED]"
    assert sanitize_module.sanitize_diagnostic_text(
        "api: key=hunter2"
    ) == "api: key=[REDACTED]"
    long_label = (
        "api.key."
        + ".".join(["filler"] * sanitize_module._TEXT_FIELD_KEY_PART_LIMIT)
        + ".value"
    )
    assert sanitize_module.sanitize_diagnostic_text(
        f"{long_label}=hunter2"
    ) == f"{long_label}=[REDACTED]"

    # Whitespace alone does not make a sensitive compound prose. Text labels
    # must retain the same fail-closed classification as mapping keys even
    # when the value is too short for token-pattern fallback redaction.
    for label in (
        "password value",
        "token value",
        "webhook signing",
        "authorization value",
    ):
        assert sanitize_module.is_sensitive_key(label)
        assert sanitize_module.sanitize_diagnostic_text(
            f"{label}=hunter2"
        ) == f"{label}=[REDACTED]"
    assert sanitize_module.sanitize_diagnostic_text(
        "password value: hunter2"
    ) == "password value: [REDACTED]"

    punctuation_labels = {
        "password label: value=hunter2": "password label: [REDACTED]",
        "token label; value=hunter2": "token label; value=[REDACTED]",
        "webhook signing, value=hunter2": (
            "webhook signing, value=[REDACTED]"
        ),
        "authorization label. value=hunter2": (
            "authorization label. value=[REDACTED]"
        ),
        "credential label! value=hunter2": (
            "credential label! value=[REDACTED]"
        ),
        "secret label? value=hunter2": "secret label? value=[REDACTED]",
    }
    for raw, expected in punctuation_labels.items():
        assert sanitize_module.sanitize_diagnostic_text(raw) == expected


def test_generic_fields_reject_ambiguous_delimiter_suffixes() -> None:
    for delimiter in ",;&)]}":
        raw = f"password={delimiter}{PLAIN_SECRET}"
        redacted = redact_sensitive_text(raw)

        assert redacted == "password=[REDACTED]"
        assert redact_sensitive_text(redacted) == redacted
        _assert_no_secret(redacted)

    for closer in ")]}":
        raw = f"password={closer},note={PLAIN_SECRET}"
        structured = f'{{"password":{closer},note={BEARER_SECRET}'

        assert redact_sensitive_text(raw) == "password=[REDACTED]"
        assert redact_sensitive_text(structured) == '{"password":[REDACTED]'
        assert redact_sensitive_text(
            redact_sensitive_text(raw)
        ) == "password=[REDACTED]"

    assert redact_sensitive_text(
        f"api_key={PLAIN_SECRET} operation=context-probe"
    ) == "api_key=[REDACTED] operation=context-probe"


def test_http_credentials_include_delimiters_before_sensitivity_is_evaluated() -> None:
    for delimiter in ",;)]}":
        raw = (
            "https://example.com/callback?access_token=alpha"
            f"{delimiter}{PLAIN_SECRET}"
        )

        assert redact_sensitive_text(raw) == "[REDACTED_URL]"
        assert sanitize_module.sanitize_diagnostic_text(
            raw,
            max_length=1000,
        ) == "[REDACTED_URL]"

    userinfo = (
        f"https://operator:alpha,{BEARER_SECRET}@example.com/path"
    )
    assert redact_sensitive_text(userinfo) == "[REDACTED_URL]"
    assert sanitize_module.sanitize_diagnostic_text(
        userinfo,
        max_length=1000,
    ) == "[REDACTED_URL]"
    assert redact_sensitive_text(
        "https://example.com/docs,"
    ) == "https://example.com/docs,"
    assert redact_sensitive_text(
        "https://example.com/path?authorization=private"
    ) == "[REDACTED_URL]"


def test_http_urls_classify_structural_suffixes_and_nested_encoding() -> None:
    for delimiter in ",;)]}":
        raw = (
            "https://example.invalid/docs"
            f"{delimiter}api_key={PLAIN_SECRET}"
        )

        assert redact_sensitive_text(raw) == "[REDACTED_URL]"
        assert redact_sensitive_text(redact_sensitive_text(raw)) == (
            "[REDACTED_URL]"
        )

    cases = (
        f"https://example.invalid/docs;private.key={BEARER_SECRET}",
        f"https://example.invalid/docs)webhook.url={WEBHOOK_SECRET}",
        f"https://example.test/callback?public=1;api_key={PLAIN_SECRET}",
        f"https://example.test/callback#public=1;access_token={BEARER_SECRET}",
        f"https://example.test/callback?%25252561pi_key={DSN_SECRET}",
        f"https://example.test/%252577ebhook/{WEBHOOK_SECRET}",
    )

    for raw in cases:
        assert redact_sensitive_text(raw) == "[REDACTED_URL]"
        assert sanitize_module.sanitize_diagnostic_text(
            raw,
            max_length=1000,
        ) == "[REDACTED_URL]"

    encoded_key = "%61pi_key"
    for _ in range(sanitize_module._URL_COMPONENT_DECODE_LIMIT + 1):
        encoded_key = quote(encoded_key, safe="")
    over_encoded = (
        f"https://example.test/callback?{encoded_key}={PREFIXED_API_KEY}"
    )

    assert redact_sensitive_text(over_encoded) == "[REDACTED_URL]"
    assert redact_sensitive_text(
        "https://example.test/docs;version=1,stable"
    ) == "https://example.test/docs;version=1,stable"


def test_url_review_counterexamples_are_closed_at_final_output_boundaries() -> None:
    hostile_urls = (
        f"https://example.invalid/docs,api_key={PLAIN_SECRET}",
        f"https://example.test/callback?public=1;access_token={BEARER_SECRET}",
        f"https://example.test/%252577ebhook/{WEBHOOK_SECRET}",
    )
    diagnostic = " ".join(hostile_urls)
    api_payload = error_body(
        "provider_rejected",
        diagnostic,
        details={"provider_urls": list(hostile_urls)},
    )
    stream_payload = sanitize_stream_event(
        {
            "type": "tool_progress",
            "details": {"provider_urls": list(hostile_urls)},
        },
        trace_id="trace-url-review-counterexamples",
    )
    formatter = RelativePathFormatter("%(levelname)s %(message)s")
    record = logging.LogRecord(
        name="tests.security.url_review",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg=diagnostic,
        args=(),
        exc_info=None,
    )
    tool_preview = redact_diagnostic_value({"provider_urls": list(hostile_urls)})
    local_cli = redact_local_cli_text(diagnostic, limit=2000)
    hermes = sanitize_hermes_error_text(diagnostic)
    alphasift = _sanitize_public_alphasift_diagnostics(
        {"provider_error": diagnostic}
    )

    diagnostic_token = activate_run_diagnostic_context(
        trace_id="trace-url-review-diagnostics",
        query_id="query-url-review-diagnostics",
        stock_code="600519",
    )
    try:
        record_llm_run(
            success=False,
            provider="test-provider",
            model="test-model",
            error_type="ProviderError",
            error_message=diagnostic,
        )
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(diagnostic_token)

    messages = [
        {"role": "user", "content": "current"},
        {
            "role": "assistant",
            "_trace_provider": "deepseek",
            "_trace_model": "deepseek/deepseek-chat",
            "reasoning_content": diagnostic,
            "tool_calls": [
                {
                    "id": "call-url-review",
                    "name": "echo",
                    "arguments": {"message": "public"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call-url-review",
            "content": "public result",
        },
    ]
    turns, diagnostics = extract_provider_trace_turns(messages, baseline_len=1)

    _assert_no_secret(
        {
            "api": api_payload,
            "stream": stream_payload,
            "log": formatter.format(record),
            "tool": tool_preview,
            "local_cli": local_cli,
            "hermes": hermes,
            "alphasift": alphasift,
            "snapshot": snapshot,
        }
    )
    assert turns == []
    assert diagnostics.trace_dropped_reason == "sensitive_data_redacted"


def test_tool_audit_recursively_redacts_identity_and_error_fields() -> None:
    audit = build_tool_audit(
        tool_name=f"api.key={PLAIN_SECRET}",
        arguments={"query": "public"},
        result={"status": "public"},
        error_code=f"private.key={BEARER_SECRET}",
        context=ToolAccessContext(
            backend=f"proxy.url={DSN_SECRET}",
            session_id=f"raw.response={WEBHOOK_SECRET}",
            audit_context={"webhook.url": PREFIXED_API_KEY},
        ),
    )

    _assert_no_secret(audit)
    assert audit["tool_name"] == "api.key=[REDACTED]"
    assert audit["error_code"] == "private.key=[REDACTED]"
    assert audit["backend"] == "proxy.url=[REDACTED]"
    assert audit["session_id"] == "raw.response=[REDACTED]"


def test_provider_trace_drops_every_secret_bearing_identity_before_persistence(
    monkeypatch,
) -> None:
    def messages_for(
        *,
        provider: str = "deepseek",
        model: str = "deepseek/deepseek-chat",
        tool_call_id: str = "call-public",
        tool_name: str = "echo",
        tool_result_id: str | None = None,
    ) -> list[dict]:
        return [
            {"role": "user", "content": "current"},
            {
                "role": "assistant",
                "_trace_provider": provider,
                "_trace_model": model,
                "reasoning_content": "public reasoning",
                "tool_calls": [
                    {
                        "id": tool_call_id,
                        "name": tool_name,
                        "arguments": {"message": "public"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": tool_result_id or tool_call_id,
                "content": "public result",
            },
        ]

    cases = (
        (
            messages_for(provider=f"deepseek/api_key={PLAIN_SECRET}"),
            "session-public",
            "run-public",
        ),
        (
            messages_for(model=f"deepseek/model/api_key={BEARER_SECRET}"),
            "session-public",
            "run-public",
        ),
        (
            messages_for(),
            f"api_key={DSN_SECRET}",
            "run-public",
        ),
        (
            messages_for(),
            "session-public",
            f"access_token={WEBHOOK_SECRET}",
        ),
        (
            messages_for(tool_call_id=f"api_key={PLAIN_SECRET}"),
            "session-public",
            "run-public",
        ),
        (
            messages_for(tool_name=f"access_token={BEARER_SECRET}"),
            "session-public",
            "run-public",
        ),
        (
            messages_for(tool_result_id=f"private_key={DSN_SECRET}"),
            "session-public",
            "run-public",
        ),
    )

    for messages, session_id, run_id in cases:
        turns, diagnostics = extract_provider_trace_turns(
            messages,
            baseline_len=1,
            session_id=session_id,
            run_id=run_id,
        )

        assert turns == []
        assert diagnostics.trace_dropped_reason == "sensitive_data_redacted"
        assert diagnostics.dropped_trace_count == 1

    safe_turns, safe_diagnostics = extract_provider_trace_turns(
        messages_for(),
        baseline_len=1,
        session_id="session-public",
        run_id="run-public",
    )

    assert safe_diagnostics.trace_dropped_reason == ""
    assert len(safe_turns) == 1
    assert safe_turns[0].session_id == "session-public"
    assert safe_turns[0].run_id == "run-public"

    persistence_calls: list[dict] = []

    class CapturingDb:
        def save_agent_provider_turn(self, **kwargs) -> None:
            persistence_calls.append(kwargs)

    monkeypatch.setattr(executor_module, "get_db", lambda: CapturingDb())
    executor_module.AgentExecutor._persist_provider_trace(
        object(),
        session_id=f"api_key={PLAIN_SECRET}",
        run_id="run-public",
        messages=messages_for(),
        baseline_len=1,
        user_message_id=1,
        assistant_message_id=2,
    )

    assert persistence_calls == []


def test_native_tool_trace_redacts_name_without_changing_dispatch() -> None:
    dispatched_names: list[str] = []

    class RecordingSession:
        execution_id = "native-redaction-test"

        @staticmethod
        def is_non_retriable_cached(_cache_key: str) -> bool:
            return False

        @staticmethod
        def execute(name: str, arguments: dict, **_kwargs) -> dict:
            dispatched_names.append(name)
            return {
                "result_text": json.dumps({"echo": arguments.get("message")}),
                "ok": True,
            }

    tool_call = ToolCall(
        id="call-public",
        name=PREFIXED_API_KEY,
        arguments={"message": "public"},
    )
    events: list[dict] = []
    tool_calls_log: list[dict] = []

    results = _execute_tools(
        [tool_call],
        RecordingSession(),
        step=1,
        progress_callback=events.append,
        tool_calls_log=tool_calls_log,
    )

    assert dispatched_names == [PREFIXED_API_KEY]
    assert tool_call.name == PREFIXED_API_KEY
    assert results[0]["tc"].name == PREFIXED_API_KEY
    assert tool_calls_log[0]["tool"] == "[REDACTED]"
    assert [event["tool"] for event in events] == [
        "[REDACTED]",
        "[REDACTED]",
    ]
    _assert_no_secret({
        "events": events,
        "tool_calls_log": tool_calls_log,
    })

    class BlockingSession(RecordingSession):
        @staticmethod
        def execute(name: str, arguments: dict, **_kwargs) -> dict:
            time.sleep(0.05)
            return {
                "result_text": json.dumps({"echo": arguments.get("message")}),
                "ok": True,
            }

    timed_out_call = ToolCall(
        id="call-timeout",
        name=PREFIXED_API_KEY,
        arguments={"message": "public", "api_key": PLAIN_SECRET},
    )
    timed_out_log: list[dict] = []

    _execute_tools(
        [timed_out_call],
        BlockingSession(),
        step=2,
        progress_callback=None,
        tool_calls_log=timed_out_log,
        tool_wait_timeout_seconds=0.01,
    )

    assert timed_out_call.name == PREFIXED_API_KEY
    assert timed_out_log[0]["tool"] == "[REDACTED]"
    assert timed_out_log[0]["arguments"]["api_key"] == "[REDACTED]"
    assert timed_out_log[0]["timeout"] is True
    _assert_no_secret(timed_out_log)

    queued_calls = [
        ToolCall(
            id=f"call-queued-{index}",
            name="echo",
            arguments={"message": "public", "api_key": PLAIN_SECRET},
        )
        for index in range(6)
    ]
    queued_log: list[dict] = []

    _execute_tools(
        queued_calls,
        BlockingSession(),
        step=3,
        progress_callback=None,
        tool_calls_log=queued_log,
        tool_wait_timeout_seconds=0.01,
    )

    assert len(queued_log) == 6
    assert all(entry["timeout"] is True for entry in queued_log)
    assert all(
        entry["arguments"]["api_key"] == "[REDACTED]"
        for entry in queued_log
    )
    _assert_no_secret(queued_log)


def test_exception_chain_reapplies_exact_values_across_joined_parts() -> None:
    cause = RuntimeError("RIGHT")
    error = ValueError("PLACEHOLDER_LEFT")
    error.__cause__ = cause
    declared = "PLACEHOLDER_LEFT <- RuntimeError"

    summary = sanitize_module.sanitize_exception_chain(
        error,
        redaction_values={declared},
    )

    records: list[str] = []

    class CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    logger = logging.getLogger("tests.security.cross_part_exact_value")
    old_handlers = logger.handlers[:]
    old_level = logger.level
    old_propagate = logger.propagate
    logger.handlers = [CaptureHandler()]
    logger.setLevel(logging.ERROR)
    logger.propagate = False
    try:
        sanitize_module.log_safe_exception(
            logger,
            "provider failed",
            error,
            error_code="provider_failed",
            redaction_values={declared},
        )
    finally:
        logger.handlers = old_handlers
        logger.setLevel(old_level)
        logger.propagate = old_propagate

    assert declared not in summary
    assert "[REDACTED]" in summary
    assert records
    assert all(declared not in record for record in records)
    assert any("[REDACTED]" in record for record in records)


def test_authorization_redaction_preserves_public_url_markers_on_repeated_passes() -> None:
    diagnostic = "Authorization: [REDACTED] [REDACTED_URL]"
    punctuated_diagnostic = "Authorization: [REDACTED]. diagnostic=public"
    canonical = (
        "Authorization: [REDACTED] [REDACTED_URL]. "
        "public_diagnostic=provider_unavailable"
    )
    localized = (
        "Authorization: [REDACTED] <redacted-url>. "
        "public_diagnostic=provider_unavailable"
    )
    parameterized = (
        "Authorization: Digest realm=public, "
        f"note=[REDACTED_URL], response={WEBHOOK_SECRET}"
    )

    for _ in range(3):
        diagnostic = sanitize_module.sanitize_diagnostic_text(diagnostic)
        punctuated_diagnostic = redact_sensitive_text(punctuated_diagnostic)
        canonical = redact_sensitive_text(canonical)
        localized = redact_sensitive_text(localized)

    assert diagnostic == "Authorization: [REDACTED] [REDACTED_URL]"
    assert punctuated_diagnostic == (
        "Authorization: [REDACTED]"
    )
    assert canonical == (
        "Authorization: [REDACTED] [REDACTED_URL]. "
        "public_diagnostic=provider_unavailable"
    )
    assert localized == (
        "Authorization: [REDACTED] <redacted-url>. "
        "public_diagnostic=provider_unavailable"
    )
    assert redact_sensitive_text(parameterized) == "Authorization: [REDACTED]"


def test_set_cookie_redaction_handles_folded_and_combined_fields() -> None:
    folded_sensitive_attribute = (
        "Set-Cookie: id=PUBLIC;\r\n Path=/;\r\n "
        f"private_session={PLAIN_SECRET}"
    )
    comma_combined_cookie = (
        f"Set-Cookie: id=PUBLIC; Path=/, session={BEARER_SECRET} next"
    )
    folded_safe_attributes = (
        f"Set-Cookie: session={WEBHOOK_SECRET};\r\n Path=/;\r\n "
        "HttpOnly next"
    )
    expires_attribute = (
        f"Set-Cookie: session={PLAIN_SECRET}; "
        "Expires=Wed, 21 Oct 2026 07:28:00 GMT; Path=/; Secure next"
    )

    assert redact_sensitive_text(folded_sensitive_attribute) == (
        "Set-Cookie: [REDACTED]"
    )
    assert redact_sensitive_text(comma_combined_cookie) == (
        "Set-Cookie: [REDACTED] next"
    )
    assert redact_sensitive_text(folded_safe_attributes) == (
        "Set-Cookie: [REDACTED];\r\n Path=/;\r\n HttpOnly next"
    )
    assert redact_sensitive_text(expires_attribute) == (
        "Set-Cookie: [REDACTED]; "
        "Expires=Wed, 21 Oct 2026 07:28:00 GMT; Path=/; Secure next"
    )

    api_payload = error_body(
        "provider_rejected",
        folded_sensitive_attribute,
        details={"provider_diagnostic": comma_combined_cookie},
    )
    stream_payload = sanitize_stream_event(
        {
            "type": "tool_progress",
            "details": {"provider_diagnostic": folded_sensitive_attribute},
        },
        trace_id="trace-set-cookie-grammar",
    )
    formatter = RelativePathFormatter("%(levelname)s %(message)s")
    record = logging.LogRecord(
        name="tests.security.set_cookie",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg=comma_combined_cookie,
        args=(),
        exc_info=None,
    )
    rendered_log = formatter.format(record)

    _assert_no_secret(
        {"api": api_payload, "stream": stream_payload, "log": rendered_log}
    )
    assert api_payload["message"] == "Set-Cookie: [REDACTED]"
    assert stream_payload["details"]["provider_diagnostic"] == (
        "Set-Cookie: [REDACTED]"
    )
    assert "Set-Cookie: [REDACTED] next" in rendered_log


def test_field_scanner_checks_one_public_boundary_per_whitespace_run(
    monkeypatch,
) -> None:
    original_pattern = sanitize_module._PUBLIC_DIAGNOSTIC_FIELD_PATTERN

    class CountingPattern:
        def __init__(self) -> None:
            self.match_calls = 0

        def match(self, text, index=0):
            self.match_calls += 1
            return original_pattern.match(text, index)

    counting_pattern = CountingPattern()
    monkeypatch.setattr(
        sanitize_module,
        "_PUBLIC_DIAGNOSTIC_FIELD_PATTERN",
        counting_pattern,
    )
    raw_text = f"Cookie: session={PLAIN_SECRET}" + (" " * 32_000) + "public=401"

    redacted = redact_sensitive_text(raw_text)

    assert redacted == "Cookie: [REDACTED]" + (" " * 32_000) + "public=401"
    assert counting_pattern.match_calls == 1

    for near_match in (
        "authorizatioX: value",
        "set_cookiX: value",
        "cookiX: value",
        "api_keX=value",
        "postgresqlX://value",
    ):
        hostile_text = ("a-" * 4_000) + near_match
        started = time.perf_counter()
        hostile_redacted = redact_sensitive_text(hostile_text)
        elapsed = time.perf_counter() - started

        assert hostile_redacted == hostile_text
        assert elapsed < 0.5


def test_sensitive_field_boundary_search_uses_bounded_lookahead(
    monkeypatch,
) -> None:
    original_pattern = sanitize_module._TEXT_FIELD_START_PATTERN
    bounded_spans: list[int] = []

    class CountingPattern:
        def search(self, text, start=0, end=None):
            if end is None:
                return original_pattern.search(text, start)
            bounded_spans.append(end - start)
            return original_pattern.search(text, start, end)

        def match(self, text, start=0):
            return original_pattern.match(text, start)

    monkeypatch.setattr(
        sanitize_module,
        "_TEXT_FIELD_START_PATTERN",
        CountingPattern(),
    )
    word_count = 4096
    raw = "Authorization: BENIGN " + ("word " * word_count) + "END"

    assert redact_sensitive_text(raw) == "Authorization: [REDACTED]"
    assert bounded_spans
    assert max(bounded_spans) <= sanitize_module._TEXT_FIELD_BOUNDARY_LOOKAHEAD
    assert len(bounded_spans) <= word_count + 8


def test_structured_closer_runs_are_checked_a_constant_number_of_times(
    monkeypatch,
) -> None:
    original = sanitize_module._is_structured_field_suffix
    match_calls = 0

    def counting_suffix(text: str, index: int) -> bool:
        nonlocal match_calls
        match_calls += 1
        return original(text, index)

    monkeypatch.setattr(
        sanitize_module,
        "_is_structured_field_suffix",
        counting_suffix,
    )
    raw = '{"api_key":"BENIGN"' + (")" * 32_000) + "x"

    redacted = redact_sensitive_text(raw)

    assert "BENIGN" not in redacted
    assert redacted == '{"api_key":"[REDACTED]"'
    assert match_calls <= 2


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

    nested = json.dumps(
        {
            "wrapped": json.dumps(
                {
                    "diagnostic": (
                        "Authorization: Odd "
                        f"Signature={WEBHOOK_SECRET}"
                    )
                }
            )
        }
    )
    nested_once = redact_sensitive_text(nested)
    nested_twice = redact_sensitive_text(nested_once)
    nested_thrice = redact_sensitive_text(nested_twice)
    nested_inner = json.loads(json.loads(nested_once)["wrapped"])

    _assert_no_secret(nested_once)
    assert nested_twice == nested_once
    assert nested_thrice == nested_once
    assert nested_inner == {"diagnostic": "Authorization: [REDACTED]"}


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
                "WWW-Authenticate": f'Bearer error="api.key={PLAIN_SECRET}"',
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
    assert "www-authenticate" in response.headers
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
