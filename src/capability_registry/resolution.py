# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Dependency and version compatibility resolution for declared capabilities.

Resolution is fail-closed: missing dependencies, retired targets, version
mismatches, cycles, and inventory source errors produce explicit reason codes.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional, Set

from src.capability_registry.write_models import (
    DependencyIssue,
    ResolutionResult,
    WriteCapabilityEntry,
    WriteRegistrySnapshot,
    parse_dependency_token,
    versions_compatible,
)
from src.capability_registry.write_store import WriteRegistryStoreError


class CapabilityResolutionError(Exception):
    """Raised when the resolver cannot evaluate the graph at all."""

    def __init__(self, error_code: str, message: str = "") -> None:
        super().__init__(message or error_code)
        self.error_code = error_code
        self.message = message or error_code


def _inventory_index(
    inventory_items: Iterable[Any] | None,
) -> Dict[str, Any]:
    index: Dict[str, Any] = {}
    if inventory_items is None:
        return index
    for item in inventory_items:
        capability_id = getattr(item, "capability_id", None)
        if capability_id is None and isinstance(item, Mapping):
            capability_id = item.get("capability_id") or item.get("id")
        if not capability_id:
            continue
        index[str(capability_id)] = item
    return index


def _entry_version(provider: Any) -> str:
    if isinstance(provider, WriteCapabilityEntry):
        return provider.version
    version = getattr(provider, "version", None)
    if version is None and isinstance(provider, Mapping):
        version = provider.get("version")
    return str(version or "1")


def _is_available(provider: Any) -> tuple[bool, str]:
    """Return whether a provider entry can satisfy a dependency."""

    if isinstance(provider, WriteCapabilityEntry):
        if provider.status == "retired":
            return False, "dependency_retired"
        return True, ""
    status = getattr(provider, "status", None)
    if status is None and isinstance(provider, Mapping):
        status = provider.get("status")
    if status == "retired":
        return False, "dependency_retired"
    registered = getattr(provider, "registered", None)
    if registered is None and isinstance(provider, Mapping):
        registered = provider.get("registered")
    if registered is False:
        return False, "dependency_not_registered"
    executable = getattr(provider, "executable", None)
    if executable is None and isinstance(provider, Mapping):
        executable = provider.get("executable")
    if executable is False:
        reason = getattr(provider, "reason_code", None)
        if reason is None and isinstance(provider, Mapping):
            reason = provider.get("reason_code")
        return False, str(reason or "dependency_not_executable")
    return True, ""


def detect_dependency_cycle(
    entry: WriteCapabilityEntry,
    *,
    write_snapshot: WriteRegistrySnapshot,
) -> Optional[tuple[str, ...]]:
    """Return a cycle path starting at ``entry`` when one exists, else None."""

    write_index = {item.capability_id: item for item in write_snapshot.entries}

    def neighbors(capability_id: str) -> list[str]:
        node = write_index.get(capability_id)
        if node is None:
            return []
        result: list[str] = []
        for token in node.dependencies:
            dep_id, _operator, _version = parse_dependency_token(token)
            if dep_id in write_index:
                result.append(dep_id)
        return result

    path: list[str] = [entry.capability_id]
    visiting: Set[str] = {entry.capability_id}
    visited: Set[str] = set()

    def dfs(node_id: str) -> Optional[tuple[str, ...]]:
        for dep_id in neighbors(node_id):
            if dep_id in visiting:
                cycle_start = path.index(dep_id)
                return tuple(path[cycle_start:] + [dep_id])
            if dep_id in visited:
                continue
            visiting.add(dep_id)
            path.append(dep_id)
            found = dfs(dep_id)
            path.pop()
            visiting.remove(dep_id)
            if found is not None:
                return found
        visited.add(node_id)
        return None

    return dfs(entry.capability_id)


def resolve_capability_dependencies(
    entry: WriteCapabilityEntry,
    *,
    write_snapshot: WriteRegistrySnapshot,
    inventory_items: Iterable[Any] | None = None,
) -> ResolutionResult:
    """Resolve one entry's dependencies against write registry + inventory."""

    write_index = {
        item.capability_id: item for item in write_snapshot.entries
    }
    live_index = _inventory_index(inventory_items)
    satisfied: list[str] = []
    issues: list[DependencyIssue] = []

    cycle = detect_dependency_cycle(entry, write_snapshot=write_snapshot)
    if cycle is not None:
        cycle_text = " -> ".join(cycle)
        return ResolutionResult(
            capability_id=entry.capability_id,
            ready=False,
            reason_code="dependency_cycle",
            satisfied=(),
            issues=(
                DependencyIssue(
                    dependency=cycle_text,
                    capability_id=entry.capability_id,
                    reason_code="dependency_cycle",
                    detail=cycle_text,
                ),
            ),
            checked_against_generation=write_snapshot.generation,
        )

    for token in entry.dependencies:
        dep_id, operator, required_version = parse_dependency_token(token)
        provider: Any | None = write_index.get(dep_id)
        source = "write_registry"
        if provider is None:
            provider = live_index.get(dep_id)
            source = "inventory"
        if provider is None:
            issues.append(
                DependencyIssue(
                    dependency=token,
                    capability_id=dep_id,
                    reason_code="dependency_missing",
                    detail="not found in write registry or live inventory",
                )
            )
            continue
        available, reason = _is_available(provider)
        if not available:
            issues.append(
                DependencyIssue(
                    dependency=token,
                    capability_id=dep_id,
                    reason_code=reason,
                    detail=f"source={source}",
                )
            )
            continue
        installed_version = _entry_version(provider)
        if operator and not versions_compatible(
            installed_version, operator=operator, required=required_version
        ):
            issues.append(
                DependencyIssue(
                    dependency=token,
                    capability_id=dep_id,
                    reason_code="version_incompatible",
                    detail=(
                        f"installed={installed_version} required={operator}"
                        f"{required_version} source={source}"
                    ),
                )
            )
            continue
        satisfied.append(token)

    if issues:
        primary = issues[0].reason_code
        return ResolutionResult(
            capability_id=entry.capability_id,
            ready=False,
            reason_code=primary,
            satisfied=tuple(satisfied),
            issues=tuple(issues),
            checked_against_generation=write_snapshot.generation,
        )
    return ResolutionResult(
        capability_id=entry.capability_id,
        ready=True,
        reason_code="dependencies_satisfied",
        satisfied=tuple(satisfied),
        issues=(),
        checked_against_generation=write_snapshot.generation,
    )


def resolve_many(
    capability_ids: Iterable[str] | None,
    *,
    write_snapshot: WriteRegistrySnapshot,
    inventory_items: Iterable[Any] | None = None,
    active_only: bool = True,
) -> tuple[ResolutionResult, ...]:
    """Resolve selected entries or every active entry when ids are omitted."""

    wanted: Optional[Set[str]]
    if capability_ids is None:
        wanted = None
    else:
        wanted = {str(item).strip() for item in capability_ids if str(item).strip()}
        if not wanted:
            raise CapabilityResolutionError(
                "empty_capability_set",
                "at least one capability_id is required",
            )

    results: list[ResolutionResult] = []
    seen: set[str] = set()
    for entry in write_snapshot.entries:
        if wanted is not None and entry.capability_id not in wanted:
            continue
        if active_only and entry.status != "active":
            if wanted is not None:
                results.append(
                    ResolutionResult(
                        capability_id=entry.capability_id,
                        ready=False,
                        reason_code="capability_retired",
                        checked_against_generation=write_snapshot.generation,
                    )
                )
            continue
        results.append(
            resolve_capability_dependencies(
                entry,
                write_snapshot=write_snapshot,
                inventory_items=inventory_items,
            )
        )
        seen.add(entry.capability_id)

    if wanted is not None:
        missing = sorted(wanted - seen)
        for capability_id in missing:
            results.append(
                ResolutionResult(
                    capability_id=capability_id,
                    ready=False,
                    reason_code="capability_not_found",
                    checked_against_generation=write_snapshot.generation,
                )
            )

    results.sort(key=lambda item: item.capability_id)
    return tuple(results)


def load_snapshot_or_raise(service: Any) -> WriteRegistrySnapshot:
    """Load the write registry through a service, mapping store errors."""

    try:
        return service.list_entries(include_retired=True)
    except WriteRegistryStoreError as exc:
        raise CapabilityResolutionError(exc.error_code, str(exc)) from exc
