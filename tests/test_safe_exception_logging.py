# -*- coding: utf-8 -*-
"""Security regressions for exception logging at HTTP boundaries."""

import logging
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middlewares.error_handler import ErrorHandlerMiddleware, add_error_handlers
from src.utils.sanitize import (
    exception_chain_redaction_values,
    log_safe_exception,
    safe_before_sleep_log,
    sanitize_diagnostic_text,
    sanitize_exception_chain,
)


SECRET_MARKERS = (
    "api-key-canary-c01",
    "bearer-canary-c01",
    "cookie-canary-c01",
    "query-canary-c01",
    "userinfo-canary-c01",
    "webhook-canary-c01",
    "private.example.invalid",
)
SAFE_RENDER_FAILURE = "[UNRENDERABLE]"


class BrokenStringError(Exception):
    def __str__(self) -> str:
        raise RuntimeError("string conversion failed")

    def __repr__(self) -> str:
        return "BROKEN_EXCEPTION_REPR_CANARY"


class BrokenBaseExceptionStringError(Exception):
    def __str__(self) -> str:
        raise KeyboardInterrupt("string conversion interrupted")

    def __repr__(self) -> str:
        return "BROKEN_BASE_EXCEPTION_REPR_CANARY"


class MultiArgumentError(Exception):
    def __str__(self) -> str:
        return "wrapped multi-argument failure"


class BrokenNestedValue:
    def __str__(self) -> str:
        raise RuntimeError("nested string conversion failed")

    def __repr__(self) -> str:
        return "BROKEN_NESTED_REPR_CANARY"


class BrokenRedactionValues:
    def __iter__(self):
        yield "PARTIAL_REDACTION_CANARY"
        raise RuntimeError("redaction iteration failed")


class BrokenContext(dict):
    def items(self):
        raise RuntimeError("context iteration failed")


class BrokenBooleanContext(dict):
    def __bool__(self) -> bool:
        raise RuntimeError("context truthiness failed")


class BrokenContextKey:
    def __str__(self) -> str:
        raise RuntimeError("context key conversion failed")

    def __repr__(self) -> str:
        return "BROKEN_CONTEXT_KEY_REPR_CANARY"


class FalseSensitiveContextKey:
    def __bool__(self) -> bool:
        return False

    def __str__(self) -> str:
        return "api_key"

    def __repr__(self) -> str:
        return "FALSE_SENSITIVE_CONTEXT_KEY_REPR_CANARY"


class BrokenExceptionAttributeError(Exception):
    broken_attribute = ""

    def __getattribute__(self, name: str):
        broken_attribute = object.__getattribute__(self, "broken_attribute")
        if name == broken_attribute:
            raise RuntimeError(f"{name} access failed")
        return super().__getattribute__(name)


class BrokenArgsAccessError(BrokenExceptionAttributeError):
    broken_attribute = "args"


class BrokenCauseAccessError(BrokenExceptionAttributeError):
    broken_attribute = "__cause__"


class BrokenContextAccessError(BrokenExceptionAttributeError):
    broken_attribute = "__context__"


class BrokenSuppressContextAccessError(BrokenExceptionAttributeError):
    broken_attribute = "__suppress_context__"


class RetryStateReadFailure(BaseException):
    pass


class BrokenRetryState:
    @property
    def attempt_number(self):
        raise RetryStateReadFailure("token=RETRY_STATE_READ_CANARY")


def _raise_secret_exception_chain() -> None:
    try:
        raise ValueError(
            "Authorization: Bearer bearer-canary-c01 "
            "Cookie: session=cookie-canary-c01 "
            "https://userinfo-canary-c01:password@private.example.invalid/internal"
            "?token=query-canary-c01"
        )
    except ValueError as cause:
        raise RuntimeError(
            "api_key=api-key-canary-c01 "
            "webhook_url=https://hooks.example.invalid/webhook/webhook-canary-c01"
        ) from cause


def _assert_safe_http_exception_log(caplog, *, trace_id: str, path: str) -> None:
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    for marker in SECRET_MARKERS:
        assert marker not in rendered
    assert trace_id in rendered
    assert "method=GET" in rendered
    assert f"path={path}" in rendered
    assert "error_code=internal_error" in rendered
    assert "exception_type=RuntimeError" in rendered
    assert "ValueError" in rendered
    assert "summary=" in rendered
    assert all(record.exc_info is None for record in caplog.records)


def test_error_middleware_logs_only_sanitized_exception_chain(caplog) -> None:
    app = FastAPI()
    app.add_middleware(ErrorHandlerMiddleware)

    @app.get("/middleware-failure/{item_id}")
    async def middleware_failure(item_id: int) -> None:
        _raise_secret_exception_chain()

    caplog.set_level(logging.ERROR, logger="api.middlewares.error_handler")
    response = TestClient(app, raise_server_exceptions=False).get(
        "/middleware-failure/17?token=query-canary-c01",
        headers={"X-Trace-ID": "trace-middleware-c01"},
    )

    assert response.status_code == 500
    _assert_safe_http_exception_log(
        caplog,
        trace_id="trace-middleware-c01",
        path="/middleware-failure/{item_id}",
    )


def test_general_exception_handler_logs_only_sanitized_exception_chain(caplog) -> None:
    app = FastAPI()
    add_error_handlers(app)

    @app.get("/handler-failure/{item_id}")
    async def handler_failure(item_id: int) -> None:
        _raise_secret_exception_chain()

    caplog.set_level(logging.ERROR, logger="api.middlewares.error_handler")
    response = TestClient(app, raise_server_exceptions=False).get(
        "/handler-failure/23?token=query-canary-c01",
        headers={"X-Trace-ID": "trace-handler-c01"},
    )

    assert response.status_code == 500
    _assert_safe_http_exception_log(
        caplog,
        trace_id="trace-handler-c01",
        path="/handler-failure/{item_id}",
    )


def test_safe_exception_summary_is_bounded(caplog) -> None:
    caplog.set_level(logging.ERROR, logger="tests.safe_exception")
    target_logger = logging.getLogger("tests.safe_exception")

    log_safe_exception(
        target_logger,
        "Bounded diagnostic",
        RuntimeError("ordinary diagnostic " * 500),
        error_code="bounded_error",
    )

    assert len(caplog.records) == 1
    assert len(caplog.records[0].getMessage()) < 2500
    assert caplog.records[0].exc_info is None


def test_exception_chain_preserves_segment_chain_and_total_bounds() -> None:
    chain = RuntimeError("segment-0 " * 100)
    for index in range(1, 7):
        outer = RuntimeError(f"segment-{index} " * 100)
        outer.__cause__ = chain
        chain = outer

    rendered = sanitize_exception_chain(chain)

    assert len(rendered) <= 900
    assert rendered.count("RuntimeError:") == 4
    assert "segment-6" in rendered
    assert "segment-2" not in rendered


def test_exception_chain_uses_fixed_placeholder_when_exception_string_fails() -> None:
    rendered = sanitize_exception_chain(
        BrokenStringError("RAW_EXCEPTION_CANARY"),
        redaction_values=(SAFE_RENDER_FAILURE,),
    )

    assert rendered == f"BrokenStringError: {SAFE_RENDER_FAILURE}"
    assert "RAW_EXCEPTION_CANARY" not in rendered
    assert "BROKEN_EXCEPTION_REPR_CANARY" not in rendered


def test_exception_chain_redaction_values_catches_base_exception_from_string() -> None:
    values = exception_chain_redaction_values(
        BrokenBaseExceptionStringError("RAW_BASE_EXCEPTION_CANARY")
    )

    assert values == set()


def test_exception_chain_redaction_values_match_key_error_diagnostic_source() -> None:
    canary = "KEY_ERROR_DIAGNOSTIC_CANARY"
    error = KeyError(canary)

    rendered = sanitize_exception_chain(
        error,
        redaction_values=exception_chain_redaction_values(error),
    )

    assert rendered == "KeyError: [REDACTED]"
    assert canary not in rendered


def test_exception_chain_redaction_values_match_os_error_diagnostic_source() -> None:
    canary = "OS_ERROR_DIAGNOSTIC_CANARY"
    raw_path = "/Users/private-user/.config/stockpulse/provider.json"
    error = OSError(5, canary, raw_path)

    rendered = sanitize_exception_chain(
        error,
        redaction_values=exception_chain_redaction_values(error),
    )

    assert rendered == "OSError: [REDACTED]"
    assert canary not in rendered
    assert raw_path not in rendered


def test_exception_chain_redaction_values_match_multi_argument_diagnostic_source() -> None:
    message_canary = "MULTI_ARGUMENT_MESSAGE_CANARY"
    path_canary = "/Users/private-user/MULTI_ARGUMENT_PATH_CANARY"
    error = MultiArgumentError(message_canary, path_canary)

    rendered = sanitize_exception_chain(
        error,
        redaction_values=exception_chain_redaction_values(error),
    )

    assert rendered == "MultiArgumentError: [REDACTED]"
    assert message_canary not in rendered
    assert path_canary not in rendered


def test_exception_chain_redaction_values_cover_each_chain_diagnostic_source() -> None:
    outer_canary = "OUTER_KEY_ERROR_CANARY"
    cause_canary = "CAUSE_OS_ERROR_CANARY"
    cause = OSError(5, cause_canary)
    outer = KeyError(outer_canary)
    outer.__cause__ = cause

    rendered = sanitize_exception_chain(
        outer,
        redaction_values=exception_chain_redaction_values(outer),
    )

    assert rendered == "KeyError: [REDACTED] <- OSError: [REDACTED]"
    assert outer_canary not in rendered
    assert cause_canary not in rendered


def test_exception_chain_redaction_values_are_bounded_for_long_diagnostics() -> None:
    canary = "LONG_DIAGNOSTIC_CANARY_"
    error = OSError(5, canary * 2000)

    values = exception_chain_redaction_values(error)
    rendered = sanitize_exception_chain(error, redaction_values=values)

    assert len(values) <= 65
    assert all(0 < len(value) <= 240 for value in values)
    assert canary not in rendered


def test_exception_chain_uses_fixed_placeholder_for_broken_cause() -> None:
    cause = BrokenStringError("RAW_CAUSE_CANARY")
    outer = RuntimeError("outer diagnostic")
    outer.__cause__ = cause

    rendered = sanitize_exception_chain(outer)

    assert rendered == (
        f"RuntimeError: outer diagnostic <- BrokenStringError: {SAFE_RENDER_FAILURE}"
    )
    assert "RAW_CAUSE_CANARY" not in rendered
    assert "BROKEN_EXCEPTION_REPR_CANARY" not in rendered


def test_exception_chain_uses_fixed_placeholder_for_broken_context() -> None:
    context = BrokenStringError("RAW_CONTEXT_CANARY")
    outer = RuntimeError("outer diagnostic")
    outer.__context__ = context
    outer.__suppress_context__ = False

    rendered = sanitize_exception_chain(outer)

    assert rendered == (
        f"RuntimeError: outer diagnostic <- BrokenStringError: {SAFE_RENDER_FAILURE}"
    )
    assert "RAW_CONTEXT_CANARY" not in rendered
    assert "BROKEN_EXCEPTION_REPR_CANARY" not in rendered


def test_diagnostic_mapping_never_falls_back_to_nested_object_repr() -> None:
    rendered = sanitize_diagnostic_text({"detail": BrokenNestedValue()})

    assert rendered == f"{{'detail': '{SAFE_RENDER_FAILURE}'}}"
    assert "BROKEN_NESTED_REPR_CANARY" not in rendered


def test_diagnostic_containers_never_fall_back_to_nested_object_repr() -> None:
    values_and_expected = (
        ([BrokenNestedValue()], f"['{SAFE_RENDER_FAILURE}']"),
        ((BrokenNestedValue(),), f"('{SAFE_RENDER_FAILURE}',)"),
    )

    for value, expected in values_and_expected:
        rendered = sanitize_diagnostic_text(value)

        assert rendered == expected
        assert "BROKEN_NESTED_REPR_CANARY" not in rendered


def test_diagnostic_sets_never_render_nested_object_repr() -> None:
    values = (
        {BrokenNestedValue()},
        frozenset({BrokenNestedValue()}),
        {"detail": {BrokenNestedValue()}},
    )

    for value in values:
        rendered = sanitize_diagnostic_text(value)

        assert SAFE_RENDER_FAILURE in rendered
        assert "BROKEN_NESTED_REPR_CANARY" not in rendered


def test_multi_argument_exception_never_renders_nested_object_repr() -> None:
    rendered = sanitize_exception_chain(
        RuntimeError("ordinary diagnostic", BrokenNestedValue())
    )

    assert SAFE_RENDER_FAILURE in rendered
    assert "BROKEN_NESTED_REPR_CANARY" not in rendered


def test_diagnostic_text_fails_closed_when_redaction_value_cannot_render() -> None:
    rendered = sanitize_diagnostic_text(
        "diagnostic that must not survive incomplete redaction",
        redaction_values=(BrokenNestedValue(),),
    )

    assert rendered == SAFE_RENDER_FAILURE
    assert "BROKEN_NESTED_REPR_CANARY" not in rendered


def test_diagnostic_text_fails_closed_when_redaction_iteration_fails() -> None:
    rendered = sanitize_diagnostic_text(
        "PARTIAL_REDACTION_CANARY must not survive incomplete redaction",
        redaction_values=BrokenRedactionValues(),
    )

    assert rendered == SAFE_RENDER_FAILURE
    assert "PARTIAL_REDACTION_CANARY" not in rendered


def test_diagnostic_text_fails_closed_when_redaction_limit_is_exceeded() -> None:
    overflow_canary = "REDACTION_OVERFLOW_CANARY"
    rendered = sanitize_diagnostic_text(
        overflow_canary,
        redaction_values=(
            *(f"redaction-value-{index}" for index in range(64)),
            overflow_canary,
        ),
    )

    assert rendered == SAFE_RENDER_FAILURE
    assert overflow_canary not in rendered


def test_safe_exception_log_fails_closed_when_redaction_values_fail(caplog) -> None:
    caplog.set_level(logging.ERROR, logger="tests.safe_failed_redactions")
    target_logger = logging.getLogger("tests.safe_failed_redactions")

    log_safe_exception(
        target_logger,
        "event contains RAW_EVENT_CANARY",
        RuntimeError("exception contains RAW_EXCEPTION_CANARY"),
        error_code="raw_error_code",
        redaction_values=(BrokenNestedValue(),),
    )

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.getMessage() == SAFE_RENDER_FAILURE
    assert record.exc_info is None


def test_exception_chain_fails_closed_when_redaction_values_fail() -> None:
    rendered = sanitize_exception_chain(
        RuntimeError("RAW_EXCEPTION_CANARY"),
        redaction_values=BrokenRedactionValues(),
    )

    assert rendered == SAFE_RENDER_FAILURE
    assert "RAW_EXCEPTION_CANARY" not in rendered
    assert "PARTIAL_REDACTION_CANARY" not in rendered


def test_safe_logging_never_replaces_the_original_broken_exception(caplog) -> None:
    caplog.set_level(logging.ERROR, logger="tests.safe_broken_exception")
    target_logger = logging.getLogger("tests.safe_broken_exception")
    original = BrokenStringError("RAW_ORIGINAL_EXCEPTION_CANARY")

    try:
        raise original
    except BrokenStringError as caught:
        log_safe_exception(
            target_logger,
            "Original operation failed",
            caught,
            error_code="original_operation_failed",
            context={"detail": BrokenNestedValue()},
        )
        assert caught is original

    assert len(caplog.records) == 1
    record = caplog.records[0]
    rendered = record.getMessage()
    assert f"detail={SAFE_RENDER_FAILURE}" in rendered
    assert f"summary=BrokenStringError: {SAFE_RENDER_FAILURE}" in rendered
    assert "RAW_ORIGINAL_EXCEPTION_CANARY" not in rendered
    assert "BROKEN_EXCEPTION_REPR_CANARY" not in rendered
    assert "BROKEN_NESTED_REPR_CANARY" not in rendered
    assert record.exc_info is None


def test_retry_log_fails_closed_when_redaction_values_fail(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="tests.safe_retry_failed_redactions")
    target_logger = logging.getLogger("tests.safe_retry_failed_redactions")
    callback = safe_before_sleep_log(
        target_logger,
        logging.WARNING,
        event="retry contains RAW_RETRY_EVENT_CANARY",
        error_code="raw_retry_error_code",
        redaction_values=BrokenRedactionValues(),
    )
    retry_state = SimpleNamespace(
        outcome=SimpleNamespace(
            exception=lambda: RuntimeError("RAW_RETRY_EXCEPTION_CANARY")
        )
    )

    callback(retry_state)

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.getMessage() == SAFE_RENDER_FAILURE
    assert record.exc_info is None


def test_retry_log_catches_base_exception_from_state_access(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="tests.safe_retry_state_access")
    target_logger = logging.getLogger("tests.safe_retry_state_access")
    callback = safe_before_sleep_log(
        target_logger,
        logging.WARNING,
        event="Retry state inspection failed",
        error_code="retry_state_inspection_failed",
    )

    escaped = None
    try:
        callback(BrokenRetryState())
    except BaseException as exc:  # pragma: no cover - asserted below
        escaped = exc

    assert escaped is None
    assert len(caplog.records) == 1
    rendered = caplog.records[0].getMessage()
    assert "RETRY_STATE_READ_CANARY" not in rendered
    assert "error_code=retry_state_inspection_failed" in rendered
    assert "summary=RetryStateReadFailure: [REDACTED]" in rendered
    assert caplog.records[0].exc_info is None


def test_retry_logger_construction_does_not_evaluate_context_truthiness(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="tests.safe_retry_broken_context")
    target_logger = logging.getLogger("tests.safe_retry_broken_context")

    callback = safe_before_sleep_log(
        target_logger,
        logging.WARNING,
        event="Retry operation failed",
        error_code="retry_operation_failed",
        context=BrokenBooleanContext({"token": "RAW_RETRY_CONTEXT_CANARY"}),
    )
    callback(
        SimpleNamespace(
            outcome=SimpleNamespace(
                exception=lambda: RuntimeError("ordinary retry diagnostic")
            )
        )
    )

    assert len(caplog.records) == 1
    record = caplog.records[0]
    rendered = record.getMessage()
    assert "token=[REDACTED]" in rendered
    assert "RAW_RETRY_CONTEXT_CANARY" not in rendered
    assert record.exc_info is None


def test_retry_logger_fails_closed_when_context_snapshot_fails(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="tests.safe_retry_context_snapshot")
    target_logger = logging.getLogger("tests.safe_retry_context_snapshot")

    callback = safe_before_sleep_log(
        target_logger,
        logging.WARNING,
        event="Retry operation failed",
        error_code="retry_operation_failed",
        context=BrokenContext({"token": "RAW_RETRY_SNAPSHOT_CANARY"}),
    )
    callback(
        SimpleNamespace(
            outcome=SimpleNamespace(
                exception=lambda: RuntimeError("ordinary retry diagnostic")
            )
        )
    )

    assert len(caplog.records) == 1
    record = caplog.records[0]
    rendered = record.getMessage()
    assert f"context={SAFE_RENDER_FAILURE}" in rendered
    assert "RAW_RETRY_SNAPSHOT_CANARY" not in rendered
    assert record.exc_info is None


def test_safe_exception_log_fails_closed_when_context_iteration_fails(caplog) -> None:
    caplog.set_level(logging.ERROR, logger="tests.safe_broken_context")
    target_logger = logging.getLogger("tests.safe_broken_context")

    log_safe_exception(
        target_logger,
        "Context operation failed",
        RuntimeError("ordinary diagnostic"),
        error_code="context_operation_failed",
        context=BrokenContext({"token": "RAW_CONTEXT_TOKEN_CANARY"}),
    )

    assert len(caplog.records) == 1
    record = caplog.records[0]
    rendered = record.getMessage()
    assert f"context={SAFE_RENDER_FAILURE}" in rendered
    assert "RAW_CONTEXT_TOKEN_CANARY" not in rendered
    assert record.exc_info is None


def test_safe_exception_log_never_uses_broken_context_key_repr(caplog) -> None:
    caplog.set_level(logging.ERROR, logger="tests.safe_broken_context_key")
    target_logger = logging.getLogger("tests.safe_broken_context_key")

    log_safe_exception(
        target_logger,
        "Context key operation failed",
        RuntimeError("ordinary diagnostic"),
        error_code="context_key_operation_failed",
        context={BrokenContextKey(): "RAW_CONTEXT_VALUE_CANARY"},
    )

    assert len(caplog.records) == 1
    record = caplog.records[0]
    rendered = record.getMessage()
    assert f"context={SAFE_RENDER_FAILURE}" in rendered
    assert "BROKEN_CONTEXT_KEY_REPR_CANARY" not in rendered
    assert "RAW_CONTEXT_VALUE_CANARY" not in rendered
    assert record.exc_info is None


def test_safe_exception_log_classifies_falsey_context_key_from_one_render(caplog) -> None:
    caplog.set_level(logging.ERROR, logger="tests.safe_falsey_context_key")
    target_logger = logging.getLogger("tests.safe_falsey_context_key")

    log_safe_exception(
        target_logger,
        "Context key operation failed",
        RuntimeError("ordinary diagnostic"),
        error_code="context_key_operation_failed",
        context={FalseSensitiveContextKey(): "FALSE_KEY_SECRET_CANARY"},
    )

    assert len(caplog.records) == 1
    rendered = caplog.records[0].getMessage()
    assert "FALSE_KEY_SECRET_CANARY" not in rendered
    assert "FALSE_SENSITIVE_CONTEXT_KEY_REPR_CANARY" not in rendered
    assert "api_key=[REDACTED]" in rendered
    assert caplog.records[0].exc_info is None


def test_exception_chain_attribute_access_failures_return_fixed_placeholder() -> None:
    for error_type in (
        BrokenArgsAccessError,
        BrokenCauseAccessError,
        BrokenContextAccessError,
        BrokenSuppressContextAccessError,
    ):
        escaped = None
        rendered = None
        try:
            rendered = sanitize_exception_chain(error_type("RAW_ATTRIBUTE_CANARY"))
        except BaseException as exc:  # pragma: no cover - asserted below
            escaped = exc

        assert escaped is None
        assert rendered == SAFE_RENDER_FAILURE
        assert "RAW_ATTRIBUTE_CANARY" not in rendered


def test_exception_chain_redaction_values_never_propagates_attribute_failures() -> None:
    for error_type in (
        BrokenCauseAccessError,
        BrokenContextAccessError,
        BrokenSuppressContextAccessError,
    ):
        escaped = None
        try:
            values = exception_chain_redaction_values(error_type("ordinary diagnostic"))
        except BaseException as exc:  # pragma: no cover - asserted below
            escaped = exc
            values = set()

        assert escaped is None
        assert values == {"ordinary diagnostic"}


def test_diagnostic_text_redacts_sensitive_mapping_values() -> None:
    rendered = sanitize_diagnostic_text({"token": "QUOTED_TOKEN_CANARY"})

    assert "QUOTED_TOKEN_CANARY" not in rendered
    assert "'token': '[REDACTED]'" in rendered


def test_diagnostic_text_redacts_quoted_json_assignments() -> None:
    rendered = sanitize_diagnostic_text(
        '{"api_key": "QUOTED_JSON_API_KEY_CANARY", "status": "failed"}'
    )

    assert "QUOTED_JSON_API_KEY_CANARY" not in rendered
    assert '"api_key": "[REDACTED]"' in rendered
    assert '"status": "failed"' in rendered


def test_diagnostic_text_redacts_complete_cookie_headers() -> None:
    rendered_cookie = sanitize_diagnostic_text(
        "Cookie: session=COOKIE_ONE; private_session=COOKIE_TWO"
    )
    rendered_set_cookie = sanitize_diagnostic_text(
        "Set-Cookie: session=SET_COOKIE_ONE; Path=/; private_session=SET_COOKIE_TWO"
    )

    for canary in (
        "COOKIE_ONE",
        "COOKIE_TWO",
        "SET_COOKIE_ONE",
        "SET_COOKIE_TWO",
    ):
        assert canary not in rendered_cookie
        assert canary not in rendered_set_cookie
    assert rendered_cookie == "Cookie: [REDACTED]"
    assert rendered_set_cookie == "Set-Cookie: [REDACTED]"


def test_exception_chain_redacts_sensitive_mapping_values() -> None:
    rendered = sanitize_exception_chain(
        RuntimeError({"api_key": "QUOTED_API_KEY_CANARY"})
    )

    assert "QUOTED_API_KEY_CANARY" not in rendered
    assert "RuntimeError" in rendered
    assert "'api_key': '[REDACTED]'" in rendered


def test_exception_chain_redacts_spaced_secret_assignment() -> None:
    canary = "SPACED_ASSIGNMENT_CANARY"

    rendered = sanitize_exception_chain(
        RuntimeError(f"provider rejected api_key = {canary}")
    )

    assert canary not in rendered
    assert "api_key = [REDACTED]" in rendered


def test_exception_chain_redacts_non_string_sensitive_mapping_values() -> None:
    for key, value in (
        ("token", 123456789),
        ("api_key", 987654321),
        ("token", None),
    ):
        rendered = sanitize_exception_chain(RuntimeError({key: value}))

        assert str(value) not in rendered
        assert "RuntimeError" in rendered
        assert f"'{key}': '[REDACTED]'" in rendered


def test_safe_exception_log_redacts_sensitive_context_keys(caplog) -> None:
    caplog.set_level(logging.ERROR, logger="tests.safe_context")
    target_logger = logging.getLogger("tests.safe_context")

    log_safe_exception(
        target_logger,
        "failure",
        RuntimeError("ordinary diagnostic"),
        error_code="probe",
        context={
            "api_key": "CONTEXT_API_KEY_CANARY",
            "token": "CONTEXT_TOKEN_CANARY",
            "operation": "context-probe",
        },
    )

    assert len(caplog.records) == 1
    record = caplog.records[0]
    rendered = record.getMessage()
    assert "CONTEXT_API_KEY_CANARY" not in rendered
    assert "CONTEXT_TOKEN_CANARY" not in rendered
    assert "api_key=[REDACTED]" in rendered
    assert "token=[REDACTED]" in rendered
    assert "operation=context-probe" in rendered
    assert record.exc_info is None


def test_safe_before_sleep_log_preserves_retry_diagnostics_without_secrets(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="tests.safe_retry")
    target_logger = logging.getLogger("tests.safe_retry")
    exception_canary = "TENACITY_EXCEPTION_CANARY"
    context_canary = "TENACITY_CONTEXT_CANARY"
    callback = safe_before_sleep_log(
        target_logger,
        logging.WARNING,
        event="Search request failed; scheduling retry",
        error_code="search_retry_scheduled",
        context={"provider": "probe", "api_key": context_canary},
    )
    retry_state = SimpleNamespace(
        attempt_number=3,
        next_action=SimpleNamespace(sleep=1.25),
        outcome=SimpleNamespace(
            exception=lambda: RuntimeError(
                {
                    "token": exception_canary,
                    "endpoint": (
                        "https://private.example.invalid/search"
                        f"?token={exception_canary}"
                    ),
                }
            )
        ),
    )

    callback(retry_state)

    assert len(caplog.records) == 1
    record = caplog.records[0]
    rendered = record.getMessage()
    assert exception_canary not in rendered
    assert context_canary not in rendered
    assert "private.example.invalid" not in rendered
    assert "error_code=search_retry_scheduled" in rendered
    assert "provider=probe" in rendered
    assert "api_key=[REDACTED]" in rendered
    assert "attempt=3" in rendered
    assert "retry_in_seconds=1.25" in rendered
    assert "exception_type=RuntimeError" in rendered
    assert "[REDACTED]" in rendered
    assert "[REDACTED_URL]" in rendered
    assert record.exc_info is None


def test_safe_exception_log_redacts_configured_standalone_values(caplog) -> None:
    caplog.set_level(logging.ERROR, logger="tests.safe_known_values")
    target_logger = logging.getLogger("tests.safe_known_values")
    configured_canary = "llm-config-value-8xQ2mP7z"

    log_safe_exception(
        target_logger,
        f"Provider request failed for {configured_canary}",
        RuntimeError(
            f"provider rejected configured credential {configured_canary}"
        ),
        error_code="provider_request_failed",
        context={
            "provider": "custom",
            "diagnostic_hint": f"configured value {configured_canary}",
        },
        redaction_values=(
            value
            for value in (None, "", configured_canary)
        ),
    )

    assert len(caplog.records) == 1
    record = caplog.records[0]
    rendered = record.getMessage()
    assert configured_canary not in rendered
    assert "Provider request failed for [REDACTED]" in rendered
    assert "diagnostic_hint=configured value [REDACTED]" in rendered
    assert "error_code=provider_request_failed" in rendered
    assert "exception_type=RuntimeError" in rendered
    assert "summary=RuntimeError:" in rendered
    assert "[REDACTED]" in rendered
    assert len(rendered) < 2500
    assert record.exc_info is None


def test_exception_redactions_do_not_corrupt_stable_log_fields(caplog) -> None:
    caplog.set_level(logging.ERROR, logger="tests.safe_exception_fields")
    target_logger = logging.getLogger("tests.safe_exception_fields")
    error = RuntimeError("failed")

    log_safe_exception(
        target_logger,
        "Search provider failed",
        error,
        error_code="tavily_search_failed",
        context={"provider": "failed-provider"},
        exception_redaction_values=exception_chain_redaction_values(error),
    )

    assert len(caplog.records) == 1
    rendered = caplog.records[0].getMessage()
    assert "Search provider failed" in rendered
    assert "error_code=tavily_search_failed" in rendered
    assert "provider=failed-provider" in rendered
    assert "summary=RuntimeError: [REDACTED]" in rendered
    assert "diagnostic=RuntimeError: [REDACTED]" in rendered
    assert "tavily_search_[REDACTED]" not in rendered


def test_retry_log_redacts_arbitrary_exception_without_corrupting_fields(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="tests.safe_retry_arbitrary")
    target_logger = logging.getLogger("tests.safe_retry_arbitrary")
    callback = safe_before_sleep_log(
        target_logger,
        logging.WARNING,
        event="Search request failed",
        error_code="search_retry_failed",
        context={"provider": "failed-provider"},
    )
    retry_state = SimpleNamespace(
        attempt_number=1,
        next_action=SimpleNamespace(sleep=0.25),
        outcome=SimpleNamespace(exception=lambda: RuntimeError("failed")),
    )

    callback(retry_state)

    assert len(caplog.records) == 1
    rendered = caplog.records[0].getMessage()
    assert "Search request failed" in rendered
    assert "error_code=search_retry_failed" in rendered
    assert "provider=failed-provider" in rendered
    assert "summary=RuntimeError: [REDACTED]" in rendered
    assert "search_retry_[REDACTED]" not in rendered
