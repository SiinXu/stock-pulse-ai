#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Enforce a measured offline-suite coverage floor (one-way ratchet).

Reads a coverage.py JSON report (``coverage.json`` by default) produced by the
CI gate's offline suite and fails when the combined line coverage for the
scoped packages falls below the checked-in floor.

The floor is intentionally measured, not aspirational: set it to
``measured_percent - epsilon`` after a clean offline run. Raising the floor is
always allowed; lowering it requires an explicit ``--allow-lower`` flag so
accidental regressions cannot silently rewrite the baseline.

Anti-lowering vs ``origin/main``
--------------------------------
The working-tree ``floor_percent`` must not fall below the value checked in on
``origin/main`` (see ``assert_floor_not_lowered_vs_ref``). Raising is free.
Missing refs / first-run clones skip the comparison with a logged notice.

Legitimate floor lowering (maintainers only; keep it honest and loud)
---------------------------------------------------------------------
1. Re-measure the offline suite and run
   ``python scripts/check_coverage_floor.py --write-baseline --allow-lower``.
2. Open a dedicated PR that lowers ``floor_percent`` and explains the regression.
3. In that same PR, set environment variable
   ``COVERAGE_FLOOR_ALLOW_LOWER_VS_MAIN=1`` for the gate job *or* temporarily
   edit this script's comparison so review sees an explicit maintainer decision
   (do not silently lower only the JSON).
4. After merge, clear the override so the ratchet re-arms against the new floor
   on ``origin/main``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = ROOT / "scripts" / "coverage_floor_baseline.json"
DEFAULT_REPORT = ROOT / "coverage.json"
BASELINE_VERSION = 1
DEFAULT_EPSILON = 0.5
DEFAULT_MAIN_REF = "origin/main"
SCOPED_PACKAGES = ("src", "api", "data_provider", "bot")
ALLOW_LOWER_VS_MAIN_ENV = "COVERAGE_FLOOR_ALLOW_LOWER_VS_MAIN"


class BaselineError(ValueError):
    """Raised when the checked-in baseline is malformed."""


class ReportError(ValueError):
    """Raised when a coverage report cannot be interpreted."""


@dataclass(frozen=True)
class Baseline:
    """Checked-in coverage floor and provenance."""

    floor_percent: float
    measured_percent: float
    epsilon: float
    packages: tuple[str, ...]
    measured_command: str
    notes: str

    def as_json(self) -> dict[str, Any]:
        """Render the baseline document."""

        return {
            "version": BASELINE_VERSION,
            "description": (
                "Measured offline-suite line-coverage floor for the packages "
                "listed under packages. Floor is measured_percent - epsilon. "
                "Do not lower floor_percent without an explicit --allow-lower "
                "review; raise it only after a clean offline measurement. "
                "The gate also refuses a working-tree floor lower than "
                f"{DEFAULT_MAIN_REF} unless {ALLOW_LOWER_VS_MAIN_ENV}=1."
            ),
            "packages": list(self.packages),
            "floor_percent": self.floor_percent,
            "measured_percent": self.measured_percent,
            "epsilon": self.epsilon,
            "measured_command": self.measured_command,
            "notes": self.notes,
        }


def load_baseline(path: Path) -> Baseline:
    """Load and validate the coverage-floor baseline."""

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

    try:
        floor = float(payload["floor_percent"])
        measured = float(payload["measured_percent"])
        epsilon = float(payload.get("epsilon", DEFAULT_EPSILON))
    except (KeyError, TypeError, ValueError) as exc:
        raise BaselineError(
            "baseline requires numeric floor_percent, measured_percent, "
            f"and optional epsilon: {exc}"
        ) from exc

    if not 0.0 <= floor <= 100.0:
        raise BaselineError(f"floor_percent out of range: {floor}")
    if not 0.0 <= measured <= 100.0:
        raise BaselineError(f"measured_percent out of range: {measured}")
    if epsilon < 0.0:
        raise BaselineError(f"epsilon must be non-negative: {epsilon}")

    packages = payload.get("packages")
    if not isinstance(packages, list) or not packages or not all(
        isinstance(item, str) and item for item in packages
    ):
        raise BaselineError("baseline.packages must be a non-empty string list")

    measured_command = payload.get("measured_command", "")
    notes = payload.get("notes", "")
    if not isinstance(measured_command, str) or not isinstance(notes, str):
        raise BaselineError("measured_command and notes must be strings")

    return Baseline(
        floor_percent=floor,
        measured_percent=measured,
        epsilon=epsilon,
        packages=tuple(packages),
        measured_command=measured_command,
        notes=notes,
    )


def serialize_baseline(baseline: Baseline) -> str:
    """Render the baseline JSON document with stable formatting."""

    return json.dumps(baseline.as_json(), indent=2, sort_keys=False) + "\n"


def read_total_percent(report_path: Path) -> float:
    """Extract totals.percent_covered from a coverage.py JSON report."""

    payload = _load_report_payload(report_path)
    totals = payload.get("totals")
    if not isinstance(totals, Mapping):
        raise ReportError("coverage report missing totals object")
    percent = totals.get("percent_covered")
    if not isinstance(percent, (int, float)):
        raise ReportError(
            "coverage report totals.percent_covered must be a number; "
            f"got {type(percent).__name__}"
        )
    value = float(percent)
    if not 0.0 <= value <= 100.0:
        raise ReportError(f"percent_covered out of range: {value}")
    return value


def _load_report_payload(report_path: Path) -> dict[str, Any]:
    """Load a coverage.py JSON report object."""

    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReportError(f"coverage report not found: {report_path}") from exc
    except json.JSONDecodeError as exc:
        raise ReportError(f"coverage report is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ReportError("coverage report root must be an object")
    return payload


def report_file_paths(report_path: Path) -> tuple[str, ...]:
    """Return measured file paths from a coverage.py JSON report."""

    payload = _load_report_payload(report_path)
    files = payload.get("files")
    if files is None:
        return ()
    if not isinstance(files, Mapping):
        raise ReportError("coverage report files must be an object when present")
    return tuple(str(path) for path in files.keys())


def package_prefixes_missing(
    file_paths: Sequence[str],
    packages: Sequence[str],
) -> list[str]:
    """Return baseline package prefixes with no measured files in the report.

    A path matches package ``P`` when it is exactly ``P``, starts with ``P/``,
    or starts with ``P\\`` (Windows-style). This makes ``baseline.packages``
    enforceable: narrowing ``--cov=`` to a single well-covered package fails.
    """

    missing: list[str] = []
    for package in packages:
        prefix_fwd = f"{package}/"
        prefix_bwd = f"{package}\\"
        if any(
            path == package
            or path.startswith(prefix_fwd)
            or path.startswith(prefix_bwd)
            for path in file_paths
        ):
            continue
        missing.append(package)
    return missing


def assert_cov_flags_match_packages(
    cov_packages: Sequence[str],
    baseline_packages: Sequence[str],
) -> list[str]:
    """Return violations when ``--cov`` packages do not match the baseline.

    Order-sensitive exact match: the gate must pass the same package list the
    baseline documents, so the measured total cannot silently exclude scopes.
    """

    cov_list = list(cov_packages)
    base_list = list(baseline_packages)
    if cov_list == base_list:
        return []
    return [
        (
            "coverage --cov packages "
            f"{cov_list!r} do not match baseline.packages {base_list!r} exactly"
        )
    ]


def floor_from_measurement(
    measured: float,
    *,
    epsilon: float = DEFAULT_EPSILON,
) -> float:
    """Derive a floor slightly below the measured total coverage."""

    if not 0.0 <= measured <= 100.0:
        raise ValueError(f"measured percent out of range: {measured}")
    if epsilon < 0.0:
        raise ValueError(f"epsilon must be non-negative: {epsilon}")
    return max(0.0, round(measured - epsilon, 2))


def evaluate(
    *,
    actual: float,
    floor: float,
) -> list[str]:
    """Return human-readable violations for an actual coverage percentage."""

    if actual + 1e-9 < floor:
        return [
            (
                f"coverage {actual:.2f}% is below the floor {floor:.2f}%. "
                "Raise tests or implementation coverage; do not lower the floor "
                "without an explicit review (--allow-lower)."
            )
        ]
    return []


def load_ref_floor_percent(
    *,
    ref: str = DEFAULT_MAIN_REF,
    baseline_git_path: str = "scripts/coverage_floor_baseline.json",
    repo: Path = ROOT,
    git_show=None,
) -> float | None:
    """Load ``floor_percent`` from ``ref:baseline_git_path``.

    Returns ``None`` when the ref or blob is missing (first-run / shallow clone
    without the remote tip). Callers log a notice and skip the anti-lowering
    check in that case.
    """

    runner = git_show or _git_show
    try:
        stdout, returncode = runner(ref, baseline_git_path, repo=repo)
    except OSError as exc:
        print(
            f"[coverage-floor] NOTICE: cannot run git show for {ref}: {exc}; "
            "skipping anti-lowering comparison",
            file=sys.stderr,
        )
        return None

    if returncode != 0 or not stdout.strip():
        return None

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        print(
            f"[coverage-floor] NOTICE: {ref}:{baseline_git_path} is not valid "
            f"JSON ({exc}); skipping anti-lowering comparison",
            file=sys.stderr,
        )
        return None

    if not isinstance(payload, dict):
        print(
            f"[coverage-floor] NOTICE: {ref}:{baseline_git_path} root is not "
            "an object; skipping anti-lowering comparison",
            file=sys.stderr,
        )
        return None

    try:
        floor = float(payload["floor_percent"])
    except (KeyError, TypeError, ValueError) as exc:
        print(
            f"[coverage-floor] NOTICE: {ref}:{baseline_git_path} missing "
            f"numeric floor_percent ({exc}); skipping anti-lowering comparison",
            file=sys.stderr,
        )
        return None

    if not 0.0 <= floor <= 100.0:
        print(
            f"[coverage-floor] NOTICE: {ref} floor_percent out of range "
            f"({floor}); skipping anti-lowering comparison",
            file=sys.stderr,
        )
        return None
    return floor


def _git_show(ref: str, path: str, *, repo: Path) -> tuple[str, int]:
    """Run ``git show ref:path`` and return (stdout, returncode)."""

    completed = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout, completed.returncode


def allow_lower_vs_main_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Return True when the loud maintainer override env var is set."""

    source = env if env is not None else os.environ
    raw = str(source.get(ALLOW_LOWER_VS_MAIN_ENV, "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def assert_floor_not_lowered_vs_ref(
    baseline_path: Path,
    *,
    ref: str = DEFAULT_MAIN_REF,
    repo: Path = ROOT,
    git_show=None,
    env: Mapping[str, str] | None = None,
) -> int:
    """Fail when the working-tree floor is below the floor on ``ref``.

    Missing refs skip with a notice (exit 0). An explicit maintainer override
    via ``COVERAGE_FLOOR_ALLOW_LOWER_VS_MAIN=1`` also skips with a loud notice.
    """

    baseline = load_baseline(baseline_path)
    if allow_lower_vs_main_enabled(env):
        print(
            (
                f"[coverage-floor] NOTICE: {ALLOW_LOWER_VS_MAIN_ENV} is set; "
                f"skipping anti-lowering comparison against {ref}. "
                "This override is for intentional maintainer floor lowers only; "
                "clear it after the new floor lands on main."
            ),
            file=sys.stderr,
        )
        return 0

    ref_floor = load_ref_floor_percent(
        ref=ref,
        repo=repo,
        git_show=git_show,
    )
    if ref_floor is None:
        print(
            (
                f"[coverage-floor] NOTICE: could not load floor from "
                f"{ref}:scripts/coverage_floor_baseline.json; "
                "skipping anti-lowering comparison (missing ref or first-run)"
            ),
            file=sys.stderr,
        )
        return 0

    if baseline.floor_percent + 1e-9 < ref_floor:
        print(
            (
                f"[coverage-floor] ERROR: working-tree floor "
                f"{baseline.floor_percent:.2f}% is below {ref} floor "
                f"{ref_floor:.2f}%. Raising the floor is free; lowering "
                f"requires an explicit maintainer review. See module docstring "
                f"and set {ALLOW_LOWER_VS_MAIN_ENV}=1 only for intentional "
                "lowers (keep the override temporary and loud)."
            ),
            file=sys.stderr,
        )
        return 1

    print(
        f"[coverage-floor] OK: floor {baseline.floor_percent:.2f}% >= "
        f"{ref} floor {ref_floor:.2f}%"
    )
    return 0


def write_baseline_from_report(
    report_path: Path,
    baseline_path: Path,
    *,
    epsilon: float,
    allow_lower: bool,
    measured_command: str,
    notes: str,
) -> int:
    """Rewrite the baseline floor from a measured coverage report."""

    measured = read_total_percent(report_path)
    new_floor = floor_from_measurement(measured, epsilon=epsilon)

    previous: Baseline | None = None
    if baseline_path.is_file():
        previous = load_baseline(baseline_path)
        if new_floor + 1e-9 < previous.floor_percent and not allow_lower:
            print(
                (
                    f"[coverage-floor] ERROR: refusing to lower floor from "
                    f"{previous.floor_percent:.2f}% to {new_floor:.2f}% "
                    f"(measured {measured:.2f}%, epsilon {epsilon}). "
                    "Re-run with --allow-lower after an explicit review."
                ),
                file=sys.stderr,
            )
            return 1

    baseline = Baseline(
        floor_percent=new_floor,
        measured_percent=round(measured, 4),
        epsilon=epsilon,
        packages=SCOPED_PACKAGES,
        measured_command=measured_command
        or (
            "python -m pytest -m 'not network and not benchmark' "
            "--cov=src --cov=api --cov=data_provider --cov=bot "
            "--cov-report=json:coverage.json"
        ),
        notes=notes
        or (
            "Floor is measured offline-suite total line coverage minus epsilon. "
            "Update only after a clean gate run."
        ),
    )
    baseline_path.write_text(serialize_baseline(baseline), encoding="utf-8")
    print(
        f"[coverage-floor] wrote floor {baseline.floor_percent:.2f}% "
        f"(measured {baseline.measured_percent:.4f}%, epsilon {epsilon}) "
        f"to {baseline_path}"
    )
    return 0


def run_check(report_path: Path, baseline_path: Path) -> int:
    """Compare the coverage report against the checked-in floor and scope."""

    baseline = load_baseline(baseline_path)
    file_paths = report_file_paths(report_path)
    missing_packages = package_prefixes_missing(file_paths, baseline.packages)
    if missing_packages:
        print(
            (
                "[coverage-floor] ERROR: coverage report is missing measured "
                f"files under baseline package prefix(es): "
                f"{', '.join(missing_packages)}. "
                "Do not narrow --cov= below baseline.packages; the gate must "
                "measure every scoped package."
            ),
            file=sys.stderr,
        )
        return 1

    actual = read_total_percent(report_path)
    violations = evaluate(actual=actual, floor=baseline.floor_percent)
    if violations:
        for message in violations:
            print(f"[coverage-floor] ERROR: {message}", file=sys.stderr)
        print(
            (
                f"[coverage-floor] actual={actual:.2f}% "
                f"floor={baseline.floor_percent:.2f}% "
                f"measured_at_write={baseline.measured_percent:.2f}% "
                f"report={report_path}"
            ),
            file=sys.stderr,
        )
        return 1

    print(
        f"[coverage-floor] OK: {actual:.2f}% >= floor {baseline.floor_percent:.2f}% "
        f"(packages={','.join(baseline.packages)}; report={report_path})"
    )
    return 0


def run_assert_cov_flags(
    baseline_path: Path,
    cov_packages: Sequence[str],
) -> int:
    """Assert CLI ``--cov`` package list matches ``baseline.packages`` exactly."""

    baseline = load_baseline(baseline_path)
    violations = assert_cov_flags_match_packages(cov_packages, baseline.packages)
    if violations:
        for message in violations:
            print(f"[coverage-floor] ERROR: {message}", file=sys.stderr)
        return 1
    print(
        f"[coverage-floor] OK: --cov packages match baseline.packages "
        f"exactly ({list(baseline.packages)!r})"
    )
    return 0


def run_self_tests() -> None:
    """Exercise floor derivation, parsing, scope, and anti-lowering."""

    cases = 0
    with tempfile.TemporaryDirectory(prefix="coverage-floor-") as tmp:
        root = Path(tmp)
        report = root / "coverage.json"
        baseline_path = root / "coverage_floor_baseline.json"

        def _write_report(
            percent: float,
            *,
            files: dict[str, Any] | None = None,
        ) -> None:
            payload: dict[str, Any] = {
                "meta": {"version": "7.0.0"},
                "files": files
                if files is not None
                else {
                    "src/mod.py": {"summary": {"percent_covered": percent}},
                    "api/mod.py": {"summary": {"percent_covered": percent}},
                    "data_provider/mod.py": {
                        "summary": {"percent_covered": percent}
                    },
                    "bot/mod.py": {"summary": {"percent_covered": percent}},
                },
                "totals": {
                    "covered_lines": int(percent * 10),
                    "num_statements": 1000,
                    "percent_covered": percent,
                    "missing_lines": 1000 - int(percent * 10),
                    "excluded_lines": 0,
                },
            }
            report.write_text(json.dumps(payload), encoding="utf-8")

        _write_report(43.0)
        measured = read_total_percent(report)
        if measured != 43.0:
            raise AssertionError(f"unexpected measured value: {measured}")
        cases += 1

        floor = floor_from_measurement(43.0, epsilon=0.5)
        if floor != 42.5:
            raise AssertionError(f"unexpected floor: {floor}")
        cases += 1

        if evaluate(actual=42.5, floor=42.5):
            raise AssertionError("exact floor should pass")
        cases += 1
        if not evaluate(actual=42.49, floor=42.5):
            raise AssertionError("below floor should fail")
        cases += 1

        rc = write_baseline_from_report(
            report,
            baseline_path,
            epsilon=0.5,
            allow_lower=False,
            measured_command="pytest --cov",
            notes="self-test",
        )
        if rc != 0:
            raise AssertionError("initial write failed")
        baseline = load_baseline(baseline_path)
        if baseline.floor_percent != 42.5:
            raise AssertionError(f"unexpected written floor: {baseline.floor_percent}")
        cases += 1

        # Raising measured coverage must be allowed to raise the floor.
        _write_report(50.0)
        rc = write_baseline_from_report(
            report,
            baseline_path,
            epsilon=0.5,
            allow_lower=False,
            measured_command="pytest --cov",
            notes="raised",
        )
        if rc != 0:
            raise AssertionError("raise write failed")
        baseline = load_baseline(baseline_path)
        if baseline.floor_percent != 49.5:
            raise AssertionError(f"floor did not raise: {baseline.floor_percent}")
        cases += 1

        # Lowering without --allow-lower must fail closed.
        _write_report(40.0)
        rc = write_baseline_from_report(
            report,
            baseline_path,
            epsilon=0.5,
            allow_lower=False,
            measured_command="pytest --cov",
            notes="lower-denied",
        )
        if rc == 0:
            raise AssertionError("lower without allow-lower must fail")
        baseline = load_baseline(baseline_path)
        if baseline.floor_percent != 49.5:
            raise AssertionError("floor was lowered without allow-lower")
        cases += 1

        rc = write_baseline_from_report(
            report,
            baseline_path,
            epsilon=0.5,
            allow_lower=True,
            measured_command="pytest --cov",
            notes="lower-allowed",
        )
        if rc != 0:
            raise AssertionError("allow-lower write failed")
        baseline = load_baseline(baseline_path)
        if baseline.floor_percent != 39.5:
            raise AssertionError(f"allow-lower floor wrong: {baseline.floor_percent}")
        cases += 1

        # Check path (full package scope present).
        _write_report(39.5)
        if run_check(report, baseline_path) != 0:
            raise AssertionError("equal floor should pass check")
        cases += 1
        _write_report(39.4)
        if run_check(report, baseline_path) == 0:
            raise AssertionError("below floor should fail check")
        cases += 1

        # Scope assertion: missing package prefix must fail.
        _write_report(
            90.0,
            files={
                "src/only.py": {"summary": {"percent_covered": 90.0}},
                "api/only.py": {"summary": {"percent_covered": 90.0}},
                # data_provider and bot intentionally absent
            },
        )
        # Keep floor low so only the package-scope check fails.
        baseline_path.write_text(
            serialize_baseline(
                Baseline(
                    floor_percent=10.0,
                    measured_percent=90.0,
                    epsilon=0.5,
                    packages=SCOPED_PACKAGES,
                    measured_command="self-test",
                    notes="scope-missing",
                )
            ),
            encoding="utf-8",
        )
        if run_check(report, baseline_path) == 0:
            raise AssertionError("missing package prefixes must fail check")
        cases += 1

        missing = package_prefixes_missing(
            ("src/a.py", "api/b.py"),
            SCOPED_PACKAGES,
        )
        if missing != ["data_provider", "bot"]:
            raise AssertionError(f"unexpected missing packages: {missing}")
        cases += 1

        if package_prefixes_missing(
            (
                "src/a.py",
                "api/b.py",
                "data_provider/c.py",
                "bot/d.py",
            ),
            SCOPED_PACKAGES,
        ):
            raise AssertionError("full package set should not report missing")
        cases += 1

        # --cov flag exact match.
        if assert_cov_flags_match_packages(
            ["src", "api", "data_provider", "bot"],
            SCOPED_PACKAGES,
        ):
            raise AssertionError("exact cov flags should match")
        cases += 1
        if not assert_cov_flags_match_packages(
            ["src"],
            SCOPED_PACKAGES,
        ):
            raise AssertionError("narrowed cov flags must fail")
        cases += 1
        if not assert_cov_flags_match_packages(
            ["src", "api", "bot", "data_provider"],
            SCOPED_PACKAGES,
        ):
            raise AssertionError("reordered cov flags must fail exact match")
        cases += 1
        if run_assert_cov_flags(
            baseline_path,
            ["src", "api", "data_provider", "bot"],
        ) != 0:
            raise AssertionError("run_assert_cov_flags should pass exact list")
        cases += 1
        if run_assert_cov_flags(baseline_path, ["src"]) == 0:
            raise AssertionError("run_assert_cov_flags should fail narrowed list")
        cases += 1

        # Anti-lowering vs ref.
        baseline_path.write_text(
            serialize_baseline(
                Baseline(
                    floor_percent=80.0,
                    measured_percent=80.5,
                    epsilon=0.5,
                    packages=SCOPED_PACKAGES,
                    measured_command="self-test",
                    notes="anti-lower",
                )
            ),
            encoding="utf-8",
        )

        def fake_git_show_ok(ref: str, path: str, *, repo: Path):
            payload = json.dumps({"floor_percent": 82.08})
            return payload, 0

        def fake_git_show_missing(ref: str, path: str, *, repo: Path):
            return "", 128

        if (
            assert_floor_not_lowered_vs_ref(
                baseline_path,
                git_show=fake_git_show_ok,
            )
            == 0
        ):
            raise AssertionError("floor below ref must fail anti-lowering")
        cases += 1

        baseline_path.write_text(
            serialize_baseline(
                Baseline(
                    floor_percent=83.0,
                    measured_percent=83.5,
                    epsilon=0.5,
                    packages=SCOPED_PACKAGES,
                    measured_command="self-test",
                    notes="anti-lower-raise",
                )
            ),
            encoding="utf-8",
        )
        if (
            assert_floor_not_lowered_vs_ref(
                baseline_path,
                git_show=fake_git_show_ok,
            )
            != 0
        ):
            raise AssertionError("raised floor vs ref must pass")
        cases += 1

        if (
            assert_floor_not_lowered_vs_ref(
                baseline_path,
                git_show=fake_git_show_missing,
            )
            != 0
        ):
            raise AssertionError("missing ref must skip anti-lowering")
        cases += 1

        baseline_path.write_text(
            serialize_baseline(
                Baseline(
                    floor_percent=10.0,
                    measured_percent=10.5,
                    epsilon=0.5,
                    packages=SCOPED_PACKAGES,
                    measured_command="self-test",
                    notes="anti-lower-override",
                )
            ),
            encoding="utf-8",
        )
        if (
            assert_floor_not_lowered_vs_ref(
                baseline_path,
                git_show=fake_git_show_ok,
                env={ALLOW_LOWER_VS_MAIN_ENV: "1"},
            )
            != 0
        ):
            raise AssertionError("override env must allow intentional lower")
        cases += 1

        bad = root / "bad.json"
        bad.write_text(json.dumps({"version": 99, "floor_percent": 1}), encoding="utf-8")
        try:
            load_baseline(bad)
        except BaselineError:
            cases += 1
        else:
            raise AssertionError("bad version accepted")

    print(f"Coverage floor self-tests passed ({cases} cases).")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI options."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
        help="Path to coverage.py JSON report (default: coverage.json).",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help="Path to the coverage-floor baseline JSON.",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help=(
            "Rewrite the floor from --report as measured_percent - epsilon. "
            "Refuses to lower the floor unless --allow-lower is set."
        ),
    )
    parser.add_argument(
        "--allow-lower",
        action="store_true",
        help="Permit --write-baseline to lower the existing floor after review.",
    )
    parser.add_argument(
        "--epsilon",
        type=float,
        default=DEFAULT_EPSILON,
        help=f"Points to subtract from measured coverage (default {DEFAULT_EPSILON}).",
    )
    parser.add_argument(
        "--measured-command",
        default="",
        help="Optional command string recorded in the baseline for provenance.",
    )
    parser.add_argument(
        "--notes",
        default="",
        help="Optional notes recorded in the baseline.",
    )
    parser.add_argument(
        "--assert-floor-not-lowered",
        action="store_true",
        help=(
            f"Compare working-tree floor_percent against {DEFAULT_MAIN_REF} "
            "and fail if lower (skip with notice when the ref is missing)."
        ),
    )
    parser.add_argument(
        "--main-ref",
        default=DEFAULT_MAIN_REF,
        help=f"Git ref used by --assert-floor-not-lowered (default {DEFAULT_MAIN_REF}).",
    )
    parser.add_argument(
        "--assert-cov-flags",
        action="store_true",
        help=(
            "Assert that --cov package values match baseline.packages exactly. "
            "Pass packages via one or more --cov arguments."
        ),
    )
    parser.add_argument(
        "--cov",
        action="append",
        default=[],
        dest="cov_packages",
        help="Package name passed to pytest --cov= (repeatable; used with --assert-cov-flags).",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run isolated guard regression cases and exit.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the coverage-floor guard."""

    args = _parse_args(argv)
    if args.self_test:
        run_self_tests()
        return 0

    baseline_path = args.baseline.resolve()

    try:
        if args.assert_floor_not_lowered:
            return assert_floor_not_lowered_vs_ref(
                baseline_path,
                ref=args.main_ref,
            )
        if args.assert_cov_flags:
            if not args.cov_packages:
                print(
                    "[coverage-floor] ERROR: --assert-cov-flags requires one or "
                    "more --cov package arguments",
                    file=sys.stderr,
                )
                return 1
            return run_assert_cov_flags(baseline_path, args.cov_packages)
        if args.write_baseline:
            return write_baseline_from_report(
                args.report.resolve(),
                baseline_path,
                epsilon=args.epsilon,
                allow_lower=args.allow_lower,
                measured_command=args.measured_command,
                notes=args.notes,
            )
        return run_check(args.report.resolve(), baseline_path)
    except (BaselineError, ReportError, ValueError) as exc:
        print(f"[coverage-floor] ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
