# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-closed HTTP model_pack.import security-audit coverage (#1062 DAG-7)."""

from __future__ import annotations

import io
import json
import shutil
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from src.api import deps as api_deps
from src.api.v1.endpoints import model_packs
from src.api.v1.services.model_pack_import_audit import (
    MODEL_PACK_IMPORT_ACTION,
    MODEL_PACK_IMPORT_EVENT_TYPE,
    MODEL_PACK_IMPORT_KIND,
    MODEL_PACK_IMPORT_TARGET_TYPE,
    UNKNOWN_IMPORT_TARGET_ID,
    bounded_import_metadata,
    model_pack_import_metadata,
)
from src.config import Config
from src.repositories.security_audit_repo import SecurityAuditRepository
from src.services.security_audit_service import SecurityAuditService
from src.storage import DatabaseManager
from src.task_execution import TaskCommand, TaskStatus
from tests.api.test_model_packs import _desktop_attestation
from tests.security.test_security_audit_integrations import _RecordingAudit


CANARY = "model-pack-import-canary-secret"
CANARY_TOKEN = f"sk-{CANARY}"
CANARY_FILENAME = "secret-key.modelpack"
QUEUED_TASK_ID = "task-model-pack"


@pytest.fixture
def import_database(tmp_path):
    DatabaseManager.reset_instance()
    Config.reset_instance()
    manager = DatabaseManager(
        db_url=f"sqlite:///{tmp_path / 'model-pack-import-audit.sqlite'}"
    )
    try:
        yield manager
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


class _FakeImportService:
    def __init__(self, *, cleanup_on_start: bool = False) -> None:
        self.started: list[dict] = []
        self.statuses: dict[str, dict] = {}
        self.raise_on_start = None
        self.desktop_activations: list[tuple] = []
        self.queued: list[SimpleNamespace] = []
        self.cleanup_on_start = cleanup_on_start

    def start_import(self, source: Path, *, cleanup_root: Path):
        if self.raise_on_start is not None:
            raise self.raise_on_start
        task = SimpleNamespace(
            task_id=QUEUED_TASK_ID,
            status=TaskStatus.PENDING,
            kind=MODEL_PACK_IMPORT_KIND,
        )
        self.started.append(
            {
                "source_name": source.name,
                "source_parent": source.parent,
                "cleanup_root": cleanup_root,
                "byte_length": source.stat().st_size,
            }
        )
        self.queued.append(task)
        if self.cleanup_on_start:
            shutil.rmtree(cleanup_root, ignore_errors=True)
        return task

    def get_import(self, task_id: str):
        return self.statuses.get(task_id)

    def activate_desktop_import(self, local_model_service, **kwargs):
        self.desktop_activations.append((local_model_service, kwargs))
        return {
            "config_version": "config-2",
            "registered_models": [kwargs["model_id"]],
            "primary_model": f"ollama/{kwargs['model_id']}",
            "agent_model": "",
            "imported_models": [
                {
                    "model_id": kwargs["model_id"],
                    "display_name": kwargs["display_name"],
                    "minimum_memory_gb": kwargs["minimum_memory_gb"],
                    "license_id": kwargs["license_id"],
                }
            ],
            "model_id": kwargs["model_id"],
            "selected_primary": True,
            "selected_agent": False,
            "updated_keys": ["LLM_OLLAMA_MODELS"],
            "warnings": [],
            "applied_count": 1,
            "skipped_masked_count": 0,
            "reload_triggered": True,
        }


def _tiny_zip_with_canary(canary: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{canary}.txt", b"payload")
        archive.comment = canary.encode("utf-8")
    return buffer.getvalue()


def _http_app(service: _FakeImportService, audit) -> FastAPI:
    app = FastAPI()
    app.include_router(model_packs.router, prefix="/api/v1/model-packs")
    app.dependency_overrides[api_deps.get_model_pack_import_service] = lambda: service
    app.dependency_overrides[api_deps.get_local_model_service] = (
        lambda: "local-model-service"
    )
    app.dependency_overrides[api_deps.require_security_audit_service] = lambda: audit
    return app


def _post_import(client: TestClient, *, filename: str, content: bytes, headers=None):
    return client.post(
        "/api/v1/model-packs/import",
        headers=headers or {},
        files={"file": (filename, content, "application/zip")},
    )


def _import_events(audit: _RecordingAudit, *, phase: str) -> list[dict]:
    source = audit.attempts if phase == "attempt" else audit.completions
    return [
        event
        for event in source
        if event.get("event_type") == MODEL_PACK_IMPORT_EVENT_TYPE
    ]


def _visible_audit_payload(audit: _RecordingAudit) -> str:
    return json.dumps(
        {"attempts": audit.attempts, "completions": audit.completions},
        ensure_ascii=False,
        default=str,
    )


def _assert_accepted_pair(audit: _RecordingAudit, *, task_id: str) -> None:
    attempts = _import_events(audit, phase="attempt")
    completions = _import_events(audit, phase="completion")
    assert len(attempts) == 1
    assert len(completions) == 1
    assert attempts[0]["action"] == MODEL_PACK_IMPORT_ACTION
    assert attempts[0]["target_type"] == MODEL_PACK_IMPORT_TARGET_TYPE
    assert attempts[0]["target_id"] == UNKNOWN_IMPORT_TARGET_ID
    assert attempts[0]["actor_type"] == "administrator"
    assert attempts[0]["actor_id"] == "local_operator"
    assert attempts[0]["correlation_id"] == completions[0]["correlation_id"]
    assert completions[0]["target_id"] == task_id
    assert completions[0]["outcome"] == "accepted"
    assert completions[0]["reason_code"] == "accepted"
    assert completions[0]["metadata"]["kind"] == MODEL_PACK_IMPORT_KIND
    assert completions[0]["metadata"]["suffix"] in {".modelpack", ".zip"}
    assert type(completions[0]["metadata"]["byte_length"]) is int
    assert completions[0]["metadata"]["status"] == "pending"


def test_metadata_allowlist_drops_filename_path_archive_and_secrets() -> None:
    payload = model_pack_import_metadata(
        suffix=".modelpack",
        byte_length=12,
        status="pending",
    )
    assert payload["kind"] == MODEL_PACK_IMPORT_KIND
    assert payload["suffix"] == ".modelpack"
    assert payload["byte_length"] == 12
    assert payload["status"] == "pending"
    dropped = {
        "filename": CANARY_FILENAME,
        "path": "/tmp/secret-key.modelpack",
        "archive": CANARY,
        "cookie": CANARY,
        "token": CANARY_TOKEN,
        "manifest": "licensed/finance:q4",
        "model": "licensed/finance:q4",
        "license": "LicenseRef-Finance",
        "hash": "sha256:deadbeef",
        "prompt": "leak me",
        "Authorization": f"Bearer {CANARY_TOKEN}",
    }
    bounded = bounded_import_metadata({**payload, **dropped})
    dumped = json.dumps(bounded, ensure_ascii=False)
    for forbidden in dropped:
        assert forbidden not in bounded
    assert CANARY not in dumped
    assert CANARY_TOKEN not in dumped
    assert CANARY_FILENAME not in dumped
    assert "licensed/finance:q4" not in dumped


def test_http_happy_path_records_attempt_and_accepted_completion() -> None:
    audit = _RecordingAudit()
    service = _FakeImportService(cleanup_on_start=True)
    with TestClient(_http_app(service, audit)) as client:
        response = _post_import(
            client, filename="pack.modelpack", content=b"PK\x03\x04data"
        )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["task_id"] == QUEUED_TASK_ID
    assert body["message_code"] == "local_model.import.queued"
    assert len(service.started) == 1
    _assert_accepted_pair(audit, task_id=QUEUED_TASK_ID)
    assert audit.completions[0]["metadata"]["suffix"] == ".modelpack"
    assert audit.completions[0]["metadata"]["byte_length"] == len(b"PK\x03\x04data")


def test_attempt_failure_does_not_queue_and_cleans_staging(
    tmp_path: Path, monkeypatch
) -> None:
    staging_root = tmp_path / "staging"
    audit = _RecordingAudit(fail_attempt=True)
    service = _FakeImportService()

    def make_staging(*, prefix: str) -> str:
        assert prefix == "stockpulse-model-pack-upload-"
        staging_root.mkdir()
        return str(staging_root)

    monkeypatch.setattr(model_packs.tempfile, "mkdtemp", make_staging)
    with TestClient(_http_app(service, audit)) as client:
        response = _post_import(
            client, filename="pack.modelpack", content=b"PK\x03\x04data"
        )
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error"] == "security_audit_unavailable"
    assert detail["operation_completed"] is False
    assert "task_id" not in detail
    assert service.started == []
    assert service.queued == []
    assert not staging_root.exists()
    assert audit.attempts == []
    assert audit.completions == []


def test_completion_failure_after_accept_keeps_queued_task() -> None:
    audit = _RecordingAudit(fail_completion=True)
    service = _FakeImportService()
    with TestClient(_http_app(service, audit)) as client:
        response = _post_import(
            client, filename="pack.zip", content=b"PK\x03\x04data"
        )
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error"] == "security_audit_unavailable"
    assert detail["operation_completed"] is True
    assert detail["task_id"] == QUEUED_TASK_ID
    assert detail["kind"] == MODEL_PACK_IMPORT_KIND
    assert detail["status"] == "pending"
    assert len(service.started) == 1
    assert len(service.queued) == 1
    assert service.queued[0].task_id == QUEUED_TASK_ID
    assert _import_events(audit, phase="attempt")
    assert _import_events(audit, phase="completion") == []


def test_invalid_empty_unsupported_and_oversize_record_zero_events(
    monkeypatch,
) -> None:
    audit = _RecordingAudit()
    service = _FakeImportService()
    monkeypatch.setattr(model_packs, "MAX_MODEL_PACK_UPLOAD_BYTES", 4)
    with TestClient(_http_app(service, audit)) as client:
        unsupported = _post_import(
            client, filename="weights.gguf", content=b"GGUF"
        )
        empty = _post_import(client, filename="empty.modelpack", content=b"")
        oversize = _post_import(
            client, filename="large.modelpack", content=b"12345"
        )
    assert unsupported.status_code == 400
    assert unsupported.json()["detail"]["error"] == "unsupported_archive"
    assert empty.status_code == 400
    assert empty.json()["detail"]["error"] == "empty_model_pack"
    assert oversize.status_code == 413
    assert oversize.json()["detail"]["error"] == "model_pack_too_large"
    assert service.started == []
    assert audit.attempts == []
    assert audit.completions == []


def test_staging_enospc_records_zero_events(monkeypatch) -> None:
    audit = _RecordingAudit()
    service = _FakeImportService()

    def no_staging_space(*, prefix: str) -> str:
        assert prefix == "stockpulse-model-pack-upload-"
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(model_packs.tempfile, "mkdtemp", no_staging_space)
    with TestClient(_http_app(service, audit)) as client:
        response = _post_import(
            client, filename="pack.modelpack", content=b"PK\x03\x04data"
        )
    assert response.status_code == 507
    assert response.json()["detail"]["error"] == "insufficient_disk_space"
    assert service.started == []
    assert audit.attempts == []
    assert audit.completions == []


def test_queue_exception_records_failed_completion_and_preserves_500() -> None:
    audit = _RecordingAudit()
    service = _FakeImportService()
    service.raise_on_start = RuntimeError("secret /private/path")
    with TestClient(_http_app(service, audit)) as client:
        response = _post_import(
            client, filename="pack.modelpack", content=b"PK\x03\x04data"
        )
    assert response.status_code == 500
    body = response.json()
    assert body["detail"]["error"] == "model_pack_import_submission_failed"
    assert "secret" not in str(body)
    assert "/private/path" not in str(body)
    attempts = _import_events(audit, phase="attempt")
    completions = _import_events(audit, phase="completion")
    assert len(attempts) == 1
    assert len(completions) == 1
    assert completions[0]["outcome"] == "failure"
    assert completions[0]["reason_code"] == "submit_failed"
    assert attempts[0]["correlation_id"] == completions[0]["correlation_id"]


def test_http_canaries_never_reach_metadata() -> None:
    audit = _RecordingAudit()
    service = _FakeImportService(cleanup_on_start=True)
    archive = _tiny_zip_with_canary(CANARY)
    with TestClient(_http_app(service, audit)) as client:
        response = _post_import(
            client,
            filename=CANARY_FILENAME,
            content=archive,
            headers={
                "Cookie": f"session={CANARY}",
                "Authorization": f"Bearer {CANARY_TOKEN}",
            },
        )
    assert response.status_code == 202
    visible = _visible_audit_payload(audit)
    assert CANARY not in visible
    assert CANARY_TOKEN not in visible
    assert CANARY_FILENAME not in visible
    metadata = audit.completions[0]["metadata"]
    for forbidden in (
        "filename",
        "path",
        "archive",
        "cookie",
        "token",
        "manifest",
        "model",
        "license",
        "hash",
        "prompt",
        "Authorization",
    ):
        assert forbidden not in metadata
    assert set(metadata) <= {"kind", "suffix", "byte_length", "status"}


def test_desktop_activation_and_status_get_do_not_emit_model_pack_import(
    monkeypatch,
) -> None:
    audit = _RecordingAudit()
    service = _FakeImportService()
    service.statuses[QUEUED_TASK_ID] = {
        "task_id": QUEUED_TASK_ID,
        "status": "pending",
        "progress": 10,
        "error": None,
        "message": "queued",
        "result": None,
    }
    attestation = _desktop_attestation(monkeypatch, nonce="4" * 32)
    with TestClient(_http_app(service, audit)) as client:
        activation = client.post(
            "/api/v1/model-packs/desktop-activations",
            json={
                "model_id": "licensed/finance:q4",
                "display_name": "Licensed Finance Q4",
                "minimum_memory_gb": 16,
                "license_id": "LicenseRef-Finance",
                "expected_config_version": "config-1",
                "expected_runtime_identity": "a" * 64,
                "desktop_attestation": attestation,
            },
        )
        status_get = client.get(f"/api/v1/model-packs/imports/{QUEUED_TASK_ID}")
    assert activation.status_code == 200
    assert status_get.status_code == 200
    assert _import_events(audit, phase="attempt") == []
    assert _import_events(audit, phase="completion") == []


def test_direct_task_queue_submit_does_not_emit_model_pack_import() -> None:
    audit = _RecordingAudit()
    fake_queue = MagicMock()
    fake_queue.submit.return_value = "other-task"
    command = TaskCommand(
        kind="stock_analysis",
        run=lambda _context: {},
        metadata={"stock_code": "600519", "stock_name": "internal"},
    )
    with patch(
        "src.services.security_audit_service.get_security_audit_service",
        return_value=audit,
    ):
        fake_queue.submit(command)
    assert fake_queue.submit.call_count == 1
    assert _import_events(audit, phase="attempt") == []
    assert _import_events(audit, phase="completion") == []


def test_durable_store_happy_path_is_queryable_and_redacts_canaries(
    import_database,
) -> None:
    store = SecurityAuditService(
        repository=SecurityAuditRepository(import_database)
    )
    service = _FakeImportService(cleanup_on_start=True)
    archive = _tiny_zip_with_canary(CANARY)
    with TestClient(_http_app(service, store)) as client:
        response = _post_import(
            client,
            filename=CANARY_FILENAME,
            content=archive,
            headers={
                "Cookie": f"session={CANARY}",
                "Authorization": f"Bearer {CANARY_TOKEN}",
            },
        )
    assert response.status_code == 202
    page = store.list_events(
        event_type=MODEL_PACK_IMPORT_EVENT_TYPE, page_size=20
    )
    types = {(item.phase, item.action, item.outcome) for item in page.items}
    assert ("attempt", MODEL_PACK_IMPORT_ACTION, "pending") in types
    assert ("completion", MODEL_PACK_IMPORT_ACTION, "accepted") in types
    assert page.total >= 2
    correlation_ids = {item.correlation_id for item in page.items}
    assert len(correlation_ids) == 1
    dumped = json.dumps(
        [item.model_dump(mode="json") for item in page.items],
        ensure_ascii=False,
    )
    assert CANARY not in dumped
    assert CANARY_TOKEN not in dumped
    assert CANARY_FILENAME not in dumped
    assert all(item.metadata.get("kind") == MODEL_PACK_IMPORT_KIND for item in page.items)
    assert all(
        item.actor.type == "administrator" and item.actor.id == "local_operator"
        for item in page.items
    )
    with import_database.get_session() as session:
        raw_rows = session.execute(
            text(
                "SELECT actor_id, execution_id, target_id, metadata_json "
                "FROM security_audit_events"
            )
        ).all()
    rendered = " ".join(str(value) for row in raw_rows for value in row)
    assert CANARY not in rendered
    assert CANARY_TOKEN not in rendered
    assert CANARY_FILENAME not in rendered
    assert "Authorization" not in rendered


def test_desktop_operator_actor_token_when_desktop_mode(monkeypatch) -> None:
    monkeypatch.setenv("DSA_DESKTOP_MODE", "true")
    audit = _RecordingAudit()
    service = _FakeImportService(cleanup_on_start=True)
    with TestClient(_http_app(service, audit)) as client:
        response = _post_import(
            client, filename="pack.modelpack", content=b"PK\x03\x04data"
        )
    assert response.status_code == 202
    assert audit.attempts[0]["actor_id"] == "desktop_operator"
    assert audit.completions[0]["actor_id"] == "desktop_operator"
    assert audit.attempts[0]["actor_type"] == "administrator"
