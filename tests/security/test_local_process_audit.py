# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deny and failure path coverage for local-process security audit."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.llm.generation_backend import GenerationError, GenerationErrorCode
from src.llm.local_cli_backend import LocalCliGenerationBackend
from src.services.local_process_audit import LocalProcessAuditor
from src.services.ocr_extraction_service import OcrExtractionService
from src.services.security_audit_service import SecurityAuditUnavailable


class _RecordingAudit:
    def __init__(self, *, fail_attempt: bool = False, fail_completion: bool = False):
        self.fail_attempt = fail_attempt
        self.fail_completion = fail_completion
        self.attempts: list[dict] = []
        self.completions: list[dict] = []

    def record_attempt(self, **fields):
        if self.fail_attempt:
            raise SecurityAuditUnavailable()
        self.attempts.append(fields)

    def record_completion(self, **fields):
        if self.fail_completion:
            raise SecurityAuditUnavailable()
        self.completions.append(fields)


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ocr"


def test_ocr_reject_path_records_attempt_and_completion(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes((FIXTURES / "sample_statement_en.png").read_bytes())
    recorder = _RecordingAudit()
    service = OcrExtractionService(
        file_root=str(root),
        engine=lambda *_a, **_k: "must-not-run",
        local_process_auditor=LocalProcessAuditor(recorder=recorder),
    )

    payload = service.extract_path(str(outside))

    assert payload["status"] == "unavailable"
    assert len(recorder.attempts) == 1
    assert len(recorder.completions) == 1
    assert recorder.attempts[0]["event_type"] == "local_process.execute"
    assert recorder.attempts[0]["action"] == "local_process.ocr"
    assert recorder.completions[0]["outcome"] == "rejected"
    assert recorder.attempts[0]["correlation_id"] == recorder.completions[0]["correlation_id"]


def test_ocr_success_path_records_success(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    image = root / "statement.png"
    image.write_bytes((FIXTURES / "sample_statement_en.png").read_bytes())
    recorder = _RecordingAudit()
    service = OcrExtractionService(
        file_root=str(root),
        engine=lambda *_a, **_k: "AAPL 100",
        local_process_auditor=LocalProcessAuditor(recorder=recorder),
    )

    payload = service.extract_path("statement.png")

    assert payload["status"] == "available"
    assert recorder.completions[0]["outcome"] == "success"
    assert recorder.completions[0]["reason_code"] == "ocr_extract_succeeded"


def test_ocr_attempt_audit_failure_is_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    image = root / "statement.png"
    image.write_bytes((FIXTURES / "sample_statement_en.png").read_bytes())
    engine_calls = {"count": 0}

    def engine(*_a, **_k):
        engine_calls["count"] += 1
        return "must-not-run"

    service = OcrExtractionService(
        file_root=str(root),
        engine=engine,
        local_process_auditor=LocalProcessAuditor(
            recorder=_RecordingAudit(fail_attempt=True)
        ),
    )

    with pytest.raises(SecurityAuditUnavailable):
        service.extract_path("statement.png")
    assert engine_calls["count"] == 0


def test_ocr_completion_audit_failure_is_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    image = root / "statement.png"
    image.write_bytes((FIXTURES / "sample_statement_en.png").read_bytes())
    service = OcrExtractionService(
        file_root=str(root),
        engine=lambda *_a, **_k: "ok",
        local_process_auditor=LocalProcessAuditor(
            recorder=_RecordingAudit(fail_completion=True)
        ),
    )

    with pytest.raises(SecurityAuditUnavailable):
        service.extract_path("statement.png")


def test_local_cli_config_reject_is_audited(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _RecordingAudit()
    auditor = LocalProcessAuditor(recorder=recorder)
    monkeypatch.setattr(
        "src.services.local_process_audit.get_local_process_auditor",
        lambda: auditor,
    )
    backend = LocalCliGenerationBackend(
        SimpleNamespace(
            generation_backend_timeout_seconds=5,
            generation_backend_max_output_bytes=1024,
            local_cli_backend_max_concurrency=1,
        ),
        preset_id="codex_cli",
    )

    with patch.object(
        backend,
        "_resolve_command",
        side_effect=GenerationError(
            error_code=GenerationErrorCode.UNSAFE_CONFIG,
            stage="configuration",
            retryable=False,
            fallbackable=False,
            backend="codex_cli",
            provider="codex_cli",
            details={"reason": "unknown_local_cli_preset"},
        ),
    ):
        with pytest.raises(GenerationError):
            backend.generate("prompt", {})

    assert len(recorder.attempts) == 1
    assert recorder.attempts[0]["action"] == "local_process.cli"
    assert len(recorder.completions) == 1
    assert recorder.completions[0]["outcome"] == "rejected"
    assert recorder.completions[0]["reason_code"] == "unknown_local_cli_preset"


def test_local_cli_attempt_audit_failure_prevents_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auditor = LocalProcessAuditor(recorder=_RecordingAudit(fail_attempt=True))
    monkeypatch.setattr(
        "src.services.local_process_audit.get_local_process_auditor",
        lambda: auditor,
    )
    backend = LocalCliGenerationBackend(
        SimpleNamespace(
            generation_backend_timeout_seconds=5,
            generation_backend_max_output_bytes=1024,
            local_cli_backend_max_concurrency=1,
        ),
        preset_id="codex_cli",
    )
    resolve_called = {"count": 0}

    def _resolve():
        resolve_called["count"] += 1
        raise AssertionError("process must not start when audit attempt fails")

    with patch.object(backend, "_resolve_command", side_effect=_resolve):
        with pytest.raises(SecurityAuditUnavailable):
            backend.generate("prompt", {})
    assert resolve_called["count"] == 0
