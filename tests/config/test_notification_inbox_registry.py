# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Configuration registry contract for the in-app notification inbox."""

from src.core.config_registry import build_schema_response, get_field_definition


def test_notification_inbox_limits_match_runtime_contract() -> None:
    retention = get_field_definition("NOTIFICATION_INBOX_RETENTION_DAYS")
    maximum = get_field_definition("NOTIFICATION_INBOX_MAX_ITEMS")

    assert retention["category"] == "notification"
    assert retention["data_type"] == "integer"
    assert retention["ui_control"] == "number"
    assert retention["default_value"] == "90"
    assert retention["validation"] == {"min": 1, "max": 3650}

    assert maximum["category"] == "notification"
    assert maximum["data_type"] == "integer"
    assert maximum["ui_control"] == "number"
    assert maximum["default_value"] == "500"
    assert maximum["validation"] == {"min": 10, "max": 5000}


def test_notification_inbox_limits_are_exposed_by_the_schema_entrypoint() -> None:
    schema = build_schema_response()
    notification = next(
        category
        for category in schema["categories"]
        if category["category"] == "notification"
    )

    keys = {field["key"] for field in notification["fields"]}
    assert "NOTIFICATION_INBOX_RETENTION_DAYS" in keys
    assert "NOTIFICATION_INBOX_MAX_ITEMS" in keys
