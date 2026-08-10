# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Settings-page category lifecycle regression (visible → editable → savable → effective).

Background
----------
The Web settings page renders fields from ``GET /api/v1/system/config``
(schema + values) and persists through ``PUT /api/v1/system/config``. When a
key is present in ``.env.example`` but missing from the config registry, it can
land in the uncategorized bucket, render with the wrong control type, or vanish
entirely when the key has never been saved. Backend unit tests that mock the
save path cannot catch that contract drift.

What this module covers
-----------------------
For each settings category (base / data_source / ai_model / notification /
system / agent / backtest / indicators) a representative registered key is
exercised end-to-end against the **real** FastAPI app, **real**
``SystemConfigService`` / ``ConfigManager`` persistence, and **real** runtime
``Config`` reload:

1. Visible: key appears in GET with the expected category metadata
2. Editable: schema marks the field editable with a non-empty title/control
3. Savable: PUT with ``reload_now=True`` applies the change
4. Effective after reload: subsequent GET and ``Config.get_instance()`` agree
5. Failure: illegal values are rejected with a readable validation issue
6. Sensitive: mask token preserves the secret and keeps the display masked

Isolation policy
----------------
Only ambient process environment and filesystem location are isolated (temp
``.env`` + sqlite). The save / validate / reload circuit is **not** mocked.
Outbound network is not required; failed remote stock-index updates during app
startup are acceptable and do not affect these assertions.

CI execution
------------
- PR ``backend-gate`` selective offline tests: this file is selected when it
  changes (``tests/`` map) and is included in FULL suite when
  ``src/core/config_registry*`` or shared config infrastructure changes.
- Push-to-main ``api-real-client`` job runs ``tests/api`` with the real
  Starlette TestClient (``STOCKPULSE_TEST_THREADLESS=0``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import src.auth as auth
from api.app import create_app
from src.config import Config
from src.core.config_registry import WEB_SETTINGS_HIDDEN_FROM_UI
from src.storage import DatabaseManager
from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

CONFIG_PATH = "/api/v1/system/config"


def _reset_auth_globals() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


def _items_by_key(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["key"]: item for item in payload["items"]}


def _validation_issues(response_json: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize validation issues from the public error envelope."""
    params = response_json.get("params") or {}
    if isinstance(params, dict) and params.get("issues"):
        return list(params["issues"])
    detail = response_json.get("detail")
    if isinstance(detail, dict) and detail.get("issues"):
        return list(detail["issues"])
    details = response_json.get("details")
    if isinstance(details, dict) and details.get("issues"):
        return list(details["issues"])
    return []


@dataclass(frozen=True)
class CategoryLifecycleCase:
    """One representative key per settings category."""

    category: str
    key: str
    initial_value: str
    updated_value: str
    invalid_value: str
    """Value that must be rejected with a readable validation error."""
    expected_ui_control: str
    effective_attr: str
    """Attribute on ``Config`` after reload_now activation."""
    expected_effective: Any
    """Expected runtime value after a successful update."""


# Representative keys are intentionally non-sensitive for the happy path so
# assertions can compare display values without mask tokens. Sensitive masking
# is covered separately via TUSHARE_TOKEN.
CATEGORY_CASES: tuple[CategoryLifecycleCase, ...] = (
    CategoryLifecycleCase(
        category="base",
        key="STOCK_LIST",
        initial_value="600519,000001",
        updated_value="300750,TSLA",
        # Empty STOCK_LIST is currently accepted for non-required fields
        # (registry min_items is not enforced on empty). Newlines are rejected.
        invalid_value="600519\n000001",
        expected_ui_control="textarea",
        effective_attr="stock_list",
        expected_effective=["300750", "TSLA"],
    ),
    CategoryLifecycleCase(
        category="data_source",
        key="TENCENT_PRIORITY",
        initial_value="5",
        updated_value="7",
        invalid_value="-1",
        expected_ui_control="number",
        effective_attr="tencent_priority",
        expected_effective=7,
    ),
    CategoryLifecycleCase(
        category="ai_model",
        key="GENERATION_BACKEND",
        initial_value="litellm",
        updated_value="codex_cli",
        invalid_value="not_a_backend",
        expected_ui_control="select",
        effective_attr="generation_backend",
        expected_effective="codex_cli",
    ),
    CategoryLifecycleCase(
        category="notification",
        key="DINGTALK_STREAM_ENABLED",
        initial_value="false",
        updated_value="true",
        invalid_value="not-a-bool",
        expected_ui_control="switch",
        effective_attr="dingtalk_stream_enabled",
        expected_effective=True,
    ),
    CategoryLifecycleCase(
        category="system",
        key="LOG_LEVEL",
        initial_value="INFO",
        updated_value="DEBUG",
        invalid_value="NOT_A_LEVEL",
        expected_ui_control="select",
        effective_attr="log_level",
        expected_effective="DEBUG",
    ),
    CategoryLifecycleCase(
        category="agent",
        key="AGENT_MODE",
        initial_value="false",
        updated_value="true",
        invalid_value="not-a-bool",
        expected_ui_control="switch",
        effective_attr="agent_mode",
        expected_effective=True,
    ),
    CategoryLifecycleCase(
        category="backtest",
        key="BACKTEST_EVAL_WINDOW_DAYS",
        initial_value="10",
        updated_value="15",
        invalid_value="0",
        expected_ui_control="number",
        effective_attr="backtest_eval_window_days",
        expected_effective=15,
    ),
    CategoryLifecycleCase(
        category="indicators",
        key="INDICATOR_MACD_FAST",
        initial_value="12",
        updated_value="10",
        invalid_value="0",
        expected_ui_control="number",
        effective_attr="indicator_macd_fast",
        expected_effective=10,
    ),
)


def _seed_env_lines(cases: tuple[CategoryLifecycleCase, ...], database_path: Path) -> list[str]:
    lines = [
        f"DATABASE_PATH={database_path}",
        "ADMIN_AUTH_ENABLED=false",
        # Sensitive seed used by the mask-preservation case only.
        "TUSHARE_TOKEN=tushare-lifecycle-secret",
        "GEMINI_API_KEY=gemini-lifecycle-secret",
        # Keep MACD slow strictly above the representative fast period.
        "INDICATOR_MACD_SLOW=26",
        "INDICATOR_MACD_SIGNAL=9",
    ]
    seen: set[str] = set()
    for case in cases:
        if case.key not in seen:
            lines.append(f"{case.key}={case.initial_value}")
            seen.add(case.key)
    return lines


@pytest.fixture
def settings_client(tmp_path: Path):
    """Real FastAPI app + isolated ENV_FILE / DATABASE_PATH (no save-path mocks)."""
    _reset_auth_globals()
    env_path = tmp_path / ".env"
    database_path = tmp_path / "settings_category_lifecycle.sqlite"
    env_path.write_text(
        "\n".join(_seed_env_lines(CATEGORY_CASES, database_path)) + "\n",
        encoding="utf-8",
    )

    previous_env_file = os.environ.get("ENV_FILE")
    previous_database_path = os.environ.get("DATABASE_PATH")
    os.environ["ENV_FILE"] = str(env_path)
    os.environ["DATABASE_PATH"] = str(database_path)

    Config.reset_instance()
    DatabaseManager.reset_instance()

    with TestClient(create_app(static_dir=tmp_path / "empty-static")) as client:
        yield client, env_path

    DatabaseManager.reset_instance()
    Config.reset_instance()
    if previous_env_file is None:
        os.environ.pop("ENV_FILE", None)
    else:
        os.environ["ENV_FILE"] = previous_env_file
    if previous_database_path is None:
        os.environ.pop("DATABASE_PATH", None)
    else:
        os.environ["DATABASE_PATH"] = previous_database_path
    _reset_auth_globals()


def _get_config(client: TestClient) -> dict[str, Any]:
    response = client.get(CONFIG_PATH, params={"include_schema": "true"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("config_version")
    assert payload.get("mask_token")
    assert isinstance(payload.get("items"), list)
    return payload


def _assert_visible_and_editable(item: dict[str, Any], case: CategoryLifecycleCase) -> None:
    assert case.key not in WEB_SETTINGS_HIDDEN_FROM_UI, (
        f"{case.key} is hidden from the Web settings UI"
    )
    schema = item.get("schema")
    assert isinstance(schema, dict), (
        f"{case.key} missing schema on GET (settings page cannot render metadata)"
    )
    assert schema.get("category") == case.category, (
        f"{case.key} category drift: expected {case.category!r}, got {schema.get('category')!r}"
    )
    assert schema.get("is_editable") is True, f"{case.key} is not editable"
    assert (schema.get("title") or "").strip(), f"{case.key} missing title"
    assert schema.get("ui_control") == case.expected_ui_control, (
        f"{case.key} ui_control drift: expected {case.expected_ui_control!r}, "
        f"got {schema.get('ui_control')!r}"
    )
    assert schema.get("is_sensitive") is False


@pytest.mark.parametrize("case", CATEGORY_CASES, ids=lambda c: f"{c.category}:{c.key}")
def test_settings_category_key_visible_editable_savable_effective(
    settings_client,
    case: CategoryLifecycleCase,
) -> None:
    """Each category representative key survives the full settings lifecycle."""
    client, env_path = settings_client

    before = _get_config(client)
    item_map = _items_by_key(before)
    assert case.key in item_map, (
        f"{case.key} not returned by GET /system/config — settings page cannot show it "
        f"(registered keys ∪ saved keys contract broken for category {case.category})"
    )
    item = item_map[case.key]
    _assert_visible_and_editable(item, case)
    assert str(item["value"]) == case.initial_value

    update = client.put(
        CONFIG_PATH,
        json={
            "config_version": before["config_version"],
            "mask_token": before["mask_token"],
            "reload_now": True,
            "items": [{"key": case.key, "value": case.updated_value}],
        },
    )
    assert update.status_code == 200, update.text
    body = update.json()
    assert body.get("success") is True
    assert body.get("reload_triggered") is True
    assert case.key in body.get("updated_keys", [])
    assert body.get("applied_count", 0) >= 1

    after = _get_config(client)
    after_item = _items_by_key(after)[case.key]
    _assert_visible_and_editable(after_item, case)
    assert str(after_item["value"]) == case.updated_value
    assert after_item.get("is_masked") is False

    env_text = env_path.read_text(encoding="utf-8")
    assert f"{case.key}={case.updated_value}" in env_text, (
        f"{case.key} was not persisted to ENV_FILE after PUT"
    )

    runtime = Config.get_instance()
    effective = getattr(runtime, case.effective_attr, "MISSING_ATTR")
    assert effective != "MISSING_ATTR", (
        f"Config has no attribute {case.effective_attr!r} for {case.key}"
    )
    assert effective == case.expected_effective, (
        f"Runtime effective value mismatch for {case.key}: "
        f"expected {case.expected_effective!r}, got {effective!r}"
    )


@pytest.mark.parametrize("case", CATEGORY_CASES, ids=lambda c: f"{c.category}:{c.key}")
def test_settings_category_key_rejects_illegal_value_with_readable_error(
    settings_client,
    case: CategoryLifecycleCase,
) -> None:
    """Illegal values must fail closed with a readable issue and leave config unchanged."""
    client, env_path = settings_client

    before = _get_config(client)
    before_item = _items_by_key(before)[case.key]
    before_value = str(before_item["value"])
    before_env = env_path.read_text(encoding="utf-8")
    before_effective = getattr(Config.get_instance(), case.effective_attr)

    response = client.put(
        CONFIG_PATH,
        json={
            "config_version": before["config_version"],
            "mask_token": before["mask_token"],
            "reload_now": True,
            "items": [{"key": case.key, "value": case.invalid_value}],
        },
    )
    assert response.status_code == 400, response.text
    payload = response.json()
    assert payload.get("error") == "validation_failed"
    assert payload.get("message"), "validation failure must include a human-readable message"
    issues = _validation_issues(payload)
    assert issues, f"expected validation issues for {case.key}, got {payload}"
    matching = [issue for issue in issues if issue.get("key") == case.key]
    assert matching, f"no issue attached to {case.key}: {issues}"
    for issue in matching:
        assert issue.get("severity") == "error"
        assert (issue.get("message") or "").strip(), f"issue for {case.key} lacks message: {issue}"

    # Persistence and runtime must be unchanged after rejection.
    after = _get_config(client)
    after_item = _items_by_key(after)[case.key]
    assert str(after_item["value"]) == before_value
    assert env_path.read_text(encoding="utf-8") == before_env
    assert getattr(Config.get_instance(), case.effective_attr) == before_effective
    assert after["config_version"] == before["config_version"]


def test_sensitive_value_remains_masked_and_is_not_cleared_on_mask_save(
    settings_client,
) -> None:
    """Saving a masked secret must not clear or expose the stored credential."""
    client, env_path = settings_client
    secret_key = "TUSHARE_TOKEN"
    secret_value = "tushare-lifecycle-secret"

    before = _get_config(client)
    item = _items_by_key(before)[secret_key]
    schema = item.get("schema") or {}
    assert schema.get("category") == "data_source"
    assert schema.get("is_sensitive") is True
    assert schema.get("is_editable") is True
    assert schema.get("ui_control") == "password"
    assert item["is_masked"] is True
    assert item["raw_value_exists"] is True
    assert item["value"] == before["mask_token"]
    assert secret_value not in str(before)

    response = client.put(
        CONFIG_PATH,
        json={
            "config_version": before["config_version"],
            "mask_token": before["mask_token"],
            "reload_now": True,
            "items": [{"key": secret_key, "value": before["mask_token"]}],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("success") is True
    assert body.get("skipped_masked_count", 0) >= 1
    assert secret_key not in body.get("updated_keys", [])

    after = _get_config(client)
    after_item = _items_by_key(after)[secret_key]
    assert after_item["is_masked"] is True
    assert after_item["raw_value_exists"] is True
    assert after_item["value"] == after["mask_token"]
    assert secret_value not in str(after)
    assert secret_value not in response.text

    env_text = env_path.read_text(encoding="utf-8")
    assert f"{secret_key}={secret_value}" in env_text
    assert Config.get_instance().tushare_token == secret_value


def test_all_declared_settings_categories_have_lifecycle_coverage() -> None:
    """Guard against dropping a category from the representative matrix."""
    expected = {
        "base",
        "data_source",
        "ai_model",
        "notification",
        "system",
        "agent",
        "backtest",
        "indicators",
    }
    covered = {case.category for case in CATEGORY_CASES}
    assert covered == expected, f"category coverage drift: {sorted(expected ^ covered)}"
    # One representative key per category keeps the matrix intentional.
    by_category: dict[str, list[str]] = {}
    for case in CATEGORY_CASES:
        by_category.setdefault(case.category, []).append(case.key)
    for category, keys in by_category.items():
        assert len(keys) == 1, f"{category} has multiple representatives: {keys}"
