# -*- coding: utf-8 -*-
"""Regression tests for the legacy facade import ratchet."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from scripts.check_legacy_facade_imports import (
    BASELINE_VERSION,
    LEGACY_FACADES,
    collect_violations,
    main,
)


def test_legacy_facade_catalog_includes_notification_sender_shims():
    """Notification sender package and leaf facades are guarded."""

    assert "src.notification_sender" in LEGACY_FACADES
    assert (
        LEGACY_FACADES["src.notification_sender"]
        == "src.notification_parts.senders"
    )
    assert (
        LEGACY_FACADES["src.notification_sender.email_sender"]
        == "src.notification_parts.senders.email_sender"
    )


def test_new_notification_sender_facade_import_is_rejected(tmp_path: Path):
    """A production importer outside the allowlist fails the checker."""

    root = tmp_path
    (root / "src").mkdir()
    (root / "src" / "notification_parts").mkdir()
    (root / "src" / "notification_parts" / "senders").mkdir()
    (root / "src" / "notification_parts" / "senders" / "email_sender.py").write_text(
        "class EmailSender:\n    pass\n",
        encoding="utf-8",
    )
    (root / "src" / "notification_sender").mkdir()
    (root / "src" / "notification_sender" / "__init__.py").write_text(
        "from .email_sender import EmailSender\n",
        encoding="utf-8",
    )
    (root / "src" / "notification_sender" / "email_sender.py").write_text(
        "from src.notification_parts.senders.email_sender import EmailSender\n",
        encoding="utf-8",
    )
    (root / "scripts").mkdir()
    baseline = {
        "version": BASELINE_VERSION,
        "facades": {
            "src.notification_sender": ["src/notification.py"],
            "src.notification_sender.email_sender": [],
        },
    }
    baseline_path = root / "scripts" / "legacy_facade_import_baseline.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

    (root / "src" / "notification.py").write_text(
        "from src.notification_sender import EmailSender\n",
        encoding="utf-8",
    )
    assert collect_violations(root, baseline_path) == []

    (root / "src" / "new_caller.py").write_text(
        "from src.notification_sender.email_sender import EmailSender\n",
        encoding="utf-8",
    )
    violations = collect_violations(root, baseline_path)
    assert any(
        item.path == "src/new_caller.py"
        and item.facade == "src.notification_sender.email_sender"
        for item in violations
    )


def test_checker_self_test_cli_passes():
    """The built-in --self-test path stays green after nested facade support."""

    assert main(["--self-test"]) == 0
