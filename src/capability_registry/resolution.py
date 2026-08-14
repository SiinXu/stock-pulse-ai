# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Dependency and version compatibility resolution for declared capabilities."""

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
    def __init__(self, error_code: str, message: str = "") -> None:
        super().__init__(message or error_code)
        self.error_code = error_code
        self.message = message or error_code


def _inventory_index(inventory_items: Iterable[Any] | None) -> Dict[str, Any]:
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


def resolve_capability_dependencies(
    entry: WriteCapabilityEntry,
    *,
    write_snapshot: WriteRegistrySnapshot,
    inventory_items: Iterable[Any] | None = None,
) -> ResolutionResult:
    write_index = {item.capability_id: item for item in write_snapshot.entries}
    live_index = _inventory_index(inventory_items)
    satisfied: list[str] = []
    issues: list[DependencyIssue] = []

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
        return ResolutionResult(
            capability_id=entry.capability_id,
            ready=False,
            reason_code=issues[0].reason_code,
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
    if capability_ids is None:
        wanted: Optional[Set[str]] = None
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
                # The id was requested and answered as retired; without this the
                # `wanted - seen` sweep below would append a second, contradictory
                # capability_not_found result for the same capability.
                seen.add(entry.capability_id)
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
        for capability_id in sorted(wanted - seen):
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
    try:
        return service.list_entries(include_retired=True)
    except WriteRegistryStoreError as exc:
        raise CapabilityResolutionError(exc.error_code, str(exc)) from exc
