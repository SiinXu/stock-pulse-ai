#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Ratcheting guard: ban new bidirectional package import cycles.

Scans production Python under ``src/`` plus top-level entrypoints. Computes
package-level dependency edges from **import-time** imports, then detects
bidirectional package pairs.

"Import-time" means every import statement that runs when the module object is
built: the module body plus any statement body nested in it that executes
eagerly (``try``/``except``/``else``/``finally``, ``if``/``else``,
``with``/``async with``, ``for``/``while`` bodies and their ``else`` clauses,
``match`` cases, and class bodies). Imports inside ``def`` / ``async def``
bodies are lazy and are **not** edges, and imports guarded by
``if TYPE_CHECKING:`` never execute, so they are excluded too. See
``classify_import_modules`` for the exact traversal.

A package is:

- ``src.<name>`` for modules under ``src/`` (first segment after ``src``), or
- a top-level entrypoint name.

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

PRODUCTION_ROOTS = ("src",)
PRODUCTION_FILES = ("main.py", "server.py")
ROOT_PACKAGES = frozenset({"main", "server"})

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


TYPE_CHECKING_MODULES = frozenset({"typing", "typing_extensions"})

_FUNCTION_NODES: tuple[type, ...] = (ast.FunctionDef, ast.AsyncFunctionDef)
_TRY_NODES: tuple[type, ...] = tuple(
    node for node in (ast.Try, getattr(ast, "TryStar", None)) if node is not None
)


@dataclass(frozen=True)
class ImportPlacement:
    """Absolute module names imported by one file, split by execution placement."""

    import_time: tuple[str, ...]
    function_local: tuple[str, ...]


def _pattern_bound_names(pattern: ast.AST) -> Iterable[str]:
    """Yield names bound by a ``match`` case pattern (capture, star, or rest)."""

    for node in ast.walk(pattern):
        for attribute in ("name", "rest"):
            value = getattr(node, attribute, None)
            if isinstance(value, str) and value:
                yield value


def _target_bound_names(target: ast.AST) -> Iterable[str]:
    """Yield names bound (or deleted) by an assignment / loop / ``with`` target.

    Only ``Store``/``Del`` contexts count, so ``typing.X = 1`` does not look like
    a rebinding of the ``typing`` alias itself.
    """

    for node in ast.walk(target):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            yield node.id


class _ImportPlacementVisitor:
    """Split a module's imports into import-time and function-local buckets.

    Traversal rules:

    - Recurse into every statement body that executes while the module is being
      imported, including class bodies, so nested-but-eager imports are real
      package edges.
    - Never treat ``def`` / ``async def`` bodies as import-time; their imports go
      to the function-local bucket instead (lambdas cannot contain statements).
    - Drop ``if TYPE_CHECKING:`` bodies entirely. Resolution is binding-aware:
      only the names actually bound to ``typing``/``typing_extensions``
      ``TYPE_CHECKING`` in this file count, and rebinding such a name clears it.
    """

    def __init__(self, root: Path, path: Path) -> None:
        self._root = root
        self._path = path
        self._type_checking_names: Set[str] = set()
        self._typing_aliases: Set[str] = set()
        self.import_time: list[str] = []
        self.function_local: list[str] = []

    # -- binding tracking -------------------------------------------------

    def _unbind(self, name: str) -> None:
        self._type_checking_names.discard(name)
        self._typing_aliases.discard(name)

    def _snapshot(self) -> Tuple[Set[str], Set[str]]:
        return set(self._type_checking_names), set(self._typing_aliases)

    def _restore(self, snapshot: Tuple[Set[str], Set[str]]) -> None:
        self._type_checking_names, self._typing_aliases = snapshot

    def _record_statement_bindings(self, node: ast.stmt) -> None:
        """Clear tracked aliases that this statement rebinds or deletes."""

        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets.extend(node.targets)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets.append(node.target)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            targets.append(node.target)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            targets.extend(
                item.optional_vars
                for item in node.items
                if item.optional_vars is not None
            )
        elif isinstance(node, ast.Delete):
            targets.extend(node.targets)
        elif isinstance(node, _TRY_NODES):
            for handler in node.handlers:
                if handler.name:
                    self._unbind(handler.name)
        elif isinstance(node, (*_FUNCTION_NODES, ast.ClassDef)):
            self._unbind(node.name)
            return
        elif isinstance(node, ast.Match):
            for case in node.cases:
                for name in _pattern_bound_names(case.pattern):
                    self._unbind(name)
            return
        for target in targets:
            for name in _target_bound_names(target):
                self._unbind(name)

    def _record_import_bindings(self, node: ast.Import | ast.ImportFrom) -> None:
        """Track (or clear) ``TYPE_CHECKING`` aliases introduced by an import."""

        if isinstance(node, ast.Import):
            for alias in node.names:
                if not alias.name:
                    continue
                bound = alias.asname or alias.name.split(".")[0]
                self._unbind(bound)
                if alias.name in TYPE_CHECKING_MODULES:
                    self._typing_aliases.add(bound)
            return
        for alias in node.names:
            if not alias.name:
                continue
            if alias.name == "*":
                # A star import from typing brings TYPE_CHECKING into scope.
                if node.level == 0 and node.module in TYPE_CHECKING_MODULES:
                    self._type_checking_names.add("TYPE_CHECKING")
                continue
            bound = alias.asname or alias.name
            self._unbind(bound)
            if (
                node.level == 0
                and node.module in TYPE_CHECKING_MODULES
                and alias.name == "TYPE_CHECKING"
            ):
                self._type_checking_names.add(bound)

    # -- TYPE_CHECKING resolution ----------------------------------------

    def _type_checking_polarity(self, test: ast.expr) -> bool | None:
        """Return True for ``TYPE_CHECKING``, False for ``not TYPE_CHECKING``."""

        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            inner = self._type_checking_polarity(test.operand)
            return None if inner is None else not inner
        if isinstance(test, ast.Name):
            return True if test.id in self._type_checking_names else None
        if (
            isinstance(test, ast.Attribute)
            and test.attr == "TYPE_CHECKING"
            and isinstance(test.value, ast.Name)
            and test.value.id in self._typing_aliases
        ):
            return True
        return None

    # -- traversal --------------------------------------------------------

    def _emit(self, node: ast.Import | ast.ImportFrom, in_function: bool) -> None:
        bucket = self.function_local if in_function else self.import_time
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name:
                    bucket.append(alias.name)
            return
        resolved = _resolve_from_import(self._root, self._path, node)
        if resolved:
            bucket.append(resolved)

    def visit_body(self, body: Sequence[ast.stmt], in_function: bool) -> None:
        """Walk one statement list, keeping the import-time/lazy split."""

        for node in body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                self._record_import_bindings(node)
                self._emit(node, in_function)
                continue
            self._record_statement_bindings(node)
            if isinstance(node, _FUNCTION_NODES):
                snapshot = self._snapshot()
                self.visit_body(node.body, True)
                self._restore(snapshot)
            elif isinstance(node, ast.ClassDef):
                snapshot = self._snapshot()
                self.visit_body(node.body, in_function)
                self._restore(snapshot)
            elif isinstance(node, _TRY_NODES):
                self.visit_body(node.body, in_function)
                for handler in node.handlers:
                    self.visit_body(handler.body, in_function)
                self.visit_body(node.orelse, in_function)
                self.visit_body(node.finalbody, in_function)
            elif isinstance(node, ast.If):
                polarity = self._type_checking_polarity(node.test)
                if polarity is not True:
                    self.visit_body(node.body, in_function)
                if polarity is not False:
                    self.visit_body(node.orelse, in_function)
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                self.visit_body(node.body, in_function)
            elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
                self.visit_body(node.body, in_function)
                self.visit_body(node.orelse, in_function)
            elif isinstance(node, ast.Match):
                for case in node.cases:
                    self.visit_body(case.body, in_function)


def classify_import_modules(root: Path, path: Path) -> ImportPlacement:
    """Split one file's absolute import targets by execution placement.

    ``import_time`` holds imports that run while the module is imported
    (module body plus eagerly executed nested bodies and class bodies), with
    ``if TYPE_CHECKING:`` branches excluded. ``function_local`` holds imports
    deferred inside function bodies. Both preserve source order and may contain
    duplicates; callers deduplicate at the package-edge level.
    """

    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return ImportPlacement((), ())
    try:
        tree = ast.parse(source, filename=_relative_to_root(root, path))
    except SyntaxError:
        return ImportPlacement((), ())

    visitor = _ImportPlacementVisitor(root, path)
    visitor.visit_body(tree.body, False)
    return ImportPlacement(tuple(visitor.import_time), tuple(visitor.function_local))


def import_time_import_modules(root: Path, path: Path) -> list[str]:
    """Collect absolute module names imported at import time."""

    return list(classify_import_modules(root, path).import_time)


def function_local_import_modules(root: Path, path: Path) -> list[str]:
    """Collect absolute module names imported lazily inside function bodies."""

    return list(classify_import_modules(root, path).function_local)


def build_package_edges(root: Path) -> Dict[str, Set[str]]:
    """Build directed package edges from production import-time imports."""

    edges: Dict[str, Set[str]] = {}
    for path in _iter_production_python(root):
        source_module = module_name_for_path(root, path)
        source_package = package_of_module(source_module)
        if not source_package:
            continue
        for imported in import_time_import_modules(root, path):
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
            "Allowlisted bidirectional package import pairs (import-time "
            "imports: the module body plus nested bodies that execute during "
            "import, including class bodies; function-body and "
            "`if TYPE_CHECKING:` imports are excluded). New pairs are banned; "
            "shrink this list by breaking cycles and running --write-baseline. "
            "Growth requires an explicit PR justification and is refused by "
            "--write-baseline."
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


def _run_placement_self_tests() -> int:
    """Check import placement classification: eager nesting vs lazy vs typing-only."""

    cases = 0
    with tempfile.TemporaryDirectory(prefix="import-placement-") as tmp:
        root = Path(tmp)
        (root / "src" / "alpha").mkdir(parents=True)
        (root / "src" / "beta").mkdir(parents=True)
        (root / "src" / "beta" / "leaf.py").write_text("VALUE = 1\n", encoding="utf-8")

        eager_variants = {
            "try": (
                "try:\n"
                "    from src.beta.leaf import VALUE\n"
                "except ImportError:\n"
                "    VALUE = None\n"
            ),
            "except": (
                "try:\n"
                "    VALUE = 0\n"
                "except ImportError:\n"
                "    from src.beta.leaf import VALUE\n"
            ),
            "try-else": (
                "try:\n"
                "    VALUE = 0\n"
                "except ImportError:\n"
                "    pass\n"
                "else:\n"
                "    from src.beta.leaf import VALUE\n"
            ),
            "try-finally": (
                "try:\n"
                "    VALUE = 0\n"
                "finally:\n"
                "    from src.beta.leaf import VALUE\n"
            ),
            "if": (
                "import os\n"
                "if os.environ.get('X'):\n"
                "    from src.beta.leaf import VALUE\n"
            ),
            "if-else": (
                "import os\n"
                "if os.environ.get('X'):\n"
                "    VALUE = 0\n"
                "else:\n"
                "    from src.beta.leaf import VALUE\n"
            ),
            "with": (
                "from contextlib import suppress\n"
                "with suppress(ImportError):\n"
                "    from src.beta.leaf import VALUE\n"
            ),
            "for": (
                "for _ in range(1):\n"
                "    from src.beta.leaf import VALUE\n"
            ),
            "for-else": (
                "for _ in range(1):\n"
                "    pass\n"
                "else:\n"
                "    from src.beta.leaf import VALUE\n"
            ),
            "while-else": (
                "while False:\n"
                "    pass\n"
                "else:\n"
                "    from src.beta.leaf import VALUE\n"
            ),
            "match": (
                "MODE = 'a'\n"
                "match MODE:\n"
                "    case 'a':\n"
                "        from src.beta.leaf import VALUE\n"
                "    case _:\n"
                "        VALUE = None\n"
            ),
            "class-body": (
                "class Loader:\n"
                "    from src.beta.leaf import VALUE\n"
            ),
            "nested-class-in-try": (
                "try:\n"
                "    class Loader:\n"
                "        if True:\n"
                "            from src.beta.leaf import VALUE\n"
                "except ImportError:\n"
                "    pass\n"
            ),
        }
        module_path = root / "src" / "alpha" / "probe.py"
        for label, source in eager_variants.items():
            module_path.write_text(source, encoding="utf-8")
            placement = classify_import_modules(root, module_path)
            if "src.beta.leaf" not in placement.import_time:
                raise AssertionError(f"eager import missed for placement {label!r}")
            if placement.function_local:
                raise AssertionError(
                    f"eager import leaked into lazy bucket for {label!r}"
                )
            cases += 1

        lazy_variants = {
            "def": (
                "def load():\n"
                "    from src.beta.leaf import VALUE\n"
                "    return VALUE\n"
            ),
            "async-def": (
                "async def load():\n"
                "    from src.beta.leaf import VALUE\n"
                "    return VALUE\n"
            ),
            "method": (
                "class Loader:\n"
                "    def load(self):\n"
                "        from src.beta.leaf import VALUE\n"
                "        return VALUE\n"
            ),
            "nested-def": (
                "def outer():\n"
                "    def inner():\n"
                "        from src.beta.leaf import VALUE\n"
                "        return VALUE\n"
                "    return inner\n"
            ),
            "class-in-def": (
                "def outer():\n"
                "    class Inner:\n"
                "        from src.beta.leaf import VALUE\n"
                "    return Inner\n"
            ),
            "def-in-try": (
                "try:\n"
                "    def load():\n"
                "        from src.beta.leaf import VALUE\n"
                "        return VALUE\n"
                "except ImportError:\n"
                "    load = None\n"
            ),
        }
        for label, source in lazy_variants.items():
            module_path.write_text(source, encoding="utf-8")
            placement = classify_import_modules(root, module_path)
            if placement.import_time:
                raise AssertionError(f"lazy import treated as eager for {label!r}")
            if "src.beta.leaf" not in placement.function_local:
                raise AssertionError(f"lazy import missed for placement {label!r}")
            cases += 1

        typing_variants = {
            "plain": (
                "from typing import TYPE_CHECKING\n"
                "if TYPE_CHECKING:\n"
                "    from src.beta.leaf import VALUE\n"
            ),
            "alias": (
                "from typing import TYPE_CHECKING as TC\n"
                "if TC:\n"
                "    from src.beta.leaf import VALUE\n"
            ),
            "module-attribute": (
                "import typing\n"
                "if typing.TYPE_CHECKING:\n"
                "    from src.beta.leaf import VALUE\n"
            ),
            "module-alias-attribute": (
                "import typing as t\n"
                "if t.TYPE_CHECKING:\n"
                "    from src.beta.leaf import VALUE\n"
            ),
            "typing-extensions": (
                "from typing_extensions import TYPE_CHECKING\n"
                "if TYPE_CHECKING:\n"
                "    from src.beta.leaf import VALUE\n"
            ),
            "not-branch": (
                "from typing import TYPE_CHECKING\n"
                "if not TYPE_CHECKING:\n"
                "    VALUE = 0\n"
                "else:\n"
                "    from src.beta.leaf import VALUE\n"
            ),
            "nested-in-try": (
                "from typing import TYPE_CHECKING\n"
                "try:\n"
                "    if TYPE_CHECKING:\n"
                "        from src.beta.leaf import VALUE\n"
                "except ImportError:\n"
                "    pass\n"
            ),
        }
        for label, source in typing_variants.items():
            module_path.write_text(source, encoding="utf-8")
            placement = classify_import_modules(root, module_path)
            if "src.beta.leaf" in placement.import_time:
                raise AssertionError(f"TYPE_CHECKING import counted for {label!r}")
            cases += 1

        # `if not TYPE_CHECKING:` bodies DO run at import time.
        module_path.write_text(
            "from typing import TYPE_CHECKING\n"
            "if not TYPE_CHECKING:\n"
            "    from src.beta.leaf import VALUE\n",
            encoding="utf-8",
        )
        if "src.beta.leaf" not in classify_import_modules(root, module_path).import_time:
            raise AssertionError("`if not TYPE_CHECKING:` body was dropped")
        cases += 1

        # A locally rebound TYPE_CHECKING name is no longer the typing sentinel.
        rebinding_variants = {
            "assignment": (
                "from typing import TYPE_CHECKING\n"
                "TYPE_CHECKING = True\n"
                "if TYPE_CHECKING:\n"
                "    from src.beta.leaf import VALUE\n"
            ),
            "unrelated-import": (
                "from src.beta.flags import TYPE_CHECKING\n"
                "if TYPE_CHECKING:\n"
                "    from src.beta.leaf import VALUE\n"
            ),
            "shadowed-module-alias": (
                "import typing\n"
                "typing = object()\n"
                "if typing.TYPE_CHECKING:\n"
                "    from src.beta.leaf import VALUE\n"
            ),
            "no-binding": (
                "if TYPE_CHECKING:\n"
                "    from src.beta.leaf import VALUE\n"
            ),
        }
        for label, source in rebinding_variants.items():
            module_path.write_text(source, encoding="utf-8")
            if (
                "src.beta.leaf"
                not in classify_import_modules(root, module_path).import_time
            ):
                raise AssertionError(
                    f"rebound TYPE_CHECKING name still excluded imports for {label!r}"
                )
            cases += 1

        # A class-body TYPE_CHECKING rebinding must not leak into module scope.
        module_path.write_text(
            "from typing import TYPE_CHECKING\n"
            "class Shadow:\n"
            "    TYPE_CHECKING = True\n"
            "if TYPE_CHECKING:\n"
            "    from src.beta.leaf import VALUE\n",
            encoding="utf-8",
        )
        if "src.beta.leaf" in classify_import_modules(root, module_path).import_time:
            raise AssertionError("class-body rebinding leaked into module scope")
        cases += 1

        # Nested eager placement still produces a real package edge end to end.
        (root / "src" / "alpha" / "probe.py").write_text(
            "try:\n"
            "    from src.beta.leaf import VALUE\n"
            "except ImportError:\n"
            "    VALUE = None\n",
            encoding="utf-8",
        )
        (root / "src" / "beta" / "leaf.py").write_text(
            "class Holder:\n"
            "    from src.alpha.probe import VALUE\n",
            encoding="utf-8",
        )
        if scan_pairs(root) != [("src.alpha", "src.beta")]:
            raise AssertionError(
                f"nested eager imports did not form a pair: {scan_pairs(root)!r}"
            )
        cases += 1

        # The same edges behind `def` bodies stay invisible to the cycle ratchet.
        (root / "src" / "alpha" / "probe.py").write_text(
            "def load():\n"
            "    from src.beta.leaf import VALUE\n"
            "    return VALUE\n",
            encoding="utf-8",
        )
        (root / "src" / "beta" / "leaf.py").write_text(
            "def load():\n"
            "    from src.alpha.probe import load as other\n"
            "    return other\n",
            encoding="utf-8",
        )
        if scan_pairs(root):
            raise AssertionError("function-body imports formed a pair")
        cases += 1

        # Unparsable files degrade to "no imports" instead of raising.
        (root / "src" / "alpha" / "probe.py").write_text("def broken(\n", encoding="utf-8")
        if classify_import_modules(root, root / "src" / "alpha" / "probe.py") != (
            ImportPlacement((), ())
        ):
            raise AssertionError("syntax error did not degrade to empty placement")
        cases += 1

    return cases


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

    cases += _run_placement_self_tests()

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
