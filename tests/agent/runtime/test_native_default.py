# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Guards for the Native-default Agent Runtime decision (ADR-002).

The experimental PydanticAI runtime is reinstated as an optional asset
(Continue Experimental), while Native stays the permanent default and the
default dependency manifests stay PydanticAI-free.
"""

from pathlib import Path

import pytest
import yaml

from src.agent import factory
from src.agent.runtime.native_adapter import NativeRuntimeAdapter


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_REINSTATED_EXPERIMENTAL_ASSETS = (
    "requirements-pydanticai.txt",
    "src/agent/runtime/pydantic_ai_adapter.py",
    "src/agent/runtime/pydantic_ai_toolset.py",
)


@pytest.mark.parametrize("relative_path", _REINSTATED_EXPERIMENTAL_ASSETS)
def test_experimental_runtime_asset_is_present(relative_path):
    assert (_REPOSITORY_ROOT / relative_path).exists()


def test_default_dependency_manifests_do_not_include_pydantic_ai():
    # Continue Experimental constraint: the default install must keep working
    # with zero PydanticAI dependency; only requirements-pydanticai.txt may
    # reference it.
    manifests = (
        _REPOSITORY_ROOT / "requirements.txt",
        _REPOSITORY_ROOT / ".github" / "requirements-ci.txt",
        _REPOSITORY_ROOT / "pyproject.toml",
        _REPOSITORY_ROOT / "setup.cfg",
    )

    for manifest in manifests:
        normalized = manifest.read_text(encoding="utf-8").lower().replace("_", "-")
        assert "pydantic-ai" not in normalized


def test_factory_default_runtime_is_native():
    runtime = factory.build_agent_runtime(config=object())

    assert isinstance(runtime, NativeRuntimeAdapter)
    assert runtime.name == "native"


def test_ci_keeps_both_runtime_gates():
    workflow_path = _REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    assert "backend-gate" in workflow["jobs"]
    assert "pydanticai-installed" in workflow["jobs"]
