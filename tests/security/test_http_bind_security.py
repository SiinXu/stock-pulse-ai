"""Security policy coverage for authenticated and local-only HTTP binds."""

import logging
from unittest.mock import patch

import pytest

from src.security.http_bind import (
    InsecurePublicBindError,
    enforce_http_bind_security,
    is_local_only_bind,
)


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "127.20.30.40", "::1", "[::1]", "localhost", "LOCALHOST."],
)
def test_local_only_bind_recognizes_explicit_loopback_hosts(host: str) -> None:
    assert is_local_only_bind(host)


@pytest.mark.parametrize(
    "host",
    ["0.0.0.0", "::", "[::]", "*", "192.168.1.20", "10.0.0.8", "example.test", ""],
)
def test_non_local_bind_is_rejected_when_auth_is_disabled(host: str) -> None:
    with pytest.raises(InsecurePublicBindError, match="Refusing to start"):
        enforce_http_bind_security(
            host,
            auth_enabled=False,
            allow_insecure_public_bind=False,
        )


def test_unix_socket_is_allowed_when_auth_is_disabled() -> None:
    enforce_http_bind_security(
        None,
        unix_socket="/tmp/stockpulse.sock",
        auth_enabled=False,
        allow_insecure_public_bind=False,
    )


def test_inherited_socket_is_denied_when_locality_cannot_be_proven() -> None:
    with pytest.raises(InsecurePublicBindError):
        enforce_http_bind_security(
            "127.0.0.1",
            inherited_socket=True,
            auth_enabled=False,
            allow_insecure_public_bind=False,
        )


def test_auth_enabled_preserves_non_local_bind_behavior() -> None:
    enforce_http_bind_security(
        "0.0.0.0",
        auth_enabled=True,
        allow_insecure_public_bind=False,
    )


def test_override_allows_bind_and_emits_one_security_warning(caplog) -> None:
    logger = logging.getLogger("test.http_bind")
    with caplog.at_level(logging.WARNING, logger=logger.name):
        enforce_http_bind_security(
            "0.0.0.0",
            auth_enabled=False,
            allow_insecure_public_bind=True,
            event_logger=logger,
            entrypoint="test entrypoint",
        )

    messages = [record.getMessage() for record in caplog.records]
    assert len(messages) == 1
    assert "SECURITY WARNING [insecure_public_bind_override]" in messages[0]
    assert "ALLOW_INSECURE_PUBLIC_BIND=true" in messages[0]


def test_invalid_override_value_does_not_fail_open(monkeypatch) -> None:
    monkeypatch.setenv("ALLOW_INSECURE_PUBLIC_BIND", "sometimes")
    with patch("src.auth.is_auth_enabled", return_value=False):
        with pytest.raises(InsecurePublicBindError):
            enforce_http_bind_security("0.0.0.0")
