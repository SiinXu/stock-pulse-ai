# -*- coding: utf-8 -*-
"""Regression tests for the public API error envelope."""

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.middlewares.error_handler import add_error_handlers
from api.v1.errors import api_error


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

    @app.get("/internal")
    def internal() -> None:
        raise HTTPException(status_code=500, detail="secret provider payload")

    return TestClient(app, raise_server_exceptions=False)


def test_structured_error_uses_stable_envelope_and_trace_id() -> None:
    response = _client().get("/structured", headers={"X-Trace-ID": "trace-contract-1"})

    assert response.status_code == 409
    assert response.json() == {
        "error": "duplicate_task",
        "message": "legacy diagnostic copy",
        "params": {"stock_code": "600519", "existing_task_id": "task-1"},
        "details": None,
        "trace_id": "trace-contract-1",
    }
    assert response.headers["x-trace-id"] == "trace-contract-1"


def test_legacy_http_exception_is_adapted_without_using_raw_copy_as_message() -> None:
    response = _client().get("/legacy")
    payload = response.json()

    assert payload["error"] == "http_error"
    assert payload["message"] == "Request failed"
    assert payload["details"] == {"legacy_message": "legacy raw failure"}
    assert payload["params"] == {}
    assert payload["trace_id"]


def test_internal_exception_text_is_not_returned_to_client() -> None:
    response = _client().get("/internal")
    payload = response.json()

    assert payload["error"] == "internal_error"
    assert payload["message"] == "Internal server error"
    assert payload["details"] is None
    assert "secret provider payload" not in response.text
