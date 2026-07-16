#!/usr/bin/env python3
"""Gate Playwright artifacts on text scanning and a no-media policy."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import BinaryIO, Iterable, Pattern, Sequence
from zipfile import BadZipFile, ZipFile, ZipInfo, is_zipfile


CANARY_ENV_NAME = "DSA_PLAYWRIGHT_ARTIFACT_CANARY"
ARTIFACT_ROOT_LABEL = "[artifact-root]"
READ_CHUNK_SIZE = 1024 * 1024
TEXT_SAMPLE_SIZE = 8192
RAW_ZIP_SCAN_OVERLAP = 64 * 1024
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


def _compile(pattern: bytes, flags: int = 0) -> Pattern[bytes]:
    """Compile one byte-pattern rule."""
    return re.compile(pattern, flags)


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


def _matching_rule_names(data: bytes) -> set[str]:
    """Return credential-shape rule names matched by textual data."""
    matches: set[str] = set()
    for rule in SECRET_RULES:
        for pattern in rule.patterns:
            for match in pattern.finditer(data):
                value = match.group("value")
                if rule.allow_masked_value and _masked_header_value(value, rule.name):
                    continue
                matches.add(rule.name)
                break
            if rule.name in matches:
                break
    return matches


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


def _scan_raw_zip_stream(
    stream: BinaryIO,
    prefix: bytes,
    canary: bytes,
) -> tuple[bool, set[str]]:
    """Scan raw ZIP bytes for secrets hidden outside exposed ZIP metadata."""
    contains_canary = canary in prefix
    rule_names = _matching_rule_names(prefix)
    overlap = max(RAW_ZIP_SCAN_OVERLAP, len(canary) - 1)
    tail = prefix[-overlap:]
    while True:
        chunk = stream.read(READ_CHUNK_SIZE)
        if not chunk:
            return contains_canary, rule_names
        combined = tail + chunk
        contains_canary = contains_canary or canary in combined
        rule_names.update(_matching_rule_names(combined))
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
) -> list[Finding]:
    """Scan an in-memory artifact or ZIP entry for configured rules."""
    findings = []
    if canary in data:
        findings.append(Finding(artifact=artifact, zip_entry=entry, rule="playwright_canary"))
    if textual:
        findings.extend(
            Finding(artifact=artifact, zip_entry=entry, rule=rule_name)
            for rule_name in sorted(_matching_rule_names(data))
        )
    return findings


def _scan_name(
    name: str,
    *,
    artifact: str,
    canary: bytes,
    entry: str | None = None,
) -> list[Finding]:
    """Scan an artifact or ZIP entry name as untrusted text metadata."""
    return _scan_blob(
        name.encode("utf-8", errors="replace"),
        artifact=artifact,
        canary=canary,
        entry=entry,
        textual=True,
    )


def _scan_regular_file(path: Path, artifact: str, canary: bytes) -> list[Finding]:
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
                )
            if _stream_contains(stream, sample, canary):
                return [Finding(artifact=artifact, rule="playwright_canary")]
    except OSError:
        return [Finding(artifact=artifact, rule="artifact_read_error")]
    return []


def _scan_zip_file(path: Path, artifact: str, canary: bytes) -> list[Finding]:
    """Scan ZIP metadata and every readable non-directory entry."""
    findings: list[Finding] = []
    try:
        with path.open("rb") as stream:
            prefix = stream.read(TEXT_SAMPLE_SIZE)
            raw_canary, raw_rule_names = _scan_raw_zip_stream(stream, prefix, canary)
    except OSError:
        return [Finding(artifact=artifact, rule="zip_read_error")]

    try:
        with ZipFile(path) as archive:
            findings.extend(
                _scan_blob(
                    archive.comment,
                    artifact=artifact,
                    canary=canary,
                    textual=True,
                )
            )
            for info in sorted(archive.infolist(), key=lambda item: item.filename):
                findings.extend(
                    _scan_name(
                        info.filename,
                        artifact=artifact,
                        entry=info.filename,
                        canary=canary,
                    )
                )
                if info.orig_filename != info.filename:
                    findings.extend(
                        _scan_name(
                            info.orig_filename,
                            artifact=artifact,
                            entry=info.filename,
                            canary=canary,
                        )
                    )
                findings.extend(
                    _scan_blob(
                        info.comment,
                        artifact=artifact,
                        entry=info.filename,
                        canary=canary,
                        textual=True,
                    )
                )
                findings.extend(
                    _scan_blob(
                        info.extra,
                        artifact=artifact,
                        entry=info.filename,
                        canary=canary,
                        textual=True,
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
                    )
                )
    except (BadZipFile, OSError):
        return [Finding(artifact=artifact, rule="zip_read_error")]

    existing_rules = {finding.rule for finding in findings}
    if raw_canary and "playwright_canary" not in existing_rules:
        findings.append(Finding(artifact=artifact, rule="playwright_canary"))
    findings.extend(
        Finding(artifact=artifact, rule=rule_name)
        for rule_name in sorted(raw_rule_names - existing_rules)
    )
    return findings


def scan_artifacts(root: Path, canary: bytes) -> tuple[list[Finding], int]:
    """Scan every regular file below ``root`` and return redacted findings."""
    if root.is_symlink():
        return [Finding(artifact=ARTIFACT_ROOT_LABEL, rule="artifact_symlink_unsupported")], 0
    if not root.is_dir():
        return [Finding(artifact=ARTIFACT_ROOT_LABEL, rule="artifact_root_missing")], 0

    findings: list[Finding] = []
    scanned_files = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            findings.append(
                Finding(
                    artifact=path.relative_to(root).as_posix(),
                    rule="artifact_symlink_unsupported",
                )
            )
            continue
        if not path.is_file():
            continue

        scanned_files += 1
        artifact = path.relative_to(root).as_posix()
        findings.extend(_scan_name(artifact, artifact=artifact, canary=canary))
        if path.suffix.lower() == ".zip" or is_zipfile(path):
            findings.extend(_scan_zip_file(path, artifact, canary))
        else:
            findings.extend(_scan_regular_file(path, artifact, canary))

    if scanned_files == 0:
        findings.append(Finding(artifact=ARTIFACT_ROOT_LABEL, rule="artifact_root_empty"))
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
