# -*- coding: utf-8 -*-
"""Regression tests for the public API error envelope."""

import json
import logging
from pathlib import Path

import pytest
from fastapi import Body, FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.app import create_app
from api.middlewares.error_handler import add_error_handlers
from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.system_config import (
    SystemConfigConflictResponse,
    SystemConfigValidationErrorResponse,
)


SERVER_ERROR_SECRET_MARKERS = (
    "server-param-api-key-canary",
    "server-param-auth-canary",
    "server-details-canary",
    "server-legacy-detail-canary",
    "server-extra-payload-canary",
    "server-header-canary",
)


def _client() -> TestClient:
    app = FastAPI()
    add_error_handlers(app)

    @app.get("/structured")
    def structured() -> None:
        raise api_error(
            409,
            "duplicate_task",
            "legacy diagnostic copy",
            params={"stock_code": "600519", "existing_task_id": "task-1"},
        )

    @app.get("/legacy")
    def legacy() -> None:
        raise HTTPException(status_code=400, detail="legacy raw failure")

    @app.get("/client-structured")
    def client_structured() -> None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "config_conflict",
                "message": "Configuration changed",
                "params": {"current_config_version": "version-2"},
                "details": {"retryable": True},
            },
            headers={"Retry-After": "3"},
        )

    @app.get("/internal")
    def internal() -> None:
        raise HTTPException(status_code=500, detail="secret provider payload")

    @app.get("/internal-structured")
    def internal_structured() -> None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "provider_failure",
                "message": "provider request failed",
                "params": {
                    "api_key": "server-param-api-key-canary",
                    "authorization": "Bearer server-param-auth-canary",
                },
                "details": {"payload": "server-details-canary"},
                "detail": {"payload": "server-legacy-detail-canary"},
                "provider_body": "server-extra-payload-canary",
            },
            headers={"X-Provider-Diagnostic": "server-header-canary"},
        )

    @app.post("/validation")
    def validation(value: int = Body(..., embed=True)) -> dict[str, int]:
        return {"value": value}

    return TestClient(app, raise_server_exceptions=False)


def test_structured_error_uses_stable_envelope_and_trace_id() -> None:
    response = _client().get("/structured", headers={"X-Trace-ID": "trace-contract-1"})

    assert response.status_code == 409
    assert response.json() == {
        "error": "duplicate_task",
        "message": "legacy diagnostic copy",
        "params": {"stock_code": "600519", "existing_task_id": "task-1"},
        "details": None,
        "detail": None,
        "trace_id": "trace-contract-1",
    }
    assert response.headers["x-trace-id"] == "trace-contract-1"


def test_legacy_http_exception_is_adapted_without_using_raw_copy_as_message() -> None:
    response = _client().get("/legacy")
    payload = response.json()

    assert payload["error"] == "http_error"
    assert payload["message"] == "Request failed"
    assert payload["details"] == {"legacy_message": "legacy raw failure"}
    assert payload["detail"] == payload["details"]
    assert payload["params"] == {}
    assert payload["trace_id"]


def test_structured_client_error_preserves_public_semantics_and_headers() -> None:
    response = _client().get(
        "/client-structured",
        headers={"X-Trace-ID": "trace-client-conflict"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "error": "config_conflict",
        "message": "Configuration changed",
        "params": {"current_config_version": "version-2"},
        "details": {"retryable": True},
        "detail": {"retryable": True},
        "trace_id": "trace-client-conflict",
    }
    assert response.headers["retry-after"] == "3"


def test_internal_exception_text_is_not_returned_to_client() -> None:
    response = _client().get("/internal")
    payload = response.json()

    assert payload["error"] == "internal_error"
    assert payload["message"] == "Internal server error"
    assert payload["details"] is None
    assert payload["detail"] is None
    assert "secret provider payload" not in response.text


def test_structured_server_error_discards_all_private_payload_fields(caplog) -> None:
    caplog.set_level(logging.ERROR, logger="api.middlewares.error_handler")
    response = _client().get(
        "/internal-structured",
        headers={"X-Trace-ID": "trace-safe-server-error"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "error": "internal_error",
        "message": "Internal server error",
        "params": {},
        "details": None,
        "detail": None,
        "trace_id": "trace-safe-server-error",
    }
    assert response.headers["x-trace-id"] == "trace-safe-server-error"
    assert "x-provider-diagnostic" not in response.headers
    assert all(marker not in response.text for marker in SERVER_ERROR_SECRET_MARKERS)
    rendered_logs = "\n".join(record.getMessage() for record in caplog.records)
    assert all(marker not in rendered_logs for marker in SERVER_ERROR_SECRET_MARKERS)
    assert "trace-safe-server-error" in rendered_logs


def test_validation_error_preserves_alias_and_status() -> None:
    response = _client().post("/validation", json={"value": "not-an-integer"})
    payload = response.json()

    assert response.status_code == 422
    assert payload["error"] == "validation_error"
    assert payload["detail"] == payload["details"]
    assert payload["details"]["issues"]


@pytest.mark.parametrize(
    "model_type",
    (
        ErrorResponse,
        SystemConfigValidationErrorResponse,
        SystemConfigConflictResponse,
    ),
)
def test_error_models_accept_legacy_detail_only_input(model_type) -> None:
    model = model_type.model_validate(
        {
            "error": "conflict",
            "message": "Request conflict",
            "params": {},
            "detail": {"source": "legacy"},
        }
    )

    payload = model.model_dump()
    assert payload["details"] == {"source": "legacy"}
    assert payload["detail"] == payload["details"]


@pytest.mark.parametrize(
    "model_type",
    (
        ErrorResponse,
        SystemConfigValidationErrorResponse,
        SystemConfigConflictResponse,
    ),
)
def test_error_models_keep_details_authoritative_during_validation_and_serialization(
    model_type,
) -> None:
    model = model_type.model_validate(
        {
            "error": "conflict",
            "message": "Request conflict",
            "params": {},
            "details": {"source": "canonical"},
            "detail": {"source": "ignored"},
        }
    )
    model.detail = {"source": "assignment-cannot-diverge"}
    copied = model.model_copy(update={"detail": {"source": "copy-cannot-diverge"}})

    assert model.model_dump()["detail"] == model.model_dump()["details"]
    assert copied.model_dump()["detail"] == copied.model_dump()["details"]
    assert copied.model_dump()["details"] == {"source": "canonical"}


def _assert_deprecated_detail_schema(schemas: dict) -> None:
    for schema_name in (
        "ErrorResponse",
        "SystemConfigValidationErrorResponse",
        "SystemConfigConflictResponse",
    ):
        properties = schemas[schema_name]["properties"]
        assert "details" in properties
        assert properties["detail"]["deprecated"] is True
        assert properties["detail"]["readOnly"] is True
        assert "major" in properties["detail"]["description"].lower()


def test_runtime_error_schemas_publish_deprecated_read_only_detail_alias() -> None:
    _assert_deprecated_detail_schema(create_app().openapi()["components"]["schemas"])


def test_static_openapi_error_schemas_publish_deprecated_read_only_detail_alias() -> None:
    static_spec_path = Path(__file__).resolve().parents[1] / "docs" / "architecture" / "api_spec.json"
    static_schemas = json.loads(static_spec_path.read_text(encoding="utf-8"))["components"]["schemas"]

    _assert_deprecated_detail_schema(static_schemas)
