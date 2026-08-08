# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Regressions for the bare get_config() access ratchet."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_config_access import (
    BaselineError,
    collect_violations,
    load_baseline,
    main,
    scan_module_counts,
    serialize_baseline,
    write_baseline,
)


ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "scripts" / "config_access_baseline.json"


def _write_module(root: Path, relative_path: str, source: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _write_baseline(path: Path, modules: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_baseline(modules), encoding="utf-8")


def test_repository_config_access_guard() -> None:
    """Keep the checked-in production tree aligned with its baseline."""

    assert collect_violations(ROOT, BASELINE) == []


def test_detects_new_module_get_config(tmp_path: Path) -> None:
    """Reject a newly introduced production get_config() module."""

    _write_module(
        tmp_path,
        "src/services/existing.py",
        "from src.config import get_config\n\ndef load():\n    return get_config()\n",
    )
    baseline = tmp_path / "scripts" / "config_access_baseline.json"
    _write_baseline(baseline, {"src/services/existing.py": 1})
    assert collect_violations(tmp_path, baseline) == []

    _write_module(
        tmp_path,
        "src/services/new_module.py",
        "from src.config import get_config\n\ndef load():\n    return get_config()\n",
    )
    violations = collect_violations(tmp_path, baseline)
    assert len(violations) == 1
    assert violations[0].rule == "new-module-get-config"
    assert violations[0].path == "src/services/new_module.py"


def test_detects_count_growth(tmp_path: Path) -> None:
    """Reject growth of get_config() count on an allowlisted module."""

    _write_module(
        tmp_path,
        "src/services/existing.py",
        "from src.config import get_config\n\ndef load():\n    return get_config()\n",
    )
    baseline = tmp_path / "scripts" / "config_access_baseline.json"
    _write_baseline(baseline, {"src/services/existing.py": 1})

    _write_module(
        tmp_path,
        "src/services/existing.py",
        "from src.config import get_config\n\n"
        "def load():\n"
        "    a = get_config()\n"
        "    b = get_config()\n"
        "    return a, b\n",
    )
    violations = collect_violations(tmp_path, baseline)
    assert len(violations) == 1
    assert violations[0].rule == "get-config-count-growth"
    assert "grew from 1 to 2" in violations[0].message


def test_write_baseline_allows_shrink_refuses_growth(tmp_path: Path) -> None:
    """--write-baseline may shrink the allowlist but must refuse growth."""

    _write_module(
        tmp_path,
        "src/services/a.py",
        "from src.config import get_config\n\ndef load():\n    return get_config()\n",
    )
    _write_module(
        tmp_path,
        "src/services/b.py",
        "from src.config import get_config\n\ndef load():\n    return get_config()\n",
    )
    baseline = tmp_path / "scripts" / "config_access_baseline.json"
    _write_baseline(
        baseline,
        {"src/services/a.py": 1, "src/services/b.py": 1},
    )

    # Growth: new module
    _write_module(
        tmp_path,
        "src/services/c.py",
        "from src.config import get_config\n\ndef load():\n    return get_config()\n",
    )
    assert write_baseline(tmp_path, baseline) == 1
    loaded = load_baseline(baseline)
    assert "src/services/c.py" not in loaded

    # Shrink: convert a and b, drop c
    _write_module(
        tmp_path,
        "src/services/a.py",
        "def load(config):\n    return config\n",
    )
    _write_module(
        tmp_path,
        "src/services/b.py",
        "from src.application_services import get_application_services\n\n"
        "def load():\n"
        "    return get_application_services().config\n",
    )
    _write_module(
        tmp_path,
        "src/services/c.py",
        "def load(config):\n    return config\n",
    )
    assert write_baseline(tmp_path, baseline) == 0
    assert load_baseline(baseline) == {}


def test_attribute_get_config_not_counted(tmp_path: Path) -> None:
    """System-config style attribute calls must not inflate the ratchet."""

    _write_module(
        tmp_path,
        "src/services/system.py",
        "class Svc:\n"
        "    def get_config(self):\n"
        "        return {}\n"
        "\n"
        "def read(svc):\n"
        "    return svc.get_config()\n",
    )
    assert scan_module_counts(tmp_path) == {}


def test_excluded_definition_and_composition_root(tmp_path: Path) -> None:
    """config.py and application_services.py may call get_config freely."""

    _write_module(
        tmp_path,
        "src/config.py",
        "def get_config():\n    return object()\n\ndef boot():\n    return get_config()\n",
    )
    _write_module(
        tmp_path,
        "src/application_services.py",
        "def config():\n"
        "    from src.config import get_config\n"
        "    return get_config()\n",
    )
    assert scan_module_counts(tmp_path) == {}


def test_self_test_cli_exits_zero() -> None:
    """CLI --self-test must pass in isolation."""

    assert main(["--self-test"]) == 0


def test_unsorted_baseline_rejected(tmp_path: Path) -> None:
    """Baseline modules keys must be lexicographically sorted."""

    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "total_sites": 2,
                "modules": {"src/z.py": 1, "src/a.py": 1},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(BaselineError, match="sorted"):
        load_baseline(path)
