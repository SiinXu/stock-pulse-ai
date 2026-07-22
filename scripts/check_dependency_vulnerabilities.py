#!/usr/bin/env python3
"""Audit the universal Python lock with bounded advisory exceptions."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

try:
    from packaging.utils import canonicalize_name
except ModuleNotFoundError:
    from pip._vendor.packaging.utils import canonicalize_name

from check_dependency_locks import ROOT, _pin_violation, _read_requirement_file


DEFAULT_LOCK = ROOT / "constraints.txt"
DEFAULT_EXCEPTIONS = ROOT / "scripts" / "dependency_vulnerability_exceptions.json"
MAX_EXCEPTION_DAYS = 30


@dataclass(frozen=True)
class VulnerabilityException:
    """One exact, time-bounded package advisory exception."""

    package: str
    advisory: str
    expires: date
    owner: str
    reason: str

    @property
    def key(self) -> tuple[str, str]:
        """Return the canonical package and advisory lookup key."""
        return (self.package, self.advisory)


def _load_exceptions(
    path: Path,
    today: date,
) -> tuple[dict[tuple[str, str], VulnerabilityException], list[str]]:
    """Load advisory exceptions and reject invalid or overlong entries."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"{path}: cannot load vulnerability exceptions: {exc}"]
    if not isinstance(raw, dict) or set(raw) != {"exceptions"} or not isinstance(raw["exceptions"], list):
        return {}, [f"{path}: expected one 'exceptions' array"]

    errors: list[str] = []
    exceptions: dict[tuple[str, str], VulnerabilityException] = {}
    required = {"package", "advisory", "expires", "owner", "reason"}
    for index, item in enumerate(raw["exceptions"]):
        label = f"{path}: exceptions[{index}]"
        if not isinstance(item, dict) or set(item) != required:
            errors.append(f"{label}: expected exactly {sorted(required)}")
            continue
        if not all(isinstance(item[field], str) and item[field].strip() for field in required):
            errors.append(f"{label}: every field must be a non-empty string")
            continue
        try:
            expiry = date.fromisoformat(item["expires"])
        except ValueError:
            errors.append(f"{label}: expires must use YYYY-MM-DD")
            continue
        exception = VulnerabilityException(
            package=canonicalize_name(item["package"]),
            advisory=item["advisory"].strip(),
            expires=expiry,
            owner=item["owner"].strip(),
            reason=item["reason"].strip(),
        )
        if expiry < today:
            errors.append(f"{label}: exception expired on {expiry.isoformat()}")
        elif expiry > today + timedelta(days=MAX_EXCEPTION_DAYS):
            errors.append(f"{label}: exception exceeds the {MAX_EXCEPTION_DAYS}-day maximum")
        elif exception.key in exceptions:
            errors.append(f"{label}: duplicate exception for {exception.key}")
        else:
            exceptions[exception.key] = exception
    return exceptions, errors


def _audit_plan(lock_path: Path) -> tuple[list[list[str]], set[str]]:
    """Build collision-free registry audit batches and immutable VCS skips."""
    parsed = _read_requirement_file(lock_path)
    if parsed.errors:
        raise RuntimeError("\n".join(parsed.errors))

    versions_by_package: dict[str, list[str]] = {}
    vcs_packages: set[str] = set()
    for item in parsed.requirements:
        violation = _pin_violation(item.requirement)
        if violation is not None:
            raise RuntimeError(f"{item.path}:{item.line_number}: {item.name} has {violation}")
        if item.requirement.url is not None:
            vcs_packages.add(item.name)
            continue
        specifier = next(iter(item.requirement.specifier))
        versions = versions_by_package.setdefault(item.name, [])
        if specifier.version not in versions:
            versions.append(specifier.version)

    batch_count = max((len(versions) for versions in versions_by_package.values()), default=0)
    batches: list[list[str]] = [[] for _ in range(batch_count)]
    for package in sorted(versions_by_package):
        for index, version in enumerate(versions_by_package[package]):
            batches[index].append(f"{package}=={version}")
    return batches, vcs_packages


def _evaluate_audit(
    payload: dict,
    exceptions: dict[tuple[str, str], VulnerabilityException],
    allowed_skips: set[str],
) -> tuple[list[str], int, int]:
    """Evaluate pip-audit JSON against skips and bounded exceptions."""
    dependencies = payload.get("dependencies")
    if not isinstance(dependencies, list):
        return ["pip-audit JSON is missing its dependencies array"], 0, 0

    errors: list[str] = []
    used_exceptions: set[tuple[str, str]] = set()
    skipped = 0
    audited = 0
    for dependency in dependencies:
        if not isinstance(dependency, dict) or not isinstance(dependency.get("name"), str):
            errors.append("pip-audit returned an invalid dependency record")
            continue
        package = canonicalize_name(dependency["name"])
        skip_reason = dependency.get("skip_reason")
        if skip_reason:
            if package in allowed_skips:
                skipped += 1
            else:
                errors.append(f"{package}: unexpected audit skip: {skip_reason}")
            continue
        audited += 1
        vulnerabilities = dependency.get("vulns", [])
        if not isinstance(vulnerabilities, list):
            errors.append(f"{package}: invalid vulnerability list")
            continue
        for vulnerability in vulnerabilities:
            advisory = vulnerability.get("id") if isinstance(vulnerability, dict) else None
            if not isinstance(advisory, str) or not advisory:
                errors.append(f"{package}: vulnerability record is missing an ID")
                continue
            key = (package, advisory)
            if key in exceptions:
                used_exceptions.add(key)
            else:
                fixes = vulnerability.get("fix_versions", [])
                errors.append(f"{package} {dependency.get('version')}: {advisory}; fixes={fixes}")

    for unused in sorted(set(exceptions) - used_exceptions):
        errors.append(f"unused vulnerability exception for {unused}")
    return errors, audited, skipped


def _run_audit(lock_path: Path) -> tuple[dict, set[str]]:
    """Run pip-audit against every exact registry version in the universal lock."""
    batches, vcs_packages = _audit_plan(lock_path)
    dependencies: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="stockpulse-vulnerability-audit-") as directory:
        for index, batch in enumerate(batches, start=1):
            requirement_path = Path(directory) / f"requirements-{index}.txt"
            requirement_path.write_text("\n".join(batch) + "\n", encoding="utf-8")
            command = [
                sys.executable,
                "-m",
                "pip_audit",
                "--disable-pip",
                "--no-deps",
                "--requirement",
                str(requirement_path),
                "--format",
                "json",
                "--progress-spinner",
                "off",
            ]
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if completed.returncode not in {0, 1}:
                detail = completed.stderr.strip() or completed.stdout.strip() or "no diagnostic output"
                raise RuntimeError(
                    f"pip-audit batch {index} failed with exit code {completed.returncode}: {detail}"
                )
            try:
                payload = json.loads(completed.stdout)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"pip-audit batch {index} returned invalid JSON: {exc}") from exc
            batch_dependencies = payload.get("dependencies")
            if not isinstance(batch_dependencies, list):
                raise RuntimeError(f"pip-audit batch {index} JSON is missing its dependencies array")
            expected = {
                (canonicalize_name(requirement.split("==", 1)[0]), requirement.split("==", 1)[1])
                for requirement in batch
            }
            actual = {
                (canonicalize_name(item.get("name", "")), str(item.get("version", "")))
                for item in batch_dependencies
                if isinstance(item, dict)
            }
            if actual != expected:
                raise RuntimeError(
                    f"pip-audit batch {index} coverage differs: expected {sorted(expected)}, got {sorted(actual)}"
                )
            dependencies.extend(batch_dependencies)

    dependencies.extend(
        {
            "name": package,
            "version": None,
            "vulns": [],
            "skip_reason": "immutable VCS source is outside the registry advisory database",
        }
        for package in sorted(vcs_packages)
    )
    return {"dependencies": dependencies}, vcs_packages


def check_repository(
    lock_path: Path = DEFAULT_LOCK,
    exception_path: Path = DEFAULT_EXCEPTIONS,
    *,
    today: Optional[date] = None,
) -> tuple[list[str], int, int]:
    """Audit the repository lock and return errors and coverage counts."""
    current_date = today or datetime.now(timezone.utc).date()
    exceptions, errors = _load_exceptions(exception_path, current_date)
    if errors:
        return errors, 0, 0
    try:
        payload, allowed_skips = _run_audit(lock_path)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        return [str(exc)], 0, 0
    audit_errors, audited, skipped = _evaluate_audit(payload, exceptions, allowed_skips)
    return audit_errors, audited, skipped


def _write_exceptions(path: Path, exceptions: list[dict]) -> None:
    """Write one self-test exception registry."""
    path.write_text(json.dumps({"exceptions": exceptions}) + "\n", encoding="utf-8")


def _run_self_tests() -> None:
    """Exercise advisory, skip, expiry, maximum-window, and usage behavior."""
    today = date(2030, 1, 1)
    clean = {"dependencies": [{"name": "foo", "version": "1", "vulns": []}]}
    vulnerable = {
        "dependencies": [
            {
                "name": "foo",
                "version": "1",
                "vulns": [{"id": "GHSA-test-0001", "fix_versions": ["2"]}],
            }
        ]
    }
    cases = 0

    with tempfile.TemporaryDirectory() as temporary_directory:
        path = Path(temporary_directory) / "exceptions.json"
        _write_exceptions(path, [])
        exceptions, errors = _load_exceptions(path, today)
        assert not errors
        audit_errors, _, _ = _evaluate_audit(clean, exceptions, set())
        assert not audit_errors
        cases += 1

        audit_errors, _, _ = _evaluate_audit(vulnerable, exceptions, set())
        assert any("GHSA-test-0001" in error for error in audit_errors)
        cases += 1

        active = {
            "package": "foo",
            "advisory": "GHSA-test-0001",
            "expires": "2030-01-15",
            "owner": "security-maintainers",
            "reason": "Tracked remediation and compensating control.",
        }
        _write_exceptions(path, [active])
        exceptions, errors = _load_exceptions(path, today)
        assert not errors
        audit_errors, _, _ = _evaluate_audit(vulnerable, exceptions, set())
        assert not audit_errors
        cases += 1

        expired = dict(active, expires="2029-12-31")
        _write_exceptions(path, [expired])
        _, errors = _load_exceptions(path, today)
        assert any("expired" in error for error in errors)
        cases += 1

        overlong = dict(active, expires="2030-02-15")
        _write_exceptions(path, [overlong])
        _, errors = _load_exceptions(path, today)
        assert any("30-day maximum" in error for error in errors)
        cases += 1

        _write_exceptions(path, [active])
        exceptions, errors = _load_exceptions(path, today)
        assert not errors
        audit_errors, _, _ = _evaluate_audit(clean, exceptions, set())
        assert any("unused" in error for error in audit_errors)
        cases += 1

        skipped = {"dependencies": [{"name": "source-package", "skip_reason": "not on PyPI"}]}
        audit_errors, _, count = _evaluate_audit(skipped, {}, {"source-package"})
        assert not audit_errors and count == 1
        cases += 1
        audit_errors, _, _ = _evaluate_audit(skipped, {}, set())
        assert any("unexpected audit skip" in error for error in audit_errors)
        cases += 1

        lock_path = Path(temporary_directory) / "constraints.txt"
        lock_path.write_text(
            "bar==3\n"
            "foo==1 ; python_version < '3.12'\n"
            "foo==2 ; python_version >= '3.12'\n"
            "source-package @ git+https://example.com/source.git@"
            "0123456789abcdef0123456789abcdef01234567\n",
            encoding="utf-8",
        )
        batches, vcs_packages = _audit_plan(lock_path)
        assert batches == [["bar==3", "foo==1"], ["foo==2"]]
        assert vcs_packages == {"source-package"}
        cases += 1

    print(f"Dependency vulnerability self-tests passed ({cases} cases).")


def main() -> int:
    """Run vulnerability self-tests or audit the universal lock."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="run isolated audit-policy tests")
    args = parser.parse_args()
    if args.self_test:
        _run_self_tests()
        return 0

    errors, audited, skipped = check_repository()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(
        f"Dependency vulnerability audit passed for {audited} registry entries; "
        f"{skipped} immutable VCS entries were outside the advisory database."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
