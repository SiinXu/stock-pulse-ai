from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.formparsers import MultiPartParser

from api.deps import get_local_model_service, get_model_pack_import_service
from api.middlewares.model_pack_upload import (
    MODEL_PACK_IMPORT_PATH,
    ModelPackUploadLimitMiddleware,
)
from api.v1.endpoints import model_packs
from src.model_pack import (
    DESKTOP_MODEL_PACK_ATTESTATION_ENV,
    DESKTOP_MODEL_PACK_ATTESTATION_TTL_MS,
    ModelPackError,
)


_DESKTOP_ATTESTATION_SECRET = "a" * 64


def _desktop_attestation(
    monkeypatch,
    *,
    nonce: str,
    display_name: str = "Licensed Finance Q4",
    model_id: str = "licensed/finance:q4",
) -> str:
    monkeypatch.setenv("DSA_DESKTOP_MODE", "true")
    monkeypatch.setenv(
        DESKTOP_MODEL_PACK_ATTESTATION_ENV,
        _DESKTOP_ATTESTATION_SECRET,
    )
    issued_at = int(time.time() * 1000)
    payload = {
        "version": 1,
        "issuedAt": issued_at,
        "expiresAt": issued_at + DESKTOP_MODEL_PACK_ATTESTATION_TTL_MS,
        "nonce": nonce,
        "modelId": model_id,
        "displayName": display_name,
        "minimumMemoryGb": 16,
        "licenseId": "LicenseRef-Finance",
        "expectedConfigVersion": "config-1",
        "expectedRuntimeIdentity": "a" * 64,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(
        _DESKTOP_ATTESTATION_SECRET.encode("ascii"),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return f"{encoded}.{signature}"


class _ModelPackService:
    def __init__(self) -> None:
        self.started = []
        self.statuses = {}
        self.raise_on_start = None
        self.desktop_activations = []

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


def _app(
    service: _ModelPackService,
    *,
    max_request_bytes: int | None = None,
) -> FastAPI:
    app = FastAPI()
    if max_request_bytes is None:
        app.add_middleware(
            ModelPackUploadLimitMiddleware,
            import_path="/model-packs/import",
        )
    else:
        app.add_middleware(
            ModelPackUploadLimitMiddleware,
            import_path="/model-packs/import",
            max_request_bytes=max_request_bytes,
        )
    app.include_router(model_packs.router, prefix="/model-packs")
    app.dependency_overrides[get_model_pack_import_service] = lambda: service
    app.dependency_overrides[get_local_model_service] = lambda: "local-model-service"
    return app


def _client(
    service: _ModelPackService,
    *,
    max_request_bytes: int | None = None,
) -> TestClient:
    return TestClient(
        _app(service, max_request_bytes=max_request_bytes)
    )


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


def test_import_upload_rejects_bytes_beyond_the_staging_limit(monkeypatch) -> None:
    service = _ModelPackService()
    client = _client(service)
    monkeypatch.setattr(model_packs, "MAX_MODEL_PACK_UPLOAD_BYTES", 4)

    response = client.post(
        "/model-packs/import",
        files={"file": ("large.modelpack", b"12345", "application/zip")},
    )

    assert response.status_code == 413
    assert response.json()["detail"]["error"] == "model_pack_too_large"
    assert service.started == []


def test_import_rejects_declared_oversize_before_multipart_parser(
    monkeypatch,
) -> None:
    service = _ModelPackService()
    parser_called = False

    async def fail_if_parsed(_parser):
        nonlocal parser_called
        parser_called = True
        raise AssertionError("multipart parser must not receive an oversized body")

    monkeypatch.setattr(MultiPartParser, "parse", fail_if_parsed)
    client = _client(service, max_request_bytes=1024)

    response = client.post(
        "/model-packs/import",
        files={
            "file": (
                "large.modelpack",
                b"x" * (2 * 1024 * 1024),
                "application/zip",
            )
        },
    )

    assert response.status_code == 413
    assert response.json()["error"] == "model_pack_too_large"
    assert parser_called is False
    assert service.started == []


def test_import_rejects_chunked_oversize_without_forwarding_bytes_past_limit() -> None:
    forwarded = bytearray()
    sent = []

    async def downstream(scope, receive, send):
        assert scope["path"] == MODEL_PACK_IMPORT_PATH
        while True:
            message = await receive()
            forwarded.extend(message.get("body", b""))
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    messages = iter(
        [
            {"type": "http.request", "body": b"123", "more_body": True},
            {"type": "http.request", "body": b"456", "more_body": True},
            {"type": "http.request", "body": b"789", "more_body": False},
        ]
    )

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": MODEL_PACK_IMPORT_PATH,
        "raw_path": MODEL_PACK_IMPORT_PATH.encode("ascii"),
        "query_string": b"",
        "headers": [
            (b"content-type", b"multipart/form-data; boundary=model-pack"),
            (b"transfer-encoding", b"chunked"),
        ],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }

    asyncio.run(
        ModelPackUploadLimitMiddleware(
            downstream,
            max_request_bytes=4,
        )(scope, receive, send)
    )

    assert bytes(forwarded) == b"1234"
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413
    body = json.loads(sent[1]["body"])
    assert body["error"] == "model_pack_too_large"


def test_chunked_multipart_oversize_returns_413_before_endpoint() -> None:
    service = _ModelPackService()
    app = _app(service, max_request_bytes=128)
    boundary = b"model-pack"
    body = (
        b"--"
        + boundary
        + b"\r\nContent-Disposition: form-data; name=\"file\"; "
        + b"filename=\"large.modelpack\"\r\n"
        + b"Content-Type: application/zip\r\n\r\n"
        + (b"x" * 512)
        + b"\r\n--"
        + boundary
        + b"--\r\n"
    )
    chunks = iter(
        [
            {"type": "http.request", "body": body[:96], "more_body": True},
            {"type": "http.request", "body": body[96:256], "more_body": True},
            {"type": "http.request", "body": body[256:], "more_body": False},
        ]
    )
    sent = []

    async def receive():
        return next(chunks)

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/model-packs/import",
        "raw_path": b"/model-packs/import",
        "query_string": b"",
        "headers": [
            (
                b"content-type",
                b"multipart/form-data; boundary=model-pack",
            ),
            (b"transfer-encoding", b"chunked"),
        ],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
        "app": app,
    }

    asyncio.run(app(scope, receive, send))

    response_start = next(
        message for message in sent if message["type"] == "http.response.start"
    )
    response_body = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    assert response_start["status"] == 413
    assert json.loads(response_body)["error"] == "model_pack_too_large"
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


def test_stage_upload_maps_staging_root_enospc_to_507(monkeypatch) -> None:
    closed = False

    class UploadFile:
        def close(self) -> None:
            nonlocal closed
            closed = True

    def no_staging_space(*, prefix: str) -> str:
        assert prefix == "stockpulse-model-pack-upload-"
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(model_packs.tempfile, "mkdtemp", no_staging_space)
    upload = SimpleNamespace(
        filename="test.modelpack",
        file=UploadFile(),
    )

    with pytest.raises(HTTPException) as error:
        model_packs._stage_upload(upload)

    assert error.value.status_code == 507
    assert error.value.detail["error"] == "insufficient_disk_space"
    assert closed is True


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
            "activated": True,
            "selected_primary": False,
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


def test_desktop_activation_reuses_server_snapshot_without_accepting_a_target_url(
    monkeypatch,
) -> None:
    service = _ModelPackService()
    client = _client(service)
    attestation = _desktop_attestation(monkeypatch, nonce="4" * 32)

    response = client.post(
        "/model-packs/desktop-activations",
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

    assert response.status_code == 200
    assert response.json()["model_id"] == "licensed/finance:q4"
    assert service.desktop_activations[0][0] == "local-model-service"
    assert "url" not in str(service.desktop_activations[0][1]).lower()

    schema = client.get("/openapi.json").json()
    request_schema = schema["paths"]["/model-packs/desktop-activations"]["post"][
        "requestBody"
    ]["content"]["application/json"]["schema"]
    component = schema["components"]["schemas"][request_schema["$ref"].split("/")[-1]]
    assert "url" not in str(component).lower()


def test_desktop_activation_preserves_portable_non_ascii_display_boundaries(
    monkeypatch,
) -> None:
    service = _ModelPackService()
    client = _client(service)
    display_name = "\u00a0Licensed Finance Q4\u00a0"
    attestation = _desktop_attestation(
        monkeypatch,
        nonce="6" * 32,
        display_name=display_name,
    )

    response = client.post(
        "/model-packs/desktop-activations",
        json={
            "model_id": "licensed/finance:q4",
            "display_name": display_name,
            "minimum_memory_gb": 16,
            "license_id": "LicenseRef-Finance",
            "expected_config_version": "config-1",
            "expected_runtime_identity": "a" * 64,
            "desktop_attestation": attestation,
        },
    )

    assert response.status_code == 200
    assert service.desktop_activations[0][1]["display_name"] == display_name


def test_desktop_activation_preserves_the_maximum_valid_model_pack_identity(
    monkeypatch,
) -> None:
    service = _ModelPackService()
    client = _client(service)
    model_id = f"{'n' * 80}/{'m' * 80}:{'t' * 80}"
    attestation = _desktop_attestation(
        monkeypatch,
        nonce="7" * 32,
        model_id=model_id,
    )

    response = client.post(
        "/model-packs/desktop-activations",
        json={
            "model_id": model_id,
            "display_name": "Licensed Finance Q4",
            "minimum_memory_gb": 16,
            "license_id": "LicenseRef-Finance",
            "expected_config_version": "config-1",
            "expected_runtime_identity": "a" * 64,
            "desktop_attestation": attestation,
        },
    )

    assert response.status_code == 200
    assert service.desktop_activations[0][1]["model_id"] == model_id


def test_desktop_activation_returns_a_stable_registration_failure(monkeypatch) -> None:
    service = _ModelPackService()
    def reject_activation(*_args, **_kwargs):
        raise ModelPackError(
            "registration_failed",
            "The model was created, but StockPulse could not register it.",
        )

    service.activate_desktop_import = reject_activation
    client = _client(service)
    attestation = _desktop_attestation(monkeypatch, nonce="5" * 32)

    response = client.post(
        "/model-packs/desktop-activations",
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

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "registration_failed"


def test_desktop_activation_rejects_forged_metadata_without_validation() -> None:
    service = _ModelPackService()
    client = _client(service)

    response = client.post(
        "/model-packs/desktop-activations",
        json={
            "model_id": "unknown/arbitrary:q4",
            "display_name": "Forged presentation",
            "minimum_memory_gb": 1,
            "license_id": "LicenseRef-Forged",
            "expected_config_version": "config-1",
            "expected_runtime_identity": "a" * 64,
            "desktop_attestation": "forged.invalid",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "desktop_attestation_invalid"
    assert service.desktop_activations == []
