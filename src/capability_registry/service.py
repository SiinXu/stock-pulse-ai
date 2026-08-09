# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Owner-driven, read-only capability inventory snapshots."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional

from src.capability_registry.models import (
    CapabilityRecord,
    CapabilitySnapshot,
    SourceStatus,
)
from src.utils.sanitize import log_safe_exception

Clock = Callable[[], datetime]
logger = logging.getLogger(__name__)


def collect_capability_records(
    *,
    data_provider_runtime: Any | None = None,
    tool_registry: Any | None = None,
    plugin_manager: Any | None = None,
    domains: Iterable[str] | None = None,
    clock: Clock | None = None,
) -> CapabilitySnapshot:
    """Capture each authoritative owner once or expose an explicit source error."""
    allowed = _domains(domains)
    now = (clock or (lambda: datetime.now(timezone.utc)))().isoformat()
    sources: list[SourceStatus] = []
    records: list[CapabilityRecord] = []
    if "data" in allowed:
        try:
            runtime = (
                data_provider_runtime
                if data_provider_runtime is not None
                else _resolve_data_runtime()
            )
            generation, active = runtime.active_provider_snapshot()
            source_generation = str(generation)
            records.extend(_data_records(active, source_generation, now))
            sources.append(SourceStatus("data", "ok", source_generation, now))
        except Exception as exc:  # broad-exception: fallback_recorded - expose source error
            log_safe_exception(
                logger, "Capability data source unavailable", exc,
                error_code="capability_data_source_unavailable",
            )
            sources.append(SourceStatus(
                "data", "error", "unknown", now, "data_source_unavailable",
            ))
    if "tool" in allowed:
        try:
            registry = (
                tool_registry if tool_registry is not None else _resolve_tool_registry()
            )
            generation, definitions, declarations = _stable_tool_snapshot(registry)
            records.extend(_tool_records(definitions, declarations, generation, now))
            sources.append(SourceStatus("tool", "ok", generation, now))
        except RuntimeError:
            sources.append(SourceStatus(
                "tool", "generation_drift", "unknown", now,
                "tool_generation_drift",
            ))
        except Exception as exc:  # broad-exception: fallback_recorded - expose source error
            log_safe_exception(
                logger, "Capability tool source unavailable", exc,
                error_code="capability_tool_source_unavailable",
            )
            sources.append(SourceStatus(
                "tool", "error", "unknown", now, "tool_source_unavailable",
            ))
    if "extension" in allowed:
        try:
            manager = (
                plugin_manager
                if plugin_manager is not None
                else _resolve_plugin_manager()
            )
            generation, lifecycle, registrations = _stable_extension_snapshot(manager)
            records.extend(_extension_records(lifecycle, registrations, generation, now))
            sources.append(SourceStatus("extension", "ok", generation, now))
        except RuntimeError:
            sources.append(SourceStatus(
                "extension", "generation_drift", "unknown", now,
                "extension_generation_drift",
            ))
        except Exception as exc:  # broad-exception: fallback_recorded - expose source error
            log_safe_exception(
                logger, "Capability extension source unavailable", exc,
                error_code="capability_extension_source_unavailable",
            )
            sources.append(SourceStatus(
                "extension", "error", "unknown", now,
                "extension_source_unavailable",
            ))
    records.sort(key=lambda item: (item.domain, item.capability_id))
    return CapabilitySnapshot(sources=tuple(sources), items=tuple(records))


def _domains(domains: Iterable[str] | None) -> set[str]:
    allowed = {"data", "tool", "extension"} if domains is None else {
        str(item).strip() for item in domains
    }
    unknown = allowed - {"data", "tool", "extension"}
    if unknown or not allowed:
        raise ValueError(f"unsupported capability domains: {sorted(unknown)}")
    return allowed


def _resolve_data_runtime() -> Any:
    from data_provider import DataFetcherManager
    manager = DataFetcherManager()
    runtime = getattr(manager, "_data_provider_runtime", None)
    if runtime is None:
        raise RuntimeError("data provider runtime unavailable")
    return runtime


def _resolve_tool_registry() -> Any:
    from src.agent.runtime_assembly import get_tool_registry
    return get_tool_registry()


def _resolve_plugin_manager() -> Any:
    from src.application_services import get_application_services
    return get_application_services().plugin_manager


def _data_records(active: Any, generation: str, now: str) -> list[CapabilityRecord]:
    records: list[CapabilityRecord] = []
    capability_providers: dict[str, list[str]] = {}
    for item in active:
        registration = item.registration
        provider_id = registration.provider_id
        provider_name = str(getattr(item.provider, "name", provider_id))
        markets = tuple(sorted(registration.markets))
        capabilities = tuple(sorted(registration.capabilities))
        records.append(CapabilityRecord(
            f"data.provider:{provider_id}", "data", "data_provider",
            "data_provider.runtime", provider_name, "1", generation, now,
            registered=True, configured=None, dependency_ready=None,
            executable=None, healthy=None, degraded=None,
            markets=markets, display_name=provider_name,
        ))
        for capability in capabilities:
            capability_providers.setdefault(capability, []).append(provider_id)
    for capability, providers in capability_providers.items():
        records.append(CapabilityRecord(
            f"data.method:{capability}", "data", "data_method",
            "data_provider.runtime", ",".join(sorted(providers)), "1", generation, now,
            registered=True, configured=None, dependency_ready=None,
            executable=None, healthy=None, degraded=None,
            display_name=capability,
        ))
    return records


def _stable_tool_snapshot(
    registry: Any,
) -> tuple[str, tuple[Any, ...], tuple[Any, ...]]:
    inventory_snapshot = getattr(registry, "capability_inventory_snapshot", None)
    if callable(inventory_snapshot):
        generation, definitions, declarations = inventory_snapshot()
        return str(generation), tuple(definitions), tuple(declarations)
    owner_snapshot = getattr(registry, "definition_snapshot", None)
    if callable(owner_snapshot):
        generation, definitions = owner_snapshot()
        return str(generation), tuple(definitions), ()
    for _ in range(3):
        definitions = tuple(registry.list_tools())
        before = {
            definition.name: registry.definition_version(definition.name)
            for definition in definitions
        }
        after = {
            definition.name: registry.definition_version(definition.name)
            for definition in definitions
        }
        if before == after and len(before) == len(definitions):
            generation = ",".join(f"{name}:{before[name]}" for name in sorted(before)) or "empty"
            return generation, definitions, ()
    raise RuntimeError("tool registry generation drift")


def _tool_records(
    definitions: tuple[Any, ...],
    declarations: tuple[Any, ...],
    generation: str,
    now: str,
) -> list[CapabilityRecord]:
    records: list[CapabilityRecord] = []
    registered_names = {definition.name for definition in definitions}
    declared_by_name = {
        declaration.name: declaration for declaration in declarations
    }
    for definition in definitions:
        policy = getattr(definition, "policy", None)
        scopes = tuple(sorted(
            str(value) for value in (getattr(policy, "permissions", ()) or ())
        ))
        declaration = declared_by_name.get(definition.name)
        records.append(CapabilityRecord(
            f"tool:{definition.name}", "tool", "agent_tool", "agent.tool_registry",
            definition.name, "1", generation, now, registered=True,
            configured=(None if declaration is None else declaration.configured),
            dependency_ready=(
                None if declaration is None else declaration.dependency_ready
            ),
            grantable=None, executable=None, healthy=None, degraded=None,
            scopes=scopes, display_name=definition.name,
        ))
    for declaration in declarations:
        if declaration.name in registered_names:
            continue
        records.append(CapabilityRecord(
            f"tool:{declaration.name}", "tool", "agent_tool", "agent.tool_registry",
            declaration.name, "1", generation, now, registered=False,
            configured=declaration.configured,
            dependency_ready=declaration.dependency_ready,
            executable=False,
            healthy=None,
            degraded=None,
            scopes=tuple(declaration.scopes),
            reason_code=declaration.reason_code or "not_registered",
            display_name=declaration.name,
        ))
    return records


def _stable_extension_snapshot(
    manager: Any,
) -> tuple[str, tuple[Any, ...], tuple[Any, ...]]:
    owner_snapshot = getattr(manager, "capability_inventory_snapshot", None)
    if callable(owner_snapshot):
        generation, lifecycle, registrations = owner_snapshot()
        return str(generation), tuple(lifecycle), tuple(registrations)
    from src.plugins.registry import EXTENSION_POINTS
    for _ in range(3):
        before = {
            point: manager.registration_snapshot_generation(point)
            for point in EXTENSION_POINTS
        }
        registrations = tuple(manager.enabled_registrations_snapshot())
        lifecycle = tuple(manager.list_snapshots())
        after = {
            point: manager.registration_snapshot_generation(point)
            for point in EXTENSION_POINTS
        }
        if before == after:
            generation = ",".join(f"{point}:{before[point]}" for point in sorted(before))
            return generation, lifecycle, registrations
    raise RuntimeError("extension registry generation drift")


def _extension_records(
    lifecycle: tuple[Any, ...],
    registrations: tuple[Any, ...],
    generation: str,
    now: str,
) -> list[CapabilityRecord]:
    records: list[CapabilityRecord] = []
    for snapshot in lifecycle:
        plugin_id = snapshot.manifest.id
        enabled = snapshot.state == "enabled" and bool(snapshot.desired_enabled)
        records.append(CapabilityRecord(
            f"extension.plugin:{plugin_id}", "extension", "plugin_lifecycle",
            "plugin.manager", plugin_id, str(getattr(snapshot.manifest, "version", "1")),
            generation, now, registered=True, executable=False,
            reason_code="lifecycle_not_capability" if enabled else "plugin_not_enabled",
            healthy=None, degraded=snapshot.state == "failed", display_name=snapshot.manifest.name,
        ))
    for registration in registrations:
        records.append(CapabilityRecord(
            f"extension.registration:{registration.extension_point}:{registration.registration_id}",
            "extension", "extension_registration", "plugin.registry",
            registration.plugin_id, str(registration.contract_version), generation, now,
            registered=True, executable=None, healthy=None, degraded=None,
            dependencies=(registration.extension_point,), display_name=registration.registration_id,
        ))
    return records
