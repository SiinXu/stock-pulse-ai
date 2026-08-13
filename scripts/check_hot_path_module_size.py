#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Ratcheting soft size guard for core hot-path production modules.

Issue #1087: after gravity-module splits, hot-path files re-inflate unless a
lightweight code-level budget is enforced. This guard freezes historical
oversized modules and fails closed on growth:

- Soft budget (review / new-file threshold): ``SOFT_BUDGET_LINES`` physical
  lines (``wc -l`` style). Justified from issue #1087's ~1200–1500 review band;
  1500 is the upper end so modest modules stay free of allowlisting noise.
- Extraction preference (documented, not a separate hard fail): 2000 lines —
  prefer split/extract above this; files already over it remain until cleanup.
- Per-path baseline freezes the **maximum allowed line count** for each
  currently oversized hot-path file (only decrease).
- Live oversized set must be a subset of the baseline (no new oversized files).
- Live line counts for baselined paths must be ``<=`` baseline lines.
- ``hard_ceiling_count`` and ``hard_ceiling_max_lines`` never increase; they pin
  the introduction inventory.

``--write-baseline`` may shrink recorded lines / drop retired paths and
**refuses growth**. Do not raise budgets or ceilings to green CI — split the
module instead.

Scopes (issue #1087): ``data_provider/``, ``src/services/``, ``src/agent/``,
``src/market/``.

See: docs/hot-path-module-size-ratchet.md,
https://github.com/SiinXu/stock-pulse-ai/issues/1087
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = ROOT / "scripts" / "hot_path_module_size_baseline.json"
BASELINE_VERSION = 1

SOFT_BUDGET_LINES = 1500
EXTRACTION_PREFERENCE_LINES = 2000

HOT_PATH_SCOPES: tuple[str, ...] = (
    "data_provider",
    "src/services",
    "src/agent",
    "src/market",
)


class BaselineError(ValueError):
    """Raised when the checked-in baseline is malformed."""


@dataclass(frozen=True, order=True)
class Violation:
    """One unexplained hot-path size growth."""

    rule: str
    path: str
    message: str

    def render(self) -> str:
        return f"{self.rule}: {self.path}: {self.message}"


@dataclass(frozen=True)
class ModuleSize:
    """Measured physical line count for one production module."""

    path: str
    lines: int
    scope: str


def _relative_to_root(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def count_physical_lines(path: Path) -> int:
    data = path.read_bytes()
    if not data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def iter_hot_path_modules(root: Path) -> list[ModuleSize]:
    modules: list[ModuleSize] = []
    for scope in HOT_PATH_SCOPES:
        directory = root / scope
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.py")):
            relative = _relative_to_root(root, path)
            modules.append(
                ModuleSize(
                    path=relative,
                    lines=count_physical_lines(path),
                    scope=scope,
                )
            )
    return modules


def scan_oversized(root: Path, budget: int = SOFT_BUDGET_LINES) -> dict[str, int]:
    oversized: dict[str, int] = {}
    for module in iter_hot_path_modules(root):
        if module.lines > budget:
            oversized[module.path] = module.lines
    return dict(sorted(oversized.items()))


def load_baseline(path: Path) -> dict[str, int]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BaselineError(f"baseline file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BaselineError(f"baseline is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise BaselineError("baseline root must be an object")
    if payload.get("version") != BASELINE_VERSION:
        raise BaselineError(
            f"unsupported baseline version {payload.get('version')!r}; "
            f"expected {BASELINE_VERSION}"
        )

    soft_budget = payload.get("soft_budget_lines")
    if soft_budget != SOFT_BUDGET_LINES:
        raise BaselineError(
            f"baseline.soft_budget_lines {soft_budget!r} must equal "
            f"SOFT_BUDGET_LINES={SOFT_BUDGET_LINES}; never raise the budget to "
            "green CI"
        )

    hard_ceiling_count = payload.get("hard_ceiling_count")
    hard_ceiling_max_lines = payload.get("hard_ceiling_max_lines")
    if not isinstance(hard_ceiling_count, int) or hard_ceiling_count < 0:
        raise BaselineError("baseline.hard_ceiling_count must be a non-negative int")
    if not isinstance(hard_ceiling_max_lines, int) or hard_ceiling_max_lines < 0:
        raise BaselineError(
            "baseline.hard_ceiling_max_lines must be a non-negative int"
        )

    modules_raw = payload.get("modules")
    if not isinstance(modules_raw, dict):
        raise BaselineError("baseline.modules must be an object of path → lines")

    modules: dict[str, int] = {}
    for path_key, lines in modules_raw.items():
        if not isinstance(path_key, str) or not path_key:
            raise BaselineError("baseline.modules keys must be non-empty strings")
        if not isinstance(lines, int) or lines <= SOFT_BUDGET_LINES:
            raise BaselineError(
                f"baseline.modules[{path_key!r}] must be an int > soft budget "
                f"{SOFT_BUDGET_LINES}"
            )
        if lines > hard_ceiling_max_lines:
            raise BaselineError(
                f"baseline.modules[{path_key!r}]={lines} exceeds "
                f"hard_ceiling_max_lines={hard_ceiling_max_lines}; never raise "
                "the ceiling"
            )
        modules[path_key] = lines

    if list(modules) != sorted(modules):
        raise BaselineError("baseline.modules keys must be sorted lexicographically")

    if len(modules) > hard_ceiling_count:
        raise BaselineError(
            f"baseline module count {len(modules)} exceeds hard_ceiling_count "
            f"{hard_ceiling_count}; never raise the ceiling to green CI"
        )

    declared_count = payload.get("module_count")
    if declared_count is not None and declared_count != len(modules):
        raise BaselineError(
            f"baseline.module_count {declared_count!r} does not match "
            f"len(modules)={len(modules)}"
        )
    return modules


def serialize_baseline(
    modules: Mapping[str, int],
    *,
    hard_ceiling_count: int,
    hard_ceiling_max_lines: int,
) -> str:
    ordered = {path: modules[path] for path in sorted(modules)}
    measured_max = max(ordered.values()) if ordered else 0
    if len(ordered) > hard_ceiling_count:
        raise BaselineError(
            f"refusing to serialize {len(ordered)} modules above "
            f"hard_ceiling_count {hard_ceiling_count}"
        )
    if measured_max > hard_ceiling_max_lines:
        raise BaselineError(
            f"refusing to serialize max lines {measured_max} above "
            f"hard_ceiling_max_lines {hard_ceiling_max_lines}"
        )
    payload = {
        "version": BASELINE_VERSION,
        "description": (
            "Allowlisted hot-path modules that currently exceed the soft line "
            "budget. Values are maximum permitted physical line counts (only "
            "decrease). New oversized hot-path files and growth past a path's "
            "budget are banned. Never raise soft_budget_lines, "
            "hard_ceiling_count, or hard_ceiling_max_lines to green CI — split "
            "the module instead."
        ),
        "scopes": list(HOT_PATH_SCOPES),
        "soft_budget_lines": SOFT_BUDGET_LINES,
        "extraction_preference_lines": EXTRACTION_PREFERENCE_LINES,
        "hard_ceiling_count": hard_ceiling_count,
        "hard_ceiling_max_lines": hard_ceiling_max_lines,
        "module_count": len(ordered),
        "modules": ordered,
        "cleanup_plan": [
            (
                "Prefer extracting cohesive helpers/packages when a hot-path "
                f"file exceeds {EXTRACTION_PREFERENCE_LINES} lines "
                f"(soft review budget is {SOFT_BUDGET_LINES})."
            ),
            (
                "Priority gravity modules at introduction: data_provider/base.py, "
                "src/services/run_diagnostics.py, "
                "src/services/scheduled_task_service.py, src/market/analyzer.py."
            ),
            (
                "After a successful split, re-run "
                "`python scripts/check_hot_path_module_size.py --write-baseline` "
                "to shrink recorded line caps or drop retired paths."
            ),
        ],
        "threshold_rationale": {
            "soft_budget_lines": (
                "Issue #1087 suggests encouraging review when a hot-path file "
                "exceeds ~1200–1500 lines; 1500 is the upper end of that band "
                "and matches the repository's historical gravity-module split "
                "targets without allowlisting every mid-size service module."
            ),
            "extraction_preference_lines": (
                "Issue #1087 strongly prefers extraction above ~2000 lines on "
                "the primary analyze path; cleanup work should prioritize those "
                "files first while the soft budget still ratchets all >1500 debt."
            ),
            "hard_ceilings": (
                "hard_ceiling_count and hard_ceiling_max_lines pin the measured "
                "inventory at guard introduction so CI cannot be greened by "
                "raising either limit."
            ),
        },
    }
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def _read_ceilings(path: Path) -> tuple[int, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return int(payload["hard_ceiling_count"]), int(payload["hard_ceiling_max_lines"])


def collect_violations(root: Path, baseline_path: Path) -> list[Violation]:
    baseline = load_baseline(baseline_path)
    hard_ceiling_count, hard_ceiling_max_lines = _read_ceilings(baseline_path)
    current = scan_oversized(root)
    violations: list[Violation] = []

    if len(current) > hard_ceiling_count:
        violations.append(
            Violation(
                rule="hard-ceiling-count",
                path="*",
                message=(
                    f"oversized hot-path module count {len(current)} exceeds "
                    f"hard_ceiling_count {hard_ceiling_count}; never raise the "
                    "ceiling — split modules instead"
                ),
            )
        )

    measured_max = max(current.values()) if current else 0
    if measured_max > hard_ceiling_max_lines:
        violations.append(
            Violation(
                rule="hard-ceiling-max-lines",
                path="*",
                message=(
                    f"largest hot-path module is {measured_max} lines, above "
                    f"hard_ceiling_max_lines {hard_ceiling_max_lines}; never "
                    "raise the ceiling — split the module instead"
                ),
            )
        )

    for path, lines in current.items():
        if path not in baseline:
            violations.append(
                Violation(
                    rule="new-oversized-module",
                    path=path,
                    message=(
                        f"{lines} lines exceeds soft budget "
                        f"{SOFT_BUDGET_LINES}; new oversized hot-path modules "
                        "are banned. Split the file — do not expand the baseline"
                    ),
                )
            )
            continue
        allowed = baseline[path]
        if lines > allowed:
            violations.append(
                Violation(
                    rule="module-grew",
                    path=path,
                    message=(
                        f"{lines} lines exceeds baselined max {allowed}; "
                        "re-growth after split is banned. Extract code or "
                        "reduce the file — do not raise the path budget"
                    ),
                )
            )

    return sorted(violations)


def write_baseline(root: Path, baseline_path: Path) -> int:
    current = scan_oversized(root)
    if baseline_path.is_file():
        try:
            existing = load_baseline(baseline_path)
            hard_ceiling_count, hard_ceiling_max_lines = _read_ceilings(baseline_path)
        except BaselineError as exc:
            print(
                f"[hot-path-size] ERROR: invalid-baseline: {exc}",
                file=sys.stderr,
            )
            return 1

        growth_paths = sorted(set(current) - set(existing))
        grew: list[tuple[str, int, int]] = []
        for path, lines in sorted(current.items()):
            if path in existing and lines > existing[path]:
                grew.append((path, existing[path], lines))

        if growth_paths or grew:
            for path in growth_paths:
                print(
                    f"[hot-path-size] ERROR: baseline-growth: {path}: "
                    f"{current[path]} lines is a new oversized module; "
                    "refusing --write-baseline growth",
                    file=sys.stderr,
                )
            for path, old, new in grew:
                print(
                    f"[hot-path-size] ERROR: baseline-growth: {path}: "
                    f"{new} lines > baselined {old}; refusing to raise path "
                    "budget",
                    file=sys.stderr,
                )
            return 1

        shrunk = {
            path: min(existing[path], current[path])
            for path in current
            if path in existing
        }
    else:
        shrunk = current
        hard_ceiling_count = len(current)
        hard_ceiling_max_lines = max(current.values()) if current else 0

    if len(shrunk) > hard_ceiling_count or (
        shrunk and max(shrunk.values()) > hard_ceiling_max_lines
    ):
        print(
            "[hot-path-size] ERROR: hard-ceiling violated while writing baseline",
            file=sys.stderr,
        )
        return 1

    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        baseline_path.write_text(
            serialize_baseline(
                shrunk,
                hard_ceiling_count=hard_ceiling_count,
                hard_ceiling_max_lines=hard_ceiling_max_lines,
            ),
            encoding="utf-8",
        )
    except BaselineError as exc:
        print(f"[hot-path-size] ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"[hot-path-size] wrote {len(shrunk)} oversized module(s) to "
        f"{baseline_path} (hard_ceiling_count={hard_ceiling_count}, "
        f"hard_ceiling_max_lines={hard_ceiling_max_lines})"
    )
    return 0


def run_self_tests() -> None:
    cases = 0
    with tempfile.TemporaryDirectory(prefix="hot-path-size-") as tmp:
        root = Path(tmp)
        services = root / "src" / "services"
        services.mkdir(parents=True)
        (root / "scripts").mkdir()

        big = services / "big.py"
        big.write_text(
            "\n".join(f"x{i} = {i}" for i in range(SOFT_BUDGET_LINES + 1)) + "\n"
        )
        (services / "small.py").write_text("VALUE = 1\n")

        oversized = scan_oversized(root)
        if list(oversized) != ["src/services/big.py"]:
            raise AssertionError(f"unexpected oversized: {oversized!r}")
        if oversized["src/services/big.py"] != SOFT_BUDGET_LINES + 1:
            raise AssertionError(f"bad line count: {oversized}")
        cases += 1

        baseline_path = root / "scripts" / "hot_path_module_size_baseline.json"
        baseline_path.write_text(
            serialize_baseline(
                oversized,
                hard_ceiling_count=1,
                hard_ceiling_max_lines=oversized["src/services/big.py"],
            ),
            encoding="utf-8",
        )
        if collect_violations(root, baseline_path):
            raise AssertionError("clean tree produced violations")
        cases += 1

        big.write_text(
            "\n".join(f"x{i} = {i}" for i in range(SOFT_BUDGET_LINES + 50)) + "\n"
        )
        violations = collect_violations(root, baseline_path)
        if not any(item.rule == "module-grew" for item in violations):
            raise AssertionError(f"growth not rejected: {violations!r}")
        cases += 1

        if write_baseline(root, baseline_path) == 0:
            raise AssertionError("write-baseline accepted growth")
        cases += 1

        big.write_text(
            "\n".join(f"x{i} = {i}" for i in range(SOFT_BUDGET_LINES + 1)) + "\n"
        )
        other = services / "other.py"
        other.write_text(
            "\n".join(f"y{i} = {i}" for i in range(SOFT_BUDGET_LINES + 1)) + "\n"
        )
        violations = collect_violations(root, baseline_path)
        if not any(
            item.rule == "new-oversized-module" and item.path == "src/services/other.py"
            for item in violations
        ):
            raise AssertionError(f"new oversized not rejected: {violations!r}")
        cases += 1

        other.unlink()
        big.write_text("VALUE = 1\n")
        if write_baseline(root, baseline_path) != 0:
            raise AssertionError("write-baseline rejected legitimate shrink")
        loaded = load_baseline(baseline_path)
        if loaded:
            raise AssertionError(f"baseline not emptied: {loaded!r}")
        cases += 1

    print(f"Hot-path module-size self-tests passed ({cases} cases).")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help=(
            "Rewrite oversized allowlist from the current tree. Shrink is "
            "allowed; growth is refused."
        ),
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run isolated guard regression cases and exit.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.self_test:
        run_self_tests()
        return 0

    root = args.root.resolve()
    baseline_path = args.baseline.resolve()
    if args.write_baseline:
        try:
            return write_baseline(root, baseline_path)
        except BaselineError as exc:
            print(
                f"[hot-path-size] ERROR: invalid-baseline: {exc}",
                file=sys.stderr,
            )
            return 1

    try:
        violations = collect_violations(root, baseline_path)
    except BaselineError as exc:
        print(
            f"[hot-path-size] ERROR: invalid-baseline: {exc}",
            file=sys.stderr,
        )
        return 1

    if violations:
        for violation in violations:
            print(f"[hot-path-size] ERROR: {violation.render()}", file=sys.stderr)
        print(
            "[hot-path-size] HINT: split the module or see "
            "docs/hot-path-module-size-ratchet.md for the legitimate-change path",
            file=sys.stderr,
        )
        return 1

    baseline = load_baseline(baseline_path)
    current = scan_oversized(root)
    removed = len(baseline) - len(current)
    note = ""
    if removed > 0:
        note = (
            f" ({removed} baselined module(s) now under budget; "
            "run --write-baseline to shrink the allowlist)"
        )
    print(
        f"[hot-path-size] OK: {len(current)} oversized hot-path module(s) within "
        f"baseline of {len(baseline)} (soft budget {SOFT_BUDGET_LINES} lines)"
        f"{note}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
