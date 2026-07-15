# -*- coding: utf-8 -*-
"""Tests for the stable API error envelope."""

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.middlewares.error_handler import add_error_handlers
from api.v1.errors import api_error, error_body, error_json_response


def test_error_body_omits_empty_detail() -> None:
    assert error_body("validation_error", "bad input") == {
        "error": "validation_error",
        "message": "bad input",
        "params": {},
        "details": {},
    }


def test_api_error_uses_standard_detail_shape() -> None:
    exc = api_error(404, "not_found", "missing", detail={"id": 1})

    assert isinstance(exc, HTTPException)
    assert exc.status_code == 404
    assert exc.detail == {
        "error": "not_found",
        "message": "missing",
        "params": {},
        "details": {"id": 1},
    }


def test_error_json_response_uses_standard_content() -> None:
    response = error_json_response(409, "conflict", "already exists")

    assert response.status_code == 409
    assert response.body == (
        b'{"error":"conflict","message":"already exists","params":{},"details":{}}'
    )


def _error_test_client() -> TestClient:
    app = FastAPI()

    @app.get("/legacy")
    def legacy_error() -> None:
        raise HTTPException(status_code=400, detail="legacy raw diagnostic")

    @app.get("/structured")
    def structured_error() -> None:
        raise api_error(
            400,
            "invalid_password",
            "diagnostic fallback",
            params={"attempts": 1},
            details={"reason": "mismatch"},
        )

    @app.get("/leaky-internal")
    def leaky_internal() -> None:
        raise api_error(500, "internal_error", "database password=super-secret")

    @app.get("/known-internal")
    def known_internal() -> None:
        raise api_error(
            500,
            "agent_request_failed",
            "provider token=super-secret",
            params={"unsafe": "super-secret"},
            details={"debug": "super-secret"},
        )

    @app.get("/invalid-internal-code")
    def invalid_internal_code() -> None:
        raise api_error(500, "Invalid Internal Code", "token=super-secret")

    @app.get("/unhandled")
    def unhandled_error() -> None:
        raise RuntimeError("token=super-secret")

    add_error_handlers(app)
    return TestClient(app, raise_server_exceptions=False)


def test_handlers_adapt_legacy_strings_without_using_them_as_primary_message() -> None:
    response = _error_test_client().get(
        "/legacy",
        headers={"X-Request-ID": "trace-legacy"},
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": "legacy_http_error",
        "message": "Request failed",
        "params": {},
        "details": {"legacy_message": "legacy raw diagnostic"},
        "trace_id": "trace-legacy",
    }
    assert response.headers["X-Trace-ID"] == "trace-legacy"


def test_handlers_preserve_structured_code_params_and_details() -> None:
    response = _error_test_client().get("/structured")
    payload = response.json()

    assert payload["error"] == "invalid_password"
    assert payload["message"] == "diagnostic fallback"
    assert payload["params"] == {"attempts": 1}
    assert payload["details"] == {"reason": "mismatch"}
    assert payload["trace_id"]


def test_handlers_never_expose_internal_exception_text() -> None:
    client = _error_test_client()

    for path in ("/leaky-internal", "/invalid-internal-code", "/unhandled"):
        response = client.get(path)
        assert response.status_code == 500
        payload = response.json()
        assert payload["error"] == "internal_error"
        assert payload["message"] == "Internal server error"
        assert payload["details"] == {}
        assert "super-secret" not in response.text
        assert payload["trace_id"]


def test_handlers_preserve_valid_structured_500_code_while_redacting_diagnostics() -> None:
    response = _error_test_client().get("/known-internal")

    assert response.status_code == 500
    payload = response.json()
    assert payload["error"] == "agent_request_failed"
    assert payload["message"] == "Internal server error"
    assert payload["params"] == {}
    assert payload["details"] == {}
    assert payload["trace_id"]
    assert "super-secret" not in response.text
