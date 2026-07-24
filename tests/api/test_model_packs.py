from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import get_model_pack_import_service
from api.v1.endpoints import model_packs


class _ModelPackService:
    def __init__(self) -> None:
        self.started = []
        self.statuses = {}
        self.raise_on_start = None

    def start_import(self, source: Path, *, cleanup_root: Path):
        if self.raise_on_start is not None:
            raise self.raise_on_start
        self.started.append(
            {
                "source_name": source.name,
                "source_bytes": source.read_bytes(),
                "source_parent": source.parent,
                "cleanup_root": cleanup_root,
            }
        )
        shutil.rmtree(cleanup_root)
        return SimpleNamespace(task_id="task-model-pack")

    def get_import(self, task_id: str):
        return self.statuses.get(task_id)


def _client(service: _ModelPackService) -> TestClient:
    app = FastAPI()
    app.include_router(model_packs.router, prefix="/model-packs")
    app.dependency_overrides[get_model_pack_import_service] = lambda: service
    return TestClient(app)


def test_import_upload_uses_fixed_staging_name_and_returns_task() -> None:
    service = _ModelPackService()
    client = _client(service)

    response = client.post(
        "/model-packs/import",
        files={
            "file": (
                "../../private.modelpack",
                b"PK\x03\x04model-pack",
                "application/zip",
            )
        },
    )

    assert response.status_code == 202
    assert response.json() == {
        "status": "accepted",
        "task_id": "task-model-pack",
        "message": "Model Pack import queued.",
        "message_code": "local_model.import.queued",
    }
    assert len(service.started) == 1
    assert service.started[0]["source_name"] == "upload.modelpack"
    assert service.started[0]["source_bytes"] == b"PK\x03\x04model-pack"
    assert service.started[0]["source_parent"] == service.started[0]["cleanup_root"]
    assert not service.started[0]["cleanup_root"].exists()


def test_import_upload_rejects_unsupported_or_empty_files() -> None:
    service = _ModelPackService()
    client = _client(service)

    unsupported = client.post(
        "/model-packs/import",
        files={"file": ("weights.gguf", b"GGUF", "application/octet-stream")},
    )
    empty = client.post(
        "/model-packs/import",
        files={"file": ("empty.modelpack", b"", "application/zip")},
    )

    assert unsupported.status_code == 400
    assert unsupported.json()["detail"]["error"] == "unsupported_archive"
    assert empty.status_code == 400
    assert empty.json()["detail"]["error"] == "empty_model_pack"
    assert service.started == []


def test_stage_upload_cleans_private_files_after_stream_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    staging_root = tmp_path / "staging"

    class BrokenUploadFile:
        def read(self, _size: int) -> bytes:
            raise RuntimeError("read failed")

        def close(self) -> None:
            pass

    def make_staging(*, prefix: str) -> str:
        assert prefix == "stockpulse-model-pack-upload-"
        staging_root.mkdir()
        return str(staging_root)

    monkeypatch.setattr(model_packs.tempfile, "mkdtemp", make_staging)
    upload = SimpleNamespace(
        filename="test.modelpack",
        file=BrokenUploadFile(),
    )

    with pytest.raises(RuntimeError, match="read failed"):
        model_packs._stage_upload(upload)

    assert not staging_root.exists()


def test_import_submission_failure_is_sanitized() -> None:
    service = _ModelPackService()
    service.raise_on_start = RuntimeError("secret /private/path")
    client = _client(service)

    response = client.post(
        "/model-packs/import",
        files={"file": ("test.modelpack", b"PK\x03\x04data", "application/zip")},
    )

    assert response.status_code == 500
    body = response.json()
    assert body["detail"]["error"] == "model_pack_import_submission_failed"
    assert "secret" not in str(body)
    assert "/private/path" not in str(body)


def test_import_status_projects_actionable_result_and_not_found() -> None:
    service = _ModelPackService()
    service.statuses["completed"] = {
        "task_id": "completed",
        "status": "completed",
        "progress": 100,
        "error": None,
        "message": "Task completed",
        "result": {
            "model_id": "stockpulse/test:q4",
            "display_name": "Test",
            "minimum_memory_gb": 8,
            "license_id": "Apache-2.0",
            "warnings": ["Unexpected file is not part of the manifest: notes.txt"],
            "registration": {"models": "stockpulse/test:q4"},
        },
    }
    client = _client(service)

    completed = client.get("/model-packs/imports/completed")
    missing = client.get("/model-packs/imports/missing")

    assert completed.status_code == 200
    assert completed.json()["result"]["model_id"] == "stockpulse/test:q4"
    assert completed.json()["result"]["warnings"] == [
        "Unexpected file is not part of the manifest: notes.txt"
    ]
    assert missing.status_code == 404
    assert missing.json()["detail"]["error"] == "model_pack_import_not_found"


def test_import_status_uses_the_canonical_task_status_enum() -> None:
    service = _ModelPackService()
    client = _client(service)

    schema = client.get("/openapi.json").json()
    status_schema = schema["components"]["schemas"]["ModelPackImportStatus"]

    assert status_schema["properties"]["status"]["$ref"].endswith("/TaskStatusEnum")


def test_openapi_import_contract_has_no_caller_controlled_target_url() -> None:
    service = _ModelPackService()
    client = _client(service)

    schema = client.get("/openapi.json").json()
    request_schema = schema["paths"]["/model-packs/import"]["post"]["requestBody"][
        "content"
    ]["multipart/form-data"]["schema"]
    component = schema["components"]["schemas"][request_schema["$ref"].split("/")[-1]]

    assert set(component["properties"]) == {"file"}
    assert "base_url" not in str(component).lower()
    assert "url" not in str(component["properties"]).lower()
