# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Regression: connection-string credentials must not leak into diagnostics.

``_URL_PATTERN`` only matches ``http(s)://``, so a password embedded in the
userinfo of a non-HTTP connection string (``postgresql://user:pw@host``, e.g.
inside a SQLAlchemy error) previously survived ``sanitize_diagnostic_text`` /
``sanitize_sensitive_text`` and could leak into agent diagnostics and logs.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agent.public_contract import sanitize_agent_diagnostic
from src.utils.sanitize import sanitize_diagnostic_text, sanitize_sensitive_text

_SANITIZERS = {
    "sanitize_diagnostic_text": sanitize_diagnostic_text,
    "sanitize_sensitive_text": sanitize_sensitive_text,
    "sanitize_agent_diagnostic": sanitize_agent_diagnostic,
}

_CONNECTION_STRINGS = {
    "postgresql": ("sqlalchemy error postgresql://svc:MyDbPass123@db.internal:5432/prod", "MyDbPass123"),
    "mysql": ("mysql error mysql://root:rootpw999@127.0.0.1/app", "rootpw999"),
    "redis": ("redis conn redis://:RedisSecret9@cache.host:6379/0", "RedisSecret9"),
    "amqp": ("amqp amqp://guest:guestpw@rabbit:5672/vhost", "guestpw"),
    # Unescaped '@' inside the password must be redacted fully (no tail leak).
    "mongodb_at_in_password": ("mongo mongodb://admin:M0ngoP@ssWord9@mongo:27017/db", "M0ngoP@ssWord9"),
}


@pytest.mark.parametrize("sanitizer_name", list(_SANITIZERS), ids=list(_SANITIZERS))
@pytest.mark.parametrize("scheme", list(_CONNECTION_STRINGS), ids=list(_CONNECTION_STRINGS))
def test_connection_string_password_is_redacted(sanitizer_name, scheme):
    sanitizer = _SANITIZERS[sanitizer_name]
    raw, secret = _CONNECTION_STRINGS[scheme]
    sanitized = sanitizer(raw)
    assert secret not in sanitized
    assert "[REDACTED]@" in sanitized
    # The host is preserved so the diagnostic stays useful.
    assert "@" in sanitized


def test_http_urls_and_plain_text_are_unchanged():
    # No regression: existing http(s) redaction and ordinary text are intact.
    assert "[REDACTED_URL]" in sanitize_diagnostic_text("boom https://user:pass@example.com/path")
    assert sanitize_sensitive_text("visit https://example.com/docs") == "visit https://example.com/docs"
    # A bare email in prose (no scheme://) is not a credential URL.
    assert sanitize_sensitive_text("contact user@example.com about it") == "contact user@example.com about it"
