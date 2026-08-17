# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Regressions for the directed layer-import reverse-edge ratchet."""

from __future__ import annotations

from pathlib import Path

from scripts.check_layer_direction import (
    collect_violations,
    load_baseline,
    main,
    scan_reverse_edges,
    serialize_baseline,
    write_baseline,
)


ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "scripts" / "layer_direction_baseline.json"


def _write_module(root: Path, relative_path: str, source: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_repository_layer_direction_guard() -> None:
    """Keep the checked-in production tree aligned with its reverse-edge baseline."""

    assert collect_violations(ROOT, BASELINE) == []
    assert main([]) == 0


def test_detects_new_reverse_data_provider_to_services(tmp_path: Path) -> None:
    """Reject a new src.data_provider → src.services reverse import (issue #1082)."""

    _write_module(tmp_path, "src/services/svc.py", "VALUE = 1\n")
    _write_module(tmp_path, "src/data_provider/clean.py", "VALUE = 0\n")
    baseline = tmp_path / "scripts" / "layer_direction_baseline.json"
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(serialize_baseline([], hard_ceiling=0), encoding="utf-8")
    assert collect_violations(tmp_path, baseline) == []

    _write_module(
        tmp_path,
        "src/data_provider/clean.py",
        "from src.services.svc import VALUE\n",
    )
    violations = collect_violations(tmp_path, baseline)
    reverse = [item for item in violations if item.rule == "new-reverse-edge"]
    assert len(reverse) == 1
    assert reverse[0].path == "src/data_provider/clean.py"
    assert reverse[0].from_package == "src.data_provider"
    assert reverse[0].to_package == "src.services"
    # hard_ceiling=0 also reports hard-ceiling when any reverse edge exists
    assert any(item.rule == "hard-ceiling" for item in violations)


def test_detects_pipeline_to_services_reverse(tmp_path: Path) -> None:
    """pipeline.py importing services is reverse of services → pipeline."""

    _write_module(tmp_path, "src/services/svc.py", "VALUE = 1\n")
    _write_module(
        tmp_path,
        "src/core/pipeline.py",
        "from src.services.svc import VALUE\n",
    )
    baseline = tmp_path / "scripts" / "layer_direction_baseline.json"
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(serialize_baseline([], hard_ceiling=0), encoding="utf-8")
    violations = collect_violations(tmp_path, baseline)
    assert any(
        item.path == "src/core/pipeline.py" and item.to_package == "src.services"
        for item in violations
    )


def test_forward_api_to_services_is_allowed(tmp_path: Path) -> None:
    """api → services is the intended direction and must not be flagged."""

    _write_module(tmp_path, "src/services/svc.py", "VALUE = 1\n")
    _write_module(tmp_path, "api/app.py", "from src.services.svc import VALUE\n")
    edges = scan_reverse_edges(tmp_path)
    assert edges == []


def test_write_baseline_allows_shrink_refuses_growth(tmp_path: Path) -> None:
    """--write-baseline may shrink exceptions but must refuse growth."""

    _write_module(tmp_path, "src/services/svc.py", "VALUE = 1\n")
    _write_module(
        tmp_path,
        "src/data_provider/a.py",
        "from src.services.svc import VALUE\n",
    )
    baseline = tmp_path / "scripts" / "layer_direction_baseline.json"
    edges = scan_reverse_edges(tmp_path)
    assert edges == [("src/data_provider/a.py", "src.data_provider", "src.services")]
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(
        serialize_baseline(edges, hard_ceiling=len(edges)),
        encoding="utf-8",
    )

    _write_module(
        tmp_path,
        "src/data_provider/b.py",
        "from src.services.svc import VALUE\n",
    )
    assert write_baseline(tmp_path, baseline) == 1

    _write_module(tmp_path, "src/data_provider/b.py", "VALUE = 0\n")
    _write_module(tmp_path, "src/data_provider/a.py", "VALUE = 0\n")
    assert write_baseline(tmp_path, baseline) == 0
    assert load_baseline(baseline) == []


def test_baseline_hard_ceiling_matches_introduction_inventory() -> None:
    """Hard ceiling pins introduction debt; never raise it to green CI."""

    payload_edges = load_baseline(BASELINE)
    assert len(payload_edges) <= 12
