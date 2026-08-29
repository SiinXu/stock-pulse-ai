#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Ratcheting guard: ban new reverse imports against the layered architecture.

Enforces the directed dependency shape from issue #1082:

```text
src.api → services → pipeline/stages → src.data_provider
```

and keeps lower layers from reaching the HTTP transport (``src.api``).

Measurement uses **import-time** imports, reusing the same production file scope
and traversal as the import-cycle ratchet: the module body plus every nested
body that executes while the module is imported (``try``/``except``/``else``/
``finally``, ``if``/``else``, ``with``/``async with``, ``for``/``while`` bodies
and their ``else`` clauses, ``match`` cases, and class bodies).

Two placements are deliberately outside enforcement:

- ``if TYPE_CHECKING:`` branches never execute, so they are not edges. The
  exclusion is binding-aware: only names actually bound to
  ``typing``/``typing_extensions`` ``TYPE_CHECKING`` in that file are honoured.
- ``def`` / ``async def`` bodies are deferred loads. They stay out of the
  enforced inventory, but the ones that are not already visible as import-time
  edges are tracked in the baseline's advisory ``lazy_exceptions`` section so
  growth is at least observable. Drift in that section — in either direction —
  only prints ``NOTE:`` lines and never changes the exit code. A
  ``lazy_exceptions`` section the guard cannot parse is a different matter and
  is still rejected as an invalid baseline.

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
    classify_import_modules,
    module_name_for_path,
    package_of_module,
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


def _scan_reverse_edges_by_placement(root: Path) -> Tuple[list[Edge], list[Edge]]:
    """Return ``(import-time reverse edges, lazy-only reverse edges)``.

    A lazy edge whose ``(path, from, to)`` triple is also present in the
    *currently scanned* import-time set carries no new information, so it is
    dropped from the advisory inventory. The dedupe is against what this scan
    just measured, not against the baseline ``exceptions`` array — the two
    coincide only while the enforced ratchet is green.
    """

    eager: Set[Edge] = set()
    lazy: Set[Edge] = set()
    for path in _iter_production_python(root):
        relative = _relative_to_root(root, path)
        source_module = module_name_for_path(root, path)
        source_package = package_of_module(source_module)
        if not source_package:
            continue
        placement = classify_import_modules(root, path)
        for imports, sink in (
            (placement.import_time, eager),
            (placement.function_local, lazy),
        ):
            for imported in imports:
                target_package = package_of_module(imported)
                if not target_package or target_package == source_package:
                    continue
                if rule_applies(source_package, target_package, relative):
                    sink.add((relative, source_package, target_package))
    return sorted(eager), sorted(lazy - eager)


def scan_reverse_edges(root: Path) -> list[Edge]:
    """Return enforced reverse edges: import-time placements only."""

    return _scan_reverse_edges_by_placement(root)[0]


def scan_lazy_reverse_edges(root: Path) -> list[Edge]:
    """Return advisory reverse edges that only exist inside function bodies."""

    return _scan_reverse_edges_by_placement(root)[1]


def _parse_edge_list(raw: object, *, field: str) -> list[Edge]:
    """Validate one baseline edge array and return it as sorted unique edges."""

    if not isinstance(raw, list):
        raise BaselineError(f"baseline.{field} must be a list")

    edges: list[Edge] = []
    seen: set[Edge] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise BaselineError(f"baseline.{field}[{index}] must be an object")
        path_value = item.get("path")
        from_package = item.get("from_package")
        to_package = item.get("to_package")
        if not isinstance(path_value, str) or not path_value:
            raise BaselineError(
                f"baseline.{field}[{index}].path must be a non-empty string"
            )
        if not isinstance(from_package, str) or not from_package:
            raise BaselineError(
                f"baseline.{field}[{index}].from_package must be a non-empty string"
            )
        if not isinstance(to_package, str) or not to_package:
            raise BaselineError(
                f"baseline.{field}[{index}].to_package must be a non-empty string"
            )
        if not rule_applies(from_package, to_package, path_value):
            raise BaselineError(
                f"baseline.{field}[{index}] is not a configured reverse rule: "
                f"{from_package} -> {to_package} at {path_value}"
            )
        edge = (path_value, from_package, to_package)
        if edge in seen:
            raise BaselineError(f"duplicate baseline {field} entry: {edge}")
        seen.add(edge)
        edges.append(edge)

    if edges != sorted(edges):
        raise BaselineError(f"baseline.{field} must be sorted lexicographically")
    return edges


def load_lazy_inventory(path: Path) -> list[Edge]:
    """Load the advisory function-local reverse-import inventory.

    This section is observational: it is never enforced, never counted against
    ``hard_ceiling``, and absent in baselines written before it existed. A
    section that is present but malformed is still a hard error — advisory
    applies to drift, not to a baseline the guard cannot parse.
    """

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BaselineError(f"baseline file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BaselineError(f"baseline is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise BaselineError("baseline root must be an object")

    raw = payload.get("lazy_exceptions")
    if raw is None:
        return []
    edges = _parse_edge_list(raw, field="lazy_exceptions")

    declared_count = payload.get("lazy_exception_count")
    if declared_count is not None and declared_count != len(edges):
        raise BaselineError(
            f"baseline.lazy_exception_count {declared_count!r} does not match "
            f"len(lazy_exceptions)={len(edges)}"
        )
    return edges


def diff_lazy_inventory(
    current: Sequence[Edge], recorded: Sequence[Edge]
) -> Tuple[list[Edge], list[Edge]]:
    """Return ``(newly appeared, no longer present)`` for two lazy edge lists.

    Pure set arithmetic so callers that already hold both sides do not trigger
    another full-tree scan.
    """

    current_set = set(current)
    recorded_set = set(recorded)
    return sorted(current_set - recorded_set), sorted(recorded_set - current_set)


def lazy_inventory_drift(
    root: Path, baseline_path: Path
) -> Tuple[list[Edge], list[Edge]]:
    """Return ``(newly appeared, no longer present)`` advisory lazy edges.

    Advisory only: drift is reported as ``NOTE:`` output and never changes the
    guard's exit code. Nothing in CI pins this to an empty result.
    """

    return diff_lazy_inventory(
        scan_lazy_reverse_edges(root), load_lazy_inventory(baseline_path)
    )


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

    edges = _parse_edge_list(exceptions_raw, field="exceptions")

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


def serialize_baseline(
    edges: Sequence[Edge],
    hard_ceiling: int,
    lazy_edges: Sequence[Edge] = (),
) -> str:
    ordered = sorted(edges)
    ordered_lazy = sorted(set(lazy_edges))
    if len(ordered) > hard_ceiling:
        raise BaselineError(
            f"refusing to serialize {len(ordered)} exceptions above hard_ceiling "
            f"{hard_ceiling}"
        )
    payload = {
        "version": BASELINE_VERSION,
        "description": (
            "Allowlisted reverse layer-import edges (import-time imports: the "
            "module body plus nested bodies that execute during import, "
            "including class bodies; function-body and `if TYPE_CHECKING:` "
            "imports are excluded). New reverse edges are banned; shrink this "
            "list after breaking a dependency and running --write-baseline. "
            "Growth is refused. Never raise hard_ceiling to green CI — fix "
            "the reverse import."
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
        "lazy_description": (
            "Advisory inventory of reverse imports that exist only inside "
            "function bodies (deferred loads). These are NOT enforced and NOT "
            "counted against hard_ceiling; they are recorded so growth in the "
            "uncounted escape hatch stays observable. Drift here never fails "
            "CI; it only prints NOTE lines. Entries whose (path, from_package, "
            "to_package) triple is also a currently scanned import-time reverse "
            "edge are omitted as duplicates."
        ),
        "lazy_exception_count": len(ordered_lazy),
        "lazy_exceptions": [
            {
                "path": path,
                "from_package": from_package,
                "to_package": to_package,
            }
            for path, from_package, to_package in ordered_lazy
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
    baseline = load_baseline(baseline_path)
    hard_ceiling = _read_hard_ceiling(baseline_path)
    current = scan_reverse_edges(root)
    return _evaluate_reverse_edges(current, baseline, hard_ceiling)


def _evaluate_reverse_edges(
    current: Sequence[Edge], baseline: Sequence[Edge], hard_ceiling: int
) -> list[Violation]:
    """Compare scanned import-time reverse edges against the enforced baseline.

    Split out of ``collect_violations`` so ``main`` can reuse the single
    placement scan it already needs for the advisory inventory instead of
    walking the tree again.
    """

    allowed = set(baseline)
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
        if (path, from_package, to_package) in allowed:
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
    """Rewrite the baseline from the current tree (shrink-only for enforcement).

    The advisory ``lazy_exceptions`` section is always regenerated from the
    scan, so this path repairs a malformed advisory section rather than
    refusing it. The checking run — the one CI executes — still fails closed on
    a ``lazy_exceptions`` block it cannot parse.
    """

    current, current_lazy = _scan_reverse_edges_by_placement(root)
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
            serialize_baseline(
                current, hard_ceiling=hard_ceiling, lazy_edges=current_lazy
            ),
            encoding="utf-8",
        )
    except BaselineError as exc:
        print(f"[layer-direction] ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"[layer-direction] wrote {len(current)} reverse-edge exception(s) to "
        f"{baseline_path} (hard_ceiling={hard_ceiling}, "
        f"{len(current_lazy)} advisory lazy edge(s))"
    )
    return 0


def _run_placement_self_tests() -> int:
    """Cover import placement: nested-but-eager, TYPE_CHECKING, and lazy edges."""

    cases = 0
    with tempfile.TemporaryDirectory(prefix="layer-direction-placement-") as tmp:
        root = Path(tmp)
        (root / "src" / "services").mkdir(parents=True)
        (root / "src" / "data_provider").mkdir(parents=True)
        (root / "scripts").mkdir()
        (root / "src" / "services" / "svc.py").write_text("VALUE = 1\n", encoding="utf-8")

        baseline_path = root / "scripts" / "layer_direction_baseline.json"
        baseline_path.write_text(
            serialize_baseline([], hard_ceiling=0), encoding="utf-8"
        )
        probe = root / "src" / "data_provider" / "probe.py"
        edge = ("src/data_provider/probe.py", "src.data_provider", "src.services")

        eager_placements = {
            "try": (
                "try:\n"
                "    from src.services.svc import VALUE\n"
                "except ImportError:\n"
                "    VALUE = None\n"
            ),
            "except": (
                "try:\n"
                "    VALUE = 0\n"
                "except ImportError:\n"
                "    from src.services.svc import VALUE\n"
            ),
            "try-finally": (
                "try:\n"
                "    VALUE = 0\n"
                "finally:\n"
                "    from src.services.svc import VALUE\n"
            ),
            "if": (
                "import os\n"
                "if os.environ.get('X'):\n"
                "    from src.services.svc import VALUE\n"
            ),
            "if-else": (
                "import os\n"
                "if os.environ.get('X'):\n"
                "    VALUE = 0\n"
                "else:\n"
                "    from src.services.svc import VALUE\n"
            ),
            "with": (
                "from contextlib import suppress\n"
                "with suppress(ImportError):\n"
                "    from src.services.svc import VALUE\n"
            ),
            "for": (
                "for _ in range(1):\n"
                "    from src.services.svc import VALUE\n"
            ),
            "match": (
                "MODE = 'a'\n"
                "match MODE:\n"
                "    case 'a':\n"
                "        from src.services.svc import VALUE\n"
                "    case _:\n"
                "        VALUE = None\n"
            ),
            "class-body": (
                "class Loader:\n"
                "    from src.services.svc import VALUE\n"
            ),
        }
        for label, source in eager_placements.items():
            probe.write_text(source, encoding="utf-8")
            if edge not in scan_reverse_edges(root):
                raise AssertionError(f"nested eager import missed: {label}")
            violations = collect_violations(root, baseline_path)
            if not any(
                item.rule == "new-reverse-edge" and item.path == edge[0]
                for item in violations
            ):
                raise AssertionError(f"nested eager import not rejected: {label}")
            if scan_lazy_reverse_edges(root):
                raise AssertionError(f"eager import leaked into lazy inventory: {label}")
            cases += 1

        type_checking_placements = {
            "plain": (
                "from typing import TYPE_CHECKING\n"
                "if TYPE_CHECKING:\n"
                "    from src.services.svc import VALUE\n"
            ),
            "alias": (
                "from typing import TYPE_CHECKING as TC\n"
                "if TC:\n"
                "    from src.services.svc import VALUE\n"
            ),
            "module-attribute": (
                "import typing\n"
                "if typing.TYPE_CHECKING:\n"
                "    from src.services.svc import VALUE\n"
            ),
            "typing-extensions": (
                "from typing_extensions import TYPE_CHECKING\n"
                "if TYPE_CHECKING:\n"
                "    from src.services.svc import VALUE\n"
            ),
        }
        for label, source in type_checking_placements.items():
            probe.write_text(source, encoding="utf-8")
            if scan_reverse_edges(root):
                raise AssertionError(f"TYPE_CHECKING import counted: {label}")
            if collect_violations(root, baseline_path):
                raise AssertionError(f"TYPE_CHECKING import produced violation: {label}")
            cases += 1

        # A rebound TYPE_CHECKING name is not the typing sentinel.
        probe.write_text(
            "from typing import TYPE_CHECKING\n"
            "TYPE_CHECKING = True\n"
            "if TYPE_CHECKING:\n"
            "    from src.services.svc import VALUE\n",
            encoding="utf-8",
        )
        if edge not in scan_reverse_edges(root):
            raise AssertionError("rebound TYPE_CHECKING still suppressed the edge")
        cases += 1

        # Function-local imports stay out of enforcement and land in the advisory list.
        probe.write_text(
            "def load():\n"
            "    from src.services.svc import VALUE\n"
            "    return VALUE\n",
            encoding="utf-8",
        )
        if scan_reverse_edges(root):
            raise AssertionError("function-body import treated as enforced edge")
        if collect_violations(root, baseline_path):
            raise AssertionError("function-body import produced a violation")
        if scan_lazy_reverse_edges(root) != [edge]:
            raise AssertionError(
                f"lazy inventory missed the deferred load: "
                f"{scan_lazy_reverse_edges(root)!r}"
            )
        cases += 1

        # Advisory drift is reported against the recorded inventory.
        added, removed = lazy_inventory_drift(root, baseline_path)
        if added != [edge] or removed:
            raise AssertionError(f"unexpected lazy drift: {added!r} / {removed!r}")
        if write_baseline(root, baseline_path) != 0:
            raise AssertionError("write-baseline refused an advisory-only refresh")
        if load_lazy_inventory(baseline_path) != [edge]:
            raise AssertionError("lazy inventory was not persisted")
        if lazy_inventory_drift(root, baseline_path) != ([], []):
            raise AssertionError("lazy drift survived a baseline refresh")
        if load_baseline(baseline_path):
            raise AssertionError("advisory lazy edge leaked into enforced exceptions")
        cases += 1

        # The same file with both placements reports the edge once, eager only.
        # The baseline written just above holds zero enforced exceptions, so the
        # only thing that can suppress the lazy copy is the *scanned* import-time
        # set — this pins the dedupe to the measurement, not to `exceptions`.
        probe.write_text(
            "from src.services.svc import VALUE\n"
            "def load():\n"
            "    from src.services.svc import VALUE as OTHER\n"
            "    return OTHER\n",
            encoding="utf-8",
        )
        if load_baseline(baseline_path):
            raise AssertionError("dedupe fixture expected an empty enforced baseline")
        if scan_reverse_edges(root) != [edge]:
            raise AssertionError("duplicate placements did not collapse to one edge")
        if scan_lazy_reverse_edges(root):
            raise AssertionError(
                "edge scanned as import-time was duplicated in the lazy inventory"
            )
        cases += 1

        # A baseline without the advisory section still loads (backward compatible).
        legacy = root / "scripts" / "legacy_baseline.json"
        payload = json.loads(baseline_path.read_text(encoding="utf-8"))
        payload.pop("lazy_exceptions", None)
        payload.pop("lazy_exception_count", None)
        legacy.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        if load_lazy_inventory(legacy) != []:
            raise AssertionError("missing advisory section was not tolerated")
        cases += 1

    return cases


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

    cases += _run_placement_self_tests()

    print(f"Layer-direction self-tests passed ({cases} cases).")


def _report_lazy_inventory(
    current: Sequence[Edge], recorded: Sequence[Edge]
) -> None:
    """Print the advisory function-local reverse-import inventory and its drift.

    Never changes the exit code: deferred loads stay outside enforcement, so
    both growth and shrink only emit ``NOTE:`` lines. The notes exist so the
    uncounted escape hatch is visible in CI output instead of being silently
    dropped. Both arguments are precomputed by ``main`` — a malformed
    ``lazy_exceptions`` section has already been rejected through the standard
    ``BaselineError`` path before this printer runs.
    """

    added, removed = diff_lazy_inventory(current, recorded)
    print(
        f"[layer-direction] NOTE: {len(current)} function-local reverse "
        "import(s) tracked as advisory lazy_exceptions (not enforced)"
    )
    for path, from_package, to_package in added:
        print(
            f"[layer-direction] NOTE: lazy-inventory-growth: {path}: "
            f"{from_package} -> {to_package}: a deferred load added reverse "
            "coupling that the ratchet does not count; prefer extracting a leaf "
            "utility, then run --write-baseline to refresh the advisory list"
        )
    for path, from_package, to_package in removed:
        print(
            f"[layer-direction] NOTE: lazy-inventory-shrink: {path}: "
            f"{from_package} -> {to_package}: no longer present; run "
            "--write-baseline to refresh the advisory list"
        )


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

    # Load and validate every baseline section — enforced and advisory — before
    # anything is reported, so a malformed `lazy_exceptions` block fails closed
    # through the standard invalid-baseline line instead of escaping as a
    # traceback from the reporter further down.
    try:
        baseline = load_baseline(baseline_path)
        recorded_lazy = load_lazy_inventory(baseline_path)
        hard_ceiling = _read_hard_ceiling(baseline_path)
    except BaselineError as exc:
        print(
            f"[layer-direction] ERROR: invalid-baseline: {exc}",
            file=sys.stderr,
        )
        return 1

    current, current_lazy = _scan_reverse_edges_by_placement(root)
    violations = _evaluate_reverse_edges(current, baseline, hard_ceiling)

    if violations:
        for violation in violations:
            print(f"[layer-direction] ERROR: {violation.render()}", file=sys.stderr)
        print(
            "[layer-direction] HINT: break the reverse import or see "
            "docs/layer-direction-ratchet.md for the legitimate-change path",
            file=sys.stderr,
        )
        return 1

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
    _report_lazy_inventory(current_lazy, recorded_lazy)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
