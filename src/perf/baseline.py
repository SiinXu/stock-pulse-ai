# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Baseline load / write / compare for offline key-path performance reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

SCHEMA_VERSION = "perf-baseline-v1"
DEFAULT_REGRESSION_RATIO = 2.5


def load_baseline(path: Path) -> Dict[str, Any]:
    """Load a committed baseline JSON document."""
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"baseline must be a JSON object: {path}")
    return data


def write_baseline(path: Path, report: Mapping[str, Any]) -> None:
    """Write a baseline document with stable key ordering."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "workloads": _canonical_workloads(report.get("workloads") or []),
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _canonical_workloads(workloads: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in workloads:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or "")
        if not name:
            continue
        rows.append(
            {
                "name": name,
                "category": str(item.get("category") or ""),
                "iterations": int(item.get("iterations") or 1),
                "duration_ms": round(float(item.get("duration_ms") or 0.0), 3),
                "ops_per_sec": round(float(item.get("ops_per_sec") or 0.0), 3),
                "notes": str(item.get("notes") or ""),
            }
        )
    rows.sort(key=lambda row: row["name"])
    return rows


def compare_to_baseline(
    report: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    regression_ratio: float = DEFAULT_REGRESSION_RATIO,
) -> Dict[str, Any]:
    """Compare a fresh report to a baseline."""
    ratio = max(1.0, float(regression_ratio))
    base_map = {
        str(item["name"]): item
        for item in (baseline.get("workloads") or [])
        if isinstance(item, Mapping) and item.get("name")
    }
    report_map = {
        str(item["name"]): item
        for item in (report.get("workloads") or [])
        if isinstance(item, Mapping) and item.get("name")
    }

    comparisons: List[Dict[str, Any]] = []
    regressions: List[str] = []
    for name in sorted(set(base_map) | set(report_map)):
        base = base_map.get(name)
        current = report_map.get(name)
        if base is None:
            comparisons.append(
                {
                    "name": name,
                    "status": "new",
                    "baseline_ms": None,
                    "current_ms": float(current.get("duration_ms") or 0.0) if current else None,
                    "ratio": None,
                }
            )
            continue
        if current is None:
            comparisons.append(
                {
                    "name": name,
                    "status": "missing",
                    "baseline_ms": float(base.get("duration_ms") or 0.0),
                    "current_ms": None,
                    "ratio": None,
                }
            )
            continue
        base_ms = max(0.0, float(base.get("duration_ms") or 0.0))
        current_ms = max(0.0, float(current.get("duration_ms") or 0.0))
        observed_ratio = (current_ms / base_ms) if base_ms > 0 else None
        status = "ok"
        if base_ms > 0 and current_ms > base_ms * ratio:
            status = "regressed"
            regressions.append(name)
        elif base_ms > 0 and current_ms < base_ms / ratio:
            status = "improved"
        comparisons.append(
            {
                "name": name,
                "status": status,
                "baseline_ms": round(base_ms, 3),
                "current_ms": round(current_ms, 3),
                "ratio": round(observed_ratio, 3) if observed_ratio is not None else None,
                "threshold_ratio": ratio,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "regression_ratio": ratio,
        "regressed": regressions,
        "ok": len(regressions) == 0,
        "comparisons": comparisons,
    }


def render_markdown_report(
    report: Mapping[str, Any],
    *,
    comparison: Optional[Mapping[str, Any]] = None,
) -> str:
    """Render a short markdown summary for local/CI logs."""
    lines = [
        "# Performance baseline report",
        "",
        f"- schema: `{report.get('schema_version') or SCHEMA_VERSION}`",
        "",
        "| Workload | Category | Iterations | Duration (ms) | Ops/s |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for item in report.get("workloads") or []:
        if not isinstance(item, Mapping):
            continue
        lines.append(
            "| {name} | {category} | {iterations} | {duration_ms:.3f} | {ops_per_sec:.3f} |".format(
                name=item.get("name") or "",
                category=item.get("category") or "",
                iterations=int(item.get("iterations") or 1),
                duration_ms=float(item.get("duration_ms") or 0.0),
                ops_per_sec=float(item.get("ops_per_sec") or 0.0),
            )
        )
    if comparison is not None:
        lines.extend(
            [
                "",
                "## Baseline comparison",
                "",
                f"- regression ratio threshold: `{comparison.get('regression_ratio')}`",
                f"- ok: `{comparison.get('ok')}`",
                f"- regressed: `{', '.join(comparison.get('regressed') or []) or '(none)'}`",
                "",
                "| Workload | Status | Baseline (ms) | Current (ms) | Ratio |",
                "| --- | --- | ---: | ---: | ---: |",
            ]
        )
        for row in comparison.get("comparisons") or []:
            if not isinstance(row, Mapping):
                continue
            lines.append(
                "| {name} | {status} | {baseline} | {current} | {ratio} |".format(
                    name=row.get("name") or "",
                    status=row.get("status") or "",
                    baseline=_fmt_optional(row.get("baseline_ms")),
                    current=_fmt_optional(row.get("current_ms")),
                    ratio=_fmt_optional(row.get("ratio")),
                )
            )
    lines.append("")
    return "\n".join(lines)


def _fmt_optional(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return str(value)
