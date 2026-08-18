# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Regression checks for the single canonical ``src`` package layout."""

from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
RETIRED_ROOT_PACKAGES = frozenset({"api", "bot", "data_provider"})


def test_retired_root_package_directories_are_absent() -> None:
    for name in ("api", "bot", "data_provider"):
        assert not (ROOT / name).exists()


def test_only_src_is_configured_for_package_discovery() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'include = ["src*"]' in pyproject
    assert 'known_first_party = ["src"]' in pyproject


def test_python_imports_do_not_reference_retired_root_packages() -> None:
    search_roots = (
        ROOT / "src",
        ROOT / "tests",
        ROOT / "scripts",
        ROOT / ".github" / "scripts",
        ROOT / "examples",
        ROOT / "docs" / "examples",
    )
    paths = [path for path in ROOT.glob("*.py") if path.is_file()]
    for search_root in search_roots:
        if search_root.is_dir():
            paths.extend(search_root.rglob("*.py"))

    violations: list[str] = []
    for path in sorted(set(paths)):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: tuple[str, ...] = ()
            if isinstance(node, ast.Import):
                modules = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = (node.module,)
            for module in modules:
                if module.split(".", 1)[0] in RETIRED_ROOT_PACKAGES:
                    relative = path.relative_to(ROOT)
                    violations.append(f"{relative}:{node.lineno}: {module}")

    assert violations == []


def test_canonical_packages_resolve_and_retired_roots_do_not_off_repo_cwd(
    tmp_path: Path,
) -> None:
    script = """
import importlib.util

for name in ("src.api", "src.bot", "src.data_provider"):
    assert importlib.util.find_spec(name) is not None, name

for name in ("api", "bot", "data_provider"):
    assert importlib.util.find_spec(name) is None, name
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT)
    completed = subprocess.run(
        [sys.executable, "-S", "-c", script],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
