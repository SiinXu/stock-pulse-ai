#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Ratcheting guard: ban new bidirectional package import cycles.

Scans production Python under ``src/``, ``data_provider/``, ``api/``, ``bot/``,
plus top-level entrypoints. Computes package-level dependency edges from
**module-level** imports only (lazy imports inside functions are ignored), then
detects bidirectional package pairs.

A package is:

- ``src.<name>`` for modules under ``src/`` (first segment after ``src``), or
- a root package ``data_provider`` / ``api`` / ``bot`` / entrypoint name.

Known pairs live in the checked-in baseline. New pairs fail CI. Removing a pair
does not fail the check; run ``--write-baseline`` after a deliberate break to
shrink the allowlist. ``--write-baseline`` refuses growth relative to the
existing baseline.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Mapping, Sequence, Set, Tuple


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = ROOT / "scripts" / "import_layer_baseline.json"
BASELINE_VERSION = 1

PRODUCTION_ROOTS = ("src", "data_provider", "api", "bot")
PRODUCTION_FILES = ("main.py", "server.py", "webui.py")
ROOT_PACKAGES = frozenset({"data_provider", "api", "bot", "main", "server", "webui"})

Pair = Tuple[str, str]


class BaselineError(ValueError):
    """Raised when the checked-in baseline is malformed."""


@dataclass(frozen=True, order=True)
class Violation:
    """One unexplained bidirectional package pair (or baseline growth attempt)."""

    rule: str
    package_a: str
    package_b: str
    message: str

    def render(self) -> str:
        pair = f"{self.package_a} <-> {self.package_b}"
        return f"{self.rule}: {pair}: {self.message}"


def _relative_to_root(root: Path, path: Path) -> str:
    """Return a stable POSIX path relative to the repository root."""

    return path.resolve().relative_to(root.resolve()).as_posix()


def _iter_production_python(root: Path) -> Iterable[Path]:
    """Yield production Python files within the guard ownership scope."""

    for relative in PRODUCTION_FILES:
        path = root / relative
        if path.is_file():
            yield path
    for relative_directory in PRODUCTION_ROOTS:
        directory = root / relative_directory
        if not directory.is_dir():
            continue
        yield from sorted(directory.rglob("*.py"))


def module_name_for_path(root: Path, path: Path) -> str | None:
    """Map a file path to its dotted Python module name."""

    relative = _relative_to_root(root, path)
    if not relative.endswith(".py"):
        return None
    if relative.endswith("/__init__.py"):
        dotted = relative[: -len("/__init__.py")].replace("/", ".")
        return dotted or None
    return relative[: -len(".py")].replace("/", ".")


def package_of_module(module_name: str | None) -> str | None:
    """Map a dotted module name to its ratchet package identity."""

    if not module_name:
        return None
    parts = module_name.split(".")
    head = parts[0]
    if head == "src":
        if len(parts) >= 2:
            return f"src.{parts[1]}"
        return "src"
    if head in ROOT_PACKAGES:
        return head
    return None


def _resolve_from_import(root: Path, path: Path, node: ast.ImportFrom) -> str | None:
    """Resolve a ``from ... import ...`` module target to an absolute name."""

    if node.level == 0:
        return node.module

    current = module_name_for_path(root, path)
    if not current:
        return None
    parts = current.split(".")
    if path.name != "__init__.py":
        parts = parts[:-1]
    ascend = node.level - 1
    if ascend > len(parts):
        return None
    if ascend:
        parts = parts[:-ascend]
    if node.module:
        parts = parts + node.module.split(".")
    return ".".join(parts) if parts else None


def top_level_import_modules(root: Path, path: Path) -> list[str]:
    """Collect absolute module names imported at module body level only."""

    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        tree = ast.parse(source, filename=_relative_to_root(root, path))
    except SyntaxError:
        return []

    modules: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name:
                    modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve_from_import(root, path, node)
            if resolved:
                modules.append(resolved)
    return modules


def build_package_edges(root: Path) -> Dict[str, Set[str]]:
    """Build directed package edges from production module-level imports."""

    edges: Dict[str, Set[str]] = {}
    for path in _iter_production_python(root):
        source_module = module_name_for_path(root, path)
        source_package = package_of_module(source_module)
        if not source_package:
            continue
        for imported in top_level_import_modules(root, path):
            target_package = package_of_module(imported)
            if not target_package or target_package == source_package:
                continue
            edges.setdefault(source_package, set()).add(target_package)
    return edges


def find_bidirectional_pairs(edges: Mapping[str, Set[str]]) -> list[Pair]:
    """Return sorted undirected bidirectional package pairs."""

    pairs: list[Pair] = []
    for source, targets in edges.items():
        for target in targets:
            if source < target and source in edges.get(target, ()):
                pairs.append((source, target))
    return sorted(pairs)


def scan_pairs(root: Path) -> list[Pair]:
    """Scan the repository and return current bidirectional package pairs."""

    return find_bidirectional_pairs(build_package_edges(root))


def normalize_pair(left: str, right: str) -> Pair:
    """Canonical undirected pair ordering."""

    return (left, right) if left < right else (right, left)


def load_baseline(path: Path) -> list[Pair]:
    """Load the checked-in allowlist of bidirectional package pairs."""

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
    pairs_raw = payload.get("pairs")
    if not isinstance(pairs_raw, list):
        raise BaselineError("baseline.pairs must be a list")

    pairs: list[Pair] = []
    seen: set[Pair] = set()
    for index, item in enumerate(pairs_raw):
        if not isinstance(item, list) or len(item) != 2:
            raise BaselineError(
                f"baseline.pairs[{index}] must be a two-element string list"
            )
        left, right = item
        if not isinstance(left, str) or not left or not isinstance(right, str) or not right:
            raise BaselineError(
                f"baseline.pairs[{index}] must contain two non-empty strings"
            )
        if left == right:
            raise BaselineError(
                f"baseline.pairs[{index}] must not be a self-pair: {left}"
            )
        if left > right:
            raise BaselineError(
                f"baseline.pairs[{index}] must be ordered as left < right "
                f"(got {left!r}, {right!r})"
            )
        pair = (left, right)
        if pair in seen:
            raise BaselineError(f"duplicate baseline pair: {pair[0]} <-> {pair[1]}")
        seen.add(pair)
        pairs.append(pair)

    if pairs != sorted(pairs):
        raise BaselineError("baseline.pairs must be sorted lexicographically")
    return pairs


def serialize_baseline(pairs: Sequence[Pair]) -> str:
    """Render the baseline JSON document with a stable schema."""

    ordered = sorted(normalize_pair(a, b) for a, b in pairs)
    payload = {
        "version": BASELINE_VERSION,
        "description": (
            "Allowlisted bidirectional package import pairs (module-level "
            "imports only). New pairs are banned; shrink this list by breaking "
            "cycles and running --write-baseline. Growth requires an explicit "
            "PR justification and is refused by --write-baseline."
        ),
        "pair_count": len(ordered),
        "pairs": [[a, b] for a, b in ordered],
    }
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def collect_violations(root: Path, baseline_path: Path) -> list[Violation]:
    """Return violations for bidirectional pairs outside the baseline."""

    baseline = set(load_baseline(baseline_path))
    current = scan_pairs(root)
    violations: list[Violation] = []
    for left, right in current:
        if (left, right) in baseline:
            continue
        violations.append(
            Violation(
                rule="new-bidirectional-pair",
                package_a=left,
                package_b=right,
                message=(
                    "new bidirectional package import cycle is banned; break "
                    "the cycle (prefer leaf utilities / one-way dependency) or "
                    "document an intentional baseline update with PR "
                    "justification (manual baseline edit only — "
                    "--write-baseline refuses growth)"
                ),
            )
        )
    return sorted(violations)


def write_baseline(root: Path, baseline_path: Path) -> int:
    """Rewrite the pair allowlist from the current tree, refusing growth."""

    current = scan_pairs(root)
    if baseline_path.is_file():
        try:
            existing = set(load_baseline(baseline_path))
        except BaselineError as exc:
            print(
                f"[import-layers] ERROR: invalid-baseline: {exc}",
                file=sys.stderr,
            )
            return 1
        growth = sorted(set(current) - existing)
        if growth:
            for left, right in growth:
                violation = Violation(
                    rule="baseline-growth",
                    package_a=left,
                    package_b=right,
                    message=(
                        "refusing to grow the allowlist via --write-baseline; "
                        "break the new cycle or manually edit the baseline with "
                        "explicit PR justification"
                    ),
                )
                print(
                    f"[import-layers] ERROR: {violation.render()}",
                    file=sys.stderr,
                )
            return 1

    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(serialize_baseline(current), encoding="utf-8")
    print(
        f"[import-layers] wrote {len(current)} bidirectional pair(s) to "
        f"{baseline_path}"
    )
    return 0


def run_self_tests() -> None:
    """Exercise pair detection, shrink, growth refusal, and baseline parsing."""

    cases = 0
    with tempfile.TemporaryDirectory(prefix="import-layers-") as tmp:
        root = Path(tmp)
        (root / "src" / "config").mkdir(parents=True)
        (root / "src" / "services").mkdir(parents=True)
        (root / "src" / "utils").mkdir(parents=True)
        (root / "scripts").mkdir()

        (root / "src" / "config" / "settings.py").write_text(
            "from src.services.parser import split_list\n",
            encoding="utf-8",
        )
        (root / "src" / "services" / "parser.py").write_text(
            "from src.config.settings import Config\n"
            "def split_list(value):\n"
            "    return value.split(',')\n",
            encoding="utf-8",
        )
        (root / "src" / "utils" / "leaf.py").write_text(
            "def split_list(value):\n"
            "    return value.split(',')\n",
            encoding="utf-8",
        )

        baseline_path = root / "scripts" / "import_layer_baseline.json"
        pairs = scan_pairs(root)
        if pairs != [("src.config", "src.services")]:
            raise AssertionError(f"expected config/services pair, got {pairs!r}")
        cases += 1

        baseline_path.write_text(serialize_baseline(pairs), encoding="utf-8")
        if collect_violations(root, baseline_path):
            raise AssertionError("clean tree produced violations")
        cases += 1

        # Introduce a second cycle: services <-> utils
        (root / "src" / "services" / "parser.py").write_text(
            "from src.config.settings import Config\n"
            "from src.utils.leaf import split_list as _\n"
            "def split_list(value):\n"
            "    return value.split(',')\n",
            encoding="utf-8",
        )
        (root / "src" / "utils" / "leaf.py").write_text(
            "from src.services.parser import split_list as original\n"
            "def split_list(value):\n"
            "    return original(value)\n",
            encoding="utf-8",
        )
        violations = collect_violations(root, baseline_path)
        if not any(
            item.package_a == "src.services" and item.package_b == "src.utils"
            for item in violations
        ):
            raise AssertionError(f"new pair was not rejected: {violations!r}")
        cases += 1

        # --write-baseline must refuse growth
        if write_baseline(root, baseline_path) == 0:
            raise AssertionError("write-baseline accepted growth")
        cases += 1

        # Break both cycles: config and services depend on utils only
        (root / "src" / "config" / "settings.py").write_text(
            "from src.utils.leaf import split_list\n",
            encoding="utf-8",
        )
        (root / "src" / "services" / "parser.py").write_text(
            "from src.utils.leaf import split_list\n",
            encoding="utf-8",
        )
        (root / "src" / "utils" / "leaf.py").write_text(
            "def split_list(value):\n"
            "    return value.split(',')\n",
            encoding="utf-8",
        )
        shrunk = scan_pairs(root)
        if shrunk:
            raise AssertionError(f"expected empty pairs after break, got {shrunk!r}")
        if write_baseline(root, baseline_path) != 0:
            raise AssertionError("write-baseline rejected legitimate shrink")
        loaded = load_baseline(baseline_path)
        if loaded:
            raise AssertionError(f"baseline not shrunk: {loaded!r}")
        cases += 1

        # Lazy (function-body) imports must not create pairs
        (root / "src" / "config" / "settings.py").write_text(
            "def load():\n"
            "    from src.services.parser import split_list\n"
            "    return split_list\n",
            encoding="utf-8",
        )
        (root / "src" / "services" / "parser.py").write_text(
            "def split_list(value):\n"
            "    from src.config.settings import load\n"
            "    return value.split(',')\n",
            encoding="utf-8",
        )
        if scan_pairs(root):
            raise AssertionError("function-body imports were treated as edges")
        cases += 1

        bad = {
            "version": BASELINE_VERSION,
            "pairs": [["src.b", "src.a"]],  # unsorted
        }
        bad_path = root / "scripts" / "bad_baseline.json"
        bad_path.write_text(json.dumps(bad), encoding="utf-8")
        try:
            load_baseline(bad_path)
        except BaselineError:
            cases += 1
        else:
            raise AssertionError("unsorted baseline was accepted")

        # Tests are out of scope
        (root / "tests").mkdir()
        (root / "tests" / "test_cycle.py").write_text(
            "from src.config.settings import load\n"
            "from src.services.parser import split_list\n",
            encoding="utf-8",
        )
        # restore one-way edges only
        (root / "src" / "config" / "settings.py").write_text(
            "from src.utils.leaf import split_list\n",
            encoding="utf-8",
        )
        (root / "src" / "services" / "parser.py").write_text(
            "from src.utils.leaf import split_list\n",
            encoding="utf-8",
        )
        if scan_pairs(root):
            raise AssertionError(f"tests leaked into scan: {scan_pairs(root)!r}")
        cases += 1

    print(f"Import-layer self-tests passed ({cases} cases).")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI options."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help=(
            "Rewrite the bidirectional-pair allowlist from the current tree. "
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
    """Run the import-layer cycle ratchet."""

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
                f"[import-layers] ERROR: invalid-baseline: {exc}",
                file=sys.stderr,
            )
            return 1

    try:
        violations = collect_violations(root, baseline_path)
    except BaselineError as exc:
        print(
            f"[import-layers] ERROR: invalid-baseline: {exc}",
            file=sys.stderr,
        )
        return 1

    if violations:
        for violation in violations:
            print(f"[import-layers] ERROR: {violation.render()}", file=sys.stderr)
        print(
            "[import-layers] HINT: break the cycle or see "
            "docs/import-cycle-ratchet.md for the legitimate-change path",
            file=sys.stderr,
        )
        return 1

    baseline = load_baseline(baseline_path)
    current = scan_pairs(root)
    removed = len(baseline) - len(current)
    note = ""
    if removed > 0:
        note = (
            f" ({removed} baseline pair(s) no longer present; "
            "run --write-baseline to shrink the allowlist)"
        )
    print(
        f"[import-layers] OK: {len(current)} bidirectional pair(s) within "
        f"baseline of {len(baseline)}{note}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
