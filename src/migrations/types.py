"""Stable migration definitions, results, and errors."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Callable, Optional, Tuple, Union

from sqlalchemy.engine import Connection


MigrationUpgrade = Callable[[Connection], None]
_MIGRATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def normalize_checksum_source(source: str) -> str:
    """Normalize physical line endings while preserving authored semantics."""
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Migration checksum source must be non-empty")
    return source.replace("\r\n", "\n").replace("\r", "\n")


def calculate_checksum(*, migration_id: str, description: str, source: str) -> str:
    """Return the deterministic SHA-256 for canonical migration content."""
    material = json.dumps(
        {
            "description": description,
            "id": migration_id,
            "source": normalize_checksum_source(source),
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _resolve_checksum_source(source_file: Union[str, Path]) -> Path:
    path = Path(source_file)
    candidates = [path]
    if path.suffix in {".pyc", ".pyo"}:
        if path.parent.name == "__pycache__":
            module_name = path.name.split(".", 1)[0]
            candidates.insert(0, path.parent.parent / f"{module_name}.py")
        else:
            candidates.insert(0, path.with_suffix(".py"))

    for candidate in candidates:
        if candidate.is_file() and candidate.suffix == ".py":
            return candidate
    raise ValueError("Migration source file is unavailable")


def read_checksum_source(source_file: Union[str, Path]) -> str:
    """Read authored migration source without including its machine-local path."""
    try:
        return _resolve_checksum_source(source_file).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError("Migration source file cannot be read") from exc


@dataclass(frozen=True)
class Migration:
    """One immutable, explicitly registered migration."""

    id: str
    description: str
    upgrade: MigrationUpgrade = field(repr=False, compare=False)
    checksum_source: str = field(repr=False, compare=False)
    source_bound: bool = field(default=False, init=False, repr=False, compare=False)
    is_legacy_baseline: bool = False
    bootstraps_registry: bool = False
    checksum: str = field(init=False)

    @classmethod
    def from_source_file(
        cls,
        *,
        id: str,
        description: str,
        upgrade: MigrationUpgrade,
        source_file: Union[str, Path],
        is_legacy_baseline: bool = False,
        bootstraps_registry: bool = False,
    ) -> "Migration":
        """Create a migration whose checksum covers its complete authored module."""
        source_path = _resolve_checksum_source(source_file)
        module_parts = tuple(upgrade.__module__.split("."))
        source_module_parts = source_path.with_suffix("").parts[-len(module_parts):]
        if tuple(source_module_parts) != module_parts:
            raise ValueError("Migration source file does not match upgrade module")

        migration = cls(
            id=id,
            description=description,
            upgrade=upgrade,
            checksum_source=read_checksum_source(source_path),
            is_legacy_baseline=is_legacy_baseline,
            bootstraps_registry=bootstraps_registry,
        )
        object.__setattr__(migration, "source_bound", True)
        return migration

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not _MIGRATION_ID_PATTERN.fullmatch(self.id):
            raise ValueError(f"Invalid migration ID: {self.id!r}")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("Migration description must be non-empty")
        if len(self.description) > 255:
            raise ValueError("Migration description exceeds 255 characters")
        if not callable(self.upgrade):
            raise TypeError("Migration upgrade must be callable")
        checksum = calculate_checksum(
            migration_id=self.id,
            description=self.description,
            source=self.checksum_source,
        )
        object.__setattr__(self, "checksum", checksum)


@dataclass(frozen=True, kw_only=True)
class MigrationState:
    """Structured state shared by status, verification, and apply results."""

    current_version: Optional[str] = None
    target_version: Optional[str] = None
    applied_ids: Tuple[str, ...] = ()
    pending_ids: Tuple[str, ...] = ()
    unknown_ids: Tuple[str, ...] = ()
    checksum_mismatches: Tuple[str, ...] = ()
    description_mismatches: Tuple[str, ...] = ()
    success: bool = False
    failure_code: Optional[str] = None
    failed_migration_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Return a JSON-ready public representation."""
        return {
            "current_version": self.current_version,
            "target_version": self.target_version,
            "applied_ids": list(self.applied_ids),
            "pending_ids": list(self.pending_ids),
            "unknown_ids": list(self.unknown_ids),
            "checksum_mismatches": list(self.checksum_mismatches),
            "description_mismatches": list(self.description_mismatches),
            "success": self.success,
            "failure_code": self.failure_code,
            "failed_migration_id": self.failed_migration_id,
        }


@dataclass(frozen=True, kw_only=True)
class MigrationStatus(MigrationState):
    """Read-only ordered migration status."""


@dataclass(frozen=True, kw_only=True)
class VerificationResult(MigrationState):
    """Verification result; pending migrations make verification fail."""


@dataclass(frozen=True, kw_only=True)
class MigrationResult(MigrationState):
    """Result of applying every currently pending migration."""

    executed_ids: Tuple[str, ...] = ()

    def to_dict(self) -> dict:
        result = super().to_dict()
        result["executed_ids"] = list(self.executed_ids)
        return result


class MigrationError(RuntimeError):
    """Safe migration failure with a stable category and optional ID."""

    def __init__(
        self,
        failure_code: str,
        migration_id: Optional[str] = None,
        *,
        state: Optional[MigrationState] = None,
    ):
        self.failure_code = failure_code
        self.migration_id = migration_id
        self.state = state
        detail = f" code={failure_code}"
        if migration_id:
            detail += f" migration_id={migration_id}"
        super().__init__(f"Database migration failed:{detail}")

    @classmethod
    def from_state(cls, state: MigrationState) -> "MigrationError":
        return cls(
            state.failure_code or "migration_failed",
            state.failed_migration_id,
            state=state,
        )


class MigrationRegistryError(MigrationError):
    """The in-code registry is invalid and cannot be executed."""


def validate_registry(migrations: Tuple[Migration, ...]) -> Tuple[Migration, ...]:
    """Validate uniqueness and strict authored ordering."""
    if not migrations:
        raise MigrationRegistryError("empty_registry")

    seen = set()
    previous_id: Optional[str] = None
    for migration in migrations:
        if migration.id in seen:
            raise MigrationRegistryError("duplicate_migration_id", migration.id)
        if previous_id is not None and migration.id <= previous_id:
            raise MigrationRegistryError("migration_order_invalid", migration.id)
        seen.add(migration.id)
        previous_id = migration.id
    return migrations
