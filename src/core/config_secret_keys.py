# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Shared heuristics for config keys that carry secrets.

Used by the config registry (settings UI / API masking), profile export, and
onboarding so secret-bearing names stay consistent without per-callsite drift.

Rules (applied in order):
1. Empty names are not classified here (callers decide fail-open vs fail-closed).
2. Exact secret allowlist (known secret containers without KEY/TOKEN markers).
3. Exact non-secret denylist and structural suffixes (token *counts*, public keys,
   keywords, key version labels).
4. Explicit secret suffixes (extra headers, install specs).
5. Substring markers: KEY / TOKEN / SECRET / PASSWORD / PASSWD / CREDENTIAL.

Registered field definitions may still override ``is_sensitive`` explicitly.
"""

from __future__ import annotations

import re
from typing import Final

# Known secret containers that do not include KEY/TOKEN/SECRET/PASSWORD markers.
_SECRET_EXACT: Final[frozenset[str]] = frozenset(
    {
        "LITELLM_CONFIG",
        "ALPHASIFT_INSTALL_SPEC",
    }
)

# Registered structural fields that match crude markers but are not credentials.
_NON_SECRET_EXACT: Final[frozenset[str]] = frozenset(
    {
        "AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS",
        "ANTHROPIC_MAX_TOKENS",
        "DISCORD_INTERACTIONS_PUBLIC_KEY",
        "FEISHU_WEBHOOK_KEYWORD",
        "LLM_USAGE_HMAC_KEY_VERSION",
    }
)

# Quantity / structural suffixes that embed TOKEN or KEY without holding secrets.
_NON_SECRET_SUFFIX_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:"
    r"_MAX_TOKENS|"
    r"_MIN_TOKENS|"
    r"_TRIGGER_TOKENS|"
    r"_OUTPUT_TOKENS|"
    r"_CONTEXT_TOKENS|"
    r"_PROMPT_TOKENS|"
    r"_COMPLETION_TOKENS|"
    r"_TOKEN_LIMIT|"
    r"_TOKEN_COUNT|"
    r"_TOKEN_BUDGET|"
    r"_TOKEN_WINDOW|"
    r"_TOKEN_USAGE|"
    r"_KEY_VERSION|"
    r"_KEY_NAME|"
    r"_KEY_ID|"
    r"_KEYWORD|"
    r"_KEYWORDS"
    r")$"
)

_NON_SECRET_CONTAINS: Final[tuple[str, ...]] = (
    "_PUBLIC_KEY",
    "_PUBLIC_KEYS",
)

_SECRET_SUFFIXES: Final[tuple[str, ...]] = (
    "_EXTRA_HEADERS",
    "_INSTALL_SPEC",
)

# Substring markers for credential-bearing env names.
_SECRET_MARKERS: Final[tuple[str, ...]] = (
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
    "TOKEN",
    "KEY",
)


def normalize_config_key_name(key: str | None) -> str:
    """Return an upper-cased, trimmed config key name."""
    return str(key or "").strip().upper()


def is_sensitive_config_key_name(key: str | None) -> bool:
    """Return True when a config *name* should be treated as secret-bearing.

    Empty names return False so UI inference does not invent a secret field.
    Profile / onboarding callers that must fail closed on empty input should
    check emptiness before calling this helper (see ``is_secret_config_key``).
    """
    normalized = normalize_config_key_name(key)
    if not normalized:
        return False

    if normalized in _SECRET_EXACT:
        return True
    if normalized in _NON_SECRET_EXACT:
        return False
    if _NON_SECRET_SUFFIX_RE.search(normalized):
        return False
    if any(fragment in normalized for fragment in _NON_SECRET_CONTAINS):
        return False
    if any(normalized.endswith(suffix) for suffix in _SECRET_SUFFIXES):
        return True
    return any(marker in normalized for marker in _SECRET_MARKERS)


def is_secret_config_key(key: str | None) -> bool:
    """Return True when a key must never enter profiles / onboarding writes.

    Empty or whitespace-only names fail closed (treated as secret) so callers
    cannot smuggle writes through blank keys.
    """
    normalized = normalize_config_key_name(key)
    if not normalized:
        return True
    return is_sensitive_config_key_name(normalized)


__all__ = (
    "is_secret_config_key",
    "is_sensitive_config_key_name",
    "normalize_config_key_name",
)
