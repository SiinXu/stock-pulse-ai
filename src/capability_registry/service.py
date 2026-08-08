# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only aggregation over existing capability registries."""

from __future__ import annotations

import importlib.util
import logging
from dataclasses import dataclass
from types import MappingProxyType, SimpleNamespace
from typing import Any, Callable, Iterable, Optional, Sequence

from src.capability_registry.models import (
    REASON_FEATURE_DISABLED,
    REASON_MISSING_CONFIG,
    REASON_MISSING_DEPENDENCY,
    REASON_NOT_REGISTERED,
    REASON_PLUGIN_DISABLED,
    REASON_PLUGIN_FAILED,
    CapabilityRecord,
)

logger = logging.getLogger(__name__)
DependencyProbe = Callable[[str], bool]
ConfigLike = Any

@dataclass(frozen=True, slots=True)
class _ProviderReadinessSpec:
    provider_id: str
    provider_name: str
    required_config_attrs: tuple[str, ...] = ()
    config_any_of_groups: tuple[tuple[str, ...], ...] = ()
    required_modules: tuple[str, ...] = ()
    config_env_hints: tuple[str, ...] = ()

_DATA_PROVIDER_SPECS: tuple[_ProviderReadinessSpec, ...] = (
    _ProviderReadinessSpec("efinance", "EfinanceFetcher"),
    _ProviderReadinessSpec("tencent", "TencentFetcher"),
    _ProviderReadinessSpec("akshare", "AkshareFetcher"),
    _ProviderReadinessSpec("tushare", "TushareFetcher", required_config_attrs=("tushare_token",), config_env_hints=("TUSHARE_TOKEN",)),
    _ProviderReadinessSpec("tickflow", "TickFlowFetcher", required_config_attrs=("tickflow_api_key",), required_modules=("tickflow",), config_env_hints=("TICKFLOW_API_KEY",)),
    _ProviderReadinessSpec("pytdx", "PytdxFetcher"),
    _ProviderReadinessSpec("baostock", "BaostockFetcher"),
    _ProviderReadinessSpec("yfinance", "YfinanceFetcher"),
    _ProviderReadinessSpec(
        "longbridge", "LongbridgeFetcher",
        config_any_of_groups=(("longbridge_app_key", "longbridge_app_secret", "longbridge_access_token"), ("longbridge_oauth_client_id",)),
        config_env_hints=("LONGBRIDGE_APP_KEY", "LONGBRIDGE_APP_SECRET", "LONGBRIDGE_ACCESS_TOKEN", "LONGBRIDGE_OAUTH_CLIENT_ID"),
    ),
    _ProviderReadinessSpec("finnhub", "FinnhubFetcher", required_config_attrs=("finnhub_api_key",), config_env_hints=("FINNHUB_API_KEY",)),
    _ProviderReadinessSpec("alphavantage", "AlphaVantageFetcher", required_config_attrs=("alphavantage_api_key",), config_env_hints=("ALPHAVANTAGE_API_KEY",)),
)

def _module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False
    except Exception:  # broad-exception: fallback_recorded - hostile module names stay unavailable
        logger.debug("dependency probe failed for module=%s", module_name, exc_info=True)
        return False

def _config_attr_present(config: ConfigLike, attr: str) -> bool:
    value = getattr(config, attr, None)
    if value is None:
        return False
    if type(value) is str:
        return bool(value.strip())
    return bool(value)

def _missing_required_config(config: ConfigLike, attrs: Sequence[str]) -> tuple[str, ...]:
    return tuple(attr for attr in attrs if not _config_attr_present(config, attr))

def _any_of_group_satisfied(config: ConfigLike, groups: Sequence[Sequence[str]]) -> bool:
    if not groups:
        return True
    for group in groups:
        if group and all(_config_attr_present(config, attr) for attr in group):
            return True
    return False

def _empty_config() -> SimpleNamespace:
    return SimpleNamespace(
        tushare_token=None, tickflow_api_key=None, finnhub_api_key=None, alphavantage_api_key=None,
        longbridge_app_key=None, longbridge_app_secret=None, longbridge_access_token=None,
        longbridge_oauth_client_id=None, multimodal_agent_tools_enabled=False, multimodal_file_root=None,
        valuation_agent_tool_enabled=False, kronos_enabled=False,
    )

def _resolve_config(config: ConfigLike | None) -> ConfigLike:
    if config is not None:
        return config
    try:
        from src.config import get_config
        return get_config()
    except Exception:  # broad-exception: fallback_recorded - view still returns static catalog
        logger.debug("capability registry could not load application config", exc_info=True)
        return _empty_config()

def _collect_data_records(*, config: ConfigLike, dependency_probe: DependencyProbe) -> list[CapabilityRecord]:
    from data_provider.plugin_registry import DATA_PROVIDER_CAPABILITY_METHODS
    records: list[CapabilityRecord] = []
    for capability_name in sorted(DATA_PROVIDER_CAPABILITY_METHODS):
        method_name = DATA_PROVIDER_CAPABILITY_METHODS[capability_name]
        records.append(CapabilityRecord(
            capability_id=f"data.capability:{capability_name}", domain="data",
            provider="data_provider.catalog", available=True, display_name=capability_name,
            details=MappingProxyType({"kind": "capability_method", "method_name": method_name}),
        ))
    for spec in _DATA_PROVIDER_SPECS:
        missing_modules = tuple(m for m in spec.required_modules if not dependency_probe(m))
        if missing_modules:
            records.append(CapabilityRecord(
                capability_id=f"data.provider:{spec.provider_id}", domain="data",
                provider=spec.provider_name, available=False, reason_code=REASON_MISSING_DEPENDENCY,
                reason_message=f"Optional dependency missing: {', '.join(missing_modules)}. Install the provider package to enable this data source.",
                display_name=spec.provider_name,
                details=MappingProxyType({"kind": "provider", "provider_id": spec.provider_id, "missing_modules": list(missing_modules), "config_env_hints": list(spec.config_env_hints)}),
            ))
            continue
        missing_config = _missing_required_config(config, spec.required_config_attrs)
        if missing_config or (spec.config_any_of_groups and not _any_of_group_satisfied(config, spec.config_any_of_groups)):
            hints = ", ".join(spec.config_env_hints) or ", ".join(missing_config or ("credentials",))
            records.append(CapabilityRecord(
                capability_id=f"data.provider:{spec.provider_id}", domain="data",
                provider=spec.provider_name, available=False, reason_code=REASON_MISSING_CONFIG,
                reason_message=f"Required configuration is missing for {spec.provider_name}. Set {hints} and restart to enable this data source.",
                display_name=spec.provider_name,
                details=MappingProxyType({"kind": "provider", "provider_id": spec.provider_id, "missing_config_attrs": list(missing_config), "config_env_hints": list(spec.config_env_hints)}),
            ))
            continue
        records.append(CapabilityRecord(
            capability_id=f"data.provider:{spec.provider_id}", domain="data",
            provider=spec.provider_name, available=True, display_name=spec.provider_name,
            details=MappingProxyType({"kind": "provider", "provider_id": spec.provider_id}),
        ))
    return records

def _tool_names(tool_registry: Any | None) -> set[str]:
    if tool_registry is None:
        return set()
    list_names = getattr(tool_registry, "list_names", None)
    if callable(list_names):
        try:
            return {str(n) for n in list_names()}
        except Exception:  # broad-exception: fallback_recorded - defensive aggregation boundary
            logger.debug("tool registry list_names failed", exc_info=True)
            return set()
    list_tools = getattr(tool_registry, "list_tools", None)
    if callable(list_tools):
        try:
            return {str(getattr(t, "name", "")) for t in list_tools() if getattr(t, "name", None)}
        except Exception:  # broad-exception: fallback_recorded - defensive aggregation boundary
            logger.debug("tool registry list_tools failed", exc_info=True)
            return set()
    return set()

def _list_tool_definitions(tool_registry: Any | None) -> list[Any]:
    if tool_registry is None:
        return []
    list_tools = getattr(tool_registry, "list_tools", None)
    if not callable(list_tools):
        return []
    try:
        return list(list_tools())
    except Exception:  # broad-exception: fallback_recorded - defensive aggregation boundary
        logger.debug("tool registry list_tools failed", exc_info=True)
        return []

def _collect_registered_tools(tool_registry: Any | None) -> list[CapabilityRecord]:
    records: list[CapabilityRecord] = []
    for tool_def in _list_tool_definitions(tool_registry):
        name = str(getattr(tool_def, "name", "") or "").strip()
        if not name:
            continue
        policy = getattr(tool_def, "policy", None)
        permissions = [str(i) for i in (getattr(policy, "permissions", None) or [])] if policy is not None else []
        records.append(CapabilityRecord(
            capability_id=f"tool:{name}", domain="tool", provider=name, available=True, display_name=name,
            details=MappingProxyType({"kind": "registered_tool", "category": str(getattr(tool_def, "category", "") or ""), "permissions": permissions}),
        ))
    return records

def _collect_optional_tool_readiness(*, config: ConfigLike, registered_names: set[str], dependency_probe: DependencyProbe) -> list[CapabilityRecord]:
    records: list[CapabilityRecord] = []
    multimodal_names = ("parse_financial_pdf", "read_price_chart")
    if not any(n in registered_names for n in multimodal_names):
        enabled = getattr(config, "multimodal_agent_tools_enabled", False) is True
        file_root = getattr(config, "multimodal_file_root", None)
        file_root_text = str(file_root).strip() if file_root is not None else ""
        if not enabled:
            records.append(CapabilityRecord(
                capability_id="tool.optional:multimodal", domain="tool", provider="multimodal_tools", available=False,
                reason_code=REASON_FEATURE_DISABLED,
                reason_message="Multimodal agent tools are disabled. Set MULTIMODAL_AGENT_TOOLS_ENABLED=true, configure MULTIMODAL_FILE_ROOT, and restart to opt in.",
                display_name="Multimodal Agent Tools",
                details=MappingProxyType({"kind": "optional_tool_group", "tools": list(multimodal_names), "flag": "MULTIMODAL_AGENT_TOOLS_ENABLED"}),
            ))
        elif not file_root_text:
            records.append(CapabilityRecord(
                capability_id="tool.optional:multimodal", domain="tool", provider="multimodal_tools", available=False,
                reason_code=REASON_MISSING_CONFIG,
                reason_message="MULTIMODAL_AGENT_TOOLS_ENABLED is true but MULTIMODAL_FILE_ROOT is empty. Set a local directory for user-provided PDF/chart files and restart.",
                display_name="Multimodal Agent Tools",
                details=MappingProxyType({"kind": "optional_tool_group", "tools": list(multimodal_names), "flag": "MULTIMODAL_AGENT_TOOLS_ENABLED", "missing_config": ["MULTIMODAL_FILE_ROOT"]}),
            ))
        else:
            records.append(CapabilityRecord(
                capability_id="tool.optional:multimodal", domain="tool", provider="multimodal_tools", available=False,
                reason_code=REASON_NOT_REGISTERED,
                reason_message="Multimodal tools are configured but not present in the live ToolRegistry (service init may have failed).",
                display_name="Multimodal Agent Tools",
                details=MappingProxyType({"kind": "optional_tool_group", "tools": list(multimodal_names)}),
            ))
    if "estimate_stock_valuation" not in registered_names:
        if getattr(config, "valuation_agent_tool_enabled", False) is not True:
            records.append(CapabilityRecord(
                capability_id="tool.optional:valuation", domain="tool", provider="valuation_tools", available=False,
                reason_code=REASON_FEATURE_DISABLED,
                reason_message="Valuation agent tool is disabled. Set VALUATION_AGENT_TOOL_ENABLED=true and restart to opt in.",
                display_name="Valuation Agent Tool",
                details=MappingProxyType({"kind": "optional_tool", "tool": "estimate_stock_valuation", "flag": "VALUATION_AGENT_TOOL_ENABLED"}),
            ))
    kronos_name = "forecast_kline_with_kronos"
    if kronos_name not in registered_names:
        try:
            from src.services.kronos_forecast_service import assess_kronos_availability
            availability = assess_kronos_availability(config, dependency_probe=dependency_probe)
            reason = str(getattr(availability, "reason", "") or "not_registered")
            message = str(getattr(availability, "message", "") or "")
            if reason == "disabled":
                code = REASON_FEATURE_DISABLED
            elif reason == "dependencies_missing":
                code = REASON_MISSING_DEPENDENCY
            elif reason in {"weights_dir_unconfigured", "weights_dir_invalid", "weights_dir_missing", "weights_incomplete", "weights_invalid", "model_size_invalid"}:
                code = REASON_MISSING_CONFIG
            else:
                code = REASON_NOT_REGISTERED
            records.append(CapabilityRecord(
                capability_id="tool.optional:kronos", domain="tool", provider="kronos_tools", available=False,
                reason_code=code,
                reason_message=message or "Kronos agent tool is not registered. Enable KRONOS_ENABLED and install local model artifacts to opt in.",
                display_name="Kronos Forecast Tool",
                details=MappingProxyType({"kind": "optional_tool", "tool": kronos_name, "assessed_reason": reason}),
            ))
        except Exception:  # broad-exception: fallback_recorded - defensive aggregation boundary
            logger.debug("kronos availability assessment failed", exc_info=True)
            if getattr(config, "kronos_enabled", False) is not True:
                records.append(CapabilityRecord(
                    capability_id="tool.optional:kronos", domain="tool", provider="kronos_tools", available=False,
                    reason_code=REASON_FEATURE_DISABLED,
                    reason_message="Kronos agent tool is disabled. Set KRONOS_ENABLED=true only after installing local model dependencies.",
                    display_name="Kronos Forecast Tool",
                    details=MappingProxyType({"kind": "optional_tool", "tool": kronos_name, "flag": "KRONOS_ENABLED"}),
                ))
    return records

def _collect_tool_capability_tokens(tool_registry: Any | None) -> list[CapabilityRecord]:
    from src.agent.tools.registry import SUPPORTED_AGENT_TOOL_CAPABILITIES
    declared: dict[str, list[str]] = {token: [] for token in sorted(SUPPORTED_AGENT_TOOL_CAPABILITIES)}
    for tool_def in _list_tool_definitions(tool_registry):
        name = str(getattr(tool_def, "name", "") or "").strip()
        policy = getattr(tool_def, "policy", None)
        if policy is None or not name:
            continue
        for permission in getattr(policy, "permissions", None) or []:
            token = str(permission)
            if token in declared:
                declared[token].append(name)
    records: list[CapabilityRecord] = []
    for token, providers in declared.items():
        if providers:
            records.append(CapabilityRecord(
                capability_id=f"tool.capability:{token}", domain="tool",
                provider=",".join(sorted(providers)), available=True, display_name=token,
                details=MappingProxyType({"kind": "tool_capability_token", "providers": sorted(providers)}),
            ))
        else:
            reason_code = REASON_NOT_REGISTERED
            reason_message = f"No registered agent tool currently declares capability {token!r}."
            if token == "multimodal:read":
                reason_code = REASON_FEATURE_DISABLED
                reason_message = "No tool declares multimodal:read. Enable MULTIMODAL_AGENT_TOOLS_ENABLED with MULTIMODAL_FILE_ROOT to register PDF/chart tools."
            elif token == "local_model:execute":
                reason_code = REASON_FEATURE_DISABLED
                reason_message = "No tool declares local_model:execute. Enable the Kronos (or other local-model) tool path to populate this capability."
            records.append(CapabilityRecord(
                capability_id=f"tool.capability:{token}", domain="tool",
                provider="tool_capability_catalog", available=False, reason_code=reason_code,
                reason_message=reason_message, display_name=token,
                details=MappingProxyType({"kind": "tool_capability_token", "providers": []}),
            ))
    return records

def _collect_extension_records(plugin_manager: Any | None) -> list[CapabilityRecord]:
    records: list[CapabilityRecord] = []
    if plugin_manager is None:
        return records
    list_snapshots = getattr(plugin_manager, "list_snapshots", None)
    if not callable(list_snapshots):
        return records
    try:
        snapshots = list(list_snapshots())
    except Exception:  # broad-exception: fallback_recorded - defensive aggregation boundary
        logger.debug("plugin manager list_snapshots failed", exc_info=True)
        return records
    for snapshot in snapshots:
        manifest = getattr(snapshot, "manifest", None)
        plugin_id = str(getattr(manifest, "id", None) or getattr(snapshot, "id", None) or "").strip()
        if not plugin_id:
            continue
        state = str(getattr(snapshot, "state", "") or "")
        desired_enabled = bool(getattr(snapshot, "desired_enabled", True))
        extension_points = [str(p) for p in (getattr(snapshot, "extension_points", ()) or ())]
        display_name = str(getattr(manifest, "name", None) or plugin_id)
        base_details = {"kind": "plugin", "state": state, "desired_enabled": desired_enabled, "extension_points": extension_points, "source": str(getattr(snapshot, "source", "") or "")}
        if state == "failed":
            records.append(CapabilityRecord(
                capability_id=f"extension.plugin:{plugin_id}", domain="extension", provider=plugin_id, available=False,
                reason_code=REASON_PLUGIN_FAILED,
                reason_message=f"Plugin {plugin_id!r} is in failed state and will not contribute extension points until repaired and reloaded.",
                display_name=display_name, details=MappingProxyType(base_details),
            ))
            continue
        if state == "disabled" or not desired_enabled:
            records.append(CapabilityRecord(
                capability_id=f"extension.plugin:{plugin_id}", domain="extension", provider=plugin_id, available=False,
                reason_code=REASON_PLUGIN_DISABLED,
                reason_message=f"Plugin {plugin_id!r} is disabled (state={state!r}, desired_enabled={desired_enabled}). Enable it via the plugin lifecycle API to load extensions.",
                display_name=display_name, details=MappingProxyType(base_details),
            ))
            continue
        if state in {"enabled", "registered"}:
            records.append(CapabilityRecord(
                capability_id=f"extension.plugin:{plugin_id}", domain="extension", provider=plugin_id, available=True,
                display_name=display_name, details=MappingProxyType(base_details),
            ))
        else:
            records.append(CapabilityRecord(
                capability_id=f"extension.plugin:{plugin_id}", domain="extension", provider=plugin_id, available=False,
                reason_code=REASON_NOT_REGISTERED,
                reason_message=f"Plugin {plugin_id!r} has unexpected state {state!r}.",
                display_name=display_name, details=MappingProxyType(base_details),
            ))
    registry = getattr(plugin_manager, "registry", None)
    snapshot_fn = getattr(registry, "registrations_snapshot", None) if registry else None
    if callable(snapshot_fn):
        try:
            registrations = list(snapshot_fn())
        except Exception:  # broad-exception: fallback_recorded - defensive aggregation boundary
            logger.debug("extension registrations_snapshot failed", exc_info=True)
            registrations = []
        for registration in registrations:
            point = str(getattr(registration, "extension_point", "") or "")
            reg_id = str(getattr(registration, "registration_id", "") or "")
            plugin_id = str(getattr(registration, "plugin_id", "") or "")
            if not point or not reg_id:
                continue
            records.append(CapabilityRecord(
                capability_id=f"extension.registration:{point}:{reg_id}", domain="extension",
                provider=plugin_id or reg_id, available=True, display_name=f"{point}/{reg_id}",
                details=MappingProxyType({
                    "kind": "extension_registration", "extension_point": point, "registration_id": reg_id,
                    "plugin_id": plugin_id, "contract_version": str(getattr(registration, "contract_version", "") or ""),
                    "priority": getattr(registration, "priority", None),
                }),
            ))
    return records

def collect_capability_records(
    *, config: ConfigLike | None = None, tool_registry: Any | None = None,
    plugin_manager: Any | None = None, dependency_probe: DependencyProbe | None = None,
    domains: Iterable[str] | None = None,
) -> list[CapabilityRecord]:
    """Aggregate a read-only capability view from existing registries."""
    resolved_config = _resolve_config(config)
    probe = dependency_probe or _module_available
    if tool_registry is None:
        try:
            from src.agent.runtime_assembly import get_tool_registry
            tool_registry = get_tool_registry()
        except Exception:  # broad-exception: fallback_recorded - defensive aggregation boundary
            logger.debug("capability registry could not resolve tool registry", exc_info=True)
            tool_registry = None
    if plugin_manager is None:
        try:
            from src.application_services import get_application_services
            plugin_manager = get_application_services().plugin_manager
        except Exception:  # broad-exception: fallback_recorded - defensive aggregation boundary
            logger.debug("capability registry could not resolve plugin manager", exc_info=True)
            plugin_manager = None
    allowed: Optional[set[str]] = None
    if domains is not None:
        allowed = {str(item).strip() for item in domains if str(item).strip()}
        unknown = allowed - {"data", "tool", "extension"}
        if unknown:
            raise ValueError(f"unsupported capability domains: {sorted(unknown)}")
    records: list[CapabilityRecord] = []
    if allowed is None or "data" in allowed:
        records.extend(_collect_data_records(config=resolved_config, dependency_probe=probe))
    if allowed is None or "tool" in allowed:
        registered_names = _tool_names(tool_registry)
        records.extend(_collect_registered_tools(tool_registry))
        records.extend(_collect_optional_tool_readiness(config=resolved_config, registered_names=registered_names, dependency_probe=probe))
        records.extend(_collect_tool_capability_tokens(tool_registry))
    if allowed is None or "extension" in allowed:
        records.extend(_collect_extension_records(plugin_manager))
    records.sort(key=lambda item: (item.domain, item.capability_id))
    return records
