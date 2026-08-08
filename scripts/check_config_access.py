#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Ratcheting guard: ban unexplained growth of direct ``get_config()`` call sites.

Scans production Python under ``src/``, ``data_provider/``, ``api/``, ``bot/``,
plus top-level entrypoints. Counts bare ``get_config()`` calls (AST ``Name``
callees only) per module. Attribute calls such as
``system_config_service.get_config(...)`` are intentionally out of scope —
they are a different API surface.

``src/config.py`` (accessor definition) and ``src/application_services.py``
(composition-root lazy fallback) are excluded: the preferred path for new and
touched code is constructor/param injection or
``get_application_services().config`` (ADR-003 / ADR-011).

Known counts live in the checked-in baseline. New modules or higher per-module
counts fail CI. Lower counts do not fail; run ``--write-baseline`` after a
deliberate conversion to shrink the inventory. ``--write-baseline`` refuses
growth relative to the existing baseline.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = ROOT / "scripts" / "config_access_baseline.json"
BASELINE_VERSION = 1

PRODUCTION_ROOTS = ("src", "data_provider", "api", "bot")
PRODUCTION_FILES = ("main.py", "server.py", "webui.py")

# Composition-root and config definition may still call get_config().
EXCLUDED_RELATIVE_PATHS = frozenset(
    {
        "src/config.py",
        "src/application_services.py",
    }
)


class BaselineError(ValueError):
    """Raised when the checked-in baseline is malformed."""


@dataclass(frozen=True, order=True)
class Violation:
    """One unexplained direct-config access growth."""

    rule: str
    path: str
    message: str
    line: int = 0

    def render(self) -> str:
        location = self.path if self.line <= 0 else f"{self.path}:{self.line}"
        return f"{location}: {self.rule}: {self.message}"


@dataclass(frozen=True)
class CallSite:
    """One bare ``get_config()`` call in a production module."""

    path: str
    line: int


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


def count_get_config_calls(source: str) -> list[int]:
    """Return line numbers of bare ``get_config()`` calls in *source*."""

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "get_config":
            lines.append(getattr(node, "lineno", 0) or 0)
    return lines


def scan_module_counts(root: Path) -> Dict[str, int]:
    """Return per-module bare ``get_config()`` counts for production code."""

    counts: Dict[str, int] = {}
    for path in _iter_production_python(root):
        relative = _relative_to_root(root, path)
        if relative in EXCLUDED_RELATIVE_PATHS:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        sites = count_get_config_calls(source)
        if sites:
            counts[relative] = len(sites)
    return dict(sorted(counts.items()))


def scan_call_sites(root: Path) -> list[CallSite]:
    """Return every bare ``get_config()`` site with path and line."""

    sites: list[CallSite] = []
    for path in _iter_production_python(root):
        relative = _relative_to_root(root, path)
        if relative in EXCLUDED_RELATIVE_PATHS:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in count_get_config_calls(source):
            sites.append(CallSite(path=relative, line=line))
    return sorted(sites)


def load_baseline(path: Path) -> Dict[str, int]:
    """Load the checked-in per-module allowlist of direct ``get_config()`` counts."""

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
    modules_raw = payload.get("modules")
    if not isinstance(modules_raw, dict):
        raise BaselineError("baseline.modules must be an object")

    modules: Dict[str, int] = {}
    for key, value in modules_raw.items():
        if not isinstance(key, str) or not key:
            raise BaselineError("baseline.modules keys must be non-empty strings")
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise BaselineError(
                f"baseline.modules[{key!r}] must be a positive integer count"
            )
        modules[key] = value

    ordered_keys = sorted(modules)
    if list(modules.keys()) != ordered_keys:
        raise BaselineError("baseline.modules keys must be sorted lexicographically")

    total = payload.get("total_sites")
    if total is not None and total != sum(modules.values()):
        raise BaselineError(
            f"baseline.total_sites ({total}) does not match sum of module "
            f"counts ({sum(modules.values())})"
        )
    return modules


def serialize_baseline(modules: Mapping[str, int]) -> str:
    """Render the baseline JSON document with a stable schema."""

    ordered = {path: count for path, count in sorted(modules.items()) if count > 0}
    total = sum(ordered.values())
    payload = {
        "version": BASELINE_VERSION,
        "description": (
            "Per-module counts of bare get_config() call sites in production "
            "code (AST Name callees only). Attribute calls such as "
            "service.get_config(...) are out of scope. src/config.py and "
            "src/application_services.py are excluded. New modules or higher "
            "counts are banned; shrink this map by converting callers to "
            "constructor/param injection or get_application_services().config "
            "and running --write-baseline. Growth requires an explicit PR "
            "justification and is refused by --write-baseline."
        ),
        "total_sites": total,
        "module_count": len(ordered),
        "modules": ordered,
    }
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def collect_violations(root: Path, baseline_path: Path) -> list[Violation]:
    """Return violations for modules that grew or appeared outside the baseline."""

    baseline = load_baseline(baseline_path)
    current = scan_module_counts(root)
    violations: list[Violation] = []

    for path, count in sorted(current.items()):
        allowed = baseline.get(path, 0)
        if count > allowed:
            if path not in baseline:
                rule = "new-module-get-config"
                message = (
                    f"module introduces {count} bare get_config() call site(s); "
                    "prefer constructor/param injection or "
                    "get_application_services().config (see "
                    "docs/config-access-ratchet.md). New direct-config access is "
                    "banned without an intentional baseline edit and PR "
                    "justification (--write-baseline refuses growth)"
                )
            else:
                rule = "get-config-count-growth"
                message = (
                    f"bare get_config() count grew from {allowed} to {count}; "
                    "convert new call sites to injection / composition-root "
                    "access or document an intentional baseline update "
                    "(manual edit only — --write-baseline refuses growth)"
                )
            violations.append(
                Violation(rule=rule, path=path, message=message)
            )
    return sorted(violations)


def write_baseline(root: Path, baseline_path: Path) -> int:
    """Rewrite the per-module allowlist from the current tree, refusing growth."""

    current = scan_module_counts(root)
    if baseline_path.is_file():
        try:
            existing = load_baseline(baseline_path)
        except BaselineError as exc:
            print(
                f"[config-access] ERROR: invalid-baseline: {exc}",
                file=sys.stderr,
            )
            return 1
        growth: list[Violation] = []
        for path, count in sorted(current.items()):
            allowed = existing.get(path, 0)
            if count > allowed:
                if path not in existing:
                    message = (
                        "refusing to grow the allowlist via --write-baseline; "
                        "convert the new call sites or manually edit the "
                        "baseline with explicit PR justification"
                    )
                    rule = "baseline-growth"
                else:
                    message = (
                        f"refusing to raise {path} from {allowed} to {count} "
                        "via --write-baseline; convert the extra sites or "
                        "manually edit the baseline with explicit PR "
                        "justification"
                    )
                    rule = "baseline-growth"
                growth.append(Violation(rule=rule, path=path, message=message))
        if growth:
            for violation in growth:
                print(
                    f"[config-access] ERROR: {violation.render()}",
                    file=sys.stderr,
                )
            return 1

    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(serialize_baseline(current), encoding="utf-8")
    total = sum(current.values())
    print(
        f"[config-access] wrote {total} site(s) across {len(current)} module(s) "
        f"to {baseline_path}"
    )
    return 0


def run_self_tests() -> None:
    """Exercise new-site detection, shrink, growth refusal, and baseline parsing."""

    cases = 0
    with tempfile.TemporaryDirectory(prefix="config-access-") as tmp:
        root = Path(tmp)
        (root / "src" / "services").mkdir(parents=True)
        (root / "src").mkdir(exist_ok=True)
        (root / "scripts").mkdir()

        # Composition root and config definition may call get_config freely.
        (root / "src" / "config.py").write_text(
            "def get_config():\n"
            "    return object()\n"
            "\n"
            "def _bootstrap():\n"
            "    return get_config()\n",
            encoding="utf-8",
        )
        (root / "src" / "application_services.py").write_text(
            "def config():\n"
            "    from src.config import get_config\n"
            "    return get_config()\n",
            encoding="utf-8",
        )
        (root / "src" / "services" / "history.py").write_text(
            "from src.config import get_config\n"
            "\n"
            "def load():\n"
            "    return get_config()\n",
            encoding="utf-8",
        )
        # Attribute-style get_config must not count.
        (root / "src" / "services" / "system.py").write_text(
            "class Svc:\n"
            "    def get_config(self):\n"
            "        return {}\n"
            "\n"
            "def read(svc):\n"
            "    return svc.get_config()\n",
            encoding="utf-8",
        )

        counts = scan_module_counts(root)
        if counts != {"src/services/history.py": 1}:
            raise AssertionError(f"unexpected initial counts: {counts!r}")
        cases += 1

        baseline_path = root / "scripts" / "config_access_baseline.json"
        baseline_path.write_text(serialize_baseline(counts), encoding="utf-8")
        if collect_violations(root, baseline_path):
            raise AssertionError("clean tree produced violations")
        cases += 1

        # New site on an existing module → growth violation
        (root / "src" / "services" / "history.py").write_text(
            "from src.config import get_config\n"
            "\n"
            "def load():\n"
            "    a = get_config()\n"
            "    b = get_config()\n"
            "    return a, b\n",
            encoding="utf-8",
        )
        growth_violations = collect_violations(root, baseline_path)
        if not any(v.rule == "get-config-count-growth" for v in growth_violations):
            raise AssertionError(f"count growth not rejected: {growth_violations!r}")
        cases += 1

        # New module → new-module violation
        (root / "src" / "services" / "history.py").write_text(
            "from src.config import get_config\n"
            "\n"
            "def load():\n"
            "    return get_config()\n",
            encoding="utf-8",
        )
        (root / "src" / "services" / "extra.py").write_text(
            "from src.config import get_config\n"
            "\n"
            "def load():\n"
            "    return get_config()\n",
            encoding="utf-8",
        )
        new_mod = collect_violations(root, baseline_path)
        if not any(v.rule == "new-module-get-config" for v in new_mod):
            raise AssertionError(f"new module not rejected: {new_mod!r}")
        cases += 1

        # --write-baseline must refuse growth
        if write_baseline(root, baseline_path) == 0:
            raise AssertionError("write-baseline accepted growth")
        cases += 1

        # Convert both modules → shrink allowed
        (root / "src" / "services" / "history.py").write_text(
            "from src.application_services import get_application_services\n"
            "\n"
            "def load():\n"
            "    return get_application_services().config\n",
            encoding="utf-8",
        )
        (root / "src" / "services" / "extra.py").write_text(
            "def load(config):\n"
            "    return config\n",
            encoding="utf-8",
        )
        shrunk = scan_module_counts(root)
        if shrunk:
            raise AssertionError(f"expected empty counts after conversion: {shrunk!r}")
        if write_baseline(root, baseline_path) != 0:
            raise AssertionError("write-baseline rejected legitimate shrink")
        loaded = load_baseline(baseline_path)
        if loaded:
            raise AssertionError(f"baseline not shrunk: {loaded!r}")
        cases += 1

        # Unsorted baseline keys must fail
        bad = {
            "version": BASELINE_VERSION,
            "total_sites": 1,
            "modules": {"src/z.py": 1, "src/a.py": 1},
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
        (root / "tests" / "test_cfg.py").write_text(
            "from src.config import get_config\n"
            "def test_it():\n"
            "    get_config()\n",
            encoding="utf-8",
        )
        if scan_module_counts(root):
            raise AssertionError(
                f"tests leaked into scan: {scan_module_counts(root)!r}"
            )
        cases += 1

    print(f"Config-access self-tests passed ({cases} cases).")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI options."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help=(
            "Rewrite the per-module get_config allowlist from the current tree. "
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
    """Run the direct-config access ratchet."""

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
                f"[config-access] ERROR: invalid-baseline: {exc}",
                file=sys.stderr,
            )
            return 1

    try:
        violations = collect_violations(root, baseline_path)
    except BaselineError as exc:
        print(
            f"[config-access] ERROR: invalid-baseline: {exc}",
            file=sys.stderr,
        )
        return 1

    if violations:
        for violation in violations:
            print(f"[config-access] ERROR: {violation.render()}", file=sys.stderr)
        print(
            "[config-access] HINT: convert callers to injection / "
            "get_application_services().config or see "
            "docs/config-access-ratchet.md for the legitimate-change path",
            file=sys.stderr,
        )
        return 1

    baseline = load_baseline(baseline_path)
    current = scan_module_counts(root)
    baseline_total = sum(baseline.values())
    current_total = sum(current.values())
    removed = baseline_total - current_total
    note = ""
    if removed > 0:
        note = (
            f" ({removed} baseline site(s) no longer present; "
            "run --write-baseline to shrink the allowlist)"
        )
    print(
        f"[config-access] OK: {current_total} bare get_config() site(s) across "
        f"{len(current)} module(s) within baseline of {baseline_total} "
        f"site(s) / {len(baseline)} module(s){note}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
