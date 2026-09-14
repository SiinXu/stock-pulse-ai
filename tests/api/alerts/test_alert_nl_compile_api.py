# -*- coding: utf-8 -*-
"""Real HTTP tests for POST /api/v1/alerts/rules/compile-nl IR exposure."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

import src.auth as auth
from src.api.app import create_app
from src.config import Config
from src.storage import DatabaseManager


COMPILE_NL_PATH = "/api/v1/alerts/rules/compile-nl"


def _reset_auth_globals() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


def _write_env(path: Path, *, db_path: Path, auth_enabled: bool) -> None:
    path.write_text(
        "\n".join(
            [
                "STOCK_LIST=600519",
                "GEMINI_API_KEY=test",
                f"ADMIN_AUTH_ENABLED={'true' if auth_enabled else 'false'}",
                f"DATABASE_PATH={db_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.fixture()
def compile_nl_client(tmp_path, monkeypatch):
    old_env = dict(os.environ)
    env_path = tmp_path / ".env"
    db_path = tmp_path / "alert_nl_compile.db"
    static_dir = tmp_path / "empty-static"
    static_dir.mkdir()
    _write_env(env_path, db_path=db_path, auth_enabled=False)
    monkeypatch.setenv("ENV_FILE", str(env_path))
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("ADMIN_AUTH_ENABLED", "false")
    os.environ["ENV_FILE"] = str(env_path)
    os.environ["DATABASE_PATH"] = str(db_path)
    os.environ["ADMIN_AUTH_ENABLED"] = "false"
    _reset_auth_globals()
    Config.reset_instance()
    DatabaseManager.reset_instance()
    app = create_app(static_dir=static_dir)
    with TestClient(app) as client:
        try:
            yield client
        finally:
            DatabaseManager.reset_instance()
            Config.reset_instance()
            _reset_auth_globals()
            os.environ.clear()
            os.environ.update(old_env)


def _compile(client: TestClient, payload, **kwargs):
    return client.post(COMPILE_NL_PATH, json=payload, **kwargs)


def _assert_no_compile_side_effects(client: TestClient, cookies=None) -> None:
    request_kwargs = {} if cookies is None else {"cookies": cookies}
    rules = client.get("/api/v1/alerts/rules", **request_kwargs)
    assert rules.status_code == 200, rules.text
    assert rules.json()["total"] == 0
    assert rules.json()["items"] == []

    triggers = client.get("/api/v1/alerts/triggers", **request_kwargs)
    assert triggers.status_code == 200, triggers.text
    assert triggers.json()["total"] == 0

    notifications = client.get("/api/v1/alerts/notifications", **request_kwargs)
    assert notifications.status_code == 200, notifications.text
    assert notifications.json()["total"] == 0

    history = client.get("/api/v1/history", **request_kwargs)
    assert history.status_code == 200, history.text
    assert history.json()["total"] == 0
    assert history.json()["items"] == []


def test_compile_nl_success_returns_ir_fields_and_cooldown(compile_nl_client) -> None:
    response = _compile(
        compile_nl_client,
        {"text": "AAPL price above 200 cooldown 30 minutes"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["outcome"] == "success"
    assert payload["ir"] == {
        "symbol": "AAPL",
        "metric": "price_cross",
        "comparator": "above",
        "threshold": 200.0,
        "cooldown": 1800,
    }
    assert payload["rule"]["alert_type"] == "price_cross"
    assert payload["rule"]["parameters"]["price"] == 200.0
    assert payload["rule"]["cooldown_policy"] == {"cooldown_seconds": 1800}
    assert payload["rule"]["enabled"] is False
    assert payload["rule"]["source"] == "nl_compiler"
    _assert_no_compile_side_effects(compile_nl_client)


def test_compile_nl_success_without_cooldown_keeps_null_ir_cooldown(compile_nl_client) -> None:
    response = _compile(compile_nl_client, {"text": "AAPL price above 200"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["outcome"] == "success"
    assert payload["ir"] == {
        "symbol": "AAPL",
        "metric": "price_cross",
        "comparator": "above",
        "threshold": 200.0,
        "cooldown": None,
    }
    assert "cooldown_policy" not in payload["rule"]
    assert payload["rule"]["enabled"] is False
    assert payload["rule"]["source"] == "nl_compiler"
    _assert_no_compile_side_effects(compile_nl_client)


def test_compile_nl_omitted_default_enabled_stays_disabled(compile_nl_client) -> None:
    response = _compile(compile_nl_client, {"text": "AAPL price above 200"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["outcome"] == "success"
    assert payload["rule"]["enabled"] is False
    assert payload["rule"]["source"] == "nl_compiler"
    _assert_no_compile_side_effects(compile_nl_client)


def test_compile_nl_explicit_default_enabled_true_opts_in(compile_nl_client) -> None:
    response = _compile(
        compile_nl_client,
        {"text": "AAPL price above 200", "default_enabled": True},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["outcome"] == "success"
    assert payload["rule"]["enabled"] is True
    assert payload["rule"]["source"] == "nl_compiler"
    _assert_no_compile_side_effects(compile_nl_client)


def test_compile_nl_phrase_without_flag_does_not_set_auto_analysis(compile_nl_client) -> None:
    response = _compile(compile_nl_client, {"text": "600519 财报公告触发深度分析"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["outcome"] == "success"
    assert payload["ir"]["symbol"] == "600519"
    assert payload["ir"]["metric"] == "corporate_event"
    policy = payload["rule"].get("notification_policy") or {}
    assert "auto_analysis" not in policy
    _assert_no_compile_side_effects(compile_nl_client)


def test_persist_compiled_rule_keeps_nl_compiler_source(compile_nl_client) -> None:
    compiled = _compile(compile_nl_client, {"text": "AAPL price above 200"})
    assert compiled.status_code == 200, compiled.text
    rule = compiled.json()["rule"]
    created = compile_nl_client.post("/api/v1/alerts/rules", json=rule)
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["source"] == "nl_compiler"
    assert body["enabled"] is False
    listed = compile_nl_client.get("/api/v1/alerts/rules")
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["source"] == "nl_compiler"
    assert listed.json()["items"][0]["enabled"] is False


@pytest.mark.parametrize(
    ("text", "clarification"),
    [
        ("price above 100", "stock_code"),
        ("茅台 股价高于 1800", "stock_code"),
        ("AAPL MSFT price above 200", "single_stock_code"),
    ],
)
def test_compile_nl_clarifies_missing_or_multiple_symbols(
    compile_nl_client, text: str, clarification: str
) -> None:
    response = _compile(compile_nl_client, {"text": text})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["outcome"] == "need_clarification"
    assert clarification in payload["clarifications"]
    assert payload["rule"] is None
    assert payload["ir"] is None
    if clarification == "single_stock_code":
        assert "AAPL" in payload["matched_symbols"]
        assert "MSFT" in payload["matched_symbols"]
    _assert_no_compile_side_effects(compile_nl_client)


def test_compile_nl_rejects_unsupported_metric(compile_nl_client) -> None:
    response = _compile(compile_nl_client, {"text": "AAPL make me rich tomorrow"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["outcome"] == "rejected"
    assert payload["rejected_reason"] == "unsupported_metric"
    assert "supported monitor metric" in payload["message"].lower()
    assert payload["rule"] is None
    assert payload["ir"] is None
    _assert_no_compile_side_effects(compile_nl_client)


def test_compile_nl_rejects_code_like_input(compile_nl_client) -> None:
    response = _compile(
        compile_nl_client,
        {"text": "import os; os.system('rm -rf /')"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["outcome"] == "rejected"
    assert payload["rejected_reason"] == "code_like_input"
    assert payload["rule"] is None
    assert payload["ir"] is None
    _assert_no_compile_side_effects(compile_nl_client)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"text": ""},
        {"text": "A" * 501},
        {"text": 123},
    ],
)
def test_compile_nl_malformed_json_body_returns_422(compile_nl_client, body) -> None:
    response = _compile(compile_nl_client, body)
    assert response.status_code == 422, response.text
    payload = response.json()
    assert payload["error"] == "validation_error"
    _assert_no_compile_side_effects(compile_nl_client)


def test_compile_nl_non_json_body_returns_422(compile_nl_client) -> None:
    response = compile_nl_client.post(
        COMPILE_NL_PATH,
        content="not-json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"] == "validation_error"
    _assert_no_compile_side_effects(compile_nl_client)


def test_compile_nl_does_not_persist_notify_or_enqueue_analysis(compile_nl_client) -> None:
    success = _compile(
        compile_nl_client,
        {
            "text": "600519 财报公告触发深度分析",
            "auto_analysis": True,
        },
    )
    assert success.status_code == 200, success.text
    payload = success.json()
    assert payload["outcome"] == "success"
    assert payload["ir"]["symbol"] == "600519"
    assert payload["ir"]["metric"] == "corporate_event"
    assert payload["rule"]["notification_policy"]["auto_analysis"] is True
    _assert_no_compile_side_effects(compile_nl_client)


def test_compile_nl_is_reachable_when_auth_disabled(compile_nl_client) -> None:
    response = _compile(compile_nl_client, {"text": "AAPL price above 200"})
    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "success"
    assert response.json()["ir"]["symbol"] == "AAPL"


def test_compile_nl_requires_session_when_auth_enabled(tmp_path, monkeypatch) -> None:
    old_env = dict(os.environ)
    env_path = tmp_path / ".env"
    db_path = tmp_path / "alert_nl_compile_auth.db"
    static_dir = tmp_path / "empty-static"
    static_dir.mkdir()
    _write_env(env_path, db_path=db_path, auth_enabled=True)
    monkeypatch.setenv("ENV_FILE", str(env_path))
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("ADMIN_AUTH_ENABLED", "true")
    os.environ["ENV_FILE"] = str(env_path)
    os.environ["DATABASE_PATH"] = str(db_path)
    os.environ["ADMIN_AUTH_ENABLED"] = "true"
    _reset_auth_globals()
    Config.reset_instance()
    DatabaseManager.reset_instance()
    try:
        with TestClient(create_app(static_dir=static_dir)) as client:
            missing = _compile(client, {"text": "AAPL price above 200"})
            invalid_cookies = {auth.COOKIE_NAME: "not-a-signed-session"}
            invalid = _compile(
                client,
                {"text": "AAPL price above 200"},
                cookies=invalid_cookies,
            )
            session = auth.create_session()
            assert session
            session_cookies = {auth.COOKIE_NAME: session}
            allowed = _compile(
                client,
                {"text": "AAPL price above 200"},
                cookies=session_cookies,
            )
            assert missing.status_code == 401, missing.text
            assert missing.json()["error"] == "unauthorized"
            assert invalid.status_code == 401, invalid.text
            assert invalid.json()["error"] == "unauthorized"
            assert allowed.status_code == 200, allowed.text
            payload = allowed.json()
            assert payload["outcome"] == "success"
            assert payload["ir"]["symbol"] == "AAPL"
            _assert_no_compile_side_effects(client, cookies=session_cookies)
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        _reset_auth_globals()
        os.environ.clear()
        os.environ.update(old_env)
