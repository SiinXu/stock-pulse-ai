#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Gate Playwright artifacts on text scanning and a no-media policy."""

from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field as dataclass_field
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import BinaryIO, Iterable, Pattern, Sequence
from urllib.parse import unquote_to_bytes
from zipfile import BadZipFile, ZipFile, ZipInfo, is_zipfile


CANARY_ENV_NAME = "DSA_PLAYWRIGHT_ARTIFACT_CANARY"
ARTIFACT_ROOT_LABEL = "[artifact-root]"
READ_CHUNK_SIZE = 1024 * 1024
TEXT_SAMPLE_SIZE = 8192
# Preserve a maximum-length ZIP local name + extra field across raw reads.
RAW_ZIP_SCAN_OVERLAP = 256 * 1024
ZIP_LOCAL_FILE_HEADER_SIGNATURE = b"PK\x03\x04"
ZIP_LOCAL_FILE_HEADER_SIZE = 30
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
WEBM_EBML_SIGNATURE = b"\x1a\x45\xdf\xa3"
UNINSPECTABLE_MEDIA_SUFFIXES = frozenset({".jpeg", ".jpg", ".png", ".webm"})
TEXT_SUFFIXES = frozenset({
    ".css",
    ".env",
    ".har",
    ".htm",
    ".html",
    ".js",
    ".json",
    ".jsonl",
    ".log",
    ".map",
    ".md",
    ".mjs",
    ".network",
    ".ndjson",
    ".text",
    ".trace",
    ".ts",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
})
JSON_LINES_SUFFIXES = frozenset({".jsonl", ".ndjson"})
MASKED_VALUES = frozenset({
    b"***",
    b"******",
    b"[masked]",
    b"[redacted]",
    b"<masked>",
    b"<redacted>",
    b"masked",
    b"none",
    b"null",
    b"redacted",
    b"undefined",
})


@dataclass(frozen=True)
class Finding:
    """One rule match without the matched credential value."""

    artifact: str
    rule: str
    zip_entry: str | None = None


@dataclass(frozen=True)
class SecretRule:
    """A named set of byte patterns with a common masking policy."""

    name: str
    patterns: tuple[Pattern[bytes], ...]
    allow_masked_value: bool = True


@dataclass
class _ScanRedactionState:
    """Credential candidates and coarse-redaction state for one root scan."""

    matched_values: set[bytes] = dataclass_field(repr=False)
    redact_all_locations: bool = False


def _compile(pattern: bytes, flags: int = 0) -> Pattern[bytes]:
    """Compile one byte-pattern rule."""
    return re.compile(pattern, flags)


_PAIR_GAP_LIMIT = 65535
_API_KEY_CONFIG_NAME = (
    rb"(?:[a-z0-9]+[_\-.])*api[_-]?keys?(?:[_\-.][a-z0-9]+)*"
)
_AUTH_CONFIG_NAME = (
    rb"(?:[a-z0-9]+[_\-.])*(?:authorization|auth)(?:[_\-.][a-z0-9]+)*"
)
_COOKIE_CONFIG_NAME = (
    rb"(?:[a-z0-9]+[_\-.])*cookies?(?:[_\-.][a-z0-9]+)*"
)
_GENERIC_SECRET_CONFIG_NAME = (
    rb"(?:[a-z0-9]+[_\-.])*(?:token|password|passwd|secret)"
    rb"(?:[_\-.][a-z0-9]+)*"
)


def _paired_json_name_pattern(sensitive_name_pattern: bytes) -> Pattern[bytes]:
    """Match a sensitive JSON-shaped key/name field for text fallback scans."""
    return _compile(
        rb"[\"'](?:key|name)[\"']\s*:\s*[\"']"
        + rb"(?P<name>"
        + sensitive_name_pattern
        + rb")"
        + rb"[\"']",
        re.IGNORECASE,
    )


_PAIRED_JSON_VALUE_PATTERN = _compile(
    rb"[\"']value[\"']\s*:\s*[\"'](?P<value>[^\"']+)[\"']",
    re.IGNORECASE,
)
_PAIRED_JSON_NESTED_VALUE_PATTERN = _compile(
    rb"[\"']value[\"']\s*:\s*(?:\{|\[)",
    re.IGNORECASE,
)
_PAIR_DELIMITER_PATTERN = _compile(rb"[{}]")
_PAIRED_JSON_NAME_PATTERNS = (
    ("authorization_header", _paired_json_name_pattern(_AUTH_CONFIG_NAME)),
    ("cookie_header", _paired_json_name_pattern(_COOKIE_CONFIG_NAME)),
    ("api_key_assignment", _paired_json_name_pattern(_API_KEY_CONFIG_NAME)),
    ("sensitive_key_value", _paired_json_name_pattern(_GENERIC_SECRET_CONFIG_NAME)),
)


SECRET_RULES = (
    SecretRule(
        name="authorization_header",
        patterns=(
            _compile(
                rb"[\"'](?:proxy-)?authorization[\"']\s*:\s*"
                rb"[\"'](?P<value>[^\"']+)[\"']",
                re.IGNORECASE,
            ),
            _compile(
                rb"[\"']name[\"']\s*:\s*[\"'](?:proxy-)?authorization[\"']"
                rb"[^{}]{0,256}?[\"']value[\"']\s*:\s*[\"']"
                rb"(?P<value>[^\"']+)[\"']",
                re.IGNORECASE,
            ),
            _compile(
                rb"^[ \t]*(?:proxy-)?authorization[ \t]*[:=][ \t]*"
                rb"(?P<value>[^\r\n]+)",
                re.IGNORECASE | re.MULTILINE,
            ),
        ),
    ),
    SecretRule(
        name="cookie_header",
        patterns=(
            _compile(
                rb"[\"'](?:set-)?cookie[\"']\s*:\s*[\"']"
                rb"(?P<value>[^\"']+)[\"']",
                re.IGNORECASE,
            ),
            _compile(
                rb"[\"']name[\"']\s*:\s*[\"'](?:set-)?cookie[\"']"
                rb"[^{}]{0,256}?[\"']value[\"']\s*:\s*[\"']"
                rb"(?P<value>[^\"']+)[\"']",
                re.IGNORECASE,
            ),
            _compile(
                rb"^[ \t]*(?:set-)?cookie[ \t]*[:=][ \t]*"
                rb"(?P<value>[^\r\n]+)",
                re.IGNORECASE | re.MULTILINE,
            ),
        ),
    ),
    SecretRule(
        name="api_key_assignment",
        patterns=(
            _compile(
                rb"[\"'][a-z0-9_-]*api[_-]?keys?[\"']\s*:\s*[\"']"
                rb"(?P<value>[^\"']+)[\"']",
                re.IGNORECASE,
            ),
            _compile(
                rb"^[ \t]*(?:export[ \t]+)?[A-Z][A-Z0-9_]*API_KEYS?"
                rb"[ \t]*=[ \t]*(?P<value>[^\r\n#]+)",
                re.MULTILINE,
            ),
            _compile(
                rb"^[ \t]*(?:x[_-]?)?api[_-]?keys?[ \t]*[:=][ \t]*"
                rb"(?P<value>[^\r\n]+)",
                re.IGNORECASE | re.MULTILINE,
            ),
        ),
    ),
    SecretRule(
        name="sensitive_key_value",
        patterns=(),
    ),
    SecretRule(
        name="url_userinfo",
        patterns=(
            _compile(
                rb"\bhttps?://(?P<value>[^/\s@?#]+)@",
                re.IGNORECASE,
            ),
        ),
        allow_masked_value=False,
    ),
    SecretRule(
        name="sensitive_query_parameter",
        patterns=(
            _compile(
                rb"[?&](?:api[_-]?key|access[_-]?token|auth(?:orization)?|password|"
                rb"secret|sig(?:nature)?|token)=(?P<value>[^&#\s\"']+)",
                re.IGNORECASE,
            ),
        ),
    ),
)


def _simple_masked(value: bytes) -> bool:
    """Return whether a captured value is an accepted mask token."""
    normalized = value.strip(b" \t\r\n\"'").lower()
    return normalized in MASKED_VALUES


def _masked_header_value(value: bytes, rule_name: str) -> bool:
    """Recognize masked auth schemes and cookie value lists."""
    normalized = value.strip(b" \t\r\n\"',}")
    lower = normalized.lower()
    for scheme in (b"basic ", b"bearer ", b"token "):
        if lower.startswith(scheme):
            return _simple_masked(normalized[len(scheme):])

    if rule_name == "cookie_header" and b"=" in normalized:
        cookie_values = []
        for field in normalized.split(b";"):
            if b"=" not in field:
                return False
            cookie_values.append(field.split(b"=", 1)[1])
        return bool(cookie_values) and all(_simple_masked(item) for item in cookie_values)

    return _simple_masked(normalized)


def _pair_gap_is_allowed(
    left_end: int,
    right_start: int,
    delimiter_positions: Sequence[int],
) -> bool:
    """Return whether two fallback fields share one bounded flat-text region."""
    gap = right_start - left_end
    if gap < 0 or gap > _PAIR_GAP_LIMIT:
        return False
    delimiter_index = bisect_left(delimiter_positions, left_end)
    return (
        delimiter_index >= len(delimiter_positions)
        or delimiter_positions[delimiter_index] >= right_start
    )


def _matching_paired_rule_values(data: bytes) -> dict[str, set[bytes]]:
    """Pair sensitive key/name markers with scalar values in linear scans."""
    value_matches = list(_PAIRED_JSON_VALUE_PATTERN.finditer(data))
    if not value_matches:
        return {}
    delimiter_positions = [
        match.start()
        for match in _PAIR_DELIMITER_PATTERN.finditer(data)
    ]
    matches: dict[str, set[bytes]] = {}
    for rule_name, name_pattern in _PAIRED_JSON_NAME_PATTERNS:
        unmasked_values = [
            match
            for match in value_matches
            if not _masked_header_value(match.group("value"), rule_name)
        ]
        if not unmasked_values:
            continue
        value_starts = [match.start() for match in unmasked_values]
        value_ends = [match.end() for match in unmasked_values]
        for name_match in name_pattern.finditer(data):
            classified_rule = _sensitive_json_rule_name(
                name_match.group("name").decode("utf-8", errors="replace")
            )
            if classified_rule != rule_name:
                continue
            following = bisect_left(value_starts, name_match.end())
            if following < len(unmasked_values) and _pair_gap_is_allowed(
                name_match.end(),
                value_starts[following],
                delimiter_positions,
            ):
                matches.setdefault(rule_name, set()).add(
                    unmasked_values[following].group("value")
                )
                continue

            preceding = bisect_right(value_ends, name_match.start()) - 1
            if preceding >= 0 and _pair_gap_is_allowed(
                value_ends[preceding],
                name_match.start(),
                delimiter_positions,
            ):
                matches.setdefault(rule_name, set()).add(
                    unmasked_values[preceding].group("value")
                )
    return matches


def _matching_paired_rule_names(data: bytes) -> set[str]:
    return set(_matching_paired_rule_values(data))


def _matching_rule_values(data: bytes) -> dict[str, set[bytes]]:
    """Return credential-shape rules and matched values from textual data."""
    matches = _matching_paired_rule_values(data)
    for rule in SECRET_RULES:
        for pattern in rule.patterns:
            for match in pattern.finditer(data):
                value = match.group("value")
                if rule.allow_masked_value and _masked_header_value(value, rule.name):
                    continue
                matches.setdefault(rule.name, set()).add(value)
    return matches


def _matching_rule_names(data: bytes) -> set[str]:
    """Return credential-shape rule names matched by textual data."""
    return set(_matching_rule_values(data))


def _sensitive_json_rule_name(name: str) -> str | None:
    """Map a structured configuration name to its redacted finding rule."""
    camel_separated = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    parts = tuple(re.findall(r"[a-z0-9]+", camel_separated.lower()))
    if not parts:
        return None
    if any(part in {"apikey", "apikeys"} for part in parts) or any(
        left == "api" and right in {"key", "keys"}
        for left, right in zip(parts, parts[1:])
    ):
        return "api_key_assignment"
    if any(part in {"authorization", "auth"} for part in parts):
        return "authorization_header"
    if any(part in {"cookie", "cookies"} for part in parts):
        return "cookie_header"
    if any(part in {"password", "passwd", "secret"} for part in parts):
        return "sensitive_key_value"
    if "token" in parts:
        token_metadata_suffixes = {
            "budget",
            "count",
            "expires",
            "expiry",
            "length",
            "limit",
            "ttl",
            "type",
            "usage",
        }
        if any(
            left == "token" and right in token_metadata_suffixes
            for left, right in zip(parts, parts[1:])
        ):
            return None
        return "sensitive_key_value"
    return None


_STRUCTURED_VALUE_METADATA_FIELDS = {
    "cookie_header": frozenset({
        "domain",
        "expires",
        "httponly",
        "name",
        "partitionkey",
        "path",
        "priority",
        "sameparty",
        "samesite",
        "secure",
        "size",
        "sourceport",
        "sourcescheme",
    }),
    "sensitive_key_value": frozenset({
        "scope",
        "scopes",
        "token_type",
    }),
}
_STRUCTURED_NUMERIC_METADATA_FIELDS = frozenset({"expires_at", "expires_in"})


def _iter_unmasked_json_secret_values(
    value: object,
    rule_name: str,
) -> Iterable[bytes]:
    """Yield unmasked scalar leaves from one sensitive structured value."""
    pending = [value]
    while pending:
        current = pending.pop()
        if current is None or isinstance(current, bool):
            continue
        if isinstance(current, str):
            encoded = current.encode("utf-8", errors="replace")
            if (
                rule_name == "authorization_header"
                and encoded.strip().lower() in {b"basic", b"bearer", b"token"}
            ):
                continue
            if current and not _masked_header_value(encoded, rule_name):
                yield encoded
            continue
        if isinstance(current, dict):
            ignored_fields = _STRUCTURED_VALUE_METADATA_FIELDS.get(
                rule_name,
                frozenset(),
            )
            for field_name, field_value in current.items():
                normalized_name = (
                    field_name.casefold()
                    if isinstance(field_name, str)
                    else ""
                )
                if normalized_name in ignored_fields:
                    continue
                if (
                    normalized_name in _STRUCTURED_NUMERIC_METADATA_FIELDS
                    and isinstance(field_value, (int, float))
                    and not isinstance(field_value, bool)
                ):
                    continue
                pending.append(field_value)
            continue
        if isinstance(current, list):
            pending.extend(current)
            continue
        if isinstance(current, (int, float)):
            yield str(current).encode("ascii", errors="replace")


def _iter_json_documents(data: bytes, content_name: str) -> Iterable[object]:
    """Yield valid JSON documents while leaving malformed text to regex fallback."""
    if PurePosixPath(content_name).suffix.lower() in JSON_LINES_SUFFIXES:
        try:
            text = data.decode(json.detect_encoding(data))
        except (LookupError, UnicodeDecodeError):
            return
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except (ValueError, RecursionError):
                continue
        return

    try:
        # json.loads performs the standard UTF-8/16/32 BOM/width detection for bytes.
        yield json.loads(data)
    except (ValueError, RecursionError):
        return


def _iter_malformed_json_fragments(
    data: bytes,
    content_name: str,
) -> Iterable[bytes]:
    """Yield decoded JSON fragments that the structured parser cannot trust."""
    encoding = json.detect_encoding(data)
    undecodable = False
    try:
        text = data.decode(encoding)
    except LookupError:
        return
    except UnicodeDecodeError:
        text = data.decode(encoding, errors="replace")
        undecodable = True

    if PurePosixPath(content_name).suffix.lower() in JSON_LINES_SUFFIXES:
        candidates = (line for line in text.splitlines() if line.strip())
    else:
        candidates = (text,)

    for candidate in candidates:
        if undecodable:
            yield candidate.encode("utf-8", errors="replace")
            continue
        try:
            json.loads(candidate)
        except (ValueError, RecursionError):
            yield candidate.encode("utf-8", errors="replace")


def _matching_malformed_nested_rule_names(
    data: bytes,
    content_name: str,
) -> set[str]:
    """Fail closed on unparseable sensitive assignments with nested values."""
    matches: set[str] = set()
    for fragment in _iter_malformed_json_fragments(data, content_name):
        nested_values = list(
            _PAIRED_JSON_NESTED_VALUE_PATTERN.finditer(fragment)
        )
        if not nested_values:
            continue
        value_starts = [match.start() for match in nested_values]
        value_ends = [match.end() for match in nested_values]
        for rule_name, name_pattern in _PAIRED_JSON_NAME_PATTERNS:
            for name_match in name_pattern.finditer(fragment):
                classified_rule = _sensitive_json_rule_name(
                    name_match.group("name").decode(
                        "utf-8",
                        errors="replace",
                    )
                )
                if classified_rule != rule_name:
                    continue

                following = bisect_left(value_starts, name_match.end())
                if (
                    following < len(nested_values)
                    and value_starts[following] - name_match.end()
                    <= _PAIR_GAP_LIMIT
                ):
                    matches.add(rule_name)
                    break

                preceding = bisect_right(value_ends, name_match.start()) - 1
                if (
                    preceding >= 0
                    and name_match.start() - value_ends[preceding]
                    <= _PAIR_GAP_LIMIT
                ):
                    matches.add(rule_name)
                    break
    return matches


def _structured_json_rule_values(
    data: bytes,
    content_name: str,
) -> dict[str, set[bytes]]:
    """Find sensitive JSON assignments and their unmasked scalar values."""
    matches: dict[str, set[bytes]] = {}
    for document in _iter_json_documents(data, content_name):
        pending = [document]
        while pending:
            current = pending.pop()
            if isinstance(current, list):
                pending.extend(current)
                continue
            if not isinstance(current, dict):
                continue

            fields_by_name = {
                field_name.casefold(): field_value
                for field_name, field_value in current.items()
                if isinstance(field_name, str)
            }
            if "value" in fields_by_name:
                for marker_name in ("key", "name"):
                    sensitive_name = fields_by_name.get(marker_name)
                    if not isinstance(sensitive_name, str):
                        continue
                    rule_name = _sensitive_json_rule_name(sensitive_name)
                    if rule_name:
                        values = set(_iter_unmasked_json_secret_values(
                            fields_by_name["value"],
                            rule_name,
                        ))
                        if values:
                            matches.setdefault(rule_name, set()).update(values)

            for field_name, field_value in current.items():
                if isinstance(field_name, str):
                    rule_name = _sensitive_json_rule_name(field_name)
                    if rule_name:
                        values = set(_iter_unmasked_json_secret_values(
                            field_value,
                            rule_name,
                        ))
                        if values:
                            matches.setdefault(rule_name, set()).update(values)
                pending.append(field_value)
    return matches


def _structured_json_rule_names(data: bytes, content_name: str) -> set[str]:
    """Return sensitive rule names from structured JSON documents."""
    return set(_structured_json_rule_values(data, content_name))


def _merge_rule_values(
    target: dict[str, set[bytes]],
    source: dict[str, set[bytes]],
) -> None:
    for rule_name, values in source.items():
        target.setdefault(rule_name, set()).update(values)


def _redact_location_with_matches(
    value: str,
    matched_values: Iterable[bytes],
) -> str:
    """Hide a location when it contains any credential matched in its payload."""
    encoded = value.encode("utf-8", errors="replace")
    redaction_values: set[bytes] = set()
    for secret in matched_values:
        if not secret:
            continue
        redaction_values.add(secret)
        normalized = secret.strip(b" \t\r\n\"',}")
        if normalized:
            redaction_values.add(normalized)
            redaction_values.add(unquote_to_bytes(normalized))
        lower = normalized.lower()
        for scheme in (b"basic ", b"bearer ", b"token "):
            if lower.startswith(scheme):
                credential = normalized[len(scheme):].strip()
                if credential:
                    redaction_values.add(credential)
                break
        if b":" in normalized:
            username, password = normalized.split(b":", 1)
            username = username.strip()
            password = password.strip()
            if username:
                redaction_values.add(username)
                redaction_values.add(unquote_to_bytes(username))
            if password:
                redaction_values.add(password)
                redaction_values.add(unquote_to_bytes(password))
        for field in normalized.split(b";"):
            if b"=" not in field:
                continue
            credential = field.split(b"=", 1)[1].strip()
            if credential:
                redaction_values.add(credential)
    if any(secret in encoded for secret in redaction_values):
        return "[redacted]"
    return value


def _redact_finding_locations(
    findings: Iterable[Finding],
    matched_values: Iterable[bytes],
    *,
    redact_all_locations: bool = False,
) -> list[Finding]:
    """Apply every artifact match to every returned finding location."""
    redaction_values = set(matched_values)
    return [
        Finding(
            artifact=(
                "[redacted]"
                if redact_all_locations
                else _redact_location_with_matches(
                    finding.artifact,
                    redaction_values,
                )
            ),
            rule=finding.rule,
            zip_entry=(
                (
                    "[redacted]"
                    if redact_all_locations
                    else _redact_location_with_matches(
                        finding.zip_entry,
                        redaction_values,
                    )
                )
                if finding.zip_entry is not None
                else None
            ),
        )
        for finding in findings
    ]


def _is_probably_text(name: str, sample: bytes) -> bool:
    """Classify an artifact using its suffix and a bounded content sample."""
    suffix = PurePosixPath(name).suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return True
    if not sample or b"\0" in sample:
        return False
    try:
        decoded = sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    controls = sum(
        1
        for character in decoded
        if not character.isprintable() and character not in "\n\r\t"
    )
    return controls <= max(1, len(decoded) // 100)


def _is_uninspectable_media(name: str, sample: bytes) -> bool:
    """Identify media that byte scanning cannot inspect for rendered text."""
    suffix = PurePosixPath(name).suffix.lower()
    return (
        suffix in UNINSPECTABLE_MEDIA_SUFFIXES
        or sample.startswith(PNG_SIGNATURE)
        or sample.startswith(JPEG_SIGNATURE)
        or sample.startswith(WEBM_EBML_SIGNATURE)
    )


def _zip_entry_is_symlink(info: ZipInfo) -> bool:
    """Return whether a ZIP entry declares a Unix symbolic-link mode."""
    return stat.S_ISLNK(info.external_attr >> 16)


def _stream_contains(stream: BinaryIO, prefix: bytes, needle: bytes) -> bool:
    """Search a binary stream while preserving matches across chunk bounds."""
    if needle in prefix:
        return True
    overlap = max(0, len(needle) - 1)
    tail = prefix[-overlap:] if overlap else b""
    while True:
        chunk = stream.read(READ_CHUNK_SIZE)
        if not chunk:
            return False
        combined = tail + chunk
        if needle in combined:
            return True
        tail = combined[-overlap:] if overlap else b""


def _iter_raw_zip_local_metadata(data: bytes) -> Iterable[tuple[bytes, bytes]]:
    """Yield complete local-header filename and extra metadata from raw ZIP bytes."""
    search_offset = 0
    while True:
        header_offset = data.find(ZIP_LOCAL_FILE_HEADER_SIGNATURE, search_offset)
        if header_offset < 0:
            return
        search_offset = header_offset + len(ZIP_LOCAL_FILE_HEADER_SIGNATURE)
        if len(data) - header_offset < ZIP_LOCAL_FILE_HEADER_SIZE:
            continue
        filename_size = int.from_bytes(
            data[header_offset + 26:header_offset + 28],
            "little",
        )
        extra_size = int.from_bytes(
            data[header_offset + 28:header_offset + 30],
            "little",
        )
        filename_start = header_offset + ZIP_LOCAL_FILE_HEADER_SIZE
        filename_end = filename_start + filename_size
        extra_end = filename_end + extra_size
        if extra_end <= len(data):
            yield data[filename_start:filename_end], data[filename_end:extra_end]


def _raw_zip_metadata_matches(
    data: bytes,
) -> tuple[dict[str, set[bytes]], set[str]]:
    """Scan scalar and malformed nested secrets in raw local ZIP metadata."""
    matches: dict[str, set[bytes]] = {}
    malformed_nested_rules: set[str] = set()
    for filename, extra in _iter_raw_zip_local_metadata(data):
        _merge_rule_values(matches, _matching_rule_values(filename))
        _merge_rule_values(
            matches,
            _structured_json_rule_values(filename, "raw-filename.json"),
        )
        malformed_nested_rules.update(
            _matching_malformed_nested_rule_names(
                filename,
                "raw-filename.json",
            )
        )
        _merge_rule_values(matches, _matching_rule_values(extra))
        _merge_rule_values(
            matches,
            _structured_json_rule_values(extra, "raw-extra.json"),
        )
        try:
            for payload in _iter_zip_extra_payloads(extra):
                _merge_rule_values(matches, _matching_rule_values(payload))
                _merge_rule_values(
                    matches,
                    _structured_json_rule_values(
                        payload,
                        "raw-extra-payload.json",
                    ),
                )
                malformed_nested_rules.update(
                    _matching_malformed_nested_rule_names(
                        payload,
                        "raw-extra-payload.json",
                    )
                )
        except ValueError:
            continue
    return matches, malformed_nested_rules


def _scan_raw_zip_stream(
    stream: BinaryIO,
    prefix: bytes,
    canary: bytes,
) -> tuple[bool, dict[str, set[bytes]], set[str]]:
    """Scan raw ZIP bytes for secrets hidden outside exposed ZIP metadata."""
    contains_canary = canary in prefix
    rule_values = _matching_rule_values(prefix)
    metadata_values, malformed_nested_rules = _raw_zip_metadata_matches(prefix)
    _merge_rule_values(rule_values, metadata_values)
    overlap = max(RAW_ZIP_SCAN_OVERLAP, len(canary) - 1)
    tail = prefix[-overlap:]
    while True:
        chunk = stream.read(READ_CHUNK_SIZE)
        if not chunk:
            return contains_canary, rule_values, malformed_nested_rules
        combined = tail + chunk
        contains_canary = contains_canary or canary in combined
        _merge_rule_values(rule_values, _matching_rule_values(combined))
        metadata_values, metadata_malformed_rules = _raw_zip_metadata_matches(
            combined
        )
        _merge_rule_values(rule_values, metadata_values)
        malformed_nested_rules.update(metadata_malformed_rules)
        tail = combined[-overlap:]


def _iter_zip_extra_payloads(extra: bytes) -> Iterable[bytes]:
    """Yield payloads from well-formed ZIP extra fields."""
    offset = 0
    while offset < len(extra):
        if len(extra) - offset < 4:
            raise ValueError("truncated ZIP extra field header")
        payload_size = int.from_bytes(extra[offset + 2:offset + 4], "little")
        payload_start = offset + 4
        payload_end = payload_start + payload_size
        if payload_end > len(extra):
            raise ValueError("truncated ZIP extra field payload")
        yield extra[payload_start:payload_end]
        offset = payload_end


def _scan_blob(
    data: bytes,
    *,
    artifact: str,
    canary: bytes,
    entry: str | None = None,
    textual: bool,
    artifact_matches: set[bytes] | None = None,
    redaction_state: _ScanRedactionState | None = None,
) -> list[Finding]:
    """Scan an in-memory artifact or ZIP entry for configured rules."""
    findings = []
    contains_canary = canary in data
    rule_values: dict[str, set[bytes]] = {}
    malformed_nested_rules: set[str] = set()
    if textual:
        rule_values = _matching_rule_values(data)
        _merge_rule_values(
            rule_values,
            _structured_json_rule_values(data, entry or artifact),
        )
        malformed_nested_rules = _matching_malformed_nested_rule_names(
            data,
            entry or artifact,
        )
    matched_values = {
        value
        for values in rule_values.values()
        for value in values
    }
    if contains_canary:
        matched_values.add(canary)
    if artifact_matches is not None:
        artifact_matches.update(matched_values)
    if redaction_state is not None:
        redaction_state.matched_values.update(matched_values)
        if malformed_nested_rules:
            redaction_state.redact_all_locations = True
    redact_all_locations = bool(malformed_nested_rules) or bool(
        redaction_state and redaction_state.redact_all_locations
    )
    safe_artifact = (
        "[redacted]"
        if redact_all_locations
        else _redact_location_with_matches(artifact, matched_values)
    )
    safe_entry = (
        (
            "[redacted]"
            if redact_all_locations
            else _redact_location_with_matches(entry, matched_values)
        )
        if entry is not None
        else None
    )
    if contains_canary:
        findings.append(
            Finding(
                artifact=safe_artifact,
                zip_entry=safe_entry,
                rule="playwright_canary",
            )
        )
    if textual:
        findings.extend(
            Finding(
                artifact=safe_artifact,
                zip_entry=safe_entry,
                rule=rule_name,
            )
            for rule_name in sorted(
                set(rule_values) | malformed_nested_rules
            )
        )
    return findings


def _scan_name(
    name: str,
    *,
    artifact: str,
    canary: bytes,
    entry: str | None = None,
    artifact_matches: set[bytes] | None = None,
    redaction_state: _ScanRedactionState | None = None,
) -> list[Finding]:
    """Scan an artifact or ZIP entry name as untrusted text metadata."""
    return _scan_blob(
        name.encode("utf-8", errors="replace"),
        artifact=artifact,
        canary=canary,
        entry=entry,
        textual=True,
        artifact_matches=artifact_matches,
        redaction_state=redaction_state,
    )


def _scan_regular_file(
    path: Path,
    artifact: str,
    canary: bytes,
    artifact_matches: set[bytes],
    redaction_state: _ScanRedactionState,
) -> list[Finding]:
    """Scan one regular artifact without echoing matched values."""
    try:
        with path.open("rb") as stream:
            sample = stream.read(TEXT_SAMPLE_SIZE)
            if _is_uninspectable_media(path.name, sample):
                return [Finding(artifact=artifact, rule="uninspectable_media")]
            if _is_probably_text(path.name, sample):
                return _scan_blob(
                    sample + stream.read(),
                    artifact=artifact,
                    canary=canary,
                    textual=True,
                    artifact_matches=artifact_matches,
                    redaction_state=redaction_state,
                )
            if _stream_contains(stream, sample, canary):
                artifact_matches.add(canary)
                redaction_state.matched_values.add(canary)
                return [
                    Finding(
                        artifact=_redact_location_with_matches(
                            artifact,
                            {canary},
                        ),
                        rule="playwright_canary",
                    )
                ]
    except OSError:
        return [Finding(artifact=artifact, rule="artifact_read_error")]
    return []


def _scan_zip_file(
    path: Path,
    artifact: str,
    canary: bytes,
    artifact_matches: set[bytes],
    redaction_state: _ScanRedactionState,
) -> list[Finding]:
    """Scan ZIP metadata and every readable non-directory entry."""
    findings: list[Finding] = []
    try:
        with path.open("rb") as stream:
            prefix = stream.read(TEXT_SAMPLE_SIZE)
            (
                raw_canary,
                raw_rule_values,
                raw_malformed_nested_rules,
            ) = _scan_raw_zip_stream(stream, prefix, canary)
    except OSError:
        return [Finding(artifact=artifact, rule="zip_read_error")]

    raw_matched_values = {
        value
        for values in raw_rule_values.values()
        for value in values
    }
    if raw_canary:
        raw_matched_values.add(canary)
    artifact_matches.update(raw_matched_values)
    redaction_state.matched_values.update(raw_matched_values)
    if raw_malformed_nested_rules:
        redaction_state.redact_all_locations = True

    try:
        with ZipFile(path) as archive:
            findings.extend(
                _scan_blob(
                    archive.comment,
                    artifact=artifact,
                    canary=canary,
                    textual=True,
                    artifact_matches=artifact_matches,
                    redaction_state=redaction_state,
                )
            )
            for info in sorted(archive.infolist(), key=lambda item: item.filename):
                findings.extend(
                    _scan_name(
                        info.filename,
                        artifact=artifact,
                        entry=info.filename,
                        canary=canary,
                        artifact_matches=artifact_matches,
                        redaction_state=redaction_state,
                    )
                )
                if info.orig_filename != info.filename:
                    findings.extend(
                        _scan_name(
                            info.orig_filename,
                            artifact=artifact,
                            entry=info.filename,
                            canary=canary,
                            artifact_matches=artifact_matches,
                            redaction_state=redaction_state,
                        )
                    )
                findings.extend(
                    _scan_blob(
                        info.comment,
                        artifact=artifact,
                        entry=info.filename,
                        canary=canary,
                        textual=True,
                        artifact_matches=artifact_matches,
                        redaction_state=redaction_state,
                    )
                )
                findings.extend(
                    _scan_blob(
                        info.extra,
                        artifact=artifact,
                        entry=info.filename,
                        canary=canary,
                        textual=True,
                        artifact_matches=artifact_matches,
                        redaction_state=redaction_state,
                    )
                )
                try:
                    for payload in _iter_zip_extra_payloads(info.extra):
                        findings.extend(
                            _scan_blob(
                                payload,
                                artifact=artifact,
                                entry=info.filename,
                                canary=canary,
                                textual=True,
                                artifact_matches=artifact_matches,
                                redaction_state=redaction_state,
                            )
                        )
                except ValueError:
                    findings.append(
                        Finding(
                            artifact=artifact,
                            zip_entry=info.filename,
                            rule="zip_metadata_read_error",
                        )
                    )
                if info.is_dir():
                    continue
                if _zip_entry_is_symlink(info):
                    findings.append(
                        Finding(
                            artifact=artifact,
                            zip_entry=info.filename,
                            rule="zip_entry_symlink_unsupported",
                        )
                    )
                    continue
                try:
                    data = archive.read(info)
                except (BadZipFile, OSError, RuntimeError):
                    findings.append(
                        Finding(
                            artifact=artifact,
                            zip_entry=info.filename,
                            rule="zip_entry_read_error",
                        )
                    )
                    continue
                if _is_uninspectable_media(info.filename, data[:TEXT_SAMPLE_SIZE]):
                    findings.append(
                        Finding(
                            artifact=artifact,
                            zip_entry=info.filename,
                            rule="uninspectable_media",
                        )
                    )
                    continue
                findings.extend(
                    _scan_blob(
                        data,
                        artifact=artifact,
                        entry=info.filename,
                        canary=canary,
                        textual=_is_probably_text(info.filename, data[:TEXT_SAMPLE_SIZE]),
                        artifact_matches=artifact_matches,
                        redaction_state=redaction_state,
                    )
                )
    except (BadZipFile, OSError):
        return [Finding(artifact=artifact, rule="zip_read_error")]

    existing_rules = {finding.rule for finding in findings}
    safe_raw_artifact = (
        "[redacted]"
        if raw_malformed_nested_rules
        else _redact_location_with_matches(
            artifact,
            raw_matched_values,
        )
    )
    if raw_canary and "playwright_canary" not in existing_rules:
        findings.append(
            Finding(artifact=safe_raw_artifact, rule="playwright_canary")
        )
    findings.extend(
        Finding(artifact=safe_raw_artifact, rule=rule_name)
        for rule_name in sorted(
            (set(raw_rule_values) | raw_malformed_nested_rules) - existing_rules
        )
    )
    return findings


def scan_artifacts(root: Path, canary: bytes) -> tuple[list[Finding], int]:
    """Scan every regular file below ``root`` and return redacted findings."""
    if root.is_symlink():
        return [Finding(artifact=ARTIFACT_ROOT_LABEL, rule="artifact_symlink_unsupported")], 0
    if not root.is_dir():
        return [Finding(artifact=ARTIFACT_ROOT_LABEL, rule="artifact_root_missing")], 0

    findings: list[Finding] = []
    redaction_state = _ScanRedactionState(matched_values=set())
    scanned_files = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            artifact = path.relative_to(root).as_posix()
            artifact_matches: set[bytes] = set()
            artifact_findings = _scan_name(
                artifact,
                artifact=artifact,
                canary=canary,
                artifact_matches=artifact_matches,
                redaction_state=redaction_state,
            )
            artifact_findings.append(
                Finding(
                    artifact=artifact,
                    rule="artifact_symlink_unsupported",
                )
            )
            findings.extend(
                _redact_finding_locations(
                    artifact_findings,
                    artifact_matches,
                )
            )
            continue
        if not path.is_file():
            continue

        scanned_files += 1
        artifact = path.relative_to(root).as_posix()
        artifact_matches = set()
        artifact_findings = _scan_name(
            artifact,
            artifact=artifact,
            canary=canary,
            artifact_matches=artifact_matches,
            redaction_state=redaction_state,
        )
        if path.suffix.lower() == ".zip" or is_zipfile(path):
            artifact_findings.extend(
                _scan_zip_file(
                    path,
                    artifact,
                    canary,
                    artifact_matches,
                    redaction_state,
                )
            )
        else:
            artifact_findings.extend(
                _scan_regular_file(
                    path,
                    artifact,
                    canary,
                    artifact_matches,
                    redaction_state,
                )
            )
        findings.extend(
            _redact_finding_locations(
                artifact_findings,
                artifact_matches,
            )
        )

    if scanned_files == 0:
        findings.append(Finding(artifact=ARTIFACT_ROOT_LABEL, rule="artifact_root_empty"))
    findings = _redact_finding_locations(
        findings,
        redaction_state.matched_values,
        redact_all_locations=redaction_state.redact_all_locations,
    )
    return _deduplicate_findings(findings), scanned_files


def _deduplicate_findings(findings: Iterable[Finding]) -> list[Finding]:
    """Return stable unique findings for concise CI output."""
    return sorted(
        set(findings),
        key=lambda finding: (finding.artifact, finding.zip_entry or "", finding.rule),
    )


def _redact_diagnostic_value(value: str, canary: bytes | None) -> str:
    """Remove known credential values from untrusted diagnostic path text."""
    encoded = value.encode("utf-8", errors="replace")
    if (
        _structured_json_rule_names(encoded, value)
        or _matching_paired_rule_names(encoded)
    ):
        return "[redacted]"
    if canary:
        encoded = encoded.replace(canary, b"[redacted]")
    replacement = b"[redacted]"
    for rule in SECRET_RULES:
        for pattern in rule.patterns:
            cursor = 0
            while match := pattern.search(encoded, cursor):
                start, end = match.span("value")
                encoded = encoded[:start] + replacement + encoded[end:]
                cursor = start + len(replacement)
    return encoded.decode("utf-8", errors="replace")


def _format_finding(finding: Finding, canary: bytes | None) -> str:
    """Format finding metadata without including the matched credential."""
    fields = [
        f"artifact={json.dumps(_redact_diagnostic_value(finding.artifact, canary))}"
    ]
    if finding.zip_entry is not None:
        fields.append(
            f"zip_entry={json.dumps(_redact_diagnostic_value(finding.zip_entry, canary))}"
        )
    fields.append(f"rule={json.dumps(finding.rule)}")
    return " ".join(fields)


def _load_canary() -> bytes | None:
    """Load and validate the dedicated Playwright canary environment value."""
    raw_value = os.getenv(CANARY_ENV_NAME, "")
    if len(raw_value) < 24 or "\n" in raw_value or "\r" in raw_value:
        return None
    try:
        return raw_value.encode("utf-8")
    except UnicodeEncodeError:
        return None


def main(argv: Sequence[str] | None = None) -> int:
    """Run the artifact scanner CLI and return its process exit code."""
    parser = argparse.ArgumentParser(
        description=(
            "Scan Playwright text artifacts for credentials and reject "
            "uninspectable PNG/JPEG/WebM media."
        ),
    )
    parser.add_argument(
        "artifact_root",
        nargs="?",
        type=Path,
        default=Path("apps/dsa-web/test-results"),
    )
    args = parser.parse_args(argv)

    canary = _load_canary()
    if canary is None:
        finding = Finding(
            artifact=ARTIFACT_ROOT_LABEL,
            rule="playwright_canary_not_configured",
        )
        print(_format_finding(finding, None), file=sys.stderr)
        return 2

    try:
        findings, scanned_files = scan_artifacts(args.artifact_root, canary)
    except Exception:
        finding = Finding(
            artifact=ARTIFACT_ROOT_LABEL,
            rule="scanner_internal_error",
        )
        print(_format_finding(finding, canary), file=sys.stderr)
        return 2
    if findings:
        for finding in findings:
            print(_format_finding(finding, canary), file=sys.stderr)
        return 1

    print(f"Playwright artifact scan passed: {scanned_files} file(s) scanned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
