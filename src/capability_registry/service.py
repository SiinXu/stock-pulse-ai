# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Owner-driven, read-only capability inventory snapshots."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional

from src.capability_registry.models import (
    MAX_RECORD_LIST_LENGTH,
    CapabilityRecord,
    CapabilitySnapshot,
    SourceStatus,
)
from src.utils.sanitize import log_safe_exception

Clock = Callable[[], datetime]
logger = logging.getLogger(__name__)

DATA_RUNTIME_OWNER = "data_provider.runtime"


class OwnerNotInitialized(RuntimeError):
    """The authoritative owner does not exist in this process yet."""

    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


class OwnerReadError(RuntimeError):
    """An authoritative owner exists but could not be read safely."""

    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


def collect_capability_records(
    *,
    data_provider_runtime: Any | None = None,
    tool_registry: Any | None = None,
    plugin_manager: Any | None = None,
    skill_catalog: Any | None = None,
    pipeline_stages: Any | None = None,
    domains: Iterable[str] | None = None,
    clock: Clock | None = None,
) -> CapabilitySnapshot:
    """Capture each authoritative owner once or expose an explicit source error.

    Availability is projected only from live owner registration and health
    state. Never fabricates a success snapshot from a static catalog or by
    constructing a substitute composition root.
    """
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
        except OwnerNotInitialized as exc:
            sources.append(SourceStatus(
                "data", "not_initialized", "unknown", now, exc.error_code,
            ))
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
        except OwnerNotInitialized as exc:
            sources.append(SourceStatus(
                "extension", "not_initialized", "unknown", now, exc.error_code,
            ))
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
    if "skill" in allowed:
        try:
            catalog = (
                skill_catalog if skill_catalog is not None else _resolve_skill_catalog()
            )
            generation, plugin_skills, declarative_skills = catalog
            generation_s = str(generation)
            records.extend(
                _skill_records(plugin_skills, declarative_skills, generation_s, now)
            )
            sources.append(SourceStatus("skill", "ok", generation_s, now))
        except OwnerNotInitialized as exc:
            sources.append(SourceStatus(
                "skill", "not_initialized", "unknown", now, exc.error_code,
            ))
        except OwnerReadError as exc:
            sources.append(SourceStatus(
                "skill", "error", "unknown", now, exc.error_code,
            ))
        except RuntimeError:
            sources.append(SourceStatus(
                "skill", "generation_drift", "unknown", now,
                "skill_generation_drift",
            ))
        except Exception as exc:  # broad-exception: fallback_recorded - expose source error
            log_safe_exception(
                logger, "Capability skill source unavailable", exc,
                error_code="capability_skill_source_unavailable",
            )
            sources.append(SourceStatus(
                "skill", "error", "unknown", now, "skill_source_unavailable",
            ))
    if "pipeline" in allowed:
        try:
            stages = (
                pipeline_stages
                if pipeline_stages is not None
                else _resolve_pipeline_stages()
            )
            generation, stage_names, bound_names = stages
            generation_s = str(generation)
            records.extend(_pipeline_records(stage_names, bound_names, generation_s, now))
            sources.append(SourceStatus("pipeline", "ok", generation_s, now))
        except OwnerNotInitialized as exc:
            sources.append(SourceStatus(
                "pipeline", "not_initialized", "unknown", now, exc.error_code,
            ))
        except OwnerReadError as exc:
            sources.append(SourceStatus(
                "pipeline", "error", "unknown", now, exc.error_code,
            ))
        except Exception as exc:  # broad-exception: fallback_recorded - expose source error
            log_safe_exception(
                logger, "Capability pipeline source unavailable", exc,
                error_code="capability_pipeline_source_unavailable",
            )
            sources.append(SourceStatus(
                "pipeline", "error", "unknown", now, "pipeline_source_unavailable",
            ))
    records.sort(key=lambda item: (item.domain, item.capability_id))
    return CapabilitySnapshot(sources=tuple(sources), items=tuple(records))


def _domains(domains: Iterable[str] | None) -> set[str]:
    all_domains = {"data", "tool", "extension", "skill", "pipeline"}
    allowed = set(all_domains) if domains is None else {
        str(item).strip() for item in domains
    }
    unknown = allowed - all_domains
    if unknown or not allowed:
        raise ValueError(f"unsupported capability domains: {sorted(unknown)}")
    return allowed


def _resolve_data_runtime() -> Any:
    """Return the runtime of the manager that actually serves this process.

    Precedence follows real ownership: the composition-root manager that the
    analysis pipeline and stock services use, then the process-shared Agent
    tool manager. Constructing a manager here would publish an inventory of an
    isolated owner that serves no caller, so absence is reported explicitly.
    """

    from src.application_services import get_installed_application_services
    services = get_installed_application_services()
    manager = None if services is None else services.data_fetcher_manager
    if manager is None:
        from src.agent.tools.data_tools import active_fetcher_manager
        manager = active_fetcher_manager()
    if manager is None:
        raise OwnerNotInitialized("data_runtime_not_initialized")
    return manager.data_provider_runtime


def _resolve_tool_registry() -> Any:
    from src.agent.runtime_assembly import get_tool_registry
    return get_tool_registry()


def _resolve_plugin_manager() -> Any:
    """Observe only the installed plugin manager; never install a default root."""

    from src.application_services import get_installed_application_services

    services = get_installed_application_services()
    if services is None:
        raise OwnerNotInitialized("application_services_not_initialized")
    return services.plugin_manager


def _data_records(active: Any, generation: str, now: str) -> list[CapabilityRecord]:
    records: list[CapabilityRecord] = []
    capability_providers: dict[str, list[str]] = {}
    for item in active:
        registration = item.registration
        provider_id = str(registration.provider_id)
        provider_name = str(getattr(item.provider, "name", provider_id))
        markets = tuple(sorted(registration.markets))
        capabilities = tuple(sorted(registration.capabilities))
        records.append(CapabilityRecord(
            f"data.provider:{provider_id}", "data", "data_provider",
            DATA_RUNTIME_OWNER, provider_id, "1", generation, now,
            registered=True, configured=None, dependency_ready=None,
            executable=None, healthy=None, degraded=None,
            markets=markets, providers=(provider_id,), provider_count=1,
            display_name=_bounded_display_name(provider_name),
        ))
        for capability in capabilities:
            capability_providers.setdefault(str(capability), []).append(provider_id)
    for capability, providers in capability_providers.items():
        # A method supplied by several providers keeps every identity in the
        # bounded ``providers`` list. The scalar names the owning runtime, so
        # no valid multi-provider inventory can overflow it.
        listed = tuple(sorted(providers))[:MAX_RECORD_LIST_LENGTH]
        truncated = len(providers) > len(listed)
        records.append(CapabilityRecord(
            f"data.method:{capability}", "data", "data_method",
            DATA_RUNTIME_OWNER, DATA_RUNTIME_OWNER, "1", generation, now,
            registered=True, configured=None, dependency_ready=None,
            executable=None, healthy=None, degraded=None,
            providers=listed, provider_count=len(providers),
            reason_code="provider_list_truncated" if truncated else None,
            display_name=_bounded_display_name(capability),
        ))
    return records


def _bounded_display_name(value: str) -> str:
    """Clamp the cosmetic label without ever dropping an identity field."""

    return value if len(value) <= 200 else f"{value[:197]}..."


def _stable_tool_snapshot(
    registry: Any,
) -> tuple[str, tuple[Any, ...], tuple[Any, ...]]:
    """Read the tool owner exactly once through its inventory contract."""

    generation, entries, declarations = registry.capability_inventory_snapshot()
    return str(generation), tuple(entries), tuple(declarations)


def _tool_records(
    entries: tuple[Any, ...],
    declarations: tuple[Any, ...],
    generation: str,
    now: str,
) -> list[CapabilityRecord]:
    records: list[CapabilityRecord] = []
    registered_names = {entry.name for entry in entries}
    declared_by_name = {
        declaration.name: declaration for declaration in declarations
    }
    for entry in entries:
        declaration = declared_by_name.get(entry.name)
        records.append(CapabilityRecord(
            f"tool:{entry.name}", "tool", "agent_tool", "agent.tool_registry",
            entry.name, str(entry.definition_version), generation, now,
            registered=True,
            configured=(None if declaration is None else declaration.configured),
            dependency_ready=(
                None if declaration is None else declaration.dependency_ready
            ),
            grantable=None, executable=None, healthy=None, degraded=None,
            scopes=tuple(entry.scopes), display_name=entry.name,
        ))
    for declaration in declarations:
        if declaration.name in registered_names:
            continue
        # An owner-supplied reason (missing config, construction failure) is the
        # truth. ``not_registered`` is used only when the owner gave no reason.
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
    """Read the plugin owner exactly once through its inventory contract.

    Correlating lifecycle and registrations here would duplicate the manager's
    locking and could not observe its lifecycle generation, so the projection
    has no second implementation of that correlation.
    """

    generation, lifecycle, registrations = manager.capability_inventory_snapshot()
    return str(generation), tuple(lifecycle), tuple(registrations)


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
        failed = snapshot.state == "failed"
        records.append(CapabilityRecord(
            f"extension.plugin:{plugin_id}", "extension", "plugin_lifecycle",
            "plugin.manager", plugin_id, str(getattr(snapshot.manifest, "version", "1")),
            generation, now, registered=True, executable=False,
            reason_code=(
                "lifecycle_not_capability" if enabled else (
                    "plugin_failed" if failed else "plugin_not_enabled"
                )
            ),
            healthy=(False if failed else True if enabled else None),
            degraded=failed,
            display_name=snapshot.manifest.name,
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


def _resolve_skill_catalog() -> tuple[int, tuple[Any, ...], tuple[Any, ...]]:
    """Read plugin analysis strategies and declarative skills from live owners."""

    from src.application_services import get_installed_application_services

    services = get_installed_application_services()
    if services is None:
        raise OwnerNotInitialized("application_services_not_initialized")
    try:
        snapshot = services.analysis_strategy_snapshot()
    except Exception as exc:  # broad-exception: fallback_recorded - owner read failed
        raise OwnerReadError("skill_catalog_unavailable") from exc
    try:
        config = services.config
    except Exception as exc:  # broad-exception: fallback_recorded - config read failed
        raise OwnerReadError("skill_config_unavailable") from exc
    try:
        from src.agent.skills.base import SkillManager

        skill_manager = SkillManager()
        custom_dir = getattr(config, "agent_skill_dir", None)
        if custom_dir:
            skill_manager.load_custom_skills(custom_dir)
        declarative = tuple(skill_manager.list_skills())
    except OwnerReadError:
        raise
    except Exception as exc:  # broad-exception: fallback_recorded - catalog load failed
        raise OwnerReadError("skill_catalog_unavailable") from exc
    plugin_skills = tuple(snapshot.registrations)
    generation = (int(snapshot.generation) << 16) ^ len(declarative)
    return generation, plugin_skills, declarative


def _resolve_pipeline_stages() -> tuple[str, tuple[str, ...], frozenset[str]]:
    """Read pipeline stages from the shared owner contract (not a copied list)."""

    try:
        from src.core.pipeline import StockAnalysisPipeline
        from src.core.pipeline_stage_results import PipelineStageName
        from src.services.run_diagnostics import PIPELINE_STAGE_NAMES
    except Exception as exc:  # broad-exception: fallback_recorded - owner import failed
        raise OwnerReadError("pipeline_source_unavailable") from exc
    if StockAnalysisPipeline is None:  # pragma: no cover - defensive
        raise OwnerReadError("pipeline_source_unavailable")
    stage_names = tuple(str(name) for name in PIPELINE_STAGE_NAMES)
    if not stage_names:
        raise OwnerReadError("pipeline_source_unavailable")
    enum_names = {member.value for member in PipelineStageName}
    bound = frozenset(name for name in stage_names if name in enum_names)
    return ",".join(stage_names), stage_names, bound


def _bounded_dependencies(values: Any) -> tuple[str, ...]:
    cleaned: list[str] = []
    for item in values:
        text_item = str(item).strip()
        if text_item and len(text_item) <= 128:
            cleaned.append(text_item)
        if len(cleaned) >= MAX_RECORD_LIST_LENGTH:
            break
    return tuple(cleaned)


def _skill_records(
    plugin_skills: tuple[Any, ...],
    declarative_skills: tuple[Any, ...],
    generation: str,
    now: str,
) -> list[CapabilityRecord]:
    records: list[CapabilityRecord] = []
    seen: set[str] = set()
    for item in plugin_skills:
        definition = item.definition
        name = str(definition.name)
        seen.add(name)
        enabled = bool(getattr(definition, "default_active", False)) or bool(
            getattr(definition, "user_invocable", False)
        )
        records.append(CapabilityRecord(
            f"skill:{name}", "skill", "analysis_skill",
            "plugin.analysis_strategy_registry", str(item.plugin_id), "1",
            generation, now,
            registered=True,
            configured=True,
            executable=None if enabled else False,
            healthy=True,
            degraded=False,
            reason_code=None if enabled else "skill_not_default_active",
            display_name=_bounded_display_name(
                str(getattr(definition, "display_name", name) or name)
            ),
            dependencies=_bounded_dependencies(
                getattr(definition, "required_tools", ())
            ),
        ))
    for skill in declarative_skills:
        name = str(getattr(skill, "name", "") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        enabled = bool(getattr(skill, "enabled", True))
        records.append(CapabilityRecord(
            f"skill:{name}", "skill", "analysis_skill",
            "agent.skill_manager", str(getattr(skill, "source", "custom") or "custom"),
            "1", generation, now,
            registered=True,
            configured=True,
            executable=None if enabled else False,
            healthy=True if enabled else False,
            degraded=not enabled,
            reason_code=None if enabled else "skill_disabled",
            display_name=_bounded_display_name(
                str(getattr(skill, "display_name", name) or name)
            ),
            dependencies=_bounded_dependencies(
                getattr(skill, "required_tools", None) or ()
            ),
        ))
    return records


def _pipeline_records(
    stage_names: tuple[str, ...],
    bound_names: frozenset[str],
    generation: str,
    now: str,
) -> list[CapabilityRecord]:
    records: list[CapabilityRecord] = []
    for name in stage_names:
        registered = name in bound_names
        records.append(CapabilityRecord(
            f"pipeline.stage:{name}", "pipeline", "pipeline_stage",
            "core.pipeline", name, "1", generation, now,
            registered=registered,
            configured=True if registered else None,
            executable=None if registered else False,
            healthy=True if registered else False,
            degraded=not registered,
            reason_code=None if registered else "stage_not_bound",
            display_name=name,
        ))
    return records

