# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Guards for the Native-default Agent Runtime decision (ADR-002).

The experimental PydanticAI runtime is reinstated as a test/evidence POC while
Native stays the only production assembly path and the default dependency
manifests stay PydanticAI-free.
"""

import inspect
from pathlib import Path

import pytest
import yaml

from src.agent import factory
from src.agent.runtime.native_adapter import NativeRuntimeAdapter
from src.agent.runtime.pydantic_ai_adapter import PydanticAIRuntimeAdapter


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_REINSTATED_EXPERIMENTAL_ASSETS = (
    "requirements-pydanticai.txt",
    "src/agent/runtime/pydantic_ai_adapter.py",
    "src/agent/runtime/pydantic_ai_toolset.py",
)
_LOCKED_OPTIONAL_DEPENDENCIES = frozenset(
    {
        "annotated-types",
        "anyio",
        "certifi",
        "genai-prices",
        "griffelib",
        "h11",
        "httpcore",
        "httpcore2",
        "httpx",
        "httpx2",
        "idna",
        "logfire-api",
        "opentelemetry-api",
        "pydantic",
        "pydantic-ai-slim",
        "pydantic-core",
        "pydantic-graph",
        "truststore",
        "typing-extensions",
        "typing-inspection",
    }
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


def test_experimental_runtime_is_explicit_test_evidence_construction_only():
    """No factory/config/env selector can route product traffic to the POC."""
    assert tuple(inspect.signature(factory.build_agent_runtime).parameters) == (
        "config",
        "skills",
    )

    runtime = PydanticAIRuntimeAdapter(model=object())
    assert runtime.name == "pydantic_ai_experimental"
    assert isinstance(factory.build_agent_runtime(config=object()), NativeRuntimeAdapter)


def test_optional_dependency_closure_is_complete_and_exactly_pinned():
    manifest = _REPOSITORY_ROOT / "requirements-pydanticai.txt"
    pins = {}
    for raw_line in manifest.read_text(encoding="utf-8").splitlines():
        requirement = raw_line.split("#", 1)[0].strip()
        if not requirement:
            continue
        name, separator, version = requirement.partition("==")
        assert separator == "==", requirement
        assert name and version, requirement
        normalized_name = name.strip().lower().replace("_", "-").replace(".", "-")
        assert normalized_name not in pins, normalized_name
        pins[normalized_name] = version.strip()

    assert frozenset(pins) == _LOCKED_OPTIONAL_DEPENDENCIES


def test_ci_keeps_both_runtime_gates():
    workflow_path = _REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    assert "backend-gate" in workflow["jobs"]
    assert "pydanticai-installed" in workflow["jobs"]
