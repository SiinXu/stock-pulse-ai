# -*- coding: utf-8 -*-
"""Shared text sanitizers for logs, diagnostics, and API payloads."""

from __future__ import annotations

import inspect
import json
import logging
import re
from typing import Any, Callable, Iterable, Mapping, Optional
from urllib.parse import parse_qsl, unquote, urlsplit


_REDACTED = "[REDACTED]"
_URL_USERINFO_REDACTION = "__STOCKPULSE_REDACTED__"
_SENSITIVE_KEY_PARTS = {
    "authorization",
    "cookie",
    "credential",
    "passwd",
    "password",
    "secret",
    "sendkey",
    "token",
    "webhook",
}
_SENSITIVE_KEY_PHRASES = {
    "access_token",
    "accesstoken",
    "api_key",
    "apikey",
    "api_token",
    "apitoken",
    "auth_token",
    "authtoken",
    "authorization_header",
    "authorizationheader",
    "license_key",
    "licensekey",
    "private_key",
    "privatekey",
    "proxy_authorization",
    "proxyauthorization",
    "proxy_url",
    "proxyurl",
    "raw_prompt",
    "raw_response",
    "refresh_token",
    "refreshtoken",
    "secret_key",
    "secretkey",
    "session_token",
    "sessiontoken",
    "send_key",
    "sendkey",
    "webhook_secret",
    "webhooksecret",
    "webhook_url",
    "webhookurl",
}
_SENSITIVE_COMPACT_KEY_PHRASES = {
    phrase.replace("_", "") for phrase in _SENSITIVE_KEY_PHRASES
}
_SENSITIVE_COMPACT_KEY_PATTERN = re.compile(
    r"authorization|cookie|credential|passwd|password|rawresponse|secret|"
    r"sendkey|token(?!s)|webhook"
)
_URL_PATTERN = re.compile(r"https?://[^\s,;)\]}]+", re.IGNORECASE)
# Credentials in the userinfo of a connection-string URL of any scheme
# (postgresql://, mysql://, redis://, mongodb://, amqp://, ...). _URL_PATTERN
# only covers http(s), so a password embedded in a non-HTTP connection string
# (e.g. a SQLAlchemy error) would otherwise leak into a diagnostic. The
# userinfo segment matches greedily up to the last '@' before the host, so both
# username-only tokens and username:password credentials are redacted; the '/'
# boundary keeps the match from spilling into the host or path.
_URL_CREDENTIALS_PATTERN = re.compile(
    r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.\-]*://)[^\s/?#]+@"
)
_BEARER_PATTERN = re.compile(
    r"\b(bearer\s+)[^\s,;&\"']+",
    re.IGNORECASE,
)
_DIGEST_AUTH_PARAM_PATTERN = (
    r"[A-Za-z][A-Za-z0-9_-]*\s*=\s*"
    r'(?:"(?:\\.|[^"\\])*"|[^,;\s]+)'
)
_DIGEST_AUTHORIZATION_HEADER_PATTERN = re.compile(
    r"\b(authorization|proxy[_-]?authorization)(\s*[:=]\s*)"
    rf"Digest\s+{_DIGEST_AUTH_PARAM_PATTERN}"
    rf"(?:\s*,\s*{_DIGEST_AUTH_PARAM_PATTERN})*",
    re.IGNORECASE,
)
_AUTHORIZATION_HEADER_PATTERN = re.compile(
    r"\b(authorization|proxy[_-]?authorization)(\s*[:=]\s*)"
    r"(?:(?:Bearer|Basic|Token|Digest|ApiKey|Api-Key|HMAC|Negotiate|OAuth)\s+)?"
    r"[^\s,;&\"']+",
    re.IGNORECASE,
)
_OPAQUE_AUTHORIZATION_SCHEME_PATTERN = re.compile(
    r"\b(authorization|proxy[_-]?authorization)(\s*[:=]\s*)"
    r"[A-Za-z][A-Za-z0-9._~-]{0,31}\s+"
    r"[A-Za-z0-9._~+/=-]{12,}(?=$|[\s,;&\"'])",
    re.IGNORECASE,
)
_COOKIE_VALUE_PATTERN = r'(?:"(?:\\.|[^"\\])*"|[^,;\s]+)'
_COOKIE_PAIR_PATTERN = rf"[^=,;\s]+={_COOKIE_VALUE_PATTERN}"
_COOKIE_HEADER_PATTERN = re.compile(
    r"(?<!set-)(?<!set_)\b(cookie)(\s*:\s*)"
    rf"{_COOKIE_VALUE_PATTERN}(?:\s*;\s*{_COOKIE_PAIR_PATTERN})*",
    re.IGNORECASE,
)
_SET_COOKIE_HEADER_PATTERN = re.compile(
    r"\b(set[_-]?cookie)(\s*:\s*)"
    rf"{_COOKIE_VALUE_PATTERN}",
    re.IGNORECASE,
)
_SET_COOKIE_SENSITIVE_ATTRIBUTE_PATTERN = re.compile(
    r"\b(set[_-]?cookie)(\s*:\s*)\[REDACTED\]"
    r"(?=[^\r\n]*;\s*[A-Za-z0-9_-]*"
    r"(?:auth|credential|key|password|secret|session|token)"
    r"[A-Za-z0-9_-]*\s*=)[^\r\n]+",
    re.IGNORECASE,
)
_COOKIE_ASSIGNMENT_PATTERN = re.compile(
    r"\b(cookie|set[_-]?cookie)(\s*=\s*)"
    rf"{_COOKIE_VALUE_PATTERN}(?:\s*;\s*{_COOKIE_PAIR_PATTERN})*",
    re.IGNORECASE,
)
_SENSITIVE_ASSIGNMENT_KEY_PATTERN = (
    r"(?:[a-z0-9]+[_-])*?(?:"
    r"token|secret|passwd|password|credential|credentials|sendkey|x[_-]?api[_-]?key|"
    r"api[_-]?key|apikey|api[_-]?token|auth[_-]?token|"
    r"access[_-]?token|refresh[_-]?token|session[_-]?token|license[_-]?key|private[_-]?key|"
    r"secret[_-]?key|webhook[_-]?(?:url|secret)|authorization|"
    r"proxy[_-]?(?:authorization|url)|cookie|set[_-]?cookie|headers?|"
    r"prompt|raw[_-]?prompt|raw[_-]?response"
    r")"
)
_QUOTED_SECRET_ASSIGNMENT_PATTERN = re.compile(
    rf"(?P<key_quote>['\"])(?P<key>{_SENSITIVE_ASSIGNMENT_KEY_PATTERN})(?P=key_quote)"
    r"(?P<separator>\s*:\s*)"
    r"(?P<value_quote>['\"])(?P<value>(?:\\.|(?!(?P=value_quote)).)*)(?P=value_quote)",
    re.IGNORECASE,
)
_QUOTED_SECRET_LITERAL_ASSIGNMENT_PATTERN = re.compile(
    rf"(?P<key_quote>['\"])(?P<key>{_SENSITIVE_ASSIGNMENT_KEY_PATTERN})(?P=key_quote)"
    r"(?P<separator>\s*:\s*)"
    r"(?!\[REDACTED\])"
    r"(?P<value>[^,\}\]\s'\"]+)",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    rf"\b({_SENSITIVE_ASSIGNMENT_KEY_PATTERN})(\s*[=:]\s*)"
    r"[^\s,;&\"']+",
    re.IGNORECASE,
)
_TOKEN_LIKE_PATTERN = re.compile(
    r"\b(?:"
    r"sk-[a-z0-9_\-]{12,}|"
    r"(?:sk|rk)_(?:live|test)_[a-z0-9]{12,}|"
    r"xox[baprs]-[a-z0-9\-]{12,}|"
    r"gh[pousr]_[a-z0-9_]{16,}|"
    r"github_pat_[a-z0-9_]{16,}|"
    r"AIza[a-z0-9_\-]{16,}|"
    r"(?:AKIA|ASIA)[a-z0-9]{16}|"
    r"SG\.[a-z0-9_\-]{12,}\.[a-z0-9_\-]{12,}"
    r")\b",
    re.IGNORECASE,
)
_OPAQUE_TOKEN_PATTERN = re.compile(r"\b[A-Za-z0-9_-]{32,}\b")
_SAFE_EXCEPTION_CHAIN_LIMIT = 4
_SAFE_EXCEPTION_PART_MAX_LENGTH = 240
_SAFE_EXCEPTION_SUMMARY_MAX_LENGTH = 900
_EXACT_REDACTION_VALUE_LIMIT = 64
_EXCEPTION_REDACTION_FAIL_CLOSED_LIMIT = _EXACT_REDACTION_VALUE_LIMIT + 1
_SAFE_RENDER_FAILURE = "[UNRENDERABLE]"
_UNSAFE_EXCEPTION_ACCESS = object()
_EXCEPTION_REDACTION_PROVENANCE = "\0stockpulse-exception-redaction\0"


class _ExceptionRedactionSnapshot:
    def __init__(self, root_id: int) -> None:
        self.root_id = root_id
        self.summary = _SAFE_RENDER_FAILURE


class _ExceptionRedactionValue(str):
    """Carry snapshot provenance without changing the public set contract."""

    def __new__(cls, value: str, snapshot: _ExceptionRedactionSnapshot):
        instance = super().__new__(cls, value)
        instance.snapshot = snapshot
        return instance

    def __copy__(self):
        return self

    def __deepcopy__(self, memo: dict[int, Any]):
        memo[id(self)] = self
        return self

    def __reduce__(self):
        return type(self), (str(self), self.snapshot)


class _ExceptionRedactionMarker(str):
    """Keep provenance when an empty or failed snapshot is copied or merged."""

    def __new__(cls, snapshot: _ExceptionRedactionSnapshot):
        instance = super().__new__(cls, _EXCEPTION_REDACTION_PROVENANCE)
        instance.snapshot = snapshot
        return instance

    def __hash__(self) -> int:
        return object.__hash__(self)

    def __eq__(self, other: object) -> bool:
        return self is other

    def __ne__(self, other: object) -> bool:
        return self is not other

    def __copy__(self):
        return self

    def __deepcopy__(self, memo: dict[int, Any]):
        memo[id(self)] = self
        return self

    def __reduce__(self):
        return type(self), (self.snapshot,)


class _ExceptionRedactionValues(set[str]):
    """Exact redactions paired with a single-render sanitized chain snapshot."""

    def __init__(self, root_id: int) -> None:
        super().__init__()
        self.snapshot = _ExceptionRedactionSnapshot(root_id)
        super().add(_ExceptionRedactionMarker(self.snapshot))

    def add_snapshot_value(self, value: str) -> None:
        super().add(_ExceptionRedactionValue(value, self.snapshot))

    def __copy__(self) -> set[str]:
        return set(self)

    def __deepcopy__(self, memo: dict[int, Any]) -> set[str]:
        del memo
        return set(self)

    @property
    def root_id(self) -> int:
        return self.snapshot.root_id

    @property
    def summary(self) -> str:
        return self.snapshot.summary

    @summary.setter
    def summary(self, value: str) -> None:
        self.snapshot.summary = value


class _NormalizedRedactionValues(tuple):
    """Normalized exact values with optional exception snapshot provenance."""

    def __new__(
        cls,
        values: Iterable[str],
        *,
        exception_snapshots: Iterable[_ExceptionRedactionSnapshot] = (),
    ):
        instance = super().__new__(cls, values)
        instance.exception_snapshots = tuple(exception_snapshots)
        return instance

    def __init__(
        self,
        values: Iterable[str],
        *,
        exception_snapshots: Iterable[_ExceptionRedactionSnapshot] = (),
    ) -> None:
        del values, exception_snapshots


def _bounded_render_failure(max_length: Any) -> str:
    """Return the fixed render-failure marker without trusting a custom bound."""

    if type(max_length) is not int:
        return _SAFE_RENDER_FAILURE
    return _SAFE_RENDER_FAILURE[: max(0, max_length)]


def _safe_string(value: Any) -> str:
    """Render one value without consulting repr or propagating conversion failures."""

    if value is None:
        return ""
    try:
        return str(value)
    except BaseException:
        return _SAFE_RENDER_FAILURE


def _safe_structured_string(
    value: Any,
    *,
    nested: bool = False,
    _custom_values: Optional[dict[int, str]] = None,
) -> str:
    """Render built-in containers without invoking repr on nested custom objects."""

    if _custom_values is None:
        _custom_values = {}

    if type(value) is str:
        return repr(value) if nested else value
    if value is None:
        return "None" if nested else ""
    if type(value) in {bool, int, float, complex, bytes}:
        return str(value)
    if type(value) is dict:
        try:
            items = (
                f"{_safe_structured_string(key, nested=True, _custom_values=_custom_values)}: "
                f"{_safe_structured_string(item, nested=True, _custom_values=_custom_values)}"
                for key, item in value.items()
            )
            return "{" + ", ".join(items) + "}"
        except BaseException:
            return _SAFE_RENDER_FAILURE
    if type(value) is list:
        try:
            return "[" + ", ".join(
                _safe_structured_string(
                    item,
                    nested=True,
                    _custom_values=_custom_values,
                )
                for item in value
            ) + "]"
        except BaseException:
            return _SAFE_RENDER_FAILURE
    if type(value) is tuple:
        try:
            rendered = ", ".join(
                _safe_structured_string(
                    item,
                    nested=True,
                    _custom_values=_custom_values,
                )
                for item in value
            )
            if len(value) == 1:
                rendered += ","
            return f"({rendered})"
        except BaseException:
            return _SAFE_RENDER_FAILURE
    if type(value) in {set, frozenset}:
        try:
            rendered_items = sorted(
                _safe_structured_string(
                    item,
                    nested=True,
                    _custom_values=_custom_values,
                )
                for item in value
            )
            if type(value) is set:
                return "set()" if not rendered_items else "{" + ", ".join(rendered_items) + "}"
            if not rendered_items:
                return "frozenset()"
            return "frozenset({" + ", ".join(rendered_items) + "})"
        except BaseException:
            return _SAFE_RENDER_FAILURE

    identity = id(value)
    rendered = _custom_values.get(identity)
    if rendered is None:
        rendered = _safe_string(value)
        _custom_values[identity] = rendered
    return repr(rendered) if nested else rendered


def _normalize_redaction_values(
    redaction_values: Optional[Iterable[Any]],
) -> Optional[_NormalizedRedactionValues]:
    """Return bounded exact-match values, or None when normalization is unsafe."""
    if isinstance(redaction_values, _NormalizedRedactionValues):
        return redaction_values
    if redaction_values is None:
        return _NormalizedRedactionValues(())
    candidates: Iterable[Any]
    if isinstance(redaction_values, (str, bytes)):
        candidates = (redaction_values,)
    else:
        candidates = redaction_values

    normalized: set[str] = set()
    snapshots: dict[int, _ExceptionRedactionSnapshot] = {}
    if isinstance(redaction_values, _ExceptionRedactionValues):
        snapshots[redaction_values.root_id] = redaction_values.snapshot
    try:
        iterator = iter(candidates)
    except TypeError:
        iterator = iter((candidates,))
    except BaseException:
        return None
    try:
        for value in iterator:
            if value is None:
                continue
            if isinstance(value, (_ExceptionRedactionValue, _ExceptionRedactionMarker)):
                snapshot = value.snapshot
                snapshots[snapshot.root_id] = snapshot
                if isinstance(value, _ExceptionRedactionMarker):
                    continue
            rendered = (
                value.decode("utf-8", errors="replace")
                if isinstance(value, bytes)
                else str(value)
            )
            if rendered == _EXCEPTION_REDACTION_PROVENANCE:
                return None
            if rendered == _SAFE_RENDER_FAILURE:
                continue
            if rendered.strip():
                normalized.add(rendered)
                if len(normalized) > _EXACT_REDACTION_VALUE_LIMIT:
                    return None
    except BaseException:
        return None
    return _NormalizedRedactionValues(
        sorted(normalized, key=len, reverse=True),
        exception_snapshots=snapshots.values(),
    )


def _matching_exception_snapshot(
    values: _NormalizedRedactionValues,
    error: Any,
) -> Optional[_ExceptionRedactionSnapshot]:
    root_id = id(error)
    return next(
        (
            snapshot
            for snapshot in values.exception_snapshots
            if snapshot.root_id == root_id
        ),
        None,
    )


def has_matching_exception_snapshot(
    error: Any,
    redaction_values: Optional[Iterable[Any]],
) -> bool:
    """Return whether values carry a single-render snapshot for ``error``."""

    exact_values = _normalize_redaction_values(redaction_values)
    return (
        exact_values is not None
        and _matching_exception_snapshot(exact_values, error) is not None
    )


def _redact_exact_values(text: str, redaction_values: tuple[str, ...]) -> str:
    """Replace caller-provided sensitive values before pattern sanitization."""
    redacted = text
    for value in redaction_values:
        redacted = redacted.replace(value, _REDACTED)
    return redacted


def _redact_common_secret_patterns(
    text: str,
    *,
    redact_all_http_urls: bool,
    redact_opaque_tokens: bool = False,
    preserve_http_credential_hosts: bool = False,
) -> str:
    """Apply the shared secret pattern set to one already-rendered string."""

    sanitized = text
    if preserve_http_credential_hosts and not redact_all_http_urls:
        sanitized = _URL_CREDENTIALS_PATTERN.sub(
            rf"\g<scheme>{_URL_USERINFO_REDACTION}@",
            sanitized,
        )
    if redact_all_http_urls:
        sanitized = _URL_PATTERN.sub("[REDACTED_URL]", sanitized)
    else:
        sanitized = _URL_PATTERN.sub(_redact_sensitive_url_match, sanitized)
    sanitized = _URL_CREDENTIALS_PATTERN.sub(
        r"\g<scheme>[REDACTED]@",
        sanitized,
    )
    sanitized = sanitized.replace(
        f"{_URL_USERINFO_REDACTION}@",
        "[REDACTED]@",
    )
    sanitized = _DIGEST_AUTHORIZATION_HEADER_PATTERN.sub(
        r"\1\2[REDACTED]",
        sanitized,
    )
    sanitized = _OPAQUE_AUTHORIZATION_SCHEME_PATTERN.sub(
        r"\1\2[REDACTED]",
        sanitized,
    )
    sanitized = _AUTHORIZATION_HEADER_PATTERN.sub(r"\1\2[REDACTED]", sanitized)
    sanitized = _COOKIE_HEADER_PATTERN.sub(r"\1\2[REDACTED]", sanitized)
    sanitized = _SET_COOKIE_HEADER_PATTERN.sub(r"\1\2[REDACTED]", sanitized)
    sanitized = _SET_COOKIE_SENSITIVE_ATTRIBUTE_PATTERN.sub(
        r"\1\2[REDACTED]",
        sanitized,
    )
    sanitized = _COOKIE_ASSIGNMENT_PATTERN.sub(r"\1\2[REDACTED]", sanitized)
    sanitized = _BEARER_PATTERN.sub(r"\1[REDACTED]", sanitized)
    sanitized = _QUOTED_SECRET_ASSIGNMENT_PATTERN.sub(
        r"\g<key_quote>\g<key>\g<key_quote>\g<separator>"
        r"\g<value_quote>[REDACTED]\g<value_quote>",
        sanitized,
    )
    sanitized = _QUOTED_SECRET_LITERAL_ASSIGNMENT_PATTERN.sub(
        r"\g<key_quote>\g<key>\g<key_quote>\g<separator>[REDACTED]",
        sanitized,
    )
    sanitized = _SECRET_ASSIGNMENT_PATTERN.sub(r"\1\2[REDACTED]", sanitized)
    sanitized = _TOKEN_LIKE_PATTERN.sub("[REDACTED]", sanitized)
    if redact_opaque_tokens:
        sanitized = _OPAQUE_TOKEN_PATTERN.sub("[REDACTED]", sanitized)
    return sanitized


def sanitize_diagnostic_text(
    text: Any,
    *,
    max_length: int = 300,
    redaction_values: Optional[Iterable[Any]] = None,
) -> str:
    """Redact common secrets and URLs from diagnostic text."""
    exact_values = _normalize_redaction_values(redaction_values)
    if exact_values is None:
        return _bounded_render_failure(max_length)
    snapshot = (
        _matching_exception_snapshot(exact_values, text)
        if isinstance(text, BaseException)
        else None
    )
    if snapshot is not None:
        return sanitize_diagnostic_text(
            snapshot.summary,
            max_length=max_length,
        )
    if isinstance(text, BaseException) and exact_values.exception_snapshots:
        return _bounded_render_failure(max_length)
    try:
        structured_text = (
            redact_sensitive_mapping(text)
            if isinstance(text, (Mapping, list, tuple, set, frozenset))
            else text
        )
    except BaseException:
        return _bounded_render_failure(max_length)
    sanitized = _safe_structured_string(structured_text).strip()
    if not sanitized:
        return ""
    sanitized = _redact_common_secret_patterns(
        _redact_exact_values(sanitized, exact_values),
        redact_all_http_urls=True,
    )
    return " ".join(sanitized.split())[:max_length]


def safe_exception_type_name(error: Any, *, max_length: int = 120) -> str:
    """Return a bounded exception type label without trusting its metaclass."""

    try:
        name = type(error).__name__
    except BaseException:
        return _bounded_render_failure(max_length)
    return (
        sanitize_diagnostic_text(name, max_length=max_length)
        or "BaseException"
    )


def _safe_exception_diagnostic_source(error: BaseException) -> Any:
    """Select a diagnostic source without triggering built-in nested repr paths."""

    try:
        args = error.args
        if type(args) is not tuple:
            return _UNSAFE_EXCEPTION_ACCESS
        if not args:
            return error

        string_method = inspect.getattr_static(type(error), "__str__", None)
        render_args = (
            len(args) > 1
            or isinstance(args[0], (Mapping, list, tuple, set, frozenset))
            or inspect.ismethoddescriptor(string_method)
        )
        if render_args:
            return args[0] if len(args) == 1 else args
        return error
    except BaseException:
        return _UNSAFE_EXCEPTION_ACCESS


def _safe_next_exception(error: BaseException) -> Any:
    """Read the next explicit or implicit exception without propagating access errors."""

    try:
        cause = error.__cause__
        if cause is not None:
            return cause if isinstance(cause, BaseException) else _UNSAFE_EXCEPTION_ACCESS

        suppress_context = error.__suppress_context__
        if type(suppress_context) is not bool:
            return _UNSAFE_EXCEPTION_ACCESS
        if suppress_context:
            return None

        context = error.__context__
        if context is None or isinstance(context, BaseException):
            return context
        return _UNSAFE_EXCEPTION_ACCESS
    except BaseException:
        return _UNSAFE_EXCEPTION_ACCESS


def sanitize_exception_chain(
    exc: BaseException,
    *,
    max_length: int = _SAFE_EXCEPTION_SUMMARY_MAX_LENGTH,
    redaction_values: Optional[Iterable[Any]] = None,
    redact_diagnostics: bool = False,
) -> str:
    """Return a bounded, sanitized summary of an exception and its causes."""
    exact_values = _normalize_redaction_values(redaction_values)
    if exact_values is None:
        return _bounded_render_failure(max_length)
    snapshot = _matching_exception_snapshot(exact_values, exc)
    if snapshot is not None:
        return sanitize_diagnostic_text(
            snapshot.summary,
            max_length=max_length,
        )
    if exact_values.exception_snapshots:
        return sanitize_exception_chain(
            exc,
            max_length=max_length,
            redaction_values=tuple(exact_values),
            redact_diagnostics=True,
        )
    try:
        parts: list[str] = []
        current: Optional[BaseException] = exc
        seen: set[int] = set()
        while current is not None and len(parts) < _SAFE_EXCEPTION_CHAIN_LIMIT:
            identity = id(current)
            if identity in seen:
                break
            seen.add(identity)

            if redact_diagnostics:
                diagnostic = _REDACTED
            else:
                diagnostic_source = _safe_exception_diagnostic_source(current)
                if diagnostic_source is _UNSAFE_EXCEPTION_ACCESS:
                    return _bounded_render_failure(max_length)
                diagnostic = sanitize_diagnostic_text(
                    diagnostic_source,
                    max_length=_SAFE_EXCEPTION_PART_MAX_LENGTH,
                    redaction_values=exact_values,
                ) or "no diagnostic message"
            exception_type = safe_exception_type_name(current, max_length=80)
            parts.append(
                sanitize_diagnostic_text(
                    f"{exception_type}: {diagnostic}",
                    max_length=_SAFE_EXCEPTION_PART_MAX_LENGTH,
                    redaction_values=exact_values,
                )
            )

            next_exception = _safe_next_exception(current)
            if next_exception is _UNSAFE_EXCEPTION_ACCESS:
                return _bounded_render_failure(max_length)
            current = next_exception
        return sanitize_diagnostic_text(
            " <- ".join(parts),
            max_length=max_length,
            redaction_values=exact_values,
        )
    except BaseException:
        return _bounded_render_failure(max_length)


def exception_chain_redaction_values(error: Any) -> set[str]:
    """Return bounded exact values with opaque single-render provenance."""

    values = _ExceptionRedactionValues(id(error))
    summary_parts: list[str] = []
    current = error
    seen: set[int] = set()
    rendered_custom_values: dict[int, str] = {}
    while current is not None and len(seen) < _SAFE_EXCEPTION_CHAIN_LIMIT:
        identity = id(current)
        if identity in seen:
            break
        seen.add(identity)
        if not isinstance(current, BaseException):
            break

        diagnostic_source = _safe_exception_diagnostic_source(current)
        if diagnostic_source is _UNSAFE_EXCEPTION_ACCESS:
            return values
        rendered = _safe_structured_string(
            diagnostic_source,
            _custom_values=rendered_custom_values,
        ).strip()
        if rendered == _SAFE_RENDER_FAILURE:
            return values
        if rendered and rendered != _SAFE_RENDER_FAILURE:
            examined_chunks = 0
            for offset in range(0, len(rendered), _SAFE_EXCEPTION_PART_MAX_LENGTH):
                chunk = rendered[offset : offset + _SAFE_EXCEPTION_PART_MAX_LENGTH]
                if chunk:
                    values.add_snapshot_value(chunk)
                examined_chunks += 1
                if len(values) >= _EXCEPTION_REDACTION_FAIL_CLOSED_LIMIT:
                    return values
                if examined_chunks >= _EXCEPTION_REDACTION_FAIL_CLOSED_LIMIT:
                    break

        diagnostic_markers = [_REDACTED]
        if rendered:
            sanitized_rendered = sanitize_diagnostic_text(
                rendered,
                max_length=_SAFE_EXCEPTION_PART_MAX_LENGTH,
            )
            if "[REDACTED_URL]" in sanitized_rendered:
                diagnostic_markers.append("[REDACTED_URL]")
        diagnostic = " ".join(diagnostic_markers)
        summary_parts.append(
            sanitize_diagnostic_text(
                f"{safe_exception_type_name(current, max_length=80)}: {diagnostic}",
                max_length=_SAFE_EXCEPTION_PART_MAX_LENGTH,
            )
        )

        next_exception = _safe_next_exception(current)
        if next_exception is _UNSAFE_EXCEPTION_ACCESS:
            return values
        current = next_exception
    values.summary = sanitize_diagnostic_text(
        " <- ".join(summary_parts),
        max_length=_SAFE_EXCEPTION_SUMMARY_MAX_LENGTH,
    ) or _SAFE_RENDER_FAILURE
    return values


def _safe_log_context_fields(
    context: Optional[Mapping[str, Any]],
    *,
    redaction_values: Optional[Iterable[Any]] = None,
) -> list[str]:
    """Render structured log context as sanitized key-value fields."""
    fields: list[str] = []
    if context is None:
        return fields
    try:
        for key, value in context.items():
            rendered_key = _safe_string(key)
            if rendered_key == _SAFE_RENDER_FAILURE:
                return [f"context={_SAFE_RENDER_FAILURE}"]
            safe_key = re.sub(r"[^A-Za-z0-9_.-]", "_", rendered_key)[:80]
            if not safe_key:
                continue
            safe_value = (
                _REDACTED
                if _is_sensitive_mapping_key_text(rendered_key)
                else sanitize_diagnostic_text(
                    value,
                    max_length=180,
                    redaction_values=redaction_values,
                )
            )
            if safe_key and safe_value:
                fields.append(f"{safe_key}={safe_value}")
    except BaseException:
        return [f"context={_SAFE_RENDER_FAILURE}"]
    return fields


def log_safe_exception(
    target_logger: logging.Logger,
    event: str,
    exc: BaseException,
    *,
    error_code: str,
    level: int = logging.ERROR,
    trace_id: Optional[str] = None,
    method: Optional[str] = None,
    path: Optional[str] = None,
    context: Optional[Mapping[str, Any]] = None,
    redaction_values: Optional[Iterable[Any]] = None,
    exception_redaction_values: Optional[Iterable[Any]] = None,
) -> None:
    """Log a sanitized exception summary without attaching raw exception info."""
    structural_values = _normalize_redaction_values(redaction_values)
    exception_values = _normalize_redaction_values(exception_redaction_values)
    if structural_values is None or exception_values is None:
        message = _SAFE_RENDER_FAILURE
    else:
        try:
            snapshot = (
                _matching_exception_snapshot(exception_values, exc)
                or _matching_exception_snapshot(structural_values, exc)
            )
            summary_values = _normalize_redaction_values(
                (*structural_values, *exception_values)
            )
            if summary_values is None:
                raise ValueError("unsafe exception redaction values")
            fields = [
                sanitize_diagnostic_text(
                    event,
                    max_length=160,
                    redaction_values=structural_values,
                ) or "Unhandled exception",
                "error_code="
                f"{sanitize_diagnostic_text(error_code, max_length=120, redaction_values=structural_values) or 'unknown_error'}",
            ]
            for field_name, value, field_limit in (
                ("trace_id", trace_id, 128),
                ("method", method, 16),
                ("path", path, 240),
            ):
                if value is None:
                    continue
                safe_value = sanitize_diagnostic_text(
                    value,
                    max_length=field_limit,
                    redaction_values=structural_values,
                )
                if safe_value:
                    fields.append(f"{field_name}={safe_value}")
            fields.extend(
                _safe_log_context_fields(context, redaction_values=structural_values)
            )
            if snapshot is not None:
                summary = sanitize_diagnostic_text(
                    snapshot.summary,
                    max_length=_SAFE_EXCEPTION_SUMMARY_MAX_LENGTH,
                    redaction_values=summary_values,
                )
            elif (
                structural_values.exception_snapshots
                or exception_values.exception_snapshots
                or exception_redaction_values is not None
            ):
                summary = sanitize_exception_chain(
                    exc,
                    redaction_values=summary_values,
                    redact_diagnostics=True,
                )
            else:
                summary = sanitize_exception_chain(
                    exc,
                    redaction_values=summary_values,
                )
            fields.extend(
                (
                    f"exception_type={safe_exception_type_name(exc)}",
                    f"summary={summary}",
                    f"diagnostic={summary}",
                )
            )
            message = " ".join(fields)
        except BaseException:
            message = _SAFE_RENDER_FAILURE
    target_logger.log(level, message)


def safe_before_sleep_log(
    target_logger: logging.Logger,
    level: int = logging.WARNING,
    *,
    event: str,
    error_code: str,
    context: Optional[Mapping[str, Any]] = None,
    redaction_values: Optional[Iterable[Any]] = None,
) -> Callable[[Any], None]:
    """Build a Tenacity-compatible retry callback without logging raw outcomes."""
    context_snapshot_failed = False
    try:
        static_context = dict(context.items()) if context is not None else {}
    except BaseException:
        static_context = {}
        context_snapshot_failed = True
    exact_values = _normalize_redaction_values(redaction_values)

    def _log_retry(retry_state: Any) -> None:
        """Log one retry state without exposing its raw outcome."""
        if exact_values is None:
            target_logger.log(level, _SAFE_RENDER_FAILURE)
            return
        retry_context = dict(static_context)
        if context_snapshot_failed:
            retry_context["context"] = _SAFE_RENDER_FAILURE
        retry_exception: Optional[BaseException] = None
        try:
            attempt_number = getattr(retry_state, "attempt_number", None)
            if isinstance(attempt_number, int) and not isinstance(attempt_number, bool):
                retry_context["attempt"] = attempt_number

            next_action = getattr(retry_state, "next_action", None)
            wait_seconds = getattr(next_action, "sleep", None)
            if isinstance(wait_seconds, (int, float)) and not isinstance(wait_seconds, bool):
                retry_context["retry_in_seconds"] = wait_seconds

            outcome = getattr(retry_state, "outcome", None)
            exception_getter = getattr(outcome, "exception", None)
            if callable(exception_getter):
                candidate = exception_getter()
                if isinstance(candidate, BaseException):
                    retry_exception = candidate
        except BaseException as state_error:
            retry_exception = state_error

        if retry_exception is not None:
            try:
                retry_redaction_values = exception_chain_redaction_values(retry_exception)
            except BaseException:
                retry_redaction_values = None
            if retry_redaction_values is None:
                target_logger.log(level, _SAFE_RENDER_FAILURE)
                return
            log_safe_exception(
                target_logger,
                event,
                retry_exception,
                error_code=error_code,
                level=level,
                context=retry_context,
                redaction_values=exact_values,
                exception_redaction_values=retry_redaction_values,
            )
            return

        safe_error_code = sanitize_diagnostic_text(
            error_code,
            max_length=120,
            redaction_values=exact_values,
        )
        fields = [
            sanitize_diagnostic_text(
                event,
                max_length=160,
                redaction_values=exact_values,
            ) or "Retry scheduled",
            f"error_code={safe_error_code or 'retry_scheduled'}",
            *_safe_log_context_fields(
                retry_context,
                redaction_values=exact_values,
            ),
            "exception_type=none",
            "summary=retry scheduled without an exception outcome",
        ]
        target_logger.log(level, " ".join(fields))

    return _log_retry


def redact_sensitive_mapping(obj: Any) -> Any:
    """Recursively redact sensitive values from mappings by key name only.

    This helper intentionally does not inspect arbitrary string values. P1 only
    needs a deterministic serializer for AnalysisContextPack dictionaries.
    """
    if isinstance(obj, Mapping):
        redacted = {}
        for key, value in obj.items():
            if _is_sensitive_mapping_key(key):
                redacted[key] = _REDACTED
            else:
                redacted[key] = redact_sensitive_mapping(value)
        return redacted
    if isinstance(obj, list):
        return [redact_sensitive_mapping(item) for item in obj]
    if isinstance(obj, tuple):
        return tuple(redact_sensitive_mapping(item) for item in obj)
    if isinstance(obj, set):
        return {redact_sensitive_mapping(item) for item in obj}
    if isinstance(obj, frozenset):
        return frozenset(redact_sensitive_mapping(item) for item in obj)
    return obj


def is_sensitive_key(key: Any) -> bool:
    """Return whether a mapping key denotes secret-bearing data."""

    return _is_sensitive_mapping_key(key)


def redact_sensitive_text(
    text: Any,
    *,
    redaction_values: Optional[Iterable[Any]] = None,
    redact_opaque_tokens: bool = False,
    preserve_http_credential_hosts: bool = False,
) -> str:
    """Redact secrets while preserving ordinary text and whitespace."""

    exact_values = _normalize_redaction_values(redaction_values)
    if exact_values is None:
        return _SAFE_RENDER_FAILURE
    rendered = _safe_structured_string(text)
    if rendered == _SAFE_RENDER_FAILURE:
        return _SAFE_RENDER_FAILURE
    serialized_redaction = _redact_serialized_json_text(
        rendered,
        exact_values=exact_values,
        redact_opaque_tokens=redact_opaque_tokens,
        preserve_http_credential_hosts=preserve_http_credential_hosts,
    )
    if serialized_redaction is not None:
        return serialized_redaction
    return _redact_common_secret_patterns(
        _redact_exact_values(rendered, exact_values),
        redact_all_http_urls=False,
        redact_opaque_tokens=redact_opaque_tokens,
        preserve_http_credential_hosts=preserve_http_credential_hosts,
    )


def _redact_serialized_json_text(
    text: str,
    *,
    exact_values: _NormalizedRedactionValues,
    redact_opaque_tokens: bool,
    preserve_http_credential_hosts: bool,
) -> Optional[str]:
    """Use structural redaction for serialized JSON objects and arrays."""

    stripped = text.strip()
    if not stripped or stripped[0] not in "[{":
        return None
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, (dict, list)):
        return None
    redacted = _redact_sensitive_data_value(
        parsed,
        exact_values=exact_values,
        redact_opaque_tokens=redact_opaque_tokens,
        preserve_http_credential_hosts=preserve_http_credential_hosts,
        depth=0,
        seen=set(),
    )
    if redacted == parsed:
        return None
    try:
        return json.dumps(redacted, ensure_ascii=False)
    except (TypeError, ValueError):
        return _SAFE_RENDER_FAILURE


def redact_sensitive_data(
    obj: Any,
    *,
    redaction_values: Optional[Iterable[Any]] = None,
    redact_opaque_tokens: bool = False,
    preserve_http_credential_hosts: bool = False,
) -> Any:
    """Recursively redact secret keys and string values at output boundaries."""

    exact_values = _normalize_redaction_values(redaction_values)
    if exact_values is None:
        return _SAFE_RENDER_FAILURE
    return _redact_sensitive_data_value(
        obj,
        exact_values=exact_values,
        redact_opaque_tokens=redact_opaque_tokens,
        preserve_http_credential_hosts=preserve_http_credential_hosts,
        depth=0,
        seen=set(),
    )


def _redact_sensitive_data_value(
    obj: Any,
    *,
    exact_values: _NormalizedRedactionValues,
    redact_opaque_tokens: bool,
    preserve_http_credential_hosts: bool,
    depth: int,
    seen: set[int],
) -> Any:
    if depth > 20:
        return _REDACTED
    if obj is None or type(obj) in {bool, int, float}:
        return obj
    if type(obj) is str:
        return redact_sensitive_text(
            obj,
            redaction_values=exact_values,
            redact_opaque_tokens=redact_opaque_tokens,
            preserve_http_credential_hosts=preserve_http_credential_hosts,
        )
    if type(obj) is bytes:
        return redact_sensitive_text(
            obj.decode("utf-8", errors="replace"),
            redaction_values=exact_values,
            redact_opaque_tokens=redact_opaque_tokens,
            preserve_http_credential_hosts=preserve_http_credential_hosts,
        )
    if isinstance(obj, BaseException):
        return sanitize_exception_chain(
            obj,
            redaction_values=exact_values,
        )

    if isinstance(obj, (Mapping, list, tuple, set, frozenset)):
        identity = id(obj)
        if identity in seen:
            return _REDACTED
        seen.add(identity)
        try:
            if isinstance(obj, Mapping):
                redacted: dict[Any, Any] = {}
                for key, value in obj.items():
                    safe_key, sensitive_key = _redact_mapping_key(
                        key,
                        exact_values=exact_values,
                        redact_opaque_tokens=redact_opaque_tokens,
                        preserve_http_credential_hosts=preserve_http_credential_hosts,
                    )
                    if safe_key in redacted:
                        return _SAFE_RENDER_FAILURE
                    redacted[safe_key] = (
                        _REDACTED
                        if sensitive_key
                        else _redact_sensitive_data_value(
                            value,
                            exact_values=exact_values,
                            redact_opaque_tokens=redact_opaque_tokens,
                            preserve_http_credential_hosts=preserve_http_credential_hosts,
                            depth=depth + 1,
                            seen=seen,
                        )
                    )
                return redacted
            values = [
                _redact_sensitive_data_value(
                    value,
                    exact_values=exact_values,
                    redact_opaque_tokens=redact_opaque_tokens,
                    preserve_http_credential_hosts=preserve_http_credential_hosts,
                    depth=depth + 1,
                    seen=seen,
                )
                for value in obj
            ]
            if isinstance(obj, tuple):
                return tuple(values)
            if isinstance(obj, frozenset):
                return frozenset(values)
            if isinstance(obj, set):
                return set(values)
            return values
        except BaseException:  # broad-exception: optional_metadata - Hostile containers use a fixed marker.
            return _SAFE_RENDER_FAILURE
        finally:
            seen.discard(identity)

    return redact_sensitive_text(
        obj,
        redaction_values=exact_values,
        redact_opaque_tokens=redact_opaque_tokens,
        preserve_http_credential_hosts=preserve_http_credential_hosts,
    )


def sanitize_sensitive_text(text: Any) -> str:
    """Redact secrets and credential-bearing URLs without changing normal text."""
    sanitized = redact_sensitive_text(text).strip()
    if not sanitized:
        return ""
    return " ".join(sanitized.split())


def sanitize_decision_signal_text(text: Any) -> str:
    """Backward-compatible sanitizer for persisted decision-signal text."""
    return sanitize_sensitive_text(text)


def sanitize_decision_signal_payload(obj: Any) -> Any:
    """Redact decision-signal JSON payloads by sensitive keys and string values."""
    redacted = redact_sensitive_mapping(obj)
    return _sanitize_decision_signal_payload_values(redacted)


def _sanitize_decision_signal_payload_values(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            key: _sanitize_decision_signal_payload_values(value)
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [_sanitize_decision_signal_payload_values(item) for item in obj]
    if isinstance(obj, str):
        return sanitize_decision_signal_text(obj)
    return obj


def _redact_sensitive_url_match(match: re.Match[str]) -> str:
    url = match.group(0)
    if _is_sensitive_url(url):
        return "[REDACTED_URL]"
    return url


def _is_sensitive_url(url: str) -> bool:
    if _TOKEN_LIKE_PATTERN.search(url):
        return True
    try:
        parsed = urlsplit(url)
        username = parsed.username
        password = parsed.password
        hostname = parsed.hostname or ""
        path = unquote(unquote(parsed.path))
        query = parsed.query
        fragment = parsed.fragment
        if (
            (username or password)
            and not (
                username == _URL_USERINFO_REDACTION
                and password is None
            )
        ):
            return True
        if _is_webhook_url(hostname, path):
            return True
        return (
            _has_sensitive_url_params(query)
            or _has_sensitive_url_params(fragment)
        )
    except (TypeError, UnicodeError, ValueError):
        return True


def _is_webhook_url(hostname: str, path: str) -> bool:
    hostname = str(hostname or "").lower().strip(".")
    normalized_path = f"/{path.lstrip('/').lower()}"
    path_segments = [segment for segment in normalized_path.split("/") if segment]

    if hostname == "hooks.slack.com" and normalized_path.startswith("/services/"):
        return True
    if hostname in {"discord.com", "discordapp.com"} and "/api/webhooks/" in normalized_path:
        return True
    if hostname == "open.feishu.cn" and "/open-apis/bot/" in normalized_path and "/hook/" in normalized_path:
        return True
    if hostname == "oapi.dingtalk.com" and normalized_path.startswith("/robot/send"):
        return True
    if hostname == "qyapi.weixin.qq.com" and normalized_path.startswith("/cgi-bin/webhook/send"):
        return True
    if hostname in {"sctapi.ftqq.com", "sc.ftqq.com"}:
        return True
    if hostname.startswith("hooks."):
        return True
    if {"hook", "webhook", "webhooks"} & set(path_segments):
        return True
    return False


def _has_sensitive_url_params(params_text: str) -> bool:
    if not params_text:
        return False
    try:
        params = parse_qsl(
            params_text,
            keep_blank_values=True,
            max_num_fields=100,
        )
    except (TypeError, UnicodeError, ValueError):
        return True
    for key, value in params:
        key_text = unquote(unquote(str(key or ""))).strip().lower()
        if _is_sensitive_mapping_key(key_text):
            return True
        if _TOKEN_LIKE_PATTERN.search(str(value or "")):
            return True
    return False


def _is_sensitive_mapping_key(key: Any) -> bool:
    if key is None:
        return False
    key_text = _safe_string(key)
    if key_text == _SAFE_RENDER_FAILURE:
        return True
    return _is_sensitive_mapping_key_text(key_text)


def _is_sensitive_mapping_key_text(key_text: str) -> bool:
    key_text = key_text.strip()
    if not key_text:
        return False
    parts = _mapping_key_parts(key_text)
    if parts and parts[-1] == "proxy":
        return True
    if {"header", "headers"} & set(parts):
        if parts[-1] in {"count", "length", "size"}:
            return False
        return True
    for index, part in enumerate(parts):
        if part != "prompt":
            continue
        if index + 1 < len(parts) and parts[index + 1] == "tokens":
            continue
        return True
    if _has_sensitive_phrase("_".join(parts)):
        return True
    return bool(set(parts) & _SENSITIVE_KEY_PARTS)


def _redact_mapping_key(
    key: Any,
    *,
    exact_values: _NormalizedRedactionValues,
    redact_opaque_tokens: bool,
    preserve_http_credential_hosts: bool,
) -> tuple[Any, bool]:
    """Return a JSON-safe key and classify it from the same bounded render."""

    if key is None or type(key) in {bool, int, float}:
        return key, False
    if type(key) is bytes:
        key_text = key.decode("utf-8", errors="replace")
    elif type(key) is str:
        key_text = key
    else:
        key_text = _safe_string(key)
    if key_text == _SAFE_RENDER_FAILURE:
        return _SAFE_RENDER_FAILURE, True
    return (
        redact_sensitive_text(
            key_text,
            redaction_values=exact_values,
            redact_opaque_tokens=redact_opaque_tokens,
            preserve_http_credential_hosts=preserve_http_credential_hosts,
        ),
        _is_sensitive_mapping_key_text(key_text),
    )


def _has_sensitive_phrase(normalized_key: str) -> bool:
    padded_key = f"_{normalized_key}_"
    if any(f"_{phrase}_" in padded_key for phrase in _SENSITIVE_KEY_PHRASES):
        return True
    compact_key = normalized_key.replace("_", "")
    if any(phrase in compact_key for phrase in _SENSITIVE_COMPACT_KEY_PHRASES):
        return True
    return bool(_SENSITIVE_COMPACT_KEY_PATTERN.search(compact_key))


def _mapping_key_parts(key_text: str) -> list[str]:
    split_camel = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key_text)
    return [
        part.lower()
        for part in re.split(r"[^A-Za-z0-9]+", split_camel)
        if part
    ]
