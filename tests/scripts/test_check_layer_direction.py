# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Regressions for the directed layer-import reverse-edge ratchet."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_import_layers import (
    import_time_import_modules,
    top_level_import_modules,
)
from scripts.check_layer_direction import (
    BaselineError,
    collect_violations,
    diff_lazy_inventory,
    lazy_inventory_drift,
    load_baseline,
    load_lazy_inventory,
    main,
    scan_lazy_reverse_edges,
    scan_reverse_edges,
    serialize_baseline,
    write_baseline,
)


ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "scripts" / "layer_direction_baseline.json"


def _write_module(root: Path, relative_path: str, source: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_repository_layer_direction_guard() -> None:
    """Keep the checked-in production tree aligned with its reverse-edge baseline."""

    assert collect_violations(ROOT, BASELINE) == []
    assert main([]) == 0


def test_detects_new_reverse_data_provider_to_services(tmp_path: Path) -> None:
    """Reject a new src.data_provider → src.services reverse import (issue #1082)."""

    _write_module(tmp_path, "src/services/svc.py", "VALUE = 1\n")
    _write_module(tmp_path, "src/data_provider/clean.py", "VALUE = 0\n")
    baseline = tmp_path / "scripts" / "layer_direction_baseline.json"
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(serialize_baseline([], hard_ceiling=0), encoding="utf-8")
    assert collect_violations(tmp_path, baseline) == []

    _write_module(
        tmp_path,
        "src/data_provider/clean.py",
        "from src.services.svc import VALUE\n",
    )
    violations = collect_violations(tmp_path, baseline)
    reverse = [item for item in violations if item.rule == "new-reverse-edge"]
    assert len(reverse) == 1
    assert reverse[0].path == "src/data_provider/clean.py"
    assert reverse[0].from_package == "src.data_provider"
    assert reverse[0].to_package == "src.services"
    # hard_ceiling=0 also reports hard-ceiling when any reverse edge exists
    assert any(item.rule == "hard-ceiling" for item in violations)


def test_detects_pipeline_to_services_reverse(tmp_path: Path) -> None:
    """pipeline.py importing services is reverse of services → pipeline."""

    _write_module(tmp_path, "src/services/svc.py", "VALUE = 1\n")
    _write_module(
        tmp_path,
        "src/core/pipeline.py",
        "from src.services.svc import VALUE\n",
    )
    baseline = tmp_path / "scripts" / "layer_direction_baseline.json"
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(serialize_baseline([], hard_ceiling=0), encoding="utf-8")
    violations = collect_violations(tmp_path, baseline)
    assert any(
        item.path == "src/core/pipeline.py" and item.to_package == "src.services"
        for item in violations
    )


def test_forward_src_api_to_services_is_allowed(tmp_path: Path) -> None:
    """src.api → services is the intended direction and must not be flagged."""

    _write_module(tmp_path, "src/services/svc.py", "VALUE = 1\n")
    _write_module(tmp_path, "src/api/app.py", "from src.services.svc import VALUE\n")
    edges = scan_reverse_edges(tmp_path)
    assert edges == []


def test_detects_services_to_src_api_reverse(tmp_path: Path) -> None:
    """Reject src.services → src.api so the HTTP one-way rule survives the move."""

    _write_module(tmp_path, "src/api/app.py", "VALUE = 1\n")
    _write_module(
        tmp_path,
        "src/services/svc.py",
        "from src.api.app import VALUE\n",
    )
    baseline = tmp_path / "scripts" / "layer_direction_baseline.json"
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(serialize_baseline([], hard_ceiling=0), encoding="utf-8")
    violations = collect_violations(tmp_path, baseline)
    assert any(
        item.path == "src/services/svc.py" and item.to_package == "src.api"
        for item in violations
    )


def test_write_baseline_allows_shrink_refuses_growth(tmp_path: Path) -> None:
    """--write-baseline may shrink exceptions but must refuse growth."""

    _write_module(tmp_path, "src/services/svc.py", "VALUE = 1\n")
    _write_module(
        tmp_path,
        "src/data_provider/a.py",
        "from src.services.svc import VALUE\n",
    )
    baseline = tmp_path / "scripts" / "layer_direction_baseline.json"
    edges = scan_reverse_edges(tmp_path)
    assert edges == [("src/data_provider/a.py", "src.data_provider", "src.services")]
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(
        serialize_baseline(edges, hard_ceiling=len(edges)),
        encoding="utf-8",
    )

    _write_module(
        tmp_path,
        "src/data_provider/b.py",
        "from src.services.svc import VALUE\n",
    )
    assert write_baseline(tmp_path, baseline) == 1

    _write_module(tmp_path, "src/data_provider/b.py", "VALUE = 0\n")
    _write_module(tmp_path, "src/data_provider/a.py", "VALUE = 0\n")
    assert write_baseline(tmp_path, baseline) == 0
    assert load_baseline(baseline) == []


def test_baseline_hard_ceiling_matches_introduction_inventory() -> None:
    """Hard ceiling pins introduction debt; never raise it to green CI."""

    payload_edges = load_baseline(BASELINE)
    assert len(payload_edges) <= 12


# --- issue #1555: import-time placement, TYPE_CHECKING, lazy inventory ----------

_EAGER_PLACEMENTS = {
    "try": (
        "try:\n"
        "    from src.services.svc import VALUE\n"
        "except ImportError:\n"
        "    VALUE = None\n"
    ),
    "except-handler": (
        "try:\n"
        "    VALUE = 0\n"
        "except ImportError:\n"
        "    from src.services.svc import VALUE\n"
    ),
    "try-else": (
        "try:\n"
        "    VALUE = 0\n"
        "except ImportError:\n"
        "    pass\n"
        "else:\n"
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
    "for": ("for _ in range(1):\n    from src.services.svc import VALUE\n"),
    "for-else": (
        "for _ in range(1):\n"
        "    pass\n"
        "else:\n"
        "    from src.services.svc import VALUE\n"
    ),
    "while-else": (
        "while False:\n"
        "    pass\n"
        "else:\n"
        "    from src.services.svc import VALUE\n"
    ),
    "match-case": (
        "MODE = 'a'\n"
        "match MODE:\n"
        "    case 'a':\n"
        "        from src.services.svc import VALUE\n"
        "    case _:\n"
        "        VALUE = None\n"
    ),
    "class-body": ("class Loader:\n    from src.services.svc import VALUE\n"),
    "class-body-in-try": (
        "try:\n"
        "    class Loader:\n"
        "        if True:\n"
        "            from src.services.svc import VALUE\n"
        "except ImportError:\n"
        "    Loader = None\n"
    ),
}

_TYPE_CHECKING_PLACEMENTS = {
    "plain": (
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from src.services.svc import VALUE\n"
    ),
    "symbol-alias": (
        "from typing import TYPE_CHECKING as TC\n"
        "if TC:\n"
        "    from src.services.svc import VALUE\n"
    ),
    "module-attribute": (
        "import typing\n"
        "if typing.TYPE_CHECKING:\n"
        "    from src.services.svc import VALUE\n"
    ),
    "module-alias-attribute": (
        "import typing as t\n"
        "if t.TYPE_CHECKING:\n"
        "    from src.services.svc import VALUE\n"
    ),
    "typing-extensions": (
        "from typing_extensions import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from src.services.svc import VALUE\n"
    ),
    "not-branch-else": (
        "from typing import TYPE_CHECKING\n"
        "if not TYPE_CHECKING:\n"
        "    VALUE = 0\n"
        "else:\n"
        "    from src.services.svc import VALUE\n"
    ),
    "nested-in-try": (
        "from typing import TYPE_CHECKING\n"
        "try:\n"
        "    if TYPE_CHECKING:\n"
        "        from src.services.svc import VALUE\n"
        "except ImportError:\n"
        "    pass\n"
    ),
}

_LAZY_PLACEMENTS = {
    "def": (
        "def load():\n    from src.services.svc import VALUE\n    return VALUE\n"
    ),
    "async-def": (
        "async def load():\n    from src.services.svc import VALUE\n    return VALUE\n"
    ),
    "method": (
        "class Loader:\n"
        "    def load(self):\n"
        "        from src.services.svc import VALUE\n"
        "        return VALUE\n"
    ),
    "nested-def": (
        "def outer():\n"
        "    def inner():\n"
        "        from src.services.svc import VALUE\n"
        "        return VALUE\n"
        "    return inner\n"
    ),
    "class-in-def": (
        "def outer():\n"
        "    class Inner:\n"
        "        from src.services.svc import VALUE\n"
        "    return Inner\n"
    ),
    "def-in-try": (
        "try:\n"
        "    def load():\n"
        "        from src.services.svc import VALUE\n"
        "        return VALUE\n"
        "except ImportError:\n"
        "    load = None\n"
    ),
}

_PROBE = "src/data_provider/probe.py"
_PROBE_EDGE = (_PROBE, "src.data_provider", "src.services")


def _placement_fixture(root: Path, source: str) -> Path:
    """Write a provider probe plus an empty baseline and return the baseline path."""

    _write_module(root, "src/services/svc.py", "VALUE = 1\n")
    _write_module(root, _PROBE, source)
    baseline = root / "scripts" / "layer_direction_baseline.json"
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(serialize_baseline([], hard_ceiling=0), encoding="utf-8")
    return baseline


@pytest.mark.parametrize("placement", sorted(_EAGER_PLACEMENTS))
def test_nested_import_time_reverse_edge_is_enforced(
    placement: str, tmp_path: Path
) -> None:
    """Imports nested in eagerly executed bodies are real module-level edges."""

    baseline = _placement_fixture(tmp_path, _EAGER_PLACEMENTS[placement])
    assert scan_reverse_edges(tmp_path) == [_PROBE_EDGE]
    assert scan_lazy_reverse_edges(tmp_path) == []
    violations = collect_violations(tmp_path, baseline)
    assert [item.path for item in violations if item.rule == "new-reverse-edge"] == [
        _PROBE
    ]


@pytest.mark.parametrize("placement", sorted(_EAGER_PLACEMENTS))
def test_top_level_helper_keeps_its_narrower_contract(
    placement: str, tmp_path: Path
) -> None:
    """``top_level_import_modules`` stays module-body-only for its own callers."""

    _placement_fixture(tmp_path, _EAGER_PLACEMENTS[placement])
    probe = tmp_path / _PROBE
    assert "src.services.svc" not in top_level_import_modules(tmp_path, probe)
    assert "src.services.svc" in import_time_import_modules(tmp_path, probe)


@pytest.mark.parametrize("placement", sorted(_TYPE_CHECKING_PLACEMENTS))
def test_type_checking_imports_are_never_edges(placement: str, tmp_path: Path) -> None:
    """``if TYPE_CHECKING:`` bodies never execute, so they stay excluded."""

    baseline = _placement_fixture(tmp_path, _TYPE_CHECKING_PLACEMENTS[placement])
    assert scan_reverse_edges(tmp_path) == []
    assert scan_lazy_reverse_edges(tmp_path) == []
    assert collect_violations(tmp_path, baseline) == []


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            "from typing import TYPE_CHECKING\n"
            "TYPE_CHECKING = True\n"
            "if TYPE_CHECKING:\n"
            "    from src.services.svc import VALUE\n",
            id="rebound-by-assignment",
        ),
        pytest.param(
            "from src.data_provider.flags import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from src.services.svc import VALUE\n",
            id="imported-from-elsewhere",
        ),
        pytest.param(
            "import typing\n"
            "typing = object()\n"
            "if typing.TYPE_CHECKING:\n"
            "    from src.services.svc import VALUE\n",
            id="shadowed-module-alias",
        ),
        pytest.param(
            "if TYPE_CHECKING:\n    from src.services.svc import VALUE\n",
            id="never-bound",
        ),
        pytest.param(
            "from typing import TYPE_CHECKING\n"
            "if not TYPE_CHECKING:\n"
            "    from src.services.svc import VALUE\n",
            id="not-branch-runs-at-import-time",
        ),
    ],
)
def test_type_checking_exclusion_is_binding_aware(source: str, tmp_path: Path) -> None:
    """Only a real ``typing.TYPE_CHECKING`` binding suppresses an edge."""

    _placement_fixture(tmp_path, source)
    assert scan_reverse_edges(tmp_path) == [_PROBE_EDGE]


def test_class_body_type_checking_rebinding_does_not_leak(tmp_path: Path) -> None:
    """A class-scoped ``TYPE_CHECKING`` rebinding must not clear the module alias."""

    _placement_fixture(
        tmp_path,
        "from typing import TYPE_CHECKING\n"
        "class Shadow:\n"
        "    TYPE_CHECKING = True\n"
        "if TYPE_CHECKING:\n"
        "    from src.services.svc import VALUE\n",
    )
    assert scan_reverse_edges(tmp_path) == []


@pytest.mark.parametrize("placement", sorted(_LAZY_PLACEMENTS))
def test_function_local_reverse_import_is_advisory_only(
    placement: str, tmp_path: Path
) -> None:
    """Deferred loads stay unenforced but become visible in the lazy inventory."""

    baseline = _placement_fixture(tmp_path, _LAZY_PLACEMENTS[placement])
    assert scan_reverse_edges(tmp_path) == []
    assert collect_violations(tmp_path, baseline) == []
    assert scan_lazy_reverse_edges(tmp_path) == [_PROBE_EDGE]


_BOTH_PLACEMENTS = (
    "from src.services.svc import VALUE\n"
    "def load():\n"
    "    from src.services.svc import VALUE as OTHER\n"
    "    return OTHER\n"
)


def test_lazy_inventory_dedupes_against_scanned_import_time_edges(
    tmp_path: Path,
) -> None:
    """A file importing the same target both ways is counted once, as eager."""

    baseline = _placement_fixture(tmp_path, _BOTH_PLACEMENTS)
    # The fixture ships an empty enforced allowlist, so nothing in `exceptions`
    # can explain the suppression: the dedupe is against the scan.
    assert load_baseline(baseline) == []
    assert scan_reverse_edges(tmp_path) == [_PROBE_EDGE]
    assert scan_lazy_reverse_edges(tmp_path) == []


def test_lazy_dedupe_holds_while_the_enforced_ratchet_is_red(tmp_path: Path) -> None:
    """Dedupe is against the measurement, not the baseline ``exceptions`` array.

    Here the edge is a *violation* — it is scanned import-time but absent from
    the enforced allowlist. It must still be withheld from the advisory
    inventory, because the ratchet already reports it.
    """

    baseline = _placement_fixture(tmp_path, _BOTH_PLACEMENTS)
    assert _PROBE_EDGE not in load_baseline(baseline)
    violations = collect_violations(tmp_path, baseline)
    assert "new-reverse-edge" in {v.rule for v in violations}
    assert scan_lazy_reverse_edges(tmp_path) == []


def test_lazy_inventory_drift_and_refresh(tmp_path: Path) -> None:
    """Advisory drift is reported, refreshable, and never enters enforcement."""

    baseline = _placement_fixture(tmp_path, _LAZY_PLACEMENTS["def"])
    assert load_lazy_inventory(baseline) == []
    assert lazy_inventory_drift(tmp_path, baseline) == ([_PROBE_EDGE], [])

    assert write_baseline(tmp_path, baseline) == 0
    assert load_lazy_inventory(baseline) == [_PROBE_EDGE]
    assert load_baseline(baseline) == []
    assert lazy_inventory_drift(tmp_path, baseline) == ([], [])

    _write_module(tmp_path, _PROBE, "VALUE = 0\n")
    assert lazy_inventory_drift(tmp_path, baseline) == ([], [_PROBE_EDGE])


def test_lazy_inventory_is_optional_in_the_baseline(tmp_path: Path) -> None:
    """Baselines written before the advisory section still load."""

    baseline = _placement_fixture(tmp_path, "VALUE = 0\n")
    payload = json.loads(baseline.read_text(encoding="utf-8"))
    payload.pop("lazy_exceptions", None)
    payload.pop("lazy_exception_count", None)
    baseline.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    assert load_lazy_inventory(baseline) == []
    assert lazy_inventory_drift(tmp_path, baseline) == ([], [])


_MALFORMED_LAZY_SECTIONS = {
    "not-a-list": ({"lazy_exceptions": "nope"}, "must be a list"),
    "bad-entry-shape": (
        {
            "lazy_exceptions": [{"path": "src/data_provider/x.py"}],
            "lazy_exception_count": 1,
        },
        "from_package must be a non-empty string",
    ),
    "not-a-configured-rule": (
        {
            "lazy_exceptions": [
                {
                    "path": "src/utils/x.py",
                    "from_package": "src.utils",
                    "to_package": "src.services",
                }
            ],
            "lazy_exception_count": 1,
        },
        "is not a configured reverse rule",
    ),
    "count-mismatch": ({"lazy_exception_count": 99}, "does not match"),
    "unsorted": (
        {
            "lazy_exceptions": [
                {
                    "path": "src/data_provider/z.py",
                    "from_package": "src.data_provider",
                    "to_package": "src.services",
                },
                {
                    "path": "src/data_provider/a.py",
                    "from_package": "src.data_provider",
                    "to_package": "src.services",
                },
            ],
            "lazy_exception_count": 2,
        },
        "must be sorted lexicographically",
    ),
    "duplicate-entry": (
        {
            "lazy_exceptions": [
                {
                    "path": "src/data_provider/a.py",
                    "from_package": "src.data_provider",
                    "to_package": "src.services",
                },
                {
                    "path": "src/data_provider/a.py",
                    "from_package": "src.data_provider",
                    "to_package": "src.services",
                },
            ],
            "lazy_exception_count": 2,
        },
        "duplicate baseline lazy_exceptions entry",
    ),
}


def _patch_baseline(baseline: Path, overrides: dict[str, object]) -> None:
    payload = json.loads(baseline.read_text(encoding="utf-8"))
    payload.update(overrides)
    baseline.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


@pytest.mark.parametrize("shape", sorted(_MALFORMED_LAZY_SECTIONS))
def test_lazy_inventory_rejects_a_malformed_section(shape: str, tmp_path: Path) -> None:
    """The advisory section is validated like the enforced one, not trusted blindly."""

    overrides, expected = _MALFORMED_LAZY_SECTIONS[shape]
    baseline = _placement_fixture(tmp_path, "VALUE = 0\n")
    _patch_baseline(baseline, overrides)
    with pytest.raises(BaselineError, match=expected):
        load_lazy_inventory(baseline)


@pytest.mark.parametrize("shape", sorted(_MALFORMED_LAZY_SECTIONS))
def test_cli_rejects_a_malformed_lazy_section_without_a_traceback(
    shape: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Malformed advisory state fails closed through the standard CLI contract.

    Advisory means *drift* never fails; a baseline the guard cannot parse is a
    different thing and must still exit 1 with the guard's own error line
    instead of an unhandled ``BaselineError`` traceback (review finding §8.1).
    """

    overrides, expected = _MALFORMED_LAZY_SECTIONS[shape]
    baseline = _placement_fixture(tmp_path, "VALUE = 0\n")
    _patch_baseline(baseline, overrides)

    exit_code = main(["--root", str(tmp_path), "--baseline", str(baseline)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "[layer-direction] ERROR: invalid-baseline:" in captured.err
    assert expected in captured.err
    assert "Traceback" not in captured.err


def test_write_baseline_repairs_a_malformed_lazy_section(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--write-baseline`` regenerates the advisory section instead of refusing.

    The fail-closed contract covers the *checking* run (what CI executes). The
    refresh path rewrites `lazy_exceptions` from the scan, so it is also the
    documented repair for a hand-broken advisory section.
    """

    baseline = _placement_fixture(tmp_path, _LAZY_PLACEMENTS["def"])
    _patch_baseline(baseline, {"lazy_exceptions": "nope"})
    with pytest.raises(BaselineError):
        load_lazy_inventory(baseline)

    refresh = ["--root", str(tmp_path), "--baseline", str(baseline), "--write-baseline"]
    assert main(refresh) == 0
    assert load_lazy_inventory(baseline) == [_PROBE_EDGE]
    capsys.readouterr()
    assert main(["--root", str(tmp_path), "--baseline", str(baseline)]) == 0


def test_cli_reports_a_malformed_lazy_section_even_with_reverse_violations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Baseline validation runs before edge reporting, so it cannot be masked."""

    baseline = _placement_fixture(tmp_path, "from src.services.svc import VALUE\n")
    _patch_baseline(baseline, {"lazy_exceptions": "nope"})

    exit_code = main(["--root", str(tmp_path), "--baseline", str(baseline)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "[layer-direction] ERROR: invalid-baseline:" in captured.err
    assert "Traceback" not in captured.err


def test_cli_never_fails_on_advisory_lazy_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Growth and shrink of the advisory inventory stay exit-code neutral.

    This is the contract the docs and the PR body state: a deferred load added
    or removed anywhere in the tree only changes ``NOTE:`` output. Nothing —
    the guard or this suite — pins the live inventory to the checked-in seed.
    """

    baseline = _placement_fixture(tmp_path, _LAZY_PLACEMENTS["def"])

    # Growth: the tree has a lazy edge the seed does not record.
    assert main(["--root", str(tmp_path), "--baseline", str(baseline)]) == 0
    growth = capsys.readouterr().out
    assert "NOTE: lazy-inventory-growth" in growth
    assert "ERROR" not in growth

    assert write_baseline(tmp_path, baseline) == 0
    capsys.readouterr()
    assert main(["--root", str(tmp_path), "--baseline", str(baseline)]) == 0
    assert "lazy-inventory-" not in capsys.readouterr().out

    # Shrink: the seed records a lazy edge the tree no longer has.
    _write_module(tmp_path, _PROBE, "VALUE = 0\n")
    assert main(["--root", str(tmp_path), "--baseline", str(baseline)]) == 0
    shrink = capsys.readouterr().out
    assert "NOTE: lazy-inventory-shrink" in shrink
    assert "ERROR" not in shrink


def test_diff_lazy_inventory_is_pure_set_arithmetic() -> None:
    """The reporter's drift helper needs no tree scan and no baseline read."""

    other = ("src/data_provider/other.py", "src.data_provider", "src.services")
    assert diff_lazy_inventory([_PROBE_EDGE], []) == ([_PROBE_EDGE], [])
    assert diff_lazy_inventory([], [_PROBE_EDGE]) == ([], [_PROBE_EDGE])
    assert diff_lazy_inventory([_PROBE_EDGE], [_PROBE_EDGE]) == ([], [])
    assert diff_lazy_inventory([other], [_PROBE_EDGE]) == ([other], [_PROBE_EDGE])


def test_repository_inventories_are_not_inflated() -> None:
    """Recursion must not grow the shipped enforced inventory or its ceiling."""

    payload = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert payload["hard_ceiling"] == 12
    assert payload["exception_count"] == 12
    assert len(load_baseline(BASELINE)) == 12
    assert scan_reverse_edges(ROOT) == load_baseline(BASELINE)


def test_repository_lazy_inventory_seed_is_well_formed() -> None:
    """Validate the shipped advisory seed's schema — never its live equality.

    Deliberately does **not** assert ``lazy_inventory_drift(ROOT, BASELINE) ==
    ([], [])``. Adding or removing a function-local reverse import anywhere in
    ``src/`` is advisory by design, so it must not be able to turn this suite
    red on the PR that makes the change or on a later push to ``main``.
    """

    seed = load_lazy_inventory(BASELINE)
    payload = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert payload["lazy_exception_count"] == len(seed)
    assert seed == sorted(set(seed))
    # The advisory inventory is disjoint from enforcement and uncapped: it is
    # neither folded into exception_count nor charged against hard_ceiling.
    assert not set(seed) & set(load_baseline(BASELINE))
    assert payload["exception_count"] == len(load_baseline(BASELINE))
    assert payload["hard_ceiling"] >= payload["exception_count"]


def test_repository_lazy_drift_stays_advisory() -> None:
    """Whatever the live tree holds, the shipped guard still exits 0."""

    added, removed = lazy_inventory_drift(ROOT, BASELINE)
    assert isinstance(added, list) and isinstance(removed, list)
    assert main([]) == 0
