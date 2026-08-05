#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Ratcheting guard: ban new production imports of ADR-006 legacy facades.

Scans production Python under ``src/``, ``data_provider/``, ``api/``, ``bot/``,
plus top-level entrypoints. Known legacy facade modules remain importable only
from paths listed in the checked-in baseline. Tests and docs are out of scope.

New production imports fail CI. Removing an importer does not fail the check;
run ``--write-baseline`` after a deliberate migration to shrink the allowlist.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Sequence


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = ROOT / "scripts" / "legacy_facade_import_baseline.json"
BASELINE_VERSION = 1

# Legacy compatibility shims (facade module) -> canonical implementation package.
LEGACY_FACADES: Mapping[str, str] = {
    "src.market_context": "src.market.context",
    "src.market_phase_prompt": "src.market.phase_prompt",
    "src.market_phase_summary": "src.market.phase_summary",
    "src.market_structure_prompt": "src.market.structure_prompt",
    "src.market_sector_analysis": "src.market.sector_analysis",
    "src.market_analyzer": "src.market.analyzer",
    "src.analysis_context_pack_overview": "src.analysis_context_pack.overview",
    "src.analysis_context_pack_prompt": "src.analysis_context_pack.prompt",
    "src.notification_sender": "src.notification_parts.senders",
    "src.notification_sender.astrbot_sender": "src.notification_parts.senders.astrbot_sender",
    "src.notification_sender.custom_webhook_sender": "src.notification_parts.senders.custom_webhook_sender",
    "src.notification_sender.dingtalk_sender": "src.notification_parts.senders.dingtalk_sender",
    "src.notification_sender.discord_sender": "src.notification_parts.senders.discord_sender",
    "src.notification_sender.email_sender": "src.notification_parts.senders.email_sender",
    "src.notification_sender.feishu_sender": "src.notification_parts.senders.feishu_sender",
    "src.notification_sender.gotify_sender": "src.notification_parts.senders.gotify_sender",
    "src.notification_sender.ntfy_sender": "src.notification_parts.senders.ntfy_sender",
    "src.notification_sender.pushover_sender": "src.notification_parts.senders.pushover_sender",
    "src.notification_sender.pushplus_sender": "src.notification_parts.senders.pushplus_sender",
    "src.notification_sender.serverchan3_sender": "src.notification_parts.senders.serverchan3_sender",
    "src.notification_sender.slack_sender": "src.notification_parts.senders.slack_sender",
    "src.notification_sender.telegram_sender": "src.notification_parts.senders.telegram_sender",
    "src.notification_sender.wechat_sender": "src.notification_parts.senders.wechat_sender",
}

# Shim files that re-export the canonical package; they are not importers of
# themselves for allowlist purposes.
FACADE_DEFINITION_FILES: Mapping[str, str] = {
    "src.market_context": "src/market_context.py",
    "src.market_phase_prompt": "src/market_phase_prompt.py",
    "src.market_phase_summary": "src/market_phase_summary.py",
    "src.market_structure_prompt": "src/market_structure_prompt.py",
    "src.market_sector_analysis": "src/market_sector_analysis.py",
    "src.market_analyzer": "src/market_analyzer.py",
    "src.analysis_context_pack_overview": "src/analysis_context_pack_overview.py",
    "src.analysis_context_pack_prompt": "src/analysis_context_pack_prompt.py",
    "src.notification_sender": "src/notification_sender/__init__.py",
    "src.notification_sender.astrbot_sender": "src/notification_sender/astrbot_sender.py",
    "src.notification_sender.custom_webhook_sender": "src/notification_sender/custom_webhook_sender.py",
    "src.notification_sender.dingtalk_sender": "src/notification_sender/dingtalk_sender.py",
    "src.notification_sender.discord_sender": "src/notification_sender/discord_sender.py",
    "src.notification_sender.email_sender": "src/notification_sender/email_sender.py",
    "src.notification_sender.feishu_sender": "src/notification_sender/feishu_sender.py",
    "src.notification_sender.gotify_sender": "src/notification_sender/gotify_sender.py",
    "src.notification_sender.ntfy_sender": "src/notification_sender/ntfy_sender.py",
    "src.notification_sender.pushover_sender": "src/notification_sender/pushover_sender.py",
    "src.notification_sender.pushplus_sender": "src/notification_sender/pushplus_sender.py",
    "src.notification_sender.serverchan3_sender": "src/notification_sender/serverchan3_sender.py",
    "src.notification_sender.slack_sender": "src/notification_sender/slack_sender.py",
    "src.notification_sender.telegram_sender": "src/notification_sender/telegram_sender.py",
    "src.notification_sender.wechat_sender": "src/notification_sender/wechat_sender.py",
}

PRODUCTION_ROOTS = ("src", "data_provider", "api", "bot")
PRODUCTION_FILES = ("main.py", "server.py", "webui.py")


@dataclass(frozen=True, order=True)
class Violation:
    """One unexplained production facade import."""

    path: str
    line: int
    facade: str
    message: str

    def render(self) -> str:
        location = self.path if self.line <= 0 else f"{self.path}:{self.line}"
        return f"{location}: {self.facade}: {self.message}"


@dataclass(frozen=True)
class ImportHit:
    """One production import of a legacy facade module."""

    path: str
    line: int
    facade: str


class BaselineError(ValueError):
    """Raised when the checked-in baseline is malformed."""


def _relative_to_root(root: Path, path: Path) -> str:
    """Return a stable POSIX path relative to the repository root."""

    return path.resolve().relative_to(root.resolve()).as_posix()


def _iter_production_python(root: Path):
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


def _is_facade_definition(relative_path: str) -> bool:
    """Return True when the file is a listed legacy facade shim."""

    return relative_path in FACADE_DEFINITION_FILES.values()


def _facade_for_module(module_name: str | None) -> str | None:
    """Map an imported module name to a guarded legacy facade, if any.

    Prefer the longest matching facade so nested packages such as
    ``src.notification_sender.email_sender`` are not attributed to the parent
    package facade ``src.notification_sender``.
    """

    if not module_name:
        return None
    matches = [
        facade
        for facade in LEGACY_FACADES
        if module_name == facade or module_name.startswith(facade + ".")
    ]
    if not matches:
        return None
    return max(matches, key=len)


def _facade_from_import_from(node: ast.ImportFrom) -> list[tuple[str, int]]:
    """Resolve legacy facades referenced by a ``from ... import ...`` statement."""

    hits: list[tuple[str, int]] = []
    module = node.module or ""
    if node.level and not module:
        return hits

    direct = _facade_for_module(module)
    if direct is not None:
        hits.append((direct, node.lineno))
        return hits

    # ``from src import market_context`` binds the facade package attribute.
    if module == "src":
        for alias in node.names:
            facade = _facade_for_module(f"src.{alias.name}")
            if facade is not None:
                hits.append((facade, node.lineno))
    return hits


def _scan_file(root: Path, path: Path) -> list[ImportHit]:
    """Collect legacy facade imports from one production Python file."""

    relative = _relative_to_root(root, path)
    if _is_facade_definition(relative):
        return []
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        tree = ast.parse(source, filename=relative)
    except SyntaxError:
        return []

    hits: list[ImportHit] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                facade = _facade_for_module(alias.name)
                if facade is not None:
                    hits.append(ImportHit(relative, node.lineno, facade))
        elif isinstance(node, ast.ImportFrom):
            for facade, line in _facade_from_import_from(node):
                hits.append(ImportHit(relative, line, facade))
    return hits


def scan_repository(root: Path) -> list[ImportHit]:
    """Scan production sources for legacy facade imports."""

    hits: list[ImportHit] = []
    for path in _iter_production_python(root):
        hits.extend(_scan_file(root, path))
    hits.sort(key=lambda item: (item.facade, item.path, item.line))
    return hits


def current_importer_map(hits: Sequence[ImportHit]) -> Dict[str, list[str]]:
    """Group importer paths by facade module."""

    mapping: Dict[str, set[str]] = {facade: set() for facade in LEGACY_FACADES}
    for hit in hits:
        mapping.setdefault(hit.facade, set()).add(hit.path)
    return {
        facade: sorted(paths)
        for facade, paths in sorted(mapping.items())
        if paths
    }


def load_baseline(path: Path) -> Dict[str, list[str]]:
    """Load the checked-in allowlist of production facade importers."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BaselineError(f"baseline file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BaselineError(f"baseline is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise BaselineError("baseline root must be an object")
    version = payload.get("version")
    if version != BASELINE_VERSION:
        raise BaselineError(
            f"unsupported baseline version {version!r}; expected {BASELINE_VERSION}"
        )
    facades = payload.get("facades")
    if not isinstance(facades, dict):
        raise BaselineError("baseline.facades must be an object")

    result: Dict[str, list[str]] = {}
    for facade, importers in facades.items():
        if facade not in LEGACY_FACADES:
            raise BaselineError(f"unknown facade in baseline: {facade}")
        if not isinstance(importers, list) or not all(
            isinstance(item, str) for item in importers
        ):
            raise BaselineError(f"baseline importers for {facade} must be a string list")
        result[facade] = sorted(set(importers))
    return result


def serialize_baseline(importer_map: Mapping[str, Sequence[str]]) -> str:
    """Render the baseline JSON document with a stable schema."""

    catalog = {
        facade: {
            "canonical": LEGACY_FACADES[facade],
            "definition": FACADE_DEFINITION_FILES[facade],
            "importers": sorted(set(importer_map.get(facade, ()))),
        }
        for facade in sorted(LEGACY_FACADES)
    }
    payload = {
        "version": BASELINE_VERSION,
        "description": (
            "Allowlisted production importers of ADR-006 legacy facade modules. "
            "New production imports must use the canonical package and must not "
            "expand this list without an explicit migration plan."
        ),
        "facades": {
            facade: entry["importers"]
            for facade, entry in catalog.items()
        },
        "catalog": catalog,
    }
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def collect_violations(root: Path, baseline_path: Path) -> list[Violation]:
    """Return violations for production imports outside the baseline allowlist."""

    baseline = load_baseline(baseline_path)
    hits = scan_repository(root)
    allowed = {facade: set(paths) for facade, paths in baseline.items()}
    for facade in LEGACY_FACADES:
        allowed.setdefault(facade, set())

    violations: list[Violation] = []
    seen: set[tuple[str, str]] = set()
    for hit in hits:
        key = (hit.facade, hit.path)
        if key in seen:
            continue
        seen.add(key)
        if hit.path in allowed.get(hit.facade, set()):
            continue
        canonical = LEGACY_FACADES[hit.facade]
        violations.append(
            Violation(
                path=hit.path,
                line=hit.line,
                facade=hit.facade,
                message=(
                    "new production import of legacy facade is banned; "
                    f"import {canonical!r} instead, or document a temporary "
                    "allowlist update with an explicit retirement plan"
                ),
            )
        )
    return sorted(violations)


def write_baseline(root: Path, baseline_path: Path) -> int:
    """Rewrite the allowlist from the current production import inventory."""

    hits = scan_repository(root)
    importer_map = current_importer_map(hits)
    for facade in LEGACY_FACADES:
        importer_map.setdefault(facade, [])
    baseline_path.write_text(serialize_baseline(importer_map), encoding="utf-8")
    total = sum(len(paths) for paths in importer_map.values())
    print(
        f"[legacy-facade-import] wrote {total} allowlisted importer path(s) "
        f"across {len(LEGACY_FACADES)} facades to {baseline_path}"
    )
    return 0


def run_self_tests() -> None:
    """Exercise allowlist expansion and baseline parsing on a temp tree."""

    cases = 0
    with tempfile.TemporaryDirectory(prefix="legacy-facade-import-") as tmp:
        root = Path(tmp)
        (root / "src").mkdir()
        (root / "src" / "market").mkdir()
        (root / "scripts").mkdir()

        (root / "src" / "market" / "context.py").write_text(
            "def detect_market(code):\n    return 'cn'\n",
            encoding="utf-8",
        )
        (root / "src" / "market_context.py").write_text(
            "from src.market.context import detect_market\n",
            encoding="utf-8",
        )
        (root / "src" / "analyzer.py").write_text(
            "from src.market_context import detect_market\n",
            encoding="utf-8",
        )
        (root / "src" / "services").mkdir()
        (root / "src" / "services" / "ok.py").write_text(
            "from src.market.context import detect_market\n",
            encoding="utf-8",
        )

        baseline_path = root / "scripts" / "legacy_facade_import_baseline.json"
        hits = scan_repository(root)
        importer_map = current_importer_map(hits)
        baseline_path.write_text(serialize_baseline(importer_map), encoding="utf-8")
        violations = collect_violations(root, baseline_path)
        if violations:
            raise AssertionError(f"clean tree produced violations: {violations!r}")
        cases += 1

        (root / "src" / "new_caller.py").write_text(
            "from src.market_context import detect_market\n",
            encoding="utf-8",
        )
        violations = collect_violations(root, baseline_path)
        if not any(item.path == "src/new_caller.py" for item in violations):
            raise AssertionError(f"new importer was not rejected: {violations!r}")
        cases += 1

        (root / "src" / "attr_import.py").write_text(
            "from src import market_context\n",
            encoding="utf-8",
        )
        violations = collect_violations(root, baseline_path)
        if not any(item.path == "src/attr_import.py" for item in violations):
            raise AssertionError(f"attribute import was not rejected: {violations!r}")
        cases += 1

        (root / "tests").mkdir()
        (root / "tests" / "test_facade.py").write_text(
            "from src.market_context import detect_market\n",
            encoding="utf-8",
        )
        hits = scan_repository(root)
        if any(hit.path.startswith("tests/") for hit in hits):
            raise AssertionError(f"tests were scanned: {hits!r}")
        cases += 1

        bad = {
            "version": BASELINE_VERSION,
            "facades": {"src.not_a_facade": ["src/analyzer.py"]},
        }
        bad_path = root / "scripts" / "bad_baseline.json"
        bad_path.write_text(json.dumps(bad), encoding="utf-8")
        try:
            load_baseline(bad_path)
        except BaselineError:
            cases += 1
        else:
            raise AssertionError("unknown facade was accepted")

        # Nested notification_sender package/leaf facades: new leaf importers fail,
        # and longest-match keeps leaf imports off the package allowlist.
        (root / "src" / "notification_parts").mkdir()
        (root / "src" / "notification_parts" / "senders").mkdir()
        (root / "src" / "notification_parts" / "senders" / "email_sender.py").write_text(
            "class EmailSender:\n    pass\n",
            encoding="utf-8",
        )
        (root / "src" / "notification_sender").mkdir()
        (root / "src" / "notification_sender" / "__init__.py").write_text(
            "from .email_sender import EmailSender\n",
            encoding="utf-8",
        )
        (root / "src" / "notification_sender" / "email_sender.py").write_text(
            "from src.notification_parts.senders.email_sender import EmailSender\n",
            encoding="utf-8",
        )
        sender_baseline = {
            "version": BASELINE_VERSION,
            "facades": {
                "src.notification_sender": ["src/notification.py"],
                "src.notification_sender.email_sender": [],
            },
        }
        sender_baseline_path = root / "scripts" / "sender_baseline.json"
        sender_baseline_path.write_text(json.dumps(sender_baseline), encoding="utf-8")
        (root / "src" / "notification.py").write_text(
            "from src.notification_sender import EmailSender\n",
            encoding="utf-8",
        )
        # grandfathered package importer is clean
        violations = collect_violations(root, sender_baseline_path)
        if any(item.path == "src/notification.py" for item in violations):
            raise AssertionError(
                f"grandfathered package importer rejected: {violations!r}"
            )
        cases += 1

        (root / "src" / "new_sender_caller.py").write_text(
            "from src.notification_sender.email_sender import EmailSender\n",
            encoding="utf-8",
        )
        violations = collect_violations(root, sender_baseline_path)
        leaf_hits = [
            item
            for item in violations
            if item.path == "src/new_sender_caller.py"
            and item.facade == "src.notification_sender.email_sender"
        ]
        if not leaf_hits:
            raise AssertionError(
                f"new notification_sender leaf importer was not rejected "
                f"as leaf facade: {violations!r}"
            )
        cases += 1

    print(f"Legacy facade import self-tests passed ({cases} cases).")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI options."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Rewrite the production importer allowlist from the current tree.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run isolated guard regression cases and exit.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the legacy facade import guard."""

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
                f"[legacy-facade-import] ERROR: invalid-baseline: {exc}",
                file=sys.stderr,
            )
            return 1

    try:
        violations = collect_violations(root, baseline_path)
    except BaselineError as exc:
        print(
            f"[legacy-facade-import] ERROR: invalid-baseline: {exc}",
            file=sys.stderr,
        )
        return 1

    if violations:
        for violation in violations:
            print(
                f"[legacy-facade-import] ERROR: {violation.render()}",
                file=sys.stderr,
            )
        return 1

    baseline = load_baseline(baseline_path)
    total = sum(len(paths) for paths in baseline.values())
    print(
        f"[legacy-facade-import] OK: {total} allowlisted production importer "
        f"path(s) across {len(LEGACY_FACADES)} legacy facades"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
