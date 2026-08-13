# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Regressions for the hot-path module size soft-budget ratchet."""

from __future__ import annotations

from pathlib import Path

from scripts.check_hot_path_module_size import (
    SOFT_BUDGET_LINES,
    collect_violations,
    load_baseline,
    main,
    scan_oversized,
    serialize_baseline,
    write_baseline,
)


ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "scripts" / "hot_path_module_size_baseline.json"


def _write_lines(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"x{i} = {i}" for i in range(count)) + "\n", encoding="utf-8")


def test_repository_hot_path_module_size_guard() -> None:
    """Keep the checked-in hot-path tree aligned with its size baseline."""

    assert collect_violations(ROOT, BASELINE) == []
    assert main([]) == 0


def test_soft_budget_threshold_matches_issue_guidance() -> None:
    """Soft budget is the upper end of the issue #1087 1200–1500 review band."""

    assert SOFT_BUDGET_LINES == 1500


def test_detects_new_oversized_hot_path_module(tmp_path: Path) -> None:
    """A new hot-path file over the soft budget fails closed."""

    services = tmp_path / "src" / "services"
    _write_lines(services / "ok.py", SOFT_BUDGET_LINES)
    baseline = tmp_path / "scripts" / "hot_path_module_size_baseline.json"
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(
        serialize_baseline(
            {},
            hard_ceiling_count=0,
            hard_ceiling_max_lines=0,
        ),
        encoding="utf-8",
    )
    assert collect_violations(tmp_path, baseline) == []

    _write_lines(services / "too_big.py", SOFT_BUDGET_LINES + 1)
    violations = collect_violations(tmp_path, baseline)
    assert any(
        item.rule == "new-oversized-module"
        and item.path == "src/services/too_big.py"
        for item in violations
    )


def test_detects_regrowth_of_baselined_module(tmp_path: Path) -> None:
    """Baselined path may not grow past its frozen line cap."""

    services = tmp_path / "src" / "services"
    path = services / "legacy.py"
    _write_lines(path, SOFT_BUDGET_LINES + 10)
    oversized = scan_oversized(tmp_path)
    baseline = tmp_path / "scripts" / "hot_path_module_size_baseline.json"
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(
        serialize_baseline(
            oversized,
            hard_ceiling_count=1,
            hard_ceiling_max_lines=oversized["src/services/legacy.py"],
        ),
        encoding="utf-8",
    )
    assert collect_violations(tmp_path, baseline) == []

    _write_lines(path, SOFT_BUDGET_LINES + 40)
    violations = collect_violations(tmp_path, baseline)
    assert any(item.rule == "module-grew" for item in violations)
    assert write_baseline(tmp_path, baseline) == 1


def test_write_baseline_shrinks_when_file_drops_under_budget(tmp_path: Path) -> None:
    """After a successful split under budget, --write-baseline drops the path."""

    services = tmp_path / "src" / "services"
    path = services / "legacy.py"
    _write_lines(path, SOFT_BUDGET_LINES + 5)
    oversized = scan_oversized(tmp_path)
    baseline = tmp_path / "scripts" / "hot_path_module_size_baseline.json"
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(
        serialize_baseline(
            oversized,
            hard_ceiling_count=1,
            hard_ceiling_max_lines=oversized["src/services/legacy.py"],
        ),
        encoding="utf-8",
    )

    _write_lines(path, 10)
    assert write_baseline(tmp_path, baseline) == 0
    assert load_baseline(baseline) == {}


def test_baseline_hard_ceilings_pin_introduction_inventory() -> None:
    """Hard ceilings pin introduction inventory; never raise them to green CI."""

    modules = load_baseline(BASELINE)
    assert len(modules) <= 10
    assert max(modules.values()) <= 4659
    assert all(lines > SOFT_BUDGET_LINES for lines in modules.values())
