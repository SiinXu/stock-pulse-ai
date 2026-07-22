#!/usr/bin/env python3
"""Validate and regenerate the repository-wide Python dependency lock."""

from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
import re
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

try:
    from packaging.markers import default_environment
    from packaging.requirements import InvalidRequirement, Requirement
    from packaging.utils import canonicalize_name
except ModuleNotFoundError:  # pip always carries the same parser for bootstrap use.
    from pip._vendor.packaging.markers import default_environment
    from pip._vendor.packaging.requirements import InvalidRequirement, Requirement
    from pip._vendor.packaging.utils import canonicalize_name


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "scripts" / "dependency_lock_policy.json"
DEFAULT_EXCEPTIONS = ROOT / "scripts" / "dependency_lock_exceptions.json"
MAX_EXCEPTION_DAYS = 30
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
IMMUTABLE_GIT_RE = re.compile(r"^git\+https://[^@\s]+@[0-9a-f]{40}(?:#\S*)?$")
HEADER_TITLE = "# StockPulse universal Python dependency constraints"
ALLOWED_EXCEPTION_KINDS = {"mutable-source", "unpinned-version"}
RUNTIME_EXCEPTION_KIND = "unconstrained-install"
CUTOFF_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
RUNTIME_SOURCE_ROOTS = ("src", "api", "bot")


@dataclass(frozen=True)
class ParsedRequirement:
    """One parsed requirement with its source location."""

    path: Path
    line_number: int
    text: str
    requirement: Requirement

    @property
    def name(self) -> str:
        """Return the canonical distribution name."""
        return canonicalize_name(self.requirement.name)


@dataclass(frozen=True)
class RequirementFile:
    """Parsed directives, requirements, and errors for one input file."""

    constraints: tuple[Path, ...]
    includes: tuple[Path, ...]
    requirements: tuple[ParsedRequirement, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class DependencyException:
    """One bounded dependency-policy exception."""

    kind: str
    package: str
    expires: date
    owner: str
    reason: str
    path: str = ""

    @property
    def key(self) -> tuple[str, str, str]:
        """Return the exact exception lookup key."""
        return (self.kind, self.package, self.path)


def _safe_path(root: Path, relative_path: str) -> Path:
    """Resolve a repository-relative path without allowing traversal."""
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"path escapes repository root: {relative_path}") from exc
    return candidate


def _content_sha256(content: bytes) -> str:
    """Return a lowercase SHA-256 digest for bytes."""
    return hashlib.sha256(content).hexdigest()


def _source_sha256(root: Path, source_files: Iterable[str]) -> str:
    """Hash ordered dependency source paths and their contents."""
    digest = hashlib.sha256()
    for relative_path in source_files:
        path = _safe_path(root, relative_path)
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _strip_requirement_comment(line: str) -> str:
    """Remove a supported trailing requirement comment."""
    if line.lstrip().startswith("#"):
        return ""
    return re.sub(r"\s+#.*$", "", line).strip()


def _parse_requirement(text: str) -> Requirement:
    """Parse PEP 508 or legacy VCS-with-egg requirement text."""
    candidate = text
    if text.startswith("git+") and "#egg=" in text:
        egg = text.rsplit("#egg=", 1)[1].split("&", 1)[0]
        candidate = f"{egg} @ {text}"
    return Requirement(candidate)


def _directive(parts: list[str], short: str, long: str) -> Optional[str]:
    """Extract a one-argument requirement-file directive."""
    if not parts:
        return None
    if parts[0] in {short, long} and len(parts) == 2:
        return parts[1]
    if parts[0].startswith(short) and parts[0] != short and len(parts) == 1:
        return parts[0][len(short) :]
    return None


def _read_requirement_file(path: Path) -> RequirementFile:
    """Parse one requirements or constraints file conservatively."""
    constraints: list[Path] = []
    includes: list[Path] = []
    requirements: list[ParsedRequirement] = []
    errors: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return RequirementFile((), (), (), (f"{path}: cannot read requirements file: {exc}",))

    for line_number, raw_line in enumerate(lines, start=1):
        text = _strip_requirement_comment(raw_line)
        if not text:
            continue
        if text.endswith("\\"):
            errors.append(f"{path}:{line_number}: line continuations are not supported by the lock guard")
            continue
        if text.startswith("-"):
            try:
                parts = shlex.split(text)
            except ValueError as exc:
                errors.append(f"{path}:{line_number}: invalid directive: {exc}")
                continue
            constraint = _directive(parts, "-c", "--constraint")
            include = _directive(parts, "-r", "--requirement")
            if constraint is not None:
                constraints.append((path.parent / constraint).resolve())
            elif include is not None:
                includes.append((path.parent / include).resolve())
            else:
                errors.append(f"{path}:{line_number}: unsupported requirements directive '{text}'")
            continue
        try:
            requirement = _parse_requirement(text)
        except InvalidRequirement as exc:
            errors.append(f"{path}:{line_number}: invalid requirement '{text}': {exc}")
            continue
        requirements.append(ParsedRequirement(path, line_number, text, requirement))

    return RequirementFile(tuple(constraints), tuple(includes), tuple(requirements), tuple(errors))


def _collect_resolution_requirements(
    root: Path,
    source_files: Iterable[str],
    lock_path: Path,
) -> tuple[list[ParsedRequirement], list[str]]:
    """Collect unique transitive requirement-file inputs for resolution."""
    requirements: list[ParsedRequirement] = []
    errors: list[str] = []
    visited: set[Path] = set()

    def visit(path: Path) -> None:
        """Visit one requirement file and its nested includes once."""
        resolved = path.resolve()
        if resolved in visited:
            return
        visited.add(resolved)
        parsed = _read_requirement_file(resolved)
        errors.extend(parsed.errors)
        for constraint in parsed.constraints:
            if constraint != lock_path.resolve():
                errors.append(f"{resolved}: unexpected constraint file {constraint}")
        requirements.extend(parsed.requirements)
        for include in parsed.includes:
            visit(include)

    for relative_path in source_files:
        try:
            visit(_safe_path(root, relative_path))
        except ValueError as exc:
            errors.append(str(exc))
    return requirements, errors


def _load_policy(path: Path) -> tuple[dict, list[str]]:
    """Load and structurally validate the dependency policy."""
    errors: list[str] = []
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"{path}: cannot load dependency lock policy: {exc}"]

    expected_keys = {
        "schema_version",
        "lock_file",
        "build_constraint_file",
        "resolver",
        "source_files",
        "exact_source_files",
        "install_contracts",
        "runtime_install_contracts",
        "lock_sha256",
    }
    if not isinstance(policy, dict) or set(policy) != expected_keys:
        return {}, [f"{path}: expected exactly {sorted(expected_keys)}"]
    if policy["schema_version"] != 2:
        errors.append(f"{path}: schema_version must be 2")
    if not isinstance(policy["lock_file"], str) or not policy["lock_file"]:
        errors.append(f"{path}: lock_file must be a non-empty string")
    if not isinstance(policy["build_constraint_file"], str) or not policy["build_constraint_file"]:
        errors.append(f"{path}: build_constraint_file must be a non-empty string")
    resolver = policy.get("resolver")
    resolver_keys = {
        "name",
        "version",
        "python_version",
        "python_versions",
        "exclude_newer",
        "universal",
    }
    if not isinstance(resolver, dict) or set(resolver) != resolver_keys:
        errors.append(f"{path}: resolver must contain exactly {sorted(resolver_keys)}")
    else:
        if resolver["name"] != "uv":
            errors.append(f"{path}: resolver.name must be 'uv'")
        for field in ("version", "python_version", "exclude_newer"):
            if not isinstance(resolver[field], str) or not resolver[field]:
                errors.append(f"{path}: resolver.{field} must be a non-empty string")
        python_versions = resolver.get("python_versions")
        if (
            not isinstance(python_versions, list)
            or not python_versions
            or not all(isinstance(item, str) and re.fullmatch(r"3\.\d+", item) for item in python_versions)
            or len(set(python_versions)) != len(python_versions)
        ):
            errors.append(f"{path}: resolver.python_versions must be a unique Python 3.x string array")
        elif python_versions[0] != resolver["python_version"]:
            errors.append(f"{path}: resolver.python_versions must start with resolver.python_version")
        if resolver["universal"] is not True:
            errors.append(f"{path}: resolver.universal must be true")
    for field in ("source_files", "exact_source_files"):
        value = policy.get(field)
        if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
            errors.append(f"{path}: {field} must be a non-empty string array")
    if not isinstance(policy.get("install_contracts"), dict) or not policy["install_contracts"]:
        errors.append(f"{path}: install_contracts must be a non-empty mapping")
    if not isinstance(policy.get("runtime_install_contracts"), dict):
        errors.append(f"{path}: runtime_install_contracts must be a mapping")
    lock_sha = policy.get("lock_sha256")
    if lock_sha != "" and (not isinstance(lock_sha, str) or not SHA256_RE.fullmatch(lock_sha)):
        errors.append(f"{path}: lock_sha256 must be empty or a lowercase SHA-256 digest")
    return policy, errors


def _load_exceptions(
    path: Path,
    today: date,
) -> tuple[dict[tuple[str, str, str], DependencyException], list[str]]:
    """Load exact dependency exceptions and enforce their time bounds."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"{path}: cannot load dependency exception registry: {exc}"]
    if not isinstance(raw, dict) or set(raw) != {"exceptions"} or not isinstance(raw["exceptions"], list):
        return {}, [f"{path}: expected one 'exceptions' array"]

    errors: list[str] = []
    exceptions: dict[tuple[str, str, str], DependencyException] = {}
    common_fields = {"kind", "package", "expires", "owner", "reason"}
    for index, item in enumerate(raw["exceptions"]):
        label = f"{path}: exceptions[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label}: exception must be an object")
            continue
        expected_fields = common_fields | ({"path"} if item.get("kind") == RUNTIME_EXCEPTION_KIND else set())
        if set(item) != expected_fields:
            errors.append(f"{label}: expected exactly {sorted(expected_fields)}")
            continue
        if not all(isinstance(item[field], str) and item[field].strip() for field in expected_fields):
            errors.append(f"{label}: every field must be a non-empty string")
            continue
        if item["kind"] not in ALLOWED_EXCEPTION_KINDS | {RUNTIME_EXCEPTION_KIND}:
            errors.append(f"{label}: unsupported exception kind '{item['kind']}'")
            continue
        exception_path = item.get("path", "")
        if exception_path and (
            Path(exception_path).is_absolute()
            or ".." in Path(exception_path).parts
            or not exception_path.endswith(".py")
        ):
            errors.append(f"{label}: path must be a repository-relative Python file")
            continue
        try:
            expiry = date.fromisoformat(item["expires"])
        except ValueError:
            errors.append(f"{label}: expires must use YYYY-MM-DD")
            continue
        exception = DependencyException(
            kind=item["kind"],
            package=canonicalize_name(item["package"]),
            expires=expiry,
            owner=item["owner"],
            reason=item["reason"],
            path=exception_path,
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


def _pin_violation(requirement: Requirement) -> Optional[str]:
    """Return the pin-policy violation for one resolved requirement."""
    if requirement.url is not None:
        if not IMMUTABLE_GIT_RE.fullmatch(requirement.url):
            return "mutable-source"
        return None
    specifiers = list(requirement.specifier)
    if len(specifiers) != 1 or specifiers[0].operator != "==" or "*" in specifiers[0].version:
        return "unpinned-version"
    return None


def _render_header(policy: dict, source_sha: str) -> str:
    """Render deterministic metadata for the generated universal lock."""
    resolver = policy["resolver"]
    return "\n".join(
        (
            HEADER_TITLE,
            "# Generated file; do not edit by hand.",
            f"# Resolver: uv=={resolver['version']}",
            f"# Source-SHA256: {source_sha}",
            f"# Python-Minimum: {resolver['python_version']}",
            f"# Exclude-Newer: {resolver['exclude_newer']}",
            "# Platforms: universal (Linux, macOS, Windows)",
            "# Regenerate: python scripts/check_dependency_locks.py --update",
            "",
        )
    )


def _header_value(lock_text: str, label: str) -> Optional[str]:
    """Read one metadata value from the generated lock header."""
    prefix = f"# {label}: "
    for line in lock_text.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return None


def _check_install_contracts(root: Path, policy: dict, lock_path: Path) -> list[str]:
    """Validate the reviewed contents of each install input."""
    errors: list[str] = []
    for relative_path, contract in policy["install_contracts"].items():
        label = f"install contract {relative_path}"
        required_keys = {"constraint", "includes", "packages", "allow_other_packages"}
        if not isinstance(contract, dict) or set(contract) != required_keys:
            errors.append(f"{label}: expected exactly {sorted(required_keys)}")
            continue
        try:
            path = _safe_path(root, relative_path)
            expected_constraint = _safe_path(root, contract["constraint"])
            expected_includes = {_safe_path(root, item) for item in contract["includes"]}
        except (TypeError, ValueError) as exc:
            errors.append(f"{label}: {exc}")
            continue
        parsed = _read_requirement_file(path)
        errors.extend(parsed.errors)
        actual_constraints = set(parsed.constraints)
        if actual_constraints != {expected_constraint} or expected_constraint != lock_path.resolve():
            errors.append(f"{label}: must reference only {lock_path.relative_to(root)} as its constraint")
        if set(parsed.includes) != expected_includes:
            errors.append(f"{label}: requirement includes do not match the reviewed contract")
        expected_packages = {canonicalize_name(item) for item in contract["packages"]}
        actual_packages = {item.name for item in parsed.requirements}
        if contract["allow_other_packages"] is True:
            missing = expected_packages - actual_packages
            if missing:
                errors.append(f"{label}: missing required packages {sorted(missing)}")
        elif contract["allow_other_packages"] is False:
            if actual_packages != expected_packages:
                errors.append(
                    f"{label}: packages differ (expected {sorted(expected_packages)}, got {sorted(actual_packages)})"
                )
        else:
            errors.append(f"{label}: allow_other_packages must be boolean")
    return errors


def _runtime_pip_install_calls(root: Path) -> dict[str, list[tuple[int, tuple[Optional[str], ...]]]]:
    """Find literal application-runtime subprocess calls to `pip install`."""
    calls: dict[str, list[tuple[int, tuple[Optional[str], ...]]]] = {}
    candidates: list[Path] = []
    for relative_root in RUNTIME_SOURCE_ROOTS:
        source_root = root / relative_root
        if source_root.is_dir():
            candidates.extend(source_root.rglob("*.py"))
    candidates.extend(path for path in (root / "main.py", root / "server.py") if path.is_file())

    for path in sorted(candidates):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError):
            continue
        relative_path = path.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if (
                not isinstance(node.func.value, ast.Name)
                or node.func.value.id != "subprocess"
                or node.func.attr not in {"call", "check_call", "check_output", "Popen", "run"}
                or not node.args
                or not isinstance(node.args[0], (ast.List, ast.Tuple))
            ):
                continue
            arguments = tuple(
                item.value if isinstance(item, ast.Constant) and isinstance(item.value, str) else None
                for item in node.args[0].elts
            )
            if "pip" in arguments and "install" in arguments:
                calls.setdefault(relative_path, []).append((node.lineno, arguments))
    return calls


def _check_runtime_install_contracts(
    root: Path,
    policy: dict,
    exceptions: dict[tuple[str, str, str], DependencyException],
) -> tuple[list[str], set[tuple[str, str, str]]]:
    """Require runtime pip installs to preserve the resolved environment."""
    errors: list[str] = []
    used_exceptions: set[tuple[str, str, str]] = set()
    contracts = policy["runtime_install_contracts"]
    calls = _runtime_pip_install_calls(root)
    unknown_paths = sorted(set(calls) - set(contracts))
    for relative_path in unknown_paths:
        errors.append(f"runtime install {relative_path}: missing reviewed install contract")

    for relative_path, contract in contracts.items():
        label = f"runtime install contract {relative_path}"
        if not isinstance(contract, dict) or set(contract) != {"package", "required_flags"}:
            errors.append(f"{label}: expected package and required_flags")
            continue
        package = contract.get("package")
        required_flags = contract.get("required_flags")
        if not isinstance(package, str) or not package.strip():
            errors.append(f"{label}: package must be a non-empty string")
            continue
        if (
            not isinstance(required_flags, list)
            or not required_flags
            or not all(isinstance(flag, str) and flag.startswith("--") for flag in required_flags)
        ):
            errors.append(f"{label}: required_flags must be a non-empty option array")
            continue
        path_calls = calls.get(relative_path, [])
        if not path_calls:
            errors.append(f"{label}: reviewed pip install call was not found")
            continue
        for line_number, arguments in path_calls:
            missing_flags = sorted(set(required_flags) - set(arguments))
            if not missing_flags:
                continue
            key = (RUNTIME_EXCEPTION_KIND, canonicalize_name(package), relative_path)
            if key in exceptions:
                used_exceptions.add(key)
            else:
                errors.append(
                    f"{relative_path}:{line_number}: runtime pip install is missing {missing_flags}"
                )
    return errors, used_exceptions


def _check_marker_matrix(
    requirements: Iterable[ParsedRequirement],
    python_versions: Iterable[str],
) -> list[str]:
    """Reject overlapping lock entries across every supported environment."""
    errors: list[str] = []
    grouped: dict[str, list[ParsedRequirement]] = {}
    for item in requirements:
        grouped.setdefault(item.name, []).append(item)

    platforms = (
        ("linux-x86_64", "linux", "Linux", "posix", "x86_64"),
        ("linux-aarch64", "linux", "Linux", "posix", "aarch64"),
        ("macos-x86_64", "darwin", "Darwin", "posix", "x86_64"),
        ("macos-arm64", "darwin", "Darwin", "posix", "arm64"),
        ("windows-amd64", "win32", "Windows", "nt", "AMD64"),
    )
    for python_version in python_versions:
        for platform_name, sys_platform, platform_system, os_name, machine in platforms:
            environment = default_environment()
            environment.update(
                {
                    "python_version": python_version,
                    "python_full_version": f"{python_version}.0",
                    "sys_platform": sys_platform,
                    "platform_system": platform_system,
                    "os_name": os_name,
                    "platform_machine": machine,
                    "implementation_name": "cpython",
                    "platform_python_implementation": "CPython",
                    "extra": "",
                }
            )
            for package, candidates in grouped.items():
                active = [
                    item
                    for item in candidates
                    if item.requirement.marker is None or item.requirement.marker.evaluate(environment)
                ]
                if len(active) > 1:
                    locations = [f"{item.path.name}:{item.line_number}" for item in active]
                    errors.append(
                        f"{package}: overlapping lock entries for Python {python_version} {platform_name}: {locations}"
                    )
    return errors


def check_repository(
    root: Path = ROOT,
    policy_path: Path = DEFAULT_POLICY,
    exception_path: Path = DEFAULT_EXCEPTIONS,
    *,
    today: Optional[date] = None,
) -> list[str]:
    """Validate lock provenance, pins, matrix markers, and install contracts."""
    policy, errors = _load_policy(policy_path)
    if not policy:
        return errors
    try:
        lock_path = _safe_path(root, policy["lock_file"])
        build_constraint_path = _safe_path(root, policy["build_constraint_file"])
        source_sha = _source_sha256(root, policy["source_files"])
        lock_bytes = lock_path.read_bytes()
        build_constraint_path.read_bytes()
    except (OSError, TypeError, ValueError) as exc:
        errors.append(f"dependency lock inputs are unavailable: {exc}")
        return errors

    lock_text = lock_bytes.decode("utf-8")
    if not lock_text.startswith(HEADER_TITLE + "\n"):
        errors.append(f"{lock_path}: missing generated lock header")
    if _header_value(lock_text, "Resolver") != f"uv=={policy['resolver']['version']}":
        errors.append(f"{lock_path}: resolver header does not match policy")
    if _header_value(lock_text, "Source-SHA256") != source_sha:
        errors.append(f"{lock_path}: source digest drift; regenerate the dependency lock")
    if _header_value(lock_text, "Python-Minimum") != policy["resolver"]["python_version"]:
        errors.append(f"{lock_path}: Python minimum header does not match policy")
    if _header_value(lock_text, "Exclude-Newer") != policy["resolver"]["exclude_newer"]:
        errors.append(f"{lock_path}: resolution cutoff header does not match policy")
    actual_lock_sha = _content_sha256(lock_bytes)
    if policy["lock_sha256"] != actual_lock_sha:
        errors.append(f"{lock_path}: lock digest drift; use the reviewed update command")

    now = datetime.now(timezone.utc)
    current_date = today or now.date()
    cutoff = policy["resolver"]["exclude_newer"]
    if not CUTOFF_RE.fullmatch(cutoff):
        errors.append(f"{policy_path}: resolver.exclude_newer must be a fixed UTC timestamp")
    else:
        try:
            cutoff_time = datetime.strptime(cutoff, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            errors.append(f"{policy_path}: resolver.exclude_newer is not a valid timestamp")
        else:
            comparison_time = (
                datetime.combine(current_date, datetime.max.time(), tzinfo=timezone.utc)
                if today is not None
                else now
            )
            if cutoff_time > comparison_time:
                errors.append(f"{policy_path}: resolver.exclude_newer must not be in the future")
    exceptions, exception_errors = _load_exceptions(exception_path, current_date)
    errors.extend(exception_errors)
    used_exceptions: set[tuple[str, str, str]] = set()

    parsed_lock = _read_requirement_file(lock_path)
    errors.extend(parsed_lock.errors)
    if parsed_lock.constraints or parsed_lock.includes:
        errors.append(f"{lock_path}: generated constraints must not include other requirement files")
    seen_entries: set[tuple[str, str]] = set()
    for item in parsed_lock.requirements:
        marker = str(item.requirement.marker or "")
        key = (item.name, marker)
        if key in seen_entries:
            errors.append(f"{lock_path}:{item.line_number}: duplicate lock entry for {item.name} ({marker or 'all'})")
        seen_entries.add(key)
        violation = _pin_violation(item.requirement)
        if violation is not None:
            exception_key = (violation, item.name, "")
            if exception_key in exceptions:
                used_exceptions.add(exception_key)
            else:
                errors.append(f"{lock_path}:{item.line_number}: {item.name} has {violation}")

    source_requirements, source_errors = _collect_resolution_requirements(
        root, policy["source_files"], lock_path
    )
    errors.extend(source_errors)
    locked_names = {item.name for item in parsed_lock.requirements}
    missing = sorted({item.name for item in source_requirements} - locked_names)
    if missing:
        errors.append(f"{lock_path}: direct resolution inputs are missing from the lock: {missing}")
    for item in source_requirements:
        if item.requirement.url is None:
            continue
        violation = _pin_violation(item.requirement)
        if violation is None:
            continue
        exception_key = (violation, item.name, "")
        if exception_key in exceptions:
            used_exceptions.add(exception_key)
        else:
            errors.append(f"{item.path}:{item.line_number}: direct source has {violation} for {item.name}")

    for relative_path in policy["exact_source_files"]:
        try:
            exact_file = _safe_path(root, relative_path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        parsed = _read_requirement_file(exact_file)
        errors.extend(parsed.errors)
        for item in parsed.requirements:
            violation = _pin_violation(item.requirement)
            if violation is not None:
                errors.append(f"{exact_file}:{item.line_number}: optional closure has {violation} for {item.name}")

    errors.extend(
        _check_marker_matrix(
            parsed_lock.requirements,
            policy["resolver"]["python_versions"],
        )
    )
    errors.extend(_check_install_contracts(root, policy, lock_path))
    runtime_errors, runtime_exceptions = _check_runtime_install_contracts(
        root,
        policy,
        exceptions,
    )
    errors.extend(runtime_errors)
    used_exceptions.update(runtime_exceptions)
    for unused in sorted(set(exceptions) - used_exceptions):
        errors.append(f"{exception_path}: unused dependency exception for {unused}")
    return errors


def _generate_lock_content(root: Path, policy: dict, uv_binary: str) -> str:
    """Resolve and render the universal lock without modifying the repository."""
    lock_path = _safe_path(root, policy["lock_file"])
    requirements, source_errors = _collect_resolution_requirements(root, policy["source_files"], lock_path)
    if source_errors:
        raise RuntimeError("\n".join(source_errors))
    resolver = policy["resolver"]
    version = subprocess.run(
        [uv_binary, "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    if not re.fullmatch(rf"uv {re.escape(resolver['version'])}(?:\s+.*)?", version):
        raise RuntimeError(f"expected uv {resolver['version']}, got '{version}'")

    unique_lines = list(dict.fromkeys(item.text for item in requirements))
    with tempfile.TemporaryDirectory(prefix="stockpulse-dependency-lock-") as temporary_directory:
        temporary = Path(temporary_directory)
        source_path = temporary / "requirements-all.txt"
        raw_lock_path = temporary / "constraints.txt"
        source_path.write_text("\n".join(unique_lines) + "\n", encoding="utf-8")
        command = [
            uv_binary,
            "pip",
            "compile",
            "--universal",
            "--python-version",
            resolver["python_version"],
            "--exclude-newer",
            resolver["exclude_newer"],
            "--build-constraints",
            str(_safe_path(root, policy["build_constraint_file"])),
            "--quiet",
            "--no-header",
            "--no-annotate",
            str(source_path),
            "--output-file",
            str(raw_lock_path),
        ]
        subprocess.run(command, cwd=root, check=True)
        raw_lock = raw_lock_path.read_text(encoding="utf-8").strip() + "\n"

    source_sha = _source_sha256(root, policy["source_files"])
    return _render_header(policy, source_sha) + raw_lock


def _generated_lock_diff(current: str, generated: str) -> list[str]:
    """Return a bounded unified diff when resolver output differs."""
    if current == generated:
        return []
    return list(
        difflib.unified_diff(
            current.splitlines(),
            generated.splitlines(),
            fromfile="constraints.txt (reviewed)",
            tofile="constraints.txt (regenerated)",
            lineterm="",
            n=2,
        )
    )[:80]


def _verify_generated_lock(root: Path, policy_path: Path, uv_binary: str) -> None:
    """Regenerate with pinned uv and require byte-for-byte lock equality."""
    policy, errors = _load_policy(policy_path)
    errors.extend(check_repository(root, policy_path, DEFAULT_EXCEPTIONS))
    if errors:
        raise RuntimeError("\n".join(dict.fromkeys(errors)))
    lock_path = _safe_path(root, policy["lock_file"])
    current = lock_path.read_text(encoding="utf-8")
    generated = _generate_lock_content(root, policy, uv_binary)
    difference = _generated_lock_diff(current, generated)
    if difference:
        raise RuntimeError("resolver output drift:\n" + "\n".join(difference))
    parsed = _read_requirement_file(lock_path)
    print(f"Resolver reproduced all {len(parsed.requirements)} locked entries byte-for-byte.")


def _update_lock(root: Path, policy_path: Path, uv_binary: str) -> None:
    """Regenerate the lock and refresh its reviewed digest."""
    policy, errors = _load_policy(policy_path)
    if errors:
        raise RuntimeError("\n".join(errors))
    lock_path = _safe_path(root, policy["lock_file"])
    lock_content = _generate_lock_content(root, policy, uv_binary)
    lock_path.write_text(lock_content, encoding="utf-8")
    policy["lock_sha256"] = _content_sha256(lock_content.encode("utf-8"))
    policy_path.write_text(json.dumps(policy, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    post_update_errors = check_repository(root, policy_path, DEFAULT_EXCEPTIONS)
    if post_update_errors:
        raise RuntimeError("generated dependency lock failed validation:\n" + "\n".join(post_update_errors))
    parsed = _read_requirement_file(lock_path)
    print(f"Updated {lock_path.relative_to(root)} with {len(parsed.requirements)} resolved entries.")


def _write_fixture(
    root: Path,
    lock_body: str = "bar==2\nfoo==1\nsetuptools==1\n",
) -> tuple[Path, Path]:
    """Create one isolated repository fixture for guard self-tests."""
    if not any(line.startswith("setuptools") for line in lock_body.splitlines()):
        lock_body = lock_body.rstrip() + "\nsetuptools==1\n"
    (root / "scripts").mkdir(parents=True)
    (root / "requirements.txt").write_text("-c constraints.txt\nfoo>=1\n", encoding="utf-8")
    (root / "requirements-pydanticai.txt").write_text("bar==2\n", encoding="utf-8")
    (root / "build-constraints.txt").write_text("setuptools==1\n", encoding="utf-8")
    exception_path = root / "scripts" / "dependency_lock_exceptions.json"
    exception_path.write_text('{"exceptions": []}\n', encoding="utf-8")
    policy = {
        "schema_version": 2,
        "lock_file": "constraints.txt",
        "build_constraint_file": "build-constraints.txt",
        "resolver": {
            "name": "uv",
            "version": "0.11.31",
            "python_version": "3.10",
            "python_versions": ["3.10", "3.11", "3.12", "3.13", "3.14"],
            "exclude_newer": "2030-01-01T00:00:00Z",
            "universal": True,
        },
        "source_files": [
            "requirements.txt",
            "requirements-pydanticai.txt",
            "build-constraints.txt",
        ],
        "exact_source_files": ["requirements-pydanticai.txt", "build-constraints.txt"],
        "install_contracts": {
            "requirements.txt": {
                "constraint": "constraints.txt",
                "includes": [],
                "packages": [],
                "allow_other_packages": True,
            }
        },
        "runtime_install_contracts": {},
        "lock_sha256": "",
    }
    policy_path = root / "scripts" / "dependency_lock_policy.json"
    policy_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    _refresh_fixture_lock(root, lock_body)
    return policy_path, exception_path


def _refresh_fixture_lock(root: Path, lock_body: str) -> None:
    """Refresh fixture lock metadata after an intentional test mutation."""
    policy_path = root / "scripts" / "dependency_lock_policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    source_sha = _source_sha256(root, policy["source_files"])
    content = _render_header(policy, source_sha) + lock_body.strip() + "\n"
    (root / "constraints.txt").write_text(content, encoding="utf-8")
    policy["lock_sha256"] = _content_sha256(content.encode("utf-8"))
    policy_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")


def _run_self_tests() -> None:
    """Exercise compliant, drift, pin, matrix, and exception fixtures."""
    today = date(2030, 1, 1)
    cases = 0

    def validate(root: Path, expected_fragment: Optional[str] = None) -> None:
        """Run one fixture and assert its expected outcome."""
        nonlocal cases
        cases += 1
        errors = check_repository(
            root,
            root / "scripts" / "dependency_lock_policy.json",
            root / "scripts" / "dependency_lock_exceptions.json",
            today=today,
        )
        if expected_fragment is None:
            assert not errors, errors
        else:
            assert any(expected_fragment in error for error in errors), errors

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        _write_fixture(root)
        validate(root)

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        _write_fixture(root)
        (root / "requirements.txt").write_text("-c constraints.txt\nfoo>=2\n", encoding="utf-8")
        validate(root, "source digest drift")

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        _write_fixture(root)
        with (root / "constraints.txt").open("a", encoding="utf-8") as lock_file:
            lock_file.write("\n")
        validate(root, "lock digest drift")

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        _write_fixture(root, "bar==2\nfoo>=1\n")
        validate(root, "unpinned-version")

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        _write_fixture(root, "bar==2\nfoo @ git+https://example.com/foo.git@main\n")
        validate(root, "mutable-source")

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        policy_path, _ = _write_fixture(root)
        (root / "requirements.txt").write_text(
            "-c constraints.txt\nfoo @ git+https://example.com/foo.git@main\n",
            encoding="utf-8",
        )
        _refresh_fixture_lock(
            root,
            "bar==2\n"
            "foo @ git+https://example.com/foo.git@0123456789abcdef0123456789abcdef01234567\n"
            "setuptools==1\n",
        )
        validate(root, "direct source has mutable-source")

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        policy_path, _ = _write_fixture(root)
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["resolver"]["exclude_newer"] = "2031-01-01T00:00:00Z"
        policy_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
        _refresh_fixture_lock(root, "bar==2\nfoo==1\nsetuptools==1\n")
        validate(root, "must not be in the future")

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        _write_fixture(
            root,
            'bar==2\nfoo==1 ; python_version >= "3.10"\nfoo==2 ; python_version < "3.12"\n',
        )
        validate(root, "overlapping lock entries")

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        _write_fixture(root, "bar==2\nfoo>=1\n")
        (root / "scripts" / "dependency_lock_exceptions.json").write_text(
            json.dumps(
                {
                    "exceptions": [
                        {
                            "kind": "unpinned-version",
                            "package": "foo",
                            "expires": "2030-01-15",
                            "owner": "security-maintainers",
                            "reason": "Tracked resolver blocker with a bounded remediation plan.",
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )
        validate(root)

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        _write_fixture(root, "bar==2\nfoo>=1\n")
        (root / "scripts" / "dependency_lock_exceptions.json").write_text(
            '{"exceptions":[{"kind":"unpinned-version","package":"foo",'
            '"expires":"2029-12-31","owner":"security-maintainers",'
            '"reason":"Tracked blocker."}]}\n',
            encoding="utf-8",
        )
        validate(root, "exception expired")

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        _write_fixture(root, "bar==2\nfoo>=1\n")
        (root / "scripts" / "dependency_lock_exceptions.json").write_text(
            '{"exceptions":[{"kind":"unpinned-version","package":"foo",'
            '"expires":"2030-02-15","owner":"security-maintainers",'
            '"reason":"Tracked blocker."}]}\n',
            encoding="utf-8",
        )
        validate(root, "30-day maximum")

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        _write_fixture(root)
        (root / "requirements.txt").write_text("-c constraints.txt\nfoo>=2\n", encoding="utf-8")
        _refresh_fixture_lock(root, "bar==2\nfoo==2\nsetuptools==1\n")
        validate(root)

    cases += 1
    assert _generated_lock_diff("foo==1\n", "bar==1\nfoo==1\n")

    def write_runtime_fixture(root: Path, *, safe: bool) -> None:
        """Add one reviewed runtime pip-install contract to a fixture."""
        source_dir = root / "src"
        source_dir.mkdir()
        no_deps = ', "--no-deps"' if safe else ""
        (source_dir / "service.py").write_text(
            "import subprocess\nimport sys\n"
            f"subprocess.run([sys.executable, '-m', 'pip', 'install'{no_deps}, 'example'])\n",
            encoding="utf-8",
        )
        policy_path = root / "scripts" / "dependency_lock_policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["runtime_install_contracts"] = {
            "src/service.py": {"package": "example", "required_flags": ["--no-deps"]}
        }
        policy_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        _write_fixture(root)
        write_runtime_fixture(root, safe=False)
        validate(root, "runtime pip install is missing")

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        _write_fixture(root)
        write_runtime_fixture(root, safe=False)
        (root / "scripts" / "dependency_lock_exceptions.json").write_text(
            json.dumps(
                {
                    "exceptions": [
                        {
                            "kind": "unconstrained-install",
                            "package": "example",
                            "path": "src/service.py",
                            "expires": "2030-01-15",
                            "owner": "security-maintainers",
                            "reason": "Tracked cross-owner remediation with a bounded deadline.",
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )
        validate(root)

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        _write_fixture(root)
        write_runtime_fixture(root, safe=True)
        validate(root)

    print(f"Dependency lock self-tests passed ({cases} cases).")


def main() -> int:
    """Run repository validation, self-tests, regeneration, or resolver verification."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--self-test", action="store_true", help="run isolated guard regression cases")
    mode.add_argument("--update", action="store_true", help="regenerate the universal lock with pinned uv")
    mode.add_argument(
        "--verify-generated",
        action="store_true",
        help="require pinned uv to reproduce the lock byte-for-byte",
    )
    parser.add_argument("--uv", default="uv", help="path to the pinned uv executable")
    args = parser.parse_args()

    if args.self_test:
        _run_self_tests()
        return 0
    if args.update:
        try:
            _update_lock(ROOT, DEFAULT_POLICY, args.uv)
        except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
            print(f"Dependency lock update failed: {exc}")
            return 1
        return 0
    if args.verify_generated:
        try:
            _verify_generated_lock(ROOT, DEFAULT_POLICY, args.uv)
        except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
            print(f"Dependency lock verification failed: {exc}")
            return 1
        return 0

    errors = check_repository()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    lock = _read_requirement_file(ROOT / "constraints.txt")
    print(f"Dependency lock checks passed for {len(lock.requirements)} resolved entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
