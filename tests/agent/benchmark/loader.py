# -*- coding: utf-8 -*-
"""Load offline agent-eval benchmark scenarios and referenced runtime fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

BENCHMARK_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "agent_runtime" / "benchmark"
)
AGENT_RUNTIME_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "agent_runtime"
MANIFEST_PATH = BENCHMARK_FIXTURE_ROOT / "manifest.json"
BASELINE_PATH = Path(__file__).resolve().parent / "baselines" / "v0.json"

SCHEMA_VERSION = "agent-eval-benchmark-v0"
METRIC_FAMILIES = (
    "financial_task_correctness",
    "tool_usage_discipline",
    "uncertainty_honesty",
)


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_manifest() -> Dict[str, Any]:
    data = load_json(MANIFEST_PATH)
    if not isinstance(data, dict):
        raise TypeError(f"benchmark manifest must be an object: {MANIFEST_PATH}")
    return data


def load_scenario(relative_file: str) -> Dict[str, Any]:
    path = BENCHMARK_FIXTURE_ROOT / relative_file
    data = load_json(path)
    if not isinstance(data, dict):
        raise TypeError(f"scenario must be an object: {path}")
    return data


def load_source_case(relative_file: str) -> Dict[str, Any]:
    """Load a read-only AR-01 agent_runtime fixture referenced by a scenario."""
    path = AGENT_RUNTIME_ROOT / relative_file
    if not path.is_file():
        raise FileNotFoundError(f"source agent_runtime fixture missing: {path}")
    data = load_json(path)
    if not isinstance(data, dict):
        raise TypeError(f"source case must be an object: {path}")
    return data


def iter_scenarios() -> Iterable[Dict[str, Any]]:
    """Yield each scenario dict in manifest order with id normalized."""
    manifest = load_manifest()
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("benchmark manifest must declare a non-empty cases list")
    for entry in cases:
        if not isinstance(entry, Mapping):
            raise TypeError(f"manifest case entry must be an object: {entry!r}")
        relative = entry.get("file")
        if not isinstance(relative, str) or not relative.strip():
            raise ValueError(f"manifest case entry missing file: {entry!r}")
        scenario = load_scenario(relative)
        case_id = scenario.get("id") or entry.get("id")
        if case_id is None:
            raise ValueError(f"scenario missing id: {relative}")
        scenario.setdefault("id", str(case_id))
        evaluation = scenario.get("evaluation")
        if not isinstance(evaluation, Mapping):
            raise ValueError(f"scenario {case_id!r} missing evaluation object")
        for family in METRIC_FAMILIES:
            if family not in evaluation:
                raise ValueError(
                    f"scenario {case_id!r} missing evaluation family {family!r}"
                )
        source = scenario.get("source_case")
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"scenario {case_id!r} missing source_case")
        yield scenario


def list_scenario_ids() -> List[str]:
    return [str(scenario["id"]) for scenario in iter_scenarios()]


def load_baseline() -> Dict[str, Any]:
    if not BASELINE_PATH.is_file():
        raise FileNotFoundError(f"baseline score file missing: {BASELINE_PATH}")
    data = load_json(BASELINE_PATH)
    if not isinstance(data, dict):
        raise TypeError(f"baseline must be an object: {BASELINE_PATH}")
    return data
