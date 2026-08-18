#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Ratcheting guard: ban new reverse imports against the layered architecture.

Enforces the directed dependency shape from issue #1082:

```text
src.api → services → pipeline/stages → src.data_provider
```

and keeps lower layers from reaching the HTTP transport (``src.api``).

Measurement uses **module-level** imports only (function-body lazy imports are
ignored), reusing the same production file scope as the import-cycle ratchet.

Existing reverse edges are frozen in a shrink-only baseline. New reverse edges
fail CI. ``--write-baseline`` may shrink the allowlist and **refuses growth**.
Do not expand the baseline to green CI — extract leaf utilities or invert the
dependency instead.

See: docs/layer-direction-ratchet.md, https://github.com/SiinXu/stock-pulse-ai/issues/1082
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_import_layers import (  # noqa: E402
    ROOT as DEFAULT_ROOT,
    _iter_production_python,
    module_name_for_path,
    package_of_module,
    top_level_import_modules,
)


ROOT = DEFAULT_ROOT
DEFAULT_BASELINE = ROOT / "scripts" / "layer_direction_baseline.json"
BASELINE_VERSION = 1

FORBIDDEN_RULES: Tuple[Tuple[str, str], ...] = (
    ("src.data_provider", "src.services"),
    ("src.data_provider", "src.api"),
    ("src.data_provider", "src.core"),
    ("src.data_provider", "src.agent"),
    ("src.services", "src.api"),
    ("src.core", "src.api"),
    ("src.agent", "src.api"),
    ("src.market", "src.api"),
    ("src.analyzer", "src.api"),
    ("src.core", "src.services"),
)

Edge = Tuple[str, str, str]


class BaselineError(ValueError):
    """Raised when the checked-in baseline is malformed."""


@dataclass(frozen=True, order=True)
class Violation:
    """One unexplained reverse import (or baseline growth attempt)."""

    rule: str
    path: str
    from_package: str
    to_package: str
    message: str

    def render(self) -> str:
        edge = f"{self.from_package} -> {self.to_package}"
        return f"{self.rule}: {self.path}: {edge}: {self.message}"


def _relative_to_root(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def rule_applies(from_package: str, to_package: str, path: str) -> bool:
    if (from_package, to_package) not in FORBIDDEN_RULES:
        return False
    if (from_package, to_package) == ("src.core", "src.services"):
        if path == "src/core/pipeline.py":
            return True
        return path.startswith("src/core/stages/")
    return True


def scan_reverse_edges(root: Path) -> list[Edge]:
    edges: Set[Edge] = set()
    for path in _iter_production_python(root):
        relative = _relative_to_root(root, path)
        source_module = module_name_for_path(root, path)
        source_package = package_of_module(source_module)
        if not source_package:
            continue
        targets: Set[str] = set()
        for imported in top_level_import_modules(root, path):
            target_package = package_of_module(imported)
            if target_package and target_package != source_package:
                targets.add(target_package)
        for target_package in targets:
            if rule_applies(source_package, target_package, relative):
                edges.add((relative, source_package, target_package))
    return sorted(edges)


def load_baseline(path: Path) -> list[Edge]:
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

    hard_ceiling = payload.get("hard_ceiling")
    if not isinstance(hard_ceiling, int) or hard_ceiling < 0:
        raise BaselineError("baseline.hard_ceiling must be a non-negative int")

    exceptions_raw = payload.get("exceptions")
    if not isinstance(exceptions_raw, list):
        raise BaselineError("baseline.exceptions must be a list")

    edges: list[Edge] = []
    seen: set[Edge] = set()
    for index, item in enumerate(exceptions_raw):
        if not isinstance(item, dict):
            raise BaselineError(f"baseline.exceptions[{index}] must be an object")
        path_value = item.get("path")
        from_package = item.get("from_package")
        to_package = item.get("to_package")
        if not isinstance(path_value, str) or not path_value:
            raise BaselineError(
                f"baseline.exceptions[{index}].path must be a non-empty string"
            )
        if not isinstance(from_package, str) or not from_package:
            raise BaselineError(
                f"baseline.exceptions[{index}].from_package must be a non-empty string"
            )
        if not isinstance(to_package, str) or not to_package:
            raise BaselineError(
                f"baseline.exceptions[{index}].to_package must be a non-empty string"
            )
        if not rule_applies(from_package, to_package, path_value):
            raise BaselineError(
                f"baseline.exceptions[{index}] is not a configured reverse rule: "
                f"{from_package} -> {to_package} at {path_value}"
            )
        edge = (path_value, from_package, to_package)
        if edge in seen:
            raise BaselineError(f"duplicate baseline exception: {edge}")
        seen.add(edge)
        edges.append(edge)

    if edges != sorted(edges):
        raise BaselineError("baseline.exceptions must be sorted lexicographically")

    if len(edges) > hard_ceiling:
        raise BaselineError(
            f"baseline exception count {len(edges)} exceeds hard_ceiling "
            f"{hard_ceiling}; never raise the ceiling to green CI"
        )

    declared_count = payload.get("exception_count")
    if declared_count is not None and declared_count != len(edges):
        raise BaselineError(
            f"baseline.exception_count {declared_count!r} does not match "
            f"len(exceptions)={len(edges)}"
        )
    return edges


def serialize_baseline(edges: Sequence[Edge], hard_ceiling: int) -> str:
    ordered = sorted(edges)
    if len(ordered) > hard_ceiling:
        raise BaselineError(
            f"refusing to serialize {len(ordered)} exceptions above hard_ceiling "
            f"{hard_ceiling}"
        )
    payload = {
        "version": BASELINE_VERSION,
        "description": (
            "Allowlisted reverse layer-import edges (module-level imports only). "
            "New reverse edges are banned; shrink this list after breaking a "
            "dependency and running --write-baseline. Growth is refused. "
            "Never raise hard_ceiling to green CI — fix the reverse import."
        ),
        "rules": [[a, b] for a, b in FORBIDDEN_RULES],
        "hard_ceiling": hard_ceiling,
        "exception_count": len(ordered),
        "exceptions": [
            {
                "path": path,
                "from_package": from_package,
                "to_package": to_package,
            }
            for path, from_package, to_package in ordered
        ],
        "cleanup_plan": [
            (
                "src.data_provider → src.services: move market/symbol helpers used by "
                "providers into a leaf module (for example src.utils or "
                "src.data_provider-local) so providers no longer import services."
            ),
            (
                "src.core pipeline/stages → src.services: inject service ports from "
                "the services layer (or leaf adapters) instead of importing "
                "application services from orchestration stages."
            ),
            (
                "Any * → api / src.api edge: keep HTTP transport one-way; share "
                "DTOs via src.schemas or dedicated contracts, never import the "
                "HTTP package from below."
            ),
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def _read_hard_ceiling(path: Path) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return int(payload["hard_ceiling"])


def collect_violations(root: Path, baseline_path: Path) -> list[Violation]:
    baseline = set(load_baseline(baseline_path))
    hard_ceiling = _read_hard_ceiling(baseline_path)
    current = scan_reverse_edges(root)
    violations: list[Violation] = []

    if len(current) > hard_ceiling:
        violations.append(
            Violation(
                rule="hard-ceiling",
                path="*",
                from_package="*",
                to_package="*",
                message=(
                    f"reverse-edge count {len(current)} exceeds hard_ceiling "
                    f"{hard_ceiling}; never raise the ceiling — remove reverse "
                    "imports instead"
                ),
            )
        )

    for path, from_package, to_package in current:
        if (path, from_package, to_package) in baseline:
            continue
        violations.append(
            Violation(
                rule="new-reverse-edge",
                path=path,
                from_package=from_package,
                to_package=to_package,
                message=(
                    "new reverse layer import is banned (api → services → "
                    "pipeline/stages → src.data_provider); extract a leaf utility "
                    "or invert the dependency. Do not expand the baseline to "
                    "green CI"
                ),
            )
        )
    return sorted(violations)


def write_baseline(root: Path, baseline_path: Path) -> int:
    current = scan_reverse_edges(root)
    if baseline_path.is_file():
        try:
            existing = set(load_baseline(baseline_path))
            hard_ceiling = _read_hard_ceiling(baseline_path)
        except BaselineError as exc:
            print(
                f"[layer-direction] ERROR: invalid-baseline: {exc}",
                file=sys.stderr,
            )
            return 1
        growth = sorted(set(current) - existing)
        if growth:
            for path, from_package, to_package in growth:
                violation = Violation(
                    rule="baseline-growth",
                    path=path,
                    from_package=from_package,
                    to_package=to_package,
                    message=(
                        "refusing to grow the reverse-edge allowlist via "
                        "--write-baseline; break the reverse import instead"
                    ),
                )
                print(
                    f"[layer-direction] ERROR: {violation.render()}",
                    file=sys.stderr,
                )
            return 1
        if len(current) > hard_ceiling:
            print(
                f"[layer-direction] ERROR: hard-ceiling: reverse-edge count "
                f"{len(current)} exceeds hard_ceiling {hard_ceiling}",
                file=sys.stderr,
            )
            return 1
    else:
        hard_ceiling = len(current)

    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        baseline_path.write_text(
            serialize_baseline(current, hard_ceiling=hard_ceiling),
            encoding="utf-8",
        )
    except BaselineError as exc:
        print(f"[layer-direction] ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"[layer-direction] wrote {len(current)} reverse-edge exception(s) to "
        f"{baseline_path} (hard_ceiling={hard_ceiling})"
    )
    return 0


def run_self_tests() -> None:
    cases = 0
    with tempfile.TemporaryDirectory(prefix="layer-direction-") as tmp:
        root = Path(tmp)
        (root / "src" / "services").mkdir(parents=True)
        (root / "src" / "core" / "stages").mkdir(parents=True)
        (root / "src" / "data_provider").mkdir(parents=True)
        (root / "src" / "api").mkdir(parents=True)
        (root / "scripts").mkdir()

        (root / "src" / "services" / "svc.py").write_text(
            "VALUE = 1\n", encoding="utf-8"
        )
        (root / "src" / "data_provider" / "fetcher.py").write_text(
            "from src.services.svc import VALUE\n", encoding="utf-8"
        )
        (root / "src" / "core" / "pipeline.py").write_text(
            "from src.services.svc import VALUE\n", encoding="utf-8"
        )
        (root / "src" / "api" / "app.py").write_text(
            "from src.services.svc import VALUE\n", encoding="utf-8"
        )

        edges = scan_reverse_edges(root)
        expected = {
            ("src/data_provider/fetcher.py", "src.data_provider", "src.services"),
            ("src/core/pipeline.py", "src.core", "src.services"),
        }
        if set(edges) != expected:
            raise AssertionError(f"unexpected edges: {edges!r}")
        cases += 1

        baseline_path = root / "scripts" / "layer_direction_baseline.json"
        baseline_path.write_text(
            serialize_baseline(edges, hard_ceiling=len(edges)), encoding="utf-8"
        )
        if collect_violations(root, baseline_path):
            raise AssertionError("clean tree produced violations")
        cases += 1

        (root / "src" / "data_provider" / "other.py").write_text(
            "from src.services.svc import VALUE\n", encoding="utf-8"
        )
        violations = collect_violations(root, baseline_path)
        if not any(
            item.rule == "new-reverse-edge" and item.path == "src/data_provider/other.py"
            for item in violations
        ):
            raise AssertionError(f"new reverse edge not rejected: {violations!r}")
        cases += 1

        if write_baseline(root, baseline_path) == 0:
            raise AssertionError("write-baseline accepted growth")
        cases += 1

        (root / "src" / "data_provider" / "other.py").unlink()
        (root / "src" / "data_provider" / "fetcher.py").write_text("VALUE = 0\n", encoding="utf-8")
        if write_baseline(root, baseline_path) != 0:
            raise AssertionError("write-baseline rejected legitimate shrink")
        loaded = load_baseline(baseline_path)
        if loaded != [("src/core/pipeline.py", "src.core", "src.services")]:
            raise AssertionError(f"baseline not shrunk: {loaded!r}")
        cases += 1

        (root / "src" / "data_provider" / "fetcher.py").write_text(
            "def load():\n"
            "    from src.services.svc import VALUE\n"
            "    return VALUE\n",
            encoding="utf-8",
        )
        if any(edge[0] == "src/data_provider/fetcher.py" for edge in scan_reverse_edges(root)):
            raise AssertionError("function-body import treated as reverse edge")
        cases += 1

        if any(edge[1] == "src.api" for edge in scan_reverse_edges(root)):
            raise AssertionError("forward src.api→services treated as reverse")
        cases += 1

    print(f"Layer-direction self-tests passed ({cases} cases).")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help=(
            "Rewrite the reverse-edge allowlist from the current tree. "
            "Shrink is allowed; growth is refused."
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
                f"[layer-direction] ERROR: invalid-baseline: {exc}",
                file=sys.stderr,
            )
            return 1

    try:
        violations = collect_violations(root, baseline_path)
    except BaselineError as exc:
        print(
            f"[layer-direction] ERROR: invalid-baseline: {exc}",
            file=sys.stderr,
        )
        return 1

    if violations:
        for violation in violations:
            print(f"[layer-direction] ERROR: {violation.render()}", file=sys.stderr)
        print(
            "[layer-direction] HINT: break the reverse import or see "
            "docs/layer-direction-ratchet.md for the legitimate-change path",
            file=sys.stderr,
        )
        return 1

    baseline = load_baseline(baseline_path)
    current = scan_reverse_edges(root)
    removed = len(baseline) - len(current)
    note = ""
    if removed > 0:
        note = (
            f" ({removed} baseline exception(s) no longer present; "
            "run --write-baseline to shrink the allowlist)"
        )
    print(
        f"[layer-direction] OK: {len(current)} reverse-edge exception(s) within "
        f"baseline of {len(baseline)}{note}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
