"""Stable migration definitions, results, and errors."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from functools import partial
import hashlib
import inspect
import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence, Tuple, Union

from sqlalchemy.sql.elements import TextClause


MigrationParameters = Optional[Union[Mapping[str, Any], Sequence[Any]]]


class MigrationMappingResult(Protocol):
    """Safe mapping rows returned by a migration statement."""

    def one_or_none(self) -> Optional[Mapping[str, Any]]:
        """Return the only mapping row, failing if more than one exists."""


class MigrationStatementResult(Protocol):
    """Materialized statement result without a raw cursor or connection handle."""

    def fetchall(self) -> list[Tuple[Any, ...]]:
        """Return all rows as detached tuples."""

    def mappings(self) -> MigrationMappingResult:
        """Return detached rows keyed by their selected column names."""


class MigrationExecution(Protocol):
    """Restricted SQL execution capability supplied to migration upgrades."""

    def execute(
        self,
        statement: TextClause,
        parameters: MigrationParameters = None,
    ) -> MigrationStatementResult:
        """Execute one exact ``sqlalchemy.text()`` statement in the transaction."""

    def exec_driver_sql(
        self,
        statement: str,
        parameters: MigrationParameters = None,
    ) -> MigrationStatementResult:
        """Execute one driver SQL statement inside the runner-owned transaction."""


MigrationUpgrade = Callable[[MigrationExecution], None]
_MIGRATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_MIGRATION_EXECUTION_ANNOTATION_NAMES = frozenset(
    {
        "Connection",
        "MigrationExecution",
    }
)
_RAW_DBAPI_SOURCE_ATTRIBUTES = frozenset(
    {
        "dbapi_connection",
        "driver_connection",
        "raw_connection",
    }
)
_RAW_DBAPI_SOURCE_NAMES = frozenset(
    {
        "dbapi_connection",
        "driver_connection",
        "raw_connection",
    }
)
_TRANSACTION_CONTROL_SOURCE_ATTRIBUTES = frozenset(
    {
        "begin",
        "begin_nested",
        "begin_twophase",
        "close",
        "commit",
        "detach",
        "execution_options",
        "get_nested_transaction",
        "get_transaction",
        "invalidate",
        "rollback",
        "set_authorizer",
    }
)


def _is_lazy_upgrade_callable(upgrade: MigrationUpgrade) -> bool:
    """Return whether registration cannot prove immediate synchronous execution."""
    checked = set()
    active = set()

    def visit(candidate) -> bool:
        candidate_key = id(candidate)
        if candidate_key in active:
            return True
        if candidate_key in checked:
            return False

        active.add(candidate_key)
        try:
            try:
                unwrapped = inspect.unwrap(candidate)
            except ValueError:
                return True

            if any(
                inspect.iscoroutinefunction(current)
                or inspect.isasyncgenfunction(current)
                or inspect.isgeneratorfunction(current)
                for current in (candidate, unwrapped)
            ):
                return True

            dependencies = []
            if unwrapped is not candidate:
                dependencies.append(unwrapped)
            if isinstance(candidate, partial):
                dependencies.append(candidate.func)
            elif not inspect.isroutine(candidate):
                call = getattr(type(candidate), "__call__", None)
                if call is not None:
                    dependencies.append(call)
            return any(visit(dependency) for dependency in dependencies)
        finally:
            active.remove(candidate_key)
            checked.add(candidate_key)

    return visit(upgrade)


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


def _function_migration_parameter_names(
    node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
) -> frozenset[str]:
    names = set()
    positional = (*node.args.posonlyargs, *node.args.args)
    if node.name == "upgrade" and positional:
        names.add(positional[0].arg)
    for argument in (*positional, *node.args.kwonlyargs):
        annotation = argument.annotation
        if annotation is not None and any(
            (
                isinstance(part, ast.Name)
                and part.id in _MIGRATION_EXECUTION_ANNOTATION_NAMES
            ) or (
                isinstance(part, ast.Attribute)
                and part.attr in _MIGRATION_EXECUTION_ANNOTATION_NAMES
            )
            for part in ast.walk(annotation)
        ):
            names.add(argument.arg)
    return frozenset(names)


def _attribute_root_name(node: ast.AST) -> Optional[str]:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _receiver_attribute_names(node: ast.AST) -> frozenset[str]:
    names = set()
    while isinstance(node, ast.Attribute):
        names.add(node.attr)
        node = node.value
    return frozenset(names)


class _SourceBoundMigrationGuard(ast.NodeVisitor):
    def __init__(self) -> None:
        self._migration_scopes = [frozenset()]

    @property
    def _migration_names(self) -> frozenset[str]:
        return self._migration_scopes[-1]

    def _visit_function(
        self,
        node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
    ) -> None:
        parameters = (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        )
        parameter_names = {argument.arg for argument in parameters}
        if node.args.vararg is not None:
            parameter_names.add(node.args.vararg.arg)
        if node.args.kwarg is not None:
            parameter_names.add(node.args.kwarg.arg)
        inherited_names = self._migration_names - parameter_names
        self._migration_scopes.append(
            inherited_names | _function_migration_parameter_names(node)
        )
        try:
            self.generic_visit(node)
        finally:
            self._migration_scopes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        root_name = _attribute_root_name(node.value)
        receiver_attributes = _receiver_attribute_names(node.value)
        chain_attributes = receiver_attributes | {node.attr}
        raw_attribute = next(
            (
                name
                for name in chain_attributes
                if name in _RAW_DBAPI_SOURCE_ATTRIBUTES
            ),
            None,
        )
        if raw_attribute is None and (
            "connection" in chain_attributes
            and root_name in self._migration_names
        ):
            raw_attribute = "connection"
        if raw_attribute is not None:
            raise ValueError(
                "Migration source contains forbidden raw DBAPI access "
                f"({raw_attribute}) at line {node.lineno}"
            )

        if (
            node.attr in _TRANSACTION_CONTROL_SOURCE_ATTRIBUTES
            and (
                root_name
                in self._migration_names | _RAW_DBAPI_SOURCE_NAMES
                or receiver_attributes & _RAW_DBAPI_SOURCE_ATTRIBUTES
            )
        ):
            raise ValueError(
                "Migration source contains forbidden transaction control "
                f"({node.attr}) at line {node.lineno}"
            )
        self.generic_visit(node)


def _validate_source_bound_migration_source(source: str) -> None:
    """Reject direct transaction escape hatches in trusted migration modules.

    This source guard is defense in depth for repository-owned code. It does not
    attempt to make an arbitrary Python migration a security sandbox.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError("Migration source cannot be parsed") from exc

    _SourceBoundMigrationGuard().visit(tree)


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

        checksum_source = read_checksum_source(source_path)
        _validate_source_bound_migration_source(checksum_source)
        migration = cls(
            id=id,
            description=description,
            upgrade=upgrade,
            checksum_source=checksum_source,
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
        if _is_lazy_upgrade_callable(self.upgrade):
            raise TypeError("Migration upgrade must be synchronous")
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
