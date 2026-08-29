# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Regressions for the bidirectional package-pair import-cycle ratchet."""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from scripts.check_import_layers import (
    BaselineError,
    ImportPlacement,
    classify_import_modules,
    collect_violations,
    import_time_import_modules,
    load_baseline,
    main,
    scan_pairs,
    serialize_baseline,
    top_level_import_modules,
    write_baseline,
)


ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "scripts" / "import_layer_baseline.json"

# Introduction pair inventory (ADR-010). Shrink is free; never raise this ceiling.
INTRODUCTION_PAIR_CEILING = 11


def _guard_argv() -> list[str]:
    """Point the CLI at the same ROOT/BASELINE the repository tests read."""

    return ["--root", str(ROOT), "--baseline", str(BASELINE)]


def _assert_pair_inventory_is_not_inflated(
    live: Sequence[object],
    baseline: Sequence[object],
    ceiling: int,
) -> None:
    """Shrink-only pin: live may be a subset of baseline; neither may exceed the ceiling."""

    extra = set(live) - set(baseline)
    assert len(baseline) <= ceiling
    assert len(live) <= ceiling
    assert not extra, extra


def _write_module(root: Path, relative_path: str, source: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _write_baseline(path: Path, pairs: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        serialize_baseline([(a, b) for a, b in pairs]),
        encoding="utf-8",
    )


def test_repository_import_layer_guard() -> None:
    """Keep the checked-in production tree aligned with its baseline.

    Alignment here is the guard contract: no *new* bidirectional pair. A live
    scan that is a strict subset of the allowlist (legitimate shrink, baseline
    not yet rewritten) must stay green.
    """

    assert collect_violations(ROOT, BASELINE) == []
    assert main(_guard_argv()) == 0


def test_detects_new_bidirectional_pair(tmp_path: Path) -> None:
    """Reject a newly introduced bidirectional package cycle."""

    _write_module(
        tmp_path,
        "src/alpha/a.py",
        "from src.beta.b import value\n",
    )
    _write_module(
        tmp_path,
        "src/beta/b.py",
        "value = 1\n",
    )
    baseline = tmp_path / "scripts" / "import_layer_baseline.json"
    _write_baseline(baseline, [])
    assert collect_violations(tmp_path, baseline) == []

    _write_module(
        tmp_path,
        "src/beta/b.py",
        "from src.alpha.a import missing\nvalue = 1\n",
    )
    violations = collect_violations(tmp_path, baseline)
    assert len(violations) == 1
    assert violations[0].rule == "new-bidirectional-pair"
    assert {violations[0].package_a, violations[0].package_b} == {
        "src.alpha",
        "src.beta",
    }


def test_write_baseline_allows_shrink_refuses_growth(tmp_path: Path) -> None:
    """--write-baseline may shrink the allowlist but must refuse growth."""

    _write_module(
        tmp_path,
        "src/alpha/a.py",
        "from src.beta.b import value\n",
    )
    _write_module(
        tmp_path,
        "src/beta/b.py",
        "from src.alpha.a import missing\nvalue = 1\n",
    )
    baseline = tmp_path / "scripts" / "import_layer_baseline.json"
    pairs = scan_pairs(tmp_path)
    assert pairs == [("src.alpha", "src.beta")]
    _write_baseline(baseline, [["src.alpha", "src.beta"]])

    # Growth: second cycle
    _write_module(
        tmp_path,
        "src/gamma/g.py",
        "from src.delta.d import value\n",
    )
    _write_module(
        tmp_path,
        "src/delta/d.py",
        "from src.gamma.g import missing\nvalue = 1\n",
    )
    assert write_baseline(tmp_path, baseline) == 1
    assert load_baseline(baseline) == [("src.alpha", "src.beta")]

    # Shrink: break first cycle only, leave second so growth still refused
    _write_module(tmp_path, "src/beta/b.py", "value = 1\n")
    assert write_baseline(tmp_path, baseline) == 1

    # Break second cycle too — pure shrink from original baseline
    _write_module(tmp_path, "src/delta/d.py", "value = 1\n")
    # Current has no pairs; original baseline had one — shrink OK
    # But wait: gamma/delta cycle still? No, we broke delta's import of gamma.
    # alpha no longer cycles. No pairs remain.
    assert scan_pairs(tmp_path) == []
    assert write_baseline(tmp_path, baseline) == 0
    assert load_baseline(baseline) == []


def test_function_body_imports_are_ignored(tmp_path: Path) -> None:
    """Lazy imports inside functions must not create package edges."""

    _write_module(
        tmp_path,
        "src/alpha/a.py",
        "def load():\n    from src.beta.b import value\n    return value\n",
    )
    _write_module(
        tmp_path,
        "src/beta/b.py",
        "def load():\n    from src.alpha.a import load as other\n    return 1\n",
    )
    assert scan_pairs(tmp_path) == []


def test_load_baseline_rejects_unsorted_pairs(tmp_path: Path) -> None:
    """Baseline pairs must be left < right and lexicographically sorted."""

    path = tmp_path / "baseline.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "pairs": [["src.b", "src.a"]],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(BaselineError, match="ordered as left < right"):
        load_baseline(path)


def test_self_test_entrypoint_passes() -> None:
    """CLI --self-test exercises the isolated regression suite."""

    assert main(["--self-test"]) == 0


# --- issue #1555: whole-file import placement classification -------------------


def _classify(tmp_path: Path, source: str) -> ImportPlacement:
    """Classify one probe module's imports by execution placement."""

    _write_module(tmp_path, "src/beta/leaf.py", "value = 1\n")
    probe = _write_module(tmp_path, "src/alpha/probe.py", source)
    return classify_import_modules(tmp_path, probe)


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            "try:\n"
            "    from src.beta.leaf import value\n"
            "except ImportError:\n"
            "    value = None\n",
            id="try",
        ),
        pytest.param(
            "try:\n"
            "    value = 0\n"
            "except ImportError:\n"
            "    from src.beta.leaf import value\n",
            id="except-handler",
        ),
        pytest.param(
            "try:\n"
            "    value = 0\n"
            "except ImportError:\n"
            "    pass\n"
            "else:\n"
            "    from src.beta.leaf import value\n",
            id="try-else",
        ),
        pytest.param(
            "try:\n"
            "    value = 0\n"
            "finally:\n"
            "    from src.beta.leaf import value\n",
            id="try-finally",
        ),
        pytest.param(
            "import os\nif os.environ.get('X'):\n    from src.beta.leaf import value\n",
            id="if",
        ),
        pytest.param(
            "import os\n"
            "if os.environ.get('X'):\n"
            "    value = 0\n"
            "else:\n"
            "    from src.beta.leaf import value\n",
            id="if-else",
        ),
        pytest.param(
            "from contextlib import suppress\n"
            "with suppress(ImportError):\n"
            "    from src.beta.leaf import value\n",
            id="with",
        ),
        pytest.param(
            "for _ in range(1):\n    from src.beta.leaf import value\n",
            id="for",
        ),
        pytest.param(
            "while False:\n    pass\nelse:\n    from src.beta.leaf import value\n",
            id="while-else",
        ),
        pytest.param(
            "MODE = 'a'\n"
            "match MODE:\n"
            "    case 'a':\n"
            "        from src.beta.leaf import value\n"
            "    case _:\n"
            "        value = None\n",
            id="match-case",
        ),
        pytest.param(
            "class Loader:\n    from src.beta.leaf import value\n",
            id="class-body",
        ),
        pytest.param(
            "import src.beta.leaf\n",
            id="plain-import-statement",
        ),
    ],
)
def test_eager_placements_are_import_time(source: str, tmp_path: Path) -> None:
    """Every eagerly executed body contributes import-time edges."""

    placement = _classify(tmp_path, source)
    assert any(name.startswith("src.beta") for name in placement.import_time)
    assert placement.function_local == ()


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            "def load():\n    from src.beta.leaf import value\n    return value\n",
            id="def",
        ),
        pytest.param(
            "async def load():\n"
            "    from src.beta.leaf import value\n"
            "    return value\n",
            id="async-def",
        ),
        pytest.param(
            "class Loader:\n"
            "    def load(self):\n"
            "        from src.beta.leaf import value\n"
            "        return value\n",
            id="method",
        ),
        pytest.param(
            "def outer():\n"
            "    class Inner:\n"
            "        from src.beta.leaf import value\n"
            "    return Inner\n",
            id="class-in-def",
        ),
    ],
)
def test_function_bodies_are_never_import_time(source: str, tmp_path: Path) -> None:
    """Deferred loads land in the lazy bucket and create no package edge."""

    placement = _classify(tmp_path, source)
    assert placement.import_time == ()
    assert "src.beta.leaf" in placement.function_local


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from src.beta.leaf import value\n",
            id="plain",
        ),
        pytest.param(
            "from typing import TYPE_CHECKING as TC\n"
            "if TC:\n"
            "    from src.beta.leaf import value\n",
            id="symbol-alias",
        ),
        pytest.param(
            "import typing as t\n"
            "if t.TYPE_CHECKING:\n"
            "    from src.beta.leaf import value\n",
            id="module-alias-attribute",
        ),
        pytest.param(
            "from typing_extensions import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from src.beta.leaf import value\n",
            id="typing-extensions",
        ),
    ],
)
def test_type_checking_blocks_are_excluded(source: str, tmp_path: Path) -> None:
    """``if TYPE_CHECKING:`` bodies never execute, so they are not edges."""

    placement = _classify(tmp_path, source)
    assert not any(name.startswith("src.beta") for name in placement.import_time)


def test_nested_eager_imports_form_a_bidirectional_pair(tmp_path: Path) -> None:
    """Nested-but-eager imports on both sides are a real cycle for the ratchet."""

    _write_module(
        tmp_path,
        "src/alpha/a.py",
        "try:\n"
        "    from src.beta.b import value\n"
        "except ImportError:\n"
        "    value = None\n",
    )
    _write_module(
        tmp_path,
        "src/beta/b.py",
        "class Holder:\n    from src.alpha.a import value\n",
    )
    assert scan_pairs(tmp_path) == [("src.alpha", "src.beta")]


def test_function_local_imports_still_form_no_pair(tmp_path: Path) -> None:
    """Lazy imports remain outside the cycle ratchet after the traversal change."""

    _write_module(
        tmp_path,
        "src/alpha/a.py",
        "def load():\n    from src.beta.b import value\n    return value\n",
    )
    _write_module(
        tmp_path,
        "src/beta/b.py",
        "def load():\n    from src.alpha.a import load as other\n    return other\n",
    )
    assert scan_pairs(tmp_path) == []


def test_top_level_helper_contract_is_unchanged(tmp_path: Path) -> None:
    """``top_level_import_modules`` keeps its module-body-only scope for callers."""

    probe = _write_module(
        tmp_path,
        "src/alpha/probe.py",
        "import os\n"
        "try:\n"
        "    from src.beta.leaf import value\n"
        "except ImportError:\n"
        "    value = None\n",
    )
    assert top_level_import_modules(tmp_path, probe) == ["os"]
    assert import_time_import_modules(tmp_path, probe) == ["os", "src.beta.leaf"]


def test_unparsable_module_degrades_to_empty_placement(tmp_path: Path) -> None:
    """A syntax error must not crash the guard."""

    probe = _write_module(tmp_path, "src/alpha/probe.py", "def broken(\n")
    assert classify_import_modules(tmp_path, probe) == ImportPlacement((), ())


def test_repository_pair_inventory_is_not_inflated() -> None:
    """Recursive traversal must not grow the shipped cycle baseline.

    Shrink is free: the live scan may be a subset of the checked-in pairs and
    ``pair_count`` may fall. Live equality (``scan == baseline`` /
    ``pair_count == 11``) would turn a later legitimate shrink red before
    ``--write-baseline`` ran.
    """

    payload = json.loads(BASELINE.read_text(encoding="utf-8"))
    baseline_pairs = load_baseline(BASELINE)
    live_pairs = scan_pairs(ROOT)
    assert payload["pair_count"] <= INTRODUCTION_PAIR_CEILING
    assert payload["pair_count"] == len(baseline_pairs)
    _assert_pair_inventory_is_not_inflated(
        live_pairs, baseline_pairs, INTRODUCTION_PAIR_CEILING
    )
    assert collect_violations(ROOT, BASELINE) == []
    assert main(_guard_argv()) == 0


def _pair_fixture(tmp_path: Path) -> Path:
    """One allowlisted ``src.alpha <-> src.beta`` pair."""

    _write_module(tmp_path, "src/alpha/a.py", "from src.beta.b import value\n")
    _write_module(
        tmp_path,
        "src/beta/b.py",
        "from src.alpha.a import missing\nvalue = 1\n",
    )
    pairs = scan_pairs(tmp_path)
    assert pairs == [("src.alpha", "src.beta")]
    baseline = tmp_path / "scripts" / "import_layer_baseline.json"
    _write_baseline(baseline, [["src.alpha", "src.beta"]])
    return baseline


def test_pair_inventory_pin_stays_green_after_legitimate_shrink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reviewer counterexample: breaking an allowlisted cycle must not redden the suite."""

    baseline = _pair_fixture(tmp_path)
    _write_module(tmp_path, "src/beta/b.py", "value = 1\n")
    this_module = sys.modules[__name__]
    monkeypatch.setattr(this_module, "ROOT", tmp_path)
    monkeypatch.setattr(this_module, "BASELINE", baseline)

    live = scan_pairs(tmp_path)
    recorded = load_baseline(baseline)
    assert live == []
    assert recorded
    _assert_pair_inventory_is_not_inflated(
        live, recorded, INTRODUCTION_PAIR_CEILING
    )
    assert collect_violations(tmp_path, baseline) == []
    assert main(["--root", str(tmp_path), "--baseline", str(baseline)]) == 0
    test_repository_pair_inventory_is_not_inflated()
    test_repository_import_layer_guard()


def test_pair_inventory_pin_fails_on_growth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same pin, plus the guard, must still fail when a new pair appears."""

    baseline = _pair_fixture(tmp_path)
    _write_module(tmp_path, "src/gamma/g.py", "from src.delta.d import value\n")
    _write_module(
        tmp_path,
        "src/delta/d.py",
        "from src.gamma.g import missing\nvalue = 1\n",
    )
    this_module = sys.modules[__name__]
    monkeypatch.setattr(this_module, "ROOT", tmp_path)
    monkeypatch.setattr(this_module, "BASELINE", baseline)

    live = scan_pairs(tmp_path)
    recorded = load_baseline(baseline)
    extra = set(live) - set(recorded)
    assert extra
    with pytest.raises(AssertionError):
        _assert_pair_inventory_is_not_inflated(
            live, recorded, INTRODUCTION_PAIR_CEILING
        )
    with pytest.raises(AssertionError):
        test_repository_pair_inventory_is_not_inflated()
    with pytest.raises(AssertionError):
        test_repository_import_layer_guard()
    assert collect_violations(tmp_path, baseline)
    assert main(["--root", str(tmp_path), "--baseline", str(baseline)]) == 1


def test_star_import_from_typing_binds_the_sentinel(tmp_path: Path) -> None:
    """``from typing import *`` still brings ``TYPE_CHECKING`` into scope."""

    placement = _classify(
        tmp_path,
        "from typing import *\nif TYPE_CHECKING:\n    from src.beta.leaf import value\n",
    )
    assert not any(name.startswith("src.beta") for name in placement.import_time)


def test_except_handler_rebinding_clears_the_sentinel(tmp_path: Path) -> None:
    """An ``except ... as TYPE_CHECKING`` binding is not the typing sentinel."""

    placement = _classify(
        tmp_path,
        "from typing import TYPE_CHECKING\n"
        "try:\n"
        "    pass\n"
        "except ImportError as TYPE_CHECKING:\n"
        "    pass\n"
        "if TYPE_CHECKING:\n"
        "    from src.beta.leaf import value\n",
    )
    assert "src.beta.leaf" in placement.import_time


def test_attribute_assignment_does_not_clear_the_typing_alias(tmp_path: Path) -> None:
    """``typing.X = 1`` stores into an attribute; it does not rebind ``typing``."""

    placement = _classify(
        tmp_path,
        "import typing\n"
        "typing.CUSTOM = 1\n"
        "if typing.TYPE_CHECKING:\n"
        "    from src.beta.leaf import value\n",
    )
    assert not any(name.startswith("src.beta") for name in placement.import_time)


def test_match_mapping_rest_rebinding_clears_the_sentinel(tmp_path: Path) -> None:
    """A ``match`` mapping ``**rest`` capture named TYPE_CHECKING is a rebinding."""

    placement = _classify(
        tmp_path,
        "from typing import TYPE_CHECKING\n"
        "PAYLOAD = {}\n"
        "match PAYLOAD:\n"
        "    case {**TYPE_CHECKING}:\n"
        "        pass\n"
        "if TYPE_CHECKING:\n"
        "    from src.beta.leaf import value\n",
    )
    assert "src.beta.leaf" in placement.import_time
