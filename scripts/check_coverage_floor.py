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
"""

from __future__ import annotations

import argparse
import json
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
SCOPED_PACKAGES = ("src", "api", "data_provider", "bot")


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
                "review; raise it only after a clean offline measurement."
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

    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReportError(f"coverage report not found: {report_path}") from exc
    except json.JSONDecodeError as exc:
        raise ReportError(f"coverage report is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ReportError("coverage report root must be an object")
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
    """Compare the coverage report against the checked-in floor."""

    baseline = load_baseline(baseline_path)
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
        f"(report={report_path})"
    )
    return 0


def run_self_tests() -> None:
    """Exercise floor derivation, parsing, and ratchet direction."""

    cases = 0
    with tempfile.TemporaryDirectory(prefix="coverage-floor-") as tmp:
        root = Path(tmp)
        report = root / "coverage.json"
        baseline_path = root / "coverage_floor_baseline.json"

        report.write_text(
            json.dumps(
                {
                    "meta": {"version": "7.0.0"},
                    "files": {},
                    "totals": {
                        "covered_lines": 430,
                        "num_statements": 1000,
                        "percent_covered": 43.0,
                        "missing_lines": 570,
                        "excluded_lines": 0,
                    },
                }
            ),
            encoding="utf-8",
        )
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
        report.write_text(
            json.dumps(
                {
                    "totals": {
                        "percent_covered": 50.0,
                        "covered_lines": 500,
                        "num_statements": 1000,
                        "missing_lines": 500,
                        "excluded_lines": 0,
                    }
                }
            ),
            encoding="utf-8",
        )
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
        report.write_text(
            json.dumps({"totals": {"percent_covered": 40.0}}),
            encoding="utf-8",
        )
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

        # Check path.
        report.write_text(
            json.dumps({"totals": {"percent_covered": 39.5}}),
            encoding="utf-8",
        )
        if run_check(report, baseline_path) != 0:
            raise AssertionError("equal floor should pass check")
        cases += 1
        report.write_text(
            json.dumps({"totals": {"percent_covered": 39.4}}),
            encoding="utf-8",
        )
        if run_check(report, baseline_path) == 0:
            raise AssertionError("below floor should fail check")
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

    report_path = args.report.resolve()
    baseline_path = args.baseline.resolve()

    try:
        if args.write_baseline:
            return write_baseline_from_report(
                report_path,
                baseline_path,
                epsilon=args.epsilon,
                allow_lower=args.allow_lower,
                measured_command=args.measured_command,
                notes=args.notes,
            )
        return run_check(report_path, baseline_path)
    except (BaselineError, ReportError, ValueError) as exc:
        print(f"[coverage-floor] ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
