"""FastAPI contract tests for the personal investment framework backend."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import src.auth as auth
from api.app import create_app
from src.config import Config
from src.storage import DatabaseManager


FRAMEWORK_PATHS = (
    "/api/v1/investment-framework",
    "/api/v1/investment-framework/history",
    "/api/v1/investment-framework/deactivate",
)
FRAMEWORK_SCHEMAS = (
    "InvestmentFrameworkContent",
    "InvestmentFrameworkCreateRequest",
    "InvestmentFrameworkDeactivateRequest",
    "InvestmentFrameworkDecisionBranch",
    "InvestmentFrameworkDecisionNode",
    "InvestmentFrameworkDeleteResponse",
    "InvestmentFrameworkEvaluationDimension",
    "InvestmentFrameworkHistoryItem",
    "InvestmentFrameworkHistoryResponse",
    "InvestmentFrameworkResponse",
    "InvestmentFrameworkUpdateRequest",
)


def _reset_auth_globals() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


@pytest.fixture
def client(tmp_path: Path):
    _reset_auth_globals()
    env_path = tmp_path / ".env"
    database_path = tmp_path / "investment-framework.sqlite"
    env_path.write_text(
        "\n".join(
            (
                "STOCK_LIST=600519",
                "ADMIN_AUTH_ENABLED=false",
                f"DATABASE_PATH={database_path}",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    os.environ["ENV_FILE"] = str(env_path)
    os.environ["DATABASE_PATH"] = str(database_path)
    Config.reset_instance()
    DatabaseManager.reset_instance()
    with TestClient(create_app(static_dir=tmp_path / "empty-static")) as test_client:
        yield test_client
    DatabaseManager.reset_instance()
    Config.reset_instance()
    os.environ.pop("ENV_FILE", None)
    os.environ.pop("DATABASE_PATH", None)
    _reset_auth_globals()


def _content(title: str) -> dict:
    return {
        "title": title,
        "evaluation_dimensions": [
            {
                "name": "Moat",
                "weight": 50,
                "criteria": ["Evidence supports durable pricing power"],
            }
        ],
        "risk_rules": ["Cap position size at the documented limit"],
        "tracking_criteria": ["Review material guidance changes"],
    }


def test_api_crud_history_conflict_deactivate_and_delete(client: TestClient) -> None:
    missing = client.get("/api/v1/investment-framework")
    assert missing.status_code == 404
    assert missing.json()["error"] == "investment_framework_not_found"

    created = client.post(
        "/api/v1/investment-framework",
        json={"content": _content("Initial"), "change_summary": "Initial version"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["scope"] == "local"
    assert created.json()["revision"] == 1
    assert "owner_id" not in created.json()

    duplicate = client.post(
        "/api/v1/investment-framework",
        json={"content": _content("Duplicate")},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"] == "investment_framework_already_exists"

    updated = client.put(
        "/api/v1/investment-framework",
        json={
            "expected_revision": 1,
            "content": _content("Updated"),
            "change_summary": "Update criteria",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2

    stale = client.put(
        "/api/v1/investment-framework",
        json={"expected_revision": 1, "content": _content("Stale")},
    )
    assert stale.status_code == 409
    assert stale.json()["error"] == "investment_framework_revision_conflict"
    assert stale.json()["params"]["current_revision"] == 2

    history = client.get("/api/v1/investment-framework/history")
    assert history.status_code == 200
    assert [item["version"] for item in history.json()["items"]] == [2, 1]

    deactivated = client.post(
        "/api/v1/investment-framework/deactivate",
        json={"expected_revision": 2},
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["active_version"] is None
    assert deactivated.json()["revision"] == 3
    assert client.get("/api/v1/investment-framework").json()["is_active"] is False

    stale_delete = client.delete(
        "/api/v1/investment-framework",
        params={"expected_revision": 2},
    )
    assert stale_delete.status_code == 409
    deleted = client.delete(
        "/api/v1/investment-framework",
        params={"expected_revision": 3},
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted_through_version"] == 2
    assert client.get("/api/v1/investment-framework/history").status_code == 404


def test_api_schema_is_strict_and_has_no_client_selected_account_identity(
    client: TestClient,
) -> None:
    invalid = client.post(
        "/api/v1/investment-framework",
        json={"content": _content("Initial"), "owner_id": "other-user"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"] == "validation_error"

    schema = client.get("/openapi.json").json()
    path = schema["paths"]["/api/v1/investment-framework"]
    assert set(path) >= {"get", "post", "put", "delete"}
    create_schema = schema["components"]["schemas"][
        "InvestmentFrameworkCreateRequest"
    ]
    update_schema = schema["components"]["schemas"][
        "InvestmentFrameworkUpdateRequest"
    ]
    assert create_schema["additionalProperties"] is False
    assert update_schema["additionalProperties"] is False
    assert "owner_id" not in create_schema["properties"]
    assert "user_id" not in create_schema["properties"]
    assert update_schema["properties"]["expected_revision"]["minimum"] == 1


def test_framework_api_uses_the_existing_optional_admin_session_boundary(
    client: TestClient,
) -> None:
    with patch("api.middlewares.auth.is_auth_enabled", return_value=True):
        response = client.get("/api/v1/investment-framework")
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_framework_static_api_spec_matches_runtime_contract(
    client: TestClient,
) -> None:
    static_spec_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "architecture"
        / "api_spec.json"
    )
    static_spec = json.loads(static_spec_path.read_text(encoding="utf-8"))
    runtime_spec = client.get("/openapi.json").json()

    for path in FRAMEWORK_PATHS:
        assert static_spec["paths"][path] == runtime_spec["paths"][path]
    for schema_name in FRAMEWORK_SCHEMAS:
        assert (
            static_spec["components"]["schemas"][schema_name]
            == runtime_spec["components"]["schemas"][schema_name]
        )
