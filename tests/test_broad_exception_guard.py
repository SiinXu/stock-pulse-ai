# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Regressions for broad exception classification and debt ratcheting."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from scripts.check_broad_exceptions import (
    BaselineError,
    _handler_digest,
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
    """Write a minimal baseline fixture."""

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
    """Write one production-scope module fixture."""

    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _rules(root: Path, baseline: Path) -> set[str]:
    """Return the emitted rule identifiers for a fixture repository."""

    return {violation.rule for violation in collect_violations(root, baseline)}


def test_repository_broad_exception_guard() -> None:
    """Keep the checked-in production tree aligned with its baseline."""

    assert collect_violations(ROOT, BASELINE) == ()


def test_new_unclassified_handler_fails_closed(tmp_path: Path) -> None:
    """Reject a newly introduced unclassified broad handler."""

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
    """Accept supported markers when their required evidence is present."""

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
    """Reject unknown markers and fallbacks without recording evidence."""

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
    """Reject a marker left behind after its handler is narrowed."""

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
    """Require explicit cleanup intent for BaseException pass handlers."""

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
    """Accept deterministic propagation and safely logged typed mapping."""

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
        "def propagate_with_noop_finally():\n"
        "    try:\n"
        "        object()\n"
        "    except Exception:\n"
        "        raise\n"
        "    finally:\n"
        "        pass\n"
        "def mapped():\n"
        "    try:\n"
        "        object()\n"
        "    except Exception as exc:\n"
        "        logger.error('mapped failure')\n"
        "        raise DomainError() from exc\n"
        "def mapped_with_noop_finally():\n"
        "    try:\n"
        "        object()\n"
        "    except Exception as exc:\n"
        "        logger.error('mapped failure')\n"
        "        raise DomainError() from exc\n"
        "    finally:\n"
        "        pass\n",
    )

    assert collect_violations(tmp_path, baseline) == ()


def test_nested_handler_escape_is_not_treated_as_propagation(tmp_path: Path) -> None:
    """Reject propagation proofs with a nested handler escape."""

    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    _write_module(
        tmp_path,
        "def load():\n"
        "    try:\n"
        "        object()\n"
        "    except Exception:\n"
        "        try:\n"
        "            object()\n"
        "        except ValueError:\n"
        "            return None\n"
        "        raise\n",
    )

    assert "new-broad-handler" in _rules(tmp_path, baseline)


def test_finally_escape_cancels_raise_exemptions(tmp_path: Path) -> None:
    """Reject raise exemptions when finally can suppress or replace them."""

    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    _write_module(
        tmp_path,
        "class DomainError(Exception):\n"
        "    pass\n"
        "def propagate():\n"
        "    try:\n"
        "        work()\n"
        "    except Exception:\n"
        "        raise\n"
        "    finally:\n"
        "        return None\n"
        "def mapped():\n"
        "    try:\n"
        "        work()\n"
        "    except Exception:\n"
        "        logger.error('mapped failure')\n"
        "        raise DomainError()\n"
        "    finally:\n"
        "        return None\n"
        "def replaced():\n"
        "    try:\n"
        "        work()\n"
        "    except Exception:\n"
        "        raise\n"
        "    finally:\n"
        "        raise RuntimeError('replacement')\n"
        "def call_replaced():\n"
        "    try:\n"
        "        work()\n"
        "    except Exception:\n"
        "        raise\n"
        "    finally:\n"
        "        replace_exception()\n"
        "def mapped_call_replaced():\n"
        "    try:\n"
        "        work()\n"
        "    except Exception:\n"
        "        logger.error('mapped failure')\n"
        "        raise DomainError()\n"
        "    finally:\n"
        "        replace_exception()\n",
    )

    violations = collect_violations(tmp_path, baseline)
    assert sum(item.rule == "new-broad-handler" for item in violations) == 5


def test_unlogged_typed_mapping_remains_legacy_debt(tmp_path: Path) -> None:
    """Keep unlogged typed mappings in the structural debt baseline."""

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


def test_typed_mapping_requires_a_direct_safe_log_and_exception_factory(
    tmp_path: Path,
) -> None:
    """Require reachable safe logging and a recognized exception factory."""

    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    _write_module(
        tmp_path,
        "class DomainError(Exception):\n"
        "    pass\n"
        "def conditional_log(flag):\n"
        "    try:\n"
        "        object()\n"
        "    except Exception:\n"
        "        if flag:\n"
        "            logger.error('mapped failure')\n"
        "        raise DomainError()\n"
        "def fake_logger_owner():\n"
        "    try:\n"
        "        object()\n"
        "    except Exception:\n"
        "        catalogger.error('mapped failure')\n"
        "        raise DomainError()\n"
        "def raised_logger_call():\n"
        "    try:\n"
        "        object()\n"
        "    except Exception:\n"
        "        logger.error('mapped failure')\n"
        "        raise logger.error('not an exception factory')\n"
        "def unreachable_log():\n"
        "    try:\n"
        "        object()\n"
        "    except Exception:\n"
        "        raise RuntimeError('first exit')\n"
        "        logger.error('unreachable mapping')\n"
        "        raise DomainError()\n",
    )

    violations = collect_violations(tmp_path, baseline)
    assert sum(item.rule == "new-broad-handler" for item in violations) == 4


def test_logged_non_exception_raise_remains_legacy_debt(tmp_path: Path) -> None:
    """Reject logged raises whose value is not an exception constructor."""

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
    """Reject propagation proofs that can yield before the final raise."""

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


def test_fallback_recorded_accepts_direct_structured_records(tmp_path: Path) -> None:
    """Accept direct structured sinks that explicitly record failure."""

    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    _write_module(
        tmp_path,
        "def provider(source):\n"
        "    try:\n"
        "        return source.fetch()\n"
        "    except Exception as exc:  # broad-exception: fallback_recorded - provider run stores fallback details.\n"
        "        record_provider_run(error=type(exc).__name__, fallback_from='primary', fallback_to='cache')\n"
        "        return source.cached()\n"
        "def future_result(future):\n"
        "    try:\n"
        "        return object()\n"
        "    except Exception as exc:  # broad-exception: fallback_recorded - future exposes the failure.\n"
        "        future.set_exception(exc)\n"
        "        return None\n"
        "def child_process(child_conn):\n"
        "    try:\n"
        "        return object()\n"
        "    except Exception as exc:  # broad-exception: fallback_recorded - parent receives the failure.\n"
        "        child_conn.send({'error': type(exc).__name__})\n"
        "        return None\n"
        "def holder(state):\n"
        "    try:\n"
        "        return object()\n"
        "    except Exception as exc:  # broad-exception: fallback_recorded - state retains the failure.\n"
        "        state.last_error = type(exc).__name__\n"
        "        return None\n"
        "def diagnostics(result):\n"
        "    try:\n"
        "        return object()\n"
        "    except Exception as exc:  # broad-exception: fallback_recorded - result exposes diagnostics.\n"
        "        result['diagnostic'] = type(exc).__name__\n"
        "        return None\n"
        "def failed_status(source):\n"
        "    try:\n"
        "        return source.fetch()\n"
        "    except Exception:  # broad-exception: fallback_recorded - failed run is recorded.\n"
        "        record_notification_run(status='failed', success=False)\n"
        "        return source.cached()\n"
        "def failed_flag(source):\n"
        "    try:\n"
        "        return source.fetch()\n"
        "    except Exception:  # broad-exception: fallback_recorded - failed run is recorded.\n"
        "        record_provider_run(failed=True)\n"
        "        return source.cached()\n"
        "def negative_ipc(source, child_conn):\n"
        "    try:\n"
        "        return source.fetch()\n"
        "    except Exception:  # broad-exception: fallback_recorded - parent receives failure status.\n"
        "        child_conn.send({'success': False})\n"
        "        return source.cached()\n",
    )

    assert collect_violations(tmp_path, baseline) == ()


def test_fallback_record_must_be_direct_and_observable(tmp_path: Path) -> None:
    """Reject conditional, local-only, empty, or unreachable records."""

    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    _write_module(
        tmp_path,
        "def conditional(source, should_record):\n"
        "    try:\n"
        "        return source.fetch()\n"
        "    except Exception as exc:  # broad-exception: fallback_recorded - fallback should be recorded.\n"
        "        if should_record:\n"
        "            record_provider_run(error=type(exc).__name__)\n"
        "        return source.cached()\n"
        "def local_only(source):\n"
        "    try:\n"
        "        return source.fetch()\n"
        "    except Exception as exc:  # broad-exception: fallback_recorded - fallback should be recorded.\n"
        "        error = type(exc).__name__\n"
        "        return source.cached()\n"
        "def unreachable(source):\n"
        "    try:\n"
        "        return source.fetch()\n"
        "    except Exception:  # broad-exception: fallback_recorded - fallback should be recorded.\n"
        "        return source.cached()\n"
        "        logger.error('unreachable fallback')\n"
        "def start_only(source):\n"
        "    try:\n"
        "        return source.fetch()\n"
        "    except Exception:  # broad-exception: fallback_recorded - fallback should be recorded.\n"
        "        record_provider_run_started()\n"
        "        return source.cached()\n"
        "def success_ipc(source, child_conn):\n"
        "    try:\n"
        "        return source.fetch()\n"
        "    except Exception:  # broad-exception: fallback_recorded - fallback should be recorded.\n"
        "        child_conn.send({'status': 'ok'})\n"
        "        return source.cached()\n"
        "def cleared_holder(source, state):\n"
        "    try:\n"
        "        return source.fetch()\n"
        "    except Exception:  # broad-exception: fallback_recorded - fallback should be recorded.\n"
        "        state.last_error = None\n"
        "        return source.cached()\n"
        "def empty_future(source, future):\n"
        "    try:\n"
        "        return source.fetch()\n"
        "    except Exception:  # broad-exception: fallback_recorded - fallback should be recorded.\n"
        "        future.set_exception(None)\n"
        "        return source.cached()\n",
    )

    violations = collect_violations(tmp_path, baseline)
    assert sum(item.rule == "unrecorded-fallback" for item in violations) == 7


def test_outer_fingerprint_tracks_nested_handler_body_changes(tmp_path: Path) -> None:
    """Fingerprint nested handler behavior inside a legacy outer handler."""

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
    rules = _rules(tmp_path, baseline)
    assert {"new-broad-handler", "orphan-marker", "stale-baseline-entry"} <= rules


def test_fingerprint_tracks_protected_operations_and_refuses_replacement(
    tmp_path: Path,
) -> None:
    """Churn fingerprints when the protected operation set changes."""

    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    module = _write_module(
        tmp_path,
        "def load():\n"
        "    try:\n"
        "        return read_cache()\n"
        "    except Exception:\n"
        "        return None\n",
    )
    handler = scan_repository(tmp_path)[0]
    _write_baseline(baseline, legacy_handlers=[handler.baseline_entry.as_json()])
    original_baseline = baseline.read_text(encoding="utf-8")

    module.write_text(
        module.read_text(encoding="utf-8").replace(
            "        return read_cache()\n",
            "        charge_customer()\n        return read_cache()\n",
        ),
        encoding="utf-8",
    )

    rules = _rules(tmp_path, baseline)
    assert {"new-broad-handler", "stale-baseline-entry"} <= rules
    assert write_baseline(tmp_path, baseline) == 1
    assert baseline.read_text(encoding="utf-8") == original_baseline


def test_fingerprint_tracks_handler_order_within_a_try(tmp_path: Path) -> None:
    """Distinguish ordered broad handlers within one try statement."""

    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    module = _write_module(
        tmp_path,
        "def load():\n"
        "    try:\n"
        "        return object()\n"
        "    except Exception:\n"
        "        return 'first'\n"
        "    except Exception:\n"
        "        return 'second'\n",
    )
    entries = sorted(handler.baseline_entry for handler in scan_repository(tmp_path))
    _write_baseline(
        baseline,
        legacy_handlers=[entry.as_json() for entry in entries],
    )

    module.write_text(
        module.read_text(encoding="utf-8")
        .replace("return 'first'", "return 'temporary'")
        .replace("return 'second'", "return 'first'")
        .replace("return 'temporary'", "return 'second'"),
        encoding="utf-8",
    )

    rules = _rules(tmp_path, baseline)
    assert {"new-broad-handler", "stale-baseline-entry"} <= rules


def test_fingerprint_tracks_sibling_handler_coverage(tmp_path: Path) -> None:
    """Churn fingerprints when sibling handler coverage changes."""

    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    module = _write_module(
        tmp_path,
        "def load():\n"
        "    try:\n"
        "        return work()\n"
        "    except ValueError:\n"
        "        return 'invalid'\n"
        "    except Exception:\n"
        "        return None\n",
    )
    handler = scan_repository(tmp_path)[0]
    _write_baseline(baseline, legacy_handlers=[handler.baseline_entry.as_json()])
    original_baseline = baseline.read_text(encoding="utf-8")

    module.write_text(
        module.read_text(encoding="utf-8").replace("ValueError", "KeyError"),
        encoding="utf-8",
    )

    rules = _rules(tmp_path, baseline)
    assert {"new-broad-handler", "stale-baseline-entry"} <= rules
    assert write_baseline(tmp_path, baseline) == 1
    assert baseline.read_text(encoding="utf-8") == original_baseline


def test_fingerprint_distinguishes_identical_try_sites(tmp_path: Path) -> None:
    """Distinguish structurally identical try statements in one scope."""

    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    module = _write_module(
        tmp_path,
        "def load():\n"
        "    try:\n"
        "        work()\n"
        "    except Exception:\n"
        "        return 'first'\n"
        "    try:\n"
        "        work()\n"
        "    except Exception:\n"
        "        return 'second'\n",
    )
    entries = sorted(handler.baseline_entry for handler in scan_repository(tmp_path))
    _write_baseline(
        baseline,
        legacy_handlers=[entry.as_json() for entry in entries],
    )

    module.write_text(
        module.read_text(encoding="utf-8")
        .replace("return 'first'", "return 'temporary'")
        .replace("return 'second'", "return 'first'")
        .replace("return 'temporary'", "return 'second'"),
        encoding="utf-8",
    )

    rules = _rules(tmp_path, baseline)
    assert {"new-broad-handler", "stale-baseline-entry"} <= rules


def test_fingerprint_tracks_the_protected_try_site(tmp_path: Path) -> None:
    """Churn fingerprints when a handler moves to another try site."""

    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    module = _write_module(
        tmp_path,
        "def load():\n"
        "    try:\n"
        "        return work()\n"
        "    except Exception:\n"
        "        return None\n"
        "    try:\n"
        "        return work()\n"
        "    except ValueError:\n"
        "        return None\n",
    )
    handler = scan_repository(tmp_path)[0]
    _write_baseline(baseline, legacy_handlers=[handler.baseline_entry.as_json()])

    module.write_text(
        module.read_text(encoding="utf-8")
        .replace("except Exception", "except TemporaryError")
        .replace("except ValueError", "except Exception"),
        encoding="utf-8",
    )

    rules = _rules(tmp_path, baseline)
    assert {"new-broad-handler", "stale-baseline-entry"} <= rules


def test_fingerprint_tracks_enclosing_control_flow(tmp_path: Path) -> None:
    """Include enclosing behavior-bearing control flow in site identity."""

    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    module = _write_module(
        tmp_path,
        "def load(flag):\n"
        "    if flag:\n"
        "        try:\n"
        "            return work()\n"
        "        except Exception:\n"
        "            return None\n",
    )
    handler = scan_repository(tmp_path)[0]
    _write_baseline(baseline, legacy_handlers=[handler.baseline_entry.as_json()])
    original_baseline = baseline.read_text(encoding="utf-8")

    module.write_text(
        module.read_text(encoding="utf-8").replace("if flag:", "if not flag:"),
        encoding="utf-8",
    )

    rules = _rules(tmp_path, baseline)
    assert {"new-broad-handler", "stale-baseline-entry"} <= rules
    assert write_baseline(tmp_path, baseline) == 1
    assert baseline.read_text(encoding="utf-8") == original_baseline


def test_fingerprint_tracks_lexical_statement_position(tmp_path: Path) -> None:
    """Include lexical statement position without relying on line numbers."""

    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    module = _write_module(
        tmp_path,
        "def load():\n"
        "    prepare()\n"
        "    try:\n"
        "        return work()\n"
        "    except Exception:\n"
        "        return None\n",
    )
    handler = scan_repository(tmp_path)[0]
    _write_baseline(baseline, legacy_handlers=[handler.baseline_entry.as_json()])

    module.write_text(
        "def load():\n"
        "    try:\n"
        "        return work()\n"
        "    except Exception:\n"
        "        return None\n"
        "    prepare()\n",
        encoding="utf-8",
    )

    rules = _rules(tmp_path, baseline)
    assert {"new-broad-handler", "stale-baseline-entry"} <= rules


def test_fingerprint_ignores_python_version_ast_metadata() -> None:
    """Ignore AST fields that vary across supported Python minor versions."""

    tree = ast.parse(
        "try:\n"
        "    def nested():\n"
        "        return 1\n"
        "except Exception:\n"
        "    return_value = None\n"
    )
    owner = next(node for node in ast.walk(tree) if isinstance(node, ast.Try))
    handler = owner.handlers[0]
    before = _handler_digest(owner, 0, 0, handler)

    nested = next(
        node for node in ast.walk(owner) if isinstance(node, ast.FunctionDef)
    )
    nested.type_params = [ast.Name(id="T", ctx=ast.Load())]

    assert _handler_digest(owner, 0, 0, handler) == before


def test_baseline_fingerprint_ignores_line_only_changes_and_rejects_stale_debt(
    tmp_path: Path,
) -> None:
    """Ignore line movement while rejecting obsolete baseline debt."""

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
    """Allow only debt removal when rewriting the baseline."""

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
    """Detect broad exceptions nested in tuples and bare handlers."""

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


def test_exception_group_handlers_are_in_scope(tmp_path: Path) -> None:
    """Detect broad exception-group handlers."""

    baseline = tmp_path / "baseline.json"
    _write_baseline(baseline)
    _write_module(
        tmp_path,
        "def handle(group, errors):\n"
        "    try:\n"
        "        raise group\n"
        "    except* Exception:\n"
        "        errors.append('failed')\n",
    )

    assert "new-broad-handler" in _rules(tmp_path, baseline)


def test_deferred_files_require_live_handlers_and_reasons(tmp_path: Path) -> None:
    """Validate deferred paths, live handlers, and non-empty reasons."""

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
    """Reject nondeterministically ordered baseline entries."""

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
