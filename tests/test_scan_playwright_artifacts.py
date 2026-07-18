# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Regression tests for the Playwright artifact secret gate."""

from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from PIL import Image, ImageChops, ImageDraw, ImageFont
import pytest
import yaml

from scripts import scan_playwright_artifacts as artifact_scanner


REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNER = REPO_ROOT / "scripts" / "scan_playwright_artifacts.py"
CANARY = "stockpulse-playwright-canary-7f91c2a6b43d"
FORBIDDEN_CREDENTIAL_E2E_MEDIA_PATTERNS = (
    re.compile(r"\.\s*screenshot\s*\("),
    re.compile(r"contentType\s*:\s*['\"]image/"),
    re.compile(r"\brecordVideo\b"),
    re.compile(r"\.\s*video\s*\("),
    re.compile(r"\bscreenshots\s*:\s*true\b"),
)


def _run_scanner(artifact_root: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DSA_PLAYWRIGHT_ARTIFACT_CANARY"] = CANARY
    return subprocess.run(
        [sys.executable, str(SCANNER), str(artifact_root)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _rendered_canary_png() -> bytes:
    """Render the canary into pixels without storing it as PNG text metadata."""
    image = Image.new("RGB", (420, 48), "white")
    draw = ImageDraw.Draw(image)
    draw.text((8, 16), CANARY, fill="black", font=ImageFont.load_default())
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _rendered_canary_jpeg() -> bytes:
    """Render the canary into pixels without storing it as JPEG metadata."""
    image = Image.new("RGB", (420, 48), "white")
    draw = ImageDraw.Draw(image)
    draw.text((8, 16), CANARY, fill="black", font=ImageFont.load_default())
    output = BytesIO()
    image.save(output, format="JPEG", quality=95)
    return output.getvalue()


def _zip_extra_field(payload: bytes) -> bytes:
    return struct.pack("<HH", 0xCAFE, len(payload)) + payload


@pytest.mark.parametrize(
    ("rule_name", "content", "secret"),
    [
        (
            "authorization_header",
            b'headers={"Authorization":"Bearer plain-auth-value"}',
            "plain-auth-value",
        ),
        (
            "cookie_header",
            b'headers={"Cookie":"session=plain-cookie-value"}',
            "plain-cookie-value",
        ),
        (
            "api_key_assignment",
            b"OPENAI_API_KEY=plain-api-key-value\n",
            "plain-api-key-value",
        ),
        (
            "api_key_assignment",
            b"api_key = spaced-plain-api-key-value\n",
            "spaced-plain-api-key-value",
        ),
        (
            "url_userinfo",
            b"request=https://artifact-user:plain-url-password@example.test/v1",
            "plain-url-password",
        ),
        (
            "url_userinfo",
            b"request=https://plain-url-user@example.test/v1",
            "plain-url-user",
        ),
        (
            "sensitive_query_parameter",
            b"request=https://example.test/v1?mode=fast&access_token=plain-query-value",
            "plain-query-value",
        ),
    ],
    ids=[
        "authorization-header",
        "cookie-header",
        "api-key-assignment",
        "spaced-api-key-assignment",
        "url-userinfo",
        "username-only-url-userinfo",
        "sensitive-query",
    ],
)
def test_plain_artifact_leaks_fail_without_echoing_secret(
    tmp_path: Path,
    rule_name: str,
    content: bytes,
    secret: str,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    (artifact_root / "failure.log").write_bytes(content)

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == f'artifact="failure.log" rule="{rule_name}"\n'
    assert secret not in result.stderr


def test_application_key_value_json_leak_fails_without_echoing_secret(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    secret = "real-secret-value-123456789"
    (artifact_root / "playwright-results.json").write_text(
        '{"key":"LLM_ALPHA_API_KEY","value":"' + secret + '"}\n',
        encoding="utf-8",
    )

    findings, scanned_files = artifact_scanner.scan_artifacts(
        artifact_root,
        CANARY.encode("ascii"),
    )
    result = _run_scanner(artifact_root)

    assert scanned_files == 1
    assert findings == [
        artifact_scanner.Finding(
            artifact="playwright-results.json",
            rule="api_key_assignment",
        )
    ]
    assert secret not in repr(findings)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        'artifact="playwright-results.json" rule="api_key_assignment"\n'
    )
    assert secret not in result.stderr


@pytest.mark.parametrize("encoding", ["utf-16", "utf-32"])
def test_structured_json_uses_standard_encoding_detection(
    tmp_path: Path,
    encoding: str,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    secret = f"{encoding}-encoded-secret-value-123456789"
    (artifact_root / "playwright-results.json").write_bytes(
        json.dumps({"key": "LLM_ALPHA_API_KEY", "value": secret}).encode(encoding)
    )

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        'artifact="playwright-results.json" rule="api_key_assignment"\n'
    )
    assert secret not in result.stderr


@pytest.mark.parametrize("suffix", [".jsonl", ".ndjson"])
@pytest.mark.parametrize("encoding", ["utf-16", "utf-32"])
def test_json_lines_uses_standard_encoding_detection(
    tmp_path: Path,
    suffix: str,
    encoding: str,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    secret = f"{encoding}-{suffix[1:]}-secret-value-123456789"
    payload = json.dumps({"key": "LLM_ALPHA_API_KEY", "value": secret}) + "\n"
    (artifact_root / f"events{suffix}").write_bytes(payload.encode(encoding))

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        f'artifact="events{suffix}" rule="api_key_assignment"\n'
    )
    assert secret not in result.stderr


@pytest.mark.parametrize(
    ("sensitive_name", "rule_name"),
    [
        ("LLM_ALPHA_API_KEYS", "api_key_assignment"),
        ("Authorization", "authorization_header"),
        ("ACCESS_TOKEN", "sensitive_key_value"),
        ("EMAIL_PASSWORD", "sensitive_key_value"),
        ("DINGTALK_SECRET", "sensitive_key_value"),
        ("Cookie", "cookie_header"),
    ],
)
def test_structured_key_and_name_fields_cover_sensitive_categories(
    tmp_path: Path,
    sensitive_name: str,
    rule_name: str,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    secret = f"structured-{sensitive_name.lower()}-value"
    (artifact_root / "playwright-results.json").write_text(
        json.dumps({"name": sensitive_name, "value": secret}),
        encoding="utf-8",
    )

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        f'artifact="playwright-results.json" rule="{rule_name}"\n'
    )
    assert secret not in result.stderr


def test_nested_key_value_json_leak_fails_without_echoing_secret(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    secret = "nested-real-secret-value-123456789"
    payload = {
        "suites": [
            {
                "settings": [
                    {
                        "value": {"primary": "******", "fallbacks": [secret]},
                        "key": "LLM_NESTED_API_KEYS",
                    }
                ]
            }
        ]
    }
    (artifact_root / "playwright-results.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        'artifact="playwright-results.json" rule="api_key_assignment"\n'
    )
    assert secret not in result.stderr


@pytest.mark.parametrize("suffix", [".jsonl", ".ndjson"])
def test_json_lines_key_value_leak_fails_without_echoing_secret(
    tmp_path: Path,
    suffix: str,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    secret = f"json-lines-secret-{suffix[1:]}-123456789"
    path = artifact_root / f"events{suffix}"
    path.write_text(
        json.dumps({"key": "LLM_MAX_TOKENS", "value": "2048"})
        + "\n"
        + json.dumps(
            {"key": "LLM_ALPHA_API_KEY", "value": {"primary": secret}}
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        f'artifact="events{suffix}" rule="api_key_assignment"\n'
    )
    assert secret not in result.stderr


@pytest.mark.parametrize("entry_name", ["report.json", "events.jsonl", "events.ndjson"])
def test_zip_json_entry_key_value_leak_fails_without_echoing_secret(
    tmp_path: Path,
    entry_name: str,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    secret = f"zip-json-secret-{entry_name}-123456789"
    payload = json.dumps(
        {"key": "LLM_ZIP_API_KEY", "value": {"primary": secret}}
    ) + "\n"
    with ZipFile(artifact_root / "trace.zip", "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(entry_name, payload)

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        f'artifact="trace.zip" zip_entry="{entry_name}" '
        'rule="api_key_assignment"\n'
    )
    assert secret not in result.stderr


def test_masked_structured_key_value_payloads_pass(tmp_path: Path) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    payload = [
        {"key": "LLM_ALPHA_API_KEY", "value": "******"},
        {"name": "ACCESS_TOKEN", "value": "[redacted]"},
        {"name": "EMAIL_PASSWORD", "value": "<masked>"},
        {"name": "DINGTALK_SECRET", "value": ["masked", None]},
        {"name": "Authorization", "value": "Bearer [masked]"},
        {"name": "Cookie", "value": "session=******"},
        {
            "cookies": [
                {
                    "name": "session",
                    "value": "******",
                    "domain": "example.test",
                    "path": "/",
                    "httpOnly": True,
                }
            ]
        },
        {
            "key": "Authorization",
            "value": {"scheme": "Bearer", "credentials": "[redacted]"},
        },
        {"token_type": "Bearer", "expires_in": 3600},
        {"key": "TOKEN_TYPE", "value": "Bearer"},
        {"name": "TOKEN_COUNT", "value": "4096"},
        {"key": "TOKEN_BUDGET", "value": "8192"},
        {"name": "TOKEN_USAGE", "value": "1024"},
        {
            "key": "ACCESS_TOKEN",
            "value": {"token": "[redacted]", "expires_at": 1893456000},
        },
        {
            "key": "ACCESS_TOKEN",
            "value": {
                "token": "[redacted]",
                "scope": "openid profile",
                "token_type": "Bearer",
            },
        },
    ]
    (artifact_root / "playwright-results.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    result = _run_scanner(artifact_root)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "Playwright artifact scan passed" in result.stdout


def test_invalid_json_still_uses_key_value_text_fallback(tmp_path: Path) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    secret = "malformed-json-secret-value-123456789"
    (artifact_root / "broken.json").write_text(
        '{"key":"LLM_ALPHA_API_KEY","value":"' + secret + '"',
        encoding="utf-8",
    )

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == 'artifact="broken.json" rule="api_key_assignment"\n'
    assert secret not in result.stderr


def test_pretty_truncated_json_still_uses_key_value_text_fallback(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    secret = "pretty-malformed-json-secret-value-123456789"
    (artifact_root / "broken.json").write_text(
        '{\n  "key": "LLM_ALPHA_API_KEY",\n  "value": "' + secret + '"\n',
        encoding="utf-8",
    )

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == 'artifact="broken.json" rule="api_key_assignment"\n'
    assert secret not in result.stderr


@pytest.mark.parametrize("suffix", [".json", ".jsonl", ".ndjson"])
def test_malformed_nested_key_value_json_fails_closed_with_coarse_locations(
    tmp_path: Path,
    suffix: str,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    secret = f"malformed-nested-{suffix[1:]}-secret-123456789"
    malformed = (
        '{"key":"LLM_ALPHA_API_KEY","value":{"primary":"'
        + secret
        + '"'
    )
    content = malformed
    if suffix in {".jsonl", ".ndjson"}:
        content = json.dumps({"safe": True}) + "\n" + malformed + "\n"
    (artifact_root / f"events{suffix}").write_text(content, encoding="utf-8")

    findings, scanned_files = artifact_scanner.scan_artifacts(
        artifact_root,
        CANARY.encode("ascii"),
    )
    result = _run_scanner(artifact_root)

    assert scanned_files == 1
    assert findings == [
        artifact_scanner.Finding(
            artifact="[redacted]",
            rule="api_key_assignment",
        )
    ]
    assert secret not in repr(findings)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        'artifact="[redacted]" rule="api_key_assignment"\n'
    )
    assert secret not in result.stderr


def test_malformed_nested_key_value_zip_entry_fails_closed(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    secret = "malformed-nested-zip-secret-123456789"
    payload = (
        '{"key":"LLM_ALPHA_API_KEY","value":{"primary":"'
        + secret
        + '"'
    )
    with ZipFile(artifact_root / "trace.zip", "w") as archive:
        archive.writestr("broken.json", payload)

    findings, scanned_files = artifact_scanner.scan_artifacts(
        artifact_root,
        CANARY.encode("ascii"),
    )
    result = _run_scanner(artifact_root)

    assert scanned_files == 1
    assert findings == [
        artifact_scanner.Finding(
            artifact="[redacted]",
            zip_entry="[redacted]",
            rule="api_key_assignment",
        )
    ]
    assert secret not in repr(findings)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        'artifact="[redacted]" zip_entry="[redacted]" '
        'rule="api_key_assignment"\n'
    )
    assert secret not in result.stderr


@pytest.mark.parametrize("container", ["regular", "zip-entry"])
def test_undecodable_malformed_nested_json_fails_closed(
    tmp_path: Path,
    container: str,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    secret = "undecodable-malformed-nested-secret-123456789"
    payload = (
        b'{"key":"LLM_ALPHA_API_KEY","value":{"primary":"'
        + secret.encode("ascii")
        + b'"\xff'
    )
    if container == "regular":
        (artifact_root / f"{secret}.json").write_bytes(payload)
        expected = artifact_scanner.Finding(
            artifact="[redacted]",
            rule="api_key_assignment",
        )
        expected_stderr = (
            'artifact="[redacted]" rule="api_key_assignment"\n'
        )
    else:
        with ZipFile(artifact_root / "trace.zip", "w") as archive:
            archive.writestr(f"{secret}.json", payload)
        expected = artifact_scanner.Finding(
            artifact="[redacted]",
            zip_entry="[redacted]",
            rule="api_key_assignment",
        )
        expected_stderr = (
            'artifact="[redacted]" zip_entry="[redacted]" '
            'rule="api_key_assignment"\n'
        )

    findings, scanned_files = artifact_scanner.scan_artifacts(
        artifact_root,
        CANARY.encode("ascii"),
    )
    result = _run_scanner(artifact_root)

    assert scanned_files == 1
    assert findings == [expected]
    assert secret not in repr(findings)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == expected_stderr
    assert secret not in result.stderr


def test_authorization_metadata_field_cannot_hide_an_unmasked_secret(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    secret = "authorization-scheme-secret-value-123456789"
    (artifact_root / "playwright-results.json").write_text(
        json.dumps(
            {
                "key": "Authorization",
                "value": {"scheme": secret, "credentials": "[redacted]"},
            }
        ),
        encoding="utf-8",
    )

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        'artifact="playwright-results.json" rule="authorization_header"\n'
    )
    assert secret not in result.stderr


def test_trace_zip_entry_leak_fails_without_echoing_secret(tmp_path: Path) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    trace_path = artifact_root / "trace.zip"
    with ZipFile(trace_path, "w") as archive:
        archive.writestr(
            "trace.network",
            b'{"headers":[{"name":"authorization","value":"Bearer zip-auth-value"}]}',
        )

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        'artifact="trace.zip" zip_entry="trace.network" '
        'rule="authorization_header"\n'
    )
    assert "zip-auth-value" not in result.stderr


def test_zip_archive_comment_canary_fails_without_echoing_secret(tmp_path: Path) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    with ZipFile(artifact_root / "trace.zip", "w") as archive:
        archive.writestr("trace.network", b'{"safe":true}')
        archive.comment = CANARY.encode("ascii")

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == 'artifact="trace.zip" rule="playwright_canary"\n'
    assert CANARY not in result.stderr


def test_zip_entry_comment_credential_fails_without_echoing_secret(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    info = ZipInfo("trace.network")
    info.comment = b'Authorization: Bearer zip-comment-secret'
    with ZipFile(artifact_root / "trace.zip", "w") as archive:
        archive.writestr(info, b'{"safe":true}')

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        'artifact="trace.zip" zip_entry="trace.network" '
        'rule="authorization_header"\n'
    )
    assert "zip-comment-secret" not in result.stderr


@pytest.mark.parametrize(
    ("payload", "rule_name", "secret"),
    [
        (CANARY.encode("ascii"), "playwright_canary", CANARY),
        (b'{"api_key":"zip-extra-secret"}', "api_key_assignment", "zip-extra-secret"),
        (
            b'{"key":"LLM_ALPHA_API_KEY","value":"zip-extra-pair-secret"}',
            "api_key_assignment",
            "zip-extra-pair-secret",
        ),
    ],
    ids=["canary", "credential-shape", "key-value-pair"],
)
def test_zip_entry_extra_field_fails_without_echoing_secret(
    tmp_path: Path,
    payload: bytes,
    rule_name: str,
    secret: str,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    info = ZipInfo("trace.network")
    info.extra = _zip_extra_field(payload)
    with ZipFile(artifact_root / "trace.zip", "w") as archive:
        archive.writestr(info, b'{"safe":true}')

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        'artifact="trace.zip" zip_entry="trace.network" '
        f'rule="{rule_name}"\n'
    )
    assert secret not in result.stderr


@pytest.mark.parametrize(
    ("payload", "rule_name", "secret"),
    [
        (CANARY.encode("ascii"), "playwright_canary", CANARY),
        (b'{"api_key":"local-extra-secret"}', "api_key_assignment", "local-extra-secret"),
        (
            b'{"key":"LLM_ALPHA_API_KEY","value":"local-extra-pair-secret"}',
            "api_key_assignment",
            "local-extra-pair-secret",
        ),
        (
            b'{"key":"LLM_ALPHA_API_KEY","value":'
            b'{"primary":"nested-local-extra-secret"}}',
            "api_key_assignment",
            "nested-local-extra-secret",
        ),
        (
            b'{"key":"LLM_ALPHA_API_KEY","padding":"'
            + b"x" * 8192
            + b'","value":"long-local-extra-pair-secret"}',
            "api_key_assignment",
            "long-local-extra-pair-secret",
        ),
    ],
    ids=[
        "canary",
        "credential-shape",
        "key-value-pair",
        "nested-key-value-pair",
        "long-key-value-pair",
    ],
)
def test_raw_local_zip_metadata_fails_without_echoing_secret(
    tmp_path: Path,
    payload: bytes,
    rule_name: str,
    secret: str,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    trace_path = artifact_root / "trace.zip"
    safe_extra = _zip_extra_field(b"x" * len(payload))
    info = ZipInfo("trace.network")
    info.extra = safe_extra
    with ZipFile(trace_path, "w") as archive:
        archive.writestr(info, b'{"safe":true}')

    raw_archive = trace_path.read_bytes()
    assert raw_archive.startswith(b"PK\x03\x04")
    filename_size = int.from_bytes(raw_archive[26:28], "little")
    extra_size = int.from_bytes(raw_archive[28:30], "little")
    extra_start = 30 + filename_size
    extra_end = extra_start + extra_size
    assert raw_archive[extra_start:extra_end] == safe_extra
    raw_archive = (
        raw_archive[:extra_start]
        + _zip_extra_field(payload)
        + raw_archive[extra_end:]
    )
    trace_path.write_bytes(raw_archive)

    with ZipFile(trace_path) as archive:
        assert archive.infolist()[0].extra == safe_extra
        assert archive.read("trace.network") == b'{"safe":true}'

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == f'artifact="trace.zip" rule="{rule_name}"\n'
    assert secret not in result.stderr


def test_raw_local_malformed_nested_metadata_redacts_global_locations(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    secret = "raw-local-malformed-nested-secret-123456789"
    (artifact_root / f"a-{secret}.png").write_bytes(b"not-actually-media")
    payload = (
        b'{"key":"LLM_ALPHA_API_KEY","value":{"primary":"'
        + secret.encode("ascii")
        + b'"'
    )
    trace_path = artifact_root / "z-trace.zip"
    safe_extra = _zip_extra_field(b"x" * len(payload))
    info = ZipInfo("trace.network")
    info.extra = safe_extra
    with ZipFile(trace_path, "w") as archive:
        archive.writestr(info, b'{"safe":true}')

    raw_archive = trace_path.read_bytes()
    filename_size = int.from_bytes(raw_archive[26:28], "little")
    extra_size = int.from_bytes(raw_archive[28:30], "little")
    extra_start = 30 + filename_size
    extra_end = extra_start + extra_size
    trace_path.write_bytes(
        raw_archive[:extra_start]
        + _zip_extra_field(payload)
        + raw_archive[extra_end:]
    )

    with ZipFile(trace_path) as archive:
        assert archive.infolist()[0].extra == safe_extra
        assert archive.read("trace.network") == b'{"safe":true}'

    findings, scanned_files = artifact_scanner.scan_artifacts(
        artifact_root,
        CANARY.encode("ascii"),
    )
    result = _run_scanner(artifact_root)

    assert scanned_files == 2
    assert findings == [
        artifact_scanner.Finding(
            artifact="[redacted]",
            rule="api_key_assignment",
        ),
        artifact_scanner.Finding(
            artifact="[redacted]",
            rule="uninspectable_media",
        ),
    ]
    assert secret not in repr(findings)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        'artifact="[redacted]" rule="api_key_assignment"\n'
        'artifact="[redacted]" rule="uninspectable_media"\n'
    )
    assert secret not in result.stderr


@pytest.mark.parametrize(
    ("rule_name", "secret", "payload"),
    [
        (
            "authorization_header",
            "raw-local-auth-secret-123456789",
            b"Authorization: Bearer raw-local-auth-secret-123456789",
        ),
        (
            "cookie_header",
            "raw-local-cookie-secret-123456789",
            b"Cookie: session=raw-local-cookie-secret-123456789",
        ),
        (
            "api_key_assignment",
            "raw-local-api-secret-123456789",
            b"OPENAI_API_KEY=raw-local-api-secret-123456789   ",
        ),
    ],
    ids=["authorization", "cookie", "api-key"],
)
def test_raw_local_zip_extra_text_at_payload_start_is_detected(
    tmp_path: Path,
    rule_name: str,
    secret: str,
    payload: bytes,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    trace_path = artifact_root / f"{secret}.zip"
    safe_extra = _zip_extra_field(b"x" * len(payload))
    info = ZipInfo("trace.network")
    info.extra = safe_extra
    with ZipFile(trace_path, "w") as archive:
        archive.writestr(info, b'{"safe":true}')

    raw_archive = trace_path.read_bytes()
    filename_size = int.from_bytes(raw_archive[26:28], "little")
    extra_size = int.from_bytes(raw_archive[28:30], "little")
    extra_start = 30 + filename_size
    extra_end = extra_start + extra_size
    raw_archive = (
        raw_archive[:extra_start]
        + _zip_extra_field(payload)
        + raw_archive[extra_end:]
    )
    trace_path.write_bytes(raw_archive)

    with ZipFile(trace_path) as archive:
        assert archive.infolist()[0].extra == safe_extra
        assert archive.read("trace.network") == b'{"safe":true}'

    findings, scanned_files = artifact_scanner.scan_artifacts(
        artifact_root,
        CANARY.encode("ascii"),
    )
    result = _run_scanner(artifact_root)

    assert scanned_files == 1
    assert findings == [
        artifact_scanner.Finding(
            artifact="[redacted]",
            rule=rule_name,
        )
    ]
    assert secret not in repr(findings)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        f'artifact="[redacted]" rule="{rule_name}"\n'
    )
    assert secret not in result.stderr


def test_raw_key_value_pair_is_detected_across_read_chunks() -> None:
    secret = b"cross-chunk-secret-value-123456789"
    payload = b'{"key":"LLM_ALPHA_API_KEY","value":"' + secret + b'"}'
    split_at = len(payload) // 2
    stream = BytesIO(
        b"x" * (artifact_scanner.READ_CHUNK_SIZE - split_at)
        + payload[:split_at]
        + payload[split_at:]
    )

    contains_canary, rule_names, malformed_rules = (
        artifact_scanner._scan_raw_zip_stream(
            stream,
            b"PK\x03\x04",
            CANARY.encode("ascii"),
        )
    )

    assert contains_canary is False
    assert "api_key_assignment" in rule_names
    assert malformed_rules == set()


def test_maximum_key_value_gap_is_detected_across_read_chunks() -> None:
    secret = b"maximum-gap-cross-chunk-secret"
    gap_prefix = b',"padding":"'
    gap_suffix = b'",'
    padding_size = 65535 - len(gap_prefix) - len(gap_suffix)
    payload = (
        b'{"key":"LLM_ALPHA_API_KEY"'
        + gap_prefix
        + b"x" * padding_size
        + gap_suffix
        + b'"value":"'
        + secret
        + b'"}'
    )
    value_field_offset = payload.index(b'"value"')
    stream = BytesIO(
        b"x" * (artifact_scanner.READ_CHUNK_SIZE - value_field_offset)
        + payload
    )

    contains_canary, rule_names, malformed_rules = (
        artifact_scanner._scan_raw_zip_stream(
            stream,
            b"PK\x03\x04",
            CANARY.encode("ascii"),
        )
    )

    assert contains_canary is False
    assert "api_key_assignment" in rule_names
    assert malformed_rules == set()


def test_malformed_zip_extra_field_fails_closed(tmp_path: Path) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    info = ZipInfo("trace.network")
    info.extra = b"\xfe"
    with ZipFile(artifact_root / "trace.zip", "w") as archive:
        archive.writestr(info, b'{"safe":true}')

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        'artifact="trace.zip" zip_entry="trace.network" '
        'rule="zip_metadata_read_error"\n'
    )


def test_zip_secret_redacts_every_finding_location_for_the_artifact(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    secret = "opaque-zip-entry-secret-value-123456789"
    info = ZipInfo(secret)
    info.extra = b"\xfe"
    payload = json.dumps({"key": "LLM_ALPHA_API_KEY", "value": secret})
    with ZipFile(artifact_root / "trace.zip", "w") as archive:
        archive.writestr(info, payload)

    findings, scanned_files = artifact_scanner.scan_artifacts(
        artifact_root,
        CANARY.encode("ascii"),
    )
    result = _run_scanner(artifact_root)

    assert scanned_files == 1
    assert findings == [
        artifact_scanner.Finding(
            artifact="trace.zip",
            zip_entry="[redacted]",
            rule="api_key_assignment",
        ),
        artifact_scanner.Finding(
            artifact="trace.zip",
            zip_entry="[redacted]",
            rule="zip_metadata_read_error",
        ),
    ]
    assert all(secret not in repr(finding) for finding in findings)
    assert secret not in repr(findings)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        'artifact="trace.zip" zip_entry="[redacted]" '
        'rule="api_key_assignment"\n'
        'artifact="trace.zip" zip_entry="[redacted]" '
        'rule="zip_metadata_read_error"\n'
    )
    assert secret not in result.stderr


def test_corrupt_trace_zip_fails_without_exception_text(tmp_path: Path) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    (artifact_root / "trace.zip").write_bytes(b"not-a-zip corrupt-archive-value")

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == 'artifact="trace.zip" rule="zip_read_error"\n'
    assert "corrupt-archive-value" not in result.stderr
    assert "Traceback" not in result.stderr


def test_raw_canary_in_unknown_binary_fails_without_echoing_canary(tmp_path: Path) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    (artifact_root / "failure.bin").write_bytes(
        b"\x00binary-prefix\x00" + CANARY.encode("ascii") + b"\x00binary-suffix"
    )

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == 'artifact="failure.bin" rule="playwright_canary"\n'
    assert CANARY not in result.stderr


def test_valid_png_with_rendered_canary_is_rejected_as_uninspectable_media(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    png = _rendered_canary_png()
    screenshot = artifact_root / "failure.png"
    screenshot.write_bytes(png)

    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert CANARY.encode("ascii") not in png
    with Image.open(screenshot) as decoded:
        assert decoded.format == "PNG"
        difference = ImageChops.difference(
            decoded.convert("RGB"),
            Image.new("RGB", decoded.size, "white"),
        )
        assert difference.getbbox() is not None

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == 'artifact="failure.png" rule="uninspectable_media"\n'
    assert CANARY not in result.stderr


def test_valid_png_in_extensionless_trace_entry_is_rejected(tmp_path: Path) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    with ZipFile(artifact_root / "trace.zip", "w") as archive:
        archive.writestr("resources/content-addressed-entry", _rendered_canary_png())

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stderr == (
        'artifact="trace.zip" zip_entry="resources/content-addressed-entry" '
        'rule="uninspectable_media"\n'
    )
    assert CANARY not in result.stderr


@pytest.mark.parametrize("filename", ["failure.jpg", "failure.jpeg", "failure.bin"])
def test_valid_jpeg_with_rendered_canary_is_rejected_as_uninspectable_media(
    tmp_path: Path,
    filename: str,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    jpeg = _rendered_canary_jpeg()
    screenshot = artifact_root / filename
    screenshot.write_bytes(jpeg)

    assert jpeg.startswith(b"\xff\xd8\xff")
    assert CANARY.encode("ascii") not in jpeg
    with Image.open(screenshot) as decoded:
        assert decoded.format == "JPEG"
        difference = ImageChops.difference(
            decoded.convert("RGB"),
            Image.new("RGB", decoded.size, "white"),
        )
        assert difference.getbbox() is not None

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == f'artifact="{filename}" rule="uninspectable_media"\n'
    assert CANARY not in result.stderr


def test_webm_suffix_and_extensionless_ebml_entry_are_rejected(tmp_path: Path) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    (artifact_root / "failure.webm").write_bytes(b"not-trusted-by-extension")
    with ZipFile(artifact_root / "trace.zip", "w") as archive:
        archive.writestr("resources/video", b"\x1a\x45\xdf\xa3webm-fixture")

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stderr == (
        'artifact="failure.webm" rule="uninspectable_media"\n'
        'artifact="trace.zip" zip_entry="resources/video" '
        'rule="uninspectable_media"\n'
    )


def test_canary_in_artifact_filename_is_redacted(tmp_path: Path) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    (artifact_root / f"failure-{CANARY}.log").write_text("safe\n", encoding="utf-8")

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        'artifact="[redacted]" rule="playwright_canary"\n'
    )
    assert CANARY not in result.stderr


def test_canary_in_zip_entry_filename_is_redacted(tmp_path: Path) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    with ZipFile(artifact_root / "trace.zip", "w") as archive:
        archive.writestr(f"resources/failure-{CANARY}.network", "safe\n")

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        'artifact="trace.zip" '
        'zip_entry="[redacted]" '
        'rule="playwright_canary"\n'
    )
    assert CANARY not in result.stderr


@pytest.mark.parametrize(
    ("container", "path_name", "secret", "expected_stderr"),
    [
        (
            "regular",
            "OPENAI_API_KEY=filename-secret.log",
            "filename-secret",
            'artifact="[redacted]" rule="api_key_assignment"\n',
        ),
        (
            "zip",
            "OPENAI_API_KEY=zip-filename-secret.network",
            "zip-filename-secret",
            'artifact="trace.zip" zip_entry="[redacted]" '
            'rule="api_key_assignment"\n',
        ),
    ],
)
def test_credential_shaped_name_alone_fails_without_echoing_value(
    tmp_path: Path,
    container: str,
    path_name: str,
    secret: str,
    expected_stderr: str,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    if container == "regular":
        (artifact_root / path_name).write_text("safe\n", encoding="utf-8")
    else:
        with ZipFile(artifact_root / "trace.zip", "w") as archive:
            archive.writestr(path_name, "safe\n")

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == expected_stderr
    assert secret not in result.stderr


def test_structured_secret_in_artifact_name_is_fully_redacted(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    secret = "nested-filename-secret-value-123456789"
    artifact_name = json.dumps(
        {
            "key": "LLM_ALPHA_API_KEY",
            "value": {"primary": secret},
        },
        separators=(",", ":"),
    )
    (artifact_root / artifact_name).write_text("safe\n", encoding="utf-8")

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        'artifact="[redacted]" rule="api_key_assignment"\n'
    )
    assert secret not in result.stderr


@pytest.mark.parametrize("container", ["regular", "zip-entry"])
def test_matched_plain_secret_reused_as_location_is_fully_redacted(
    tmp_path: Path,
    container: str,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    secret = "opaque-value-12345678901234567890"
    payload = json.dumps({"key": "LLM_ALPHA_API_KEY", "value": secret})
    if container == "regular":
        (artifact_root / secret).write_text(payload, encoding="utf-8")
        expected = artifact_scanner.Finding(
            artifact="[redacted]",
            rule="api_key_assignment",
        )
        expected_stderr = 'artifact="[redacted]" rule="api_key_assignment"\n'
    else:
        with ZipFile(artifact_root / "trace.zip", "w") as archive:
            archive.writestr(secret, payload)
        expected = artifact_scanner.Finding(
            artifact="trace.zip",
            zip_entry="[redacted]",
            rule="api_key_assignment",
        )
        expected_stderr = (
            'artifact="trace.zip" zip_entry="[redacted]" '
            'rule="api_key_assignment"\n'
        )

    findings, scanned_files = artifact_scanner.scan_artifacts(
        artifact_root,
        CANARY.encode("ascii"),
    )
    result = _run_scanner(artifact_root)

    assert scanned_files == 1
    assert findings == [expected]
    assert secret not in repr(findings)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == expected_stderr
    assert secret not in result.stderr


@pytest.mark.parametrize(
    ("unsafe_name", "credential_name", "unsafe_content", "unsafe_rule"),
    [
        (
            "a-{secret}.png",
            "z-credentials.json",
            b"not-actually-media",
            "uninspectable_media",
        ),
        (
            "z-{secret}.zip",
            "a-credentials.json",
            b"not-a-zip",
            "zip_read_error",
        ),
    ],
    ids=["media-before-secret", "read-error-after-secret"],
)
def test_scan_global_secret_reuse_redacts_locations_in_either_order(
    tmp_path: Path,
    unsafe_name: str,
    credential_name: str,
    unsafe_content: bytes,
    unsafe_rule: str,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    secret = "cross-artifact-secret-value-123456789"
    (artifact_root / unsafe_name.format(secret=secret)).write_bytes(unsafe_content)
    (artifact_root / credential_name).write_text(
        json.dumps({"key": "LLM_ALPHA_API_KEY", "value": secret}),
        encoding="utf-8",
    )

    findings, scanned_files = artifact_scanner.scan_artifacts(
        artifact_root,
        CANARY.encode("ascii"),
    )
    result = _run_scanner(artifact_root)

    assert scanned_files == 2
    assert findings == [
        artifact_scanner.Finding(
            artifact="[redacted]",
            rule=unsafe_rule,
        ),
        artifact_scanner.Finding(
            artifact=credential_name,
            rule="api_key_assignment",
        ),
    ]
    assert secret not in repr(findings)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        f'artifact="[redacted]" rule="{unsafe_rule}"\n'
        f'artifact="{credential_name}" rule="api_key_assignment"\n'
    )
    assert secret not in result.stderr


def test_malformed_nested_secret_coarsely_redacts_cross_artifact_location(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    secret = "malformed-cross-artifact-secret-123456789"
    (artifact_root / f"a-{secret}.png").write_bytes(b"not-actually-media")
    (artifact_root / "z-broken.json").write_text(
        '{"key":"LLM_ALPHA_API_KEY","value":{"primary":"'
        + secret
        + '"',
        encoding="utf-8",
    )

    findings, scanned_files = artifact_scanner.scan_artifacts(
        artifact_root,
        CANARY.encode("ascii"),
    )
    result = _run_scanner(artifact_root)

    assert scanned_files == 2
    assert findings == [
        artifact_scanner.Finding(
            artifact="[redacted]",
            rule="api_key_assignment",
        ),
        artifact_scanner.Finding(
            artifact="[redacted]",
            rule="uninspectable_media",
        ),
    ]
    assert secret not in repr(findings)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        'artifact="[redacted]" rule="api_key_assignment"\n'
        'artifact="[redacted]" rule="uninspectable_media"\n'
    )
    assert secret not in result.stderr


@pytest.mark.parametrize("container", ["regular", "zip-entry"])
@pytest.mark.parametrize(
    ("rule_name", "secret", "payload"),
    [
        (
            "authorization_header",
            "bearer-location-secret-123456789",
            "Authorization: Bearer bearer-location-secret-123456789\n",
        ),
        (
            "cookie_header",
            "cookie-location-secret-123456789",
            "Cookie: session=cookie-location-secret-123456789\n",
        ),
        (
            "api_key_assignment",
            "api-key-location-secret-123456789",
            "OPENAI_API_KEY=api-key-location-secret-123456789   \n",
        ),
        (
            "url_userinfo",
            "userinfo-password-location-secret-123456789",
            "request=https://artifact-user:"
            "userinfo-password-location-secret-123456789@example.test/v1\n",
        ),
        (
            "url_userinfo",
            "userinfo-username-location-secret-123456789",
            "request=https://userinfo-username-location-secret-123456789:"
            "artifact-password@example.test/v1\n",
        ),
        (
            "url_userinfo",
            "userinfo-encoded-password-secret-123456789",
            "request=https://artifact-user:"
            "%75serinfo-encoded-password-secret-123456789@example.test/v1\n",
        ),
        (
            "url_userinfo",
            "userinfo-encoded-username-secret-123456789",
            "request=https://"
            "%75serinfo-encoded-username-secret-123456789:"
            "artifact-password@example.test/v1\n",
        ),
    ],
    ids=[
        "bearer-token",
        "cookie-value",
        "api-key-trailing-space",
        "userinfo-password",
        "userinfo-username",
        "percent-encoded-userinfo-password",
        "percent-encoded-userinfo-username",
    ],
)
def test_credential_component_reused_as_location_is_fully_redacted(
    tmp_path: Path,
    container: str,
    rule_name: str,
    secret: str,
    payload: str,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    path_name = f"{secret}.log"
    if container == "regular":
        (artifact_root / path_name).write_text(payload, encoding="utf-8")
        expected = artifact_scanner.Finding(
            artifact="[redacted]",
            rule=rule_name,
        )
        expected_stderr = f'artifact="[redacted]" rule="{rule_name}"\n'
    else:
        with ZipFile(artifact_root / "trace.zip", "w") as archive:
            archive.writestr(path_name, payload)
        expected = artifact_scanner.Finding(
            artifact="trace.zip",
            zip_entry="[redacted]",
            rule=rule_name,
        )
        expected_stderr = (
            'artifact="trace.zip" zip_entry="[redacted]" '
            f'rule="{rule_name}"\n'
        )

    findings, scanned_files = artifact_scanner.scan_artifacts(
        artifact_root,
        CANARY.encode("ascii"),
    )
    result = _run_scanner(artifact_root)

    assert scanned_files == 1
    assert findings == [expected]
    assert secret not in repr(findings)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == expected_stderr
    assert secret not in result.stderr


def test_safe_failed_playwright_diagnostics_and_masked_values_pass(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    (artifact_root / "service.log").write_text(
        "backend ready\n"
        'Authorization: Bearer ******\n'
        "Cookie: session=******\n"
        "OPENAI_API_KEY=******\n"
        "request=https://example.test/v1?token=***\n",
        encoding="utf-8",
    )
    (artifact_root / "playwright-results.json").write_text(
        '{"stats":{"expected":0,"unexpected":1},'
        '"errors":[{"message":"assertion failed"}],"suites":[]}\n',
        encoding="utf-8",
    )
    result = _run_scanner(artifact_root)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "Playwright artifact scan passed" in result.stdout
    assert {path.name for path in artifact_root.iterdir()} == {
        "playwright-results.json",
        "service.log",
    }


def test_safe_masked_trace_zip_and_opaque_resource_pass(tmp_path: Path) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    with ZipFile(artifact_root / "trace.zip", "w") as archive:
        archive.writestr(
            "trace.network",
            '{"headers":['
            '{"name":"authorization","value":"[redacted]"},'
            '{"name":"cookie","value":"session=******"}'
            '],"url":"https://example.test/v1?api_key=***",'
            '"api_key":"******"}',
        )
        archive.writestr(
            "masked.json",
            json.dumps(
                {
                    "key": "LLM_ALPHA_API_KEY",
                    "value": {"primary": "[redacted]"},
                }
            ),
        )
        archive.writestr("resources/image", b"\x00\x01\x02normal-resource")

    result = _run_scanner(artifact_root)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "Playwright artifact scan passed" in result.stdout


def test_machine_readable_playwright_report_is_strictly_scanned(tmp_path: Path) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    (artifact_root / "playwright-results.json").write_text(
        '{"error":"' + CANARY + '"}\n',
        encoding="utf-8",
    )

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stderr == (
        'artifact="playwright-results.json" rule="playwright_canary"\n'
    )
    assert CANARY not in result.stderr


def test_regular_file_read_failure_fails_closed_without_exception_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    unreadable = artifact_root / "service.log"
    unreadable.write_text("backend ready\n", encoding="utf-8")
    original_open = Path.open

    def fail_target_open(path: Path, *args: object, **kwargs: object):
        if path == unreadable:
            raise OSError(f"read failed: {CANARY}")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_target_open)
    monkeypatch.setenv("DSA_PLAYWRIGHT_ARTIFACT_CANARY", CANARY)

    exit_code = artifact_scanner.main([str(artifact_root)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == 'artifact="service.log" rule="artifact_read_error"\n'
    assert CANARY not in captured.err


def test_filesystem_and_zip_symlinks_fail_closed(tmp_path: Path) -> None:
    artifact_root = tmp_path / "test-results"
    artifact_root.mkdir()
    target = tmp_path / "outside.log"
    target.write_text(CANARY, encoding="utf-8")
    (artifact_root / "linked.log").symlink_to(target)
    link_info = ZipInfo("resources/linked.log")
    link_info.create_system = 3
    link_info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with ZipFile(artifact_root / "trace.zip", "w") as archive:
        archive.writestr(link_info, CANARY)

    result = _run_scanner(artifact_root)

    assert result.returncode == 1
    assert result.stderr == (
        'artifact="linked.log" rule="artifact_symlink_unsupported"\n'
        'artifact="trace.zip" rule="playwright_canary"\n'
        'artifact="trace.zip" zip_entry="resources/linked.log" '
        'rule="zip_entry_symlink_unsupported"\n'
    )
    assert CANARY not in result.stderr


def test_missing_canary_configuration_fails_closed(tmp_path: Path) -> None:
    root_secret = "caller-path-secret"
    artifact_root = tmp_path / root_secret
    artifact_root.mkdir()
    (artifact_root / "service.log").write_text("backend ready\n", encoding="utf-8")
    env = os.environ.copy()
    env.pop("DSA_PLAYWRIGHT_ARTIFACT_CANARY", None)

    result = subprocess.run(
        [sys.executable, str(SCANNER), str(artifact_root)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        'artifact="[artifact-root]" rule="playwright_canary_not_configured"\n'
    )
    assert root_secret not in result.stderr


def test_missing_artifact_root_uses_fixed_safe_label(tmp_path: Path) -> None:
    missing_root = tmp_path / f"missing-{CANARY}"

    result = _run_scanner(missing_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        'artifact="[artifact-root]" rule="artifact_root_missing"\n'
    )
    assert CANARY not in result.stderr


def test_internal_error_uses_fixed_safe_label(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_root = tmp_path / f"internal-{CANARY}"
    artifact_root.mkdir()
    monkeypatch.setenv("DSA_PLAYWRIGHT_ARTIFACT_CANARY", CANARY)

    def fail_scan(_root: Path, _canary: bytes):
        raise RuntimeError(CANARY)

    monkeypatch.setattr(artifact_scanner, "scan_artifacts", fail_scan)

    exit_code = artifact_scanner.main([str(artifact_root)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert captured.err == 'artifact="[artifact-root]" rule="scanner_internal_error"\n'
    assert CANARY not in captured.err


def test_secret_bearing_playwright_run_is_text_only_and_emits_json_report() -> None:
    config = (REPO_ROOT / "apps" / "dsa-web" / "playwright.config.ts").read_text(
        encoding="utf-8",
    )

    assert "['list']" in config
    assert "['json', { outputFile: path.join(resultDir, 'playwright-results.json') }]" in config
    assert "captureGitInfo: { commit: false, diff: false }" in config
    assert "globalSetup: './e2e/playwright-trace-global-setup.ts'" in config
    assert "resolvePlaywrightTracePolicy(process.env, process.argv.slice(2))" in config
    assert "trace: requestedTraceMode === 'off'" in config
    assert "screenshot: 'off'" in config
    assert "video: 'off'" in config
    assert "screenshots: false" in config
    assert "attachments: false" in config

    e2e_root = REPO_ROOT / "apps" / "dsa-web" / "e2e"
    source_paths = sorted(
        path
        for path in e2e_root.rglob("*")
        if path.suffix in {".js", ".mjs", ".ts", ".tsx"}
    )
    assert source_paths
    for source_path in source_paths:
        source = source_path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_CREDENTIAL_E2E_MEDIA_PATTERNS:
            assert forbidden.search(source) is None, (
                f"{source_path.relative_to(e2e_root)} generates uninspectable media"
            )


def test_ci_upload_is_gated_on_the_corresponding_scan_success() -> None:
    workflow_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    job = workflow["jobs"]["web-e2e"]
    steps = job["steps"]
    by_name = {step["name"]: step for step in steps}

    e2e = by_name["🎭 Playwright e2e (including i18n acceptance)"]
    preflight = by_name["🔒 Playwright credential safety preflight"]
    scan = by_name["🔐 Scan Playwright artifacts for secrets"]
    stage = by_name["📦 Stage allowlisted Playwright diagnostics"]
    staged_scan = by_name["🔐 Scan staged Playwright diagnostics"]
    upload = by_name["📤 Upload scanned Playwright diagnostics"]
    assert steps.index(preflight) < steps.index(e2e)
    assert steps.index(e2e) < steps.index(scan) < steps.index(stage)
    assert steps.index(stage) < steps.index(staged_scan) < steps.index(upload)
    assert preflight["run"] == "npm run test:e2e-security-preflight"
    assert scan["id"] == "artifact_scan"
    assert scan["if"] == "always()"
    assert scan["run"] == (
        'python scripts/scan_playwright_artifacts.py '
        '"apps/dsa-web/test-results/${DSA_WEB_E2E_RUN_ID}/"'
    )
    assert stage["id"] == "artifact_stage"
    assert stage["if"] == "${{ always() && steps.artifact_scan.outcome == 'success' }}"
    assert stage["env"] == {
        "SOURCE_DIR": "apps/dsa-web/test-results/${{ env.DSA_WEB_E2E_RUN_ID }}",
        "STAGING_DIR": "${{ runner.temp }}/playwright-upload",
    }
    assert stage["run"] == (
        'python scripts/stage_playwright_diagnostics.py '
        '"${SOURCE_DIR}" "${STAGING_DIR}"'
    )
    assert staged_scan["id"] == "staged_artifact_scan"
    assert staged_scan["if"] == (
        "${{ always() && steps.artifact_scan.outcome == 'success' "
        "&& steps.artifact_stage.outcome == 'success' }}"
    )
    assert staged_scan["run"] == (
        'python scripts/scan_playwright_artifacts.py '
        '"${{ runner.temp }}/playwright-upload/"'
    )
    assert upload["if"] == (
        "${{ always() && steps.artifact_scan.outcome == 'success' "
        "&& steps.artifact_stage.outcome == 'success' "
        "&& steps.staged_artifact_scan.outcome == 'success' }}"
    )
    assert upload["with"]["path"] == "${{ runner.temp }}/playwright-upload/"
    assert upload["with"]["if-no-files-found"] == "error"
    assert job["env"]["DSA_WEB_E2E_RUN_ID"] == "ci-secret-bearing"
    assert job["env"]["DSA_WEB_E2E_CREDENTIAL_BEARING"] == "true"
    assert job["env"]["DSA_WEB_E2E_TRACE"] == "off"
    assert "DSA_PLAYWRIGHT_ARTIFACT_CANARY" in job["env"]
    assert e2e["env"]["DSA_WEB_E2E_ALPHA_API_KEY"] == (
        "${{ env.DSA_PLAYWRIGHT_ARTIFACT_CANARY }}"
    )


def test_repository_playwright_entrypoint_rejects_alternate_config() -> None:
    web_root = REPO_ROOT / "apps" / "dsa-web"
    package = json.loads((web_root / "package.json").read_text(encoding="utf-8"))

    assert package["scripts"]["test:smoke"] == "node e2e/run-playwright-tests.mjs"
    result = subprocess.run(
        [
            "node",
            "e2e/run-playwright-tests.mjs",
            "--config",
            "alternate.config.ts",
        ],
        cwd=web_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "The repository Playwright entry point does not allow alternate config files.\n"
    )
