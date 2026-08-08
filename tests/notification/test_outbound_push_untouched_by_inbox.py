# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Regression: inbox module must not import or patch outbound push senders."""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
INBOX_PATHS = (
    REPO_ROOT / "src/services/notification_inbox_service.py",
    REPO_ROOT / "src/repositories/notification_inbox_repo.py",
    REPO_ROOT / "api/v1/endpoints/notification_inbox.py",
)
FORBIDDEN_IMPORT_PREFIXES = (
    "src.notification",
    "src.notification_sender",
    "src.services.alert_service",
    "src.services.event_alerts",
    "src.services.alert_worker",
    "src.services.scheduled_task_service",
)
FORBIDDEN_NAMES = {
    "NotificationService",
    "send_notification",
    "AlertService",
    "ScheduledTaskService",
}


def test_inbox_modules_do_not_import_outbound_push_stack() -> None:
    for path in INBOX_PATHS:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(FORBIDDEN_IMPORT_PREFIXES), path
                    assert alias.name.split(".")[-1] not in FORBIDDEN_NAMES, path
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not module.startswith(FORBIDDEN_IMPORT_PREFIXES), (
                    f"{path} imports forbidden module {module}"
                )
                for alias in node.names:
                    assert alias.name not in FORBIDDEN_NAMES, (
                        f"{path} imports forbidden name {alias.name} from {module}"
                    )
