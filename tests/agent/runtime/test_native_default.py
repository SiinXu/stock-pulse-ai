# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Guards for the Native-only Agent Runtime decision."""

from pathlib import Path

import pytest
import yaml

from src.agent import factory


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_REMOVED_EXPERIMENTAL_ASSETS = (
    "requirements-pydanticai.txt",
    "src/agent/runtime/pydantic_ai_adapter.py",
    "src/agent/runtime/pydantic_ai_toolset.py",
)


@pytest.mark.parametrize("relative_path", _REMOVED_EXPERIMENTAL_ASSETS)
def test_experimental_runtime_asset_is_absent(relative_path):
    assert not (_REPOSITORY_ROOT / relative_path).exists()


def test_default_dependency_manifests_do_not_include_pydantic_ai():
    manifests = (
        _REPOSITORY_ROOT / "requirements.txt",
        _REPOSITORY_ROOT / ".github" / "requirements-ci.txt",
        _REPOSITORY_ROOT / "pyproject.toml",
        _REPOSITORY_ROOT / "setup.cfg",
    )

    for manifest in manifests:
        normalized = manifest.read_text(encoding="utf-8").lower().replace("_", "-")
        assert "pydantic-ai" not in normalized


def test_factory_has_no_runtime_selector_or_experimental_injection_seam():
    assert not hasattr(factory, "build_agent_runtime")


def test_ci_has_no_experimental_runtime_job():
    workflow_path = _REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    assert "pydanticai-installed" not in workflow["jobs"]
