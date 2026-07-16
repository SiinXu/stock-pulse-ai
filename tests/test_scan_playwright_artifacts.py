"""Regression tests for the Playwright artifact secret gate."""

from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
from zipfile import ZipFile, ZipInfo

from PIL import Image, ImageChops, ImageDraw, ImageFont
import pytest
import yaml

from scripts import scan_playwright_artifacts as artifact_scanner


REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNER = REPO_ROOT / "scripts" / "scan_playwright_artifacts.py"
CANARY = "stockpulse-playwright-canary-7f91c2a6b43d"


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
    ],
    ids=["canary", "credential-shape"],
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
    ],
    ids=["canary", "credential-shape"],
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
        'artifact="failure-[redacted].log" rule="playwright_canary"\n'
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
        'zip_entry="resources/failure-[redacted].network" '
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
            'artifact="OPENAI_API_KEY=[redacted]" rule="api_key_assignment"\n',
        ),
        (
            "zip",
            "OPENAI_API_KEY=zip-filename-secret.network",
            "zip-filename-secret",
            'artifact="trace.zip" zip_entry="OPENAI_API_KEY=[redacted]" '
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
    with ZipFile(artifact_root / "trace.zip", "w") as archive:
        archive.writestr(
            "trace.network",
            '{"headers":['
            '{"name":"authorization","value":"[redacted]"},'
            '{"name":"cookie","value":"session=******"}'
            '],"url":"https://example.test/v1?api_key=***",'
            '"api_key":"******"}',
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
    assert "screenshot: 'off'" in config
    assert "video: 'off'" in config
    assert "screenshots: false" in config
    assert "attachments: false" in config

    forbidden_media_generation = (
        re.compile(r"\.\s*screenshot\s*\("),
        re.compile(r"contentType\s*:\s*['\"]image/"),
        re.compile(r"\brecordVideo\b"),
        re.compile(r"\.\s*video\s*\("),
        re.compile(r"\bscreenshots\s*:\s*true\b"),
    )
    e2e_root = REPO_ROOT / "apps" / "dsa-web" / "e2e"
    source_paths = sorted(
        path
        for path in e2e_root.rglob("*")
        if path.suffix in {".js", ".mjs", ".ts", ".tsx"}
    )
    assert source_paths
    for source_path in source_paths:
        source = source_path.read_text(encoding="utf-8")
        for forbidden in forbidden_media_generation:
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
    scan = by_name["🔐 Scan Playwright artifacts for secrets"]
    upload = by_name["📤 Upload scanned Playwright diagnostics"]
    assert steps.index(e2e) < steps.index(scan) < steps.index(upload)
    assert scan["id"] == "artifact_scan"
    assert scan["if"] == "always()"
    assert scan["run"] == (
        'python scripts/scan_playwright_artifacts.py '
        '"apps/dsa-web/test-results/${DSA_WEB_E2E_RUN_ID}/"'
    )
    assert upload["if"] == "${{ always() && steps.artifact_scan.outcome == 'success' }}"
    assert upload["with"]["path"] == (
        "apps/dsa-web/test-results/${{ env.DSA_WEB_E2E_RUN_ID }}/"
    )
    assert job["env"]["DSA_WEB_E2E_RUN_ID"] == "ci-secret-bearing"
    assert "DSA_PLAYWRIGHT_ARTIFACT_CANARY" in job["env"]
    assert e2e["env"]["DSA_WEB_E2E_ALPHA_API_KEY"] == (
        "${{ env.DSA_PLAYWRIGHT_ARTIFACT_CANARY }}"
    )
