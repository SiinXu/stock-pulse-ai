# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Regressions for the bidirectional package-pair import-cycle ratchet."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_import_layers import (
    BaselineError,
    collect_violations,
    load_baseline,
    main,
    scan_pairs,
    serialize_baseline,
    write_baseline,
)


ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "scripts" / "import_layer_baseline.json"


def _write_module(root: Path, relative_path: str, source: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _write_baseline(path: Path, pairs: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        serialize_baseline([(a, b) for a, b in pairs]),
        encoding="utf-8",
    )


def test_repository_import_layer_guard() -> None:
    """Keep the checked-in production tree aligned with its baseline."""

    assert collect_violations(ROOT, BASELINE) == []


def test_detects_new_bidirectional_pair(tmp_path: Path) -> None:
    """Reject a newly introduced bidirectional package cycle."""

    _write_module(
        tmp_path,
        "src/alpha/a.py",
        "from src.beta.b import value\n",
    )
    _write_module(
        tmp_path,
        "src/beta/b.py",
        "value = 1\n",
    )
    baseline = tmp_path / "scripts" / "import_layer_baseline.json"
    _write_baseline(baseline, [])
    assert collect_violations(tmp_path, baseline) == []

    _write_module(
        tmp_path,
        "src/beta/b.py",
        "from src.alpha.a import missing\nvalue = 1\n",
    )
    violations = collect_violations(tmp_path, baseline)
    assert len(violations) == 1
    assert violations[0].rule == "new-bidirectional-pair"
    assert {violations[0].package_a, violations[0].package_b} == {
        "src.alpha",
        "src.beta",
    }


def test_write_baseline_allows_shrink_refuses_growth(tmp_path: Path) -> None:
    """--write-baseline may shrink the allowlist but must refuse growth."""

    _write_module(
        tmp_path,
        "src/alpha/a.py",
        "from src.beta.b import value\n",
    )
    _write_module(
        tmp_path,
        "src/beta/b.py",
        "from src.alpha.a import missing\nvalue = 1\n",
    )
    baseline = tmp_path / "scripts" / "import_layer_baseline.json"
    pairs = scan_pairs(tmp_path)
    assert pairs == [("src.alpha", "src.beta")]
    _write_baseline(baseline, [["src.alpha", "src.beta"]])

    # Growth: second cycle
    _write_module(
        tmp_path,
        "src/gamma/g.py",
        "from src.delta.d import value\n",
    )
    _write_module(
        tmp_path,
        "src/delta/d.py",
        "from src.gamma.g import missing\nvalue = 1\n",
    )
    assert write_baseline(tmp_path, baseline) == 1
    assert load_baseline(baseline) == [("src.alpha", "src.beta")]

    # Shrink: break first cycle only, leave second so growth still refused
    _write_module(tmp_path, "src/beta/b.py", "value = 1\n")
    assert write_baseline(tmp_path, baseline) == 1

    # Break second cycle too — pure shrink from original baseline
    _write_module(tmp_path, "src/delta/d.py", "value = 1\n")
    # Current has no pairs; original baseline had one — shrink OK
    # But wait: gamma/delta cycle still? No, we broke delta's import of gamma.
    # alpha no longer cycles. No pairs remain.
    assert scan_pairs(tmp_path) == []
    assert write_baseline(tmp_path, baseline) == 0
    assert load_baseline(baseline) == []


def test_function_body_imports_are_ignored(tmp_path: Path) -> None:
    """Lazy imports inside functions must not create package edges."""

    _write_module(
        tmp_path,
        "src/alpha/a.py",
        "def load():\n    from src.beta.b import value\n    return value\n",
    )
    _write_module(
        tmp_path,
        "src/beta/b.py",
        "def load():\n    from src.alpha.a import load as other\n    return 1\n",
    )
    assert scan_pairs(tmp_path) == []


def test_load_baseline_rejects_unsorted_pairs(tmp_path: Path) -> None:
    """Baseline pairs must be left < right and lexicographically sorted."""

    path = tmp_path / "baseline.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "pairs": [["src.b", "src.a"]],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(BaselineError, match="ordered as left < right"):
        load_baseline(path)


def test_self_test_entrypoint_passes() -> None:
    """CLI --self-test exercises the isolated regression suite."""

    assert main(["--self-test"]) == 0
