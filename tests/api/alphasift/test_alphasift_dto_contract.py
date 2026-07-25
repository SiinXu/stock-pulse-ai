"""Pydantic v2 and OpenAPI contracts for the AlphaSift route group."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient as FastAPITestClient
from pydantic import ValidationError

from api.middlewares.error_handler import add_error_handlers
from api.v1.endpoints import alphasift as alphasift_endpoint
from api.v1.schemas.alphasift import (
    AlphaSiftScreenRequest,
    AlphaSiftScreenResponse,
    AlphaSiftStatusResponse,
)
from src.services.task_queue import TaskInfo, TaskStatus as QueueTaskStatus


def _test_client() -> FastAPITestClient:
    app = FastAPI()
    add_error_handlers(app)
    app.include_router(alphasift_endpoint.router, prefix="/api/v1/alphasift")
    app.dependency_overrides[alphasift_endpoint.get_config_dep] = lambda: MagicMock()
    return FastAPITestClient(app, raise_server_exceptions=False)


def test_screen_request_preserves_defaults_aliases_and_extra_policy() -> None:
    defaults = AlphaSiftScreenRequest.model_validate({})
    legacy = AlphaSiftScreenRequest.model_validate({"max_results": 7})
    camel_case = AlphaSiftScreenRequest.model_validate({"maxResults": 8})
    with_extra = AlphaSiftScreenRequest.model_validate({"max_results": 9, "future_flag": True})

    assert defaults.model_dump() == {
        "market": "cn",
        "strategy": "dual_low",
        "max_results": 20,
    }
    assert legacy.max_results == 7
    assert camel_case.max_results == 8
    assert with_extra.model_dump() == {
        "market": "cn",
        "strategy": "dual_low",
        "max_results": 9,
    }


def test_legacy_screen_payload_keeps_request_coercion_and_extra_policy() -> None:
    service = MagicMock()
    service.screen.return_value = {
        "enabled": True,
        "candidates": [],
        "candidate_count": 0,
    }

    with patch("api.v1.endpoints.alphasift._service", return_value=service):
        response = _test_client().post(
            "/api/v1/alphasift/screen",
            json={
                "market": "cn",
                "strategy": "dual_low",
                "max_results": "7",
                "future_flag": True,
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "candidates": [],
        "candidate_count": 0,
    }
    service.screen.assert_called_once_with(
        strategy="dual_low",
        market="cn",
        max_results=7,
    )


@pytest.mark.parametrize(
    "payload",
    (
        None,
        {"max_results": ["invalid"]},
        {"max_results": 101},
    ),
)
def test_invalid_screen_payload_uses_structured_validation_error(payload: object) -> None:
    client = _test_client()

    with patch("api.v1.endpoints.alphasift._service") as service_factory:
        response = client.post("/api/v1/alphasift/screen", json=payload)

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "validation_error"
    assert body["message"] == "Request validation failed"
    assert body["details"]["issues"]
    assert body["detail"] == body["details"]
    assert body["trace_id"]
    service_factory.assert_not_called()


def test_response_boundary_preserves_known_and_extension_fields() -> None:
    payload = {
        "enabled": True,
        "available": True,
        "install_spec_is_default": True,
        "contract_version": "1",
        "version": "0.2.0",
        "strategy_count": 4,
        "adapter_capability": {"future": True},
    }
    service = MagicMock()
    service.status.return_value = payload

    with patch("api.v1.endpoints.alphasift._service", return_value=service):
        direct_payload = alphasift_endpoint.alphasift_status(config=MagicMock())
        response = _test_client().get("/api/v1/alphasift/status")

    assert direct_payload == payload
    assert response.status_code == 200
    assert response.json() == payload


def test_sync_response_rejects_coercible_core_types() -> None:
    payload = {
        "enabled": "false",
        "available": "true",
        "install_spec_is_default": 1,
    }
    with pytest.raises(ValidationError) as caught:
        AlphaSiftStatusResponse.model_validate(payload)

    error_locations = {tuple(error["loc"]) for error in caught.value.errors()}
    assert {
        ("enabled",),
        ("available",),
        ("install_spec_is_default",),
    } <= error_locations

    service = MagicMock()
    service.status.return_value = payload
    with patch("api.v1.endpoints.alphasift._service", return_value=service):
        response = _test_client().get("/api/v1/alphasift/status")

    assert response.status_code == 500
    assert response.json()["error"] == "internal_error"


def test_invalid_service_payload_fails_closed_at_response_boundary() -> None:
    with pytest.raises(ValidationError):
        AlphaSiftStatusResponse.model_validate({
            "enabled": True,
            "install_spec_is_default": True,
        })

    service = MagicMock()
    service.status.return_value = {
        "enabled": True,
        "install_spec_is_default": True,
    }
    with patch("api.v1.endpoints.alphasift._service", return_value=service):
        response = _test_client().get("/api/v1/alphasift/status")

    assert response.status_code == 500
    assert response.json()["error"] == "internal_error"


def test_task_status_preserves_minimal_nested_result_shape() -> None:
    result = {"enabled": True, "candidates": [], "candidate_count": 0}
    task = TaskInfo(
        task_id="screen-task-1",
        trace_id="screen-task-1",
        stock_code="alphasift_screen",
        status=QueueTaskStatus.COMPLETED,
        progress=100,
        message="Screening completed",
        result=result,
        report_type="alphasift_screen",
    )
    queue = MagicMock()
    queue.get_task.return_value = task

    with patch("api.v1.endpoints.alphasift.get_task_queue", return_value=queue):
        response = _test_client().get("/api/v1/alphasift/screen/tasks/screen-task-1")

    assert response.status_code == 200
    assert response.json()["result"] == result


def test_background_screen_rejects_coercible_core_types() -> None:
    task = TaskInfo(
        task_id="screen-task-background",
        trace_id="screen-task-background",
        stock_code="alphasift_screen",
        status=QueueTaskStatus.PENDING,
        message="AlphaSift screening queued",
        report_type="alphasift_screen",
    )
    queue = MagicMock()
    queue.submit_background_task.return_value = task
    service = MagicMock()
    service.screen.return_value = {
        "enabled": True,
        "candidates": [],
        "candidate_count": "0",
    }

    with (
        patch("api.v1.endpoints.alphasift.get_task_queue", return_value=queue),
        patch("api.v1.endpoints.alphasift._service", return_value=service),
    ):
        alphasift_endpoint.alphasift_start_screen_task(
            AlphaSiftScreenRequest(),
            http_request=MagicMock(),
            config=MagicMock(),
        )
        run_screen = queue.submit_background_task.call_args.args[0]
        with pytest.raises(ValidationError):
            run_screen()


def test_completed_task_rejects_coercible_core_types() -> None:
    task = TaskInfo(
        task_id="screen-task-completed",
        trace_id="screen-task-completed",
        stock_code="alphasift_screen",
        status=QueueTaskStatus.COMPLETED,
        progress=100,
        message="Screening completed",
        result={"enabled": True, "candidates": [], "candidate_count": "0"},
        report_type="alphasift_screen",
    )
    queue = MagicMock()
    queue.get_task.return_value = task

    with patch("api.v1.endpoints.alphasift.get_task_queue", return_value=queue):
        response = _test_client().get(
            "/api/v1/alphasift/screen/tasks/screen-task-completed",
        )

    assert response.status_code == 500
    assert response.json()["error"] == "internal_error"


def test_screen_response_rejects_missing_or_wrong_core_fields() -> None:
    with pytest.raises(ValidationError):
        AlphaSiftScreenResponse.model_validate({
            "enabled": True,
            "candidates": [],
        })

    with pytest.raises(ValidationError):
        AlphaSiftScreenResponse.model_validate({
            "enabled": True,
            "candidates": {},
            "candidate_count": 0,
        })


@pytest.mark.parametrize(
    "payload",
    (
        {"enabled": True, "candidates": [], "candidate_count": "0"},
        {
            "enabled": True,
            "candidates": [
                {
                    "rank": "1",
                    "code": "600519",
                    "name": "Kweichow Moutai",
                    "reason": "candidate",
                    "raw": {},
                },
            ],
            "candidate_count": 1,
        },
        {
            "enabled": True,
            "candidates": [
                {
                    "rank": 1,
                    "code": "600519",
                    "name": "Kweichow Moutai",
                    "score": "88.5",
                    "reason": "candidate",
                    "raw": {},
                },
            ],
            "candidate_count": 1,
        },
    ),
)
def test_screen_response_rejects_coercible_numeric_core_fields(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        AlphaSiftScreenResponse.model_validate(payload)


def test_alphasift_openapi_declares_the_complete_route_group() -> None:
    app = FastAPI()
    app.include_router(alphasift_endpoint.router, prefix="/api/v1/alphasift")
    schema = app.openapi()
    expected_responses = {
        ("/api/v1/alphasift/status", "get", "200"): "AlphaSiftStatusResponse",
        ("/api/v1/alphasift/strategies", "get", "200"): "AlphaSiftStrategiesResponse",
        ("/api/v1/alphasift/hotspots", "get", "200"): "AlphaSiftHotspotsResponse",
        ("/api/v1/alphasift/hotspots/{topic}", "get", "200"): "AlphaSiftHotspotDetailResponse",
        ("/api/v1/alphasift/install", "post", "200"): "AlphaSiftInstallResponse",
        ("/api/v1/alphasift/screen/tasks", "post", "202"): "AlphaSiftScreenAccepted",
        ("/api/v1/alphasift/screen/tasks/{task_id}", "get", "200"): "AlphaSiftScreenTaskStatus",
        ("/api/v1/alphasift/screen", "post", "200"): "AlphaSiftScreenResponse",
    }

    for (path, method, status), component in expected_responses.items():
        response_schema = schema["paths"][path][method]["responses"][status]["content"][
            "application/json"
        ]["schema"]
        assert response_schema["$ref"] == f"#/components/schemas/{component}"

    for path in ("/api/v1/alphasift/screen", "/api/v1/alphasift/screen/tasks"):
        request_schema = schema["paths"][path]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]
        assert request_schema["$ref"] == "#/components/schemas/AlphaSiftScreenRequest"
        validation_schema = schema["paths"][path]["post"]["responses"]["422"]["content"][
            "application/json"
        ]["schema"]
        assert validation_schema["$ref"] == "#/components/schemas/ErrorResponse"

    request_component = schema["components"]["schemas"]["AlphaSiftScreenRequest"]
    assert "max_results" in request_component["properties"]
    assert "maxResults" not in request_component["properties"]
    assert request_component["properties"]["max_results"]["default"] == 20

    for component in expected_responses.values():
        assert schema["components"]["schemas"][component]["additionalProperties"] is True
