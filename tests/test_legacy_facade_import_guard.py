# -*- coding: utf-8 -*-
"""Regression tests for the legacy facade import ratchet."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from scripts.check_legacy_facade_imports import (
    BASELINE_VERSION,
    LEGACY_FACADES,
    BaselineError,
    load_baseline,
    main,
)


def test_legacy_facade_catalog_excludes_all_retired_stage2_shims():
    """Deleted analysis-context-pack and market facades are not catalogued."""

    retired = (
        "src.analysis_context_pack_overview",
        "src.analysis_context_pack_prompt",
        "src.market_analyzer",
        "src.market_context",
        "src.market_phase_prompt",
        "src.market_phase_summary",
        "src.market_regime_prompt",
        "src.market_structure_prompt",
    )
    for name in retired:
        assert name not in LEGACY_FACADES
    leftover = {
        "version": BASELINE_VERSION,
        "facades": {
            "src.analysis_context_pack_overview": ["src/core/pipeline.py"],
        },
    }
    with tempfile.TemporaryDirectory(prefix="retired-stage2-baseline-") as tmp:
        leftover_path = Path(tmp) / "leftover.json"
        leftover_path.write_text(json.dumps(leftover), encoding="utf-8")
        try:
            load_baseline(leftover_path)
        except BaselineError as exc:
            assert "unknown facade" in str(exc)
        else:
            raise AssertionError("retired Stage 2 facade was accepted")


def test_legacy_facade_catalog_excludes_retired_notification_sender_shims():
    """The deleted notification_sender shim package is no longer catalogued."""

    assert "src.notification_sender" not in LEGACY_FACADES
    assert not any(
        name == "src.notification_sender" or name.startswith("src.notification_sender.")
        for name in LEGACY_FACADES
    )
    leftover = {
        "version": BASELINE_VERSION,
        "facades": {
            "src.notification_sender": ["src/notification.py"],
            "src.notification_sender.email_sender": [],
        },
    }
    with tempfile.TemporaryDirectory(prefix="retired-sender-baseline-") as tmp:
        leftover_path = Path(tmp) / "leftover.json"
        leftover_path.write_text(json.dumps(leftover), encoding="utf-8")
        try:
            load_baseline(leftover_path)
        except BaselineError as exc:
            assert "unknown facade" in str(exc)
        else:
            raise AssertionError("retired notification_sender facade was accepted")


def test_legacy_facade_catalog_excludes_retired_root_package_shims():
    """The removed root API, Bot, and provider packages are no longer facades."""

    for name in ("api", "bot", "data_provider"):
        assert name not in LEGACY_FACADES


def test_checker_self_test_cli_passes():
    """The built-in --self-test path stays green after catalog retirement."""

    assert main(["--self-test"]) == 0
