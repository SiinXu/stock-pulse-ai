# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Regressions for broad exception classification and debt ratcheting."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.check_broad_exceptions import (
    BaselineError,
    collect_violations,
    load_baseline,
    scan_repository,
    write_baseline,
)


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "scripts" / "broad_exception_baseline.json"


def _write_baseline(
    path: Path,
    *,
    deferred_files: dict[str, str] | None = None,
    legacy_handlers: list[dict[str, object]] | None = None,
) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "deferred_files": deferred_files or {},
                "legacy_handlers": legacy_handlers or [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_module(root: Path, source: str, relative_path: str = "src/example.py") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _rules(root: Path, baseline: Path) -> set[str]:
    return {violation.rule for violation in collect_violations(root, baseline)}


def test_repository_broad_exception_guard() -> None:
    assert collect_violations(ROOT, BASELINE) == ()


def test_new_unclassified_handler_fails_closed(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    _write_module(
        tmp_path,
        "def load():\n"
        "    try:\n"
        "        return object()\n"
        "    except Exception:\n"
        "        return None\n",
    )

    assert "new-broad-handler" in _rules(tmp_path, baseline)


def test_supported_classifications_are_explicit_and_recorded(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    _write_module(
        tmp_path,
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "def cleanup(resource):\n"
        "    try:\n"
        "        resource.use()\n"
        "    except Exception:  # broad-exception: cleanup - release is best effort.\n"
        "        resource.close()\n"
        "def metadata(item):\n"
        "    try:\n"
        "        return item.title\n"
        "    except Exception:  # broad-exception: optional_metadata - title is optional.\n"
        "        return None\n"
        "def fallback(source):\n"
        "    try:\n"
        "        return source.fetch()\n"
        "    except Exception:  # broad-exception: fallback_recorded - caller receives cache.\n"
        "        logger.warning('source fallback')\n"
        "        return source.cached()\n",
    )

    assert collect_violations(tmp_path, baseline) == ()


def test_invalid_category_and_unrecorded_fallback_are_rejected(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    _write_module(
        tmp_path,
        "def first():\n"
        "    try:\n"
        "        return 1\n"
        "    except Exception:  # broad-exception: ignored - not a supported category.\n"
        "        return 0\n"
        "def second():\n"
        "    try:\n"
        "        return 1\n"
        "    except Exception:  # broad-exception: fallback_recorded - use default.\n"
        "        return 0\n",
    )

    rules = _rules(tmp_path, baseline)
    assert "invalid-marker" in rules
    assert "unrecorded-fallback" in rules


def test_orphan_marker_is_rejected_after_handler_is_narrowed(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    _write_module(
        tmp_path,
        "def load():\n"
        "    try:\n"
        "        return object()\n"
        "    except ValueError:  # broad-exception: optional_metadata - value is optional.\n"
        "        return None\n",
    )

    assert "orphan-marker" in _rules(tmp_path, baseline)


def test_base_exception_pass_requires_cleanup_reason(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    module = _write_module(
        tmp_path,
        "def close():\n"
        "    try:\n"
        "        object()\n"
        "    except BaseException:\n"
        "        pass\n",
    )

    assert "base-exception-pass" in _rules(tmp_path, baseline)
    module.write_text(
        "def close():\n"
        "    try:\n"
        "        object()\n"
        "    except BaseException:  # broad-exception: cleanup - shutdown cannot escape.\n"
        "        pass\n",
        encoding="utf-8",
    )
    assert collect_violations(tmp_path, baseline) == ()


def test_propagation_and_logged_typed_mapping_need_no_baseline(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    _write_module(
        tmp_path,
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "class DomainError(Exception):\n"
        "    pass\n"
        "def propagate():\n"
        "    try:\n"
        "        object()\n"
        "    except Exception:\n"
        "        raise\n"
        "def mapped():\n"
        "    try:\n"
        "        object()\n"
        "    except Exception as exc:\n"
        "        logger.error('mapped failure')\n"
        "        raise DomainError() from exc\n",
    )

    assert collect_violations(tmp_path, baseline) == ()


def test_unlogged_typed_mapping_remains_legacy_debt(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    _write_module(
        tmp_path,
        "class DomainError(Exception):\n"
        "    pass\n"
        "def mapped():\n"
        "    try:\n"
        "        object()\n"
        "    except Exception as exc:\n"
        "        raise DomainError() from exc\n",
    )

    assert "new-broad-handler" in _rules(tmp_path, baseline)


def test_logged_non_exception_raise_remains_legacy_debt(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    _write_module(
        tmp_path,
        "import logging\n"
        "logger = logging.getLogger(__name__)\n"
        "def make_value():\n"
        "    return 42\n"
        "def mapped():\n"
        "    try:\n"
        "        object()\n"
        "    except Exception:\n"
        "        logger.error('mapped failure')\n"
        "        raise make_value()\n",
    )

    assert "new-broad-handler" in _rules(tmp_path, baseline)


def test_yield_before_final_raise_is_not_treated_as_propagation(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    _write_module(
        tmp_path,
        "def values():\n"
        "    try:\n"
        "        yield 1\n"
        "    except Exception:\n"
        "        yield 0\n"
        "        raise\n",
    )

    assert "new-broad-handler" in _rules(tmp_path, baseline)


def test_outer_fingerprint_ignores_nested_handler_body_changes(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    module = _write_module(
        tmp_path,
        "def load():\n"
        "    try:\n"
        "        return object()\n"
        "    except Exception:\n"
        "        try:\n"
        "            return object()\n"
        "        except Exception:  # broad-exception: optional_metadata - nested value is optional.\n"
        "            return None\n",
    )
    outer = scan_repository(tmp_path)[0]
    _write_baseline(baseline, legacy_handlers=[outer.baseline_entry.as_json()])

    module.write_text(
        module.read_text(encoding="utf-8")
        .replace("except Exception:  # broad-exception", "except ValueError:  # broad-exception")
        .replace("return None", "return 'missing'"),
        encoding="utf-8",
    )
    assert _rules(tmp_path, baseline) == {"orphan-marker"}


def test_baseline_fingerprint_ignores_line_only_changes_and_rejects_stale_debt(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    module = _write_module(
        tmp_path,
        "def load():\n"
        "    try:\n"
        "        return object()\n"
        "    except Exception:\n"
        "        return None\n",
    )
    handler = scan_repository(tmp_path)[0]
    _write_baseline(baseline, legacy_handlers=[handler.baseline_entry.as_json()])
    module.write_text("\n\n" + module.read_text(encoding="utf-8"), encoding="utf-8")
    assert collect_violations(tmp_path, baseline) == ()

    module.write_text("def load():\n    return None\n", encoding="utf-8")
    assert "stale-baseline-entry" in _rules(tmp_path, baseline)
    assert write_baseline(tmp_path, baseline) == 0
    assert load_baseline(baseline).legacy_handlers == ()


def test_baseline_writer_refuses_new_or_modified_debt(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    _write_module(
        tmp_path,
        "def load():\n"
        "    try:\n"
        "        return object()\n"
        "    except Exception:\n"
        "        return None\n",
    )

    assert write_baseline(tmp_path, baseline) == 1
    assert load_baseline(baseline).legacy_handlers == ()

    module = tmp_path / "src" / "example.py"
    handler = scan_repository(tmp_path)[0]
    _write_baseline(baseline, legacy_handlers=[handler.baseline_entry.as_json()])
    original_entry = load_baseline(baseline).legacy_handlers
    module.write_text(
        module.read_text(encoding="utf-8").replace("return None", "return False"),
        encoding="utf-8",
    )
    assert write_baseline(tmp_path, baseline) == 1
    assert load_baseline(baseline).legacy_handlers == original_entry


def test_tuple_and_bare_handlers_are_in_scope(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    _write_module(
        tmp_path,
        "def tuple_handler():\n"
        "    try:\n"
        "        object()\n"
        "    except (ValueError, Exception):\n"
        "        return None\n"
        "def bare_handler():\n"
        "    try:\n"
        "        object()\n"
        "    except:\n"
        "        return None\n",
    )

    violations = collect_violations(tmp_path, baseline)
    assert sum(item.rule == "new-broad-handler" for item in violations) == 2


def test_deferred_files_require_live_handlers_and_reasons(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    _write_module(tmp_path, "value = 1\n")
    _write_baseline(
        baseline,
        deferred_files={"src/example.py": "Open PR owns this module."},
    )
    assert "stale-deferred-file" in _rules(tmp_path, baseline)

    _write_baseline(
        baseline,
        deferred_files={"src/example.py": ""},
    )
    assert "invalid-baseline" in _rules(tmp_path, baseline)


def test_baseline_loader_rejects_unsorted_entries(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    entries = [
        {
            "path": "src/z.py",
            "scope": "<module>",
            "caught": ["Exception"],
            "digest": "a" * 64,
        },
        {
            "path": "src/a.py",
            "scope": "<module>",
            "caught": ["Exception"],
            "digest": "b" * 64,
        },
    ]
    _write_baseline(baseline, legacy_handlers=entries)

    try:
        load_baseline(baseline)
    except BaselineError as exc:
        assert "deterministically sorted" in str(exc)
    else:
        raise AssertionError("unsorted baseline was accepted")
